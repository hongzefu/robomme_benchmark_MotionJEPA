#!/usr/bin/env python3
"""网格 mask：像素级机械臂 mask → Wan VAE latent 对齐的 32×32 格级 mask。

## 口径（用户 2026-08-12 拍板）

- **网格粒度对齐 Wan VAE 输入**：front_rgb 与 Wan VAE 输入同为 256×256，VAE 做 8×
  空间下采样，因此网格 32×32、每格 8×8 px——**一格恰对应一个 latent 空间位置**。
- **占比分子**：格内被 v4.2 像素级最终 mask（`arm_mask_v4.arm_masks_for_episode`
  的输出，产出不看 GT）判为机械臂的像素数；格内计数 ≥ `min_pixels` ⇒ 整格标臂。
  判据是**整数比较**，分数入口 `GridParams.from_fraction` 用有理数精确换算，全链路
  没有浮点边界。
- **阈值全局统一**：`min_pixels` 是唯一阈值，对全部任务、全部 episode、全部格子
  位置一体生效。本模块与扫描入口都**不提供** per-task / per-episode / per-cell 的
  覆盖通道——这是口径不是省事，用户原话「阈值是全局全task/episode全8*8位置必须
  统一的！」。
- `min_pixels` **刻意没有默认值**：阈值本身待标定（`grid_sweep.py` 扫全 64 档供
  目视挑选），在代码里给默认值等于偷偷立第二个口径。

## ⚠ 两条必须记住的性质

1. **网格 mask 打破了 v4.2「只减不增」的链路单调性**。四条形态学规则每条都只让
   区域变小或持平，而网格化在 `min_pixels=1` 时是像素 mask 的**严格超集**——它是
   整条链路第一个会让区域**变大**的算子。因此「不得把物体判错成 robot arm」的刚性
   红线**不适用于网格口径**（整格涂红必然覆盖物体/背景像素），GT 只做量化记录、
   不设闸门。不要拿 README「刚性原则」一节的结论来推网格 mask 的性质。
2. 替代性质是**对阈值单调**：`K1 ≤ K2 ⇒ grid(K2) ⊆ grid(K1)`。

## 逐帧独立

时间维的处理（`is_video_demo` 相位切段 + 3 帧多数表决）已经在
`arm_masks_for_episode` 里做完，网格化是逐格纯计数、无任何状态，因此本模块只接受
**单帧** 2D mask，签名上不接受帧序列与相位参数，钉死不引入时间依赖。若将来要在
格级加时间平滑，注意 `arm_mask_v4` 第④条的白名单交**兜不住格级**的非单调性。

另注：Wan VAE 还有时间维 4× 压缩（首帧单独成组），本模块只对齐空间 8×，时间维
不在本轮范围（见 README 网格 mask 一节）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

import numpy as np


# Wan VAE 空间下采样倍率 = 格子边长（px）。只作文档锚点：下面的函数全部按输入形状
# 与 cell_size 推导，不硬编码 256/32——若将来喂进 Wan 的分辨率变了，只需换 cell_size
# 并重推对齐关系。
WAN_VAE_SPATIAL_DOWNSAMPLE = 8
FRONT_FRAME_SIZE = 256  # front_rgb 实测 (256, 256, 3) uint8
GRID_SIZE = FRONT_FRAME_SIZE // WAN_VAE_SPATIAL_DOWNSAMPLE  # = 32


@dataclass(frozen=True)
class GridParams:
    """网格化仅有的两个参数。`min_pixels` 无默认值，强制每个调用点显式写。"""

    min_pixels: int
    cell_size: int = WAN_VAE_SPATIAL_DOWNSAMPLE

    def __post_init__(self) -> None:
        # 拒绝 float（含 0.5 这类想当分数用的值）：判据必须是整数比较，
        # 分数请走 from_fraction 的精确换算
        if not isinstance(self.min_pixels, (int, np.integer)) or isinstance(
            self.min_pixels, bool
        ):
            raise ValueError(f"min_pixels 必须是 int：{self.min_pixels!r}")
        if not isinstance(self.cell_size, (int, np.integer)) or isinstance(
            self.cell_size, bool
        ):
            raise ValueError(f"cell_size 必须是 int：{self.cell_size!r}")
        if self.cell_size < 1:
            raise ValueError(f"cell_size 必须 ≥ 1：{self.cell_size}")
        # K=0 意味着全图涂满、K>c² 恒空，都是无意义口径，当场拒绝
        if not 1 <= self.min_pixels <= self.cell_size**2:
            raise ValueError(
                f"min_pixels 必须在 [1, {self.cell_size**2}] 内：{self.min_pixels}"
            )

    @classmethod
    def from_fraction(
        cls, fraction: float | str, cell_size: int = WAN_VAE_SPATIAL_DOWNSAMPLE
    ) -> "GridParams":
        """占比 → 整数像素数：格内占比 ≥ fraction ⟺ 计数 ≥ ceil(fraction · cell_size²)。

        用 `Fraction(str(fraction))` 转精确有理数再 ceil，0.5→32、0.1→7、
        0.203125→13 都是确定的，不存在 `0.3*64 = 19.199999…` 这类浮点边界抖动。
        """
        exact = Fraction(str(fraction))
        if not 0 < exact <= 1:
            raise ValueError(f"fraction 必须在 (0, 1] 内：{fraction!r}")
        return cls(min_pixels=int(math.ceil(exact * cell_size**2)), cell_size=cell_size)


def _as_2d_bool(mask: np.ndarray) -> np.ndarray:
    array = np.asarray(mask)
    if array.ndim != 2:
        raise ValueError(f"mask 必须是单帧 2D（逐帧独立是口径）：shape={array.shape}")
    if array.dtype != np.bool_:
        raise ValueError(f"mask 必须是 bool：{array.dtype}")
    return array


def cell_counts(mask: np.ndarray, cell_size: int = WAN_VAE_SPATIAL_DOWNSAMPLE) -> np.ndarray:
    """(H, W) bool → (H//c, W//c) int64：每格内 True 的像素数。

    这是整条链路唯一与阈值无关的量——扫描入口靠它把 65 档阈值降成一次计算
    （任意阈值的聚合指标都是逐计数档位累计表的后缀和）。
    """
    array = _as_2d_bool(mask)
    height, width = array.shape
    if height % cell_size or width % cell_size:
        # 不许静默裁边：尺寸对不上说明喂错了帧或格子口径变了
        raise ValueError(
            f"帧尺寸 {array.shape} 不能被 cell_size={cell_size} 整除，拒绝静默裁边"
        )
    counts = (
        array.reshape(height // cell_size, cell_size, width // cell_size, cell_size)
        .sum(axis=(1, 3))
    )
    assert counts.max(initial=0) <= cell_size**2
    return counts


def grid_from_counts(counts: np.ndarray, min_pixels: int) -> np.ndarray:
    """(gh, gw) int → (gh, gw) bool：整数比较 counts ≥ min_pixels。"""
    return np.asarray(counts) >= int(min_pixels)


def grid_mask(mask: np.ndarray, params: GridParams) -> np.ndarray:
    """(H, W) bool 像素 mask → (gh, gw) bool 格级 mask。"""
    return grid_from_counts(cell_counts(mask, params.cell_size), params.min_pixels)


def upsample_grid(grid: np.ndarray, cell_size: int = WAN_VAE_SPATIAL_DOWNSAMPLE) -> np.ndarray:
    """(gh, gw) bool → (gh·c, gw·c) bool：最近邻块状展开。

    实现固定为 `np.repeat` 两次：保持 bool dtype，且「块状」是它的定义而不是近似。
    ⚠ 禁止 cv2.resize（哪怕 INTER_NEAREST）与任何插值路径——块状硬边正是下游要
    消费/目视的东西；⚠ 不用 np.kron——它会把 bool 提升成 int。
    """
    array = _as_2d_bool(grid)
    return np.repeat(np.repeat(array, cell_size, axis=0), cell_size, axis=1)


def grid_mask_pixels(mask: np.ndarray, params: GridParams) -> np.ndarray:
    """(H, W) bool → (H, W) bool：块状网格 mask，与输入同形。"""
    return upsample_grid(grid_mask(mask, params), params.cell_size)
