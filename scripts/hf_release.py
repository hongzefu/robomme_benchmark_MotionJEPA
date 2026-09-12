"""把注入专项运行的产物发布成 Hugging Face 公开 dataset 的全链路脚本。

链路按子命令切成八步，每步只做一件事、各自落一份 ``.release/*.json`` 断点，
后一步靠前一步的断点做**顺序守卫**（缺前置产物直接 :class:`ReleaseError`）：

``plan``          只算不落盘：展开 28 个归档、统计视频与小产物、估算压缩后体积。
``pack``          按组把 h5 打成 ``.tar.xz``（h5 只读，``tar -cf -`` 读取后管道给 ``xz``）。
``stage``         视频硬链接进 staging、小产物复制进 ``meta/``。
``manifest``      写 ``MANIFEST.json`` / ``SHA256SUMS`` / ``README.md`` / ``tarxz_h5.py`` 并冻结归档。
``verify-local``  本地流式复核：归档自身散列 + 逐成员 h5 散列对 MANIFEST。
``upload``        ``upload_large_folder`` 推到 HF dataset 仓库。
``verify-remote`` 用 ``list_repo_tree`` 的 LFS sha256 / blob sha1 与本地逐文件比对。
``verify-sample`` 抽样回下载，重新解包核验成员散列。

**只读铁律**：h5 与 mp4 全程不合并、不改内容、不重命名；打包只读取原文件，
视频进 staging 用硬链接（同一 inode，不产生副本也不改原件）。
``MANIFEST.json`` 里的 ``h5_sha256`` **逐字抄自交付清单**，本脚本绝不重算 h5 散列。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

# 本文件位于 scripts/ 下，向上一级就是仓库根；与 campaign.py 同样把根与 src 插进 sys.path，
# 这样既能 `python scripts/hf_release.py` 直跑，也能 `from scripts.hf_release import ...`。
REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (REPO_ROOT, REPO_ROOT / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from scripts.injection.delivery import render_verdict_line  # noqa: E402

#: 默认发布的运行编号。
DEFAULT_RUN_ID = "20260912-contract-v3-10"
#: 默认 HF dataset 仓库。
DEFAULT_REPO_ID = "HongzeFu/robomme-4task-h5-20260912-v2"
#: 正式（primary）与备件（spare）h5 所在的档目录名。
PRIMARY_MODE_DIR = "P01x20"
#: smoke 档目录名（只有 RouteStick/easy 一条）。
SMOKE_MODE_DIR = "P0x1"
#: smoke 那条固定是 RouteStick/easy。
SMOKE_TASK = "RouteStick"
SMOKE_DIFFICULTY = "easy"
#: 交付清单必须满足的三条硬指标（对不上说明换了运行或清单被改）。
EXPECTED_GROUPS = 14
EXPECTED_PRIMARY = 1600
EXPECTED_SPARE = 196
#: 估算压缩后体积用的压缩比（h5 实测 8× 量级）。
EST_COMPRESS_RATIO = 8.0
#: 读取大文件时的分块大小。
CHUNK = 1 << 22
#: 仓库自身的 git 远端（私有仓库，README 里照放链接）。
GIT_REMOTE_URL = "https://github.com/hongzefu/robomme_benchmark_MotionJEPA"
#: 上传时永远排除的本地断点／旁车文件。
UPLOAD_IGNORE = [".release/**", ".cache/**", "**/.sha256", "*.sha256"]


class ReleaseError(RuntimeError):
    """发布链路的硬失败：宁可停，也不静默修正。"""


# ── 数据结构 ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ReleaseLayout:
    """一次发布涉及的全部路径与身份信息。"""

    repo_id: str
    run_id: str
    run_root: Path
    staging: Path
    repo_root: Path
    git_commit: str | None = None
    git_branch: str | None = None

    @property
    def release_dir(self) -> Path:
        """断点目录 ``staging/.release/``（不上传）。"""
        return self.staging / ".release"


@dataclass(frozen=True)
class ArchivePlan:
    """一个 ``.tar.xz`` 归档的完整计划（纯数据，不碰磁盘）。"""

    task: str
    difficulty: str
    role: str  # primary / spare / smoke
    rows: tuple[dict, ...]
    rel_path: str
    top_dir: str
    source_dir: Path
    members: tuple[tuple[Path, str], ...]  # (源绝对路径, 包内路径)

    @property
    def raw_bytes(self) -> int:
        """包内 h5 原始体积合计（不含 metadata.json，量级可忽略）。"""
        return sum(int(row.get("bytes") or 0) for row in self.rows)


@dataclass(frozen=True)
class ArchiveResult:
    """一个归档实际打出来的结果。"""

    rel_path: str
    bytes: int
    sha256: str
    member_count: int
    xz_preset: int
    xz_threads: int
    wall_s: float

    def to_dict(self) -> dict:
        return {
            "rel_path": self.rel_path, "bytes": self.bytes, "sha256": self.sha256,
            "member_count": self.member_count, "xz_preset": self.xz_preset,
            "xz_threads": self.xz_threads, "wall_s": round(self.wall_s, 3),
        }


@dataclass(frozen=True)
class StagedFile:
    """staging 里的一个文件（归档／视频／小产物／文档）。"""

    rel_path: str
    src: Path | None
    bytes: int
    sha256: str
    kind: str  # archive / video / meta / doc

    def to_dict(self) -> dict:
        return {
            "rel_path": self.rel_path, "src": str(self.src) if self.src else None,
            "bytes": self.bytes, "sha256": self.sha256, "kind": self.kind,
        }


# ── 基础工具 ────────────────────────────────────────────────────────────────
def sha256_file(path: Path) -> str:
    """分块算文件 sha256（大 h5 也不会吃内存）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(data: bytes) -> str:
    """按 git 的 blob 口径算 sha1（``blob <len>\\0<data>``），用于和远端 ``blob_id`` 比对。"""
    digest = hashlib.sha1()
    digest.update(b"blob %d\0" % len(data))
    digest.update(data)
    return digest.hexdigest()


