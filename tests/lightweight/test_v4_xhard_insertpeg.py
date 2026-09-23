#!/usr/bin/env python3
"""轻量测试：V4 InsertPeg 的 xhard 档（计划 2.16 / 2.18），纯 CPU、不起 sapien 场景。

* A6：``configs`` 三档同值且等于原全局常量，xhard 为 4 根杆 / ±180° / 近目标干扰杆；
* ``_native_decision`` 去掉 ``xhard`` 子键后与 V3 原值逐字相同，守卫放行 xhard 取新值、拒绝原值偏离；
* B11 等价朝向归约：判据在原三档（±45°）范围内从不翻转；翻转后 ``insert_peg`` 的**世界系**
  路点与杆位姿对 ``obj × direction`` 四种组合逐一与未归约时一致（且不补偿时会明显不一致，
  证明测试有鉴别力）；
* VQA 选项 a 的候选随杆数自动从 6 涨到 8（仅 xhard 有 4 根杆）。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_insertpeg.py -q
"""

from __future__ import annotations

import copy
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

sapien = pytest.importorskip("sapien")

import importlib  # noqa: E402

# 包 __init__ 把同名类导出成属性，必须按模块路径取模块本体
insertpeg_mod = importlib.import_module("robomme.robomme_env.InsertPeg")
from robomme.robomme_env.utils import subgoal_planner_func as spf  # noqa: E402
from robomme.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    assert_native_decision,
)

CLS = insertpeg_mod.InsertPeg

# V3 原值（计划 2.18 表「现值」列），逐字抄录用于锁定原三档可见部分
V3_DECISION = {
    "peg_count": 3,
    "peg_offsets": [0.1, 0, -0.1],
    "near_target_distractor": None,
    "peg_yaw_range": {"half_span_deg": 45},
}


# ── A6 / decision 结构 ────────────────────────────────────────────────────────
def test_configs_three_tiers_identical_to_native() -> None:
    for tier in ("easy", "medium", "hard"):
        assert CLS.configs[tier] == V3_DECISION
    x = CLS.configs["xhard"]
    assert x["peg_count"] == 4 and len(x["peg_offsets"]) == 4
    assert x["peg_yaw_range"] == {"half_span_deg": 180}
    near = x["near_target_distractor"]
    assert near["anchor_peg_index"] == 0
    # 带宽上限必须严格大于杆间下限 length*1.5 = 0.075（B6 判据不动）
    assert near["max_center_distance_m"] > 0.05 * 1.5


def test_decision_visible_part_unchanged_and_guard() -> None:
    decision, _native = insertpeg_mod.native_blocks(CLS)
    visible = {k: v for k, v in decision.items() if k != "xhard"}
    assert visible == V3_DECISION
    assert decision["xhard"] == CLS.configs["xhard"]
    # 守卫：xhard 子键取新值放行
    narrowed = copy.deepcopy(decision)
    narrowed["xhard"]["near_target_distractor"]["max_center_distance_m"] = 0.08
    assert_native_decision(narrowed, decision, "InsertPeg")
    # 守卫：原值部分偏离拒绝
    bad = copy.deepcopy(decision)
    bad["peg_count"] = 4
    with pytest.raises(SamplingConfigError):
        assert_native_decision(bad, decision, "InsertPeg")
    # 守卫：xhard 里新增申报外的键拒绝
    extra = copy.deepcopy(decision)
    extra["xhard"]["surprise"] = 1
    with pytest.raises(SamplingConfigError):
        assert_native_decision(extra, decision, "InsertPeg")


# ── B11：等价朝向归约 ──────────────────────────────────────────────────────────
BASE_XY = (-0.615, 0.0)


def _rz(theta):
    return [math.cos(theta / 2), 0.0, 0.0, math.sin(theta / 2)]


def _grasp_q(yaw):
    """与 grasp_and_lift_peg_side 相同：peg_q ⊗ Rx(π)。"""
    return spf._quat_wxyz_mul(_rz(yaw), [0.0, 1.0, 0.0, 0.0])


def _rot(q):
    return sapien.Pose(q=np.asarray(q, dtype=np.float64)).to_transformation_matrix()[:3, :3]


@pytest.mark.parametrize("yaw_deg", np.arange(-45, 46, 5))
def test_native_yaw_range_never_flips(yaw_deg) -> None:
    # 原三档杆根点 y∈±[0.15,0.25]（MoveCube）或 [-0.3,0.3]（InsertPeg），±45° 下都不翻
    for p in ([0.0, 0.25, 0.0], [0.0, -0.25, 0.0], [-0.2, 0.3, 0.0], [0.2, -0.3, 0.0]):
        assert not spf.peg_grasp_needs_flip(p, _grasp_q(math.radians(yaw_deg)), BASE_XY)


@pytest.mark.parametrize("yaw_deg", np.arange(-180, 180, 7.5))
def test_reduced_grasp_keeps_relative_heading_within_90(yaw_deg) -> None:
    p = [0.05, 0.2, 0.0]
    q = _grasp_q(math.radians(yaw_deg))
    if spf.peg_grasp_needs_flip(p, q, BASE_XY):
        q = spf.flip_grasp_q(q)
    bearing = math.atan2(p[1] - BASE_XY[1], p[0] - BASE_XY[0])
    rel = (spf._quat_x_axis_heading(q) - bearing + math.pi) % (2 * math.pi) - math.pi
    assert abs(rel) <= math.pi / 2 + 1e-6
    # 夹持几何等价：归约前后夹爪 approach 轴（局部 z）相同，局部 x 轴共线
    r0, r1 = _rot(_grasp_q(math.radians(yaw_deg))), _rot(q)
    assert np.allclose(r0[:, 2], r1[:, 2], atol=1e-6)
    assert abs(abs(float(np.dot(r0[:, 0], r1[:, 0]))) - 1.0) < 1e-6


