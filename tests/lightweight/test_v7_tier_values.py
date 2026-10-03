#!/usr/bin/env python3
"""轻量测试：v8 档位取值表（1001 方案 §1 表 1；沿用 V7 定值表的文件与结构）——14 个梯度任务 × 各自支持档的
类常量与 decision 逐项等于取值表。

纯 CPU、不起 sapien：只读类属性 ``configs`` 与 ``native_blocks`` 导出的 decision 块。
SwingXtimes、StopCube 支持 xhard1～5，其余任务 xhard1～4；RouteStick、PatternLock 的 xhard1～3 为区间，
其余每个维度每档必须是一个定数（区间两端相等），数值见 ``tests/_shared/v7_tier_values.py``。

    uv run --no-sync python -m pytest tests/lightweight/test_v7_tier_values.py -q -s
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402
from tests._shared.v7_tier_values import (  # noqa: E402
    RANGE_TASKS,
    TIERS,
    V7_TIER_VALUES,
    NotFixedValue,
    summarize,
    tiers_for,
)

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
    tiers = tiers_for(task)
    for tier in tiers:
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
        elif task == "StopCube":
            stop = cfg["stop_time_range"]
            assert stop["high_exclusive"] == stop["low"] + 1, (task, tier, cfg)
            assert len(cfg["move_interval_choices"]) == 1, (task, tier, cfg)
            row = {"stop_time": stop["low"], "move_interval": cfg["move_interval_choices"][0]}
        elif task in RANGE_TASKS:
            # v8：xhard1～3 为区间 [lo, hi]，xhard4 仍定值
            lo, hi = cfg["length"]
            assert lo <= hi, (task, tier, cfg)
            row = {"length": lo if lo == hi else (lo, hi)}
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
    return {dim: tuple(out[tier][dim] for tier in tiers) for dim in out[tiers[0]]}


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
    """逐任务汇总：14 任务 × 各自支持档全部等于取值表才 PASS（打印 V7_TIER_VALUES 行供留证）。"""
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
        cells = sum(len(tiers_for(task)) for task in TASKS)
        print(f"\nV7_TIER_VALUES={'PASS' if not bad else 'FAIL'} tasks={len(TASKS)} cells={cells} bad={bad}")
    assert not bad
    assert len(TASKS) == 14


def test_读取函数拒绝区间():
    """非区间任务「每档一个定数」：把某档改回区间，读取函数必须报错。"""
    decision = _decision("PickXtimes")
    decision["number_range"]["xhard2"] = [8, 9]
    with pytest.raises(NotFixedValue):
        summarize("PickXtimes", decision)
    decision = _decision("StopCube")
    decision["xhard3"]["stop_time_range"] = {"low": 8, "high_exclusive": 10}
    with pytest.raises(NotFixedValue):
        summarize("StopCube", decision)


def test_读取函数对两区间任务放行区间():
    """v8：RouteStick、PatternLock 的 xhard1～3 读成 (lo, hi)，xhard4 仍读成定数。"""
    assert set(RANGE_TASKS) == {"RouteStick", "PatternLock"}
    assert summarize("RouteStick", _decision("RouteStick"))["length"] == ((8, 10), (11, 13), (14, 16), 19)
    assert summarize("PatternLock", _decision("PatternLock"))["length"] == ((9, 12), (13, 15), (16, 18), 21)


def test_逐任务支持档():
    """v8：只有 SwingXtimes、StopCube 支持 xhard5；其余任务四档、类常量里没有 xhard5。"""
    for task in TASKS:
        cls = getattr(_module(task), task)
        if task in ("SwingXtimes", "StopCube"):
            assert tiers_for(task) == (*TIERS, "xhard5")
            assert "xhard5" in cls.configs
        else:
            assert tiers_for(task) == TIERS
            assert "xhard5" not in cls.configs, task


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
    # v8：VideoUnmask xhard1 干扰 0 → 4（含 cube 0 → 2）；采样器对 count=0 的支持仍保留，用手工配置验
    decision_cfg = dict(_decision("VideoUnmask")["xhard1"]["distractor"])
    assert decision_cfg["count"] == 4 and decision_cfg["cube_count_range"] == [2, 2]
    cfg = {**decision_cfg, "count": 0, "cube_count_range": [0, 0]}
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
    """贴身环带干扰为 0（v7 的 xhard1；v8 起 xhard1 改为 4，这里用手工配置保留采样器回归）：
    采样器不放容器、不放 cube，只照常消费随机数。"""
    import torch  # noqa: PLC0415

    for task in ("VideoUnmask", "ButtonUnmask"):
        cfg = {**_decision(task)["xhard1"]["distractor"], "count": 0, "cube_count_range": [0, 0]}
        generator = torch.Generator()
        generator.manual_seed(1)
        layout = uds.sample_distractor_layout(cfg, obstacles=[], generator=generator, cube_half_size=0.02)
        assert layout.count == 0 and layout.cube_count == 0 and layout.cube_bins == [] and layout.trials == []
        assert layout.to_spec()["bin_names"] == []
