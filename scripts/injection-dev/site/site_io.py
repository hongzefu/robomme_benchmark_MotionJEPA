"""site/ 只读出图工具（文件名不用 _io：与 Python 内建模块 _io 重名）的共用读写（原 ``scripts/parity/v4_specs.py`` 的 ``_read_jsonl`` / ``_check_sources`` 搬来）。

``sampling_config`` 快照 ``scripts/configs/newtask-v6/sampling_config.json`` 已删；默认配置改读包内
``src/robomme_hard/env_metadata/test-hard/xhard4/specs.jsonl`` header 的 ``sampling_config``（16 任务，与原快照逐任务相同）。
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGED_XHARD4 = REPO_ROOT / "src" / "robomme_hard" / "env_metadata" / "test-hard" / "xhard4" / "specs.jsonl"
RUNTIME = {"obs_mode": "rgb+depth+segmentation", "control_mode": "pd_joint_pos", "render_mode": "rgb_array",
           "reward_mode": "dense"}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 存在重复字段：{key}")
        result[key] = value
    return result


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as stream:
        records = [json.loads(line, object_pairs_hook=_unique_object) for line in stream if line.strip()]
    if not records:
        raise ValueError(f"{path} 为空")
    return records


def _digest(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def packaged_sampling_document() -> dict[str, Any]:
    header = json.loads(PACKAGED_XHARD4.open(encoding="utf-8").readline())
    return {"tasks": copy.deepcopy(header["sampling_config"])}


V6_FROZEN = REPO_ROOT / "scripts" / "configs" / "newtask-v6" / "v6-sampling-frozen.json"


def frozen_v6_sampling_document() -> dict[str, Any]:
    """v6 定值快照（v7 换包后包内 header 已是 v7 定值；v6 检查器一律读这份）。xhard4 档含全部 16 任务。"""
    frozen = json.loads(V6_FROZEN.read_text(encoding="utf-8"))
    return {"tasks": copy.deepcopy(frozen["sampling_config"]["xhard4"])}


def load_sampling_document(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return packaged_sampling_document()
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _check_sources(header: dict[str, Any], sampling_document: dict[str, Any], label: str) -> None:
    """封存的来源与给定配置逐项比对：配置全文、配置散列自洽、runtime。
    （原实现还比 ``src/robomme/robomme_env`` 的源码指纹；拆包后环境源码在 robomme_hard，旧指纹不再适用，不比。）"""
    problems = []
    for task in header["tasks"]:
        block = sampling_document["tasks"].get(task)
        if block is not None and header["sampling_config"].get(task) != {"decision": block["decision"],
                                                                          "native": block["native"]}:
            problems.append(f"sampling_config[{task}]")
    if header["sampling_config_sha256"] != _digest(header["sampling_config"]):
        problems.append("sampling_config_sha256 与内嵌配置不自洽")
    if header["runtime"] != RUNTIME:
        problems.append("runtime")
    if problems:
        raise ValueError(f"{label}：封存的来源与配置不一致：{problems}")
