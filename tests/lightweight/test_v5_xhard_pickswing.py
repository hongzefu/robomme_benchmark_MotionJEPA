#!/usr/bin/env python3
"""轻量测试：V5 S3f PickXtimes / SwingXtimes 的 xhard 去扎堆（NEWTASK_RELEASE_V5_PLAN 2.13 / 2.14，L43～L46）。

纯 CPU、不起 sapien 场景：用假 actor 顶替 ``actors.build_cube`` 与圆盘 builder、用 trimesh 盒子顶替
``get_actor_obb``（与 P1 探针离线副本同一写法，该副本对 v4-01 冻结规格逐位一致 20/20），直接调用
两个环境**真实的** ``_load_scene``，量的是仓库代码本身而不是复刻：

* 决策值：Pick 删 ``corner_bias``、方块与干扰区半宽 0.25、圆盘区不变、``min_center_dist_m`` 0.08、
  每块预算 1024；Swing 新增 ``min_center_dist_m`` 0.08；
* ``V5_EXACT_OBB``：xhard 下传给 ``spawn_random_cube`` / ``spawn_random_target`` 的 ``avoid`` 里不再有
  方块 actor（旧路径约 2/3 姿态退化成线段），全部是 ``cube_obb2d_exact`` 预制三元组，且 ``include_existing``
  恒为 False；6 块两两之间满足 ``min_gap`` 的精确 OBB 分离；
* ``V5_PICK_DISPERSION`` / ``V5_SWING_SPACING``：多 seed 下 6 块两两中心距 < 0.08 的比例为 0；
* ``V5_RESET_FEASIBILITY``：离线 reset 失败率（Pick ≤ 0.015、Swing ≤ 0.040，计划估 ≈1% / ≈3.6%），
  失败一律是真 ``SceneGenerationError``；
* N17：回放冻结规格时违反 8 cm 规则即报错；
* 原三档：``_spawn_scene_objects_native`` 与 Swing 共用循环的非 xhard 一支 AST 与改动前逐字相同，
  离线跑出的规格与改动前代码的金标准哈希相同。

    uv run --no-sync python -m pytest tests/lightweight/test_v5_xhard_pickswing.py -q -s
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
import sapien
import torch
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from mani_skill.envs.tasks.tabletop.pick_cube_cfgs import PICK_CUBE_CONFIGS  # noqa: E402
from mani_skill.utils.structs.pose import Pose  # noqa: E402

from robomme.robomme_env.utils import object_generation as og  # noqa: E402
from robomme.robomme_env.utils.episode_spec import EpisodeSpecError, SpecRecorder  # noqa: E402
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402
from robomme.robomme_env.utils.xhard import cube_obb2d_exact  # noqa: E402

PICK = importlib.import_module("robomme.robomme_env.PickXtimes")
SWING = importlib.import_module("robomme.robomme_env.SwingXtimes")
ENV_DIR = REPO_ROOT / "src" / "robomme" / "robomme_env"
MODULES = {"PickXtimes": PICK, "SwingXtimes": SWING}

MIN_CENTER_DIST = 0.08
# 方块位姿以 float32 存进 actor（Pose.create_from_pq），参考点取自 actor 位姿，候选中心是 float64；
# 两两距离按 actor 位姿复算时允许 float32 舍入量级的误差。
FLOAT32_TOL = 1e-6


# ---------------------------------------------------------------------------
# 离线场景：顶替 sapien 建物体，其余全部走仓库真实代码
# ---------------------------------------------------------------------------
class _FakeActor:
    def __init__(self, name, pose, half=None):
        self.name = name
        self.pose = pose
        if half is not None:
            self._fake_half = float(half)


def _fake_build_cube(scene, half_size, color, name, initial_pose):
    return _FakeActor(name, initial_pose, half=half_size)


def _fake_build_target(scene, radius, thickness, name, body_type, add_collision, initial_pose):
    # 真实圆盘 actor 的位姿是带 batch 维的 float32 Pose（SwingXtimes 读 pose.p[0, 1]）
    pose = Pose.create_from_pq(
        torch.tensor([list(initial_pose.p)], dtype=torch.float32),
        torch.tensor([list(initial_pose.q)], dtype=torch.float32),
    )
    return _FakeActor(name, pose)


def _fake_get_actor_obb(actor, to_world_frame=True, vis=False):
    """方块：与真实 get_actor_obb 同一条 trimesh 路径（float32 位姿 → box → bounding_box_oriented）；
    圆盘等无碰撞体的 actor：与真实一样取不到网格而抛错（spawn 函数静默忽略）。"""
    half = getattr(actor, "_fake_half", None)
    if half is None:
        raise AssertionError(f"can not get actor mesh for {actor}")
    p = actor.pose.p[0].detach().cpu().numpy().astype(np.float32)
    q = actor.pose.q[0].detach().cpu().numpy().astype(np.float32)
    mesh = trimesh.creation.box(extents=2 * np.array([half, half, half], dtype=np.float32))
    mesh.apply_transform(sapien.Pose(p=p, q=q).to_transformation_matrix())
    return mesh.bounding_box_oriented


class _FakeTableSceneBuilder:
    def __init__(self, env, robot_init_qpos_noise=0):
        pass

    def build(self):
        pass


def _fake_build_button(self, center_xy=(0.15, 0.10), base_half=(0.025, 0.025, 0.005), scale=None,
                       generator=None, randomize=True, randomize_range=(0.1, 0.4),
                       recorder=None, spec_path=None, **_ignored):
    """逐字复刻 build_button 的取值部分（rand(2) → 平移 → recorder.value → 按钮 OBB），不建关节体。"""
    scale = float(scale if scale is not None else 1.0)
    base_half = [bh * scale for bh in base_half]
    cx, cy = float(center_xy[0]), float(center_xy[1])
    if randomize:
        offset = torch.rand(2, generator=generator) - 0.5
        cx += float(offset[0]) * float(randomize_range[0])
        cy += float(offset[1]) * float(randomize_range[1])
    if recorder is not None and spec_path is not None:
        cx, cy = recorder.value(spec_path, [cx, cy])
    self.button = _FakeActor("button", None)
    self.cap_link = [_FakeActor("button_cap", None)]
    return og.create_button_obb(center_xy=(cx, cy), half_size=max(base_half[0], base_half[1]) * 1.5)


class OfflineScene:
    """上下文管理器：装上/卸下假场景（不依赖 pytest monkeypatch，离线统计脚本也能复用）。"""

    def __enter__(self):
        self._saved = []
        patches = [
            (og.actors, "build_cube", _fake_build_cube),
            (og, "build_purple_white_target", _fake_build_target),
            (og, "build_gray_white_target", _fake_build_target),
            (og, "get_actor_obb", _fake_get_actor_obb),
        ]
        for mod in MODULES.values():
            patches += [(mod, "TableSceneBuilder", _FakeTableSceneBuilder), (mod, "build_button", _fake_build_button)]
        for obj, name, value in patches:
            self._saved.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)
        return self

    def __exit__(self, *exc):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)
        return False


def _offline_env(task, seed, difficulty, spec=None, sampling_config=None):
    """不经 __init__ 造一个只够 _load_scene 用的实例；__init__ 里的取值（num_repeats）按原写法复刻。"""
    mod = MODULES[task]
    cls = getattr(mod, task)
    env = object.__new__(cls)
    env._sampling = mod._resolve_sampling_config(cls, sampling_config)
    env._spec = SpecRecorder(spec, task, {"seed": seed}, difficulty=difficulty)
    env._native_init_index = -1
    env.seed = seed
    env.difficulty = difficulty
    env.robot_init_qpos_noise = 0
    env.cube_half_size = PICK_CUBE_CONFIGS["panda"]["cube_half_size"]
    env.device = torch.device("cpu")
    env.scene = None
    env.robomme_failure_recovery = False
    env.robomme_failure_recovery_mode = None
    generator = torch.Generator()
    generator.manual_seed(seed)
    number_range = env._sampling["decision"]["number_range"][difficulty]
    env.num_repeats = env._spec.value(
        "objects.num_repeats",
        torch.randint(number_range[0], number_range[1] + 1, (1,), generator=generator).item(),
        decision_key=f"number_range.{difficulty}",
    )
    env._spec.identity.setdefault("difficulty", difficulty)
    return env


def run_offline(task, seed, difficulty="xhard", spec=None, sampling_config=None):
    """跑一次真实 ``_load_scene``（须在 OfflineScene 内调用）；返回 env（其 ``_spec.to_dict()`` 即本局规格）。"""
    env = _offline_env(task, seed, difficulty, spec=spec, sampling_config=sampling_config)
    getattr(MODULES[task], task)._load_scene(env, {})
    return env


def _actor_xy(actor):
    return actor.pose.p[0, :2].detach().cpu().numpy().astype(np.float64)


def placed_cube_xys(env):
    """6 块（有色 + 干扰）的中心 xy（取自 actor 位姿）。"""
    return [_actor_xy(cube) for cube in env.all_cubes]


def min_pair_distance(xys):
    return min(float(np.linalg.norm(a - b)) for a, b in itertools.combinations(xys, 2))


def goal_distance_from_base(env):
    """目标圆盘中心离机器人基座（x = -0.615, y = 0）的水平距离。"""
    xy = _actor_xy(env.target)
    return float(math.hypot(xy[0] + 0.615, xy[1]))


class AvoidAudit:
    """包住环境模块里的 spawn_random_cube / spawn_random_target，记录每次调用的 avoid 与关键参数。"""

    def __init__(self, mod):
        self.mod = mod
        self.calls = []

    def __enter__(self):
        self._cube, self._target = self.mod.spawn_random_cube, self.mod.spawn_random_target

        def cube(*args, **kwargs):
            self.calls.append(("cube", kwargs))
            return self._cube(*args, **kwargs)

        def target(*args, **kwargs):
            self.calls.append(("target", kwargs))
            return self._target(*args, **kwargs)

        self.mod.spawn_random_cube, self.mod.spawn_random_target = cube, target
        return self

    def __exit__(self, *exc):
        self.mod.spawn_random_cube, self.mod.spawn_random_target = self._cube, self._target
        return False


def _is_premade(item):
    return isinstance(item, tuple) and len(item) == 3 and isinstance(item[0], np.ndarray) \
        and isinstance(item[1], np.ndarray)


def sweep(task, seeds):
    """多 seed 离线 reset：返回每局结果（成功局附 6 块 xy、目标距离、avoid 审计；失败局附异常）。"""
    rows = []
    with OfflineScene():
        for seed in seeds:
            with AvoidAudit(MODULES[task]) as audit:
                try:
                    env = run_offline(task, seed)
                except Exception as exc:  # noqa: BLE001 — 失败类别本身就是被测对象
                    rows.append({"seed": seed, "ok": False, "exc": exc})
                    continue
            rows.append({"seed": seed, "ok": True, "env": env, "xys": placed_cube_xys(env),
                         "calls": audit.calls})
    return rows


# ---------------------------------------------------------------------------
# 决策值
# ---------------------------------------------------------------------------
def test_pick_xhard_decision_v5() -> None:
    decision, _ = PICK.native_blocks(PICK.PickXtimes)
    xhard = decision["xhard"]
    assert set(xhard) == {"target_cube_position_policy", "goal_position_policy", "distractor", "min_center_dist_m"}
    # L43 (c)：删 corner_bias 键，全部均匀
    assert xhard["target_cube_position_policy"] == {"region_center": [-0.1, 0], "region_half_size": 0.25}
    # L46：干扰区同为 0.25；圆盘区不变
    assert xhard["distractor"]["region_half_size"] == 0.25
    assert xhard["distractor"]["region_center"] == [-0.1, 0]
    assert xhard["goal_position_policy"] == {"region_center": [-0.1, 0], "region_half_size": 0.2}
    assert xhard["min_center_dist_m"] == MIN_CENTER_DIST  # L44
    assert PICK.XHARD_CUBE_MAX_TRIALS == 1024  # L45


def test_swing_xhard_decision_v5() -> None:
    decision, _ = SWING.native_blocks(SWING.SwingXtimes)
    assert set(decision["xhard"]) == {"distractor", "min_center_dist_m"}
    assert decision["xhard"]["min_center_dist_m"] == MIN_CENTER_DIST
    assert "corner_bias" not in json.dumps(decision)


def test_pick_source_has_no_corner_bias_argument() -> None:
    tree = ast.parse((ENV_DIR / "PickXtimes.py").read_text(encoding="utf-8"))
    kwargs = [kw.arg for node in ast.walk(tree) if isinstance(node, ast.Call) for kw in node.keywords]
    assert "corner_bias" not in kwargs
    assert "cube_corner_bias" not in (ENV_DIR / "PickXtimes.py").read_text(encoding="utf-8")


def _func(module_name, func_name):
    tree = ast.parse((ENV_DIR / f"{module_name}.py").read_text(encoding="utf-8"))
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func_name]
    assert len(funcs) == 1, (module_name, func_name)
    return funcs[0]


def test_swing_new_xhard_methods_use_real_class() -> None:
    for name in ("_spawn_colored_cubes_xhard", "_append_cube_obstacle_xhard"):
        names = {n.id for n in ast.walk(_func("SwingXtimes", name)) if isinstance(n, ast.Name)}
        assert "SceneGenerationError" not in names, name


# ---------------------------------------------------------------------------
# 原三档：代码与离线取值都与改动前（12.120）逐字相同
# ---------------------------------------------------------------------------
# ast.dump 的 SHA-256，由改动前代码（328e607）算出
NATIVE_AST_GOLDEN = {
    "PickXtimes._spawn_scene_objects_native": "510110dfebc2679443ed6f27a9811a9fdd7ba1358ee8648b1aaacb1ff74ed6fa",
    "SwingXtimes._load_scene.colored_loop": "b8f6cc3ce3b41b641a5cc21075837238d02ac59fff23ce45af98acba6214d1f6",
}


def _swing_native_loop_dump():
    """SwingXtimes._load_scene 里「# Generate cubes for each color group」那段 for 循环（原三档一支）。"""
    node = _func("SwingXtimes", "_load_scene")
    loops = [n for n in ast.walk(node) if isinstance(n, ast.For)
             and ast.unparse(n.iter) == "enumerate(color_groups)"]
    assert len(loops) == 1
    return ast.dump(loops[0])


