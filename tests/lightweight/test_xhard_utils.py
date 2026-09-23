#!/usr/bin/env python3
"""轻量测试：V4 xhard 共用工具（``utils/xhard.py``）。

* ``corner_push(u, 0)`` 必须原样返回同一个对象（保证 corner_bias=0 与原均匀采样逐字等价）；
* 单调、保端点、关于 0.5 对称，b 越大越靠两端；
* 干扰色池与 B2 决策逐字一致。

    uv run --no-sync python -m pytest tests/lightweight/test_xhard_utils.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme.robomme_env.utils.xhard import DISTRACTOR_COLORS, corner_push, hsv_floor_rgb  # noqa: E402


def test_zero_bias_is_identity_object() -> None:
    for u in (0.0, 0.123456789012345, 0.5, 0.999999, 1.0):
        assert corner_push(u, 0) is u
        assert corner_push(u, 0.0) is u


def test_endpoints_symmetry_monotonic() -> None:
    for b in (0.25, 0.5, 1.0):
        assert corner_push(0.0, b) == 0.0
        assert corner_push(1.0, b) == 1.0
        assert corner_push(0.5, b) == 0.5
        grid = [i / 100 for i in range(101)]
        values = [corner_push(u, b) for u in grid]
        assert values == sorted(values)
        for u in grid:
            assert corner_push(1 - u, b) == pytest.approx(1 - corner_push(u, b), abs=1e-12)


def test_bias_pushes_outward() -> None:
    assert corner_push(0.75, 0.5) > 0.75
    assert corner_push(0.75, 1.0) > corner_push(0.75, 0.5)
    assert corner_push(0.25, 1.0) < corner_push(0.25, 0.5) < 0.25


def test_out_of_range_bias_rejected() -> None:
    with pytest.raises(ValueError):
        corner_push(0.3, 1.5)
    with pytest.raises(ValueError):
        corner_push(0.3, -0.1)


def test_distractor_palette_matches_b2() -> None:
    assert [(c["name"], c["rgba"]) for c in DISTRACTOR_COLORS] == [
        ("yellow", (1, 1, 0, 1)), ("cyan", (0, 1, 1, 1)), ("magenta", (1, 0, 1, 1)),
    ]


def test_hsv_floor_color_gamut() -> None:
    """用户 2026-09-22 定：色相任意、饱和度 ≥0.5、亮度 ≥0.4——排除近白/近黑/近灰。"""
    import colorsys
    import itertools
    grid = [0.0, 0.25, 0.5, 0.75, 0.999]
    for u in itertools.product(grid, repeat=3):
        rgb = hsv_floor_rgb(list(u))
        assert all(0.0 <= c <= 1.0 for c in rgb)
        h, s, v = colorsys.rgb_to_hsv(*rgb)
        assert s >= 0.5 - 1e-9 and v >= 0.4 - 1e-9
        assert min(rgb) <= 0.5 * max(rgb) + 1e-9  # 不会近白/近灰
