#!/usr/bin/env python3
"""轻量测试：VideoRepick 新值档中心距、S5 规划与 N17 回放复核。

纯 CPU、不起 sapien 场景：``actors.build_cube`` 用假 actor 顶替，其余全部走 ``VideoRepick`` 的真实代码
（``_load_cubes_newvalue`` → ``_plan_swaps_newvalue_v6``）；随机流头部复刻
``__init__``（num_repeats、n_swaps）与 ``_load_scene``（``build_button`` 的 ``rand(2)``）。

* ``VR_MIN_CENTER_DIST``：七块两两中心距 ≥ 0.12 m；回放冻结位姿违反即 ``EpisodeSpecError``（N17）；
* ``VR_ALL_CUBES_SWAP``：每个槽位都参与 S5 交换规划；
* ``VR_PLAN_D5``：配置开启时把按钮底座传入扫掠可行性检查；真实连续几何由 ``test_bin_collision.py`` 覆盖；
  没有可行搭档时抛真 ``SceneGenerationError``；
* ``VR_RNG_ORDER``：取值点顺序与随机调用序列（V4 前缀 + 追加一次 ``rand(n_swaps)``）；
* N17 回放：冻结规格原样回放零不等；篡改搭档（不可行）、发起者、V4 形态的发起者列表都报错；
* ``step`` 的新值分支用规划搭档（AST 抽循环实跑），原三档分支仍是最近邻。

    PYTHONPATH="$PWD/src" uv run --project /data/hongzefu/robomme_benchmark_MotionJEPANewTask --no-sync python -m pytest tests/lightweight/test_v5_xhard_videorepick.py -q
"""

from __future__ import annotations

import ast
import copy
import importlib
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
from robomme.robomme_env.utils.episode_spec import EpisodeSpecError, SpecRecorder  # noqa: E402
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402
from robomme.robomme_env.utils.xhard import cube_obb2d_exact  # noqa: E402
from robomme.robomme_env.utils.difficulty import is_newvalue_difficulty  # noqa: E402

pytestmark = pytest.mark.lightweight

MOD = importlib.import_module("robomme.robomme_env.VideoRepick")
CLS = MOD.VideoRepick
SOURCE = (REPO_ROOT / "src" / "robomme" / "robomme_env" / "VideoRepick.py").read_text(encoding="utf-8")
HALF = 0.02
# v4-01 ep3 的 seed（口径 10 的原始案例）与 P4 演示 seed；4900500 在按钮作障碍后规划失败（第 2 次交换）
# （v4-01 的 4900000 / 4900500 / 4900600 在按钮作障碍后都规划失败，只用来测失败路径）
SEEDS = [4900300, 4900100, 4900400, 4900700, 4900200, 4900800, 4900900, 7000000, 7000001, 7000002]
_FAKE_FEASIBILITY_INSTANCES = []


class _FakeActor:
    def __init__(self, name, pose):
        self.name = name
        self.pose = pose


def _fake_build_cube(scene, half_size, color, name, initial_pose):
    return _FakeActor(name, initial_pose)


@pytest.fixture(autouse=True)
def fake_scene(monkeypatch):
    _FAKE_FEASIBILITY_INSTANCES.clear()
    monkeypatch.setattr(og.actors, "build_cube", _fake_build_cube)

    class _CompleteFeasibility:
        def __init__(self, _states, statics=()):
            self.cache = {}
            self.evidence = {}
            self.statics = list(statics)
            _FAKE_FEASIBILITY_INSTANCES.append(self)

        def feasible(self, a, b):
            key = (min(a, b), max(a, b))
            self.cache[key] = True
            return True

    monkeypatch.setattr(MOD, "_XhardSlotSweepFeasibility", _CompleteFeasibility)


