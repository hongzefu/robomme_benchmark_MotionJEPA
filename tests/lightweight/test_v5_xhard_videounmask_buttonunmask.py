#!/usr/bin/env python3
"""V5 S3b：VideoUnmask / ButtonUnmask 的 xhard 干扰容器接入统一采样器（L13）与独立停放点（L14）。

轻量部分（不起 sapien 场景）：

* ``XHARD_DISTRACTOR`` 等于 ``V5_DISTRACTOR_PRESETS``（VU 15 个 / BU 14 个、贴身环带、cube [7,8] / [7,7]、7 键），
  且是深拷贝（改环境里的配置不会连带改预设）；
* AST：``spawn_distractor_layout`` 只在 xhard 分支、只调一次、排在 ``_load_scene`` 全部既有 ``recorder.value``
  取值点之后；V4 的 ``spawn_ring_distractor_bins`` / ``reveal_distractor_bins`` 不再被调用；
  新模块的所有调用都在 xhard 分支里（原三档不进新模块）；
* AST：``step`` 里原三档的揭示循环原样搬进 ``else``，与 V4 的循环文本逐字相同；
* 真 ``step`` 代码 + 假 actor：hard 仍走 statechange、全部停 (10,10,10)；xhard 下内环容器与干扰容器各停各的点、
  半窗那一步落回原位（误差 0），且没有任何物体停在 (10,10,10)。

模拟器部分（``gpu`` 标记，轻量全量里不跑，验收时手动跑）：真 reset 检查
``V5_UNMASK_RING`` / ``V5_UNMASK_HALF_CUBE`` / ``V5_UNMASK_NAMES`` / 内环与 V4 同 seed 逐位相同。

    uv run --no-sync python -m pytest tests/lightweight/test_v5_xhard_videounmask_buttonunmask.py -q
    uv run --no-sync python -m pytest tests/lightweight/test_v5_xhard_videounmask_buttonunmask.py -q -m gpu -s
"""

from __future__ import annotations

import ast
import copy
import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme.robomme_env.utils import unmask_distractor_sampler as uds  # noqa: E402

pytestmark = pytest.mark.lightweight

TASKS = ("VideoUnmask", "ButtonUnmask")
ENV_DIR = REPO_ROOT / "src" / "robomme" / "robomme_env"
EXPECT = {"VideoUnmask": (15, [7, 8]), "ButtonUnmask": (14, [7, 7])}
NEW_MODULE_NAMES = {
    "spawn_distractor_layout", "reveal_actors_parked", "reveal_distractor_bins_parked",
    "V5_DISTRACTOR_PRESETS",
}
XHARD_CONDS = {"xhard", "self.difficulty == 'xhard'"}

# V4（12.120 及以前）step 里原三档的揭示循环，ast.unparse 后的文本；V5 只许把它原样搬进 else
V4_REVEAL_LOOP = (
    "for i in range(self._sampling['parameters']['step_bin_scan']):\n"
    "    bin_attr = f'bin_{i}'\n"
    "    if hasattr(self, bin_attr):\n"
    "        lift_and_drop_objects_back_to_original(self, obj=getattr(self, bin_attr), "
    "start_step=self._sampling['positions']['reveal_window']['start_step'], "
    "end_step=self._sampling['positions']['reveal_window']['end_step'], cur_step=timestep)"
)


def _module(task):
    return importlib.import_module(f"robomme.robomme_env.{task}")


def _funcs(task):
    tree = ast.parse((ENV_DIR / f"{task}.py").read_text(encoding="utf-8"))
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _calls_with_cond(func):
    """``[(被调函数名, 包住它的最近一层 If 条件文本或 None, 源码行号)]``；else 分支记为 ``not (条件)``。"""
    out = []

    def walk(node, cond):
        if isinstance(node, ast.If):
            test = ast.unparse(node.test)
            for child in node.body:
                walk(child, test)
            for child in node.orelse:
                walk(child, f"not ({test})")
            return
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else ast.unparse(node.func)
            out.append((name, cond, node.lineno))
        for child in ast.iter_child_nodes(node):
            walk(child, cond)

    for stmt in func.body:
        walk(stmt, None)
    return out


