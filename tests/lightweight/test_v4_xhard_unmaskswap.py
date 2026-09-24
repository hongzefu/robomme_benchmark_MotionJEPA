#!/usr/bin/env python3
"""轻量测试：V4 步 3b 的 VideoUnmaskSwap / ButtonUnmaskSwap xhard（NEWTASK_RELEASE_V4_PLAN 2.7、2.10、2.11）。

纯结构与纯几何，不起 SAPIEN 场景：

* 原三档的 ``config_*``、decision 去掉 ``xhard`` 后的部分、native 关键块逐字不变（V0 口径）；
* xhard 新值：swap [8,12] / [6,8]、pick 3、bin 4、速度 ×1.5 ⇒ 每段 33 步、3 个干扰容器；
* 守卫放行已申报的 xhard 收窄、拒绝原三档改动与申报外键；VideoUnmaskSwap 的 xhard 抓取序号
  受 JSON 全等铁闸保护，外部改不了，旧快照缺它时按源码补齐；
* 干扰容器采样：外环 + 相机可见 + 避障 + 避开预演扫掠；请求数＝实际数，放不下即抛错；
* 交换预演的搭档选择与位姿互换语义；3 抓任务目标文本；N5 源码顺序；审计豁免已撤销。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_unmaskswap.py -q
"""

from __future__ import annotations

import ast
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import importlib  # noqa: E402

# 包的 __init__ 用 `from .X import *` 把同名类盖在了包属性上，模块本体要从 sys.modules 取
vus_module = importlib.import_module("robomme.robomme_env.VideoUnmaskSwap")
bus_module = importlib.import_module("robomme.robomme_env.ButtonUnmaskSwap")
from robomme.robomme_env.utils import unmask_swap_xhard as ux  # noqa: E402
from robomme.robomme_env.utils.bin_collision import (  # noqa: E402
    ObjectState,
    bin_actor_pose,
    bin_shape_specs,
    check_swap_sweep,
)
from robomme.robomme_env.utils.episode_spec import SpecRecorder  # noqa: E402
from robomme.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    _strip_xhard,
    assert_native_decision,
)
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402
from robomme.robomme_env.utils.task_goal import get_language_goal  # noqa: E402

VUS = vus_module.VideoUnmaskSwap
BUS = bus_module.ButtonUnmaskSwap
MODULES = {"VideoUnmaskSwap": (vus_module, VUS), "ButtonUnmaskSwap": (bus_module, BUS)}
CUBE_HALF = 0.02

# 改动前（00e2ef4）的原三档，逐字抄录
ORIGINAL_CONFIGS = {
    "easy": {"bin": 3, "swap_min": 1, "swap_max": 2, "pick_min": 1, "pick_max": 2},
    "medium": {"bin": 4, "swap_min": 1, "swap_max": 2, "pick_min": 1, "pick_max": 1},
    "hard": {"bin": 4, "swap_min": 2, "swap_max": 3, "pick_min": 2, "pick_max": 2},
}
ORIGINAL_DECISION = {
    "swap_count_range": {"easy": [1, 2], "medium": [1, 2], "hard": [2, 3]},
    "pick_count_range": {"easy": [1, 2], "medium": [1, 1], "hard": [2, 2]},
    "swap_speed_multiplier": 1,
    "distractor": None,
}
XHARD = {
    "VideoUnmaskSwap": {"bin": 4, "swap_min": 8, "swap_max": 12, "pick_min": 3, "pick_max": 3},
    "ButtonUnmaskSwap": {"bin": 4, "swap_min": 6, "swap_max": 8, "pick_min": 3, "pick_max": 3},
}


# ── 配置与 decision ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("task", sorted(MODULES))
def test_原三档配置逐字不变_xhard为新值(task):
    _module, cls = MODULES[task]
    for difficulty, expected in ORIGINAL_CONFIGS.items():
        assert cls.configs[difficulty] == expected
    assert cls.configs["xhard"] == XHARD[task]
    assert (cls.SWAP_WINDOW_START, cls.SWAP_WINDOW_STEPS) == (64, 50)