def _reset(seed, spec=None, sampling=None, torch_log=None):
    """用 xhard1 的四块假布局和固定完全图执行新值 S5 取值链。"""
    sampling = sampling or MOD._resolve_sampling_config(CLS, None)
    g = torch.Generator()
    g.manual_seed(seed)
    tier = "xhard1"
    rec = SpecRecorder(spec, "VideoRepick", {"seed": seed}, difficulty=tier)
    rep = sampling["decision"]["num_repeats_range"][tier]
    rec.value("objects.num_repeats", torch.randint(rep["low"], rep["high_exclusive"], (1,), generator=g).item())
    sw = sampling["decision"]["swap"][tier]
    n_swaps = rec.value("objects.n_swaps", torch.randint(sw["swap_min"], sw["swap_max"] + 1, (1,), generator=g).item())
    button = sampling["positions"]["button"]
    offset = torch.rand(2, generator=g) - 0.5
    center = (button["center_xy"][0] + float(offset[0]) * button["randomize_range"][0],
              button["center_xy"][1] + float(offset[1]) * button["randomize_range"][1])
    # 与 build_button 的返回同形：按钮 OBB 是 _load_scene 放进 avoid 的第一个元素
    button_obb = og.create_button_obb(center_xy=center, half_size=0.025 * button["scale"] * 1.5)
    fake = SimpleNamespace(difficulty=tier, generator=g, _spec=rec, cube_half_size=HALF, _sampling=sampling,
                           swap_times=n_swaps, device="cpu", scene=None, seed=seed, button_center=center)
    for name in ("_load_cubes_newvalue", "_plan_swaps_newvalue_v6", "_refresh_swap_schedule",
                 "_newvalue_planned_partner"):
        setattr(fake, name, types.MethodType(getattr(CLS, name), fake))
    if torch_log is not None:
        torch_log.clear()
    fake._load_cubes_newvalue([button_obb])
    return fake, rec


_CACHE = {}


def _cached(seed):
    if seed not in _CACHE:
        _CACHE[seed] = _reset(seed)
    return _CACHE[seed]


def _centers(fake):
    return np.array([cube_obb2d_exact(cube, HALF)[0] for cube in fake.spawned_cubes])


# ── 配置与三档隔离 ───────────────────────────────────────────────────────────


def test_新规则只挂在decision_xhard4且原三档与native守卫不动():
    decision, native = MOD.native_blocks(CLS)
    assert decision["xhard4"]["layout"]["min_center_dist_m"] == 0.12
    # V6（计划 2.5 S5）：搭档规则换成均衡贪心，不再有 nearest_k
    assert decision["xhard4"]["swap_plan"]["partner_rule"] == "s5_balanced_greedy"
    assert "nearest_k" not in decision["xhard4"]["swap_plan"]
    assert decision["xhard4"]["swap_plan"]["sweep_margin_m"] == 0.005
    assert decision["xhard4"]["swap_plan"]["button_obstacle"] is True
    # native 的 object_selection / swap_selection 原样（JSON 全等守卫不改）
    assert native["parameters"]["object_selection"]["swap_remaining_count"] == 2
    assert native["parameters"]["swap_selection"]["partner"]["position_axes"] == [0, 1]
    for name in ("easy", "medium", "hard"):
        assert "min_center_dist_m" not in CLS.configs[name]
    # 新值代码不再读 native 的 swap_remaining_count / position_axes
    funcs = {n.name: ast.unparse(n) for n in ast.walk(ast.parse(SOURCE)) if isinstance(n, ast.FunctionDef)}
    for name in ("_load_cubes_newvalue", "_plan_swaps_newvalue_v6"):
        assert "swap_remaining_count" not in funcs[name] and "position_axes" not in funcs[name], name


# ── VR_MIN_CENTER_DIST ─────────────────────────────────────────────────────


@pytest.mark.parametrize("seed", SEEDS)
def test_VR_MIN_CENTER_DIST(seed):
    fake, _rec = _cached(seed)
    points = _centers(fake)
    assert len(points) == 4
    dist = np.linalg.norm(points[:, None] - points[None], axis=-1) + np.eye(len(points)) * 9
    assert dist.min() >= 0.12 - 1e-12


def test_回放冻结位姿违反最小中心距即报错():
    fake, rec = _cached(SEEDS[0])
    spec = copy.deepcopy(rec.to_dict())
    xy_yaw = spec["layout"]["cubes"]["0"]["xy_yaw"]
    other = spec["layout"]["cubes"]["1"]["xy_yaw"]
    # 把 bin_1 挪到离 bin_0 只有 0.10 m 的位置（方向取远离按钮的 +x；区域内且不压按钮）
    spec["layout"]["cubes"]["1"]["xy_yaw"] = [xy_yaw[0] + 0.10, xy_yaw[1], other[2]]
    with pytest.raises(EpisodeSpecError):
        _reset(SEEDS[0], spec=spec)


# ── VR_ALL_CUBES_SWAP ──────────────────────────────────────────────────────


