#!/usr/bin/env python3
"""轻量测试：V7 定值表（0928 方案 §3.2.2）——13 个梯度任务 × 4 档的类常量与 decision 逐项等于定值表。

纯 CPU、不起 sapien：只读类属性 ``configs`` 与 ``native_blocks`` 导出的 decision 块。
每个维度每档必须是一个定数（区间两端相等），数值见 ``tests/_shared/v7_tier_values.py``。

    uv run --no-sync python -m pytest tests/lightweight/test_v7_tier_values.py -q -s
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402
from tests._shared.v7_tier_values import TIERS, V7_TIER_VALUES, NotFixedValue, summarize  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme_hard.robomme_env.utils import unmask_distractor_sampler as uds  # noqa: E402
from robomme_hard.robomme_env.utils.xhard import BLOCK_DISTRACTOR_COLORS, DISTRACTOR_COLORS  # noqa: E402

TASKS = tuple(V7_TIER_VALUES)
#: native_blocks 带 release 参数的五个环境：newtask-v7 与 v6 同一解析路径
RELEASE_AWARE = ("VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick", "VideoPlaceButton", "VideoPlaceOrder")


def _module(task):
    return importlib.import_module(f"robomme_hard.robomme_env.{task}")


def _decision(task):
    module = _module(task)
    decision, _native = module.native_blocks(getattr(module, task))
    return decision


def _config_values(task, cls):
    """从类常量 ``configs`` 读能对上的维度（各任务 configs 键名不同，只取与定值表同义的那几个）。"""
    out = {}
    for tier in TIERS:
        cfg = cls.configs[tier]
        if task in ("PickXtimes", "SwingXtimes"):
            assert cfg["number_min"] == cfg["number_max"], (task, tier, cfg)
            row = {"number": cfg["number_min"]}
        elif task in ("VideoUnmask", "ButtonUnmask"):
            assert cfg["bin"] == 8, (task, tier, cfg)  # 内环 8 个固定
            row = {"pick": cfg["pick"]}
        elif task in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
            assert cfg["bin"] == 4 and cfg["swap_min"] == cfg["swap_max"] and cfg["pick_min"] == cfg["pick_max"]
            row = {"swap": cfg["swap_min"], "pick": cfg["pick_min"]}
        elif task == "VideoRepick":
            assert cfg["swap_min"] == cfg["swap_max"] and cfg["num_repeats_high_exclusive"] == cfg["num_repeats_low"] + 1
            row = {"cube": cfg["cube"], "swap": cfg["swap_min"], "repick": cfg["num_repeats_low"]}
        elif task in ("PatternLock", "RouteStick"):
            lo, hi = cfg["length"]
            assert lo == hi, (task, tier, cfg)
            row = {"length": lo}
        elif task == "BinFill":
            assert cfg["spawn_cubes"][0] == cfg["spawn_cubes"][1] and cfg["put_in_numbers"][0] == cfg["put_in_numbers"][1]
            row = {"spawn": cfg["spawn_cubes"][0], "put_in": cfg["put_in_numbers"][0]}
        elif task == "PickHighlight":
            assert cfg["spawn"][0] == cfg["spawn"][1] and cfg["pickup"][0] == cfg["pickup"][1]
            row = {"spawn": cfg["spawn"][0], "pick": cfg["pickup"][0]}
        elif task == "VideoPlaceButton":
            row = {"targets": cfg["targets"]}
        else:  # VideoPlaceOrder：放台次数只在 decision 里
            row = {}
        out[tier] = row
    return {dim: tuple(out[tier][dim] for tier in TIERS) for dim in out[TIERS[0]]}


@pytest.mark.parametrize("task", TASKS)
def test_decision各档定值等于V7定值表(task):
    assert summarize(task, _decision(task)) == V7_TIER_VALUES[task]


@pytest.mark.parametrize("task", TASKS)
def test_类常量各档定值等于V7定值表(task):
    module = _module(task)
    got = _config_values(task, getattr(module, task))
    expected = {dim: V7_TIER_VALUES[task][dim] for dim in got}
    assert got == expected


def test_V7定值表总判定行(capsys):
    """逐任务汇总：13 任务 × 4 档全部等于定值表才 PASS（打印 V7_TIER_VALUES 行供留证）。"""
    bad = {}
    for task in TASKS:
        try:
            got = summarize(task, _decision(task))
        except NotFixedValue as exc:
            bad[task] = str(exc)
            continue
        if got != V7_TIER_VALUES[task]:
            bad[task] = got
    with capsys.disabled():
        print(f"\nV7_TIER_VALUES={'PASS' if not bad else 'FAIL'} tasks={len(TASKS)} tiers={len(TIERS)} bad={bad}")
    assert not bad
    assert len(TASKS) == 13


def test_读取函数拒绝区间():
    """V7 口径「每档一个定数」：把某档改回区间，读取函数必须报错。"""
    decision = _decision("PickXtimes")
    decision["number_range"]["xhard2"] = [8, 9]
    with pytest.raises(NotFixedValue):
        summarize("PickXtimes", decision)


@pytest.mark.parametrize("task", RELEASE_AWARE)
def test_release_v7与缺省解析路径相同(task):
    module = _module(task)
    cls = getattr(module, task)
    v7 = module.native_blocks(cls, release="newtask-v7")
    assert v7 == module.native_blocks(cls, release="newtask-v6") == module.native_blocks(cls)
    with pytest.raises(ValueError):
        module.native_blocks(cls, release="newtask-v8")


def test_第四干扰色只给Pick与Swing用():
    assert [c["name"] for c in DISTRACTOR_COLORS] == ["yellow", "cyan", "magenta"]
    assert BLOCK_DISTRACTOR_COLORS[:3] == DISTRACTOR_COLORS
    assert len(BLOCK_DISTRACTOR_COLORS) == 4
    # Unmask／Swap 的干扰色池仍是三色（采样器要求逐字相等）
    for task in ("VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap"):
        for tier in TIERS:
            assert _decision(task)[tier]["distractor"]["color_pool"] == ["yellow", "cyan", "magenta"], (task, tier)


def test_干扰配置count为0合法_负数报错():
    cfg = dict(_decision("VideoUnmask")["xhard1"]["distractor"])
    assert cfg["count"] == 0 and cfg["cube_count_range"] == [0, 0]
    parsed = uds.parse_distractor_cfg(cfg)
    assert parsed.count == 0 and tuple(parsed.cube_count_range) == (0, 0)
    with pytest.raises(ValueError, match="≥ 0"):
        uds.parse_distractor_cfg({**cfg, "count": -1})
    # count 为 0 时 cube 数只能是 0
    with pytest.raises(ValueError, match="cube_count_range"):
        uds.parse_distractor_cfg({**cfg, "cube_count_range": [0, 1]})


def test_V5预设常量本身不动():
    """XHARD_DISTRACTOR（V5 预设 15／14）作为常量保留，但 xhard4 decision 已改用 12。"""
    for task, count in (("VideoUnmask", 15), ("ButtonUnmask", 14)):
        module = _module(task)
        assert module.XHARD_DISTRACTOR["count"] == count
        assert _decision(task)["xhard4"]["distractor"]["count"] == 12


def test_干扰数为0时采样器返回空布局():
    """VideoUnmask／ButtonUnmask 的 xhard1 贴身环带干扰为 0：采样器不放容器、不放 cube，只照常消费随机数。"""
    import torch  # noqa: PLC0415

    for task in ("VideoUnmask", "ButtonUnmask"):
        cfg = _decision(task)["xhard1"]["distractor"]
        generator = torch.Generator()
        generator.manual_seed(1)
        layout = uds.sample_distractor_layout(cfg, obstacles=[], generator=generator, cube_half_size=0.02)
        assert layout.count == 0 and layout.cube_count == 0 and layout.cube_bins == [] and layout.trials == []
        assert layout.to_spec()["bin_names"] == []
