#!/usr/bin/env python3
"""轻量测试：V5 S3g VideoRepick 的 xhard 改动（NEWTASK_RELEASE_V5_PLAN 2.15，L47～L51、L54，N17）。

纯 CPU、不起 sapien 场景：``actors.build_cube`` 用假 actor 顶替，其余全部走 ``VideoRepick`` 的真实代码
（``_load_cubes_xhard`` → ``_plan_swaps_xhard`` → ``_plan_swap_partners_xhard``）；随机流头部复刻
``__init__``（num_repeats、n_swaps）与 ``_load_scene``（``build_button`` 的 ``rand(2)``）。

* ``VR_MIN_CENTER_DIST``：6 块两两中心距 ≥ 0.12 m；回放冻结位姿违反即 ``EpisodeSpecError``（N17）；
* ``VR_ALL_CUBES_SWAP``：发起者 ``seq[k % 6]``（``seq = [目标] + randperm(5)``），6 块全部参与交换；
* ``VR_PLAN_D5``：规划出的每一对在 reset 名义槽位上用**原** ``check_swap_sweep``（不预筛）复核扫掠可行，
  按钮底座作 bystander 也不被拒；没有可行搭档时抛真 ``SceneGenerationError``；
* ``VR_RNG_ORDER``：取值点顺序与随机调用序列（V4 前缀 + 追加一次 ``rand(n_swaps)``）；
* N17 回放：冻结规格原样回放零不等；篡改搭档（不可行）、发起者、V4 形态的发起者列表都报错；
* ``step`` 的 xhard 分支用规划搭档（AST 抽循环实跑），原三档分支仍是最近邻。

    uv run --no-sync python -m pytest tests/lightweight/test_v5_xhard_videorepick.py -q
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
from robomme.robomme_env.utils.bin_collision import (  # noqa: E402
    button_base_state,
    check_swap_sweep,
)
from robomme.robomme_env.utils.episode_spec import EpisodeSpecError, SpecRecorder  # noqa: E402
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402
from robomme.robomme_env.utils.xhard import cube_obb2d_exact  # noqa: E402

pytestmark = pytest.mark.lightweight

MOD = importlib.import_module("robomme.robomme_env.VideoRepick")
CLS = MOD.VideoRepick
SOURCE = (REPO_ROOT / "src" / "robomme" / "robomme_env" / "VideoRepick.py").read_text(encoding="utf-8")
HALF = 0.02
# v4-01 ep3 的 seed（口径 10 的原始案例）与 P4 演示 seed；4900500 在按钮作障碍后规划失败（第 2 次交换）
# （v4-01 的 4900000 / 4900500 / 4900600 在按钮作障碍后都规划失败，只用来测失败路径）
SEEDS = [4900300, 4900100, 4900400, 4900700, 4900200, 4900800, 4900900, 7000000, 7000001, 7000002]
PLAN_FAIL_SEED = 4900500


class _FakeActor:
    def __init__(self, name, pose):
        self.name = name
        self.pose = pose


def _fake_build_cube(scene, half_size, color, name, initial_pose):
    return _FakeActor(name, initial_pose)


@pytest.fixture(autouse=True)
def fake_scene(monkeypatch):
    monkeypatch.setattr(og.actors, "build_cube", _fake_build_cube)


def _reset(seed, spec=None, sampling=None, torch_log=None):
    """复刻 xhard 的 reset 取值链，返回 (fake_env, recorder)；规划失败照常抛异常。"""
    sampling = sampling or MOD._resolve_sampling_config(CLS, None)
    g = torch.Generator()
    g.manual_seed(seed)
    rec = SpecRecorder(spec, "VideoRepick", {"seed": seed}, difficulty="xhard")
    rep = sampling["decision"]["num_repeats_range"]["xhard"]
    rec.value("objects.num_repeats", torch.randint(rep["low"], rep["high_exclusive"], (1,), generator=g).item())
    sw = sampling["decision"]["swap"]["xhard"]
    n_swaps = rec.value("objects.n_swaps", torch.randint(sw["swap_min"], sw["swap_max"] + 1, (1,), generator=g).item())
    button = sampling["positions"]["button"]
    offset = torch.rand(2, generator=g) - 0.5
    center = (button["center_xy"][0] + float(offset[0]) * button["randomize_range"][0],
              button["center_xy"][1] + float(offset[1]) * button["randomize_range"][1])
    # 与 build_button 的返回同形：按钮 OBB 是 _load_scene 放进 avoid 的第一个元素
    button_obb = og.create_button_obb(center_xy=center, half_size=0.025 * button["scale"] * 1.5)
    fake = SimpleNamespace(difficulty="xhard", generator=g, _spec=rec, cube_half_size=HALF, _sampling=sampling,
                           swap_times=n_swaps, device="cpu", scene=None, seed=seed, button_center=center)
    for name in ("_load_cubes_xhard", "_plan_swaps_xhard", "_refresh_swap_schedule", "_xhard_planned_partner"):
        setattr(fake, name, types.MethodType(getattr(CLS, name), fake))
    if torch_log is not None:
        torch_log.clear()
    fake._load_cubes_xhard([button_obb])
    return fake, rec


_CACHE = {}


def _cached(seed):
    if seed not in _CACHE:
        _CACHE[seed] = _reset(seed)
    return _CACHE[seed]


def _centers(fake):
    return np.array([cube_obb2d_exact(cube, HALF)[0] for cube in fake.spawned_cubes])


# ── 配置与三档隔离 ───────────────────────────────────────────────────────────


def test_新规则只挂在decision_xhard且原三档与native守卫不动():
    decision, native = MOD.native_blocks(CLS)
    assert decision["xhard"]["layout"]["min_center_dist_m"] == 0.12
    assert decision["xhard"]["swap_plan"]["nearest_k"] == 3
    assert decision["xhard"]["swap_plan"]["sweep_margin_m"] == 0.005
    assert decision["xhard"]["swap_plan"]["button_obstacle"] is True
    # native 的 object_selection / swap_selection 原样（JSON 全等守卫不改）
    assert native["parameters"]["object_selection"]["swap_remaining_count"] == 2
    assert native["parameters"]["swap_selection"]["partner"]["position_axes"] == [0, 1]
    for name in ("easy", "medium", "hard"):
        assert "min_center_dist_m" not in CLS.configs[name]
    # xhard 代码不再读 native 的 swap_remaining_count / position_axes
    funcs = {n.name: ast.unparse(n) for n in ast.walk(ast.parse(SOURCE)) if isinstance(n, ast.FunctionDef)}
    for name in ("_load_cubes_xhard", "_plan_swaps_xhard"):
        assert "swap_remaining_count" not in funcs[name] and "position_axes" not in funcs[name], name


# ── VR_MIN_CENTER_DIST ─────────────────────────────────────────────────────


@pytest.mark.parametrize("seed", SEEDS)
def test_VR_MIN_CENTER_DIST(seed):
    fake, _rec = _cached(seed)
    points = _centers(fake)
    assert len(points) == 6
    dist = np.linalg.norm(points[:, None] - points[None], axis=-1) + np.eye(6) * 9
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
def test_VR_ALL_CUBES_SWAP(seed):
    fake, rec = _cached(seed)
    doc = rec.to_dict()
    target = doc["objects"]["target"]
    remaining = [i for i in range(6) if i != target]
    perm = doc["objects"]["swap_initiators_remaining"]
    assert sorted(perm) == list(range(5)) and len(perm) == 5  # L47 a'：长度 5
    seq = [target] + [remaining[i] for i in perm]
    assert doc["objects"]["swap_initiators"] == [f"bin_{i}" for i in seq]
    n = fake.swap_times
    assert 8 <= n <= 12
    plan = fake._xhard_swap_plan_info["plan"]
    assert [step["initiator"] for step in plan] == [seq[k % 6] for k in range(n)]
    for k in range(n):
        assert getattr(fake, f"swap_pair{k+1}_idx1") is fake.spawned_cubes[seq[k % 6]]
        assert getattr(fake, f"swap_pair{k+1}_idx2") is None
    participants = {step["initiator"] for step in plan} | {step["partner"] for step in plan}
    assert participants == set(range(6))
    # 注入的 actions.swap_pairs.<k>：{"initiator": "bin_a", "partner": "bin_b"}，按事件序号的字典
    pairs = doc["actions"]["swap_pairs"]
    assert sorted(pairs, key=int) == [str(k) for k in range(n)]
    assert [pairs[str(k)] for k in range(n)] == [
        {"initiator": f"bin_{s['initiator']}", "partner": f"bin_{s['partner']}"} for s in plan
    ]
    assert fake._xhard_swap_partners == [s["partner"] for s in plan]


# ── VR_PLAN_D5 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("seed", SEEDS[:4])
def test_VR_PLAN_D5_规划出的每一对在reset时扫掠可行且不压按钮(seed):
    fake, _rec = _cached(seed)
    info = fake._xhard_swap_plan_info
    swap_cfg = fake._sampling["decision"]["xhard"]["swap_plan"]
    states = MOD._xhard_slot_states(info["slots"], HALF, swap_cfg["sweep_margin_m"])
    button = button_base_state("button_base", fake.button_center, scale=fake._sampling["positions"]["button"]["scale"])
    checked = set()
    for step in info["plan"]:
        key = (min(step["slot_a"], step["slot_b"]), max(step["slot_a"], step["slot_b"]))
        if key in checked:
            continue
        checked.add(key)
        others = [s for j, s in enumerate(states) if j not in key]
        # 用原 check_swap_sweep（不预筛）独立复核规划口径：其余槽位 + 按钮底座
        _gap, rejection = check_swap_sweep(states[key[0]], states[key[1]], others + [button])
        assert rejection is None, (seed, key, rejection and rejection.as_dict())
    # 候选池：非回退时取前 nearest_k 个可行者，u 下标落在池内
    for step in info["plan"]:
        assert 1 <= step["pool"] <= (5 if step["fallback"] else swap_cfg["nearest_k"])


def test_VR_PLAN_D5_按钮作障碍确实生效():
    """同一 seed：按钮不作障碍时规划出的某一对会压按钮（被按钮拒），开了按钮后规划里不再出现。"""
    decision, native = MOD.native_blocks(CLS)
    decision = copy.deepcopy(decision)
    decision["xhard"]["swap_plan"]["button_obstacle"] = False
    off = MOD._resolve_sampling_config(CLS, {"decision": decision, "native": native})
    fake_off, _ = _reset(4900100, sampling=off)
    fake_on, _ = _cached(4900100)
    info = fake_off._xhard_swap_plan_info
    states = MOD._xhard_slot_states(info["slots"], HALF, 0.005)
    button = button_base_state("button_base", fake_off.button_center, scale=1.5)
    hit = []
    for step in info["plan"]:
        key = (min(step["slot_a"], step["slot_b"]), max(step["slot_a"], step["slot_b"]))
        _gap, rejection = check_swap_sweep(states[key[0]], states[key[1]], [button])
        if rejection is not None:
            hit.append(key)
    assert hit, "P4 记录 4900100 按钮关时有一段压按钮，这里应能复现"
    on_keys = {(min(s["slot_a"], s["slot_b"]), max(s["slot_a"], s["slot_b"])) for s in fake_on._xhard_swap_plan_info["plan"]}
    assert not on_keys & set(hit)


def test_没有可行搭档抛真SceneGenerationError():
    with pytest.raises(SceneGenerationError, match="没有扫掠可行的搭档"):
        _reset(PLAN_FAIL_SEED)


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
    # 环境侧：颜色 rand(3) → 目标 randint → randperm(5)（V4 同一次，不再截断）→ 追加 rand(n_swaps)
    env_calls = [c for c in log if c[0] == "env"]
    assert env_calls == [("env", "rand", (3,)), ("env", "randint", (0, 6, (1,))), ("env", "randperm", (5,)),
                         ("env", "rand", (n,))]
    # 摆放：每次 trial 仍是 3 个 rand(1)，全部落在颜色之后、目标之前
    first_env = [i for i, c in enumerate(log) if c[0] == "env"]
    spawn_block = log[first_env[0] + 1: first_env[1]]
    assert spawn_block and len(spawn_block) % 3 == 0
    assert all(c == ("spawn", "rand", (1,)) for c in spawn_block)
    assert all(c[0] == "env" for c in log[first_env[1]:])
    # 取值点顺序
    order = [t["path"] for t in rec.trace if t["source"] == "draw"]
    expected = (["objects.num_repeats", "objects.n_swaps", "objects.color_rgb"]
                + [f"layout.cubes.{i}.xy_yaw" for i in range(6)]
                + ["objects.target", "objects.swap_initiators_remaining", "objects.swap_partner_u"]
                + [f"actions.swap_pairs.{k}" for k in range(n)])
    assert order == expected


# ── N17 回放 ───────────────────────────────────────────────────────────────


def test_回放原样规格零不等且搭档一致():
    fake, rec = _cached(SEEDS[0])
    spec = copy.deepcopy(rec.to_dict())
    fake2, rec2 = _reset(SEEDS[0], spec=spec)
    assert rec2.mismatches == []
    assert fake2._xhard_swap_partners == fake._xhard_swap_partners


def _infeasible_partner_spec(seed):
    fake, rec = _cached(seed)
    spec = copy.deepcopy(rec.to_dict())
    info = fake._xhard_swap_plan_info
    first = info["plan"][0]
    bad = [b for (a, b) in info["infeasible_slot_pairs"] if a == first["slot_a"]] + \
          [a for (a, b) in info["infeasible_slot_pairs"] if b == first["slot_a"]]
    return spec, first, bad


def test_回放篡改为不可行搭档即报错():
    for seed in SEEDS:
        spec, first, bad = _infeasible_partner_spec(seed)
        if bad:
            break
    else:
        pytest.fail("没找到有不可行槽位对的 seed")
    spec["actions"]["swap_pairs"]["0"]["partner"] = f"bin_{bad[0]}"  # k=0 时槽位号 = 方块号
    with pytest.raises(EpisodeSpecError, match="不可行"):
        _reset(seed, spec=spec)


def test_回放篡改发起者或自换即报错():
    fake, rec = _cached(SEEDS[0])
    spec = copy.deepcopy(rec.to_dict())
    first = fake._xhard_swap_plan_info["plan"][0]
    spec["actions"]["swap_pairs"]["0"]["initiator"] = f"bin_{first['partner']}"
    with pytest.raises(EpisodeSpecError, match="发起者"):
        _reset(SEEDS[0], spec=spec)
    spec = copy.deepcopy(rec.to_dict())
    spec["actions"]["swap_pairs"]["0"]["partner"] = f"bin_{first['initiator']}"
    with pytest.raises(EpisodeSpecError, match="非法"):
        _reset(SEEDS[0], spec=spec)


def test_回放V4形态的发起者列表即报错():
    fake, rec = _cached(SEEDS[0])
    spec = copy.deepcopy(rec.to_dict())
    spec["objects"]["swap_initiators_remaining"] = spec["objects"]["swap_initiators_remaining"][:2]
    with pytest.raises(EpisodeSpecError, match="完整排列"):
        _reset(SEEDS[0], spec=spec)


def test_load_scene_对xhard的EpisodeSpecError不包成SceneGenerationError():
    scene = ast.unparse(next(n for n in ast.walk(ast.parse(SOURCE))
                             if isinstance(n, ast.FunctionDef) and n.name == "_load_scene"))
    assert "if self.difficulty == 'xhard' and isinstance(exc, _EpisodeSpecError):\n            raise\n" in scene


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
                          _sampling=MOD._resolve_sampling_config(CLS, None), _xhard_swap_partners=planned,
                          _spec=SimpleNamespace(record=lambda path, value: calls.append(("record", path, value))))
    env._get_actor_position = lambda actor: actor.position
    env._refresh_swap_schedule = lambda *args: None
    env._sweep_checks_enabled = lambda: difficulty == "xhard"
    env._check_swap_sweep_from_actual = lambda i, a, b: calls.append(("d5", i, actors.index(a), actors.index(b)))
    env._xhard_planned_partner = types.MethodType(CLS._xhard_planned_partner, env)
    return env, actors, calls


def test_step_xhard分支用规划搭档且D5照跑():
    env, actors, calls = _loop_env("xhard", [2])
    exec(_swap_loop(), {"self": env, "np": np})
    assert env.swap_pair1_idx2 is actors[2]  # 规划搭档是最远的那块，不是最近邻 actors[1]
    assert ("d5", 0, 0, 2) in calls
    assert ("record", "actions.swap_pairs.0", {"initiator": "bin_0", "partner": "bin_2"}) in calls


def test_step_原三档分支仍取最近邻():
    env, actors, calls = _loop_env("easy", None)
    exec(_swap_loop(), {"self": env, "np": np})
    assert env.swap_pair1_idx2 is actors[1]
    assert not [c for c in calls if c[0] == "d5"]


def test_step_xhard缺规划即报错():
    from robomme.robomme_env.utils.bin_collision import SpecBindingError

    env, _actors, _calls = _loop_env("xhard", None)
    with pytest.raises(SpecBindingError):
        exec(_swap_loop(), {"self": env, "np": np})
