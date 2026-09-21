#!/usr/bin/env python3
"""原始 train 五路对拍编排入口（方案见 NEWTASK_RELEASE_V3_PLAN.md）。

子命令与方案步骤的对应关系：

* ``freeze-identities``（步 0）：从官方 ``dataset-gen`` 固定提交逐字读取十六份 train
  metadata，冻结 1600 条来源身份与 144 条运行子集，输出 G1 的两行判定
  ``TRAIN_IDENTITY`` 与 ``TRAIN_SUBSET``。只读、不启动仿真。
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
import subprocess
import sys
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


def cmd_run(args: argparse.Namespace) -> int:
    manifest = _load_subset_manifest(Path(args.manifest))
    paths = _parse_paths(args.paths)
    shard = _parse_shard(args.shard)
    rows = manifest["rows"]  # type: ignore[index]
    if args.env is not None:
        if args.env not in ALL_TASKS:
            raise IdentityFreezeError(f"未知环境名：{args.env}")
        if args.episode is not None:
            hit = [
                row
                for row in rows  # type: ignore[union-attr]
                if row["task"] == args.env and int(row["episode"]) == args.episode
            ]
            if not hit:
                raise IdentityFreezeError(
                    f"{args.env}/episode {args.episode} 不在子集 manifest 内；"
                    "不得由 --episodes N 推导连续编号，也不得换样本"
                )
    elif args.episode is not None:
        raise IdentityFreezeError("--episode 必须与 --env 一起给出")
    if args.workers < 1:
        raise IdentityFreezeError("--workers 必须 ≥ 1")
    if args.gpus != "0":
        raise IdentityFreezeError("官方 _parse_gpus 只接受 \"0\"；集群 job 内 CUDA_VISIBLE_DEVICES=0")
    print(
        f"# 参数校验通过：paths={','.join(paths)} workers={args.workers} "
        f"shard={args.shard or '-'} rows={len(rows)}"  # type: ignore[arg-type]
    )
    raise SystemExit("run 子命令待步 1b 实现；本步只提供 --help 与参数校验")


def cmd_compare(args: argparse.Namespace) -> int:
    run_dir = Path(args.run)
    if not run_dir.exists():
        raise IdentityFreezeError(f"运行目录不存在：{run_dir}")
    print(f"# 参数校验通过：run={run_dir}")
    raise SystemExit("compare 子命令待步 1b 实现；本步只提供 --help 与参数校验")


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

    run = sub.add_parser("run", help="按五路运行选定身份（步 1b 起实现）")
    run.add_argument("--manifest", default=str(DEFAULT_FROZEN_DIR / "subset_manifest.json"))
    run.add_argument("--env", default=None, help="单环境名，须同时属于全量来源与子集")
    run.add_argument("--episode", type=int, default=None, help="官方原 episode 编号，不重编号")
    run.add_argument("--paths", default="A1,A2,B,C,D", help="五路子集，逗号分隔")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--gpus", default="0")
    run.add_argument("--shard", default=None, help="分片 k/N，按 task 切")
    run.add_argument("--output", required=True)
    run.set_defaults(func=cmd_run)

    compare = sub.add_parser("compare", help="只读比较五路产物（步 1b 起实现）")
    compare.add_argument("--run", required=True, help="运行目录")
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