@pytest.mark.parametrize("task", sorted(MODULES))
def test_decision去掉xhard后与原值相同(task):
    module, cls = MODULES[task]
    decision, _native = module.native_blocks(cls)
    assert _strip_xhard(decision) == ORIGINAL_DECISION
    lo, hi = XHARD[task]["swap_min"], XHARD[task]["swap_max"]
    assert decision["swap_count_range"]["xhard"] == [lo, hi]
    assert decision["pick_count_range"]["xhard"] == [3, 3]
    assert decision["xhard"]["swap_speed_multiplier"] == 1.5
    # V5（2.6/2.7，L16 b）：干扰容器改为统一采样器的键与值（V4 环带、10 个、含 cube [5,5]），新增外环交换配置块
    assert decision["xhard"]["distractor"] == {
        "count": 10, "ring_max_abs_xy": [0.2675, 0.45], "cube_count_range": [5, 5],
        "color_pool": ["yellow", "cyan", "magenta"], "color_rule": "balanced_cycle",
        "min_gap_factor": 0.75, "max_trials": 1024,
    }
    assert decision["xhard"]["distractor_swap"] == ux.v5_distractor_swap_cfg(task)


@pytest.mark.parametrize("task", sorted(MODULES))
def test_守卫放行xhard收窄_拒绝原三档改动与申报外键(task):
    module, cls = MODULES[task]
    default, _native = module.native_blocks(cls)
    narrowed = copy.deepcopy(default)
    narrowed["swap_count_range"]["xhard"] = [narrowed["swap_count_range"]["xhard"][1]] * 2
    narrowed["xhard"]["distractor"]["cube_count_range"] = [4, 4]  # V5 统一键名（V4 为 with_cube_range）
    assert_native_decision(narrowed, default, task)
    for mutate in (
        lambda d: d["swap_count_range"].__setitem__("hard", [2, 4]),
        lambda d: d.__setitem__("swap_speed_multiplier", 1.5),
        lambda d: d["xhard"].__setitem__("新键", 1),
    ):
        bad = copy.deepcopy(default)
        mutate(bad)
        with pytest.raises(SamplingConfigError):
            assert_native_decision(bad, default, task)


def test_bus_native_swap_window与原值相同且被声明为具名常量():
    _decision, native = bus_module.native_blocks(BUS)
    assert native["parameters"]["swap_window"] == {"start_step": 64, "duration_steps": 50}
    assert native["parameters"]["bin_count"] == {"easy": 3, "medium": 4, "hard": 4, "xhard": 4}


def test_vus_object_selection原值不变_xhard抓取序号单列():
    _decision, native = vus_module.native_blocks(VUS)
    assert native["parameters"]["object_selection"] == {
        "hidden_bin_permutation_size": 3, "hidden_bin_count_max": 3,
        "pickup_selected_indices": [0, 1], "swap_seed_target_count": 2,
    }
    assert native["parameters"]["xhard"] == {"object_selection": {"pickup_selected_indices": [0, 1, 2]}}


def test_vus_外部改不了xhard抓取序号_旧快照缺项按源码补齐():
    _decision, native = vus_module.native_blocks(VUS)
    bad = copy.deepcopy(native)
    bad["parameters"]["xhard"]["object_selection"]["pickup_selected_indices"] = [0, 1]
    with pytest.raises(ValueError):
        vus_module._resolve_sampling_config(VUS, bad)
    old = copy.deepcopy(native)
    del old["parameters"]["xhard"]  # v2/v3 旧格式快照
    state = torch.get_rng_state().clone()
    resolved = vus_module._resolve_sampling_config(VUS, old)
    assert resolved["parameters"]["xhard"]["object_selection"]["pickup_selected_indices"] == [0, 1, 2]
    assert json.dumps(resolved, sort_keys=True) == json.dumps(vus_module._resolve_sampling_config(VUS, None), sort_keys=True)
    assert torch.equal(state, torch.get_rng_state())


# ── 交换窗口 ────────────────────────────────────────────────────────────────
def test_窗口倍率取整():
    assert ux.scaled_window_steps(50, 1) == 50 and type(ux.scaled_window_steps(50, 1)) is int
    assert ux.scaled_window_steps(50, 1.0) == 50
    assert ux.scaled_window_steps(50, 1.5) == 33
    for bad in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            ux.scaled_window_steps(50, bad)


# ── 干扰容器采样 ────────────────────────────────────────────────────────────
def _recorder():
    return SpecRecorder(None, "VideoUnmaskSwap", {"seed": 1}, difficulty="xhard")


def _bin_state(name, xy, yaw=0.0):
    p, q = bin_actor_pose(xy, yaw, CUBE_HALF)
    return ObjectState(name=name, p=p, q=q, shapes=bin_shape_specs(CUBE_HALF))


