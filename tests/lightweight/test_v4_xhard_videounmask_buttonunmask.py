#!/usr/bin/env python3
"""轻量测试：V4 步 3b 的 VideoUnmask / ButtonUnmask xhard（NEWTASK_RELEASE_V4_PLAN 2.7 / 2.8 / 2.9）。

只导入环境模块、不起 sapien 场景：

* 原三档的 configs 与 decision（去掉 xhard 键后）逐字不变；xhard 新值与用户决策（G2 / B3 / B13）一致；
* 守卫放行源码默认与「去掉 xhard 的旧快照」，拒绝申报外的 xhard 键；
* ``_append_xhard_pick_tasks`` 按 pick_count 循环生成「放下 → 抓下一个」，lambda 绑定正确，
  ``task4recovery`` 能扫到 3 个抓取任务（2.7④ 的抽样空间 2 → 3）；
* 外环干扰容器工具的纯几何函数（方环判据、相机可见判据、容器尺寸）。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_videounmask_buttonunmask.py -q
"""

from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme.robomme_env.utils.episode_spec import SpecRecorder  # noqa: E402
from robomme.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    _strip_xhard,
    assert_native_decision,
)
from robomme.robomme_env.utils.task4recovery import task4recovery  # noqa: E402
from robomme.robomme_env.utils import unmask_distractors as ud  # noqa: E402

TASKS = ("VideoUnmask", "ButtonUnmask")

# 改动前（00e2ef4）两个环境 _native_decision 的原值，逐字抄录
ORIGINAL_DECISION = {
    "pick_count": {"hard": 2, "easy": 1, "medium": 1},
    "bin_layout_policy": {
        "count": {"hard": 15, "easy": 3, "medium": 5},
        "region_center": [0, 0],
        "region_half_size": 0.2,
    },
    "distractor": None,
}


def _module(task):
    return importlib.import_module(f"robomme.robomme_env.{task}")


def _cls(task):
    return getattr(_module(task), task)


@pytest.mark.parametrize("task", TASKS)
def test_original_three_configs_unchanged(task) -> None:
    cls = _cls(task)
    assert cls.configs["easy"] == {"bin": 3, "pick": 1}
    assert cls.configs["medium"] == {"bin": 5, "pick": 1}
    assert cls.configs["hard"] == {"bin": 15, "pick": 2}


@pytest.mark.parametrize("task", TASKS)
def test_xhard_values_match_user_decisions(task) -> None:
    mod, cls = _module(task), _cls(task)
    assert cls.configs["xhard"] == {"bin": 8, "pick": 3}          # G2 N=8、pick 3
    decision = mod._native_decision(cls)
    assert decision["bin_layout_policy"]["xhard"] == {"min_gap_factor": 0.75}   # G2
    dist = decision["xhard"]["distractor"]
    assert dist["count"] == 3                                        # B3
    assert dist["ring_max_abs_xy"] == [0.2675, 0.45]                 # B13
    assert dist["cube_count_range"] == [1, 2]                        # B13：3 个里 1~2 个含 cube
    assert dist["color_pool"] == [c["name"] for c in ud.DISTRACTOR_COLORS]   # B2
    # 揭示动画的扫描上限必须覆盖 xhard 容器数
    assert mod.NATIVE_SAMPLING["parameters"]["step_bin_scan"] >= cls.configs["xhard"]["bin"]
    # native 原值不动
    assert mod.NATIVE_SAMPLING["positions"]["bins"]["min_gap_factor"] == 2


@pytest.mark.parametrize("task", TASKS)
def test_decision_visible_to_original_three_unchanged(task) -> None:
    mod, cls = _module(task), _cls(task)
    assert _strip_xhard(mod._native_decision(cls)) == ORIGINAL_DECISION


@pytest.mark.parametrize("task", TASKS)
def test_guard(task) -> None:
    mod, cls = _module(task), _cls(task)
    default = mod._native_decision(cls)
    assert_native_decision(copy.deepcopy(default), default, task)
    # 去掉全部 xhard 条目的旧快照照旧放行
    assert_native_decision(copy.deepcopy(ORIGINAL_DECISION), default, task)
    # 已申报的 xhard 条目可改值（组合覆盖扫描收窄用）
    narrowed = copy.deepcopy(default)
    narrowed["xhard"]["distractor"]["cube_count_range"] = [2, 2]
    assert_native_decision(narrowed, default, task)
    # 申报外的 xhard 键拒绝
    extra = copy.deepcopy(default)
    extra["xhard"]["distractor"]["bogus"] = 1
    with pytest.raises(SamplingConfigError):
        assert_native_decision(extra, default, task)
    # 原三档可见部分改动拒绝
    bad = copy.deepcopy(default)
    bad["bin_layout_policy"]["count"]["hard"] = 8
    with pytest.raises(SamplingConfigError):
        assert_native_decision(bad, default, task)


