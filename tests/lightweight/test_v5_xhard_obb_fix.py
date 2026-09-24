#!/usr/bin/env python3
"""轻量测试：V5 S3i——PickHighlight / VideoPlaceButton / VideoPlaceOrder 的 xhard 障碍框修复（计划 2.16、L2 b）。

背景（计划 2.0①）：已放方块以 actor 形式进 ``avoid`` 时，``_trimesh_box_to_obb2d`` 对正方体的轴序任意，
竖直轴落进前两列就退化成一条线段，``min_gap`` 在其法向失效。V5 在这三个环境的 xhard 分支里改把
``cube_obb2d_exact(cube.initial_pose, cube_half_size)`` 预制三元组放进 ``avoid``；原三档仍放 actor。

纯 CPU、不起 sapien 场景：用假 ``self``（SimpleNamespace）直接调环境类的 ``_load_scene``，
``TableSceneBuilder`` / ``build_button`` / 方块与圆盘 builder 换成只记位姿的替身（按钮替身与真
``build_button`` 抽同样的随机数、返回同一个按钮 OBB，因此布局与真 reset 同一随机流），
``spawn_random_cube`` / ``spawn_random_target`` 包一层探针记下每次调用的 ``avoid`` 与 ``min_gap``。

* 多 seed xhard：已放物体两两（后放者对先放者）实际间距 ≥ 名义 ``min_gap``（violations=0），
  传入 spawn 的障碍里方块一律是非退化的精确三元组（退化数 = 0、方块 actor 数 = 0）；
* 原三档：方块仍以 actor 进 ``avoid``（路径未改），源码里 xhard 分支与原三档分支的静态自查。

    uv run --no-sync python -m pytest tests/lightweight/test_v5_xhard_obb_fix.py -q
"""

from __future__ import annotations

import ast
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


from robomme.robomme_env.utils import object_generation as og  # noqa: E402
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402
from robomme.robomme_env.utils.episode_spec import SpecRecorder  # noqa: E402

ENV_DIR = REPO_ROOT / "src" / "robomme" / "robomme_env"
ENV_NAMES = ("PickHighlight", "VideoPlaceButton", "VideoPlaceOrder")
CUBE_HALF = 0.02  # PICK_CUBE_CONFIGS["panda"]["cube_half_size"]
# 真实布局用 float32 位姿建物体，拒绝循环里判的是 float64 候选值；容差吸收这一层舍入
GAP_TOL = 1e-6
N_SEEDS = 60


# ---------------------------------------------------------------------------
# 假场景
# ---------------------------------------------------------------------------
class _FakeActor:
    def __init__(self, name, initial_pose):
        self.name = name
        self.initial_pose = initial_pose
        self.pose = initial_pose


def _fake_build_cube(scene, half_size, color, name, initial_pose):
    actor = _FakeActor(name, initial_pose)
    actor._fake_kind = "cube"
    return actor


def _fake_build_target(scene, radius, thickness, name, body_type, add_collision, initial_pose):
    actor = _FakeActor(name, initial_pose)
    actor._fake_kind = "target"
    return actor


def _fake_build_button(self, center_xy=(0.15, 0.10), base_half=(0.025, 0.025, 0.005), scale=None,
                       generator=None, randomize=True, randomize_range=(0.1, 0.4),
                       recorder=None, spec_path=None, **_ignored):
    """与真 ``build_button`` 同样的随机数消费与返回值（不建 articulation）。"""
    scale = float(scale if scale is not None else 1.0)
    base_half = [bh * scale for bh in base_half]
    cx, cy = float(center_xy[0]), float(center_xy[1])
    if randomize:
        range_x, range_y = float(randomize_range[0]), float(randomize_range[1])
        offset = torch.rand(2, generator=generator) - 0.5
        cx += float(offset[0]) * range_x
        cy += float(offset[1]) * range_y
    if recorder is not None and spec_path is not None:
        cx, cy = recorder.value(spec_path, [cx, cy])
    self.button = object()
    self.cap_link = [object()]
    return og.create_button_obb(center_xy=(cx, cy), half_size=max(base_half[0], base_half[1]) * 1.5)


class _FakeTableSceneBuilder:
    def __init__(self, env, robot_init_qpos_noise=0):
        pass

    def build(self):
        pass