@pytest.mark.parametrize("seed", SEEDS)
def test_VR_S5序列覆盖有效槽位且无立即撤销(seed):
    fake, rec = _cached(seed)
    doc = rec.to_dict()
    target = doc["objects"]["target"]
    remaining = [i for i in range(4) if i != target]
    perm = doc["objects"]["swap_initiators_remaining"]
    assert sorted(perm) == list(range(3)) and len(perm) == 3
    n = fake.swap_times
    assert 3 <= n <= 4
    plan = fake._newvalue_swap_plan_info["plan"]
    # V6 S5：swap_initiators 记录实际发起者序列；发起者不按固定轮转
    assert doc["objects"]["swap_initiators"] == [f"bin_{step['initiator']}" for step in plan]
    for k in range(n):
        assert getattr(fake, f"swap_pair{k+1}_idx1") is fake.spawned_cubes[plan[k]["initiator"]]
        assert getattr(fake, f"swap_pair{k+1}_idx2") is None
    participants = {step["initiator"] for step in plan} | {step["partner"] for step in plan}
    assert participants <= set(range(4))
    counts = doc["objects"]["swap_plan"]["counts"]
    assert len(counts) == 4 and max(counts) - min(counts) <= 2 and doc["objects"]["swap_plan"]["undo"] == 0
    # 注入的 actions.swap_pairs.<k>：{"initiator": "bin_a", "partner": "bin_b"}，按事件序号的字典
    pairs = doc["actions"]["swap_pairs"]
    assert sorted(pairs, key=int) == [str(k) for k in range(n)]
    assert [pairs[str(k)] for k in range(n)] == [
        {"initiator": f"bin_{s['initiator']}", "partner": f"bin_{s['partner']}"} for s in plan
    ]
    assert fake._newvalue_swap_partners == [s["partner"] for s in plan]


# ── VR_PLAN_D5 ─────────────────────────────────────────────────────────────


def test_VR_PLAN_D5_按钮底座按配置传入可行性检查():
    """确认按钮开关控制 S5 可行性检查的静止障碍；真实扫掠几何由 bin_collision 单测覆盖。"""
    decision, native = MOD.native_blocks(CLS)
    _reset(4900100)
    assert _FAKE_FEASIBILITY_INSTANCES[-1].statics[0].name == "button_base"
    decision = copy.deepcopy(decision)
    decision["xhard1"]["swap_plan"]["button_obstacle"] = False
    off = MOD._resolve_sampling_config(CLS, {"decision": decision, "native": native})
    _reset(4900100, sampling=off)
    assert _FAKE_FEASIBILITY_INSTANCES[-1].statics == []


def test_没有可行搭档抛真SceneGenerationError(monkeypatch):
    fake, _rec = _reset(SEEDS[0])

    class _NoEdges:
        cache = {}

        @staticmethod
        def feasible(_a, _b):
            return False

    monkeypatch.setattr(MOD, "_XhardSlotSweepFeasibility", lambda *_args, **_kwargs: _NoEdges())
    cfg = fake._sampling["decision"][fake.difficulty]["swap_plan"]
    cfg["button_obstacle"] = False
    with pytest.raises(SceneGenerationError, match="没有扫掠可行的搭档"):
        fake._plan_swaps_newvalue_v6(1, None)


def test_规划纯函数_候选池与回退():
    # 槽位 0 在原点；1、2、3 依次变远，4 最远
    slots = [(0.0, 0.0), (0.10, 0.0), (0.20, 0.0), (0.30, 0.0), (0.40, 0.0)]
    bad = {(0, 1), (0, 2)}
    feasible = lambda a, b: (min(a, b), max(a, b)) not in bad  # noqa: E731
    # 最近 3 个（1,2,3）里 3 可行 ⇒ 非回退，池 = 前 3 个可行者 [3, 4]（只剩 2 个）
    plan = MOD._plan_swap_partners_xhard(slots, [0], [0.99], feasible, 3)
    assert plan[0]["partner"] == 4 and plan[0]["pool"] == 2 and not plan[0]["fallback"]
    # 最近 3 个全不可行 ⇒ 回退到任一可行
    bad2 = {(0, 1), (0, 2), (0, 3)}
    plan = MOD._plan_swap_partners_xhard(slots, [0], [0.0], lambda a, b: (min(a, b), max(a, b)) not in bad2, 3)
    assert plan[0]["partner"] == 4 and plan[0]["fallback"]
    # 名义对换后占用关系更新：第 1 次 0↔1 后，方块 1 在槽位 0，方块 0 在槽位 1
    plan = MOD._plan_swap_partners_xhard(slots, [0, 1], [0.0, 0.0], lambda a, b: True, 3)
    assert (plan[0]["partner"], plan[1]["slot_a"], plan[1]["partner"]) == (1, 0, 0)
    with pytest.raises(SceneGenerationError):
        MOD._plan_swap_partners_xhard(slots, [0], [0.5], lambda a, b: False, 3)


