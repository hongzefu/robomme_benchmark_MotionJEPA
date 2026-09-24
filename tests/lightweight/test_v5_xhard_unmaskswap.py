#!/usr/bin/env python3
"""轻量测试：V5 S3h，VideoUnmaskSwap / ButtonUnmaskSwap xhard 的外环随内环同步交换（NEWTASK_RELEASE_V5_PLAN 2.5～2.7）。

纯几何与假环境，不起 SAPIEN 场景：

* 配置：``decision.xhard.distractor`` 为统一采样器预设（10 个、V4 环带、cube [5,5]），``distractor_swap`` 配置块与校验；
* 几何件：向量化可见判据与精确判据逐点一致；H1 守卫与 ``check_multi_swap_sweep`` 的「静止物 × 交换者」判定一致；
  内环预演与 V4 ``predict_swap_sweeps`` 同语义；
* L20 反例：V4 实跑碰撞局 VUS seed 4500300 的内环布局在 reset 预判第 1 段被拒（bin_2 撞 bin_1）；
* 规划：每窗恰好一次外环交换、外环对只在干扰容器之间、独立复核四条可行条件全部成立、名字无重复；
* 记录纪律（N18）与回放复核（N17）：只在被接受的那次 value；回放逐值复现；篡改冻结值被拒或按冻结值重规划复核；
* 运行时：外环交换与内环同窗口、每窗恰好一次；联合复核带上外环对并记录内环搭档是否与预演一致；
* 源码结构：外环循环不在 AST 锁定的内环搭档循环里、只在 xhard 分支；BUS 内环截断在 xhard 抛真异常（L15）。

    uv run --no-sync python -m pytest tests/lightweight/test_v5_xhard_unmaskswap.py -q
"""

from __future__ import annotations

import ast
import copy
import importlib
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

pytestmark = pytest.mark.lightweight

vus_module = importlib.import_module("robomme.robomme_env.VideoUnmaskSwap")
bus_module = importlib.import_module("robomme.robomme_env.ButtonUnmaskSwap")
from robomme.robomme_env.utils import unmask_swap_xhard as ux  # noqa: E402
from robomme.robomme_env.utils.bin_collision import (  # noqa: E402
    ObjectState,
    bin_actor_pose,
    bin_shape_specs,
    check_multi_swap_sweep,
)
from robomme.robomme_env.utils.episode_spec import SpecRecorder  # noqa: E402
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402
from robomme.robomme_env.utils.unmask_distractor_sampler import (  # noqa: E402
    V5_DISTRACTOR_PRESETS,
    DistractorLayout,
    bin_obb2d,
    bin_visible,
    verify_distractor_layout,
)

CH = 0.02
ENV_DIR = REPO_ROOT / "src" / "robomme" / "robomme_env"
MODULES = {"VideoUnmaskSwap": (vus_module, vus_module.VideoUnmaskSwap),
           "ButtonUnmaskSwap": (bus_module, bus_module.ButtonUnmaskSwap)}
BTN_HALF = 0.025 * 1.5 * 1.5  # build_button 返回的 create_button_obb 半边（scale 1.5 × 安全区 1.5）