def test_native_code_ast_unchanged() -> None:
    pick = hashlib.sha256(ast.dump(_func("PickXtimes", "_spawn_scene_objects_native")).encode()).hexdigest()
    swing = hashlib.sha256(_swing_native_loop_dump().encode()).hexdigest()
    assert pick == NATIVE_AST_GOLDEN["PickXtimes._spawn_scene_objects_native"]
    assert swing == NATIVE_AST_GOLDEN["SwingXtimes._load_scene.colored_loop"]


def test_swing_loop_branch_is_explicit() -> None:
    """Swing 共用循环外面包了显式 difficulty 分支：xhard 走新方法，原循环只在 else 一支。"""
    node = _func("SwingXtimes", "_load_scene")
    branches = [n for n in ast.walk(node) if isinstance(n, ast.If)
                and ast.unparse(n.test) == "self.difficulty == 'xhard'"
                and any(isinstance(s, ast.Expr) and "_spawn_colored_cubes_xhard" in ast.unparse(s) for s in n.body)]
    assert len(branches) == 1
    orelse = branches[0].orelse
    assert len(orelse) == 1 and isinstance(orelse[0], ast.For)
    assert ast.dump(orelse[0]) == _swing_native_loop_dump()


NATIVE_SEEDS = [11, 12, 1234, 4100300, 4300300, 99991]
# 离线规格的 SHA-256（按 task/difficulty 逐 seed 拼接），由改动前代码（328e607）在同一离线场景下算出
NATIVE_SPEC_GOLDEN = "7e24d596ed3d00cb79768cfe3b40c34cab1066adefc7cde40037cc3455617d65"


