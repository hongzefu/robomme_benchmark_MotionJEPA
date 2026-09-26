#!/usr/bin/env python3
"""轻量测试：V4 MoveCube 的 xhard4 档兼容机制（计划 2.16 / 2.17），纯 CPU、不起 sapien 场景。

* A6：``configs`` 三档同值且等于原全局常量；xhard4 为 ±180°；
  V5（计划 2.9，L33）：旧档的 ``corner_bias`` 已删干净，改为 ``center_exclusion``；V6（计划 2.6）再换成
  统一区域 ``region``（断言已改为 V6 语义，
  ``corner_bias`` 取值校验的旧单测随 ``_xhard_corner_bias`` 一并删除，禁区校验见 ``test_v5_xhard_movecube.py``）；
* ``_native_decision`` 去掉 ``xhard4`` 子键后与 V3 原值逐字相同；守卫放行 xhard4 取新值；
  演示段与执行段的 ``region`` 各自声明（两套不可合并）；
* B11：翻转夹爪后 ``solve_push_to_target_with_peg`` 的世界系路点与杆位姿对
  ``obj_flag × direction`` 四种组合逐一与未归约时一致，不补偿则杆朝向相差 180°。

    PYTHONPATH="$PWD/src" uv run --project /data/hongzefu/robomme_benchmark_MotionJEPANewTask --no-sync python -m pytest tests/lightweight/test_v4_xhard_movecube.py -q
"""

from __future__ import annotations

import copy
import importlib
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

# 包 __init__ 把同名类导出成属性，必须按模块路径取模块本体
movecube_mod = importlib.import_module("robomme.robomme_env.MoveCube")
from robomme.robomme_env.utils import subgoal_planner_func as spf  # noqa: E402
from robomme.robomme_env.utils.sampling_config import (  # noqa: E402
    SamplingConfigError,
    assert_native_decision,
)

CLS = movecube_mod.MoveCube

V3_DECISION = {
    "demo_layout": {
        "peg_position_policy": {"base_y_abs": 0.2, "base_y_threshold": 0.5, "jitter_span": 0.1},
        "cube_position_policy": {"center_span": 0.2, "center_offset": -0.1, "region_half_size": 0.05},
    },
    "execution_layout": {
        "peg_position_policy": {"base_y_abs": 0.2, "base_y_threshold": 0.5, "jitter_span": 0.1},
        "cube_position_policy": {"center_span": 0.2, "center_offset": -0.1, "region_half_size": 0.05},
    },
    "peg_yaw_range": {"span_rad": np.pi / 2, "offset_rad": np.pi / 4},
}


def _strip(node):
    if isinstance(node, dict):
        return {k: _strip(v) for k, v in node.items() if k != "xhard4"}
    return node


def test_configs_three_tiers_identical_and_xhard4_values() -> None:
    for tier in ("easy", "medium", "hard"):
        assert CLS.configs[tier]["peg_yaw_range"] == V3_DECISION["peg_yaw_range"]
        assert CLS.configs[tier]["corner_bias"] == 0.0
    x = CLS.configs["xhard4"]
    assert x["peg_yaw_range"]["span_rad"] == pytest.approx(2 * np.pi)
    assert x["peg_yaw_range"]["offset_rad"] == pytest.approx(np.pi)
    # V5 L33：corner_bias 删键；V6（计划 2.6）：V5 的中心圆禁区换成统一区域 U（圆环版，用户 2026-09-25 定）
    assert "corner_bias" not in x and "center_exclusion" not in x
    assert x["region"] == {"center": [-0.06, 0.0], "r_in": 0.12, "r_out": 0.20, "base_dist": [0.35, 0.76],
                           "push_len_max": 0.30, "peg_gap": 0.04, "goal_peg_gap": 0.02,
                           "peg_max_trials": 128, "goal_max_trials": 256, "cube_max_trials": 4096}


def test_decision_visible_part_unchanged_and_guard() -> None:
    decision, _native = movecube_mod.native_blocks(CLS)
    assert _strip(decision) == V3_DECISION
    assert decision["demo_layout"]["xhard4"] == {"region": CLS.configs["xhard4"]["region"]}
    assert decision["execution_layout"]["xhard4"] == {"region": CLS.configs["xhard4"]["region"]}
    # 两段是各自的副本，改一段不影响另一段与类默认值
    assert decision["demo_layout"]["xhard4"]["region"] is not decision["execution_layout"]["xhard4"]["region"]
    assert decision["peg_yaw_range"]["xhard4"] == CLS.configs["xhard4"]["peg_yaw_range"]
    # 演示段与执行段各自一份（可取不同值）
    tuned = copy.deepcopy(decision)
    tuned["demo_layout"]["xhard4"]["region"]["r_in"] = 0.10
    tuned["execution_layout"]["xhard4"]["region"]["r_in"] = 0.14
    assert_native_decision(tuned, decision, "MoveCube")
    bad = copy.deepcopy(decision)
    bad["demo_layout"]["peg_position_policy"]["jitter_span"] = 0.2
    with pytest.raises(SamplingConfigError):
        assert_native_decision(bad, decision, "MoveCube")