# 内环布局常量：抄自 V4 冻结规格 v4-01 的内环容器 [x, y, yaw_deg]、发起者循环基与交换次数（BUS 的按钮中心按同 seed
# 的 build_button 抽样复算）。V4 已作废，这里只把数值当作「真实环境会出现的内环布局」样本，不引用 V4 产物。
LAYOUTS = [
    dict(task="VideoUnmaskSwap", seed=4500000, n_swaps=10, initiators=[0, 2, 1], buttons=[],
         bins=[[0.010426, -0.112116, 66.454394], [-0.075487, 0.074412, 78.302447],
               [0.040068, 0.159031, 29.868012], [0.119454, 0.004828, 47.350945]]),
    dict(task="VideoUnmaskSwap", seed=4500100, n_swaps=10, initiators=[0, 2, 1], buttons=[],
         bins=[[0.094577, -0.037561, 1.475306], [-0.10325, -0.006758, 16.186638],
               [-0.061278, 0.134406, 57.246451], [0.128882, 0.079593, 81.495069]]),
    dict(task="ButtonUnmaskSwap", seed=4700000, n_swaps=8, initiators=[0, 2, 1],
         buttons=[[-0.183457, -0.11385], [-0.220621, 0.099195]],
         bins=[[0.023393, -0.051385, 54.389716], [0.027751, 0.117596, 39.295456],
               [0.114673, 0.174468, 14.554321], [0.125409, -0.013743, 37.637417]]),
    dict(task="ButtonUnmaskSwap", seed=4700200, n_swaps=7, initiators=[2, 1, 0],
         buttons=[[-0.207638, -0.075355], [-0.206003, 0.082404]],
         bins=[[0.02061, -0.070452, 29.563115], [-0.007559, 0.085633, 8.93586],
               [0.077806, 0.168378, 34.973211], [0.136325, -0.04651, 47.881781]]),
]
# V4 实跑 VUS ep3（seed 4500300）sweep#1 bin_2 撞 bin_1（g = −0.00207）；V5 L20 要求 reset 时就拒掉
COLLIDING_4500300 = dict(task="VideoUnmaskSwap", seed=4500300, n_swaps=10, initiators=[0, 2, 1], buttons=[],
                         bins=[[0.029888, -0.062441, 6.630839], [-0.102923, -0.020455, 20.776305],
                               [-0.015707, 0.112358, 8.764456], [0.139727, 0.059803, 5.141907]])


def _bin_state(name, x, y, yaw):
    p, q = bin_actor_pose([x, y], yaw, CH)
    return ObjectState(name=name, p=p, q=q, shapes=bin_shape_specs(CH))


def _windows(lay):
    states = [_bin_state(f"bin_{i}", x, y, yaw) for i, (x, y, yaw) in enumerate(lay["bins"])]
    positions = [np.array([x, y, 0.0], dtype=np.float32) for x, y, _ in lay["bins"]]
    initiators = [lay["initiators"][k % 3] for k in range(lay["n_swaps"])]
    return ux.predict_inner_windows_from_states(states, positions, initiators, [0, 1])


def _obstacles(lay):
    obst = [(np.asarray(b, float), np.eye(2), np.array([BTN_HALF, BTN_HALF])) for b in lay["buttons"]]
    return obst + [bin_obb2d(x, y, yaw, CH, pad=CH * 0.75) for x, y, yaw in lay["bins"]]


def _plan(lay, recorder=None, swap_cfg=None):
    recorder = recorder or SpecRecorder(None, lay["task"], {"seed": lay["seed"]}, difficulty="xhard")
    out = ux.plan_swap_distractors(
        windows=_windows(lay), obstacles=_obstacles(lay), buttons_xy=lay["buttons"],
        generator=ux.distractor_generator(lay["seed"]), recorder=recorder,
        distractor_cfg=ux.v5_distractor_cfg(lay["task"]),
        swap_cfg=swap_cfg or ux.v5_distractor_swap_cfg(lay["task"]), cube_half_size=CH,
    )
    return out, recorder


# ── 配置 ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("task", sorted(MODULES))
def test_decision_xhard为统一预设与外环交换配置块(task):
    module, cls = MODULES[task]
    decision, _native = module.native_blocks(cls)
    assert decision["xhard"]["distractor"] == V5_DISTRACTOR_PRESETS[task]
    assert decision["xhard"]["distractor"]["count"] == 10
    assert decision["xhard"]["distractor"]["ring_max_abs_xy"] == [0.2675, 0.45]
    assert decision["xhard"]["distractor"]["cube_count_range"] == [5, 5]
    swap = decision["xhard"]["distractor_swap"]
    assert swap["enabled"] is True and swap["lane_offset"] == 0.07 and swap["layout_max_attempts"] == 16
    assert swap["initiator_rule"] == "permutation_cycle" and swap["fallback"] == "next_in_permutation"
    assert swap["partner"]["population"] == "distractor_bins" and swap["partner"]["resolve_at"] == "reset_plan"
    assert swap["path_constraints"]["min_inner_circle_clearance_m"] == 0.04
    button = swap["path_constraints"]["min_button_center_dist_m"]
    assert button == (0.122 if task == "ButtonUnmaskSwap" else None)
    ux.parse_distractor_swap_cfg(swap)


