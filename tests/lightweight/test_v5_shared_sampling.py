#!/usr/bin/env python3
"""轻量测试：V5 S2a 共用采样基础设施（NEWTASK_RELEASE_V5_PLAN 2.0①②③、L3、L4 b）。

纯 CPU、不起 sapien 场景（``actors.build_cube`` 与圆盘 builder 用假 actor 顶替）：

* ``utils/xhard.py::cube_obb2d_exact``：任意 yaw、任意姿态都不退化，与解析方块
  ``_build_new_cube_obb2d`` 逐位一致；输出形态被两个 spawn 函数识别为「预制障碍」；
* ``spawn_random_cube`` / ``spawn_random_target`` 的新参数 ``min_center_dist`` / ``center_exclusion``
  在默认值（None）下逐位不变——与改动前代码算出的金标准哈希比对（抽样结果 + 调用后随机流哨兵）；
* 新参数开启时确实拒绝、且不多抽随机数（拒绝只影响 trial 次数）；回放冻结值违反规则时报错（N17）；
* 7 个被遮蔽模块（L3）：xhard 拿到真 ``SceneGenerationError``，原三档仍是被遮蔽的子模块（TypeError 现状）。

    uv run --no-sync python -m pytest tests/lightweight/test_v5_shared_sampling.py -q
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import math
import sys
import types
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

from mani_skill.utils.structs.pose import Pose  # noqa: E402

from robomme.robomme_env.utils import object_generation as og  # noqa: E402
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402
from robomme.robomme_env.utils.xhard import cube_obb2d_exact  # noqa: E402

ENV_DIR = REPO_ROOT / "src" / "robomme" / "robomme_env"


# ---------------------------------------------------------------------------
# 假场景：顶替 sapien 建物体，只记录位姿
# ---------------------------------------------------------------------------
class _FakeActor:
    def __init__(self, name, pose):
        self.name = name
        self.pose = pose


def _fake_build_cube(scene, half_size, color, name, initial_pose):
    return _FakeActor(name, initial_pose)


def _fake_build_target(scene, radius, thickness, name, body_type, add_collision, initial_pose):
    return _FakeActor(name, initial_pose)


@pytest.fixture
def fake_scene(monkeypatch):
    monkeypatch.setattr(og.actors, "build_cube", _fake_build_cube)
    monkeypatch.setattr(og, "build_purple_white_target", _fake_build_target)
    monkeypatch.setattr(og, "build_gray_white_target", _fake_build_target)


def _fake_env():
    return SimpleNamespace(device="cpu", scene=None)


def _cube_xy_yaw(actor):
    p = actor.pose.p[0].tolist()
    w, _, _, z = actor.pose.q[0].tolist()
    return p[0], p[1], 2.0 * math.atan2(z, w)


def _target_xy(actor):
    p = actor.pose.p
    return float(p[0]), float(p[1])


# 静态障碍：解析方块（改动前后都存在的 _build_new_cube_obb2d），保证拒绝循环真的有多次 trial
_STATIC_OBSTACLES = [(0.0, 0.0, 0.3), (0.05, -0.04, 1.1), (-0.06, 0.05, 2.0), (0.08, 0.08, 0.7)]


def _static_avoid():
    return [og._build_new_cube_obb2d(x, y, 0.02, yaw) for x, y, yaw in _STATIC_OBSTACLES]


CUBE_SCENARIOS = {
    "yaw_uniform": dict(region_half_size=0.15, random_yaw=True, corner_bias=0.0),
    "no_yaw": dict(region_half_size=[0.15, 0.11], random_yaw=False, corner_bias=0.0),
    "corner_bias": dict(region_half_size=0.15, random_yaw=True, corner_bias=0.5),
}


def _run_cube_scenario(scenario, seed, extra_for_call=None):
    """同一 seed 连放 4 块（每块进下一块的 avoid），返回可哈希的逐位文本与放下的 xy。

    ``extra_for_call(i, placed_xy)`` 返回第 i 次调用额外传的关键字（新参数），None 即不传。
    """
    cfg = CUBE_SCENARIOS[scenario]
    env = _fake_env()
    gen = torch.Generator().manual_seed(seed)
    avoid = _static_avoid()
    placed = []
    out = []
    for i in range(4):
        extra = {} if extra_for_call is None else extra_for_call(i, list(placed))
        try:
            cube = og.spawn_random_cube(
                env,
                region_center=[0.0, 0.0],
                region_half_size=cfg["region_half_size"],
                half_size=0.02,
                min_gap=0.02,
                max_trials=64,
                avoid=avoid,
                random_yaw=cfg["random_yaw"],
                include_existing=True,
                include_goal=True,
                generator=gen,
                name_prefix=f"cube_{i}",
                corner_bias=cfg["corner_bias"],
                **extra,
            )
        except RuntimeError:
            out.append("FAIL")
            continue
        x, y, yaw = _cube_xy_yaw(cube)
        placed.append((x, y))
        out.append(f"{x.hex()},{y.hex()},{yaw.hex()}")
        avoid.append(og._build_new_cube_obb2d(x, y, 0.02, yaw))
    out.append(f"sentinel={torch.rand(1, generator=gen).item().hex()}")
    return "|".join(out), placed


def _run_target_scenario(seed, extra_for_call=None, style="purple"):
    env = _fake_env()
    gen = torch.Generator().manual_seed(seed)
    avoid = _static_avoid()
    placed = []
    out = []
    for i in range(3):
        extra = {} if extra_for_call is None else extra_for_call(i, list(placed))
        try:
            target = og.spawn_random_target(
                env,
                region_center=[0.0, 0.0],
                region_half_size=0.2,
                radius=0.03,
                thickness=0.005,
                min_gap=0.02,
                max_trials=64,
                avoid=avoid,
                include_existing=True,  # 已放圆盘走 _spawned_targets 的圆障碍
                include_goal=True,
                generator=gen,
                name_prefix=f"target_{i}",
                target_style=style,
                **extra,
            )
        except RuntimeError:
            out.append("FAIL")
            continue
        x, y = _target_xy(target)
        placed.append((x, y))
        out.append(f"{x.hex()},{y.hex()}")
    out.append(f"sentinel={torch.rand(1, generator=gen).item().hex()}")
    return "|".join(out), placed


SEEDS = range(40)


def _digest(texts):
    return hashlib.sha256("\n".join(texts).encode()).hexdigest()


# 金标准：在改动前的 object_generation.py（基线提交 f5b6a17）上用同一套场景算出，逐位锁死默认行为
GOLDEN = {
    "cube.yaw_uniform": "7bbb171296ce324e1c16be060123cea6dbef71c2448f43f34e9586031dfe102d",
    "cube.no_yaw": "474ea9df5696b717eefa2ee8fd6bd970b8a22070a21253e949c6f33ec8cae580",
    "cube.corner_bias": "dc572d47a1592f47efc8280cb7a0a0f1f8697aedb79cef4f3cd9edde8a4f6813",
    "target.purple": "bc3efdd2c25086b6fa124c85424a65b90c23704ea320b560483606b333c83566",
}


def compute_digests():
    """供重算金标准用：``python -c 'import tests.lightweight.test_v5_shared_sampling as t; ...'``。"""
    digests = {}
    for name in CUBE_SCENARIOS:
        digests[f"cube.{name}"] = _digest([_run_cube_scenario(name, s)[0] for s in SEEDS])
    digests["target.purple"] = _digest([_run_target_scenario(s)[0] for s in SEEDS])
    return digests


# ---------------------------------------------------------------------------
# 一、cube_obb2d_exact
# ---------------------------------------------------------------------------
def _corners(obb):
    c, A, h = obb
    pts = [c + A @ np.array([sx * h[0], sy * h[1]]) for sx in (-1, 1) for sy in (-1, 1)]
    return np.array(sorted(tuple(np.round(p, 7)) for p in pts))


def _quat_wxyz_from_matrix(R):
    """3×3 旋转矩阵 → wxyz 四元数（测试构造任意姿态用）。"""
    m = torch.as_tensor(np.asarray(R), dtype=torch.float64)[None]
    return og.matrix_to_quaternion(m)[0].numpy()


def _rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


_ROT_X90 = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
_ROT_Y90 = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])


def _assert_not_degenerate(obb):
    _, A, h = obb
    assert np.allclose(np.linalg.norm(A, axis=0), 1.0, atol=1e-12)
    assert np.allclose(A.T @ A, np.eye(2), atol=1e-12)
    assert abs(np.linalg.det(A) - 1.0) < 1e-12
    assert np.all(h > 0)


@pytest.mark.parametrize("pad", [0.0, 0.02])
def test_exact_obb_xy_yaw_matches_analytic_bitwise(pad) -> None:
    for yaw in np.linspace(-4 * math.pi, 4 * math.pi, 721):
        got = cube_obb2d_exact((0.03, -0.07, float(yaw)), 0.02, pad=pad)
        ref = og._build_new_cube_obb2d(0.03, -0.07, 0.02, float(yaw), pad_xy=pad)
        for a, b in zip(got, ref):
            assert a.dtype == np.float64 and np.array_equal(a, b)
        _assert_not_degenerate(got)
        assert np.array_equal(got[2], np.array([0.02 + pad, 0.02 + pad]))


def test_exact_obb_from_spawn_pose_matches_analytic() -> None:
    """spawn_random_cube 建方块用的四元数（float32）→ 精确 OBB 与解析方块一致（到 float32 精度）。"""
    for yaw in np.linspace(0.0, 2 * math.pi, 361):
        q = og._yaw_to_quat_tensor(float(yaw), device="cpu")
        pose = Pose.create_from_pq(torch.tensor([[0.11, 0.05, 0.02]]), q)
        got = cube_obb2d_exact(pose, 0.02)
        ref = og._build_new_cube_obb2d(0.11, 0.05, 0.02, float(yaw))
        _assert_not_degenerate(got)
        assert np.allclose(got[0], ref[0], atol=1e-7)
        assert np.allclose(got[1], ref[1], atol=1e-6)  # 直立方块取体 x 轴，轴向本身也一致
        assert np.allclose(_corners(got), _corners(ref), atol=1e-6)
        # actor（带 .pose）与 sapien 风格（非 batch 的 p/q）输入给同一结果
        assert all(np.array_equal(a, b) for a, b in zip(got, cube_obb2d_exact(_FakeActor("c", pose), 0.02)))
        flat = SimpleNamespace(p=pose.p[0].numpy(), q=pose.q[0].numpy())
        assert all(np.array_equal(a, b) for a, b in zip(got, cube_obb2d_exact(flat, 0.02)))


@pytest.mark.parametrize("tilt", ["x90", "y90", "x90y90"])
def test_exact_obb_never_degenerates_for_any_resting_face(tilt) -> None:
    """竖直轴落在体 x／y 列（旧路径退化的情形）时，新函数仍给出与俯视正方形一致的 2D 障碍。"""
    base = {"x90": _ROT_X90, "y90": _ROT_Y90, "x90y90": _ROT_X90 @ _ROT_Y90}[tilt]
    rng = np.random.default_rng(0)
    for yaw in rng.uniform(-math.pi, math.pi, 200):
        R = _rot_z(float(yaw)) @ base
        pose = SimpleNamespace(p=np.array([-0.02, 0.09, 0.02]), q=_quat_wxyz_from_matrix(R))
        got = cube_obb2d_exact(pose, 0.02)
        _assert_not_degenerate(got)
        # 正方体任一面着地，俯视都是同一个正方形（只差 90° 的倍数）
        ref = og._build_new_cube_obb2d(-0.02, 0.09, 0.02, float(yaw))
        assert np.allclose(_corners(got), _corners(ref), atol=1e-6)


def test_old_trimesh_path_degenerates_where_exact_does_not() -> None:
    """复现计划 2.0① 的缺陷：竖直轴落在第 0 列时 _trimesh_box_to_obb2d 给出零长轴（线段）。"""
    R = _rot_z(0.4) @ _ROT_Y90  # 体 x 轴竖直
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = [0.0, 0.0, 0.02]
    box = SimpleNamespace(transform=T, extents=np.array([0.04, 0.04, 0.04]))
    _, A_old, _ = og._trimesh_box_to_obb2d(box)
    assert np.linalg.norm(A_old[:, 0]) < 1e-9  # 旧路径：退化
    pose = SimpleNamespace(p=T[:3, 3], q=_quat_wxyz_from_matrix(R))
    _assert_not_degenerate(cube_obb2d_exact(pose, 0.02))


def test_exact_obb_input_validation() -> None:
    with pytest.raises(ValueError):
        cube_obb2d_exact((0.0, 0.0), 0.02)
    with pytest.raises(ValueError):
        cube_obb2d_exact((0.0, 0.0, 0.0), 0.0)
    with pytest.raises(ValueError):
        cube_obb2d_exact((0.0, 0.0, 0.0), 0.02, pad=-0.01)


def test_exact_obb_is_recognized_as_premade_obstacle(fake_scene) -> None:
    """两个 spawn 函数的 avoid 已支持预制三元组（前两项 ndarray）；精确 OBB 放进去确实挡住候选。"""
    obstacle = cube_obb2d_exact((0.0, 0.0, 0.5), 0.05)
    assert isinstance(obstacle, tuple) and len(obstacle) == 3
    assert isinstance(obstacle[0], np.ndarray) and isinstance(obstacle[1], np.ndarray)
    for seed in range(30):
        env = _fake_env()
        gen = torch.Generator().manual_seed(seed)
        cube = og.spawn_random_cube(env, region_half_size=0.12, half_size=0.02, min_gap=0.01,
                                    avoid=[obstacle], generator=gen, max_trials=512)
        x, y, yaw = _cube_xy_yaw(cube)
        new = og._build_new_cube_obb2d(x, y, 0.02, yaw, pad_xy=0.01)
        assert not og._obb2d_intersect(*obstacle, *new)
        target = og.spawn_random_target(env, region_half_size=0.2, radius=0.03, min_gap=0.01,
                                        avoid=[obstacle], generator=gen, max_trials=512,
                                        include_existing=False)
        tx, ty = _target_xy(target)
        c, A, h = obstacle
        local = np.clip(A.T @ (np.array([tx, ty]) - c), -h, h)
        assert np.linalg.norm(np.array([tx, ty]) - (c + A @ local)) >= 0.04 - 1e-12


# ---------------------------------------------------------------------------
# 二、新参数默认值下逐位不变
# ---------------------------------------------------------------------------
def test_defaults_bitwise_identical_to_pre_change_golden(fake_scene) -> None:
    assert compute_digests() == GOLDEN


def _explicit_none(i, placed):
    return {"min_center_dist": None, "center_exclusion": None}


def _never_firing(i, placed):
    # d = 0 / R = 0 的规则永远不会拒绝：结果仍须逐位等于金标准，证明新判定本身不抽随机数
    return {"min_center_dist": (0.0, placed + [(0.0, 0.0)]), "center_exclusion": ((0.0, 0.0), 0.0)}


@pytest.mark.parametrize("extra", [_explicit_none, _never_firing], ids=["explicit_none", "never_firing"])
def test_new_params_inert_values_bitwise_identical(fake_scene, extra) -> None:
    for name in CUBE_SCENARIOS:
        texts = [_run_cube_scenario(name, s, extra)[0] for s in SEEDS]
        assert _digest(texts) == GOLDEN[f"cube.{name}"], name
    texts = [_run_target_scenario(s, extra)[0] for s in SEEDS]
    assert _digest(texts) == GOLDEN["target.purple"]


def test_only_min_center_dist_param_inert(fake_scene) -> None:
    for name in CUBE_SCENARIOS:
        texts = [_run_cube_scenario(name, s, lambda i, p: {"min_center_dist": None})[0] for s in SEEDS]
        assert _digest(texts) == GOLDEN[f"cube.{name}"]
        texts = [_run_cube_scenario(name, s, lambda i, p: {"center_exclusion": None})[0] for s in SEEDS]
        assert _digest(texts) == GOLDEN[f"cube.{name}"]


# ---------------------------------------------------------------------------
# 三、新参数开启时确实拒绝，且只改变 trial 次数
# ---------------------------------------------------------------------------
def test_cube_min_center_dist_rejects(fake_scene) -> None:
    changed = 0
    for seed in SEEDS:
        text, placed = _run_cube_scenario("yaw_uniform", seed, lambda i, p: {"min_center_dist": (0.1, p)})
        pts = np.array(placed)
        for a in range(len(pts)):
            for b in range(a):
                assert np.linalg.norm(pts[a] - pts[b]) >= 0.1
        changed += text != _run_cube_scenario("yaw_uniform", seed)[0]
    assert changed > 0


def test_cube_center_exclusion_rejects(fake_scene) -> None:
    changed = 0
    for seed in SEEDS:
        text, placed = _run_cube_scenario("no_yaw", seed, lambda i, p: {"center_exclusion": ((0.02, -0.01), 0.1)})
        for xy in placed:
            assert np.linalg.norm(np.array(xy) - np.array([0.02, -0.01])) >= 0.1
        changed += text != _run_cube_scenario("no_yaw", seed)[0]
    assert changed > 0


def test_target_rules_reject(fake_scene) -> None:
    changed = 0
    for seed in SEEDS:
        extra = lambda i, p: {"min_center_dist": (0.15, p), "center_exclusion": ((0.0, 0.0), 0.05)}  # noqa: E731
        text, placed = _run_target_scenario(seed, extra)
        pts = np.array(placed)
        for a in range(len(pts)):
            assert np.linalg.norm(pts[a]) >= 0.05
            for b in range(a):
                assert np.linalg.norm(pts[a] - pts[b]) >= 0.15
        changed += text != _run_target_scenario(seed)[0]
    assert changed > 0


def test_rules_consume_no_randomness_cube(fake_scene) -> None:
    """规则开启时被接受的，恰是「同一随机流里第一个满足规则的 trial」：拒绝不多抽也不少抽随机数。"""
    points = [(0.03, 0.02), (-0.05, -0.06)]
    zone = ((0.0, 0.0), 0.06)
    lo, hi = -0.1 + 0.02, 0.1 - 0.02
    for seed in range(60):
        ref = torch.Generator().manual_seed(seed)
        while True:
            u1, u2, u3 = (torch.rand(1, generator=ref).item() for _ in range(3))
            x, y, yaw = lo + u1 * (hi - lo), lo + u2 * (hi - lo), u3 * 2 * np.pi
            c = np.array([x, y])
            if min(np.linalg.norm(c - np.array(p)) for p in points) >= 0.07 and np.linalg.norm(c) >= 0.06:
                break
        gen = torch.Generator().manual_seed(seed)
        cube = og.spawn_random_cube(_fake_env(), region_half_size=0.1, half_size=0.02, generator=gen,
                                    max_trials=10_000, min_center_dist=(0.07, points), center_exclusion=zone)
        gx, gy, _ = _cube_xy_yaw(cube)
        assert (float(np.float32(x)), float(np.float32(y))) == (gx, gy)
        assert torch.equal(gen.get_state(), ref.get_state())


def test_rules_consume_no_randomness_target(fake_scene) -> None:
    lo, hi = -0.1 + 0.03, 0.1 - 0.03
    for seed in range(60):
        ref = torch.Generator().manual_seed(seed)
        while True:
            x = float(torch.rand(1, generator=ref).item() * (hi - lo) + lo)
            y = float(torch.rand(1, generator=ref).item() * (hi - lo) + lo)
            if math.hypot(x, y) >= 0.05:
                break
        gen = torch.Generator().manual_seed(seed)
        target = og.spawn_random_target(_fake_env(), region_half_size=0.1, radius=0.03, generator=gen,
                                        max_trials=10_000, include_existing=False,
                                        center_exclusion=((0.0, 0.0), 0.05))
        assert _target_xy(target) == (float(np.float32(x)), float(np.float32(y)))  # sapien.Pose 存 float32
        assert torch.equal(gen.get_state(), ref.get_state())


def test_rules_exhaust_budget_raises_runtime_error(fake_scene) -> None:
    gen = torch.Generator().manual_seed(0)
    with pytest.raises(RuntimeError):
        og.spawn_random_cube(_fake_env(), region_half_size=0.1, generator=gen, max_trials=50,
                             center_exclusion=((0.0, 0.0), 1.0))
    with pytest.raises(RuntimeError):
        og.spawn_random_target(_fake_env(), region_half_size=0.1, generator=gen, max_trials=50,
                               min_center_dist=(1.0, [(0.0, 0.0)]))


def test_rule_points_accept_premade_obstacles(fake_scene) -> None:
    obstacle = cube_obb2d_exact((0.04, 0.0, 0.3), 0.02)
    for seed in range(20):
        gen = torch.Generator().manual_seed(seed)
        cube = og.spawn_random_cube(_fake_env(), region_half_size=0.1, generator=gen, max_trials=2000,
                                    min_center_dist=(0.08, [obstacle]))
        x, y, _ = _cube_xy_yaw(cube)
        assert math.hypot(x - 0.04, y) >= 0.08 - 1e-6


@pytest.mark.parametrize("kwargs", [
    {"min_center_dist": 0.08},
    {"min_center_dist": (-0.1, [])},
    {"min_center_dist": (0.1, [(0.0, 0.0, 0.0)])},
    {"center_exclusion": (0.0, 0.05)},
    {"center_exclusion": ((0.0, 0.0), -1.0)},
    {"center_exclusion": ((0.0, 0.0), 0.05, 1)},
])
def test_rule_argument_validation(fake_scene, kwargs) -> None:
    gen = torch.Generator().manual_seed(0)
    with pytest.raises(ValueError):
        og.spawn_random_cube(_fake_env(), generator=gen, **kwargs)
    with pytest.raises(ValueError):
        og.spawn_random_target(_fake_env(), generator=gen, **kwargs)


# ---------------------------------------------------------------------------
# 四、N17：回放冻结值 / fixed_xy 注入按同一规则复核
# ---------------------------------------------------------------------------
class _ReplayRecorder:
    """回放模式替身：无论抽到什么都返回冻结值（与 SpecRecorder.value 回放语义相同）。"""

    def __init__(self, frozen):
        self.frozen = frozen

    def value(self, path, drawn, decision_key=None):
        return list(self.frozen)


def test_replay_violating_frozen_value_is_rejected(fake_scene) -> None:
    from robomme.robomme_env.utils.episode_spec import EpisodeSpecError

    zone = ((0.0, 0.0), 0.05)
    bad_cube = _ReplayRecorder([0.01, 0.0, 0.0])
    with pytest.raises(EpisodeSpecError):
        og.spawn_random_cube(_fake_env(), generator=torch.Generator().manual_seed(0), recorder=bad_cube,
                             spec_path="layout.demo.cube_pose", center_exclusion=zone)
    with pytest.raises(EpisodeSpecError):
        og.spawn_random_cube(_fake_env(), generator=torch.Generator().manual_seed(0), recorder=bad_cube,
                             spec_path="layout.cubes.1", min_center_dist=(0.08, [(0.05, 0.0)]))
    with pytest.raises(EpisodeSpecError):
        og.spawn_random_target(_fake_env(), generator=torch.Generator().manual_seed(0),
                               recorder=_ReplayRecorder([0.0, 0.02]), spec_path="layout.demo.goal_xy",
                               include_existing=False, center_exclusion=zone)
    with pytest.raises(EpisodeSpecError):
        og.spawn_random_cube(_fake_env(), fixed_xy=[0.0, 0.03], fixed_yaw=0.0, center_exclusion=zone)
    # 合规冻结值照常放行；不传规则时（原行为）不复核
    ok = og.spawn_random_cube(_fake_env(), generator=torch.Generator().manual_seed(0),
                              recorder=_ReplayRecorder([0.08, 0.0, 0.0]), spec_path="p", center_exclusion=zone)
    assert _cube_xy_yaw(ok)[:2] == (pytest.approx(0.08), 0.0)
    og.spawn_random_cube(_fake_env(), generator=torch.Generator().manual_seed(0), recorder=bad_cube, spec_path="p")
    og.spawn_random_cube(_fake_env(), fixed_xy=[0.0, 0.03], fixed_yaw=0.0)


# ---------------------------------------------------------------------------
# 五、L3：7 个被遮蔽模块
# ---------------------------------------------------------------------------
SHADOWED = ["VideoRepick", "SwingXtimes", "PatternLock", "RouteStick", "StopCube",
            "VideoUnmaskSwap", "ButtonUnmaskSwap"]


@pytest.mark.parametrize("name", SHADOWED)
def test_shadowed_module_selects_real_class_only_for_xhard(name) -> None:
    mod = importlib.import_module(f"robomme.robomme_env.{name}")
    # 遮蔽现状仍在（原三档依赖它保持 TypeError，H2）
    assert isinstance(mod.SceneGenerationError, types.ModuleType)
    assert mod._RealSceneGenerationError is SceneGenerationError
    real = mod._scene_gen_error("xhard")
    assert real is SceneGenerationError
    with pytest.raises(SceneGenerationError):
        raise real("xhard 场景生成失败")
    for difficulty in ("easy", "medium", "hard"):
        legacy = mod._scene_gen_error(difficulty)
        assert legacy is mod.SceneGenerationError
        with pytest.raises(TypeError):
            raise legacy("原三档仍是 TypeError")
        with pytest.raises(TypeError):
            try:
                raise RuntimeError("x")
            except legacy:
                pass


def test_no_other_env_module_is_shadowed() -> None:
    """自省：除 VideoPlaceOrder（K2 已修）与上面 7 个外，其余环境模块的名字仍是真类。"""
    shadowed = []
    for path in sorted(ENV_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        mod = importlib.import_module(f"robomme.robomme_env.{path.stem}")
        if isinstance(getattr(mod, "SceneGenerationError", None), types.ModuleType):
            shadowed.append(path.stem)
    assert sorted(shadowed) == sorted(SHADOWED + ["VideoPlaceOrder"])


def _func_source(module_name, func_name):
    tree = ast.parse((ENV_DIR / f"{module_name}.py").read_text(encoding="utf-8"))
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func_name]
    assert len(funcs) == 1, (module_name, func_name)
    return funcs[0]


@pytest.mark.parametrize("module_name,func_names", [
    ("VideoRepick", ["_load_cubes_xhard"]),
    ("SwingXtimes", ["_color_name_of", "_select_target_xhard", "_spawn_distractors_xhard"]),
])
def test_xhard_only_methods_use_real_class(module_name, func_names) -> None:
    for func_name in func_names:
        node = _func_source(module_name, func_name)
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        assert "SceneGenerationError" not in names, (module_name, func_name)


@pytest.mark.parametrize("module_name", ["VideoRepick", "SwingXtimes"])
def test_load_scene_outer_handler_selects_by_difficulty(module_name) -> None:
    node = _func_source(module_name, "_load_scene")
    outer = [n for n in node.body if isinstance(n, ast.Try)]
    assert outer, module_name
    handler_types = [ast.unparse(h.type) for h in outer[-1].handlers]
    assert handler_types == ["_scene_gen_error(self.difficulty)", "Exception"]
    reraise = [n for n in ast.walk(outer[-1].handlers[1]) if isinstance(n, ast.Raise)]
    assert ast.unparse(reraise[0].exc.func) == "_scene_gen_error(self.difficulty)"


class _PassSpec:
    def value(self, path, drawn, decision_key=None):
        return drawn

    def record(self, path, value):
        pass


def test_videorepick_xhard_raise_is_real_class(monkeypatch) -> None:
    mod = importlib.import_module("robomme.robomme_env.VideoRepick")

    def _fail(*args, **kwargs):
        raise RuntimeError("Region crowded")

    monkeypatch.setattr(mod, "spawn_random_cube", _fail)
    from robomme.robomme_env.utils.xhard import HSV_FLOOR_COLOR

    fake = SimpleNamespace(
        difficulty="xhard",
        generator=torch.Generator().manual_seed(0),
        _spec=_PassSpec(),
        cube_half_size=0.02,
        _sampling={
            "decision": {"xhard": {
                "layout": {"mode": "clutter", "cube_count": 6, "region_center": [-0.1, 0.0],
                           "region_half_size": [0.2, 0.25]},
                "block_color": HSV_FLOOR_COLOR,
            }},
            "positions": {"hard_cubes": {"random_yaw": True, "include_existing": True, "include_goal": True}},
        },
    )
    with pytest.raises(SceneGenerationError, match="failed to generate bin_0"):
        mod.VideoRepick._load_cubes_xhard(fake, [])


def test_swingxtimes_xhard_raise_is_real_class() -> None:
    mod = importlib.import_module("robomme.robomme_env.SwingXtimes")
    fake = SimpleNamespace(_cube_color_of=[])
    with pytest.raises(SceneGenerationError, match="颜色登记表"):
        mod.SwingXtimes._color_name_of(fake, object())