# ── B11：推杆路点补偿 ──────────────────────────────────────────────────────────
def _rz(theta):
    return [math.cos(theta / 2), 0.0, 0.0, math.sin(theta / 2)]


def _grasp_q(yaw):
    return spf._quat_wxyz_mul(_rz(yaw), [0.0, 1.0, 0.0, 0.0])


class _Actor:
    def __init__(self, p):
        self.pose = SimpleNamespace(sp=SimpleNamespace(p=np.asarray(p, dtype=np.float64)))


class _Planner:
    def __init__(self):
        self.targets = []

    def move_to_pose_with_screw(self, pose):
        self.targets.append(pose)

    def open_gripper(self):
        pass

    def close_gripper(self):
        pass


def _run_push(peg_yaw, direction, obj_flag, flip, reduce_flag=True):
    link_pose = sapien.Pose(p=[0.0, 0.2, 0.01], q=_rz(peg_yaw))
    q = _grasp_q(peg_yaw)
    if flip:
        q = spf.flip_grasp_q(q)
    tcp_grasp = sapien.Pose(p=[0.0, 0.2, 0.01], q=np.asarray(q, dtype=np.float64))
    rel = tcp_grasp.inv() * link_pose  # 抓住后杆相对夹爪固定
    env = SimpleNamespace()
    env.unwrapped = env
    if reduce_flag:
        env._xhard_peg_yaw_reduction = True
        env._peg_grasp_flipped = flip
    planner = _Planner()
    spf.solve_push_to_target_with_peg(env, planner, obj=_Actor([0.05, -0.06, 0.02]),
                                      target=_Actor([-0.08, 0.07, 0.0]),
                                      direction=direction, obj_flag=obj_flag)
    return [(np.asarray(t.p, dtype=np.float64), t * rel) for t in planner.targets]


def _rot(pose):
    return pose.to_transformation_matrix()[:3, :3]


@pytest.mark.parametrize("obj_flag", [-1, 1])
@pytest.mark.parametrize("direction", [-1, 1])
@pytest.mark.parametrize("peg_yaw_deg", [140.0, -150.0])
def test_push_waypoints_equivalent_after_flip(obj_flag, direction, peg_yaw_deg) -> None:
    yaw = math.radians(peg_yaw_deg)
    a = _run_push(yaw, direction, obj_flag, flip=False)
    b = _run_push(yaw, direction, obj_flag, flip=True)
    assert len(a) == len(b) == 3
    for (pa, peg_a), (pb, peg_b) in zip(a, b):
        assert np.allclose(pa, pb, atol=1e-6)
        assert np.allclose(np.asarray(peg_a.p), np.asarray(peg_b.p), atol=1e-5)
        assert np.allclose(_rot(peg_a), _rot(peg_b), atol=1e-5)


@pytest.mark.parametrize("obj_flag", [-1, 1])
@pytest.mark.parametrize("direction", [-1, 1])
def test_push_without_compensation_flips_peg(obj_flag, direction) -> None:
    yaw = math.radians(140.0)
    a = _run_push(yaw, direction, obj_flag, flip=False)
    bad = _run_push(yaw, direction, obj_flag, flip=True, reduce_flag=False)
    # 不补偿：杆长轴在世界系反向（点积 ≈ -1），伸出的一端落到推杆方向的另一侧
    dots = [float(np.dot(_rot(pa)[:, 0], _rot(pb)[:, 0])) for (_, pa), (_, pb) in zip(a, bad)]
    assert all(d < -0.99 for d in dots)


@pytest.mark.parametrize("tier", ["xhard1", "xhard2", "xhard3"])
def test_v6_no_tier_rejects_xhard123(tier) -> None:
    """V6（计划 2.13 / M2）：本环境原版无梯度、不加档，configs 仍只有 xhard4；
    传入 xhard1/2/3 在 __init__ 里（super().__init__ 之前、不起 sapien 场景）明确抛 ValueError。"""
    assert set(CLS.configs) == {"easy", "medium", "hard", "xhard4"}
    with pytest.raises(ValueError, match="不加档"):
        CLS(difficulty=tier)