@pytest.mark.parametrize("mutate", [
    lambda c: c.__setitem__("lane_offset", 0.05),
    lambda c: c.__setitem__("initiator_rule", "random"),
    lambda c: c.__setitem__("fallback", "skip"),
    lambda c: c["partner"].__setitem__("resolve_at", "swap_start"),
    lambda c: c.__setitem__("smooth", False),
    lambda c: c.__setitem__("layout_max_attempts", 0),
    lambda c: c.__setitem__("新键", 1),
    lambda c: c["path_constraints"].__setitem__("min_inner_circle_clearance_m", -1),
])
def test_外环交换配置非法即报错(mutate):
    cfg = ux.v5_distractor_swap_cfg("ButtonUnmaskSwap")
    mutate(cfg)
    with pytest.raises(ValueError):
        ux.parse_distractor_swap_cfg(cfg)


# ── 几何件 ──────────────────────────────────────────────────────────────────
def test_向量化可见判据与精确判据逐点一致():
    rng = np.random.default_rng(20260924)
    xy = rng.uniform(-0.6, 0.6, size=(3000, 2))
    fast = ux.bins_visible_many(xy, CH)
    slow = np.array([bin_visible(x, y, CH) for x, y in xy])
    assert np.array_equal(fast, slow)
    assert 0.2 < fast.mean() < 0.9  # 样本里可见与不可见都有


def test_H1守卫与联合判据的静止物对判定一致():
    rng = np.random.default_rng(7)
    windows = _windows(LAYOUTS[0])
    guard = ux.InnerSweepGuard(windows)
    rejected = passed = 0
    for i in range(70):
        x, y = rng.uniform(-0.3, 0.3, size=2)
        cand = _bin_state(f"distractor_bin_{i}", x, y, float(rng.uniform(0, 90)))
        expected = None
        for k, w in enumerate(windows):
            # 内环对自身在 L20 已证，这里只比「候选 × 交换者」：候选放在外面时内环对自身必通过
            _g, rej = check_multi_swap_sweep([(w.states[w.a], w.states[w.b])], [cand], sweep_index=k)
            if rej is not None:
                expected = rej
                break
        got = guard.first_rejection(cand)
        assert (got is None) == (expected is None), (x, y)
        if got is not None:
            assert (got.object_a, got.object_b, got.sweep_index) == (expected.object_a, expected.object_b, expected.sweep_index)
            rejected += 1
        else:
            passed += 1
    assert rejected >= 5 and passed >= 5


def test_内环预演与V4预演同语义(monkeypatch):
    lay = LAYOUTS[1]
    actors = [SimpleNamespace(xy=np.array(b[:2], dtype=np.float32), yaw=b[2]) for b in lay["bins"]]
    monkeypatch.setattr(ux, "object_state_from_actor",
                        lambda actor, name: _bin_state(name, float(actor.xy[0]), float(actor.xy[1]), actor.yaw))
    env = SimpleNamespace(spawned_bins=actors, swap_times=lay["n_swaps"],
                          _get_actor_position=lambda a: np.array([a.xy[0], a.xy[1], 0.0], dtype=np.float32))
    for k in range(lay["n_swaps"]):
        setattr(env, f"swap_pair{k + 1}_idx1", actors[lay["initiators"][k % 3]])
    old = ux.predict_swap_sweeps(env, [0, 1])
    new = ux.predict_inner_windows(env, [0, 1])
    assert [(a.name, b.name) for a, b in old] == [(f"bin_{w.a}", f"bin_{w.b}") for w in new]
    for (sa, sb), w in zip(old, new):
        assert np.allclose(sa.p, w.states[w.a].p) and np.allclose(sb.p, w.states[w.b].p)


# ── L20：内环对内环 reset 预判 ──────────────────────────────────────────────────
def test_V4碰撞局4500300在reset预判被拒():
    hit = ux.prejudge_inner_windows(_windows(COLLIDING_4500300))
    assert hit is not None
    k, rejection = hit
    assert k == 1 and {rejection.object_a, rejection.object_b} == {"bin_1", "bin_2"}
    assert rejection.reason == "contact"
    with pytest.raises(SceneGenerationError) as info:
        _plan(COLLIDING_4500300)
    assert "L20" in str(info.value)