class _Probe:
    """包住 spawn_random_cube / spawn_random_target：记下每次调用的 avoid 快照、min_gap 与返回物体。"""

    def __init__(self):
        self.calls = []

    def wrap(self, kind, real):
        def spy(env, *args, **kwargs):
            avoid = kwargs.get("avoid")
            snapshot = list(avoid) if avoid else []
            obj = real(env, *args, **kwargs)
            self.calls.append({"kind": kind, "avoid": snapshot, "min_gap": float(kwargs["min_gap"]),
                               "radius": kwargs.get("radius"), "obj": obj})
            return obj
        return spy


@pytest.fixture
def fake_scene(monkeypatch):
    monkeypatch.setattr(og.actors, "build_cube", _fake_build_cube)
    for name in ("build_purple_white_target", "build_gray_white_target",
                 "build_green_white_target", "build_red_white_target"):
        monkeypatch.setattr(og, name, _fake_build_target)
    return monkeypatch


def _env_module(env_name):
    return importlib.import_module(f"robomme.robomme_env.{env_name}")


def _fake_self(env_name, difficulty, seed):
    module = _env_module(env_name)
    cls = getattr(module, env_name)
    fake = SimpleNamespace(
        _sampling=module._resolve_sampling_config(cls, None),
        _spec=SpecRecorder(None, env_name, {"seed": seed}, difficulty=difficulty),
        seed=seed,
        difficulty=difficulty,
        cube_half_size=CUBE_HALF,
        robot_init_qpos_noise=0,
        robomme_failure_recovery=False,
        robomme_failure_recovery_mode=None,
        device="cpu",
        scene=None,
        generator=torch.Generator().manual_seed(seed),
    )
    for method in ("_xhard_spec_kwargs",):
        if hasattr(cls, method):
            setattr(fake, method, types.MethodType(getattr(cls, method), fake))
    # xhard 尾段（选目标、演示模板、放回原位落点）与本修复无关，且要真 scene；这里置空
    fake._load_scene_xhard_tail = lambda *args, **kwargs: None
    return cls, fake


def _run_layout(env_name, difficulty, seed, monkeypatch):
    """跑一次 ``_load_scene``，返回 (probe, 异常或 None)。"""
    module = _env_module(env_name)
    probe = _Probe()
    monkeypatch.setattr(module, "TableSceneBuilder", _FakeTableSceneBuilder)
    monkeypatch.setattr(module, "build_button", _fake_build_button)
    monkeypatch.setattr(module, "spawn_random_cube", probe.wrap("cube", og.spawn_random_cube))
    monkeypatch.setattr(module, "spawn_random_target", probe.wrap("target", og.spawn_random_target))
    cls, fake = _fake_self(env_name, difficulty, seed)
    try:
        cls._load_scene(fake, {})
    except SceneGenerationError as exc:
        return probe, exc
    except Exception as exc:  # noqa: BLE001
        if difficulty == "xhard":
            raise
        # 原三档：布局之后的代码（如 PickHighlight 原三档当场求值的 is_any_obj_pickup、
        # VideoPlaceOrder 被遮蔽的 except 子句）要真 scene，替身下会抛错；布局已由探针记下，
        # 本文件只看布局阶段，这里放行
        return probe, exc
    return probe, None


# ---------------------------------------------------------------------------
# 几何：正方形 / 圆盘的实际间距
# ---------------------------------------------------------------------------
def _cube_xy_yaw(actor):
    p = actor.initial_pose.p[0].tolist()
    w, _, _, z = actor.initial_pose.q[0].tolist()
    return p[0], p[1], 2.0 * math.atan2(z, w)


def _square_corners(x, y, yaw, half):
    c, s = math.cos(yaw), math.sin(yaw)
    ax, ay = np.array([c, s]), np.array([-s, c])
    center = np.array([x, y])
    return [center + half * (i * ax + j * ay) for i, j in ((1, 1), (-1, 1), (-1, -1), (1, -1))]


def _point_segment_dist(p, a, b):
    ab = b - a
    t = float(np.clip(np.dot(p - a, ab) / np.dot(ab, ab), 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * ab)))


