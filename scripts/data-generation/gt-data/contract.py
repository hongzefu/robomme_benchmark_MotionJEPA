#!/usr/bin/env python3
"""生成链路共用的契约常量与 metadata 读取。

只保留生成入口真正用得上的部分：任务清单、各 split 的 episode 条数、seed/difficulty
metadata 的严格读取、h5 内部 timestep 结构的校验。历史上这里还有一整套「与官方参考
数据逐位对拍」的校验器与报告生成器，本链路**不回放 joint angle、也不与官方对拍**
（同 seed 只保证场景初始摆放一致，轨迹由 planner 重新规划），故一并删除。

⚠ episode 内部结构的严格性：``episode_<i>/`` 下除了 ``setup`` 之外**只允许**出现连续
编号的 ``timestep_<k>``，多一个别的 group 就判非法。GT segmentation 之所以挂在
``timestep_<k>/obs/`` 与 ``setup/`` 内部而不是 episode 级，正是为了不触碰这条规则——
本模块对 ``setup/`` 与 ``timestep_<k>/`` 的**内部**结构不做约束。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import h5py
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[3]
# 三套 split 的 metadata 平行放在 env_metadata/{train,val,test}/，seed 与 difficulty 逐 episode 固定
ENV_METADATA_ROOT = REPO_ROOT / "src" / "robomme" / "env_metadata"
# 官方 h5 本地备份（Yinpei/robomme_data_h5），只读参考源
REFERENCE_ROOT = Path("/data/hongzefu/robomme_data_h5")

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
# 各 split 的 episode 条数是 benchmark 定死的（readme：train 100，val/test 各 50）
SPLIT_EPISODE_COUNTS = {"train": 100, "val": 50, "test": 50}
MAX_EPISODES = 100

TIMESTEP_RE = re.compile(r"^timestep_(\d+)$")


class DatasetContractError(RuntimeError):
    """生成数据或 metadata 违反了既定契约。"""


def _integer(value: Any, field: str, path: Path) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise DatasetContractError(f"{path}: {field} 必须是整数，实际拿到 {value!r}")
    return int(value)


def parse_tasks(value: str) -> list[str]:
    """把 all 或逗号分隔的任务名解析成按标准顺序排列的任务列表。"""
    if value.strip().lower() == "all":
        return list(ALL_TASKS)
    names = [item.strip() for item in value.split(",") if item.strip()]
    if not names or len(names) != len(set(names)):
        raise DatasetContractError("任务列表不能为空，且不能有重复")
    unknown = sorted(set(names) - set(ALL_TASKS))
    if unknown:
        raise DatasetContractError("无法识别的环境名：" + ", ".join(unknown))
    return [task for task in ALL_TASKS if task in names]


def read_split_metadata(
    split: str,
    tasks: Sequence[str] = ALL_TASKS,
    metadata_root: str | Path | None = None,
) -> dict[str, dict[int, dict[str, Any]]]:
    """严格读取某个 split 的 seed/difficulty metadata，不做任何静默兜底。

    ⚠ **seed 直接取用、不做任何递增重试**：metadata 里记的就是官方当时实际用的 seed
    （含官方遇到失败时递增过的值，如 MoveCube ep6 = 14602），照抄即可与官方同场景。
    """
    if split not in SPLIT_EPISODE_COUNTS:
        raise DatasetContractError(f"split 只接受 train/val/test，实际拿到 {split!r}")
    expected = SPLIT_EPISODE_COUNTS[split]
    root = Path(metadata_root or ENV_METADATA_ROOT / split).expanduser().resolve()

    ordered_tasks = tuple(tasks)
    if not ordered_tasks or len(ordered_tasks) != len(set(ordered_tasks)):
        raise DatasetContractError("metadata 任务集合不能为空，且不能有重复")
    expected_files = {f"record_dataset_{task}_metadata.json" for task in ordered_tasks}
    actual_files = {path.name for path in root.glob("record_dataset_*_metadata.json")}
    if not expected_files <= actual_files:
        raise DatasetContractError(
            f"{root}: 缺少 metadata 文件 {sorted(expected_files - actual_files)}"
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
        if len(records) != expected:
            raise DatasetContractError(
                f"{path}: {split} split 的 records 必须恰好 {expected} 条"
            )

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
        if set(indexed) != set(range(expected)):
            raise DatasetContractError(f"{path}: episode 集合必须恰好是 0..{expected - 1}")
        all_records[task] = indexed
    return all_records


def timestep_indices(group: h5py.Group, source: str) -> tuple[list[int], list[str]]:
    """解析数字编号的 timestep 名并严格校验连续性；合法的 setup group 不计入 timestep。"""
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