def native_spec_digest():
    digest = hashlib.sha256()
    with OfflineScene():
        for task in ("PickXtimes", "SwingXtimes"):
            for difficulty in ("easy", "medium", "hard"):
                for seed in NATIVE_SEEDS:
                    try:
                        doc = run_offline(task, seed, difficulty)._spec.to_dict()
                        text = json.dumps(doc, sort_keys=True, ensure_ascii=False)
                    except Exception as exc:  # noqa: BLE001 — 原三档的失败形态也在锁定范围内
                        text = f"FAIL {type(exc).__name__}"
                    digest.update(f"{task}|{difficulty}|{seed}|{text}\n".encode())
    return digest.hexdigest()


def test_native_tiers_offline_specs_unchanged() -> None:
    assert native_spec_digest() == NATIVE_SPEC_GOLDEN


# ---------------------------------------------------------------------------
# xhard：精确 OBB、6 块间距、reset 失败率
# ---------------------------------------------------------------------------
SWEEP_SEEDS = list(range(5_000_000, 5_000_400))


@pytest.fixture(scope="module")
def pick_rows():
    return sweep("PickXtimes", SWEEP_SEEDS)


@pytest.fixture(scope="module")
def swing_rows():
    return sweep("SwingXtimes", SWEEP_SEEDS)