def _square_square_gap(sq1, sq2):
    """两个正方形（各为 (x, y, yaw)）的欧氏间距；相交返回 0。"""
    c1, a1, h1 = og._build_new_cube_obb2d(*sq1[:2], CUBE_HALF, sq1[2])
    c2, a2, h2 = og._build_new_cube_obb2d(*sq2[:2], CUBE_HALF, sq2[2])
    if og._obb2d_intersect(c1, a1, h1, c2, a2, h2):
        return 0.0
    p1 = _square_corners(*sq1, CUBE_HALF)
    p2 = _square_corners(*sq2, CUBE_HALF)
    best = math.inf
    for pts, other in ((p1, p2), (p2, p1)):
        for p in pts:
            for k in range(4):
                best = min(best, _point_segment_dist(p, other[k], other[(k + 1) % 4]))
    return best


def _square_disk_gap(sq, disk_xy, radius):
    c, a, h = og._build_new_cube_obb2d(*sq[:2], CUBE_HALF, sq[2])
    local = a.T @ (np.asarray(disk_xy, dtype=np.float64) - c)
    closest = c + a @ np.clip(local, -h, h)
    return float(np.linalg.norm(np.asarray(disk_xy) - closest)) - float(radius)


def _is_exact_triple(entry):
    return (isinstance(entry, tuple) and len(entry) == 3
            and isinstance(entry[0], np.ndarray) and isinstance(entry[1], np.ndarray))


def _triple_is_degenerate(entry):
    _c, a, h = entry
    cols_unit = np.allclose(np.linalg.norm(a, axis=0), 1.0, atol=1e-9)
    orthogonal = abs(float(np.dot(a[:, 0], a[:, 1]))) < 1e-9
    return not (cols_unit and orthogonal and np.all(np.asarray(h) > 0))


def _layout_stats(probe):
    """后放物体对先放方块的名义间距违例数、最小裕量，以及 spawn 收到的方块障碍分类计数。"""
    placed_cubes = []  # (x, y, yaw)
    violations = 0
    min_margin = math.inf
    n_pairs = 0
    exact = degenerate = cube_actor = 0
    for call in probe.calls:
        for entry in call["avoid"]:
            if _is_exact_triple(entry):
                exact += 1
                degenerate += int(_triple_is_degenerate(entry))
            elif getattr(entry, "_fake_kind", None) == "cube":
                cube_actor += 1
        obj = call["obj"]
        if call["kind"] == "cube":
            sq = _cube_xy_yaw(obj)
            for prev in placed_cubes:
                gap = _square_square_gap(prev, sq)
                n_pairs += 1
                min_margin = min(min_margin, gap - call["min_gap"])
                violations += int(gap < call["min_gap"] - GAP_TOL)
            placed_cubes.append(sq)
        else:
            xy = np.asarray(obj.pose.p, dtype=np.float64)[:2]
            for prev in placed_cubes:
                gap = _square_disk_gap(prev, xy, call["radius"])
                n_pairs += 1
                min_margin = min(min_margin, gap - call["min_gap"])
                violations += int(gap < call["min_gap"] - GAP_TOL)
    return {"violations": violations, "min_margin": min_margin, "pairs": n_pairs,
            "exact": exact, "degenerate": degenerate, "cube_actor": cube_actor,
            "n_cubes": len(placed_cubes)}


# ---------------------------------------------------------------------------
# xhard：名义间距真正生效
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("env_name", ENV_NAMES)
def test_xhard已放方块间距不小于名义min_gap且障碍无退化(env_name, fake_scene) -> None:
    totals = {"violations": 0, "pairs": 0, "exact": 0, "degenerate": 0, "cube_actor": 0}
    min_margin = math.inf
    ok = failed = 0
    for seed in range(N_SEEDS):
        probe, exc = _run_layout(env_name, "xhard", 5_000_000 + seed, fake_scene)
        stats = _layout_stats(probe)
        for key in totals:
            totals[key] += stats[key]
        min_margin = min(min_margin, stats["min_margin"])
        if exc is None:
            ok += 1
        else:
            failed += 1
    print(f"V5_XHARD_OBB_FIX env={env_name} seeds={N_SEEDS} ok={ok} scenegen_fail={failed} "
          f"pairs={totals['pairs']} violations={totals['violations']} min_margin={min_margin:.6f} "
          f"exact_obstacles={totals['exact']} degenerate={totals['degenerate']} cube_actor={totals['cube_actor']}")
    assert ok > 0
    assert totals["pairs"] > 0
    assert totals["violations"] == 0
    assert min_margin >= -GAP_TOL
    assert totals["degenerate"] == 0
    # xhard 下已放方块不再以 actor 形式进 avoid（旧的会退化的路径一次都不走）
    assert totals["cube_actor"] == 0
    # 方块确实以精确三元组进了 avoid（除按钮 OBB 外还有方块的）
    assert totals["exact"] > N_SEEDS