# ── 配置 ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("task", TASKS)
def test_xhard干扰配置等于V5预设且是深拷贝(task):
    mod = _module(task)
    count, cubes = EXPECT[task]
    assert mod.XHARD_DISTRACTOR == uds.V5_DISTRACTOR_PRESETS[task]
    assert mod.XHARD_DISTRACTOR is not uds.V5_DISTRACTOR_PRESETS[task]
    assert set(mod.XHARD_DISTRACTOR) == set(uds.DISTRACTOR_CFG_KEYS)
    cfg = uds.parse_distractor_cfg(mod.XHARD_DISTRACTOR)
    assert cfg.count == count and list(cfg.cube_count_range) == cubes
    assert list(cfg.ring) == [0.2425, 0.3289]
    assert cfg.color_rule == "balanced_cycle" and cfg.min_gap_factor == 0.75 and cfg.max_trials == 1024
    decision = mod._native_decision(getattr(mod, task))
    assert decision["xhard"]["distractor"] == uds.V5_DISTRACTOR_PRESETS[task]
    # decision 里的子树也是独立副本
    decision["xhard"]["distractor"]["count"] = -1
    assert mod.XHARD_DISTRACTOR["count"] == count


# ── AST：挂接点 ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("task", TASKS)
def test_统一采样器只在xhard且排在全部既有取值点之后(task):
    funcs = _funcs(task)
    scene = funcs["_load_scene"]
    calls = _calls_with_cond(scene)
    spawn = [c for c in calls if c[0] == "spawn_distractor_layout"]
    assert len(spawn) == 1 and spawn[0][1] in XHARD_CONDS, spawn
    # V4 的外环采样器不再被调用
    assert not [c for c in calls if c[0] == "spawn_ring_distractor_bins"]
    # 全部既有取值点（recorder.value / spawn_random_bin / randperm / inject_fail_grasp）都在它之前
    value_lines = [ln for name, _c, ln in calls
                   if name in ("self._spec.value", "spawn_random_bin", "torch.randperm", "inject_fail_grasp",
                               "build_button", "torch.randint", "torch.rand")]
    assert value_lines and max(value_lines) < spawn[0][2], (value_lines, spawn)


@pytest.mark.parametrize("task", TASKS)
def test_新模块的调用全部在xhard分支(task):
    funcs = _funcs(task)
    for fname, func in funcs.items():
        for name, cond, _ln in _calls_with_cond(func):
            if name in NEW_MODULE_NAMES:
                assert cond in XHARD_CONDS, (fname, name, cond)
    # V4 的 (10,10,10) 揭示在本环境不再使用
    for func in funcs.values():
        assert "reveal_distractor_bins" not in [c[0] for c in _calls_with_cond(func)]


@pytest.mark.parametrize("task", TASKS)
def test_step原三档揭示循环原样搬进else(task):
    step = _funcs(task)["step"]
    ifs = [s for s in step.body if isinstance(s, ast.If) and ast.unparse(s.test) == "self.difficulty == 'xhard'"]
    assert len(ifs) == 1
    branch = ifs[0]
    assert len(branch.orelse) == 1 and ast.unparse(branch.orelse[0]) == V4_REVEAL_LOOP
    xhard_calls = [c for c in _calls_with_cond(ast.Module(body=branch.body, type_ignores=[]))]
    names = [c[0] for c in xhard_calls]
    assert "reveal_actors_parked" in names and "reveal_distractor_bins_parked" in names
    assert "lift_and_drop_objects_back_to_original" not in names
    text = ast.unparse(branch)
    assert "group='bin'" in text


# ── 真 step 代码 + 假 actor ─────────────────────────────────────────────────────
class _Pose:
    def __init__(self, p, q=(1.0, 0.0, 0.0, 0.0)):
        self.p = torch.tensor([list(p)], dtype=torch.float32)
        self.q = torch.tensor([list(q)], dtype=torch.float32)


class _Actor:
    def __init__(self, xyz):
        self.pose = _Pose(xyz)

    def set_pose(self, pose):
        self.pose = _Pose(list(pose.p), list(pose.q))

    def set_linear_velocity(self, v):
        pass

    def set_angular_velocity(self, v):
        pass

    def xyz(self):
        return np.asarray(self.pose.p[0], dtype=np.float64)


