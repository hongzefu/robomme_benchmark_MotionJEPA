#!/usr/bin/env python3
"""把纯 CV 去机械臂结果写入 ``front_rgb_masked``。

v3 保留 v2 的字段名，方便现有训练与 flow 回放代码继续读取；字段语义已经改变：输入只有本 episode
的 ``front_rgb`` 与 ``front_depth``，不读取 segmentation，也不根据机器人/link 名称做判断。
机械臂（包括夹爪）由 ``cv_arm_removal.py`` 的颜色、几何连通与时序背景规则删除；未命中掩码的
原图像素逐位不变，因此桌面不会像 v2 那样整块被涂成纯色。
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import h5py
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent

from cv_arm_removal import remove_robot_arm_sequence  # noqa: E402
from flow_tracker import _timestep_names  # noqa: E402


MASKED_RGB_SCHEMA_VERSION = "masked-rgb-cv-v3"
MASKED_RGB_METHOD = "episode-temporal-cv-arm-removal"


def _jsonable(value: Any) -> Any:
    """把 dataclass / NumPy 标量递归转成可稳定写入 JSON 的基本类型。"""
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _write_text(group: h5py.Group, name: str, value: str) -> None:
    group.create_dataset(name, data=value, dtype=h5py.string_dtype(encoding="utf-8"))


def write_masked_rgb_setup(
    setup_group: h5py.Group,
    *,
    config: Any,
    stats: Mapping[str, Any],
) -> None:
    """写 episode 级算法审计信息；不伪造 v2 的 painted/kept 对象清单。"""
    _write_text(setup_group, "masked_rgb_schema_version", MASKED_RGB_SCHEMA_VERSION)
    _write_text(setup_group, "masked_rgb_method", MASKED_RGB_METHOD)
    _write_text(setup_group, "masked_rgb_source_fields", "front_rgb,front_depth")
    _write_text(
        setup_group,
        "masked_rgb_untouched_contract",
        "output[~arm_mask] == front_rgb[~arm_mask]",
    )
    _write_text(
        setup_group,
        "masked_rgb_config_json",
        json.dumps(_jsonable(config), ensure_ascii=False, sort_keys=True),
    )
    _write_text(
        setup_group,
        "masked_rgb_stats_json",
        json.dumps(_jsonable(stats), ensure_ascii=False, sort_keys=True),
    )


def write_masked_rgb_groups(
    episode_group: h5py.Group,
    sources: Sequence[tuple[Any, Any]],
) -> int:
    """对完整 episode 做纯 CV 去臂并逐帧写盘，返回写入帧数。

    ``sources`` 中每项是 ``(front_rgb, front_depth)``。完整序列一次性交给算法，是为了能从机械臂
    移开后的帧恢复同一像素处的真实桌面木纹；只对单帧做大洞 inpaint 会产生明显模糊斑块。
    """
    timestep_names = _timestep_names(episode_group)
    if len(timestep_names) != len(sources):
        raise ValueError(
            f"timestep 数量（{len(timestep_names)}）与 RGB-D 源帧数（{len(sources)}）不一致"
        )
    if not sources:
        raise ValueError("RGB-D 源帧为空，无法生成纯 CV 去臂图")

    rgb_frames = np.stack([np.asarray(rgb) for rgb, _ in sources], axis=0)
    depth_frames = np.stack([np.asarray(depth) for _, depth in sources], axis=0)
    result = remove_robot_arm_sequence(rgb_frames, depth_frames)

    output = np.asarray(result.frames)
    masks = np.asarray(result.masks, dtype=bool)
    if output.shape != rgb_frames.shape:
        raise ValueError(f"去臂结果 shape 非法：{output.shape}，期望 {rgb_frames.shape}")
    if output.dtype != np.uint8:
        raise ValueError(f"去臂结果 dtype 非法：{output.dtype}，期望 uint8")
    if masks.shape != rgb_frames.shape[:3]:
        raise ValueError(
            f"去臂 mask shape 非法：{masks.shape}，期望 {rgb_frames.shape[:3]}"
        )
    # 核心契约：算法不得悄悄改写 mask 外的桌面或任务物体。
    if not np.array_equal(output[~masks], rgb_frames[~masks]):
        raise ValueError("纯 CV 去臂违反未命中像素逐位不变契约")

    setup_group = episode_group.get("setup")
    if not isinstance(setup_group, h5py.Group):
        raise ValueError("episode 下缺少 setup group，无法写入 masked_rgb 元数据")
    write_masked_rgb_setup(setup_group, config=result.config, stats=result.stats)

    for index, name in enumerate(timestep_names):
        obs_group = episode_group[name].get("obs")
        if not isinstance(obs_group, h5py.Group):
            raise ValueError(f"{name} 下缺少 obs group")
        if "front_rgb_masked" in obs_group:
            raise ValueError(f"{name}/obs 下已存在 front_rgb_masked，拒绝覆盖")
        obs_group.create_dataset("front_rgb_masked", data=output[index])

    return len(timestep_names)