# ── VR_RNG_ORDER ───────────────────────────────────────────────────────────


class _TorchSpy:
    """顶替模块里的 ``torch``，记录带 generator 的随机调用（名字与形参），其余属性透传。"""

    def __init__(self, log, tag):
        self._log, self._tag = log, tag

    def __getattr__(self, name):
        attr = getattr(torch, name)
        if name in ("rand", "randint", "randperm", "randn"):
            def wrapped(*args, **kwargs):
                self._log.append((self._tag, name, tuple(a if isinstance(a, (int, tuple)) else "?" for a in args)))
                return attr(*args, **kwargs)
            return wrapped
        return attr


def test_VR_RNG_ORDER(monkeypatch):
    seed = SEEDS[0]
    log = []
    monkeypatch.setattr(MOD, "torch", _TorchSpy(log, "env"))
    monkeypatch.setattr(og, "torch", _TorchSpy(log, "spawn"))
    fake, rec = _reset(seed, torch_log=log)
    n = fake.swap_times
    # 环境侧：颜色 rand(3) → 目标 randint → randperm(6) → V6 追加一次规划种子 randint(0, 2**62)
    #（替换 V5 的 rand(n_swaps)；S5 的平局与重排走以它播种的局部流，不经模块 torch 的带 generator 调用之外的主流）
    env_calls = [c for c in log if c[0] == "env"]
    assert env_calls[:4] == [("env", "rand", (3,)), ("env", "randint", (0, 4, (1,))), ("env", "randperm", (3,)),
                             ("env", "randint", (0, 2 ** 62, (1,)))]
    # 摆放：每次 trial 仍是 3 个 rand(1)，全部落在颜色之后、目标之前
    first_env = [i for i, c in enumerate(log) if c[0] == "env"]
    spawn_block = log[first_env[0] + 1: first_env[1]]
    assert spawn_block and len(spawn_block) % 3 == 0
    assert all(c == ("spawn", "rand", (1,)) for c in spawn_block)
    assert all(c[0] == "env" for c in log[first_env[1]:])
    # 取值点顺序
    order = [t["path"] for t in rec.trace if t["source"] == "draw"]
    expected = (["objects.num_repeats", "objects.n_swaps", "objects.color_rgb"]
                + [f"layout.cubes.{i}.xy_yaw" for i in range(4)]
                + ["objects.target", "objects.swap_initiators_remaining", "objects.swap_plan_seed"]
                + [f"actions.swap_pairs.{k}" for k in range(n)])
    assert order == expected


# ── N17 回放 ───────────────────────────────────────────────────────────────


def test_回放原样规格零不等且搭档一致():
    fake, rec = _cached(SEEDS[0])
    spec = copy.deepcopy(rec.to_dict())
    fake2, rec2 = _reset(SEEDS[0], spec=spec)
    assert rec2.mismatches == []
    assert fake2._newvalue_swap_partners == fake._newvalue_swap_partners


def test_回放篡改为不可行搭档即报错(monkeypatch):
    fake, rec = _cached(SEEDS[0])
    first = fake._newvalue_swap_plan_info["plan"][0]
    bad = next(i for i in range(4) if i not in (first["slot_a"], first["slot_b"]))
    spec = copy.deepcopy(rec.to_dict())
    spec["actions"]["swap_pairs"]["0"]["partner"] = f"bin_{bad}"

    class _OneMissingPair:
        def __init__(self, _states, _statics=()):
            self.cache = {}
            self.evidence = {}

        def feasible(self, a, b):
            key = (min(a, b), max(a, b))
            self.cache[key] = key != (min(first["slot_a"], bad), max(first["slot_a"], bad))
            return self.cache[key]

    # 回放图只移除被篡改成的那一条边，其他冻结计划边仍然可行。
    monkeypatch.setattr(MOD, "_XhardSlotSweepFeasibility", _OneMissingPair)
    with pytest.raises(EpisodeSpecError, match="不可行"):
        _reset(SEEDS[0], spec=spec)


