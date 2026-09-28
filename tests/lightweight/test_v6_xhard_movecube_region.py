#!/usr/bin/env python3
"""轻量测试：V6 MoveCube xhard4 的统一区域 U（docs/plans/0925-newtask-release-v6-plan.md 2.6，圆环版）。

离线部分纯 CPU、不起 sapien 场景：借用 ``test_v5_xhard_movecube`` 的假场景（假 builder、假 TableSceneBuilder），
直接跑真实的 ``MoveCube._load_scene``（随机调用、拒绝循环、规格记录全是真代码）。

* ``MC_REGION``：多 seed 下两段的方块中心、goal 中心、杆抓取点都在 U 内（圆环 ∧ 离基座区间），
  推起点（后退 0.10、带杆再侧移 ±0.10）离基座在区间内，杆身线段离圆心 ≥ r_in，方块/goal 离杆身 ≥ 0.04/0.02，
  方块-goal 距离 ∈ [0.10, 0.30]；判据由本文件独立实现（照 ``reach/U/region.py``），不从被测代码取；且无一局生成失败；
* decision：``demo_layout.xhard4`` / ``execution_layout.xhard4`` 只剩 ``region`` 子键，两段各自一份；非法值被拒；
* spawn 函数的四个新参数：默认 None 时整段跳过，给了就按规则拒绝，回放冻结值违反即报 ``EpisodeSpecError``；
* 预算耗尽抛真 ``SceneGenerationError``；
* N17：回放冻结规格时杆、goal、方块违反 U 都报 ``EpisodeSpecError``；合规规格回放逐值一致。

    PYTHONPATH="$PWD/src" uv run --project /data/hongzefu/robomme_benchmark_MotionJEPANewTask --no-sync python -m pytest tests/lightweight/test_v6_xhard_movecube_region.py -q -s
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest
import torch

from tests.lightweight.test_v5_xhard_movecube import (  # noqa: F401  fake_scene 为 fixture
    CLS, PEG_EXTENT_MEASURED, EpisodeSpecError, SamplingConfigError, SceneGenerationError,
    _fingerprint, _make, _run, fake_scene, mc, og,
)

BASE = np.array([-0.615, 0.0])
C0 = np.array([-0.06, 0.0])
R_IN, R_OUT, B_LO, B_HI = 0.12, 0.20, 0.35, 0.76
PUSH_MIN, PUSH_MAX, PEG_GAP, GOAL_PEG_GAP = 0.10, 0.30, 0.04, 0.02
REGION_SEEDS = list(range(6000000, 6002000))
EPS = 1e-9


def _root(lay):
    base_y, xj, yj = lay["peg_offsets"]
    root = np.array([0.0, base_y], dtype=np.float32)
    root += np.array([xj, yj], dtype=np.float32)
    return root.astype(np.float64)


def _seg_dist(p, root, yaw, ext=PEG_EXTENT_MEASURED):
    u = np.array([math.cos(yaw), math.sin(yaw)])
    rel = np.asarray(p, dtype=np.float64) - root
    t = float(np.clip(rel @ u, ext[0], ext[1]))
    return float(np.linalg.norm(rel - t * u))


def _in_u(p):
    rc = float(np.linalg.norm(np.asarray(p) - C0))
    rb = float(np.linalg.norm(np.asarray(p) - BASE))
    return R_IN - EPS <= rc <= R_OUT + EPS and B_LO - EPS <= rb <= B_HI + EPS


def _push_ok(cube, goal):
    d = np.asarray(goal) - np.asarray(cube)
    n = float(np.linalg.norm(d))
    if not (PUSH_MIN - EPS <= n <= PUSH_MAX + EPS):
        return False
    d /= n
    lat = np.array([-d[1], d[0]])
    for s in (0.0, 1.0, -1.0):
        r = float(np.linalg.norm(np.asarray(cube) - 0.10 * d - 0.10 * s * lat - BASE))
        if not (B_LO - EPS <= r <= B_HI + EPS):
            return False
    return True


def segment_violations(lay):
    """独立复核一段布局，返回违规项列表。"""
    out = []
    root, yaw = _root(lay), float(lay["peg_yaw"])
    u = np.array([math.cos(yaw), math.sin(yaw)])
    grasp = root - 0.10 * u
    goal = np.asarray(lay["goal_xy"], dtype=np.float64)
    cube = np.asarray(lay["cube_pose"][:2], dtype=np.float64)
    if not _in_u(grasp):
        out.append("peg_grasp")
    if _seg_dist(C0, root, yaw) < R_IN - EPS:
        out.append("peg_body")
    if not _in_u(goal):
        out.append("goal")
    if not _in_u(cube):
        out.append("cube")
    if _seg_dist(cube, root, yaw) < PEG_GAP - EPS:
        out.append("cube_peg_gap")
    if _seg_dist(goal, root, yaw) < GOAL_PEG_GAP - EPS:
        out.append("goal_peg_gap")
    if not _push_ok(cube, goal):
        out.append("push")
    return out


# ---------------------------------------------------------------------------
# decision
# ---------------------------------------------------------------------------
def test_region_decision_and_validation() -> None:
    decision, _ = mc.native_blocks(CLS)
    for seg in ("demo_layout", "execution_layout"):
        assert set(decision[seg]["xhard4"]) == {"region"}
    assert decision["demo_layout"]["xhard4"]["region"] is not decision["execution_layout"]["xhard4"]["region"]
    layout = copy.deepcopy(decision["demo_layout"])
    reg = CLS._xhard4_region(None, layout, "demo_layout")
    assert reg["annulus"] == ((-0.06, 0.0), 0.12, 0.20)
    assert (reg["base_lo"], reg["base_hi"]) == (0.35, 0.76)
    assert (reg["push_len_max"], reg["peg_gap"], reg["goal_peg_gap"]) == (0.30, 0.04, 0.02)
    bad = [("r_in", 0.25), ("r_in", -0.1), ("r_out", float("nan")), ("base_dist", [0.8, 0.3]),
           ("base_dist", [0.3]), ("center", [0.0]), ("peg_gap", -0.01), ("cube_max_trials", 0),
           ("goal_max_trials", 1.5), ("peg_max_trials", True)]
    for key, value in bad:
        broken = copy.deepcopy(layout)
        broken["xhard4"]["region"][key] = value
        with pytest.raises(SamplingConfigError):
            CLS._xhard4_region(None, broken, "demo_layout")
    missing = copy.deepcopy(layout)
    del missing["xhard4"]["region"]["push_len_max"]
    with pytest.raises(SamplingConfigError):
        CLS._xhard4_region(None, missing, "demo_layout")


# ---------------------------------------------------------------------------
# MC_REGION：多 seed 离线复核
# ---------------------------------------------------------------------------
def test_region_all_rules_hold(fake_scene) -> None:
    violations, layout_fail = [], []
    peg_trials, n_seg = [], 0
    for seed in REGION_SEEDS:
        start = len(fake_scene.calls)
        env, err = _run(seed, "xhard4")
        if err is not None:
            layout_fail.append((seed, err))
            continue
        spec = env._spec.to_dict()["layout"]
        calls = fake_scene.calls[start:]
        assert [c["name"] for c in calls] == ["fixed_cube", "fixed_cube_2"]
        for seg in ("demo", "execution"):
            lay = spec[seg]
            n_seg += 1
            for what in segment_violations(lay):
                violations.append((seed, seg, what))
            assert lay["region"]["r_in"] == R_IN and lay["region"]["r_out"] == R_OUT
            assert lay["region"]["peg_axis_extent_m"] == pytest.approx(list(PEG_EXTENT_MEASURED))
            peg_trials.append(lay["region_trials"]["peg_trials"])
            assert "center_exclusion" not in lay and "corner_bias" not in lay
        for call in calls:
            assert call["extra"] == {"include_existing": False}
    print(f"MC_REGION={'PASS' if not violations and not layout_fail else 'FAIL'} seeds={len(REGION_SEEDS)} "
          f"violations={len(violations)} layout_fail={len(layout_fail)} "
          f"peg_trials_mean={np.mean(peg_trials):.2f} max={max(peg_trials)}")
    assert violations == []
    assert layout_fail == []


def test_peg_budget_exhaustion_raises_real_scene_generation_error(fake_scene) -> None:
    env = _make(6000000, "xhard4")
    for seg in ("demo_layout", "execution_layout"):
        env._sampling["decision"][seg]["xhard4"]["region"]["r_in"] = 0.199   # 杆身 0.2 长，必然伸进内孔
    with pytest.raises(SceneGenerationError, match="杆 128 次重抽"):
        env._load_scene({})


def test_cube_budget_exhaustion_raises_real_scene_generation_error(fake_scene) -> None:
    env = _make(6000000, "xhard4")
    for seg in ("demo_layout", "execution_layout"):
        env._sampling["decision"][seg]["xhard4"]["region"]["push_len_max"] = 0.1000001   # 推距窗口几乎为零
        env._sampling["decision"][seg]["xhard4"]["region"]["cube_max_trials"] = 8
    with pytest.raises(SceneGenerationError, match="方块生成失败") as info:
        env._load_scene({})
    assert isinstance(info.value.__cause__, RuntimeError)


# ---------------------------------------------------------------------------
# N17：回放
# ---------------------------------------------------------------------------
def _export(seed):
    env, err = _run(seed, "xhard4")
    assert err is None
    return env._spec.to_dict(), _fingerprint(env, err)


def test_replay_valid_spec_reproduces_layout(fake_scene) -> None:
    for seed in (6000000, 6000001, 6000007):
        spec, fp = _export(seed)
        env = _make(seed, "xhard4", spec=copy.deepcopy(spec))
        env._load_scene({})
        assert env._spec.mismatches == []
        fp2 = _fingerprint(env, None)
        for name in ("peg", "goal_site", "goal_site_2", "cube", "cube_2", "peg_init_poses_2"):
            assert fp2[name] == fp[name]


@pytest.mark.parametrize("seg", ["demo", "execution"])
@pytest.mark.parametrize("offsets, yaw, why", [
    ([0.0, -0.06, 0.05], 0.0, "抓取点"),          # 抓取点 (−0.16, 0.05)：离圆心 0.112 < r_in
    ([0.0, 0.25, 0.10], 0.0, "抓取点"),           # 抓取点 (0.15, 0.10)：离圆心 0.23 > r_out
    ([0.0, -0.06, -0.04], math.pi / 2, "杆身"),   # 抓取点 (−0.06, −0.14) 在环内，杆身沿 +y 穿过圆心
])
def test_replay_rejects_peg_violation(fake_scene, seg, offsets, yaw, why) -> None:
    spec, _ = _export(6000000)
    spec["layout"][seg]["peg_offsets"] = offsets
    spec["layout"][seg]["peg_yaw"] = yaw
    env = _make(6000000, "xhard4", spec=spec)
    with pytest.raises(EpisodeSpecError, match=f"统一区域 U.*{why}"):
        env._load_scene({})


@pytest.mark.parametrize("path, value", [
    ("demo.goal_xy", [-0.06, 0.05]),             # 圆环内孔
    ("execution.goal_xy", [0.20, 0.0]),          # 圆环外
    ("demo.cube_pose", [-0.06, 0.0, 0.3]),       # 圆环内孔
    ("execution.cube_pose", [0.16, 0.0, 1.0]),   # 离圆心 0.22 > r_out
])
def test_replay_rejects_goal_and_cube_violation(fake_scene, path, value) -> None:
    spec, _ = _export(6000000)
    seg, key = path.split(".")
    spec["layout"][seg][key] = value
    env = _make(6000000, "xhard4", spec=spec)
    with pytest.raises(EpisodeSpecError):
        env._load_scene({})


# ---------------------------------------------------------------------------
# spawn 函数新参数（默认 None 整段跳过；给了就拒）
# ---------------------------------------------------------------------------
def test_region_rules_numeric() -> None:
    rules = og._normalize_region_rules(((-0.06, 0.0), 0.12, 0.20), ((-0.615, 0.0), 0.35, 0.76),
                                       [((0.0, 0.2), (0.0, 0.3), 0.04)],
                                       ((-0.06, 0.0), 0.10, 0.30, 0.10, 0.10, (-0.615, 0.0), 0.35, 0.76), "t")
    assert og._region_rules_violation(rules, -0.06, 0.0) is not None          # 内孔
    assert og._region_rules_violation(rules, 0.0, 0.18) is not None           # 离杆段太近（且推距不够）
    assert og._region_rules_violation(rules, -0.06, -0.15) is None            # 环内、推距 0.15、三个推起点离基座 0.52～0.70
    for bad in (dict(annulus=((0, 0), 0.3, 0.2)), dict(base_band=((0, 0), 0.5)),
                dict(segment_clearance=[((0, 0), (1, 1))]), dict(push_feasible=((0, 0), 0.0, 0.3))):
        args = dict(annulus=None, base_band=None, segment_clearance=None, push_feasible=None)
        args.update(bad)
        with pytest.raises(ValueError):
            og._normalize_region_rules(args["annulus"], args["base_band"], args["segment_clearance"],
                                       args["push_feasible"], "t")
    assert og.point_segment_distance_xy((0, 0), (1, 0), (1, 0)) == pytest.approx(1.0)
    assert og.point_segment_distance_xy((0.5, 1.0), (0, 0), (1, 0)) == pytest.approx(1.0)


def test_spawn_region_params_default_none_and_reject(fake_scene) -> None:
    from tests.lightweight.test_v5_shared_sampling import _fake_env
    # 默认 None：与不传逐位一致
    a = og.spawn_random_cube(_fake_env(), region_center=[0, 0], region_half_size=0.2, half_size=0.02,
                             generator=torch.Generator().manual_seed(3), include_existing=False, include_goal=False)
    b = og.spawn_random_cube(_fake_env(), region_center=[0, 0], region_half_size=0.2, half_size=0.02,
                             generator=torch.Generator().manual_seed(3), include_existing=False, include_goal=False,
                             annulus=None, base_band=None, segment_clearance=None, push_feasible=None)
    assert torch.equal(a.pose.p, b.pose.p) and torch.equal(a.pose.q, b.pose.q)
    # 给了就拒：多次抽样全在环内
    for s in range(20):
        c = og.spawn_random_cube(_fake_env(), region_center=[-0.06, 0], region_half_size=0.22, half_size=0.02,
                                 generator=torch.Generator().manual_seed(s), include_existing=False,
                                 include_goal=False, annulus=((-0.06, 0.0), 0.12, 0.20), max_trials=4096)
        r = float(np.linalg.norm(c.pose.p[0, :2].numpy() - C0))
        assert 0.12 - 1e-6 <= r <= 0.20 + 1e-6
        t = og.spawn_random_target(_fake_env(), region_center=[-0.06, 0], region_half_size=0.24, radius=0.04,
                                   generator=torch.Generator().manual_seed(s), include_existing=False,
                                   include_goal=False, annulus=((-0.06, 0.0), 0.12, 0.20))
        r = float(np.linalg.norm(np.asarray(t.pose.p).reshape(-1)[:2] - C0))
        assert 0.12 - 1e-6 <= r <= 0.20 + 1e-6
    # 注入值违反即报错
    with pytest.raises(EpisodeSpecError):
        og.spawn_random_cube(_fake_env(), fixed_xy=[-0.06, 0.0], fixed_yaw=0.0,
                             annulus=((-0.06, 0.0), 0.12, 0.20))