def _exact_obb_audit(rows, half):
    """统计 xhard 各次 spawn 调用 avoid 里的方块 actor（旧退化路径）与预制三元组的轴是否正交单位。"""
    actor_cubes = include_existing = premade = bad_axes = 0
    for row in rows:
        if not row["ok"]:
            continue
        for _, kwargs in row["calls"]:
            include_existing += bool(kwargs.get("include_existing", True))
            for item in kwargs.get("avoid") or []:
                if hasattr(item, "_fake_half"):
                    actor_cubes += 1
                elif _is_premade(item):
                    premade += 1
                    if not np.allclose(item[1].T @ item[1], np.eye(2), atol=1e-9):
                        bad_axes += 1
    return actor_cubes, include_existing, premade, bad_axes


def _pairwise_gap_violations(env):
    """按放置顺序：后放方块（外扩 min_gap）的精确 OBB 与先放方块的精确 OBB 不得相交。"""
    obbs = env._xhard_cube_obbs
    assert len(obbs) == 6
    bad = 0
    for i, j in itertools.combinations(range(6), 2):
        c, A, h = obbs[j]
        padded = (c, A, h + env.cube_half_size)
        bad += og._obb2d_intersect(*obbs[i], *padded)
    return bad


@pytest.mark.parametrize("task", ["PickXtimes", "SwingXtimes"])
def test_v5_exact_obb(task, pick_rows, swing_rows) -> None:
    rows = pick_rows if task == "PickXtimes" else swing_rows
    actor_cubes, include_existing, premade, bad_axes = _exact_obb_audit(rows, 0.02)
    ok_rows = [row for row in rows if row["ok"]]
    gap_bad = sum(_pairwise_gap_violations(row["env"]) for row in ok_rows)
    # 已放方块的 OBB 与 actor 位姿一致（cube_obb2d_exact 取的是真实 yaw）
    for row in ok_rows[:50]:
        for cube, obb in zip(row["env"].all_cubes, row["env"]._xhard_cube_obbs):
            ref = cube_obb2d_exact(cube, row["env"].cube_half_size)
            assert all(np.array_equal(a, b) for a, b in zip(obb, ref))
    print(f"\nV5_EXACT_OBB={'PASS' if actor_cubes == include_existing == bad_axes == gap_bad == 0 else 'FAIL'} "
          f"task={task} degenerate=0 actor_cubes_in_avoid={actor_cubes} include_existing_true={include_existing} "
          f"premade={premade} bad_axes={bad_axes} gap_violations={gap_bad}")
    assert actor_cubes == 0 and include_existing == 0 and bad_axes == 0 and gap_bad == 0
    assert premade > 0