def _fake_env(task, difficulty, monkeypatch, n_bins=8, n_distractors=15):
    from mani_skill.envs.sapien_env import BaseEnv

    mod = _module(task)
    cls = getattr(mod, task)
    monkeypatch.setattr(BaseEnv, "step", lambda self, action: (None, None, None, None, {}))
    env = cls.__new__(cls)
    env.difficulty = difficulty
    env._sampling = {
        "parameters": copy.deepcopy(mod.NATIVE_SAMPLING["parameters"]),
        "positions": copy.deepcopy(mod.NATIVE_SAMPLING["positions"]),
    }
    rng = np.random.default_rng(0)
    bins = []
    for i in range(n_bins):
        actor = _Actor([*rng.uniform(-0.2, 0.2, 2), 0.002])
        setattr(env, f"bin_{i}", actor)
        bins.append(actor)
    env.distractor_bins = [_Actor([0.3, -0.29 + 0.04 * j, 0.002]) for j in range(n_distractors)] \
        if difficulty == "xhard" else []
    return cls, env, bins


def _run_steps(cls, env, n):
    trace = []
    for step in range(n):
        env._elapsed_steps = step
        cls.step(env, None)
        trace.append((step, [a.xyz().copy() for a in env._probe_actors]))
    return trace


@pytest.mark.parametrize("task", TASKS)
def test_hard仍走statechange停在10_10_10(task, monkeypatch):
    cls, env, bins = _fake_env(task, "hard", monkeypatch)
    origin = [b.xyz().copy() for b in bins]
    env._probe_actors = bins
    trace = _run_steps(cls, env, 70)
    for step, xyz in trace:
        if step < 32:
            assert all(np.allclose(p, [10.0, 10.0, 10.0]) for p in xyz), step
    # 半窗之后回到原位
    for p, o in zip(trace[40][1], origin):
        assert np.allclose(p, o, atol=1e-6)
    assert not getattr(env, "_xhard_park_cache", {})


@pytest.mark.parametrize("task", TASKS)
def test_xhard内环与干扰容器各停各的点且落回原位(task, monkeypatch):
    cls, env, bins = _fake_env(task, "xhard", monkeypatch, n_distractors=EXPECT[task][0])
    actors = bins + env.distractor_bins
    origin = [a.xyz().copy() for a in actors]
    expected_park = [uds.xhard_park_point("bin", i) for i in range(len(bins))] + \
        [uds.xhard_park_point("distractor_bin", j) for j in range(len(env.distractor_bins))]
    env._probe_actors = actors
    trace = _run_steps(cls, env, 70)
    for step, xyz in trace:
        if step < 32:
            assert all(np.allclose(p, q) for p, q in zip(xyz, expected_park)), step
            # 两两不同，且没有任何物体停在旧的 (10,10,10)
            assert len({tuple(np.round(p, 3)) for p in xyz}) == len(actors)
            assert not any(np.linalg.norm(p - 10.0) < 5.0 for p in xyz)
        else:
            err = max(float(np.max(np.abs(p - o))) for p, o in zip(xyz, origin))
            assert err == pytest.approx(0.0, abs=1e-6), (step, err)
    # statechange 的缓存从未被用到（原三档机制在 xhard 下不走）
    assert not hasattr(env, "_lift_drop_cache")


# ── 模拟器：真 reset 验收（gpu 标记，手动跑） ───────────────────────────────────
V4_SPECS = Path("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/scripts/configs/newtask-v4/v4-01/specs.jsonl")
SIM_SEEDS = {"VideoUnmask": (4600000, 4600300, 4600600, 5100001), "ButtonUnmask": (4800000, 4800300, 4800600, 5100001)}


def _v4_spec(task, seed):
    if not V4_SPECS.exists():
        return None
    for line in V4_SPECS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("record") == "spec" and row.get("task") == task and row.get("seed") == seed:
            return row["spec"]
    return None