def test_精确三元组与方块初始位姿一致(fake_scene) -> None:
    """xhard 下 avoid 里第 k 块方块的三元组 == 由其 initial_pose 解析算出的正方形（不含 pad）。"""
    probe, exc = _run_layout("PickHighlight", "xhard", 5_000_123, fake_scene)
    assert exc is None
    cubes = [call["obj"] for call in probe.calls if call["kind"] == "cube"]
    last_avoid = probe.calls[-1]["avoid"]
    cube_triples = [entry for entry in last_avoid[1:]]  # 第 0 个是按钮 OBB
    assert len(cube_triples) == len(cubes) - 1
    for cube, (c, a, h) in zip(cubes, cube_triples):
        x, y, yaw = _cube_xy_yaw(cube)
        c_ref, a_ref, h_ref = og._build_new_cube_obb2d(x, y, CUBE_HALF, yaw)
        assert np.allclose(c, c_ref, atol=1e-7)
        assert np.allclose(np.abs(a.T @ a_ref), np.eye(2), atol=1e-6) or np.allclose(
            np.abs(a.T @ a_ref), np.eye(2)[::-1], atol=1e-6)
        assert np.allclose(h, h_ref, atol=0)


# ---------------------------------------------------------------------------
# 原三档：路径未改
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("env_name", ENV_NAMES)
@pytest.mark.parametrize("difficulty", ("easy", "medium", "hard"))
def test_原三档方块仍以actor进avoid(env_name, difficulty, fake_scene) -> None:
    saw_actor = False
    for seed in range(5):
        probe, exc = _run_layout(env_name, difficulty, 6_000_000 + seed, fake_scene)
        # 布局阶段完整跑完：方块数 = 本档方块数（PickHighlight 原三档允许静默截断，至少 1 块）
        assert any(call["kind"] == "cube" for call in probe.calls)
        for call in probe.calls:
            for entry in call["avoid"]:
                # 原三档：方块从不以预制三元组进 avoid（三元组只可能是按钮 OBB）
                if _is_exact_triple(entry):
                    assert np.allclose(entry[1], np.eye(2))
                if getattr(entry, "_fake_kind", None) == "cube":
                    saw_actor = True
    # 各档至少有一块方块会作为后续方块或圆盘的障碍，且仍是 actor（旧路径，逐字未改）
    assert saw_actor


def _load_scene_source(env_name):
    tree = ast.parse((ENV_DIR / f"{env_name}.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == env_name)
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_load_scene")


def _is_xhard_test(test):
    src = ast.unparse(test)
    return src in ("xhard", "self.difficulty == 'xhard'")


@pytest.mark.parametrize("env_name", ENV_NAMES)
def test_静态自查_精确OBB只在xhard分支且spawn调用逐字不动(env_name) -> None:
    func = _load_scene_source(env_name)
    exact_calls = []
    for node in ast.walk(func):
        if isinstance(node, ast.If) and _is_xhard_test(node.test):
            body_src = "\n".join(ast.unparse(s) for s in node.body)
            else_src = "\n".join(ast.unparse(s) for s in node.orelse)
            if "cube_obb2d_exact" in body_src:
                exact_calls.append(node)
                # xhard 分支：精确三元组；else（原三档）：原来的 avoid.append(cube) 一字不差
                assert body_src == "avoid.append(cube_obb2d_exact(cube.initial_pose, self.cube_half_size))"
                assert else_src == "avoid.append(cube)"
    assert len(exact_calls) == 1
    # _load_scene 里不再有未受守卫的 avoid.append(cube)
    guarded = {id(s) for n in exact_calls for s in n.orelse}
    bare = [n for n in ast.walk(func) if isinstance(n, ast.Expr)
            and ast.unparse(n) == "avoid.append(cube)" and id(n) not in guarded]
    assert bare == []
    # spawn 调用本身未改：不传 V5 新参数，include_existing 仍为 False
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and ast.unparse(node.func) in ("spawn_random_cube", "spawn_random_target"):
            names = {kw.arg for kw in node.keywords}
            assert "min_center_dist" not in names and "center_exclusion" not in names
            inc = next(kw for kw in node.keywords if kw.arg == "include_existing")
            assert ast.unparse(inc.value) == "False"