@pytest.mark.parametrize("lay", LAYOUTS, ids=lambda l: f"{l['task']}-{l['seed']}")
def test_正常布局通过内环预判(lay):
    assert ux.prejudge_inner_windows(_windows(lay)) is None


# ── 规划 ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lay", LAYOUTS, ids=lambda l: f"{l['task']}-{l['seed']}")
def test_每窗恰好一次外环交换且规划可行(lay):
    (layout, pairs, _timing, _stats), recorder = _plan(lay)
    doc = recorder.to_dict()
    windows = _windows(lay)
    # 口径 4：每个内环窗口恰好一次外环交换
    assert len(pairs) == lay["n_swaps"] == len(windows)
    assert doc["actions"]["distractor_swap_pairs"] == [[o, p] for o, p in pairs]
    assert len(doc["actions"]["distractor_swap_fallback"]) == lay["n_swaps"]
    assert all(0 <= f < 10 for f in doc["actions"]["distractor_swap_fallback"])
    # 口径 5：外环对只在干扰容器之间（序号指 distractor_bins），永不与内环配对
    assert all(0 <= o < 10 and 0 <= p < 10 and o != p for o, p in pairs)
    # 独立复核：p 确为最近邻、画面内、离内环 ≥ 0.04、（BUS）离按钮 ≥ 0.122、两对联合证明通过
    cfg = ux.parse_distractor_swap_cfg(ux.v5_distractor_swap_cfg(lay["task"]))
    assert ux.verify_distractor_swap_plan(layout, pairs, windows, cfg=cfg, cube_half_size=CH,
                                          buttons_xy=lay["buttons"]) == []
    # 放置规则（含 H1 回调）成立
    guard = ux.InnerSweepGuard(windows)
    pad = ux.padded_bin_shapes(CH, cfg.plan_pad_m)
    reject = lambda i, x, y, yaw, _p: guard.first_rejection(ux.distractor_bin_state(i, x, y, yaw, CH, pad)) is not None
    assert verify_distractor_layout(layout, ux.v5_distractor_cfg(lay["task"]), obstacles=_obstacles(lay),
                                    cube_half_size=CH, extra_reject=reject) == []
    # 发起者排列是 0..9 的排列；第 k 窗发起者按排列顺延 fallback 位
    perm = doc["objects"]["distractors"]["swap_order"]
    assert sorted(perm) == list(range(10))
    for k, ((o, _p), f) in enumerate(zip(pairs, doc["actions"]["distractor_swap_fallback"])):
        assert o == perm[(k + f) % 10]
    # 名字无重复，且与内环名字不相交
    names = layout.bin_names + layout.cube_names
    inner = {f"bin_{i}" for i in range(4)} | {f"target_cube_{c}" for c in ("red", "green", "blue")}
    assert len(set(names)) == len(names) and not (set(names) & inner)
    assert len(layout.cube_bins) == 5 and len(set(layout.cube_bins)) == 5


def test_外环路径约束真的在拒绝候选():
    """把离内环圆距要求提到不可能的值：每窗全部候选都被拒 ⇒ 16 次整段重抽后抛真 SceneGenerationError（N18 留痕）。"""
    lay = LAYOUTS[0]
    cfg = ux.v5_distractor_swap_cfg(lay["task"])
    cfg["path_constraints"]["min_inner_circle_clearance_m"] = 10.0
    recorder = SpecRecorder(None, lay["task"], {"seed": lay["seed"]}, difficulty="xhard")
    with pytest.raises(SceneGenerationError):
        _plan(lay, recorder=recorder, swap_cfg=cfg)
    doc = recorder.to_dict()
    assert doc["layout"]["distractor_layout_attempts"] == 16
    assert doc["layout"]["distractor_layout_failures"] == ["window_0"] * 16
    # 被拒的尝试一次都不走 value：布局与排列都不进规格
    assert "bins" not in doc.get("objects", {}).get("distractors", {})
    assert "swap_order" not in doc.get("objects", {}).get("distractors", {})