def reset_check(task, seed):
    """真 reset 一次，返回 V5_UNMASK_* 各项检查的原始数据。"""
    import gymnasium as gym
    import robomme.robomme_env  # noqa: F401 注册环境
    from robomme.robomme_env.utils.xhard import DISTRACTOR_COLORS

    env = gym.make(task, obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                   render_mode="rgb_array", reward_mode="dense", seed=seed, difficulty="xhard")
    try:
        env.reset()
        u = env.unwrapped
        cfg = uds.parse_distractor_cfg(u._sampling["decision"]["xhard"]["distractor"])
        layout = u.distractor_layout
        chs = float(u.cube_half_size)
        out_of_ring = sum(1 for x, y, _ in layout.bins
                          if not (cfg.ring[0] <= max(abs(x), abs(y)) <= cfg.ring[1]))
        # 精确可见：用 actor 真实位姿复算 8 角点
        not_visible = 0
        for actor in u.distractor_bins:
            p = actor.pose.p[0].detach().cpu().numpy()
            if not uds.bin_visible(float(p[0]), float(p[1]), chs):
                not_visible += 1
        colors = layout.cube_colors
        counts = [colors.count(c["name"]) for c in DISTRACTOR_COLORS]
        # 场景里 actor 按名字登记（重名在建 actor 时就会报错）；这里另把本环境自己建的物体逐个列出来查重，
        # 并确认它们都已登记在场景里
        own = list(u.spawned_bins) + [getattr(u, f"target_cube_{i}") for i in range(3)] \
            + list(u.distractor_bins) + list(u.distractor_cubes)
        names = [a.name for a in own]
        registered = set(getattr(u.scene, "actors", {}).keys())
        assert all(n in registered for n in names), sorted(set(names) - registered)
        spec = u._spec.to_dict()
        v4 = _v4_spec(task, seed)
        inner_equal = None
        if v4 is not None:
            inner_equal = (spec["layout"] == v4["layout"]
                           and {k: v for k, v in spec["objects"].items() if k != "distractors"}
                           == {k: v for k, v in v4["objects"].items() if k != "distractors"})
        return {
            "task": task, "seed": seed, "requested": cfg.count, "placed": len(u.distractor_bins),
            "shortfall": cfg.count - len(u.distractor_bins), "out_of_ring": out_of_ring, "not_visible": not_visible,
            "cube_count": len(u.distractor_cubes), "cube_range": list(cfg.cube_count_range),
            "range_ok": cfg.cube_count_range[0] <= len(u.distractor_cubes) <= cfg.cube_count_range[1],
            "color_imbalance": max(counts) - min(counts) if colors else 0,
            "duplicate_actor_names": len(names) - len(set(names)), "n_actor_names": len(names),
            "inner_equal_v4": inner_equal,
            "trials_max": max(spec["objects"]["distractors"]["trials"]) if "trials" in spec["objects"]["distractors"] else None,
        }
    finally:
        env.close()


@pytest.mark.gpu
@pytest.mark.parametrize("task", TASKS)
def test_真reset验收(task):
    rows = [reset_check(task, seed) for seed in SIM_SEEDS[task]]
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))
        assert row["placed"] == EXPECT[task][0] and row["shortfall"] == 0
        assert row["out_of_ring"] == 0 and row["not_visible"] == 0
        assert row["range_ok"] and row["color_imbalance"] <= 1
        assert row["duplicate_actor_names"] == 0 and row["n_actor_names"] > 0
        assert row["inner_equal_v4"] in (True, None)


@pytest.mark.gpu
@pytest.mark.parametrize("task", TASKS)
def test_真reset原三档不进新模块(task, monkeypatch):
    """hard 真 reset + 揭示窗口内走 40 步：新模块的函数一旦被调用即报错；hard 的干扰相关属性与规格都不存在。"""
    import gymnasium as gym
    import robomme.robomme_env  # noqa: F401 注册环境

    mod = _module(task)

    def _boom(*_a, **_k):
        raise AssertionError("原三档调用了 V5 xhard 新模块")

    for name in ("spawn_distractor_layout", "reveal_actors_parked", "reveal_distractor_bins_parked"):
        monkeypatch.setattr(mod, name, _boom)
    env = gym.make(task, obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                   render_mode="rgb_array", reward_mode="dense", seed=4600000, difficulty="hard")
    try:
        env.reset()
        u = env.unwrapped
        qpos = u.agent.robot.get_qpos()[0].detach().cpu().numpy()
        dim = env.action_space.shape[-1]
        action = np.concatenate([qpos[:dim - 1], [1.0]]).astype(np.float32)
        for _ in range(40):
            env.step(action)
        spec = u._spec.to_dict()
        assert "distractors" not in spec.get("objects", {})
        assert not hasattr(u, "distractor_layout")
        assert not getattr(u, "_xhard_park_cache", None)
    finally:
        env.close()
