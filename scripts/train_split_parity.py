#!/usr/bin/env python3
"""原始 train 五路对拍编排入口（方案见 NEWTASK_RELEASE_V3_PLAN.md）。

子命令与方案步骤的对应关系：

* ``freeze-identities``（步 0）：从官方 ``dataset-gen`` 固定提交逐字读取十六份 train
  metadata，冻结 1600 条来源身份与 144 条运行子集，输出 G1 的两行判定
  ``TRAIN_IDENTITY`` 与 ``TRAIN_SUBSET``。只读、不启动仿真。
* ``freeze-history``（步 1a）：冻结官方历史生成报告原文与散列，按 144 条子集投影 R1a 的
  可比字段（身份／恢复模式／成功／帧数），并把历史动作逐局数值（R1c）与历史 HDF5 成品
  （R2）登记为 ``NOT_RUN``。
* ``run``（步 1b 起实现）：按 A1／A2／B／C／D 五路运行选定身份。
* ``compare``（步 1b 起实现）：只读比较五路产物。

红线（方案第二部分〇）：身份严格取官方 ``(task, episode, seed, difficulty)``，
不用 ``SeedLayout.base_seed`` 公式替换实际 seed，不重编号 episode，失败不换 seed、
不补样本。本文件只读仓库内的 Git 对象与官方 metadata，不改动 ``src/robomme/``。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from seed_layout import (
    ALL_TASKS,
    DIFFICULTY_ORDER,
    MAX_EPISODES,
    DatasetContractError,
    get_layout,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# 官方 dataset-gen 分支的本轮核验提交（方案第四节固定的对拍基线）。
DEFAULT_SOURCE_REF = "d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa"
DEFAULT_SOURCE_REPO = "https://github.com/RoboMME/robomme_benchmark.git"

# 官方 train metadata 在该提交里的路径模板。
METADATA_TEMPLATE = "src/robomme/env_metadata/train/record_dataset_{task}_metadata.json"

# 官方 dataset-gen 历史生成报告在该提交里的路径（步 1a 冻结对象）。
HISTORY_REPORT_PATHS = (
    "scripts/data-generation/reports/generation_report.json",
    "scripts/data-generation/reports/generation_report.md",
)

# 方案 9.5 与「六、盲区诚实清单」登记的历史成品探测点；缺失即记 NOT_RUN，不冒称通过。
HISTORY_ARTIFACT_PROBES = (
    "data/robomme_data_h5",
    "artifacts/native-baseline",
    "/data/hongzefu/robomme_benchmark-restore-DataGen",
)

# R1a 允许投影的历史字段；历史动作数值不在其中（R1c 记 NOT_RUN）。
HISTORY_PROJECTED_FIELDS = ("identity", "recovery_mode", "success", "timestep_count")

# 冻结产物的默认落点：git 跟踪，供本机与 NFS 副本共同消费。
DEFAULT_FROZEN_DIR = REPO_ROOT / "scripts" / "configs" / "newtask-v3"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "train-parity" / "v3-native"

# 方案 9.1 实读结论：十六份 metadata 串接后的 records SHA-256。
EXPECTED_RECORDS_SHA256 = "a57655d601c7e974c688b2b5c3602e7eb8606e2bd312dcc4ba00a1abb29d73bf"
# 方案 9.1 实读结论：1600 条里实际 seed 不等于 attempt 0 公式值的条数。
EXPECTED_NON_FORMULA_SEEDS = 170
# 方案第四节实读结论：每 task 每难度取前 3 条后，各环境固定命中的 episode 集合。
EXPECTED_SUBSET_EPISODES = (0, 1, 2, 3, 4, 6, 7, 10, 11)
# 方案口径 3：全量 1600 条与 144 条子集各自的 fail recover 配置计数。
EXPECTED_FULL_RECOVERY = {"z": 48, "xy": 48, "off": 1504}
EXPECTED_SUBSET_RECOVERY = {"z": 48, "xy": 32, "off": 64}

RECORD_KEYS = ("task", "episode", "seed", "difficulty")
PATH_NAMES = ("A1", "A2", "B", "C", "D")


class IdentityFreezeError(RuntimeError):
    """身份冻结未满足方案固定口径。"""


# --------------------------------------------------------------------------
# 官方源读取
# --------------------------------------------------------------------------


def _git(*args: str) -> bytes:
    """在本仓库执行只读 git 命令并返回标准输出字节。"""
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise IdentityFreezeError(
            "git 命令失败：git " + " ".join(args) + "\n" + proc.stderr.decode(errors="replace")
        )
    return proc.stdout


def ensure_source_ref(source_ref: str, source_repo: str | None) -> str:
    """确认官方提交对象在本地可读，必要时从官方仓库取回；返回完整 commit SHA。"""
    probe = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-t", source_ref],
        check=False,
        capture_output=True,
    )
    if probe.returncode != 0 or probe.stdout.decode().strip() != "commit":
        if not source_repo:
            raise IdentityFreezeError(
                f"本地没有官方提交 {source_ref}，且未提供 --source-repo 供取回"
            )
        fetch = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "fetch", "--no-tags", source_repo, source_ref],
            check=False,
            capture_output=True,
        )
        if fetch.returncode != 0:
            raise IdentityFreezeError(
                f"从 {source_repo} 取回 {source_ref} 失败：\n"
                + fetch.stderr.decode(errors="replace")
            )
    full = _git("rev-parse", source_ref + "^{commit}").decode().strip()
    return full


def read_official_metadata(source_ref: str) -> dict[str, dict[str, object]]:
    """逐字读取十六份官方 train metadata，返回 task → 原始字节／blob id／解析结果。"""
    out: dict[str, dict[str, object]] = {}
    for task in ALL_TASKS:
        path = METADATA_TEMPLATE.format(task=task)
        raw = _git("show", f"{source_ref}:{path}")
        blob = _git("rev-parse", f"{source_ref}:{path}").decode().strip()
        out[task] = {
            "path": path,
            "raw": raw,
            "git_blob": blob,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "parsed": json.loads(raw.decode("utf-8")),
        }
    return out


# --------------------------------------------------------------------------
# 身份口径
# --------------------------------------------------------------------------


def recovery_mode(episode: int) -> str | None:
    """官方 ``generate_dataset.py::EpisodeJob.recovery_mode``：0～2 为 z，3～5 为 xy，其余无。"""
    if episode <= 2:
        return "z"
    if episode <= 5:
        return "xy"
    return None


def _validate_records(task: str, parsed: object, expected_per_task: int) -> list[dict[str, object]]:
    """校验单份官方 metadata 的结构，返回其 records 列表。"""
    if not isinstance(parsed, dict):
        raise IdentityFreezeError(f"{task}: metadata 顶层不是对象")
    if parsed.get("env_id") != task:
        raise IdentityFreezeError(f"{task}: env_id={parsed.get('env_id')!r} 与文件名不符")
    records = parsed.get("records")
    if not isinstance(records, list):
        raise IdentityFreezeError(f"{task}: records 不是列表")
    if parsed.get("record_count") != len(records):
        raise IdentityFreezeError(
            f"{task}: record_count={parsed.get('record_count')!r} 与实际 {len(records)} 条不符"
        )
    if len(records) != expected_per_task:
        raise IdentityFreezeError(
            f"{task}: 期望 {expected_per_task} 条记录，实际 {len(records)} 条"
        )
    seen: set[int] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise IdentityFreezeError(f"{task}[{index}]: 记录不是对象")
        if set(record) != set(RECORD_KEYS):
            raise IdentityFreezeError(
                f"{task}[{index}]: 字段集合为 {sorted(record)}，期望 {sorted(RECORD_KEYS)}"
            )
        if record["task"] != task:
            raise IdentityFreezeError(f"{task}[{index}]: task 字段为 {record['task']!r}")
        episode = record["episode"]
        seed = record["seed"]
        difficulty = record["difficulty"]
        if not isinstance(episode, int) or isinstance(episode, bool):
            raise IdentityFreezeError(f"{task}[{index}]: episode 不是整数")
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise IdentityFreezeError(f"{task}[{index}]: seed 不是整数")
        if difficulty not in DIFFICULTY_ORDER:
            raise IdentityFreezeError(f"{task}[{index}]: difficulty={difficulty!r} 非法")
        if episode in seen:
            raise IdentityFreezeError(f"{task}: episode {episode} 重复")
        seen.add(episode)
    missing = sorted(set(range(expected_per_task)) - seen)
    extra = sorted(seen - set(range(expected_per_task)))
    if missing or extra:
        raise IdentityFreezeError(
            f"{task}: episode 集合不是 0～{expected_per_task - 1}；缺 {missing}，多 {extra}"
        )
    return records


def build_manifest_rows(
    metadata: dict[str, dict[str, object]], expected_per_task: int
) -> list[dict[str, object]]:
    """按 ALL_TASKS 顺序、各文件原 records 顺序串接出全量身份行。"""
    layout = get_layout("train")
    rows: list[dict[str, object]] = []
    for task in ALL_TASKS:
        records = _validate_records(task, metadata[task]["parsed"], expected_per_task)
        metadata[task]["records"] = records
        for record in records:
            episode = int(record["episode"])
            seed = int(record["seed"])
            formula_seed = layout.base_seed(task, episode)
            rows.append(
                {
                    "task": task,
                    "episode": episode,
                    "seed": seed,
                    "difficulty": record["difficulty"],
                    "recovery_mode": recovery_mode(episode),
                    "formula_base_seed": formula_seed,
                    "seed_matches_formula": seed == formula_seed,
                }
            )
    return rows


def records_sha256(metadata: dict[str, dict[str, object]]) -> str:
    """方案 9.1 的串接散列口径：十六份 records 按规范序串接后规范化 JSON 再取 SHA-256。"""
    joined: list[dict[str, object]] = []
    for task in ALL_TASKS:
        joined.extend(metadata[task]["records"])  # type: ignore[arg-type]
    payload = json.dumps(joined, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def cross_check_identity(
    rows: list[dict[str, object]],
    metadata: dict[str, dict[str, object]],
    tasks: tuple[str, ...] = ALL_TASKS,
) -> int:
    """manifest 与官方 metadata 逐条双向比较，返回 mismatch 条数。

    官方一侧从原始字节独立再解析一次，避免与建表共用同一份对象而失去比较意义。
    """
    manifest_side: list[tuple[str, int, int, str]] = [
        (str(row["task"]), int(row["episode"]), int(row["seed"]), str(row["difficulty"]))
        for row in rows
    ]
    official_side: list[tuple[str, int, int, str]] = []
    for task in tasks:
        reparsed = json.loads(metadata[task]["raw"].decode("utf-8"))  # type: ignore[union-attr]
        for record in reparsed["records"]:
            official_side.append(
                (
                    str(record["task"]),
                    int(record["episode"]),
                    int(record["seed"]),
                    str(record["difficulty"]),
                )
            )
    mismatch = 0
    # 顺序逐条比较：串接顺序本身也是冻结口径的一部分。
    for left, right in zip(manifest_side, official_side):
        if left != right:
            mismatch += 1
    mismatch += abs(len(manifest_side) - len(official_side))
    # 集合双向比较：抓重复、漏项与额外项。
    left_set = set(manifest_side)
    right_set = set(official_side)
    mismatch += len(left_set - right_set) + len(right_set - left_set)
    if len(left_set) != len(manifest_side) or len(right_set) != len(official_side):
        mismatch += 1
    return mismatch


def count_recovery(rows: list[dict[str, object]]) -> dict[str, int]:
    counts = {"z": 0, "xy": 0, "off": 0}
    for row in rows:
        mode = row["recovery_mode"]
        counts["off" if mode is None else str(mode)] += 1
    return counts


def select_subset(
    rows: list[dict[str, object]], per_cell: int, tasks: tuple[str, ...] = ALL_TASKS
) -> tuple[list[dict[str, object]], dict[str, list[int]]]:
    """每 task 每难度按官方 metadata 原顺序取前 ``per_cell`` 条。"""
    by_task: dict[str, list[dict[str, object]]] = {task: [] for task in tasks}
    for row in rows:
        by_task[str(row["task"])].append(row)
    subset: list[dict[str, object]] = []
    episodes_by_task: dict[str, list[int]] = {}
    for task in tasks:
        picked: list[dict[str, object]] = []
        for difficulty in DIFFICULTY_ORDER:
            cell = [row for row in by_task[task] if row["difficulty"] == difficulty]
            if len(cell) < per_cell:
                raise IdentityFreezeError(
                    f"{task}/{difficulty}: 只有 {len(cell)} 条，不足 per_cell={per_cell}"
                )
            picked.extend(cell[:per_cell])
        episodes_by_task[task] = sorted(int(row["episode"]) for row in picked)
        subset.extend(picked)
    return subset, episodes_by_task


# --------------------------------------------------------------------------
# freeze-identities
# --------------------------------------------------------------------------


def cmd_freeze_identities(args: argparse.Namespace) -> int:
    source_ref = ensure_source_ref(args.source_ref, args.source_repo)
    metadata = read_official_metadata(source_ref)

    rows = build_manifest_rows(metadata, args.expected_per_task)
    digest = records_sha256(metadata)
    if args.expected_records_sha256 and digest != args.expected_records_sha256:
        raise IdentityFreezeError(
            f"records 串接散列 {digest} 与期望 {args.expected_records_sha256} 不符"
        )

    mismatch = cross_check_identity(rows, metadata)
    non_formula = sum(1 for row in rows if not row["seed_matches_formula"])
    if args.expected_non_formula_seeds >= 0 and non_formula != args.expected_non_formula_seeds:
        raise IdentityFreezeError(
            f"非公式 seed 实测 {non_formula} 条，期望 {args.expected_non_formula_seeds} 条；"
            "不得用公式值替换官方实际 seed"
        )
    full_recovery = count_recovery(rows)
    if full_recovery != EXPECTED_FULL_RECOVERY:
        raise IdentityFreezeError(
            f"全量 fail recover 配置计数 {full_recovery} 与方案口径 {EXPECTED_FULL_RECOVERY} 不符"
        )

    subset, episodes_by_task = select_subset(rows, args.per_cell)
    expected_episodes = tuple(int(item) for item in args.expected_subset_episodes.split(",")) if args.expected_subset_episodes else ()
    if expected_episodes:
        for task, episodes in episodes_by_task.items():
            if tuple(episodes) != expected_episodes:
                raise IdentityFreezeError(
                    f"{task}: 子集 episode {episodes} 与冻结清单 {list(expected_episodes)} 不符"
                )
    full_index = {
        (str(row["task"]), int(row["episode"])): row for row in rows
    }
    for row in subset:
        key = (str(row["task"]), int(row["episode"]))
        if full_index.get(key) is not row:
            raise IdentityFreezeError(f"{key}: 子集行无法回指全量行")
    subset_recovery = count_recovery(subset)
    if subset_recovery != EXPECTED_SUBSET_RECOVERY:
        raise IdentityFreezeError(
            f"子集 fail recover 配置计数 {subset_recovery} 与方案口径 {EXPECTED_SUBSET_RECOVERY} 不符"
        )

    frozen_dir = Path(args.frozen_dir)
    official_dir = frozen_dir / "official_train"
    train_manifest = {
        "schema": "train-parity-manifest/1",
        "kind": "full",
        "source_repo": args.source_repo,
        "source_ref": source_ref,
        "metadata_path_template": METADATA_TEMPLATE,
        "records_sha256": digest,
        "tasks": list(ALL_TASKS),
        "rows_total": len(rows),
        "non_formula_seed_rows": non_formula,
        "recovery_config_counts": full_recovery,
        "rows": rows,
    }
    subset_manifest = {
        "schema": "train-parity-manifest/1",
        "kind": "subset",
        "source_repo": args.source_repo,
        "source_ref": source_ref,
        "selection_rule": "每 task 每难度按官方 metadata 原顺序取前 per_cell 条",
        "per_cell": args.per_cell,
        "records_sha256": digest,
        "tasks": list(ALL_TASKS),
        "rows_total": len(subset),
        "episodes_by_task": episodes_by_task,
        "recovery_config_counts": subset_recovery,
        "rows": subset,
    }
    sources = {
        "schema": "train-parity-sources/1",
        "source_repo": args.source_repo,
        "source_ref": source_ref,
        "records_sha256": digest,
        "files": [
            {
                "task": task,
                "source_path": metadata[task]["path"],
                "frozen_name": Path(str(metadata[task]["path"])).name,
                "git_blob": metadata[task]["git_blob"],
                "sha256": metadata[task]["sha256"],
                "bytes": metadata[task]["bytes"],
            }
            for task in ALL_TASKS
        ],
    }

    planned: dict[Path, bytes] = {
        frozen_dir / "train_manifest.json": _json_bytes(train_manifest),
        frozen_dir / "subset_manifest.json": _json_bytes(subset_manifest),
        official_dir / "sources.json": _json_bytes(sources),
    }
    for task in ALL_TASKS:
        name = Path(str(metadata[task]["path"])).name
        planned[official_dir / name] = metadata[task]["raw"]  # type: ignore[assignment]

    changed = _write_or_verify(planned, verify_only=args.verify)

    report = {
        "schema": "train-parity-freeze-report/1",
        "frozen_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "argv": sys.argv[1:],
        "source_repo": args.source_repo,
        "source_ref": source_ref,
        "records_sha256": digest,
        "rows_total": len(rows),
        "identity_mismatch": mismatch,
        "non_formula_seed_rows": non_formula,
        "recovery_config_counts": {"full": full_recovery, "subset": subset_recovery},
        "subset": {
            "per_cell": args.per_cell,
            "rows_total": len(subset),
            "episodes_by_task": episodes_by_task,
        },
        "frozen_dir": str(frozen_dir.relative_to(REPO_ROOT)),
        "frozen_files": {
            str(path.relative_to(REPO_ROOT)): hashlib.sha256(data).hexdigest()
            for path, data in sorted(planned.items())
        },
        "verify_only": bool(args.verify),
        "changed_files": [str(path.relative_to(REPO_ROOT)) for path in changed],
    }
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "freeze_report.json").write_bytes(_json_bytes(report))

    identity_pass = mismatch == 0 and len(rows) == len(ALL_TASKS) * args.expected_per_task
    subset_pass = len(subset) == len(ALL_TASKS) * len(DIFFICULTY_ORDER) * args.per_cell
    print(
        f"TRAIN_IDENTITY={'PASS' if identity_pass else 'FAIL'} "
        f"tasks={len(ALL_TASKS)} rows={len(rows)} mismatch={mismatch}"
    )
    print(
        f"TRAIN_SUBSET={'PASS' if subset_pass else 'FAIL'} "
        f"tasks={len(ALL_TASKS)} per_cell={args.per_cell} rows={len(subset)}"
    )
    print(
        f"# 非公式 seed {non_formula} 条；全量恢复配置 z={full_recovery['z']} "
        f"xy={full_recovery['xy']} off={full_recovery['off']}；"
        f"子集恢复配置 z={subset_recovery['z']} xy={subset_recovery['xy']} off={subset_recovery['off']}"
    )
    print(f"# records_sha256={digest}")
    print(f"# 冻结目录 {frozen_dir.relative_to(REPO_ROOT)}；运行留档 {output_dir}/freeze_report.json")
    return 0 if identity_pass and subset_pass else 1


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")


def _write_or_verify(planned: dict[Path, bytes], verify_only: bool) -> list[Path]:
    """写出冻结文件；``verify_only`` 时只比对既有文件字节，不落盘。"""
    changed: list[Path] = []
    for path, data in sorted(planned.items()):
        existing = path.read_bytes() if path.exists() else None
        if existing == data:
            continue
        if verify_only:
            reason = "内容不同" if existing is not None else "文件缺失"
            raise IdentityFreezeError(f"--verify：{path.relative_to(REPO_ROOT)} {reason}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        changed.append(path)
    return changed


# --------------------------------------------------------------------------
# freeze-history（步 1a）
# --------------------------------------------------------------------------


def _audit_episode_index(audits: list[dict]) -> dict[tuple[str, int], dict]:
    """把报告里按 task 分组的逐 episode 审计摊平成 (task, episode) → 条目。"""
    index: dict[tuple[str, int], dict] = {}
    for audit in audits:
        task = audit["task"]
        for entry in audit.get("episodes", []):
            index[(task, int(entry["episode"]))] = entry
    return index


def cmd_freeze_history(args: argparse.Namespace) -> int:
    """冻结官方历史生成报告，并按 144 条子集投影 R1a 可比字段。

    只做投影与缺证登记：历史动作逐局数值不存在（R1c）、历史 HDF5 成品缺失（R2），
    两项都记 NOT_RUN，不得用本次新结果补造。
    """
    source_ref = ensure_source_ref(args.source_ref, args.source_repo)
    frozen_dir = Path(args.frozen_dir)
    subset_path = frozen_dir / "subset_manifest.json"
    subset = _load_subset_manifest(subset_path)
    if subset.get("kind") != "subset":
        raise IdentityFreezeError(f"{subset_path} 不是子集 manifest")

    frozen: dict[Path, bytes] = {}
    report_files: list[dict[str, object]] = []
    report_payload: dict | None = None
    for path in HISTORY_REPORT_PATHS:
        raw = _git("show", f"{source_ref}:{path}")
        blob = _git("rev-parse", f"{source_ref}:{path}").decode().strip()
        name = Path(path).name
        frozen[frozen_dir / "history" / name] = raw
        report_files.append(
            {
                "source_path": path,
                "frozen_name": name,
                "git_blob": blob,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
        )
        if name.endswith(".json"):
            report_payload = json.loads(raw.decode("utf-8"))
    if report_payload is None:
        raise IdentityFreezeError("未取到历史报告 JSON")

    results = report_payload["generation"]["results"]
    if len(results) != subset.get("rows_total", 0) and len(results) != 1600:
        raise IdentityFreezeError(f"历史报告 results 条数异常：{len(results)}")
    result_index = {(row["task"], int(row["episode"])): row for row in results}
    generated_index = _audit_episode_index(report_payload["validation"]["generated"]["audits"])
    official_index = _audit_episode_index(report_payload["validation"]["official"]["audits"])

    # 历史报告的身份必须与本轮冻结的官方身份一致，否则投影无意义。
    full = json.loads((frozen_dir / "train_manifest.json").read_text(encoding="utf-8"))
    identity_mismatch = 0
    for row in full["rows"]:
        key = (row["task"], int(row["episode"]))
        hit = result_index.get(key)
        if hit is None:
            identity_mismatch += 1
            continue
        if (
            int(hit["seed"]) != int(row["seed"])
            or hit["difficulty"] != row["difficulty"]
            or hit.get("recovery_mode") != row["recovery_mode"]
        ):
            identity_mismatch += 1

    comparison = report_payload["validation"]["joint_action_comparison"]
    subset_keys = {(row["task"], int(row["episode"])) for row in subset["rows"]}
    timestep_errors = [str(item) for item in comparison.get("errors", [])]
    errors_in_subset = []
    for message in timestep_errors:
        head = message.split(":", 1)[0]
        task, _, episode_text = head.partition("/episode_")
        if episode_text.isdigit() and (task, int(episode_text)) in subset_keys:
            errors_in_subset.append(message)

    projection_rows: list[dict[str, object]] = []
    missing = 0
    for row in subset["rows"]:
        key = (row["task"], int(row["episode"]))
        hit = result_index.get(key)
        generated = generated_index.get(key)
        official = official_index.get(key)
        if hit is None or generated is None or official is None:
            missing += 1
        projection_rows.append(
            {
                "task": row["task"],
                "episode": row["episode"],
                "seed": row["seed"],
                "difficulty": row["difficulty"],
                "recovery_mode": row["recovery_mode"],
                "history": {
                    "ok": None if hit is None else bool(hit["ok"]),
                    "attempt_count": None if hit is None else int(hit["attempt_count"]),
                    "timestep_count": None if hit is None else int(hit["timestep_count"]),
                    "generated_final_is_completed": (
                        None if generated is None else bool(generated["final_is_completed"])
                    ),
                    "generated_timestep_count": (
                        None if generated is None else int(generated["timestep_count"])
                    ),
                    "reference_final_is_completed": (
                        None if official is None else bool(official["final_is_completed"])
                    ),
                    "reference_timestep_count": (
                        None if official is None else int(official["timestep_count"])
                    ),
                },
            }
        )

    projection = {
        "schema": "train-parity-history-projection/1",
        "source_ref": source_ref,
        "report_declared_head": report_payload.get("current_head"),
        "report_generated_at_utc": report_payload.get("generated_at_utc"),
        "report_status": report_payload.get("status"),
        "projected_fields": list(HISTORY_PROJECTED_FIELDS),
        "rows_total": len(projection_rows),
        "missing_rows": missing,
        "identity_mismatch": identity_mismatch,
        "report_files": report_files,
        "full_set_action_comparison": {
            "note": "全集统计，无逐局数值摘要；不能投影到 144 条（R1c）",
            "joint_vector_count": comparison.get("joint_vector_count"),
            "joint_element_count": comparison.get("joint_element_count"),
            "different_element_count": comparison.get("different_element_count"),
            "different_element_count_definition": "delta != 0.0 的元素数，不是超过 1e-8 的元素数",
            "max_abs_diff": comparison.get("max_abs_diff"),
            "max_abs_diff_location": comparison.get("max_abs_diff_location"),
            "max_allowed_abs_diff": comparison.get("max_allowed_abs_diff"),
            "passed": comparison.get("passed"),
        },
        "timestep_errors_full_set": timestep_errors,
        "timestep_errors_in_subset": errors_in_subset,
        "reference_revision": report_payload["validation"]["artifact_manifest"].get(
            "reference_revision"
        ),
        "rows": projection_rows,
        "artifact_probes": {
            probe: (Path(probe) if probe.startswith("/") else REPO_ROOT / probe).exists()
            for probe in HISTORY_ARTIFACT_PROBES
        },
        "not_run": {
            "HISTORICAL_ACTION_PARITY": "historical_per_episode_evidence_missing",
            "HISTORICAL_ARTIFACT_PARITY": "historical_files_missing",
        },
    }
    frozen[frozen_dir / "history" / "history_projection.json"] = _json_bytes(projection)
    changed = _write_or_verify(frozen, verify_only=args.verify)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "history_freeze_report.json").write_bytes(
        _json_bytes(
            {
                "schema": "train-parity-history-report/1",
                "frozen_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                "argv": sys.argv[1:],
                "identity_mismatch": identity_mismatch,
                "missing_rows": missing,
                "changed_files": [str(path.relative_to(REPO_ROOT)) for path in changed],
                "frozen_files": {
                    str(path.relative_to(REPO_ROOT)): hashlib.sha256(data).hexdigest()
                    for path, data in sorted(frozen.items())
                },
            }
        )
    )

    ok = identity_mismatch == 0 and missing == 0
    print(
        f"HISTORY_FREEZE={'PASS' if ok else 'FAIL'} rows={len(full['rows'])} "
        f"subset={len(projection_rows)} identity_mismatch={identity_mismatch} missing={missing}"
    )
    print("HISTORICAL_ACTION_PARITY=NOT_RUN reason=historical_per_episode_evidence_missing blocking=0")
    print("HISTORICAL_ARTIFACT_PARITY=NOT_RUN reason=historical_files_missing")
    absent = [probe for probe, exists in projection["artifact_probes"].items() if not exists]
    print(f"# 历史成品探测点缺失：{', '.join(absent) if absent else '无'}")
    print(
        f"# 全集动作比较原始结果：different_element_count="
        f"{comparison.get('different_element_count')} max_abs_diff={comparison.get('max_abs_diff')} "
        f"passed={comparison.get('passed')}（阈值 {comparison.get('max_allowed_abs_diff')}）"
    )
    print(
        f"# 全集 10 条帧数不符中落入 144 条子集的：{len(errors_in_subset)} 条"
        + ("：" + "；".join(errors_in_subset) if errors_in_subset else "")
    )
    return 0 if ok else 1


# --------------------------------------------------------------------------
# run / compare：步 1b 起实现，本步只做参数校验
# --------------------------------------------------------------------------


def _load_subset_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        raise IdentityFreezeError(f"manifest 不存在：{path}；先运行 freeze-identities")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "train-parity-manifest/1":
        raise IdentityFreezeError(f"manifest schema 非法：{payload.get('schema')!r}")
    return payload


def _parse_paths(value: str) -> list[str]:
    names = [item.strip() for item in value.split(",") if item.strip()]
    if not names or len(names) != len(set(names)):
        raise IdentityFreezeError("--paths 必须非空且不重复")
    unknown = sorted(set(names) - set(PATH_NAMES))
    if unknown:
        raise IdentityFreezeError("未知路径名：" + ", ".join(unknown))
    return [name for name in PATH_NAMES if name in names]


def _parse_shard(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    try:
        index_text, total_text = value.split("/", 1)
        index, total = int(index_text), int(total_text)
    except ValueError as exc:
        raise IdentityFreezeError(f"--shard 必须形如 k/N，当前为 {value!r}") from exc
    if total < 1 or not 1 <= index <= total:
        raise IdentityFreezeError(f"--shard 取值越界：{value!r}")
    return index, total


def materialize_official_source(source_ref: str, dest: Path) -> dict[str, str]:
    """把官方固定提交的整棵树导出到隔离目录，供 A 路独立进程加载（方案 R4）。"""
    tree = _git("rev-parse", f"{source_ref}^{{tree}}").decode().strip()
    marker = dest / ".official_tree"
    if dest.exists() and marker.exists() and marker.read_text().strip() == tree:
        return {"tree": tree, "reused": "1"}
    if dest.exists():
        raise IdentityFreezeError(f"{dest} 已存在且不是 {tree}；换目录或先自行清理")
    dest.mkdir(parents=True)
    archive = subprocess.Popen(
        ["git", "-C", str(REPO_ROOT), "archive", "--format=tar", source_ref],
        stdout=subprocess.PIPE,
    )
    untar = subprocess.run(["tar", "-x", "-C", str(dest)], stdin=archive.stdout, check=False)
    archive.wait()
    if archive.returncode != 0 or untar.returncode != 0:
        raise IdentityFreezeError(f"导出官方源码失败：{source_ref} → {dest}")
    marker.write_text(tree + "\n")
    return {"tree": tree, "reused": "0"}


def _environment_fingerprint() -> dict[str, object]:
    """记录本次运行的实际设备与环境（方案 9.5 要求各路都留指纹）。"""
    import platform

    def _probe(cmd: list[str]) -> str | None:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        return proc.stdout.strip() if proc.returncode == 0 else None

    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "nvidia_smi": _probe(
            ["nvidia-smi", "--query-gpu=index,name,driver_version", "--format=csv,noheader"]
        ),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_nodelist": os.environ.get("SLURM_NODELIST"),
        "uv_lock_sha256": hashlib.sha256((REPO_ROOT / "uv.lock").read_bytes()).hexdigest(),
        "pyproject_sha256": hashlib.sha256((REPO_ROOT / "pyproject.toml").read_bytes()).hexdigest(),
    }


def select_rows(
    manifest: dict[str, object],
    env: str | None,
    episode: int | None,
    shard: tuple[int, int] | None,
) -> list[dict[str, object]]:
    """从子集 manifest 里挑本次要跑的身份：单条、按 task 分片或全子集。"""
    rows = list(manifest["rows"])  # type: ignore[arg-type]
    if env is not None:
        rows = [row for row in rows if row["task"] == env]
        if episode is not None:
            rows = [row for row in rows if int(row["episode"]) == episode]
        if not rows:
            raise IdentityFreezeError(
                f"{env}/episode {episode} 不在子集 manifest 内；"
                "不得由 --episodes N 推导连续编号，也不得换样本"
            )
    if shard is not None:
        index, total = shard
        # 按 ALL_TASKS 顺序切成连续块，与方案第二部分「十」的分片表一致（4 片即 [0:4]、[4:8]…）。
        size = (len(ALL_TASKS) + total - 1) // total
        group = list(ALL_TASKS[(index - 1) * size : index * size])
        rows = [row for row in rows if row["task"] in group]
        if not rows:
            raise IdentityFreezeError(f"分片 {index}/{total} 没有命中任何身份")
    return rows


def run_path(
    path_name: str,
    rows: list[dict[str, object]],
    output: Path,
    official_root: Path,
    workers: int,
    gpu: str,
    sampling_config: str | None = None,
    episode_specs: str | None = None,
) -> dict[str, object]:
    """跑一路。

    A1／A2 用官方隔离源码；B 用同一份官方编排代码加载**本工作副本**的 `src`，
    因此 A↔B 的差异只可能来自环境源码本身（步 2 要找的正是这些继承改动）。
    C／D 需要额外传 `sampling_config`／`episode_spec`，待步 3／4 实现。
    """
    if path_name == "C" and not sampling_config:
        raise IdentityFreezeError("C 路需要 --sampling-config 指定显式原值配置")
    if path_name == "D" and not (sampling_config and episode_specs):
        raise IdentityFreezeError("D 路需要 --sampling-config 与 --episode-specs")
    path_dir = output / path_name
    jobs: list[dict[str, object]] = []
    skipped: list[str] = []
    for row in rows:
        worker_dir = path_dir / f"{row['task']}_episode_{row['episode']}"
        if worker_dir.exists():
            # job 被回收后续跑：已产出 HDF5 的身份直接跳过，不重跑（方案第二部分「十」）。
            existing = sorted((worker_dir / "hdf5_files").glob("*.h5"))
            if existing:
                skipped.append(worker_dir.name)
                continue
            raise IdentityFreezeError(
                f"{worker_dir} 已存在但没有 HDF5：官方 _worker 要求目录不存在，"
                "请换输出目录或自行清理该身份目录后重跑"
            )
        jobs.append(
            {
                "task": row["task"],
                "episode": int(row["episode"]),
                "seed": int(row["seed"]),
                "difficulty": row["difficulty"],
                "worker_dir": str(worker_dir),
            }
        )
    if skipped:
        print(f"# {path_name} 路跳过已完成身份 {len(skipped)} 条：{', '.join(skipped[:6])}")
    if not jobs:
        return {
            "path": path_name,
            "identities": 0,
            "skipped": skipped,
            "exit_code": 0,
            "elapsed_seconds": 0.0,
            "ok_count": 0,
            "failed_count": 0,
        }
    jobs_path = output / "jobs" / f"{path_name}.json"
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_bytes(_json_bytes(jobs))
    results_path = output / "results" / f"{path_name}.json"
    log_path = output / "logs" / f"{path_name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "train_split_runner.py"),
        "--official-root", str(official_root),
        *(["--src-root", str(REPO_ROOT)] if path_name in ("B", "C", "D") else []),
        *(["--sampling-config", sampling_config] if path_name in ("C", "D") and sampling_config else []),
        *(["--episode-specs", episode_specs] if path_name == "D" and episode_specs else []),
        "--jobs-json", str(jobs_path),
        "--results-json", str(results_path),
        "--workers", str(workers),
        "--gpu", gpu,
    ]
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("PYTHONPATH", None)
    started = time.time()
    with log_path.open("wb") as log_file:
        proc = subprocess.run(command, stdout=log_file, stderr=subprocess.STDOUT, env=env)
    elapsed = round(time.time() - started, 3)
    summary = {
        "path": path_name,
        "identities": len(jobs),
        "skipped": skipped,
        "exit_code": proc.returncode,
        "elapsed_seconds": elapsed,
        "results_json": str(results_path.relative_to(output)),
        "log": str(log_path.relative_to(output)),
    }
    if results_path.exists():
        payload = json.loads(results_path.read_text(encoding="utf-8"))
        results = payload["results"]
        summary["ok_count"] = sum(1 for item in results if item.get("ok"))
        summary["failed_count"] = sum(1 for item in results if not item.get("ok"))
        summary["robomme_module"] = payload.get("robomme_module")
        summary["src_root"] = payload.get("src_root")
    return summary


def collect_episode_specs(output: Path, rows: list[dict[str, object]]) -> Path:
    """把 C 路导出的逐局规格汇成 D 路的输入文件；缺一条就报错，不允许补抽。"""
    specs: dict[str, object] = {}
    missing: list[str] = []
    for row in rows:
        identity = f"{row['task']}/{row['episode']}"
        path = output / "C" / f"{row['task']}_episode_{row['episode']}" / "episode_spec.json"
        if not path.exists():
            missing.append(identity)
            continue
        specs[identity] = json.loads(path.read_text(encoding="utf-8"))
    if missing:
        raise IdentityFreezeError(
            "C 路尚未导出这些身份的规格：" + ", ".join(missing) + "；不得用重抽补位"
        )
    target = output / "episode_specs.json"
    target.write_bytes(_json_bytes({"schema": "train-parity-episode-specs/1", "specs": specs}))
    print(f"# 已汇总 C 路导出的 {len(specs)} 份规格 → {target}")
    return target


def cmd_run(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    manifest = _load_subset_manifest(manifest_path)
    paths = _parse_paths(args.paths)
    shard = _parse_shard(args.shard)
    if args.env is not None and args.env not in ALL_TASKS:
        raise IdentityFreezeError(f"未知环境名：{args.env}")
    if args.env is None and args.episode is not None:
        raise IdentityFreezeError("--episode 必须与 --env 一起给出")
    if args.workers < 1:
        raise IdentityFreezeError("--workers 必须 ≥ 1")
    # 缺输入的路径先在导出官方源码之前挡掉，避免留下半个运行目录
    if "C" in paths and not args.sampling_config:
        raise IdentityFreezeError("C 路需要 --sampling-config 指定显式原值配置")
    if "D" in paths and not args.sampling_config:
        raise IdentityFreezeError("D 路需要 --sampling-config")
    if "D" in paths and not args.episode_specs and "C" not in paths:
        raise IdentityFreezeError(
            "D 路的规格来源固定为 C 路的只读导出：要么同时跑 C，要么用 --episode-specs 指定已封存的规格"
        )
    if args.gpus != "0":
        raise IdentityFreezeError("官方 _parse_gpus 只接受 \"0\"；集群 job 内 CUDA_VISIBLE_DEVICES=0")

    rows = select_rows(manifest, args.env, args.episode, shard)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    source_ref = ensure_source_ref(args.source_ref, args.source_repo)
    official_root = Path(args.official_root) if args.official_root else output / "official-src"
    official = materialize_official_source(source_ref, official_root)

    config = {
        "schema": "train-parity-run-config/1",
        "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "argv": sys.argv[1:],
        "manifest": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "source_ref": source_ref,
        "official_tree": official["tree"],
        "official_root": str(official_root),
        "paths": paths,
        "workers": args.workers,
        "gpus": args.gpus,
        "shard": args.shard,
        "identities": [
            {
                "task": row["task"],
                "episode": row["episode"],
                "seed": row["seed"],
                "difficulty": row["difficulty"],
                "recovery_mode": row["recovery_mode"],
            }
            for row in rows
        ],
        "environment": _environment_fingerprint(),
    }
    (output / "run_config.json").write_bytes(_json_bytes(config))
    print(
        f"# 身份 {len(rows)} 条，路径 {','.join(paths)}，worker {args.workers}，"
        f"官方源码树 {official['tree'][:12]}（{'复用' if official['reused'] == '1' else '新导出'}）"
    )

    summaries = []
    failed = 0
    episode_specs = args.episode_specs
    for path_name in paths:
        if path_name == "D" and not episode_specs:
            # 方案 8.2：第一轮的规格来源固定为 C 路的只读导出，不用新 seed 重抽
            episode_specs = str(collect_episode_specs(output, rows))
        summary = run_path(
            path_name, rows, output, official_root, args.workers, args.gpus,
            sampling_config=args.sampling_config, episode_specs=episode_specs,
        )
        summaries.append(summary)
        failed += int(summary.get("failed_count", 0) or 0) + (1 if summary["exit_code"] else 0)
        print(
            f"RUN_PATH path={path_name} identities={summary['identities']} "
            f"ok={summary.get('ok_count', 0)} failed={summary.get('failed_count', 0)} "
            f"exit={summary['exit_code']} elapsed_s={summary['elapsed_seconds']}"
        )
    (output / "run_summary.json").write_bytes(
        _json_bytes({"schema": "train-parity-run-summary/1", "paths": summaries, "config": config})
    )
    print(f"RUN_DONE paths={len(paths)} identities={len(rows)} failed={failed}")
    return 0 if failed == 0 else 1


# --------------------------------------------------------------------------
# compare：HDF5 全字段逐位对拍（方案第二部分「十一」）
# --------------------------------------------------------------------------

DEFAULT_PAIRS = ("A1:A2", "A1:B", "B:C", "C:D", "A1:D")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _attr_bytes(value: object) -> bytes:
    import numpy as np

    array = np.asarray(value)
    if array.dtype == object:
        return repr(array.tolist()).encode("utf-8")
    return array.tobytes()


def _dataset_bytes(dataset) -> bytes:
    import numpy as np

    value = dataset[()]
    array = np.asarray(value)
    if array.dtype == object:
        # 字符串／变长对象：逐元素规范成 bytes 再比，不做四舍五入或文本化数值比较。
        flat = [
            item.encode("utf-8") if isinstance(item, str) else bytes(item)
            for item in array.reshape(-1).tolist()
        ]
        return b"\x00".join(flat)
    return array.tobytes()


def _first_diff_index(left, right) -> int | None:
    import numpy as np

    try:
        left_array = np.asarray(left[()])
        right_array = np.asarray(right[()])
    except Exception:  # noqa: BLE001 读不出就不给索引
        return None
    if left_array.shape != right_array.shape or left_array.dtype != right_array.dtype:
        return None
    if left_array.dtype == object:
        for index, (a, b) in enumerate(
            zip(left_array.reshape(-1).tolist(), right_array.reshape(-1).tolist())
        ):
            if a != b:
                return index
        return None
    # 按位比较：浮点不设容差，NaN 也按位模式比。
    left_view = left_array.reshape(-1).view(np.uint8)
    right_view = right_array.reshape(-1).view(np.uint8)
    diff = np.flatnonzero(left_view != right_view)
    if diff.size == 0:
        return None
    itemsize = max(left_array.dtype.itemsize, 1)
    return int(diff[0] // itemsize)


def compare_h5_pair(left: Path, right: Path) -> dict[str, object]:
    """两层比较：先整文件 SHA-256，不同再用 h5py 递归逐字段比原始字节。"""
    import h5py

    result: dict[str, object] = {
        "left": str(left),
        "right": str(right),
        "sha_equal": 0,
        "field_mismatch": 0,
        "missing_left": [],
        "missing_right": [],
        "mismatches": [],
        "timestep_count": {},
    }
    left_sha, right_sha = sha256_file(left), sha256_file(right)
    result["left_sha256"], result["right_sha256"] = left_sha, right_sha
    if left_sha == right_sha:
        result["sha_equal"] = 1
        return result

    with h5py.File(left, "r") as lf, h5py.File(right, "r") as rf:
        left_paths: dict[str, str] = {}
        right_paths: dict[str, str] = {}

        def collect(store: dict[str, str]):
            def visitor(name, obj):
                store[name] = "group" if isinstance(obj, h5py.Group) else "dataset"
            return visitor

        lf.visititems(collect(left_paths))
        rf.visititems(collect(right_paths))
        result["missing_right"] = sorted(set(left_paths) - set(right_paths))
        result["missing_left"] = sorted(set(right_paths) - set(left_paths))
        result["field_mismatch"] = len(result["missing_left"]) + len(result["missing_right"])

        # 时间步数不同时先记差异，再只比共有时间步，不截断掩盖。
        def timesteps(store: dict[str, str]) -> int:
            return sum(1 for name in store if name.count("/") == 1 and "timestep_" in name)

        left_steps, right_steps = timesteps(left_paths), timesteps(right_paths)
        result["timestep_count"] = {"left": left_steps, "right": right_steps}
        if left_steps != right_steps:
            result["field_mismatch"] = int(result["field_mismatch"]) + 1

        mismatches: list[dict[str, object]] = []
        for name in sorted(set(left_paths) & set(right_paths)):
            left_obj, right_obj = lf[name], rf[name]
            left_attrs = dict(left_obj.attrs)
            right_attrs = dict(right_obj.attrs)
            if set(left_attrs) != set(right_attrs):
                mismatches.append({"path": name, "kind": "attr_keys"})
                continue
            for key in sorted(left_attrs):
                if _attr_bytes(left_attrs[key]) != _attr_bytes(right_attrs[key]):
                    mismatches.append({"path": f"{name}@{key}", "kind": "attr_value"})
            if left_paths[name] == "dataset":
                if left_obj.dtype != right_obj.dtype or left_obj.shape != right_obj.shape:
                    mismatches.append(
                        {
                            "path": name,
                            "kind": "dtype_or_shape",
                            "left_dtype": str(left_obj.dtype),
                            "right_dtype": str(right_obj.dtype),
                            "left_shape": list(left_obj.shape),
                            "right_shape": list(right_obj.shape),
                        }
                    )
                    continue
                if _dataset_bytes(left_obj) != _dataset_bytes(right_obj):
                    mismatches.append(
                        {
                            "path": name,
                            "kind": "value",
                            "dtype": str(left_obj.dtype),
                            "shape": list(left_obj.shape),
                            "first_diff_index": _first_diff_index(left_obj, right_obj),
                        }
                    )
        result["mismatches"] = mismatches
        result["field_mismatch"] = int(result["field_mismatch"]) + len(mismatches)
    return result


def _identity_dirs(path_dir: Path) -> dict[str, Path]:
    """<路径目录>/<task>_episode_<n> → 身份键。"""
    out: dict[str, Path] = {}
    if not path_dir.is_dir():
        return out
    for child in sorted(path_dir.iterdir()):
        if child.is_dir() and "_episode_" in child.name:
            out[child.name] = child
    return out


def _h5_of(identity_dir: Path) -> Path | None:
    files = sorted((identity_dir / "hdf5_files").glob("*.h5")) if identity_dir.exists() else []
    return files[0] if len(files) == 1 else None


# 本工具自己写进身份目录的证据文件：它们是对拍的证据，不是仿真产物，不参与伴生文件比较。
EVIDENCE_FILES = ("episode_spec.json", "spec_replay.json")


def _sidecars(identity_dir: Path) -> dict[str, str]:
    """身份目录下除 HDF5 与本工具证据文件外的落盘文件散列（视频、图像、json 等）。"""
    out: dict[str, str] = {}
    for item in sorted(identity_dir.rglob("*")):
        if not item.is_file() or item.suffix == ".h5" or item.name in EVIDENCE_FILES:
            continue
        out[str(item.relative_to(identity_dir))] = sha256_file(item)
    return out


def _videos(identity_dir: Path) -> dict[str, Path]:
    """身份目录下的 MP4（录像器产物），按文件名索引。"""
    root = identity_dir / "videos"
    return {item.name: item for item in sorted(root.glob("*.mp4"))} if root.is_dir() else {}


def compare_videos(left_dir: Path, right_dir: Path) -> dict[str, int]:
    """P5：先比容器散列，散列不同才解码逐帧比像素（方案第四节要求两者分开报）。"""
    left, right = _videos(left_dir), _videos(right_dir)
    result = {"compared": 0, "container_equal": 0, "frames_mismatch": 0, "pixels_mismatch": 0,
              "missing": len(set(left) ^ set(right))}
    for name in sorted(set(left) & set(right)):
        result["compared"] += 1
        if sha256_file(left[name]) == sha256_file(right[name]):
            # 容器字节相同 ⇒ 解码帧与像素必然相同，不必再解一遍
            result["container_equal"] += 1
            continue
        import cv2  # noqa: PLC0415 仅在散列不同时才需要解码

        caps = [cv2.VideoCapture(str(left[name])), cv2.VideoCapture(str(right[name]))]
        frames = 0
        pixel_diff = 0
        while True:
            ok_l, frame_l = caps[0].read()
            ok_r, frame_r = caps[1].read()
            if not ok_l or not ok_r:
                if ok_l != ok_r:
                    result["frames_mismatch"] += 1
                break
            frames += 1
            if frame_l.shape != frame_r.shape or not (frame_l == frame_r).all():
                pixel_diff += 1
        for cap in caps:
            cap.release()
        if pixel_diff:
            result["pixels_mismatch"] += pixel_diff
    return result


def collect_recovery(run_dir: Path, path_name: str) -> dict[str, dict]:
    """把一路的恢复证据汇成 身份 → {模式, 动作索引, xy 事件}。"""
    out: dict[str, dict] = {}
    results_path = run_dir / "results" / f"{path_name}.json"
    if not results_path.exists():
        return out
    for item in json.loads(results_path.read_text(encoding="utf-8"))["results"]:
        identity = f"{item['task']}/{item['episode']}"
        entry = {"configured_mode": item.get("recovery_mode"), "ok": item.get("ok")}
        spec_path = (
            run_dir / path_name / f"{item['task']}_episode_{item['episode']}" / "episode_spec.json"
        )
        if spec_path.exists():
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            recovery = spec.get("actions", {}).get("recovery", {})
            entry["selected_action_index"] = recovery.get("selected_action_index")
            entry["events"] = recovery.get("events", {})
            inits = spec.get("initializations", {})
            entry["per_init_action_index"] = {
                key: value.get("recovery_action_index")
                for key, value in inits.items()
                if isinstance(value, dict) and "recovery_action_index" in value
            }
        out[identity] = entry
    return out


def _resolve_side(spec: str, runs: dict[str, Path]) -> tuple[str, Path]:
    if "/" in spec:
        label, _, path_name = spec.partition("/")
    else:
        label, path_name = next(iter(runs)), spec
    if label not in runs:
        raise IdentityFreezeError(f"未知运行标签 {label!r}；可用 {sorted(runs)}")
    if path_name not in PATH_NAMES:
        raise IdentityFreezeError(f"未知路径名 {path_name!r}")
    return f"{label}/{path_name}", runs[label] / path_name


def cmd_compare(args: argparse.Namespace) -> int:
    runs: dict[str, Path] = {}
    for item in args.run:
        label, _, path_text = item.partition("=")
        if not path_text:
            label, path_text = Path(item).name, item
        run_dir = Path(path_text)
        if not run_dir.exists():
            raise IdentityFreezeError(f"运行目录不存在：{run_dir}")
        if label in runs:
            raise IdentityFreezeError(f"运行标签重复：{label}")
        runs[label] = run_dir

    pair_specs = args.pair or list(DEFAULT_PAIRS)
    output = Path(args.output) if args.output else next(iter(runs.values())) / "compare"
    output.mkdir(parents=True, exist_ok=True)
    jsonl = (output / "h5_pairs.jsonl").open("w", encoding="utf-8")
    summary_rows: list[dict[str, object]] = []
    overall_fail = 0

    for spec in pair_specs:
        left_spec, _, right_spec = spec.partition(":")
        if not right_spec:
            raise IdentityFreezeError(f"--pair 必须形如 LEFT:RIGHT，当前为 {spec!r}")
        left_label, left_dir = _resolve_side(left_spec, runs)
        right_label, right_dir = _resolve_side(right_spec, runs)
        left_ids, right_ids = _identity_dirs(left_dir), _identity_dirs(right_dir)
        shared = sorted(set(left_ids) & set(right_ids))
        only_left = sorted(set(left_ids) - set(right_ids))
        only_right = sorted(set(right_ids) - set(left_ids))
        if not shared and args.pair is None:
            continue  # 默认对里尚未产出的路径直接跳过，不冒充比过
        compared = sha_equal = field_mismatch = 0
        sidecar_mismatch = 0
        for identity in shared:
            left_h5, right_h5 = _h5_of(left_ids[identity]), _h5_of(right_ids[identity])
            if left_h5 is None or right_h5 is None:
                field_mismatch += 1
                jsonl.write(
                    json.dumps(
                        {
                            "pair": f"{left_label}|{right_label}",
                            "identity": identity,
                            "error": "hdf5 缺失或不唯一",
                            "left_dir": str(left_ids[identity]),
                            "right_dir": str(right_ids[identity]),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                continue
            record = compare_h5_pair(left_h5, right_h5)
            record["pair"] = f"{left_label}|{right_label}"
            record["identity"] = identity
            left_side, right_side = _sidecars(left_ids[identity]), _sidecars(right_ids[identity])
            sidecar_diff = sorted(
                name
                for name in set(left_side) | set(right_side)
                if left_side.get(name) != right_side.get(name)
            )
            record["sidecar_mismatch"] = sidecar_diff
            sidecar_mismatch += len(sidecar_diff)
            compared += 1
            sha_equal += int(record["sha_equal"])
            field_mismatch += int(record["field_mismatch"])
            jsonl.write(json.dumps(record, ensure_ascii=False) + "\n")
        pair_tag = f"{left_label}|{right_label}".replace("/", ".")
        print(
            f"H5_PARITY pair={pair_tag} compared={compared} sha_equal={sha_equal} "
            f"field_mismatch={field_mismatch}"
        )
        if only_left or only_right:
            print(f"# 仅一侧存在的身份：left_only={only_left} right_only={only_right}")
        if sidecar_mismatch:
            print(f"# 伴生文件（视频／图像／json）散列不同：{sidecar_mismatch} 项")
        summary_rows.append(
            {
                "pair": pair_tag,
                "left": left_label,
                "right": right_label,
                "compared": compared,
                "sha_equal": sha_equal,
                "field_mismatch": field_mismatch,
                "sidecar_mismatch": sidecar_mismatch,
                "only_left": only_left,
                "only_right": only_right,
            }
        )
        overall_fail += field_mismatch + len(only_left) + len(only_right)
    jsonl.close()

    if args.history:
        projection = json.loads(Path(args.history).read_text(encoding="utf-8"))
        history_index = {
            (row["task"], int(row["episode"])): row for row in projection["rows"]
        }
        compared = outcome_mismatch = detail_mismatch = 0
        details: list[dict[str, object]] = []
        for label, run_dir in runs.items():
            results_path = run_dir / "results" / f"{args.history_path}.json"
            if not results_path.exists():
                continue
            for item in json.loads(results_path.read_text(encoding="utf-8"))["results"]:
                key = (item["task"], int(item["episode"]))
                history = history_index.get(key)
                if history is None:
                    outcome_mismatch += 1
                    details.append({"run": label, "identity": key, "error": "历史投影缺少该身份"})
                    continue
                compared += 1
                row_errors: list[str] = []
                # 身份与恢复模式：不符即 outcome_mismatch。
                if int(history["seed"]) != int(item["seed"]) or history["difficulty"] != item["difficulty"]:
                    row_errors.append("identity")
                if history["recovery_mode"] != item.get("recovery_mode"):
                    row_errors.append("recovery_mode")
                if bool(history["history"]["ok"]) != bool(item.get("ok")):
                    row_errors.append("success")
                if row_errors:
                    outcome_mismatch += 1
                # 帧数属于 detail：历史生成侧帧数与本次 A 路帧数逐条比。
                if item.get("ok") and history["history"]["timestep_count"] != item.get("timestep_count"):
                    detail_mismatch += 1
                    row_errors.append("timestep_count")
                if row_errors:
                    details.append(
                        {
                            "run": label,
                            "identity": f"{key[0]}/episode_{key[1]}",
                            "fields": row_errors,
                            "history_timestep_count": history["history"]["timestep_count"],
                            "run_timestep_count": item.get("timestep_count"),
                        }
                    )
        status = "PASS" if compared and outcome_mismatch == 0 and detail_mismatch == 0 else "FAIL"
        print(
            f"DATASET_GEN_REPORT_PARITY={status} compared={compared} "
            f"fields=identity,recovery_mode,success,timestep_count "
            f"outcome_mismatch={outcome_mismatch} detail_mismatch={detail_mismatch}"
        )
        for item in details:
            print(f"# 历史投影差异 {item}")
        (output / "history_parity.json").write_bytes(
            _json_bytes(
                {
                    "schema": "train-parity-history-check/1",
                    "path": args.history_path,
                    "compared": compared,
                    "outcome_mismatch": outcome_mismatch,
                    "detail_mismatch": detail_mismatch,
                    "details": details,
                }
            )
        )
        overall_fail += outcome_mismatch + detail_mismatch

    for gate_name in (args.gate or []):
        total_compared = sum(int(row["compared"]) for row in summary_rows)
        total_mismatch = sum(int(row["field_mismatch"]) for row in summary_rows)
        if gate_name == "BASELINE_REPEAT":
            print(
                f"BASELINE_REPEAT={'PASS' if total_mismatch == 0 and total_compared else 'FAIL'} "
                f"compared={total_compared} different={total_mismatch}"
            )
        elif gate_name == "VIDEO_PARITY":
            compared = frames_mismatch = pixels_mismatch = container_equal = missing = 0
            for row in summary_rows:
                left_label, right_label = row["left"], row["right"]
                left_run, left_path = str(left_label).split("/")
                right_run, right_path = str(right_label).split("/")
                left_dirs = _identity_dirs(runs[left_run] / left_path)
                right_dirs = _identity_dirs(runs[right_run] / right_path)
                for identity in sorted(set(left_dirs) & set(right_dirs)):
                    stat = compare_videos(left_dirs[identity], right_dirs[identity])
                    compared += stat["compared"]
                    container_equal += stat["container_equal"]
                    frames_mismatch += stat["frames_mismatch"]
                    pixels_mismatch += stat["pixels_mismatch"]
                    missing += stat["missing"]
            status = "PASS" if compared and frames_mismatch == pixels_mismatch == missing == 0 else "FAIL"
            print(
                f"VIDEO_PARITY={status} compared={compared} frames_mismatch={frames_mismatch} "
                f"pixels_mismatch={pixels_mismatch}"
            )
            print(f"# 容器散列已相同 {container_equal} 个；仅一侧存在的视频 {missing} 个")
            overall_fail += frames_mismatch + pixels_mismatch + missing
        elif gate_name == "RECOVERY_PARITY":
            # P7：逐条比恢复开关、模式与实际动作索引／xy 方向；配置计数与触发计数分开
            counts = {"z": 0, "xy": 0, "off": 0}
            compared = mode_mismatch = event_mismatch = 0
            reference = None
            for label, run_dir in runs.items():
                for path_name in PATH_NAMES:
                    evidence = collect_recovery(run_dir, path_name)
                    if not evidence:
                        continue
                    if reference is None:
                        reference = evidence
                        for entry in evidence.values():
                            mode = entry.get("configured_mode")
                            counts["off" if mode is None else str(mode)] += 1
                        continue
                    for identity, entry in evidence.items():
                        base = reference.get(identity)
                        if base is None:
                            mode_mismatch += 1
                            continue
                        compared += 1
                        if base.get("configured_mode") != entry.get("configured_mode"):
                            mode_mismatch += 1
                        for key in ("selected_action_index", "events", "per_init_action_index"):
                            if key in base and key in entry and base[key] != entry[key]:
                                event_mismatch += 1
            status = "PASS" if compared and mode_mismatch == event_mismatch == 0 else "FAIL"
            print(
                f"RECOVERY_PARITY={status} compared={compared} "
                f"configured={counts['z'] + counts['xy']} z={counts['z']} xy={counts['xy']} "
                f"off={counts['off']} mode_mismatch={mode_mismatch} event_mismatch={event_mismatch}"
            )
            overall_fail += mode_mismatch + event_mismatch
        elif gate_name == "SPEC_BINDING":
            # G4：C 路是否为每条身份导出了规格，D 路是否真的消费了它
            missing = unused = mismatch = 0
            for label, run_dir in runs.items():
                for identity_dir in _identity_dirs(run_dir / "C"):
                    if not (run_dir / "C" / identity_dir / "episode_spec.json").exists():
                        missing += 1
                for identity_dir in _identity_dirs(run_dir / "D"):
                    replay = run_dir / "D" / identity_dir / "spec_replay.json"
                    if not replay.exists():
                        missing += 1
                        continue
                    payload = json.loads(replay.read_text(encoding="utf-8"))
                    mismatch += len(payload.get("mismatches", []))
                    unused += len(payload.get("unused", []))
            status = "PASS" if missing == unused == mismatch == 0 else "FAIL"
            print(f"SPEC_BINDING={status} missing={missing} unused={unused} mismatch={mismatch}")
            overall_fail += missing + unused + mismatch
        elif gate_name == "NODE_PARITY":
            identities = max((int(row["compared"]) for row in summary_rows), default=0)
            print(
                f"NODE_PARITY={'PASS' if total_mismatch == 0 and total_compared else 'FAIL'} "
                f"identities={identities} jobs={len(runs)} mismatch={total_mismatch}"
            )
        else:
            raise IdentityFreezeError(f"未知闸门名：{gate_name}")

    (output / "summary.json").write_bytes(
        _json_bytes(
            {
                "schema": "train-parity-compare-summary/1",
                "compared_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                "runs": {label: str(path) for label, path in runs.items()},
                "pairs": summary_rows,
            }
        )
    )
    print(f"# 逐对明细 {output}/h5_pairs.jsonl；汇总 {output}/summary.json")
    return 0 if overall_fail == 0 else 1


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="train_split_parity.py",
        description="原始 train 五路对拍编排（freeze-identities / run / compare）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    freeze = sub.add_parser(
        "freeze-identities", help="冻结官方 1600 条来源身份与 144 条运行子集（步 0）"
    )
    freeze.add_argument("--source-repo", default=DEFAULT_SOURCE_REPO, help="官方仓库地址，仅在本地缺对象时用于取回")
    freeze.add_argument("--source-ref", default=DEFAULT_SOURCE_REF, help="官方 dataset-gen 固定提交")
    freeze.add_argument("--expected-per-task", type=int, default=MAX_EPISODES, help="每环境期望条数")
    freeze.add_argument("--per-cell", type=int, default=3, help="每 task 每难度取前几条")
    freeze.add_argument(
        "--expected-records-sha256", default=EXPECTED_RECORDS_SHA256, help="records 串接散列，置空则不校验"
    )
    freeze.add_argument(
        "--expected-non-formula-seeds", type=int, default=EXPECTED_NON_FORMULA_SEEDS,
        help="非公式 seed 期望条数，负数则不校验",
    )
    freeze.add_argument(
        "--expected-subset-episodes",
        default=",".join(str(item) for item in EXPECTED_SUBSET_EPISODES),
        help="每环境子集 episode 冻结清单，置空则不校验",
    )
    freeze.add_argument("--frozen-dir", default=str(DEFAULT_FROZEN_DIR), help="冻结产物目录（git 跟踪）")
    freeze.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="运行留档目录")
    freeze.add_argument("--verify", action="store_true", help="只校验既有冻结文件字节，不写盘")
    freeze.set_defaults(func=cmd_freeze_identities)

    history = sub.add_parser(
        "freeze-history", help="冻结官方历史生成报告并按子集投影 R1a 可比字段（步 1a）"
    )
    history.add_argument("--source-repo", default=DEFAULT_SOURCE_REPO)
    history.add_argument("--source-ref", default=DEFAULT_SOURCE_REF)
    history.add_argument("--frozen-dir", default=str(DEFAULT_FROZEN_DIR))
    history.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR))
    history.add_argument("--verify", action="store_true", help="只校验既有冻结文件字节，不写盘")
    history.set_defaults(func=cmd_freeze_history)

    run = sub.add_parser("run", help="按五路运行选定身份（步 1b 起实现）")
    run.add_argument("--manifest", default=str(DEFAULT_FROZEN_DIR / "subset_manifest.json"))
    run.add_argument("--env", default=None, help="单环境名，须同时属于全量来源与子集")
    run.add_argument("--episode", type=int, default=None, help="官方原 episode 编号，不重编号")
    run.add_argument("--paths", default="A1,A2,B,C,D", help="五路子集，逗号分隔")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--gpus", default="0")
    run.add_argument("--shard", default=None, help="分片 k/N，按 task 切")
    run.add_argument("--source-repo", default=DEFAULT_SOURCE_REPO)
    run.add_argument("--source-ref", default=DEFAULT_SOURCE_REF)
    run.add_argument("--official-root", default=None, help="官方隔离源码目录，默认 <output>/official-src")
    run.add_argument("--sampling-config", default=None, help="C／D 路的显式采样配置 JSON")
    run.add_argument("--episode-specs", default=None, help="D 路的每局规格 JSON")
    run.add_argument("--output", required=True)
    run.set_defaults(func=cmd_run)

    compare = sub.add_parser("compare", help="只读比较五路产物：HDF5 全字段逐位对拍")
    compare.add_argument(
        "--run", required=True, action="append",
        help="运行目录，可重复；写成 <标签>=<目录> 可自定义标签（跨 job 比较用）",
    )
    compare.add_argument(
        "--pair", action="append", default=None,
        help="比较对 LEFT:RIGHT，可重复；跨运行写 <标签>/<路径>。默认 A1:A2,A1:B,B:C,C:D,A1:D",
    )
    compare.add_argument(
        "--history", default=None,
        help="历史投影 JSON（步 1a 产物），给出后按 R1a 可比字段比对并输出 DATASET_GEN_REPORT_PARITY",
    )
    compare.add_argument("--history-path", default="A1", help="与历史投影比对的路径名，默认 A1")
    compare.add_argument(
        "--gate", action="append", default=None,
        help="额外输出闸门判定行：BASELINE_REPEAT / NODE_PARITY / SPEC_BINDING / VIDEO_PARITY / RECOVERY_PARITY",
    )
    compare.add_argument("--output", default=None, help="比较结果目录，默认 <第一个运行目录>/compare")
    compare.set_defaults(func=cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (IdentityFreezeError, DatasetContractError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