@pytest.mark.parametrize("seed", range(12))
def test_干扰容器落在外环且可见且避障(seed):
    cfg = copy.deepcopy(ux.XHARD_DISTRACTOR)
    radius = ux.bin_footprint_radius(CUBE_HALF)
    obstacles = [((x, y), radius) for x, y in [(-0.05, -0.1), (-0.05, 0.1), (0.1, 0.1), (0.1, -0.1)]]
    obstacles += [((-0.2, -0.1), 0.0795), ((-0.2, 0.1), 0.0795)]  # 两个按钮的避让圆
    # 一段会扫出 region 的交换：a、b 横向相距 0.36，弯道侧移 0.07
    sweeps = [(_bin_state("bin_0", [0.0, -0.18]), _bin_state("bin_1", [0.0, 0.18]))]
    recorder = _recorder()
    out = ux.sample_distractors(generator=ux.distractor_generator(seed), cfg=cfg, obstacles=obstacles,
                                sweeps=sweeps, recorder=recorder, cube_half_size=CUBE_HALF)
    assert len(out["placements"]) == 3
    assert 1 <= len(out["cube_colors"]) <= 2 and set(out["cube_colors"]) <= {"yellow", "cyan", "magenta"}
    assert len(set(out["cube_colors"])) == len(out["cube_colors"])
    placed = [np.array(p["xy"]) for p in out["placements"]]
    for i, entry in enumerate(out["placements"]):
        x, y = entry["xy"]
        assert 0.2675 <= max(abs(x), abs(y)) <= 0.45
        assert ux.visible_on_camera(x, y, radius)
        assert 0.0 <= entry["yaw_deg"] <= 90.0
        for xy, r in obstacles:
            assert np.linalg.norm(np.array([x, y]) - np.array(xy)) >= r + radius + cfg["min_gap"]
        for j in range(i):
            assert np.linalg.norm(placed[i] - placed[j]) >= 2 * radius + cfg["min_gap"]
        state = _bin_state(f"distractor_bin_{i}", [x, y], entry["yaw_deg"])
        assert check_swap_sweep(*sweeps[0], [state])[1] is None
    doc = recorder.to_dict()
    assert doc["layout"]["distractors_requested"] == doc["layout"]["distractors_placed"] == 3
    assert doc["objects"]["distractors"]["n_with_cube"] == len(out["cube_colors"])


def test_干扰容器放不下时抛错而不是截断():
    cfg = copy.deepcopy(ux.XHARD_DISTRACTOR)
    # 一个覆盖整张桌面的障碍圆
    with pytest.raises(SceneGenerationError):
        ux.sample_distractors(generator=ux.distractor_generator(0), cfg=cfg, obstacles=[((0.0, 0.0), 2.0)],
                              sweeps=[], recorder=_recorder(), cube_half_size=CUBE_HALF)


def test_干扰容器走专用流_不动主流():
    main = torch.Generator().manual_seed(7)
    before = main.get_state().clone()
    ux.sample_distractors(generator=ux.distractor_generator(7), cfg=copy.deepcopy(ux.XHARD_DISTRACTOR),
                          obstacles=[], sweeps=[], recorder=_recorder(), cube_half_size=CUBE_HALF)
    assert torch.equal(before, main.get_state())
    # 专用流与同 seed 的主流不是同一条
    a = ux.distractor_generator(7)
    b = torch.Generator().manual_seed(7)
    assert not torch.equal(torch.rand(4, generator=a), torch.rand(4, generator=b))


def test_色池越界与with_cube越界都拒绝():
    for mutate in (lambda c: c.__setitem__("colors", ["red"]), lambda c: c.__setitem__("with_cube_range", [2, 4])):
        cfg = copy.deepcopy(ux.XHARD_DISTRACTOR)
        mutate(cfg)
        with pytest.raises(ValueError):
            ux.sample_distractors(generator=ux.distractor_generator(0), cfg=cfg, obstacles=[], sweeps=[],
                                  recorder=_recorder(), cube_half_size=CUBE_HALF)