def test_规划只用独立流且同seed可复现():
    lay = LAYOUTS[2]
    main = torch.Generator().manual_seed(lay["seed"])
    before = main.get_state().clone()
    (layout_a, pairs_a, _t, _s), rec_a = _plan(lay)
    (layout_b, pairs_b, _t, _s), rec_b = _plan(lay)
    assert torch.equal(before, main.get_state())
    assert layout_a.same_geometry(layout_b) and pairs_a == pairs_b


# ── N18 / N17 ─────────────────────────────────────────────────────────────────
def _value_paths(recorder):
    return [item["path"] for item in recorder.trace if item["source"] in ("draw", "spec")]


def test_只在被接受那次value_回放逐值复现():
    lay = LAYOUTS[3]
    (layout, pairs, _t, _s), recorder = _plan(lay)
    paths = _value_paths(recorder)
    assert paths.count("objects.distractors.swap_order") == 1
    assert paths.count("objects.distractors.bins.0") == 1
    spec = recorder.to_dict()
    replay = SpecRecorder(copy.deepcopy(spec), lay["task"], {"seed": lay["seed"]}, difficulty="xhard")
    (layout_r, pairs_r, _t, _s), _ = _plan(lay, recorder=replay)
    assert layout_r.same_geometry(layout) and pairs_r == pairs
    assert replay.mismatches == []


def test_回放篡改冻结布局被拒():
    lay = LAYOUTS[0]
    (_layout, _pairs, _t, _s), recorder = _plan(lay)
    spec = recorder.to_dict()
    spec["objects"]["distractors"]["bins"]["0"] = [0.0, 0.0, 0.0]
    replay = SpecRecorder(spec, lay["task"], {"seed": lay["seed"]}, difficulty="xhard")
    with pytest.raises(SceneGenerationError):
        _plan(lay, recorder=replay)


def test_回放篡改发起者排列按冻结值重规划并复核():
    lay = LAYOUTS[1]
    (layout, pairs, _t, _s), recorder = _plan(lay)
    spec = recorder.to_dict()
    frozen = list(reversed(spec["objects"]["distractors"]["swap_order"]))
    spec["objects"]["distractors"]["swap_order"] = frozen
    replay = SpecRecorder(spec, lay["task"], {"seed": lay["seed"]}, difficulty="xhard")
    cfg = ux.parse_distractor_swap_cfg(ux.v5_distractor_swap_cfg(lay["task"]))
    expected = ux.plan_distractor_swaps(layout, frozen, _windows(lay), cfg=cfg, cube_half_size=CH)
    if not expected.ok:
        with pytest.raises(SceneGenerationError):
            _plan(lay, recorder=replay)
        return
    (_l, pairs_r, _t, _s), _ = _plan(lay, recorder=replay)
    assert pairs_r == expected.pairs
    assert any(m["path"] == "objects.distractors.swap_order" for m in replay.mismatches)


# ── 运行时 ────────────────────────────────────────────────────────────────────
def test_运行时外环与内环同窗口且每窗恰好一次(monkeypatch):
    calls = []
    from robomme.robomme_env.utils import statechange

    monkeypatch.setattr(statechange, "swap_flat_two_lane",
                        lambda env, **kw: calls.append((kw["cube_a"], kw["cube_b"], kw["start_step"], kw["end_step"],
                                                        kw["cur_step"], kw["lane_offset"], len(kw["other_cube"]))))
    bins = [SimpleNamespace(i=i) for i in range(10)]
    pairs = [(3, 4), (3, 4), (7, 1)]
    schedule = [(None, None, 64 + 33 * k, 64 + 33 * (k + 1)) for k in range(3)]
    recorder = SpecRecorder(None, "VideoUnmaskSwap", {"seed": 1}, difficulty="xhard")
    env = SimpleNamespace(distractor_swap_pairs=pairs, swap_schedule=schedule, distractor_bins=bins, _spec=recorder)
    for t in range(0, 200):
        before = len(calls)
        ux.run_outer_swaps(env, t)
        assert len(calls) - before == len(pairs)  # 每步对每窗都调一次，窗口外由 swap_flat_two_lane 自己 no-op
    for k, (o, p) in enumerate(pairs):
        mine = [c for c in calls if c[2] == schedule[k][2]]
        assert all(c[0] is bins[o] and c[1] is bins[p] and c[3] == schedule[k][3] for c in mine)
        assert all(c[5] == 0.07 and c[6] == 8 for c in mine)
    windows = recorder.to_dict()["actions"]["distractor_swap_windows"]
    assert sorted(windows) == ["0", "1", "2"]
    assert [windows[str(k)]["start_step"] for k in range(3)] == [s[2] for s in schedule]