def _git_describe(repo_root: Path) -> tuple[str | None, str | None]:
    """取当前 commit 与分支名；不是 git 仓库时返回 (None, None)。"""
    def _run(args: list[str]) -> str | None:
        try:
            out = subprocess.run(
                ["git", "-C", str(repo_root), *args],
                capture_output=True, text=True, timeout=20, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        value = out.stdout.strip()
        return value if out.returncode == 0 and value else None

    return _run(["rev-parse", "HEAD"]), _run(["rev-parse", "--abbrev-ref", "HEAD"])


def make_layout(
    run_id: str = DEFAULT_RUN_ID,
    repo_id: str = DEFAULT_REPO_ID,
    staging: Path | str | None = None,
    repo_root: Path | str = REPO_ROOT,
) -> ReleaseLayout:
    """按运行编号与仓库名拼出 :class:`ReleaseLayout`（staging 默认在 ``artifacts/hf-staging/<repo 名>``）。"""
    root = Path(repo_root).resolve()
    run_root = root / "artifacts" / "injection" / run_id
    staging_path = Path(staging).resolve() if staging else root / "artifacts" / "hf-staging" / repo_id.split("/")[-1]
    commit, branch = _git_describe(root)
    return ReleaseLayout(
        repo_id=repo_id, run_id=run_id, run_root=run_root, staging=staging_path,
        repo_root=root, git_commit=commit, git_branch=branch,
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReleaseError(f"找不到 {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseError(f"{path} 不是合法 JSON：{exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ReleaseError(f"找不到 {path}") from exc
    for line in text.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


# ── 交付清单 ────────────────────────────────────────────────────────────────
def load_delivery(run_root: Path | str) -> dict:
    """读 ``delivery_manifest.json`` 并硬校验四条前提：判定通过、全量散列、14 组、1600+196 条。"""
    run_root = Path(run_root)
    delivery = _read_json(run_root / "delivery_manifest.json")
    if not delivery.get("passed"):
        raise ReleaseError("交付清单 passed=False，不允许发布")
    if delivery.get("hash_mode") != "full":
        raise ReleaseError(f"交付清单 hash_mode={delivery.get('hash_mode')!r}，发布要求 full（每条 h5 都要有 sha256）")
    groups = delivery.get("groups") or {}
    if len(groups) != EXPECTED_GROUPS:
        raise ReleaseError(f"交付清单有 {len(groups)} 组，期望 {EXPECTED_GROUPS} 组")
    primary = sum(len(group.get("primary") or []) for group in groups.values())
    spare = sum(len(group.get("spare_rows") or []) for group in groups.values())
    if primary != EXPECTED_PRIMARY:
        raise ReleaseError(f"primary 合计 {primary} 条，期望 {EXPECTED_PRIMARY} 条")
    if spare != EXPECTED_SPARE:
        raise ReleaseError(f"spare 合计 {spare} 条，期望 {EXPECTED_SPARE} 条")
    return delivery


def archive_rel_path(task: str, difficulty: str, role: str) -> str:
    """归档在 staging 里的相对路径（primary 在根、spare 在 ``spare/``、smoke 在 ``smoke/``）。"""
    if role == "primary":
        return f"record_dataset_{task}_{difficulty}.h5.tar.xz"
    if role == "spare":
        return f"spare/record_dataset_{task}_{difficulty}_spare.h5.tar.xz"
    if role == "smoke":
        return f"smoke/record_dataset_{task}_{difficulty}_smoke.h5.tar.xz"
    raise ReleaseError(f"未知 role={role!r}（只认 primary/spare/smoke）")


def archive_top_dir(task: str, difficulty: str, role: str) -> str:
    """归档解开后的顶层目录名。"""
    suffix = {"primary": "", "spare": "_spare", "smoke": "_smoke"}
    if role not in suffix:
        raise ReleaseError(f"未知 role={role!r}（只认 primary/spare/smoke）")
    return f"record_dataset_{task}_{difficulty}{suffix[role]}"


def member_path(top_dir: str, h5_name: str) -> str:
    """拼包内成员路径 ``<top_dir>/hdf5_files/<名>``，并拒掉一切能把文件写到包外的名字。"""
    for name, value in (("top_dir", top_dir), ("h5_name", h5_name)):
        if not value or not value.strip():
            raise ReleaseError(f"{name} 不能为空")
        if value.startswith("/"):
            raise ReleaseError(f"{name}={value!r} 不能是绝对路径")
        if ".." in Path(value).parts:
            raise ReleaseError(f"{name}={value!r} 不能含 ..")
    if "/" in h5_name:
        raise ReleaseError(f"h5_name={h5_name!r} 必须是纯文件名，不能含 /")
    if "/" in top_dir:
        raise ReleaseError(f"top_dir={top_dir!r} 必须是单层目录名，不能含 /")
    return f"{top_dir}/hdf5_files/{h5_name}"


def group_source_dir(run_root: Path, task: str, difficulty: str, role: str) -> Path:
    """一组 h5 在运行根下的源目录。"""
    mode = SMOKE_MODE_DIR if role == "smoke" else PRIMARY_MODE_DIR
    return run_root / "feasibility" / mode / task / difficulty


def group_metadata_name(task: str) -> str:
    return f"record_dataset_{task}_metadata.json"


def _smoke_rows(run_root: Path, *, check_exists: bool) -> list[dict]:
    """把 P0x1 的 ``episode_results.jsonl`` 拼成一条和交付清单同形的记录。

    P0x1 的 jsonl 只记了 h5 路径与 timestep，没有 h5 sha256；``check_exists`` 打开时就地
    算一次，并在 ``sha256_source`` 里注明来源是「现算」而不是交付清单。
    """
    rows = _read_jsonl(run_root / "feasibility" / SMOKE_MODE_DIR / "episode_results.jsonl")
    picked = [
        row for row in rows
        if row.get("ok") and row.get("h5_path")
        and row.get("task") == SMOKE_TASK and row.get("difficulty") == SMOKE_DIFFICULTY
    ]
    if not picked:
        raise ReleaseError(f"{SMOKE_MODE_DIR} 里没有可用的 {SMOKE_TASK}/{SMOKE_DIFFICULTY} 通过条")
    row = min(picked, key=lambda item: int(item["episode"]))
    h5_path = Path(row["h5_path"])
    sha = row.get("h5_sha256") or (row.get("h5") or {}).get("sha256")
    source = "P0x1/episode_results.jsonl"
    if not sha and check_exists:
        if not h5_path.exists():
            raise ReleaseError(f"smoke h5 不存在：{h5_path}")
        sha = sha256_file(h5_path)
        source = "现算（P0x1 的 episode_results.jsonl 未记 h5 sha256）"
    try:
        size = h5_path.stat().st_size
    except OSError:
        size = 0
    return [{
        "task": SMOKE_TASK, "difficulty": SMOKE_DIFFICULTY, "episode": int(row["episode"]),
        "seed": row.get("seed"),
        "spec_sha256": (row.get("injection_evidence") or {}).get("spec_sha256"),
        "h5_path": str(h5_path), "bytes": size, "sha256": sha,
        "timestep_count": row.get("timestep_count"),
        "video_status": (row.get("video") or {}).get("status"),
        "role": "smoke", "sha256_source": source,
    }]


def plan_archives(
    delivery: dict,
    run_root: Path | str,
    *,
    include_spare: bool = True,
    include_smoke: bool = True,
    check_exists: bool = True,
) -> list[ArchivePlan]:
    """把交付清单展开成归档计划：每组 primary 一包、spare 一包，另加 smoke 一包。

    组序沿用交付清单（即 ``delivery_400.json`` 的组序），组内 rows 按 episode 升序；
    同一 (任务, 难度, episode) 只允许出现在一个包里。
    """
    run_root = Path(run_root)
    plans: list[ArchivePlan] = []
    # 唯一性按「档目录 + 任务 + 难度 + episode」判：smoke 来自另一个档（P0x1），
    # 与 P01x20 的同名 episode 是两次独立实跑，不算重复。
    seen: dict[tuple[str, str, str, int], str] = {}
    groups: dict[str, dict] = delivery.get("groups") or {}
    roles = ["primary", "spare"] if include_spare else ["primary"]
    for key, group in groups.items():
        task, difficulty = key.split("/", 1)
        for role in roles:
            rows = list(group.get("primary" if role == "primary" else "spare_rows") or [])
            if not rows:
                continue
            plans.append(_make_plan(task, difficulty, role, rows, run_root, seen, check_exists))
    if include_smoke:
        plans.append(_make_plan(
            SMOKE_TASK, SMOKE_DIFFICULTY, "smoke",
            _smoke_rows(run_root, check_exists=check_exists), run_root, seen, check_exists,
        ))
    return plans


def _make_plan(
    task: str, difficulty: str, role: str, rows: list[dict],
    run_root: Path, seen: dict[tuple[str, str, str, int], str], check_exists: bool,
) -> ArchivePlan:
    rows = sorted(rows, key=lambda row: int(row["episode"]))
    rel_path = archive_rel_path(task, difficulty, role)
    top_dir = archive_top_dir(task, difficulty, role)
    source_dir = group_source_dir(run_root, task, difficulty, role)
    members: list[tuple[Path, str]] = []
    for row in rows:
        key = (SMOKE_MODE_DIR if role == "smoke" else PRIMARY_MODE_DIR, task, difficulty, int(row["episode"]))
        if key in seen:
            raise ReleaseError(f"episode 重复归包：{key} 同时出现在 {seen[key]} 与 {rel_path}")
        seen[key] = rel_path
        name = Path(str(row["h5_path"])).name
        src = source_dir / "hdf5_files" / name
        if check_exists and not src.is_file():
            raise ReleaseError(f"h5 不存在：{src}")
        members.append((src, member_path(top_dir, name)))
    meta_name = group_metadata_name(task)
    meta_src = source_dir / meta_name
    if check_exists and not meta_src.is_file():
        raise ReleaseError(f"组 metadata 不存在：{meta_src}")
    members.append((meta_src, f"{top_dir}/{meta_name}"))
    return ArchivePlan(
        task=task, difficulty=difficulty, role=role, rows=tuple(rows),
        rel_path=rel_path, top_dir=top_dir, source_dir=source_dir, members=tuple(members),
    )


# ── 视频与小产物 ────────────────────────────────────────────────────────────
#: mp4 文件名主体形如 ``<任务>_ep<号>_seed<seed>_...``；「无物体」对照渲染在最前面多一层前缀，
#: 实测两种：成功条的 ``success_NO_OBJECT_`` 与失败条的 ``FAILED_NO_OBJECT_``。
NO_OBJECT_PREFIXES = ("success_NO_OBJECT_", "FAILED_NO_OBJECT_")


def is_no_object_video(name: str) -> bool:
    """文件名是否是「无物体」对照渲染。"""
    return name.startswith(NO_OBJECT_PREFIXES)


def parse_video_name(name: str) -> tuple[str, int, int] | None:
    """从 mp4 文件名解析 ``(任务, episode, seed)``；解析不出来返回 ``None``。"""
    stem = name
    for prefix in NO_OBJECT_PREFIXES:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    parts = stem.split("_")
    for index in range(1, len(parts) - 1):
        if parts[index].startswith("ep") and parts[index + 1].startswith("seed"):
            try:
                episode = int(parts[index][2:])
                seed = int(parts[index + 1][4:])
            except ValueError:
                continue
            return "_".join(parts[:index]), episode, seed
    return None


def _video_digest_index(run_root: Path, mode: str) -> dict[str, dict]:
    """从该档的 ``episode_results.jsonl`` 建「mp4 绝对路径 → {bytes, sha256}」索引。"""
    index: dict[str, dict] = {}
    jsonl = run_root / "feasibility" / mode / "episode_results.jsonl"
    if not jsonl.is_file():
        return index
    for row in _read_jsonl(jsonl):
        video = row.get("video") or {}
        if video.get("path"):
            index[os.path.abspath(video["path"])] = {
                "bytes": video.get("bytes"), "sha256": video.get("sha256"),
            }
        for extra in video.get("no_object_paths") or []:
            # 「无物体」变体的散列 jsonl 未单列，stage 时现算。
            index.setdefault(os.path.abspath(extra), {"bytes": None, "sha256": None})
    return index


def plan_videos(run_root: Path | str, mode: str = "files", include_smoke: bool = True) -> list[dict]:
    """枚举要随发布带走的 mp4。

    ``mode``：

    * ``files`` —— 逐个 mp4 硬链接进 ``videos/<任务>/<难度>/<原名>``（smoke 的进 ``smoke/videos/...``）；
    * ``tar``   —— 每组打一个**未压缩** ``videos/record_video_<任务>_<难度>.tar``（mp4 本身已压缩，再压无益）；
    * ``skip``  —— 不带视频。

    散列优先取 ``episode_results.jsonl`` 的 ``video.sha256``，取不到的留 ``None``、stage 时现算。
    """
    if mode not in ("files", "tar", "skip"):
        raise ReleaseError(f"未知视频模式 {mode!r}（只认 files/tar/skip）")
    run_root = Path(run_root)
    if mode == "skip":
        return []
    entries: list[dict] = []
    modes = [(PRIMARY_MODE_DIR, "videos", False)] + ([(SMOKE_MODE_DIR, "smoke/videos", True)] if include_smoke else [])
    for mode_dir, prefix, is_smoke in modes:
        index = _video_digest_index(run_root, mode_dir)
        base = run_root / "feasibility" / mode_dir
        for path in sorted(base.glob("*/*/videos/*.mp4")):
            difficulty = path.parent.parent.name
            task = path.parent.parent.parent.name
            parsed = parse_video_name(path.name)
            digests = index.get(os.path.abspath(str(path)), {})
            entries.append({
                "rel_path": f"{prefix}/{task}/{difficulty}/{path.name}",
                "src": path, "task": task, "difficulty": difficulty,
                "episode": parsed[1] if parsed else None,
                "seed": parsed[2] if parsed else None,
                "bytes": digests.get("bytes"), "sha256": digests.get("sha256"),
                "no_object": is_no_object_video(path.name),
                "smoke": is_smoke,
            })
    if mode == "files":
        return entries
    # tar 模式：每组合成一个未压缩 tar 条目，成员保持 <任务>/<难度>/<原名>。
    grouped: dict[tuple[str, str, bool], list[dict]] = {}
    for entry in entries:
        grouped.setdefault((entry["task"], entry["difficulty"], entry["smoke"]), []).append(entry)
    tars: list[dict] = []
    for (task, difficulty, is_smoke), items in grouped.items():
        prefix = "smoke/videos" if is_smoke else "videos"
        tars.append({
            "rel_path": f"{prefix}/record_video_{task}_{difficulty}.tar",
            "task": task, "difficulty": difficulty, "smoke": is_smoke,
            "members": [(item["src"], f"{task}/{difficulty}/{item['src'].name}") for item in items],
            "entries": items,
        })
    return tars


#: ``meta/`` 下要带走的小产物：运行根下的固定文件 + 通配目录。
META_FILES = (
    "delivery_manifest.json", "check_result.json", "manifest.json", "plan_stats.json",
    "feasibility_result.json", "feasibility_result_P01x20.json", "feasibility_result_P0x1.json",
    "feasibility_results.json", "env_check_result.json", "env_check_result_smoke.json",
)
META_GLOBS = (
    "specs/*/*.json", "env_check/**/*.jsonl", "manifests/*.json", "logs/*.log",
    "feasibility/P01x20/run_parameters.json", "feasibility/P01x20/run_summary.json",
    "feasibility/P01x20/sampling_config_used.json",
    "feasibility/P01x20/*/*/record_dataset_*_metadata.json",
    "feasibility/P0x1/run_parameters.json", "feasibility/P0x1/run_summary.json",
    "feasibility/P0x1/sampling_config_used.json",
    "feasibility/P0x1/*/*/record_dataset_*_metadata.json",
)
#: 跟着一起带走的配置副本（落 ``meta/configs/``）。
META_CONFIGS = (
    "scripts/configs/newtask-v2/injection_contract_v3.json",
    "scripts/configs/newtask-v2/delivery_400.json",
)


def plan_meta(run_root: Path | str, repo_root: Path | str = REPO_ROOT) -> list[dict]:
    """枚举 ``meta/`` 下的小产物：运行根内保持原相对路径，配置副本进 ``meta/configs/``。"""
    run_root = Path(run_root)
    repo_root = Path(repo_root)
    picked: dict[str, Path] = {}
    for name in META_FILES:
        path = run_root / name
        if path.is_file():
            picked[f"meta/{name}"] = path
    for pattern in META_GLOBS:
        for path in sorted(run_root.glob(pattern)):
            if path.is_file():
                picked[f"meta/{path.relative_to(run_root).as_posix()}"] = path
    for name in META_CONFIGS:
        path = repo_root / name
        if path.is_file():
            picked[f"meta/configs/{Path(name).name}"] = path
    return [{"rel_path": rel, "src": src} for rel, src in sorted(picked.items())]


# ── MANIFEST / SHA256SUMS / README ──────────────────────────────────────────
def build_manifest(
    layout: ReleaseLayout,
    delivery: dict,
    plans: Sequence[ArchivePlan],
    archive_results: dict[str, dict],
    videos: Sequence[dict],
    files: Sequence[StagedFile],
    packing: dict,
    *,
    generated_utc: str | None = None,
) -> dict:
    """拼 ``MANIFEST.json``。

    ``episodes[].h5_sha256`` **逐字来自交付清单**（smoke 那条来自 P0x1 的记录），
    本函数绝不打开 h5 重算；任何一条缺 sha256 直接 :class:`ReleaseError`。
    """
    video_by_episode: dict[tuple[str, str, int], list[str]] = {}
    video_rows: list[dict] = []
    for entry in videos:
        rel = entry["rel_path"]
        key = (entry["task"], entry["difficulty"], entry["episode"])
        if entry["episode"] is not None:
            video_by_episode.setdefault(key, []).append(rel)
        video_rows.append({
            "path": rel, "task": entry["task"], "difficulty": entry["difficulty"],
            "episode": entry["episode"], "bytes": entry.get("bytes"), "sha256": entry.get("sha256"),
        })
    for rels in video_by_episode.values():
        rels.sort()

    archives: list[dict] = []
    episodes: list[dict] = []
    counts = {"primary": 0, "spare": 0, "smoke": 0}
    for plan in plans:
        result = archive_results.get(plan.rel_path, {})
        archives.append({
            "path": plan.rel_path, "role": plan.role, "task": plan.task, "difficulty": plan.difficulty,
            "bytes": result.get("bytes"), "sha256": result.get("sha256"),
            "member_count": result.get("member_count", len(plan.members)),
        })
        counts[plan.role] = counts.get(plan.role, 0) + len(plan.rows)
        for row in plan.rows:
            sha = row.get("sha256")
            if not sha:
                raise ReleaseError(
                    f"交付清单缺 h5 sha256：{plan.task}/{plan.difficulty} episode={row.get('episode')}"
                    "（发布要求 hash_mode=full，本脚本不重算 h5 散列）"
                )
            name = Path(str(row["h5_path"])).name
            episodes.append({
                "task": plan.task, "difficulty": plan.difficulty, "episode": int(row["episode"]),
                "seed": row.get("seed"), "role": plan.role, "spec_sha256": row.get("spec_sha256"),
                "archive": plan.rel_path, "member": member_path(plan.top_dir, name),
                "h5_sha256": sha, "h5_bytes": row.get("bytes"),
                "timestep_count": row.get("timestep_count"),
                # smoke 档与正式档的 ep0 同名前缀会互相匹配：按角色只取各自前缀下的视频
                "videos": [
                    rel for rel in video_by_episode.get((plan.task, plan.difficulty, int(row["episode"])), [])
                    if rel.startswith("smoke/") == (plan.role == "smoke")
                ],
            })

    failures: list[dict] = []
    for key, group in (delivery.get("groups") or {}).items():
        task, difficulty = key.split("/", 1)
        for row in group.get("failures") or []:
            episode = row.get("episode")
            failures.append({
                "task": task, "difficulty": difficulty, "episode": episode,
                "outcome": row.get("outcome"), "error_type": row.get("error_type"),
                "videos": [rel for rel in video_by_episode.get((task, difficulty, episode), []) if not rel.startswith("smoke/")],
            })

    delivery_path = layout.run_root / "delivery_manifest.json"
    config_info = delivery.get("config") or {}
    contract_sha = None
    config_file = layout.repo_root / "scripts" / "configs" / "newtask-v2" / "delivery_400.json"
    if config_file.is_file():
        contract_sha = (_read_json(config_file) or {}).get("contract_sha256")

    return {
        "schema_version": 1,
        "repo_id": layout.repo_id,
        "run_id": layout.run_id,
        "git_commit": layout.git_commit,
        "git_branch": layout.git_branch,
        "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "delivery_manifest_sha256": sha256_file(delivery_path) if delivery_path.is_file() else None,
            "contract_sha256": contract_sha,
            "delivery_config_sha256": config_info.get("sha256"),
            "hash_mode": delivery.get("hash_mode"),
        },
        "packing": dict(packing),
        "counts": {
            "primary": counts.get("primary", 0), "spare": counts.get("spare", 0),
            "smoke": counts.get("smoke", 0), "videos": len(video_rows),
            "archives": len(archives), "files": len(files),
        },
        "archives": archives,
        "episodes": episodes,
        "failures": failures,
        "videos": video_rows,
    }


def render_sha256sums(staged: Iterable[Any]) -> str:
    """渲染 ``SHA256SUMS``：``<sha>␠␠<相对路径>``、按路径升序、LF 换行、末尾带换行。

    自身（``SHA256SUMS``）不入表。
    """
    lines: list[tuple[str, str]] = []
    for item in staged:
        rel = item.rel_path if isinstance(item, StagedFile) else item["rel_path"]
        sha = item.sha256 if isinstance(item, StagedFile) else item["sha256"]
        if rel == "SHA256SUMS":
            continue
        if not sha:
            raise ReleaseError(f"{rel} 缺 sha256，无法写入 SHA256SUMS")
        lines.append((rel, sha))
    lines.sort(key=lambda item: item[0])
    return "".join(f"{sha}  {rel}\n" for rel, sha in lines)


def render_readme(manifest: dict, layout: ReleaseLayout) -> str:
    """渲染 HF dataset 的 ``README.md``（带 YAML front-matter）。"""
    counts = manifest.get("counts", {})
    by_group: dict[tuple[str, str], dict[str, int]] = {}
    for row in manifest.get("episodes", []):
        cell = by_group.setdefault((row["task"], row["difficulty"]), {"primary": 0, "spare": 0, "smoke": 0})
        cell[row["role"]] = cell.get(row["role"], 0) + 1
    table = ["| 任务 | 难度 | primary | spare | smoke |", "| --- | --- | ---: | ---: | ---: |"]
    for (task, difficulty), cell in by_group.items():
        table.append(f"| {task} | {difficulty} | {cell['primary']} | {cell['spare']} | {cell['smoke']} |")

    return f"""---
license: apache-2.0
task_categories:
- robotics
tags:
- robotics
- manipulation
- maniskill
- robomme
- hdf5
pretty_name: RoboMME 4-task h5 ({layout.run_id})
---

# RoboMME 四任务 h5 数据集（运行 {layout.run_id}）

本仓库发布 RoboMME 新值注入专项运行 `{layout.run_id}` 的 h5 轨迹与配套录像。
四个任务 BinFill / RouteStick / VideoUnmaskSwap / VideoRepick，每个任务 400 条正式 h5，
共 **{counts.get('primary', 0)}** 条 primary、**{counts.get('spare', 0)}** 条 spare 备件、
**{counts.get('smoke', 0)}** 条 smoke 样例，另带 **{counts.get('videos', 0)}** 个 mp4 录像。

## ⚠️ 与官方 `Yinpei/robomme_data_h5` 的形状差别（务必先读）

官方 `Yinpei/robomme_data_h5` 每个包内是**一个合并后的大 h5**（多条 episode 合在一个文件里）。
**本仓库不是**：这里是**逐条 h5**，每个 `.h5` 文件里**只有 `episode_0` 一条轨迹**，
文件名形如 `<任务>_ep<号>_seed<seed>.h5`。下游若按官方形状写了「一个 h5 多条 episode」的读法，
用到本数据集时需要改成「一个目录下多个单 episode h5」。h5 内容本身未做任何合并、改写或重命名。

## 条数分布

{chr(10).join(table)}

## 生成口径

* 注入契约 **v3**（`meta/configs/injection_contract_v3.json`，sha256 `{manifest.get('source', {}).get('contract_sha256')}`）；
* 候选规格按每 100 条一个 **block** 扩容冻结，组内 episode 号连续；
* 每档**实跑目标 × 1.15** 留失败余量（`meta/configs/delivery_400.json`）；
* **严格交付**：每组按 episode 升序取**前 N 条通过**为 primary，其余通过条降级为 spare，未通过条进 `MANIFEST.json` 的 `failures`；
* 每档另有 **50 条只做 env-check、不出 h5** 的额外候选，其结果在 `meta/env_check/**.jsonl` 里 `delivered=true` 的行。

## 目录树

```
README.md              本文件
SHA256SUMS             全部文件的 sha256（不含自身）
MANIFEST.json          机器可读清单：逐条 episode 的散列、归属包、成员路径、录像
tarxz_h5.py            自包含的打包/解包脚本
record_dataset_<任务>_<难度>.h5.tar.xz          14 个正式包
spare/record_dataset_<任务>_<难度>_spare.h5.tar.xz  14 个备件包
videos/<任务>/<难度>/*.mp4                       录像
smoke/record_dataset_RouteStick_easy_smoke.h5.tar.xz  单条样例包
smoke/videos/RouteStick/easy/*.mp4               样例录像
meta/                  小产物副本（交付清单、规格、env-check、日志、配置）
```

每个包解开后是 `record_dataset_<任务>_<难度>/hdf5_files/*.h5` 加一份 `record_dataset_<任务>_metadata.json`。

## 解压

```bash
# 批量（推荐，多进程）
python tarxz_h5.py decompress --input_dir . --jobs 8

# 单个包
tar -xJf record_dataset_BinFill_easy.h5.tar.xz
```

## 校验

```bash
sha256sum -c SHA256SUMS
```

`MANIFEST.json` 主要字段：

* `archives[]` —— 每个包的 `path / role / task / difficulty / bytes / sha256 / member_count`；
* `episodes[]` —— 每条 episode 的 `episode / seed / spec_sha256 / archive / member / h5_sha256 / h5_bytes / timestep_count / videos`，
  其中 `h5_sha256` **逐字抄自生成侧的交付清单**，不是发布时重算的；
* `failures[]` —— 未通过、因而没有 h5 的候选条（仍可能留有录像）；
* `videos[]` —— 每个 mp4 的相对路径、体积与 sha256。

## 关于录像

* **部分 episode 没有录像**（录制中断或帧数不符，`video_status` 非 `complete`）；
* **部分 episode 有第二个 mp4**（`VideoUnmaskSwap` / `VideoRepick` 居多，`BinFill` 也有），文件名以 `success_NO_OBJECT_` 或 `FAILED_NO_OBJECT_` 开头，是同一条 episode 的「无物体」对照渲染；
* **被拒绝（未通过）的候选只有录像、没有 h5**，它们的录像照样收在 `videos/` 下，便于人工复看失败原因。

## 溯源

* 代码仓库：<{GIT_REMOTE_URL}>（**私有仓库**，需授权才能访问）
* 分支：`{layout.git_branch}`
* 运行编号：`{layout.run_id}`
* commit：`{layout.git_commit}`
"""


def render_tarxz_script() -> str:
    """返回自包含的 ``tarxz_h5.py`` 源码（随发布一起上传，供下游批量解压）。"""
    return '''#!/usr/bin/env python3
"""RoboMME h5 数据集的批量打包 / 解包脚本（零第三方依赖，只用标准库）。

用法::

    python tarxz_h5.py decompress --input_dir . --jobs 8
    python tarxz_h5.py compress   --input_dir . --jobs 8

``decompress`` 把目录下（含子目录）的每个 ``*.tar.xz`` 解到**归档所在目录**；
``compress`` 把每个 ``record_dataset_*`` 目录打成同名 ``.tar.xz``。
解包前逐成员校验路径，拒绝绝对路径、``..`` 穿越与符号链接。
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
import tarfile
from pathlib import Path


def _safe_members(archive: tarfile.TarFile, dest: Path):
    """逐成员做路径穿越检查，安全的才交给 extract。"""
    dest = dest.resolve()
    for member in archive.getmembers():
        if member.issym() or member.islnk():
            raise ValueError(f"拒绝链接成员：{member.name}")
        name = member.name
        if name.startswith("/") or ".." in Path(name).parts:
            raise ValueError(f"拒绝越界成员：{name}")
        target = (dest / name).resolve()
        if target != dest and dest not in target.parents:
            raise ValueError(f"拒绝越界成员：{name}")
        yield member


def _decompress_one(args) -> str:
    path, remove_archive = args
    path = Path(path)
    dest = path.parent
    with tarfile.open(path, mode="r:xz") as archive:
        for member in _safe_members(archive, dest):
            archive.extract(member, path=dest)
    if remove_archive:
        path.unlink()
    return str(path)


def _compress_one(args) -> str:
    directory, remove_original = args
    directory = Path(directory)
    out = directory.with_name(directory.name + ".h5.tar.xz")
    with tarfile.open(out, mode="w:xz") as archive:
        for item in sorted(directory.rglob("*")):
            if item.is_file():
                archive.add(item, arcname=str(Path(directory.name) / item.relative_to(directory)))
    if remove_original:
        import shutil

        shutil.rmtree(directory)
    return str(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="RoboMME h5 数据集批量打包 / 解包")
    sub = parser.add_subparsers(dest="command", required=True)

    compress = sub.add_parser("compress", help="把 record_dataset_* 目录打成 .h5.tar.xz")
    compress.add_argument("--input_dir", default=".")
    compress.add_argument("--jobs", type=int, default=4)
    compress.add_argument("--remove_original", action="store_true", help="打完删掉原目录")

    decompress = sub.add_parser("decompress", help="把 *.tar.xz 解到归档所在目录")
    decompress.add_argument("--input_dir", default=".")
    decompress.add_argument("--jobs", type=int, default=4)
    decompress.add_argument("--remove_archive", action="store_true", help="解完删掉归档")

    args = parser.parse_args(argv)
    root = Path(args.input_dir).resolve()

    if args.command == "decompress":
        tasks = [(str(p), args.remove_archive) for p in sorted(root.rglob("*.tar.xz"))]
        worker = _decompress_one
    else:
        tasks = [
            (str(p), args.remove_original)
            for p in sorted(root.rglob("record_dataset_*"))
            if p.is_dir()
        ]
        worker = _compress_one

    if not tasks:
        print(f"{root} 下没有可处理的对象", file=sys.stderr)
        return 1
    jobs = max(1, min(args.jobs, len(tasks)))
    if jobs == 1:
        for task in tasks:
            print(worker(task))
    else:
        with multiprocessing.Pool(jobs) as pool:
            for done in pool.imap_unordered(worker, tasks):
                print(done)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def compare_digests(
    local_sums: dict[str, str],
    remote: dict[str, dict],
    local_blob_sha1: dict[str, str] | None = None,
) -> dict:
    """本地散列与远端条目比对。

    远端每项是 ``{"lfs_sha256": str|None, "blob_id": str, "size": int}``：
    走 LFS 的大文件用 ``lfs_sha256`` 对本地 sha256；非 LFS 小文件用 ``blob_id`` 对本地 git blob sha1。
    返回 ``lfs_sha_match / blob_match / mismatch / missing / extra``。
    """
    local_blob_sha1 = local_blob_sha1 or {}
    lfs_match = 0
    blob_match = 0
    mismatch: list[dict] = []
    missing: list[str] = []
    for rel in sorted(local_sums):
        item = remote.get(rel)
        if item is None:
            missing.append(rel)
            continue
        lfs = item.get("lfs_sha256")
        if lfs:
            if lfs == local_sums[rel]:
                lfs_match += 1
            else:
                mismatch.append({"path": rel, "kind": "lfs_sha256", "local": local_sums[rel], "remote": lfs})
            continue
        expected = local_blob_sha1.get(rel)
        if expected is None:
            mismatch.append({"path": rel, "kind": "blob_id", "local": None, "remote": item.get("blob_id")})
        elif expected == item.get("blob_id"):
            blob_match += 1
        else:
            mismatch.append({"path": rel, "kind": "blob_id", "local": expected, "remote": item.get("blob_id")})
    extra = sorted(set(remote) - set(local_sums))
    return {
        "lfs_sha_match": lfs_match, "blob_match": blob_match,
        "mismatch": mismatch, "missing": missing, "extra": extra,
    }


# ── 打包 ────────────────────────────────────────────────────────────────────
def build_archive(plan: ArchivePlan, dest: Path, *, preset: int = 6, threads: int = 16) -> ArchiveResult:
    """把一个 :class:`ArchivePlan` 打成 ``dest``（``tar -cf - | xz``，Python 边收边算 sha256）。

    成员用 ``--files-from`` 传（1600 条 h5 直接塞命令行会超长），顺序即计划顺序；
    ``--transform`` 给所有成员统一加 ``<top_dir>/`` 前缀，和 :func:`member_path` 的约定对齐。
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for src, member in plan.members:
        rel = os.path.relpath(str(src), str(plan.source_dir))
        if rel.startswith(".."):
            raise ReleaseError(f"成员 {src} 不在源目录 {plan.source_dir} 下")
        expected = f"{plan.top_dir}/{rel}"
        if expected != member:
            raise ReleaseError(f"成员路径不一致：计划 {member}，按源目录推出 {expected}")
        names.append(rel)

    started = time.time()
    digest = hashlib.sha256()
    total = 0
    with tempfile.NamedTemporaryFile("w", suffix=".files", delete=False, encoding="utf-8") as handle:
        handle.write("\n".join(names) + "\n")
        listing = handle.name
    tar_cmd = [
        "tar", "--format=pax", "--owner=0", "--group=0", "--numeric-owner", "--mtime=@0",
        "--no-recursion", f"--transform=s|^|{plan.top_dir}/|",
        "-C", str(plan.source_dir), "-T", listing, "-cf", "-",
    ]
    try:
        tar_proc = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        xz_proc = subprocess.Popen(
            ["xz", f"-{preset}", f"-T{threads}", "-c"],
            stdin=tar_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert tar_proc.stdout is not None
        tar_proc.stdout.close()
        try:
            with open(dest, "wb") as out:
                assert xz_proc.stdout is not None
                for chunk in iter(lambda: xz_proc.stdout.read(CHUNK), b""):
                    out.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
            xz_err = (xz_proc.stderr.read() if xz_proc.stderr else b"").decode("utf-8", "replace")
            tar_err = (tar_proc.stderr.read() if tar_proc.stderr else b"").decode("utf-8", "replace")
            xz_rc = xz_proc.wait()
            tar_rc = tar_proc.wait()
        finally:
            for proc in (tar_proc, xz_proc):
                if proc.poll() is None:
                    proc.kill()
        if tar_rc != 0 or xz_rc != 0:
            dest.unlink(missing_ok=True)
            raise ReleaseError(f"打包失败 {plan.rel_path}：tar rc={tar_rc} {tar_err.strip()} / xz rc={xz_rc} {xz_err.strip()}")
    finally:
        os.unlink(listing)

    sha = digest.hexdigest()
    dest.with_name(dest.name + ".sha256").write_text(f"{sha}  {dest.name}\n", encoding="utf-8")
    return ArchiveResult(
        rel_path=plan.rel_path, bytes=total, sha256=sha, member_count=len(plan.members),
        xz_preset=preset, xz_threads=threads, wall_s=time.time() - started,
    )


def verify_archive_members(archive_path: Path | str, expected: dict[str, str]) -> dict:
    """流式解开归档，逐成员算 sha256 与 ``expected``（成员路径 → sha256）比对。

    用 ``xz -dc -T0`` 管道 + ``tarfile`` 的 ``r|`` 流模式，不落盘、不整包读进内存。
    """
    archive_path = Path(archive_path)
    matched: list[str] = []
    mismatch: list[dict] = []
    extra: list[str] = []
    seen: set[str] = set()
    proc = subprocess.Popen(
        ["xz", "-dc", "-T0", str(archive_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        assert proc.stdout is not None
        with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                stream = archive.extractfile(member)
                if stream is None:
                    continue
                digest = hashlib.sha256()
                for chunk in iter(lambda: stream.read(CHUNK), b""):
                    digest.update(chunk)
                sha = digest.hexdigest()
                seen.add(member.name)
                if member.name not in expected:
                    extra.append(member.name)
                elif expected[member.name] == sha:
                    matched.append(member.name)
                else:
                    mismatch.append({"member": member.name, "expected": expected[member.name], "actual": sha})
        err = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", "replace")
        rc = proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
    if rc != 0:
        raise ReleaseError(f"解压 {archive_path} 失败：rc={rc} {err.strip()}")
    return {
        "archive": archive_path.name, "matched": sorted(matched), "mismatch": mismatch,
        "missing": sorted(set(expected) - seen), "extra": sorted(extra),
    }


# ── 顺序守卫 ────────────────────────────────────────────────────────────────
def _require(path: Path, what: str, hint: str) -> Any:
    if not path.is_file():
        raise ReleaseError(f"缺少{what}（{path}）；请先跑 {hint}")
    return _read_json(path)


def _require_delivery(layout: ReleaseLayout) -> dict:
    if not (layout.run_root / "delivery_manifest.json").is_file():
        raise ReleaseError(f"找不到交付清单 {layout.run_root / 'delivery_manifest.json'}")
    return load_delivery(layout.run_root)


# ── 副作用子命令 ────────────────────────────────────────────────────────────
def pack(
    layout: ReleaseLayout,
    plans: Sequence[ArchivePlan],
    *,
    jobs: int = 2,
    threads: int = 16,
    preset: int = 6,
    resume: bool = True,
    only: str | None = None,
    min_free_gib: int = 200,
) -> dict:
    """并发打包：按原始体积降序开工，断点续跑靠旁车 ``.sha256``。"""
    _require_delivery(layout)
    layout.staging.mkdir(parents=True, exist_ok=True)
    free_gib = shutil.disk_usage(layout.staging).free / (1 << 30)
    if free_gib < min_free_gib:
        raise ReleaseError(f"{layout.staging} 所在盘剩余 {free_gib:.1f} GiB，低于下限 {min_free_gib} GiB")

    todo = list(plans)
    if only:
        wanted = {item.strip() for item in only.split(",") if item.strip()}
        todo = [p for p in todo if f"{p.task}/{p.difficulty}" in wanted]
        if not todo:
            raise ReleaseError(f"--only {only!r} 没匹配到任何组")
    todo.sort(key=lambda plan: plan.raw_bytes, reverse=True)

    results: dict[str, dict] = {}
    failed: list[str] = []
    started = time.time()

    def _one(plan: ArchivePlan) -> tuple[ArchivePlan, dict | None, str | None]:
        dest = layout.staging / plan.rel_path
        sidecar = dest.with_name(dest.name + ".sha256")
        if resume and sidecar.is_file() and dest.is_file() and dest.stat().st_size > 0:
            sha = sidecar.read_text(encoding="utf-8").split()[0]
            return plan, ArchiveResult(
                rel_path=plan.rel_path, bytes=dest.stat().st_size, sha256=sha,
                member_count=len(plan.members), xz_preset=preset, xz_threads=threads, wall_s=0.0,
            ).to_dict() | {"resumed": True}, None
        try:
            return plan, build_archive(plan, dest, preset=preset, threads=threads).to_dict(), None
        except ReleaseError as exc:
            return plan, None, str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for plan, payload, error in pool.map(_one, todo):
            if error:
                failed.append(plan.rel_path)
                print(f"ARCHIVE_FAIL path={plan.rel_path} error={error}", file=sys.stderr)
                continue
            results[plan.rel_path] = payload
            ratio = (plan.raw_bytes / payload["bytes"]) if payload["bytes"] else 0.0
            print(
                f"ARCHIVE_DONE path={plan.rel_path} bytes={payload['bytes']} "
                f"ratio={ratio:.2f} wall_s={payload['wall_s']:.1f}"
            )

    raw = sum(plan.raw_bytes for plan in todo)
    out = sum(item["bytes"] for item in results.values())
    packing = {
        "tool": "tar|xz", "preset": preset, "threads": threads,
        "tar": "--format=pax --owner=0 --group=0 --numeric-owner --mtime=@0",
    }
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "packing": packing, "archives": results, "failed": failed,
        "raw_bytes": raw, "out_bytes": out,
    }
    _write_json(layout.release_dir / "pack_results.json", payload)
    passed = not failed
    print(render_verdict_line({"name": "HF_PACK", "passed": passed, "fields": {
        "archives": len(results), "raw_bytes": raw, "out_bytes": out,
        "ratio": f"{(raw / out):.2f}" if out else "0", "wall_s": f"{time.time() - started:.1f}",
        "failed": len(failed),
    }}))
    payload["passed"] = passed
    return payload


def stage(layout: ReleaseLayout, videos_mode: str = "files", include_smoke: bool = True) -> dict:
    """视频硬链接、小产物复制进 staging，写 ``.release/staged.json``。"""
    pack_results = _require(layout.release_dir / "pack_results.json", "打包断点", "hf_release.py pack")
    staged: list[StagedFile] = []

    for rel, item in sorted(pack_results.get("archives", {}).items()):
        staged.append(StagedFile(rel_path=rel, src=layout.staging / rel, bytes=item["bytes"], sha256=item["sha256"], kind="archive"))

    videos = plan_videos(layout.run_root, videos_mode, include_smoke) if videos_mode != "skip" else []
    linked = 0
    for entry in videos:
        dest = layout.staging / entry["rel_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = Path(entry["src"])
        if dest.exists():
            if dest.stat().st_ino != src.stat().st_ino:
                raise ReleaseError(f"{dest} 已存在且不是 {src} 的硬链接，拒绝覆盖")
        else:
            os.link(src, dest)
            linked += 1
        sha = entry.get("sha256") or sha256_file(src)
        entry["sha256"] = sha
        entry["bytes"] = entry.get("bytes") or src.stat().st_size
        staged.append(StagedFile(rel_path=entry["rel_path"], src=src, bytes=entry["bytes"], sha256=sha, kind="video"))

    metas = plan_meta(layout.run_root, layout.repo_root)
    for entry in metas:
        dest = layout.staging / entry["rel_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry["src"], dest)
        staged.append(StagedFile(
            rel_path=entry["rel_path"], src=Path(entry["src"]),
            bytes=dest.stat().st_size, sha256=sha256_file(dest), kind="meta",
        ))

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "videos_mode": videos_mode, "include_smoke": include_smoke, "linked": linked,
        "files": [item.to_dict() for item in staged],
        "videos": [
            {k: (str(v) if isinstance(v, Path) else v) for k, v in entry.items() if k != "members"}
            for entry in videos
        ],
    }
    _write_json(layout.release_dir / "staged.json", payload)
    print(render_verdict_line({"name": "HF_STAGE", "passed": True, "fields": {
        "archives": sum(1 for item in staged if item.kind == "archive"),
        "videos": sum(1 for item in staged if item.kind == "video"),
        "meta": sum(1 for item in staged if item.kind == "meta"),
        "linked": linked, "files": len(staged),
    }}))
    payload["passed"] = True
    return payload


def write_manifest_files(layout: ReleaseLayout, packing: dict | None = None) -> dict:
    """写 MANIFEST.json / SHA256SUMS / README.md / tarxz_h5.py，并把归档冻结成只读。"""
    staged = _require(layout.release_dir / "staged.json", "staging 断点", "hf_release.py stage")
    pack_results = _require(layout.release_dir / "pack_results.json", "打包断点", "hf_release.py pack")
    delivery = _require_delivery(layout)
    plans = plan_archives(delivery, layout.run_root, check_exists=True)  # 须为 True：smoke 行的 h5 sha256 只在这里现算
    files = [StagedFile(
        rel_path=item["rel_path"], src=Path(item["src"]) if item["src"] else None,
        bytes=item["bytes"], sha256=item["sha256"], kind=item["kind"],
    ) for item in staged["files"]]
    videos = [item for item in staged.get("videos", [])]
    manifest = build_manifest(
        layout, delivery, plans, pack_results.get("archives", {}), videos, files,
        packing or pack_results.get("packing", {}),
    )

    docs: list[StagedFile] = []
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    readme_text = render_readme(manifest, layout)
    tarxz_text = render_tarxz_script()
    for name, text in (("MANIFEST.json", manifest_text), ("README.md", readme_text), ("tarxz_h5.py", tarxz_text)):
        path = layout.staging / name
        path.write_text(text, encoding="utf-8")
        data = text.encode("utf-8")
        docs.append(StagedFile(rel_path=name, src=path, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), kind="doc"))
    sums = render_sha256sums(files + docs)
    (layout.staging / "SHA256SUMS").write_text(sums, encoding="utf-8")

    # 冻结：归档一律去掉写位，并记快照，upload 前比对防止悄悄被改。
    freeze: dict[str, list[int]] = {}
    for item in files:
        if item.kind != "archive":
            continue
        path = layout.staging / item.rel_path
        if not path.is_file():
            continue
        os.chmod(path, stat.S_IMODE(path.stat().st_mode) & ~0o222)
        info = path.stat()
        freeze[item.rel_path] = [info.st_size, info.st_mtime_ns]
    _write_json(layout.release_dir / "freeze.json", {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "archives": freeze,
    })

    print(render_verdict_line({"name": "HF_MANIFEST", "passed": True, "fields": {
        "episodes": len(manifest["episodes"]),
        "primary": manifest["counts"]["primary"], "spare": manifest["counts"]["spare"],
        "videos": manifest["counts"]["videos"], "files": len(files) + len(docs),
        "sums_lines": sums.count("\n"),
    }}))
    return {"passed": True, "manifest": manifest, "sums_lines": sums.count("\n")}


def expected_members(manifest: dict, run_root: Path) -> dict[str, dict[str, str]]:
    """每个归档的期望成员集合：MANIFEST 里的 h5（散列逐字来自交付清单）+ 该组的 metadata.json（按源文件现算）。

    metadata.json 不在 MANIFEST 的 episodes 里，不加进来会被判成「多余成员」。
    """
    expected: dict[str, dict[str, str]] = {}
    for row in manifest["episodes"]:
        expected.setdefault(row["archive"], {})[row["member"]] = row["h5_sha256"]
    for item in manifest.get("archives", []):
        top = archive_top_dir(item["task"], item["difficulty"], item["role"])
        src = group_source_dir(run_root, item["task"], item["difficulty"], item["role"]) / group_metadata_name(item["task"])
        if src.is_file():
            expected.setdefault(item["path"], {})[f"{top}/{group_metadata_name(item['task'])}"] = sha256_file(src)
    return expected


def verify_local(layout: ReleaseLayout, *, jobs: int = 8, sample: int | None = None) -> dict:
    """本地复核：归档自身 sha256 对 SHA256SUMS，再逐成员 h5 sha256 对 MANIFEST。"""
    manifest = _require(layout.staging / "MANIFEST.json", "MANIFEST.json", "hf_release.py manifest")
    sums_path = layout.staging / "SHA256SUMS"
    if not sums_path.is_file():
        raise ReleaseError(f"缺少 {sums_path}；请先跑 hf_release.py manifest")
    sums = {line.split("  ", 1)[1]: line.split("  ", 1)[0] for line in sums_path.read_text(encoding="utf-8").splitlines() if line}

    expected = expected_members(manifest, layout.run_root)
    archives = [item["path"] for item in manifest["archives"]]
    if sample:
        archives = archives[:sample]

    def _one(rel: str) -> dict:
        path = layout.staging / rel
        if not path.is_file():
            return {"archive": rel, "self_ok": False, "error": "归档不存在", "mismatch": [], "missing": [], "extra": [], "matched": []}
        actual = sha256_file(path)
        self_ok = sums.get(rel) == actual
        report = verify_archive_members(path, expected.get(rel, {}))
        report["self_ok"] = self_ok
        report["archive"] = rel
        return report

    reports: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for report in pool.map(_one, archives):
            bad = report.get("mismatch") or report.get("missing") or report.get("extra") or not report.get("self_ok")
            tag = "MISMATCH" if bad else "ARCHIVE_OK"
            print(
                f"{tag} path={report['archive']} self_ok={report.get('self_ok')} "
                f"matched={len(report.get('matched', []))} mismatch={len(report.get('mismatch', []))} "
                f"missing={len(report.get('missing', []))} extra={len(report.get('extra', []))}"
            )
            reports.append(report)

    mismatch = sum(len(r.get("mismatch", [])) for r in reports) + sum(0 if r.get("self_ok") else 1 for r in reports)
    missing = sum(len(r.get("missing", [])) for r in reports)
    extra = sum(len(r.get("extra", [])) for r in reports)
    h5_ok = sum(len(r.get("matched", [])) for r in reports)
    passed = mismatch == 0 and missing == 0 and extra == 0
    payload = {"passed": passed, "reports": reports}
    _write_json(layout.release_dir / "verify_local.json", payload)
    print(render_verdict_line({"name": "HF_PACK_VERIFY", "passed": passed, "fields": {
        "archives": len(reports), "h5": h5_ok, "mismatch": mismatch, "missing": missing, "extra": extra,
    }}))
    return payload


def upload(layout: ReleaseLayout, *, workers: int = 8, include: Sequence[str] | None = None) -> dict:
    """建仓（若无）并用 ``upload_large_folder`` 推整个 staging。"""
    freeze = _require(layout.release_dir / "freeze.json", "冻结快照", "hf_release.py manifest")
    for rel, (size, mtime_ns) in freeze.get("archives", {}).items():
        path = layout.staging / rel
        if not path.is_file():
            raise ReleaseError(f"冻结后归档消失：{rel}")
        info = path.stat()
        if info.st_size != size or info.st_mtime_ns != mtime_ns:
            raise ReleaseError(f"冻结后归档被改动：{rel}（size/mtime 与 freeze.json 不符）")

    from huggingface_hub import HfApi  # 仅在需要联网时才引入

    started = time.time()
    api = HfApi()
    api.create_repo(layout.repo_id, repo_type="dataset", private=False, exist_ok=True)
    api.upload_large_folder(
        repo_id=layout.repo_id, folder_path=str(layout.staging), repo_type="dataset",
        num_workers=workers, allow_patterns=list(include) if include else None,
        ignore_patterns=UPLOAD_IGNORE,
    )
    revision = api.dataset_info(layout.repo_id).sha
    staged = _read_json(layout.release_dir / "staged.json")
    files = len(staged.get("files", [])) + 4
    total = sum(item["bytes"] for item in staged.get("files", []))
    payload = {
        "passed": True, "repo_id": layout.repo_id, "revision": revision,
        "files": files, "bytes": total, "workers": workers,
        "include": list(include) if include else None,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_json(layout.release_dir / "upload.json", payload)
    print(render_verdict_line({"name": "HF_UPLOAD", "passed": True, "fields": {
        "repo": layout.repo_id, "files": files, "bytes": total,
        "revision": revision, "wall_s": f"{time.time() - started:.1f}",
    }}))
    return payload


def verify_remote(layout: ReleaseLayout) -> dict:
    """列远端文件树，用 LFS sha256 / blob sha1 与本地 SHA256SUMS 逐文件比对。"""
    _require(layout.release_dir / "upload.json", "上传断点", "hf_release.py upload")
    sums_path = layout.staging / "SHA256SUMS"
    local = {line.split("  ", 1)[1]: line.split("  ", 1)[0] for line in sums_path.read_text(encoding="utf-8").splitlines() if line}

    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    remote: dict[str, dict] = {}
    for item in api.list_repo_tree(layout.repo_id, repo_type="dataset", recursive=True, expand=True):
        if getattr(item, "size", None) is None:  # 目录
            continue
        lfs = getattr(item, "lfs", None)
        remote[item.path] = {
            "lfs_sha256": getattr(lfs, "sha256", None) if lfs else None,
            "blob_id": getattr(item, "blob_id", None), "size": item.size,
        }
    remote.pop("SHA256SUMS", None)

    blob_sha1: dict[str, str] = {}
    for rel, item in remote.items():
        if item["lfs_sha256"] or rel not in local:
            continue
        path = Path(hf_hub_download(layout.repo_id, rel, repo_type="dataset"))
        data = path.read_bytes()
        blob_sha1[rel] = git_blob_sha1(data)
        if hashlib.sha256(data).hexdigest() != local[rel]:
            item["lfs_sha256"] = "sha256-不符"  # 让 compare_digests 记成 mismatch

    report = compare_digests(local, remote, blob_sha1)
    passed = not report["mismatch"] and not report["missing"]
    print(render_verdict_line({"name": "HF_REMOTE_VERIFY", "passed": passed, "fields": {
        "files": len(remote), "lfs_sha_match": report["lfs_sha_match"], "blob_match": report["blob_match"],
        "mismatch": len(report["mismatch"]), "missing": len(report["missing"]), "extra": len(report["extra"]),
    }}))
    report["passed"] = passed
    _write_json(layout.release_dir / "verify_remote.json", report)
    return report


def verify_sample(layout: ReleaseLayout, *, archives: int = 4, videos: int = 3, seed: int = 0) -> dict:
    """抽样回下载复核：每任务一个正式包 + 最大包 + 一个 spare 包 + N 个 mp4，校完即删。"""
    _require(layout.release_dir / "upload.json", "上传断点", "hf_release.py upload")
    manifest = _require(layout.staging / "MANIFEST.json", "MANIFEST.json", "hf_release.py manifest")
    rng = random.Random(seed)

    primary = [item for item in manifest["archives"] if item["role"] == "primary"]
    spares = [item for item in manifest["archives"] if item["role"] == "spare"]
    picked: list[str] = []
    by_task: dict[str, list[dict]] = {}
    for item in primary:
        by_task.setdefault(item["task"], []).append(item)
    for task in sorted(by_task):
        picked.append(rng.choice(by_task[task])["path"])
    if primary:
        picked.append(max(primary, key=lambda item: item.get("bytes") or 0)["path"])
    if spares:
        picked.append(rng.choice(spares)["path"])
    seen: list[str] = []
    for path in picked:
        if path not in seen:
            seen.append(path)
    picked = seen[: max(archives, 1)] if archives else seen

    video_rows = manifest.get("videos", [])
    picked_videos = rng.sample(video_rows, min(videos, len(video_rows))) if video_rows else []

    expected = expected_members(manifest, layout.run_root)
    sums = {item["path"]: item["sha256"] for item in manifest["archives"]}

    from huggingface_hub import hf_hub_download

    cache = layout.release_dir / "sample_cache"
    cache.mkdir(parents=True, exist_ok=True)
    mismatch: list[dict] = []
    h5_ok = 0
    for rel in picked:
        local = Path(hf_hub_download(layout.repo_id, rel, repo_type="dataset", local_dir=str(cache)))
        try:
            if sums.get(rel) and sha256_file(local) != sums[rel]:
                mismatch.append({"path": rel, "kind": "archive_sha256"})
                continue
            report = verify_archive_members(local, expected.get(rel, {}))
            h5_ok += len(report["matched"])
            mismatch.extend({"path": rel, **item} for item in report["mismatch"])
            mismatch.extend({"path": rel, "member": name, "kind": "missing"} for name in report["missing"])
        finally:
            local.unlink(missing_ok=True)
    for row in picked_videos:
        local = Path(hf_hub_download(layout.repo_id, row["path"], repo_type="dataset", local_dir=str(cache)))
        try:
            if row.get("sha256") and sha256_file(local) != row["sha256"]:
                mismatch.append({"path": row["path"], "kind": "video_sha256"})
        finally:
            local.unlink(missing_ok=True)
    shutil.rmtree(cache, ignore_errors=True)

    passed = not mismatch
    print(render_verdict_line({"name": "HF_SAMPLE_VERIFY", "passed": passed, "fields": {
        "archives": len(picked), "h5": h5_ok, "videos": len(picked_videos), "mismatch": len(mismatch),
    }}))
    payload = {"passed": passed, "archives": picked, "videos": [row["path"] for row in picked_videos], "mismatch": mismatch}
    _write_json(layout.release_dir / "verify_sample.json", payload)
    return payload


# ── plan（只算不落盘）────────────────────────────────────────────────────────
def cmd_plan(layout: ReleaseLayout, *, include_spare: bool = True, include_smoke: bool = True) -> dict:
    """只读盘点：展开归档、数视频与小产物、估压缩后体积，一个字节都不写。"""
    delivery = _require_delivery(layout)
    plans = plan_archives(delivery, layout.run_root, include_spare=include_spare, include_smoke=include_smoke)
    videos = plan_videos(layout.run_root, "files", include_smoke)
    metas = plan_meta(layout.run_root, layout.repo_root)
    raw = sum(plan.raw_bytes for plan in plans)
    counts = {"primary": 0, "spare": 0, "smoke": 0}
    for plan in plans:
        counts[plan.role] = counts.get(plan.role, 0) + len(plan.rows)
    fields = {
        "archives": len(plans), "primary": counts["primary"], "spare": counts["spare"],
        "smoke": counts["smoke"], "videos": len(videos), "meta": len(metas),
        "raw_bytes": raw, "est_bytes": int(raw / EST_COMPRESS_RATIO),
    }
    print(render_verdict_line({"name": "HF_PLAN", "passed": True, "fields": fields}))
    return {"passed": True, **fields}


# ── CLI ─────────────────────────────────────────────────────────────────────
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把注入专项运行的 h5/mp4 产物发布到 Hugging Face dataset")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument("--staging", default=None, help="staging 目录，默认 artifacts/hf-staging/<repo 名>")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("plan", help="只算不落盘：归档数、条数、视频数、原始与估算体积")

    pack_p = sub.add_parser("pack", help="按组把 h5 打成 .tar.xz（h5 只读）")
    pack_p.add_argument("--jobs", type=int, default=2, help="同时打几个包")
    pack_p.add_argument("--threads", type=int, default=16, help="单个 xz 的线程数")
    pack_p.add_argument("--preset", type=int, default=6, help="xz 压缩级别")
    pack_p.add_argument("--resume", dest="resume", action="store_true", default=True, help="旁车 .sha256 存在即跳过（默认）")
    pack_p.add_argument("--no-resume", dest="resume", action="store_false", help="强制重打")
    pack_p.add_argument("--no-spare", dest="include_spare", action="store_false", default=True, help="不打备件包")
    pack_p.add_argument("--no-smoke", dest="include_smoke", action="store_false", default=True, help="不打 smoke 包")
    pack_p.add_argument("--only", default=None, help="只打这些组，逗号分隔的 任务/难度")
    pack_p.add_argument("--min-free-gib", type=int, default=200, help="staging 所在盘剩余空间下限（GiB）")

    stage_p = sub.add_parser("stage", help="视频硬链接、小产物复制进 staging")
    stage_p.add_argument("--videos", default="files", choices=("files", "tar", "skip"))
    stage_p.add_argument("--include-smoke", dest="include_smoke", action="store_true", default=True)
    stage_p.add_argument("--no-smoke", dest="include_smoke", action="store_false")

    sub.add_parser("manifest", help="写 MANIFEST.json / SHA256SUMS / README.md / tarxz_h5.py 并冻结归档")

    verify_p = sub.add_parser("verify-local", help="本地流式复核归档与成员散列")
    verify_p.add_argument("--jobs", type=int, default=8)
    verify_p.add_argument("--sample", type=int, default=None, help="只核前 N 个包（自查用）")

    upload_p = sub.add_parser("upload", help="建仓并 upload_large_folder 推整个 staging")
    upload_p.add_argument("--workers", type=int, default=8)
    upload_p.add_argument("--include", action="append", default=None, help="只传匹配这些 glob 的文件，可多次给")

    sub.add_parser("verify-remote", help="列远端文件树与本地散列逐文件比对")

    sample_p = sub.add_parser("verify-sample", help="抽样回下载并重新解包核验")
    sample_p.add_argument("--archives", type=int, default=4)
    sample_p.add_argument("--videos", type=int, default=3)
    sample_p.add_argument("--seed", type=int, default=0)

    args = parser.parse_args(argv)
    layout = make_layout(args.run_id, args.repo_id, args.staging)
    try:
        if args.command == "plan":
            return 0 if cmd_plan(layout)["passed"] else 1
        if args.command == "pack":
            delivery = _require_delivery(layout)
            plans = plan_archives(
                delivery, layout.run_root,
                include_spare=args.include_spare, include_smoke=args.include_smoke,
            )
            result = pack(
                layout, plans, jobs=args.jobs, threads=args.threads, preset=args.preset,
                resume=args.resume, only=args.only, min_free_gib=args.min_free_gib,
            )
            return 0 if result["passed"] else 1
        if args.command == "stage":
            return 0 if stage(layout, args.videos, args.include_smoke)["passed"] else 1
        if args.command == "manifest":
            return 0 if write_manifest_files(layout)["passed"] else 1
        if args.command == "verify-local":
            return 0 if verify_local(layout, jobs=args.jobs, sample=args.sample)["passed"] else 1
        if args.command == "upload":
            return 0 if upload(layout, workers=args.workers, include=args.include)["passed"] else 1
        if args.command == "verify-remote":
            return 0 if verify_remote(layout)["passed"] else 1
        if args.command == "verify-sample":
            result = verify_sample(layout, archives=args.archives, videos=args.videos, seed=args.seed)
            return 0 if result["passed"] else 1
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