def test_回放篡改发起者或自换即报错():
    fake, rec = _cached(SEEDS[0])
    spec = copy.deepcopy(rec.to_dict())
    first = fake._newvalue_swap_plan_info["plan"][0]
    spec["actions"]["swap_pairs"]["0"]["initiator"] = f"bin_{first['partner']}"
    # V6：发起者与搭档都由 S5 规划，篡改成同一块 ⇒ S5 复核报「越界或重复」
    with pytest.raises(EpisodeSpecError, match="越界或重复"):
        _reset(SEEDS[0], spec=spec)
    spec = copy.deepcopy(rec.to_dict())
    spec["actions"]["swap_pairs"]["0"]["partner"] = f"bin_{first['initiator']}"
    with pytest.raises(EpisodeSpecError, match="越界或重复"):
        _reset(SEEDS[0], spec=spec)


def test_回放V4形态的发起者列表即报错():
    fake, rec = _cached(SEEDS[0])
    spec = copy.deepcopy(rec.to_dict())
    spec["objects"]["swap_initiators_remaining"] = spec["objects"]["swap_initiators_remaining"][:2]
    with pytest.raises(EpisodeSpecError, match="完整排列"):
        _reset(SEEDS[0], spec=spec)


def test_load_scene_对新值档EpisodeSpecError不包成SceneGenerationError():
    scene = ast.unparse(next(n for n in ast.walk(ast.parse(SOURCE))
                             if isinstance(n, ast.FunctionDef) and n.name == "_load_scene"))
    assert "if is_newvalue_difficulty(self.difficulty) and isinstance(exc, _EpisodeSpecError):\n            raise\n" in scene


# ── step 的 xhard 分支 ─────────────────────────────────────────────────────


def _swap_loop():
    step = next(n for n in ast.walk(ast.parse(SOURCE)) if isinstance(n, ast.FunctionDef) and n.name == "step")
    loops = [n for n in ast.walk(step) if isinstance(n, ast.For) and ast.unparse(n.iter) == "range(len(self.swap_schedule))"]
    assert len(loops) == 1
    return compile(ast.Module(body=loops, type_ignores=[]), "VideoRepick", "exec")


class _Actor:
    """只按身份比较的假 actor（SimpleNamespace 按 __dict__ 比较，含数组时 list.index 会报错）。"""

    def __init__(self, position):
        self.position = np.array(position, dtype=float)


def _loop_env(difficulty, planned):
    actors = [_Actor(p) for p in ([0, 0, 0], [0.05, 0, 0], [0.3, 0, 0])]
    calls = []
    env = SimpleNamespace(swap_schedule=[(actors[0], None, 0, 50)], swap_pair1_idx1=actors[0], swap_pair1_idx2=None,
                          elapsed_steps=0, start_step=0, _episode_spec=None, spawned_cubes=actors, difficulty=difficulty,
                          _sampling=MOD._resolve_sampling_config(CLS, None), _newvalue_swap_partners=planned,
                          _spec=SimpleNamespace(record=lambda path, value: calls.append(("record", path, value))))
    env._get_actor_position = lambda actor: actor.position
    env._refresh_swap_schedule = lambda *args: None
    env._sweep_checks_enabled = lambda: is_newvalue_difficulty(difficulty)
    env._check_swap_sweep_from_actual = lambda i, a, b: calls.append(("d5", i, actors.index(a), actors.index(b)))
    env._newvalue_planned_partner = types.MethodType(CLS._newvalue_planned_partner, env)
    return env, actors, calls


@pytest.mark.parametrize("tier", ["xhard1", "xhard2", "xhard3", "xhard4"])
def test_step_四档新值分支用规划搭档且D5照跑(tier):
    env, actors, calls = _loop_env(tier, [2])
    exec(_swap_loop(), {"self": env, "np": np, "is_newvalue_difficulty": is_newvalue_difficulty})
    assert env.swap_pair1_idx2 is actors[2]  # 规划搭档是最远的那块，不是最近邻 actors[1]
    assert ("d5", 0, 0, 2) in calls
    assert ("record", "actions.swap_pairs.0", {"initiator": "bin_0", "partner": "bin_2"}) in calls


def test_step_原三档分支仍取最近邻():
    env, actors, calls = _loop_env("easy", None)
    exec(_swap_loop(), {"self": env, "np": np, "is_newvalue_difficulty": is_newvalue_difficulty})
    assert env.swap_pair1_idx2 is actors[1]
    assert not [c for c in calls if c[0] == "d5"]


def test_step_newvalue缺规划即报错():
    from robomme.robomme_env.utils.bin_collision import SpecBindingError

    env, _actors, _calls = _loop_env("xhard1", None)
    with pytest.raises(SpecBindingError):
        exec(_swap_loop(), {"self": env, "np": np, "is_newvalue_difficulty": is_newvalue_difficulty})