def test_运行时联合复核带外环对并记录搭档不一致(monkeypatch):
    inner = [SimpleNamespace(xy=xy) for xy in [(0.0, -0.1), (0.0, 0.1), (0.12, 0.1), (0.12, -0.1)]]
    outer = [SimpleNamespace(xy=(0.3 + 0.1 * (i % 5), -0.3 + 0.15 * (i // 5))) for i in range(10)]
    monkeypatch.setattr(ux, "object_state_from_actor", lambda actor, name: _bin_state(name, *actor.xy, 0.0))
    seen = {}
    real = ux.check_multi_swap_sweep

    def spy(pairs, bystanders, **kw):
        seen["pairs"] = [(a.name, b.name) for a, b in pairs]
        seen["bystanders"] = sorted(s.name for s in bystanders)
        return real(pairs, bystanders, **kw)

    monkeypatch.setattr(ux, "check_multi_swap_sweep", spy)
    env = SimpleNamespace(spawned_bins=inner, distractor_bins=outer, distractor_swap_pairs=[(0, 1)],
                          predicted_inner_swap_pairs=[(0, 3)])
    _gap, rejection, info = ux.joint_sweep_from_actual(env, 0, inner[0], inner[1])
    assert seen["pairs"] == [("bin_0", "bin_1"), ("distractor_bin_0", "distractor_bin_1")]
    assert len(seen["bystanders"]) == 2 + 8
    assert info["outer_pair"] == [0, 1] and info["inner_partner_mismatch"] is True
    assert rejection is None


# ── 源码结构 ──────────────────────────────────────────────────────────────────
def _func(task, name):
    tree = ast.parse((ENV_DIR / f"{task}.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == task)
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)


@pytest.mark.parametrize("task", sorted(MODULES))
def test_外环循环在锁定循环之外且只在xhard(task):
    step = _func(task, "step")
    locked = [n for n in ast.walk(step) if isinstance(n, ast.For) and ast.unparse(n.iter) == "range(len(self.swap_schedule))"]
    assert len(locked) == 1
    locked_text = ast.unparse(locked[0])
    for name in ("run_outer_swaps", "park_cubes_onto_bins", "distractor_swap_pairs"):
        assert name not in locked_text
    guarded = [n for n in step.body if isinstance(n, ast.If) and ast.unparse(n.test) == "self._is_xhard"
               and "run_outer_swaps(self, timestep)" in ast.unparse(n.body[0])]
    assert len(guarded) == 1
    # 原三档的被藏 cube 跟随仍是 statechange 的原函数（在 else 分支里）
    assert "lift_and_drop_objectA_onto_objectB(" in ast.unparse(guarded[0].orelse[0])


@pytest.mark.parametrize("task", sorted(MODULES))
def test_spawn只用独立流且调用V5入口(task):
    spawn = ast.unparse(_func(task, "_spawn_xhard_distractors"))
    assert "spawn_swap_distractors_v5(" in spawn and "distractor_generator(self.seed)" in spawn
    assert "generator=generator" not in spawn


def test_bus内环截断在xhard抛真异常():
    scene = _func("ButtonUnmaskSwap", "_load_scene")
    handlers = [n for n in ast.walk(scene) if isinstance(n, ast.ExceptHandler) and ast.unparse(n.type) == "RuntimeError"]
    assert len(handlers) == 1
    body = handlers[0].body
    assert isinstance(body[0], ast.If) and ast.unparse(body[0].test) == "self._is_xhard"
    assert isinstance(body[0].body[0], ast.Raise) and "_RealSceneGenerationError" in ast.unparse(body[0].body[0])
    assert isinstance(body[-1], ast.Break)  # 原三档仍静默截断（N12：既有缺陷只在 xhard 修）
