#!/usr/bin/env python3
"""机械臂区域标定：三类标签图进，红遮罩出。

这一步**完全不看 ground truth**。输入只有 `color_model.ColorModel.classify` 给出的
逐帧三类标签图，规则一共四条，按顺序执行：

1. **开运算**（先腐蚀后膨胀，3×3）——去掉抗锯齿边缘和阴影上零星的臂色噪点。
   先腐蚀保证它只会让候选区变小或持平，不会往物体那边长。
2. **从上方进入的连通域**——只保留碰到画面上边界的连通分量。机械臂根部固定在
   画面顶部、整条臂从上方伸进来；桌面上的任务物体不触顶，这一条就是「不误标物体」
   最主要的结构性保障，比任何颜色阈值都硬。
3. **时间平滑**——3 帧滑动多数表决。渲染逐帧独立，误判往往只闪一两帧，
   多数表决把它们抹掉；真正的臂连续存在，不受影响。
4. **保守收缩**——只保留**当前帧自己**被判成机械臂的像素（判为物体的、判为背景的、
   以及颜色表没见过的一律扣掉，哪怕它连着臂），再整体腐蚀一次。

四条规则的方向是刻意统一的：**每一条都只会让标定区域变小或持平**（第 1 条的膨胀
只是把腐蚀掉的臂身补回来，受腐蚀结果约束，不会超出原候选）。这正对应本链路的宗旨——
**绝不误标其他物体，允许少量机械臂没被标进去**。

⚠ 第 4 条写成「只保留本帧的臂」而不是「扣掉物体」是必须的，留出集实测抓到过反例：
时间平滑是多数表决，会把**本帧不在候选里、但前后帧在**的像素补进来。InsertPeg 有
292 个像素就是这么被补出来的，颜色在拟合表里压根没出现过。收紧之后时间平滑只能删
不能加，上面那条「只变小或持平」的原则才真正成立。

### 参数

只有三个整数，且都是形态学的最小配置（结构元固定 3×3 四邻域）：开运算 1 次、
时间窗 3 帧、最终腐蚀 1 次。它们不是「阈值」——没有任何一个是在某个连续量上切一刀，
调大调小只改变收缩的力度，不改变判据本身。

### 相位切段

`info/is_video_demo` 标出的两个相位之间场景会重摆，跨相位做时间平滑等于把两个不同
场景的帧混在一起投票。因此平滑严格按相位分段进行，段内独立。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np

from color_model import CLASS_ARM


# 涂红用的纯红，与 v3 / v3.1 口径一致：被标定的像素涂 (255, 0, 0)，其余像素逐位不动
RED = (255, 0, 0)

# 形态学结构元：3×3 全 1（八邻域）。固定不动，不作为可调项
KERNEL = np.ones((3, 3), np.uint8)


@dataclass(frozen=True)
class MaskParams:
    """三个整数就是全部可调项，含义见模块 docstring。"""

    open_iterations: int = 1
    temporal_window: int = 3
    final_erode: int = 1

    def __post_init__(self) -> None:
        if self.open_iterations < 0 or self.final_erode < 0:
            raise ValueError("形态学次数不能为负")
        if self.temporal_window < 1 or self.temporal_window % 2 == 0:
            raise ValueError(f"时间窗必须是正奇数：{self.temporal_window}")


def _open(mask: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0:
        return mask
    opened = cv2.morphologyEx(
        mask.astype(np.uint8), cv2.MORPH_OPEN, KERNEL, iterations=iterations
    )
    return opened.astype(bool)


def _keep_top_entering(mask: np.ndarray) -> np.ndarray:
    """只保留碰到画面上边界的连通分量。"""
    if not mask.any():
        return mask
    count, components = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    if count <= 1:
        return np.zeros_like(mask)
    top_labels = set(np.unique(components[0]).tolist()) - {0}
    if not top_labels:
        return np.zeros_like(mask)
    return np.isin(components, list(top_labels))


def _temporal_majority(masks: Sequence[np.ndarray], window: int) -> list[np.ndarray]:
    """滑动窗口多数表决；窗口在序列两端自动缩短，不做补边。"""
    if window <= 1 or len(masks) <= 1:
        return [np.array(mask, copy=True) for mask in masks]
    half = window // 2
    stacked = np.stack([mask.astype(np.uint8) for mask in masks])
    smoothed: list[np.ndarray] = []
    for index in range(len(masks)):
        low = max(0, index - half)
        high = min(len(masks), index + half + 1)
        piece = stacked[low:high]
        smoothed.append(piece.sum(axis=0) * 2 > piece.shape[0])
    return smoothed


def _erode(mask: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0:
        return mask
    eroded = cv2.erode(mask.astype(np.uint8), KERNEL, iterations=iterations)
    return eroded.astype(bool)


def arm_masks_for_segment(
    labels: Sequence[np.ndarray],
    params: MaskParams = MaskParams(),
) -> list[np.ndarray]:
    """一个相位段内的逐帧标签图 → 逐帧机械臂 mask。"""
    candidates = [np.asarray(item) == CLASS_ARM for item in labels]
    candidates = [_open(item, params.open_iterations) for item in candidates]
    candidates = [_keep_top_entering(item) for item in candidates]
    candidates = _temporal_majority(candidates, params.temporal_window)

    finished: list[np.ndarray] = []
    for mask, label_map in zip(candidates, labels):
        # 硬否决：只保留**当前帧自己**被判成机械臂的像素。这一条同时干掉三种东西——
        # 判为物体的像素（接触帧里与臂连成一片的那些）、判为背景的像素，以及颜色表
        # 没见过的 UNKNOWN 像素。
        #
        # ⚠ 写成「≠ 物体」是不够的，留出集实测抓到过：时间平滑是多数表决，它会把
        # 「本帧不在候选里、但前后帧在」的像素**补进来**——InsertPeg 有 292 个像素
        # 就是这么被补出来的，颜色（品红系 (135,38,114) 等）在拟合表里压根没出现过。
        # 收紧成「必须是本帧判定的机械臂」之后，时间平滑就只能删不能加，
        # 「每条规则都只让标定区域变小或持平」这条设计原则才真正成立。
        mask = mask & (np.asarray(label_map) == CLASS_ARM)
        finished.append(_erode(mask, params.final_erode))
    return finished


def arm_masks_for_episode(
    labels: Sequence[np.ndarray],
    is_video_demo: Sequence[bool],
    params: MaskParams = MaskParams(),
) -> list[np.ndarray]:
    """整个 episode：按 `is_video_demo` 切相位段，段内独立跑上面那四条规则。"""
    if len(labels) != len(is_video_demo):
        raise ValueError(
            f"标签帧数（{len(labels)}）与相位标记数（{len(is_video_demo)}）不一致"
        )
    masks: list[np.ndarray | None] = [None] * len(labels)
    start = 0
    for index in range(1, len(labels) + 1):
        if index == len(labels) or bool(is_video_demo[index]) != bool(
            is_video_demo[start]
        ):
            segment = arm_masks_for_segment(labels[start:index], params)
            for offset, mask in enumerate(segment):
                masks[start + offset] = mask
            start = index
    if any(mask is None for mask in masks):
        raise RuntimeError("相位切段没有覆盖全部帧")
    return [mask for mask in masks if mask is not None]


def apply_red_mask(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """标定像素涂纯红，其余像素与原图逐位相同。"""
    painted = np.array(rgb, copy=True)
    painted[np.asarray(mask)] = RED
    return painted
