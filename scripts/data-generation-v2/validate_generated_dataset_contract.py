#!/usr/bin/env python3
"""独立的 HDF5 与 metadata 契约校验。

校验分三块，任何一块出错都会让整体判定为不通过：

1. **train metadata**：产物目录里的 `record_dataset_<任务>_metadata.json` 必须与当前分支的
   train metadata 完全一致（seed、difficulty、episode 集合）；
2. **生成产物**：每个 episode 的 `setup/seed`、`setup/difficulty` 要与 metadata 对得上，
   timestep 必须从 0 起连续编号，末帧的 `info/is_completed` 必须是 True，
   `action/joint_action` 必须是 `(8,) float64` 且全为有限值；
3. **官方参考数据**：同一套检查也对参考侧跑一遍，确保对拍的两边都是合法数据。

⚠ 关于 timestep 的严格性：`episode_<i>/` 下除了 `setup` 之外**只允许**出现连续编号的
`timestep_<k>`，多一个别的 group 就会被判为非法。2D flow 的字段之所以挂在 `timestep_<k>/flow/`
与 `setup/flow_*` 内部而不是 episode 级，正是为了完全不触碰这条规则——本校验器对
`setup/` 与 `timestep_<k>/` 的**内部**结构不做约束，因此 flow 是零改动接入的。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import h5py
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
METADATA_ROOT = REPO_ROOT / "src" / "robomme" / "env_metadata" / "train"
REFERENCE_ROOT = REPO_ROOT / "data" / "robomme_data_h5"
ALL_TASKS = (
    "PickXtimes",
    "StopCube",
    "SwingXtimes",
    "BinFill",
    "VideoUnmaskSwap",
    "VideoUnmask",
    "ButtonUnmaskSwap",
    "ButtonUnmask",
    "VideoRepick",
    "VideoPlaceButton",
    "VideoPlaceOrder",
    "PickHighlight",
    "InsertPeg",
    "MoveCube",
    "PatternLock",
    "RouteStick",
)
MAX_EPISODES = 100
MAX_ERRORS = 200
EPISODE_RE = re.compile(r"^episode_(\d+)$")
TIMESTEP_RE = re.compile(r"^timestep_(\d+)$")


class DatasetContractError(RuntimeError):
    """生成数据、参考数据或 train metadata 违反了既定契约。"""


def add_error(section: dict[str, Any], message: str) -> None:
    """累积有上限条数的可读错误，避免数据大面积损坏时报告无限膨胀。"""
    section["error_count"] = int(section.get("error_count", 0)) + 1
    errors = section.setdefault("errors", [])
    if len(errors) < MAX_ERRORS:
        errors.append(message)


def _integer(value: Any, field: str, path: Path) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise DatasetContractError(f"{path}: {field} 必须是整数，实际拿到 {value!r}")
    return int(value)


def read_train_metadata(
    metadata_root: str | Path = METADATA_ROOT,
    tasks: Sequence[str] = ALL_TASKS,
) -> dict[str, dict[int, dict[str, Any]]]:
    """严格读取当前分支的 train metadata，不做任何静默兜底。"""
    root = Path(metadata_root).expanduser().resolve()
    ordered_tasks = tuple(tasks)
    if not ordered_tasks or len(ordered_tasks) != len(set(ordered_tasks)):
        raise DatasetContractError("metadata 任务集合不能为空，且不能有重复")
    expected_files = {f"record_dataset_{task}_metadata.json" for task in ordered_tasks}
    actual_files = {path.name for path in root.glob("record_dataset_*_metadata.json")}
    if actual_files != expected_files:
        raise DatasetContractError(
            "train metadata 的文件集合与既定任务范围不符："
            f"缺少={sorted(expected_files - actual_files)}，"
            f"多余={sorted(actual_files - expected_files)}"
        )

    all_records: dict[str, dict[int, dict[str, Any]]] = {}
    for task in ordered_tasks:
        path = root / f"record_dataset_{task}_metadata.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatasetContractError(f"读取 {path} 失败：{exc}") from exc
        if not isinstance(payload, Mapping) or payload.get("env_id") != task:
            raise DatasetContractError(f"{path}: env_id 不匹配")
        records = payload.get("records")
        if not isinstance(records, list):
            raise DatasetContractError(f"{path}: records 必须是列表")
        if _integer(payload.get("record_count"), "record_count", path) != len(records):
            raise DatasetContractError(f"{path}: record_count 与 records 的长度不相等")
        if len(records) != 100:
            raise DatasetContractError(f"{path}: records 必须恰好有 100 条")

        indexed: dict[int, dict[str, Any]] = {}
        for record in records:
            if not isinstance(record, Mapping):
                raise DatasetContractError(f"{path}: record 必须是对象")
            if any(key not in record for key in ("task", "episode", "seed", "difficulty")):
                raise DatasetContractError(f"{path}: record 缺少 task/episode/seed/difficulty")
            if record["task"] != task:
                raise DatasetContractError(f"{path}: record 的 task 不匹配")
            episode = _integer(record["episode"], "episode", path)
            seed = _integer(record["seed"], "seed", path)
            difficulty = record["difficulty"]
            if not isinstance(difficulty, str) or not difficulty:
                raise DatasetContractError(f"{path}: difficulty 必须是非空字符串")
            if episode in indexed:
                raise DatasetContractError(f"{path}: episode {episode} 重复出现")
            indexed[episode] = {
                "task": task,
                "episode": episode,
                "seed": seed,
                "difficulty": difficulty,
            }
        if set(indexed) != set(range(100)):
            raise DatasetContractError(f"{path}: episode 集合必须恰好是 0..99")
        all_records[task] = indexed
    return all_records


def parse_tasks(value: str) -> list[str]:
    """把 all 或逗号分隔的任务名解析成按标准顺序排列的任务列表。"""
    if value.strip().lower() == "all":
        return list(ALL_TASKS)
    names = [item.strip() for item in value.split(",") if item.strip()]
    if not names or len(names) != len(set(names)):
        raise DatasetContractError("--env 不能为空，且不能有重复")
    unknown = sorted(set(names) - set(ALL_TASKS))
    if unknown:
        raise DatasetContractError("无法识别的环境名：" + ", ".join(unknown))
    return [task for task in ALL_TASKS if task in names]


def episode_groups(
    handle: h5py.File,
    label: str,
    section: dict[str, Any],
) -> dict[int, h5py.Group]:
    """返回合法的 episode group，并把根层级里的意外对象记为契约错误。"""
    groups: dict[int, h5py.Group] = {}
    for name in handle.keys():
        match = EPISODE_RE.fullmatch(name)
        if match is None or not isinstance(handle[name], h5py.Group):
            add_error(section, f"{label}: 根层级出现非法对象 {name!r}")
            continue
        groups[int(match.group(1))] = handle[name]
    return groups


def timestep_indices(group: h5py.Group, source: str) -> tuple[list[int], list[str]]:
    """解析数字编号的 timestep 名并严格校验连续性；合法的 setup group 不计入 timestep。

    ⚠ 这里是全仓库对 episode 内部结构最严的一道关：除 `setup` 外的任何非 `timestep_<数字>`
    对象都会被判非法。新增字段想不触发它，就只能挂在 `setup/` 或 `timestep_<k>/` 的内部。
    """
    errors: list[str] = []
    indices: list[int] = []
    for name in group.keys():
        if name == "setup":
            continue
        match = TIMESTEP_RE.fullmatch(name)
        if match is None or not isinstance(group[name], h5py.Group):
            errors.append(f"{source}: 非法的 timestep {name!r}")
        else:
            indices.append(int(match.group(1)))
    indices.sort()
    if not indices:
        errors.append(f"{source}: 没有任何 timestep")
    elif indices != list(range(len(indices))):
        errors.append(f"{source}: timestep 必须从 0 起连续编号，实际为 {indices[:12]}")
    return indices, errors


def inspect_episode_terminal(
    group: h5py.Group,
    source: str,
) -> tuple[list[int], bool | None, list[str]]:
    """从末个数字 timestep 里严格读取布尔标量 info/is_completed。"""
    indices, errors = timestep_indices(group, source)
    if errors:
        return indices, None, errors
    try:
        dataset = group[f"timestep_{indices[-1]}"]["info"]["is_completed"]
    except KeyError:
        return indices, None, [f"{source}: 末帧缺少 info/is_completed"]
    if (
        not isinstance(dataset, h5py.Dataset)
        or dataset.shape != ()
        or np.dtype(dataset.dtype) != np.dtype(bool)
    ):
        return indices, None, [f"{source}: info/is_completed 必须是布尔标量"]
    value = dataset[()]
    if not isinstance(value, (bool, np.bool_)):
        return indices, None, [f"{source}: info/is_completed 不是布尔值"]
    return indices, bool(value), []


def _text(dataset: h5py.Dataset, source: str) -> str:
    if dataset.shape != ():
        raise DatasetContractError(f"{source}: 字符串必须是标量")
    value = dataset.asstr()[()]
    if not isinstance(value, str):
        raise DatasetContractError(f"{source}: 不是字符串")
    return value


def _audit_episode(
    group: h5py.Group,
    task: str,
    episode: int,
    record: Mapping[str, Any],
    label: str,
    section: dict[str, Any],
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "episode": episode,
        "timestep_count": 0,
        "final_is_completed": None,
        "joint_shape": None,
        "joint_dtype": None,
    }
    setup = group.get("setup")
    if not isinstance(setup, h5py.Group):
        add_error(section, f"{label}: 缺少 setup")
    else:
        seed = setup.get("seed")
        difficulty = setup.get("difficulty")
        if not isinstance(seed, h5py.Dataset) or seed.shape != ():
            add_error(section, f"{label}: 缺少 setup/seed 或其形态非法")
        else:
            try:
                if int(seed[()]) != int(record["seed"]):
                    add_error(section, f"{label}: setup/seed 与 metadata 不一致")
            except (TypeError, ValueError, OverflowError):
                add_error(section, f"{label}: setup/seed 不是可比较的整数")
        if not isinstance(difficulty, h5py.Dataset):
            add_error(section, f"{label}: 缺少 setup/difficulty")
        else:
            try:
                if _text(difficulty, f"{label}: setup/difficulty") != record["difficulty"]:
                    add_error(section, f"{label}: setup/difficulty 与 metadata 不一致")
            except DatasetContractError as exc:
                add_error(section, str(exc))

    steps, done, terminal_errors = inspect_episode_terminal(group, label)
    for error in terminal_errors:
        add_error(section, error)
    if terminal_errors:
        return detail
    detail["timestep_count"] = len(steps)
    detail["final_is_completed"] = done

    signatures: set[tuple[tuple[int, ...], str]] = set()
    for timestep in steps:
        try:
            joint = group[f"timestep_{timestep}"]["action"]["joint_action"]
        except KeyError:
            add_error(section, f"{label}: timestep_{timestep} 缺少 action/joint_action")
            continue
        if not isinstance(joint, h5py.Dataset):
            add_error(section, f"{label}: joint_action 必须是 dataset")
            continue
        signature = (tuple(joint.shape), str(joint.dtype))
        signatures.add(signature)
        if tuple(joint.shape) != (8,) or np.dtype(joint.dtype) != np.dtype(np.float64):
            add_error(section, f"{label}: joint_action 必须是 (8,) float64")
            continue
        values = np.asarray(joint[()])
        if not np.all(np.isfinite(values)):
            add_error(section, f"{label}: joint_action 含有非有限值")
            continue
        section["joint_vector_count"] += 1
        section["joint_element_count"] += int(values.size)
    if len(signatures) == 1:
        shape, dtype = next(iter(signatures))
        detail["joint_shape"], detail["joint_dtype"] = list(shape), dtype
    elif signatures:
        add_error(section, f"{label}: joint_action 的 shape/dtype 在各帧之间不一致")
    return detail


def _audit_file(
    path: Path,
    task: str,
    records: Mapping[int, Mapping[str, Any]],
    episodes: Sequence[int],
    exact_episodes: bool,
    label: str,
) -> dict[str, Any]:
    section: dict[str, Any] = {
        "label": label,
        "task": task,
        "path": str(path),
        "episodes": [],
        "completed_count": 0,
        "joint_vector_count": 0,
        "joint_element_count": 0,
        "error_count": 0,
        "errors": [],
    }
    if not path.is_file():
        add_error(section, f"{label}/{task}: HDF5 文件不存在")
        return section
    try:
        with h5py.File(path, "r") as handle:
            groups = episode_groups(handle, f"{label}/{task}", section)
            expected = set(episodes)
            actual = set(groups)
            if not expected.issubset(actual):
                add_error(section, f"{label}/{task}: 缺少 episode {sorted(expected - actual)}")
            if exact_episodes and actual != expected:
                add_error(section, f"{label}/{task}: episode 集合与预期不完全一致")
            for episode in episodes:
                if episode not in groups:
                    continue
                detail = _audit_episode(
                    groups[episode],
                    task,
                    episode,
                    records[episode],
                    f"{label}/{task}/episode_{episode}",
                    section,
                )
                section["episodes"].append(detail)
                if detail["final_is_completed"] is True:
                    section["completed_count"] += 1
    except OSError as exc:
        add_error(section, f"{label}/{task}: 读取 HDF5 失败：{exc}")
    return section


def _audit_metadata(
    path: Path,
    task: str,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    section: dict[str, Any] = {
        "task": task,
        "path": str(path),
        "error_count": 0,
        "errors": [],
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        add_error(section, f"{task}: metadata 读取失败：{exc}")
        return section
    if not isinstance(payload, Mapping) or payload.get("env_id") != task:
        add_error(section, f"{task}: metadata 的 env_id 不匹配")
    if payload.get("record_count") != len(records):
        add_error(section, f"{task}: metadata 的 record_count 不匹配")
    if payload.get("records") != list(records):
        add_error(section, f"{task}: metadata 的 records 与 train metadata 不一致")
    return section


def _summary(audits: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    keys = ("completed_count", "joint_vector_count", "joint_element_count", "error_count")
    return {
        "file_count": len(audits),
        "episode_count": sum(len(audit["episodes"]) for audit in audits),
        **{key: sum(int(audit.get(key, 0)) for audit in audits) for key in keys},
    }


def validate_generated_dataset_contract(
    generated_root: str | Path,
    tasks: Sequence[str],
    episodes: Sequence[int],
    *,
    records_by_task: Mapping[str, Mapping[int, Mapping[str, Any]]] | None = None,
    reference_root: str | Path = REFERENCE_ROOT,
    metadata_root: str | Path = METADATA_ROOT,
) -> dict[str, Any]:
    """在指定范围内，对生成产物与官方参考数据做完整的 HDF5 契约校验。"""
    output = Path(generated_root).expanduser().resolve()
    reference = Path(reference_root).expanduser().resolve()
    ordered_tasks = list(tasks)
    episode_indices = list(episodes)
    if not ordered_tasks or len(ordered_tasks) != len(set(ordered_tasks)):
        raise DatasetContractError("校验任务列表不能为空，且不能有重复")
    if any(task not in ALL_TASKS for task in ordered_tasks):
        raise DatasetContractError("校验任务列表里含有无法识别的环境名")
    if not episode_indices or episode_indices != list(range(len(episode_indices))):
        raise DatasetContractError("校验的 episode 必须是从 0 开始的连续区间")
    if records_by_task is None:
        records_by_task = read_train_metadata(metadata_root)

    generated, official, metadata = [], [], []
    for task in ordered_tasks:
        if task not in records_by_task:
            raise DatasetContractError(f"缺少 {task} 的 train metadata")
        records_for_task = records_by_task[task]
        if any(episode not in records_for_task for episode in episode_indices):
            raise DatasetContractError(f"{task}: train metadata 缺少所请求的 episode")
        records = [records_for_task[episode] for episode in episode_indices]
        metadata.append(
            _audit_metadata(
                output / f"record_dataset_{task}_metadata.json",
                task,
                records,
            )
        )
        generated.append(
            _audit_file(
                output / f"record_dataset_{task}.h5",
                task,
                records_for_task,
                episode_indices,
                True,
                "generated",
            )
        )
        official.append(
            _audit_file(
                reference / f"record_dataset_{task}.h5",
                task,
                records_for_task,
                episode_indices,
                False,
                "official",
            )
        )

    generated_summary = _summary(generated)
    official_summary = _summary(official)
    metadata_errors = sum(int(item["error_count"]) for item in metadata)
    expected = len(ordered_tasks) * len(episode_indices)
    scope = {
        "tasks": ordered_tasks,
        "episode_indices": episode_indices,
        "expected_episode_count": expected,
        "full_16x100": (
            ordered_tasks == list(ALL_TASKS)
            and episode_indices == list(range(MAX_EPISODES))
        ),
    }
    passed = (
        metadata_errors == 0
        and generated_summary["error_count"] == 0
        and official_summary["error_count"] == 0
        and generated_summary["completed_count"] == expected
        and official_summary["completed_count"] == expected
    )
    return {
        "passed": passed,
        "scope": scope,
        "metadata": {"error_count": metadata_errors, "audits": metadata},
        "generated": {**generated_summary, "audits": generated},
        "official": {**official_summary, "audits": official},
        "acceptance": {
            "expected_final_completed": expected,
            "generated_final_completed": generated_summary["completed_count"],
            "official_final_completed": official_summary["completed_count"],
        },
    }


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验生成产物的 HDF5 与 metadata 契约")
    parser.add_argument("--output-dir", required=True, help="已存在的生成产物目录")
    parser.add_argument("--env", "--environment", default="all", help="all，或逗号分隔的环境名列表")
    parser.add_argument("--episodes", type=int, default=MAX_EPISODES, help="每个环境从 episode 0 起参与校验的 episode 数量")
    parser.add_argument("--metadata-root", default=str(METADATA_ROOT), help="当前分支的 train metadata 目录")
    parser.add_argument("--reference-root", default=str(REFERENCE_ROOT), help="官方参考 HDF5 所在目录")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _args(argv)
    try:
        if not 1 <= args.episodes <= MAX_EPISODES:
            raise DatasetContractError(f"--episodes 必须在 1..{MAX_EPISODES} 之间")
        result = validate_generated_dataset_contract(
            args.output_dir,
            parse_tasks(args.env),
            list(range(args.episodes)),
            metadata_root=args.metadata_root,
            reference_root=args.reference_root,
        )
    except DatasetContractError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