# ── 交换预演 ────────────────────────────────────────────────────────────────
def test_预演搭档取最近邻并互换位姿(monkeypatch):
    actors = [SimpleNamespace(xy=np.array(xy, dtype=np.float32)) for xy in [(0.0, 0.0), (0.1, 0.0), (0.0, 0.25), (0.3, 0.0)]]
    monkeypatch.setattr(ux, "object_state_from_actor",
                        lambda actor, name: _bin_state(name, [float(actor.xy[0]), float(actor.xy[1])]))
    env = SimpleNamespace(spawned_bins=actors, swap_times=3,
                          swap_pair1_idx1=actors[0], swap_pair2_idx1=actors[0], swap_pair3_idx1=actors[2],
                          _get_actor_position=lambda a: np.array([a.xy[0], a.xy[1], 0.0], dtype=np.float32))
    sweeps = ux.predict_swap_sweeps(env, [0, 1])
    names = [(a.name, b.name) for a, b in sweeps]
    # 第 1 段：bin_0(0,0) 最近 bin_1(0.1,0)；交换后 bin_0 在 (0.1,0)、bin_1 在 (0,0)
    # 第 2 段：bin_0(0.1,0) 最近 bin_1(0,0)（0.1）而非 bin_3（0.2）；交换后 bin_0 回 (0,0)、bin_1 回 (0.1,0)
    # 第 3 段：bin_2(0,0.25) 到 bin_0(0,0) 0.25 < 到 bin_1(0.1,0) 0.269 ⇒ 搭档是 bin_0（用的是交换后的位置）
    assert names == [("bin_0", "bin_1"), ("bin_0", "bin_1"), ("bin_2", "bin_0")]
    assert np.allclose(sweeps[1][0].p[:2], [0.1, 0.0]) and np.allclose(sweeps[1][1].p[:2], [0.0, 0.0])
    assert np.allclose(sweeps[2][1].p[:2], [0.0, 0.0])


# ── 任务目标文本 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("task,prefix", [("VideoUnmaskSwap", "watch the video carefully"),
                                         ("ButtonUnmaskSwap", "first press both buttons on the table")])
def test_三抓任务目标文本(task, prefix):
    colors = ["green", "blue", "red"]
    wrapper = SimpleNamespace(pick_times=3, env=SimpleNamespace(unwrapped=SimpleNamespace(color_names=colors)))
    goals = get_language_goal(wrapper, task)
    assert goals == [f"{prefix}, then pick up the container hiding the green cube, next pick up another container "
                     f"hiding the blue cube, finally pick up another container hiding the red cube"]
    wrapper.pick_times = 2
    assert "next pick up" not in get_language_goal(wrapper, task)[0]


# ── 源码结构：N5 顺序与审计豁免 ──────────────────────────────────────────────
def _func(path, cls_name, name):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)


@pytest.mark.parametrize("task", sorted(MODULES))
def test_干扰容器在load_scene末尾且不用主流(task):
    path = REPO_ROOT / "src" / "robomme" / "robomme_env" / f"{task}.py"
    scene = _func(path, task, "_load_scene")
    last = scene.body[-1]
    assert isinstance(last, ast.If) and "_spawn_xhard_distractors" in ast.unparse(last)
    spawn = ast.unparse(_func(path, task, "_spawn_xhard_distractors"))
    assert "distractor_generator(self.seed)" in spawn and "generator=generator" not in spawn


def test_审计已撤销两条swap_speed_multiplier豁免():
    from scripts.parity.train_split_audit import NEUTRAL_KEYS

    assert "VideoUnmaskSwap.decision.swap_speed_multiplier" not in NEUTRAL_KEYS
    assert "ButtonUnmaskSwap.decision.swap_speed_multiplier" not in NEUTRAL_KEYS


# ── ButtonUnmaskSwap xhard：按完按钮等交换结束 ──────────────────────────────
@pytest.mark.parametrize("button_result,expect_hold", [(None, True), (-1, False)])
def test_bus_按钮后等待交换结束_失败信号不被吞(monkeypatch, button_result, expect_hold):
    calls = []
    monkeypatch.setattr(bus_module, "solve_button", lambda env, planner, obj: calls.append(("button", obj)) or button_result)
    monkeypatch.setattr(bus_module, "solve_hold_obj_absTimestep",
                        lambda env, planner, absTimestep: calls.append(("hold", absTimestep)))
    fake = SimpleNamespace(swap_schedule=[(None, None, 64, 97), (None, None, 97, 130)])
    result = BUS._solve_press_then_wait_swaps(fake, "env", "planner", "button_left")
    assert result == button_result
    assert calls == ([("button", "button_left"), ("hold", 130)] if expect_hold else [("button", "button_left")])
