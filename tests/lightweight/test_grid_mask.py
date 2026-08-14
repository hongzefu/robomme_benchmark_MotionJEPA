"""网格 mask（Wan VAE latent 对齐）的逻辑测试（纯合成数据，毫秒级，不碰 h5）。

覆盖四件事：

1. **格子-像素严格对齐**：cell (i,j) ↔ 像素 [c·i : c·(i+1), c·j : c·(j+1)]，以及
   「≥ min_pixels」的整数判据边界。
2. **参数守卫**：min_pixels/cell_size 的合法区间、拒绝 float、from_fraction 的
   有理数精确换算（不依赖浮点比较）。
3. **两条结构性质**：min_pixels=1 时网格是像素 mask 的严格超集（打破像素链路
   「只减不增」单调性——这是刻意口径，见 grid_mask.py docstring）；对阈值单调收缩。
4. **65 行累计表的后缀和 == 直算**：evaluate.py 的全部网格口径指标都从逐计数档位
   累计表推导，这条锁死该推导与「真上采样后与 GT 求交」逐位相等，是全套指标的地基。
"""

from __future__ import annotations

import dataclasses
import importlib
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_GEN_DIR = REPO_ROOT / "scripts" / "data-generation"

# 重构后同名模块只剩一份（历史上 v4/v4.1/v4.2 三份同名，需要 sys.modules 隔离导入器），
# 因此这里直接按目录加载即可。
for _path in (str(DATA_GEN_DIR / "arm-mask"), str(DATA_GEN_DIR / "gt-data")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

grid_mask_mod = importlib.import_module("grid_mask")
arm_mask_mod = importlib.import_module("arm_mask")

GridParams = grid_mask_mod.GridParams
cell_counts = grid_mask_mod.cell_counts
grid_from_counts = grid_mask_mod.grid_from_counts
grid_mask = grid_mask_mod.grid_mask
grid_mask_pixels = grid_mask_mod.grid_mask_pixels
upsample_grid = grid_mask_mod.upsample_grid
apply_red_mask = arm_mask_mod.apply_red_mask

C = 8  # 测试统一用默认格边长（Wan VAE 空间 8×）


def _rng() -> np.random.Generator:
    return np.random.default_rng(42)


def test_格子与像素严格对齐():
    mask = np.zeros((32, 24), bool)
    # 只在 cell (2,1) 的像素范围 [16:24, 8:16] 内置 5 个位
    mask[16, 8] = mask[17, 9] = mask[23, 15] = mask[20, 12] = mask[16, 15] = True
    counts = cell_counts(mask, C)
    assert counts.shape == (4, 3)
    assert counts[2, 1] == 5
    counts[2, 1] = 0
    assert counts.sum() == 0  # 其余格必须全零


def test_阈值边界是大于等于K():
    for k in (1, 2, 32, 64):
        mask = np.zeros((8, 8), bool)
        mask.ravel()[:k] = True  # 恰好 K 个像素
        assert grid_mask(mask, GridParams(min_pixels=k))[0, 0]
        mask.ravel()[k - 1] = False  # K−1 个像素
        assert not grid_mask(mask, GridParams(min_pixels=k))[0, 0]


def test_参数守卫拒绝非法区间与float():
    for bad in (0, 65, -1):
        with pytest.raises(ValueError):
            GridParams(min_pixels=bad)
    with pytest.raises(ValueError):
        GridParams(min_pixels=0.5)  # float 一律拒绝，分数走 from_fraction
    with pytest.raises(ValueError):
        GridParams(min_pixels=32.0)
    with pytest.raises(ValueError):
        GridParams(min_pixels=True)  # bool 是 int 子类，同样拒绝
    with pytest.raises(ValueError):
        GridParams(min_pixels=1, cell_size=0)
    # 合法边界值必须通过
    GridParams(min_pixels=1)
    GridParams(min_pixels=64)
    GridParams(min_pixels=1, cell_size=1)


def test_分数换算精确不依赖浮点():
    assert GridParams.from_fraction(0.5).min_pixels == 32
    assert GridParams.from_fraction(0.25).min_pixels == 16
    assert GridParams.from_fraction(0.1).min_pixels == 7  # ceil(6.4)
    assert GridParams.from_fraction("0.203125").min_pixels == 13  # 恰 13/64，不多取
    assert GridParams.from_fraction(0.3).min_pixels == 20  # ceil(19.2)，非 19.1999… 抖动
    assert isinstance(GridParams.from_fraction(0.5).min_pixels, int)
    assert GridParams.from_fraction(1).min_pixels == 64
    for bad in (0, -0.1, 1.5):
        with pytest.raises(ValueError):
            GridParams.from_fraction(bad)


def test_上采样是最近邻块状且保持bool():
    grid = _rng().random((4, 3)) > 0.5
    up = upsample_grid(grid, C)
    assert up.dtype == np.bool_
    # 与 np.kron 对拍逐位相等（kron 只在测试里当参照，模块内禁用——dtype 会被提升）
    ref = np.kron(grid, np.ones((C, C), int)).astype(bool)
    assert np.array_equal(up, ref)
    # 每个 8×8 块内部取值恒定——这就是「无插值」的可检验形式
    blocks = up.reshape(4, C, 3, C)
    assert np.all(blocks.min(axis=(1, 3)) == blocks.max(axis=(1, 3)))


def test_尺寸不整除必须fail_loud():
    with pytest.raises(ValueError):
        cell_counts(np.zeros((250, 256), bool), C)
    with pytest.raises(ValueError):
        cell_counts(np.zeros((256, 250), bool), C)


def test_K为1时是像素mask的超集():
    mask = _rng().random((64, 64)) > 0.9
    up = grid_mask_pixels(mask, GridParams(min_pixels=1))
    assert np.array_equal(up | mask, up)  # mask ⊆ grid
    # 且只要存在非满格的命中格，就是严格超集（打破「只减不增」的实证）
    if mask.any() and not mask.all():
        assert up.sum() > mask.sum()


def test_对阈值单调收缩():
    mask = _rng().random((64, 64)) > 0.6
    previous = None
    for k in range(1, 65):
        current = grid_mask(mask, GridParams(min_pixels=k))
        if previous is not None:
            assert np.array_equal(current & previous, current)  # grid(K) ⊆ grid(K−1)
        previous = current


def test_K为64等价于整格全满():
    mask = np.zeros((16, 16), bool)
    mask[0:8, 0:8] = True  # cell (0,0) 全满
    mask[8:16, 8:16] = True
    mask[15, 15] = False  # cell (1,1) 差一个像素
    grid = grid_mask(mask, GridParams(min_pixels=64))
    assert grid[0, 0] and not grid[1, 1] and not grid[0, 1] and not grid[1, 0]


def test_全空与全满输入():
    for k in (1, 32, 64):
        assert not grid_mask(np.zeros((32, 32), bool), GridParams(min_pixels=k)).any()
        assert grid_mask(np.ones((32, 32), bool), GridParams(min_pixels=k)).all()


def test_涂红只动网格内像素且不就地改写():
    rng = _rng()
    rgb = rng.integers(0, 255, (32, 32, 3), np.uint8)
    original = rgb.copy()
    mask = rng.random((32, 32)) > 0.9
    up = grid_mask_pixels(mask, GridParams(min_pixels=1))
    painted = apply_red_mask(rgb, up)
    assert np.array_equal(rgb, original)  # 原图不被就地改写
    assert np.all(painted[up] == (255, 0, 0))
    assert np.array_equal(painted[~up], rgb[~up])


def test_三分解恒等式():
    rng = _rng()
    mask = rng.random((64, 64)) > 0.7
    gt = rng.integers(0, 3, (64, 64))  # 三类穷尽：0 背景 / 1 物体 / 2 臂
    up = grid_mask_pixels(mask, GridParams(min_pixels=4))
    painted = int(up.sum())
    parts = sum(int((up & (gt == c)).sum()) for c in (0, 1, 2))
    assert parts == painted == int(grid_mask(mask, GridParams(min_pixels=4)).sum()) * 64


def test_累计表后缀和等于直算():
    """65 行逐计数档位累计表的后缀和，必须与「真上采样后与 GT 求交」逐位相等。

    evaluate.py 的全部网格口径指标都建立在这条推导上，这里用小规模合成数据锁死。
    """
    rng = _rng()
    frames = [
        (rng.random((32, 32)) > t, rng.integers(0, 3, (32, 32)))
        for t in (0.3, 0.7, 0.95)
    ]
    cell_area = C * C
    # 累计表：与 evaluate.py 同法——bincount 按格计数档位累计
    table = np.zeros((cell_area + 1, 4), np.int64)  # 列：格数、GT臂px、GT物体px、GT背景px
    for mask, gt in frames:
        counts = cell_counts(mask, C).ravel()
        table[:, 0] += np.bincount(counts, minlength=cell_area + 1)
        for column, cls in ((1, 2), (2, 1), (3, 0)):
            per_cell = cell_counts(gt == cls, C).ravel()
            table[:, column] += np.bincount(
                counts, weights=per_cell, minlength=cell_area + 1
            ).astype(np.int64)
    for k in (1, 2, 13, 32, 64):
        suffix = table[k:].sum(axis=0)
        # 直算：真上采样成像素 mask，再与 GT 逐像素求交
        direct = np.zeros(4, np.int64)
        for mask, gt in frames:
            up = grid_mask_pixels(mask, GridParams(min_pixels=k))
            direct[0] += int(grid_mask(mask, GridParams(min_pixels=k)).sum())
            for column, cls in ((1, 2), (2, 1), (3, 0)):
                direct[column] += int((up & (gt == cls)).sum())
        assert np.array_equal(suffix, direct), f"K={k} 后缀和与直算不一致"


def test_纯函数无副作用且参数不可变():
    mask = _rng().random((32, 32)) > 0.5
    snapshot = mask.copy()
    params = GridParams(min_pixels=13)
    cell_counts(mask, C)
    grid_mask(mask, params)
    grid_mask_pixels(mask, params)
    assert np.array_equal(mask, snapshot)
    with pytest.raises(dataclasses.FrozenInstanceError):
        params.min_pixels = 1  # type: ignore[misc]


def test_签名拒绝序列输入钉死逐帧独立():
    frames = [np.zeros((16, 16), bool) for _ in range(3)]
    with pytest.raises(ValueError):
        grid_mask(np.stack(frames), GridParams(min_pixels=1))  # 3D 直接拒绝
    with pytest.raises(ValueError):
        cell_counts(np.zeros((16, 16), np.uint8), C)  # 非 bool 也拒绝