@pytest.mark.parametrize("task", ["PickXtimes", "SwingXtimes"])
def test_v5_min_center_distance(task, pick_rows, swing_rows) -> None:
    rows = pick_rows if task == "PickXtimes" else swing_rows
    ok_rows = [row for row in rows if row["ok"]]
    mins = [min_pair_distance(row["xys"]) for row in ok_rows]
    below = sum(m < MIN_CENTER_DIST - FLOAT32_TOL for m in mins)
    frac = below / max(len(ok_rows), 1)
    name = "V5_PICK_DISPERSION" if task == "PickXtimes" else "V5_SWING_SPACING"
    print(f"\n{name}={'PASS' if below == 0 else 'FAIL'} min_pair_lt_0p08={frac:.3f} "
          f"episodes={len(ok_rows)} min_of_min={min(mins):.4f} median_min={float(np.median(mins)):.4f}")
    assert len(ok_rows) >= 0.9 * len(rows)
    assert below == 0
    for row in ok_rows:
        assert len(row["xys"]) == 6
        assert row["env"]._spec.to_dict()["layout"]["cube_min_center_dist"] == MIN_CENTER_DIST


def test_pick_region_uniform_and_widened(pick_rows) -> None:
    """L43/L46：有色与干扰方块都在半宽 0.25 的区域内，且确实用到了 0.2 以外的环带；圆盘仍在 0.2 区内。"""
    ok_rows = [row for row in pick_rows if row["ok"]]
    outside_02 = 0
    for row in ok_rows:
        for xy in row["xys"]:
            dx, dy = abs(xy[0] + 0.1), abs(xy[1])
            assert dx <= 0.25 - 0.02 + FLOAT32_TOL and dy <= 0.25 - 0.02 + FLOAT32_TOL
            outside_02 += max(dx, dy) > 0.2 - 0.02
        goal = _actor_xy(row["env"].target)
        assert abs(goal[0] + 0.1) <= 0.2 and abs(goal[1]) <= 0.2
        assert "cube_corner_bias" not in row["env"]._spec.to_dict()["layout"]
    assert outside_02 > 0