def _fake_env(task, n_bins=8):
    bins = [SimpleNamespace(name=f"bin_{i}") for i in range(n_bins)]
    env = SimpleNamespace(
        spawned_bins=bins,
        color_names=["green", "red", "blue"],
        _spec=SpecRecorder(None, task, {"seed": 0}, difficulty="xhard"),
    )
    for i, b in enumerate(bins):
        setattr(env, f"bin_{i}", b)
    return env


@pytest.mark.parametrize("task", TASKS)
def test_xhard_pick_loop_structure(task, monkeypatch) -> None:
    mod, cls = _module(task), _cls(task)
    env = _fake_env(task)
    calls = []
    monkeypatch.setattr(mod, "is_bin_pickup", lambda self, obj: calls.append(("pickup", obj.name)) or True)
    monkeypatch.setattr(mod, "is_bin_putdown", lambda self, obj: calls.append(("putdown", obj.name)) or True)
    monkeypatch.setattr(mod, "is_any_bin_pickup", lambda self, objs: calls.append(("any", tuple(o.name for o in objs))) or False)

    tasks = []
    cls._append_xhard_pick_tasks(env, tasks, 3)
    assert [t["name"] for t in tasks] == [
        "put down the container",
        "pick up the container that hides the red cube",
        "put down the container",
        "pick up the container that hides the blue cube",
    ]
    assert tasks[1]["segment"] is env.bin_1 and tasks[3]["segment"] is env.bin_2
    assert all(t["demonstration"] is False for t in tasks)
    # lambda 绑定：第 k 个 pickup 看 bin_k，第 k 个 putdown 看 bin_{k-1}（不被循环变量晚绑定）
    for t in tasks:
        t["func"]()
        t["failure_func"]()
    assert calls[0] == ("putdown", "bin_0")
    assert calls[2] == ("pickup", "bin_1")
    assert calls[4] == ("putdown", "bin_1")
    assert calls[6] == ("pickup", "bin_2")
    assert "bin_2" not in calls[7][1] and len(calls[7][1]) == 7
    # 2.7④：连同第一个抓取，task4recovery 扫到 3 个候选（hard 为 2 个）
    first = {"name": "first", "demonstration": False,
             "solve": lambda e, p: [mod.solve_pickup_bin(e, p, obj=env.bin_0)], "segment": env.bin_0}
    indices, _ = task4recovery([first] + tasks)
    assert indices == [0, 2, 4]
    # 规格里记下抓取次数与顺序；任务目标文本读 xhard_pick_count
    doc = env._spec.to_dict()
    assert doc["objects"]["n_picks"] == 3 and doc["objects"]["pick_order"] == [0, 1, 2]
    assert env.xhard_pick_count == 3


@pytest.mark.parametrize("task", TASKS)
def test_xhard_pick_loop_rejects_too_many(task) -> None:
    from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError

    with pytest.raises(SceneGenerationError):
        _cls(task)._append_xhard_pick_tasks(_fake_env(task), [], 4)   # 只有 3 个藏物容器


def test_distractor_geometry_helpers() -> None:
    half, reach, height = ud.bin_geometry(0.02)
    assert half == pytest.approx(0.0275)                 # 与 spawn_random_bin 的 bin_half_size 相同
    assert reach == pytest.approx(0.03 * 2 ** 0.5)       # 外廓半边 0.03 的任意 yaw 外接
    assert height == pytest.approx(0.054)
    assert ud.in_ring(0.3, 0.0, [0.2675, 0.45]) and ud.in_ring(-0.1, 0.45, [0.2675, 0.45])
    assert not ud.in_ring(0.2, 0.2, [0.2675, 0.45]) and not ud.in_ring(0.46, 0.0, [0.2675, 0.45])
    # 相机可见：原点可见；外环 +x 远角 (0.45, 0.45) 出画（计划 B13：x=+0.4 处可见 y 仅 ±0.31）
    assert ud.visible_in_camera(ud.bin_corners(0.0, 0.0, reach, height))
    assert ud.visible_in_camera(ud.bin_corners(-0.45, 0.45, reach, height))
    assert not ud.visible_in_camera(ud.bin_corners(0.45, 0.45, reach, height))
    assert not ud.visible_in_camera([(0.3, 0.0, 0.5)])   # 相机背后
    # 干扰容器命名刻意避开 bin_<i>（不进揭示动画）
    assert not ud.DISTRACTOR_BIN_PREFIX.startswith("bin_")