class _Link:
    def __init__(self, pose):
        self.pose = pose


class _Planner:
    """记录目标位姿，并把「夹爪 + 手里的杆」作为刚体一起移到目标（杆相对夹爪不变）。"""

    def __init__(self, env, held_link):
        self.env = env
        self.held = held_link
        self.rel = env.agent.tcp.pose.inv() * held_link.pose
        self.targets = []

    def move_to_pose_with_screw(self, pose):
        self.targets.append(pose)
        self.env.agent.tcp.pose = pose
        self.held.pose = pose * self.rel

    def open_gripper(self):
        pass

    def close_gripper(self):
        pass


def _make_env(tcp_pose, reduce_flag, flipped):
    env = SimpleNamespace()
    env.unwrapped = env
    env.box = _Link(sapien.Pose(p=[0.02, -0.03, 0.04], q=_rz(math.radians(100))))
    env.agent = SimpleNamespace(tcp=SimpleNamespace(pose=tcp_pose),
                                robot=SimpleNamespace(pose=sapien.Pose(p=[BASE_XY[0], BASE_XY[1], 0.0])))
    env.elapsed_steps = 0
    if reduce_flag:
        env._xhard_peg_yaw_reduction = True
        env._peg_grasp_flipped = flipped
    return env


def _run_insert(peg_yaw, obj, direction, flip, reduce_flag=True):
    """杆（insert_obj 链接）在 yaw=peg_yaw 处，夹爪按原姿态或翻转姿态抓住它后执行 insert_peg。"""
    link_pose = sapien.Pose(p=[0.1, 0.2, 0.01], q=_rz(peg_yaw))
    q = _grasp_q(peg_yaw)
    if flip:
        q = spf.flip_grasp_q(q)
    tcp = sapien.Pose(p=[0.1, 0.2, 0.2], q=np.asarray(q, dtype=np.float64))
    env = _make_env(tcp, reduce_flag, flip)
    insert_obj = _Link(link_pose)
    planner = _Planner(env, insert_obj)
    spf.insert_peg(env, planner, direction=direction, obj=obj, insert_obj=insert_obj)
    tcp_ps = [np.asarray(t.p, dtype=np.float64) for t in planner.targets]
    peg_poses = [t * planner.rel for t in planner.targets]
    return tcp_ps, peg_poses


def _pose_close(a, b, atol=1e-5):
    return (np.allclose(np.asarray(a.p), np.asarray(b.p), atol=atol)
            and np.allclose(a.to_transformation_matrix()[:3, :3], b.to_transformation_matrix()[:3, :3], atol=atol))


@pytest.mark.parametrize("obj", [-1, 1])
@pytest.mark.parametrize("direction", [-1, 1])
@pytest.mark.parametrize("peg_yaw_deg", [150.0, -120.0, 175.0])
def test_insert_peg_waypoints_equivalent_after_flip(obj, direction, peg_yaw_deg) -> None:
    yaw = math.radians(peg_yaw_deg)
    tcp0, peg0 = _run_insert(yaw, obj, direction, flip=False)
    tcp1, peg1 = _run_insert(yaw, obj, direction, flip=True)
    assert len(tcp0) == len(tcp1) >= 3
    for a, b in zip(tcp0, tcp1):
        assert np.allclose(a, b, atol=1e-5), (a, b)
    for a, b in zip(peg0, peg1):
        assert _pose_close(a, b)


@pytest.mark.parametrize("obj", [-1, 1])
@pytest.mark.parametrize("direction", [-1, 1])
def test_insert_peg_without_compensation_diverges(obj, direction) -> None:
    """反例：夹爪翻了但路点不补偿（开关关闭），世界系路点至少差 0.1 m——证明上一条测试有鉴别力。"""
    yaw = math.radians(150.0)
    tcp0, _ = _run_insert(yaw, obj, direction, flip=False)
    tcp_bad, _ = _run_insert(yaw, obj, direction, flip=True, reduce_flag=False)
    assert max(float(np.linalg.norm(a - b)) for a, b in zip(tcp0, tcp_bad)) > 0.1


def test_grasp_and_lift_sets_flag_only_when_switch_on() -> None:
    yaw = math.radians(160.0)
    link = _Link(sapien.Pose(p=[0.05, 0.2, 0.01], q=_rz(yaw)))
    for switch in (False, True):
        env = _make_env(sapien.Pose(p=[0.0, 0.0, 0.3], q=[0, 1, 0, 0]), False, False)
        if switch:
            env._xhard_peg_yaw_reduction = True
        planner = _Planner(env, _Link(sapien.Pose()))
        spf.grasp_and_lift_peg_side(env, planner, link)
        final_q = np.asarray(planner.targets[-1].q, dtype=np.float64)
        expect = _grasp_q(yaw)
        if switch:
            assert env._peg_grasp_flipped is True and env._peg_grasp_flip_log == [True]
            expect = spf.flip_grasp_q(expect)
        else:
            assert not hasattr(env, "_peg_grasp_flipped")
        assert np.allclose(_rot(final_q), _rot(expect), atol=1e-5)


# ── VQA 候选 6→8 ──────────────────────────────────────────────────────────────
def test_vqa_insertpeg_available_scales_with_peg_count() -> None:
    from robomme.robomme_env.utils import vqa_options

    for n in (3, 4):
        env = SimpleNamespace(peg_heads=[object() for _ in range(n)], peg_tails=[object() for _ in range(n)],
                              obj_flag=1, insert_target=None)
        options = vqa_options._options_insertpeg(env, None, lambda: None, env)
        assert len(options[0]["available"]) == 2 * n