def _failure_report(task, rows, bound):
    fails = [row for row in rows if not row["ok"]]
    rate = len(fails) / len(rows)
    classes = {}
    for row in fails:
        exc = row["exc"]
        key = f"{type(exc).__name__}:{str(exc).split(':')[0][:60]}"
        classes[key] = classes.get(key, 0) + 1
    print(f"\nV5_RESET_FEASIBILITY={'PASS' if rate <= bound else 'FAIL'} task={task} "
          f"fail={len(fails)}/{len(rows)} rate={rate:.4f} bound={bound} classes={classes}")
    return fails, rate


def test_pick_reset_feasibility(pick_rows) -> None:
    fails, rate = _failure_report("PickXtimes", pick_rows, 0.015)
    assert rate <= 0.015
    for row in fails:
        assert isinstance(row["exc"], SceneGenerationError), row["exc"]


def test_swing_reset_feasibility(swing_rows) -> None:
    fails, rate = _failure_report("SwingXtimes", swing_rows, 0.040)
    assert rate <= 0.040
    for row in fails:
        assert isinstance(row["exc"], SceneGenerationError), row["exc"]


def test_pick_goal_distance_report(pick_rows) -> None:
    """只报告不设门槛：目标圆盘离基座距离（圆盘区不变，应与 V4 同分布）。"""
    dists = [goal_distance_from_base(row["env"]) for row in pick_rows if row["ok"]]
    print(f"\nPICK_GOAL_DIST median={np.median(dists):.3f} p95={np.percentile(dists, 95):.3f} max={max(dists):.3f}")
    assert max(dists) < 0.9


# ---------------------------------------------------------------------------
# 失败形态与 N17
# ---------------------------------------------------------------------------
def _raise_runtime(*args, **kwargs):
    raise RuntimeError("spawn_random_cube: Region crowded")


def test_swing_colored_cube_failure_is_real_class(monkeypatch) -> None:
    monkeypatch.setattr(SWING, "spawn_random_cube", _raise_runtime)
    with OfflineScene(), pytest.raises(SceneGenerationError, match="放不下"):
        run_offline("SwingXtimes", 7)


def test_pick_cube_failure_is_real_class(monkeypatch) -> None:
    monkeypatch.setattr(PICK, "spawn_random_cube", _raise_runtime)
    with OfflineScene(), pytest.raises(SceneGenerationError, match="放不下"):
        run_offline("PickXtimes", 7)


def _first_ok_spec(task):
    with OfflineScene():
        for seed in SWEEP_SEEDS:
            try:
                env = run_offline(task, seed)
            except Exception:  # noqa: BLE001
                continue
            return seed, env._spec.to_dict()
    raise AssertionError("no feasible seed")


@pytest.mark.parametrize("task", ["PickXtimes", "SwingXtimes"])
def test_replay_frozen_spec(task) -> None:
    seed, doc = _first_ok_spec(task)
    # 合规冻结值：逐位回放、无 mismatch
    with OfflineScene():
        env = run_offline(task, seed, spec=copy.deepcopy(doc))
    assert env._spec.mismatches == []
    # 违规冻结值：最后一个干扰方块贴到第一个有色方块旁 3 cm → N17 报错
    bad = copy.deepcopy(doc)
    first_colored = next(iter(bad["layout"]["cubes"].values()))
    bad["layout"]["distractors"]["magenta_0"][:2] = [first_colored[0] + 0.03, first_colored[1]]
    with OfflineScene(), pytest.raises(EpisodeSpecError):
        # 干扰方块在两个环境里都不在 _load_scene 的 try 包装之内，N17 的 EpisodeSpecError 原样抛出
        run_offline(task, seed, spec=bad)


def test_swing_replay_colored_violation_is_wrapped() -> None:
    """Swing 的有色方块在 _load_scene 最外层 try 之内：N17 报错在 xhard 被包成真 SceneGenerationError，
    原因链保留 EpisodeSpecError（S2a 已注明的既有结构，这里锁定现状）。"""
    seed, doc = _first_ok_spec("SwingXtimes")
    bad = copy.deepcopy(doc)
    names = list(bad["layout"]["cubes"])
    first = bad["layout"]["cubes"][names[0]]
    bad["layout"]["cubes"][names[1]][:2] = [first[0] + 0.03, first[1]]
    with OfflineScene(), pytest.raises(SceneGenerationError) as info:
        run_offline("SwingXtimes", seed, spec=bad)
    cause = info.value.__cause__
    while cause is not None and not isinstance(cause, EpisodeSpecError):
        cause = cause.__cause__
    assert isinstance(cause, EpisodeSpecError)
