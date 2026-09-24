#!/usr/bin/env python3
"""轻量测试：V5 BinFill xhard（NEWTASK_RELEASE_V5_PLAN 2.12、L40～L42、N17、N18），纯 CPU、不起 sapien 场景。

做法：按 ``BinFill._load_scene`` 的 xhard 随机调用顺序离线复刻「按钮 → 孔板 → 配额 → spawn_order」这一段
（与规划期离线副本同式），然后把**真实的** ``BinFill._spawn_cubes_xhard`` 挂到一个假 ``self`` 上运行
（``actors.build_cube`` 用假 actor 顶替，只记位姿）。判据：

* ``BINFILL_MIN_GAP``：方块两两精确方形间距、方块到按钮／孔板的间距都 ≥ 名义 0.02 m；
* ``BINFILL_COLOR_MIX``：最大同色连通团（中心距 ≤ 0.09 m 相连）≤ 3，且不触发兜底；
* ``BINFILL_REDRAW_APPEND_ONLY``：颜色重排不改任何槽位位置（与关掉重排的同 seed 结果逐位相同）；
* ``BINFILL_NOT_OVERMIXED``：反聚集方向置换检验 p<0.05 的局占比 ≤ 0.06；
* 槽位采样与 ``spawn_random_cube`` 的拒绝循环逐次相同（同障碍、同随机流 ⇒ 同位姿）；
* N17：回放冻结值违反间距／成团上限／身份集合即报 ``EpisodeSpecError``；N18：配色只 value 一次。

    uv run --no-sync python -m pytest tests/lightweight/test_v5_xhard_binfill.py -q
"""

from __future__ import annotations

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

binfill = importlib.import_module("robomme.robomme_env.BinFill")
from robomme.robomme_env.utils import object_generation as og  # noqa: E402
from robomme.robomme_env.utils.episode_spec import EpisodeSpecError, SpecRecorder  # noqa: E402
from robomme.robomme_env.utils.sampling_config import SamplingConfigError  # noqa: E402
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402

CLS = binfill.BinFill
HALF = 0.02
MIN_GAP = 0.02
COLOR_MIX = {"max_component": 3, "link_m": 0.09, "max_redraws": 64}
N_SEEDS = 400  # 离线局数（纯 CPU，约十几秒）


# ---------------------------------------------------------------------------
# 假场景
# ---------------------------------------------------------------------------
class _FakeActor:
    def __init__(self, name, pose, color=None):
        self.name = name
        self.pose = pose
        self.color = color


def _fake_build_cube(scene, half_size, color, name, initial_pose):
    return _FakeActor(name, initial_pose, color)


@pytest.fixture(autouse=True)
def _patch_builders(monkeypatch):
    monkeypatch.setattr(og.actors, "build_cube", _fake_build_cube)


def _sampling(color_mix=None):
    """与环境 __init__ 同一解析路径；可覆盖 color_mix（经守卫放行的 xhard 条目改值）。"""
    override = None
    if color_mix is not None:
        decision, native = binfill.native_blocks(CLS)
        decision = copy.deepcopy(decision)
        decision["configs"]["xhard"]["color_mix"] = dict(color_mix)
        override = {"decision": decision, "native": native}
    return binfill._resolve_sampling_config(CLS, override)


def _fake_env(spec_doc=None, color_mix=None):
    return SimpleNamespace(
        cube_half_size=HALF, device="cpu", scene=None, all_cubes=[],
        red_cubes=[], blue_cubes=[], green_cubes=[],
        _sampling=_sampling(color_mix),
        _spec=SpecRecorder(spec_doc, "BinFill", {"seed": 0}, difficulty="xhard"),
    )


def _pre_cube(seed, env):
    """离线复刻 _load_scene（xhard、spec=None）在方块循环之前的全部随机调用，返回 (tasks, avoid, generator)。"""
    sampling = env._sampling
    g = torch.Generator()
    g.manual_seed(int(seed))
    button_cfg = sampling["positions"]["button"]
    off = torch.rand(2, generator=g) - 0.5
    cx = float(button_cfg["center_xy"][0]) + float(off[0]) * float(button_cfg["randomize_range"][0])
    cy = float(button_cfg["center_xy"][1]) + float(off[1]) * float(button_cfg["randomize_range"][1])
    button = og.create_button_obb(center_xy=(cx, cy), half_size=0.025 * 1.5 * 1.5)
    board_cfg = sampling["positions"]["board"]
    xv = torch.rand(1, generator=g).item() * board_cfg["x_offset"]["scale"] - board_cfg["x_offset"]["subtract"]
    yv = torch.rand(1, generator=g).item() * board_cfg["y_offset"]["scale"] - board_cfg["y_offset"]["subtract"]
    torch.rand(1, generator=g)  # 孔板 yaw（障碍四条边不随 yaw 转，与环境同）
    board = SimpleNamespace(
        _board_side=board_cfg["board_side"], _hole_side=board_cfg["hole_side"],
        pose=SimpleNamespace(p=torch.tensor([[0.15 + xv, yv, 0.0]], dtype=torch.float32)),
    )
    config = sampling["parameters"]["configs"]["xhard"]
    color_pool = torch.randperm(3, generator=g).tolist()[: config["color"]]
    pic = torch.randint(config["put_in_color"][0], config["put_in_color"][1] + 1, (1,), generator=g).item()
    pic = min(max(1, min(3, pic)), max(1, config["color"]))
    active = color_pool[:pic]
    target = [0, 0, 0]
    if pic == 1:
        target[active[0]] = torch.randint(config["put_in_numbers"][0], config["put_in_numbers"][1] + 1, (1,), generator=g).item()
    else:
        total = torch.randint(config["put_in_numbers"][0], config["put_in_numbers"][1] + 1, (1,), generator=g).item()
        for _ in range(total):
            target[active[torch.randint(0, len(active), (1,), generator=g).item()]] += 1
    total_spawn = torch.randint(config["spawn_cubes"][0], config["spawn_cubes"][1] + 1, (1,), generator=g).item()
    spawn = [0, 0, 0]
    for i in color_pool:
        spawn[i] = max(target[i], 1)
    for _ in range(max(0, total_spawn - sum(spawn[i] for i in color_pool))):
        spawn[color_pool[torch.randint(0, len(color_pool), (1,), generator=g).item()]] += 1
    info = [((1, 0, 0, 1), "red", env.red_cubes), ((0, 0, 1, 1), "blue", env.blue_cubes), ((0, 1, 0, 1), "green", env.green_cubes)]
    tasks = [{"color": c, "name": nm, "list": lst, "idx": k} for (c, nm, lst), n in zip(info, spawn) for k in range(n)]
    order = torch.randperm(len(tasks), generator=g).tolist()
    return [tasks[i] for i in order], [button, board], g


def _run(seed, spec_doc=None, color_mix=None):
    env = _fake_env(spec_doc, color_mix)
    tasks, avoid, g = _pre_cube(seed, env)
    obstacles = [avoid[0]] + binfill._board_strips_obb2d(avoid[1])
    binfill.BinFill._spawn_cubes_xhard(env, tasks, avoid, env._sampling["positions"]["cubes"], MIN_GAP, g)
    return env, tasks, obstacles, g


def _cube_xy_yaw(actor):
    p = actor.pose.p.reshape(-1).tolist()
    q = actor.pose.q.reshape(-1).tolist()
    return p[0], p[1], q


def _slots(env):
    doc = env._spec.to_dict()
    return [tuple(doc["layout"]["slots"][str(k)]) for k in range(len(doc["layout"]["slots"]))]


def _square(x, y, yaw, h=HALF):
    c, s = np.cos(yaw), np.sin(yaw)
    loc = np.array([[h, h], [-h, h], [-h, -h], [h, -h]])
    return loc @ np.array([[c, s], [-s, c]]) + np.array([x, y])


def _rect(c, A, h):
    loc = np.array([[1, 1], [-1, 1], [-1, -1], [1, -1]]) * h
    return loc @ A.T + c


def _seg_pt(p, a, b):
    ab = b - a
    t = np.clip(np.dot(p - a, ab) / np.dot(ab, ab), 0, 1)
    return np.linalg.norm(p - (a + t * ab))


def _poly_gap(P1, P2):
    """两个凸四边形的精确欧氏间距（相交时为 0）。"""
    obb = lambda P: (P.mean(0), np.stack([(P[0] - P[1]) / np.linalg.norm(P[0] - P[1]), (P[1] - P[2]) / np.linalg.norm(P[1] - P[2])], 1),
                     np.array([np.linalg.norm(P[0] - P[1]) / 2, np.linalg.norm(P[1] - P[2]) / 2]))
    if og._obb2d_intersect(*obb(P1), *obb(P2)):
        return 0.0
    d = np.inf
    for Pa, Pb in ((P1, P2), (P2, P1)):
        for p in Pa:
            for i in range(4):
                d = min(d, _seg_pt(p, Pb[i], Pb[(i + 1) % 4]))
    return d


@pytest.fixture(scope="module")
def batch():
    """N_SEEDS 局离线结果（默认配置）。模块级缓存，多个判据共用。"""
    mp = pytest.MonkeyPatch()
    mp.setattr(og.actors, "build_cube", _fake_build_cube)
    try:
        out = []
        for i in range(N_SEEDS):
            seed = 5500000 + 101 * i
            env, tasks, obstacles, _ = _run(seed)
            out.append((seed, env, obstacles))
        return out
    finally:
        mp.undo()


# ---------------------------------------------------------------------------
# 配置与守卫（V5 语义；替代 V4 测试里「config_xhard 只有 5 个键」的断言）
# ---------------------------------------------------------------------------
def test_config_xhard_has_color_mix_and_three_tiers_untouched() -> None:
    assert CLS.config_xhard["color_mix"] == COLOR_MIX
    decision = binfill._native_decision(CLS)
    assert decision["configs"]["xhard"]["color_mix"] == COLOR_MIX
    for difficulty in ("easy", "medium", "hard"):
        assert "color_mix" not in CLS.configs[difficulty]
        assert set(decision["configs"][difficulty]) == {"color", "spawn_cubes", "put_in_numbers"}
    resolved = binfill._resolve_sampling_config(CLS, None)
    assert resolved["parameters"]["configs"]["xhard"]["color_mix"] == COLOR_MIX


@pytest.mark.parametrize("bad", [
    {"max_component": 0, "link_m": 0.09, "max_redraws": 64},
    {"max_component": 3.0, "link_m": 0.09, "max_redraws": 64},
    {"max_component": 3, "link_m": -0.01, "max_redraws": 64},
    {"max_component": 3, "link_m": float("nan"), "max_redraws": 64},
    {"max_component": 3, "link_m": 0.09, "max_redraws": -1},
    {"max_component": 3, "link_m": 0.09, "max_redraws": True},
])
def test_guard_rejects_bad_color_mix(bad) -> None:
    with pytest.raises(SamplingConfigError, match="color_mix"):
        _sampling(bad)


def test_guard_rejects_snapshot_missing_color_mix() -> None:
    """V4 快照的 xhard 条目没有 color_mix：形状检查拒绝（V4 作废，预期）。"""
    decision, native = binfill.native_blocks(CLS)
    decision = copy.deepcopy(decision)
    decision["configs"]["xhard"].pop("color_mix")
    with pytest.raises(SamplingConfigError, match="xhard"):
        binfill._resolve_sampling_config(CLS, {"decision": decision, "native": native})


def test_max_same_color_component() -> None:
    f = binfill._max_same_color_component
    assert f(np.zeros((0, 2)), [], 0.09) == 0
    # 用二进制可精确表示的间距 0.0625，检验「恰好等于 link 也算相连（≤）」
    xy = [[0, 0], [0.0625, 0], [0.125, 0], [0.1875, 0], [1, 1]]
    assert f(xy, ["r"] * 5, 0.0625) == 4
    assert f(xy, ["r"] * 5, 0.0624) == 1
    assert f(xy, ["r", "b", "r", "r", "r"], 0.0625) == 2
    with pytest.raises(ValueError):
        f(xy, ["r"], 0.09)


# ---------------------------------------------------------------------------
# 验收判据
# ---------------------------------------------------------------------------
def test_BINFILL_MIN_GAP(batch) -> None:
    violations, cube_pairs, worst = 0, 0, np.inf
    for _, env, obstacles in batch:
        slots = _slots(env)
        assert len(slots) == 12 and len(env.all_cubes) == 12
        squares = [_square(*s) for s in slots]
        for i in range(len(squares)):
            for j in range(i + 1, len(squares)):
                gap = _poly_gap(squares[i], squares[j])
                cube_pairs += 1
                worst = min(worst, gap)
                violations += gap < MIN_GAP - 1e-9
            for obb in obstacles:
                gap = _poly_gap(squares[i], _rect(*obb))
                violations += gap < MIN_GAP - 1e-9
    print(f"BINFILL_MIN_GAP={'PASS' if violations == 0 else 'FAIL'} violations={violations} "
          f"pairs={cube_pairs} min_gap_mm={worst * 1000:.2f}")
    assert violations == 0


def test_BINFILL_COLOR_MIX(batch) -> None:
    violations = fallback = redraw_eps = 0
    for _, env, _ in batch:
        doc = env._spec.to_dict()
        slots = _slots(env)
        labels = [ident.rsplit("_", 1)[0] for ident in doc["objects"]["slot_assignment"]]
        comp = binfill._max_same_color_component([s[:2] for s in slots], labels, COLOR_MIX["link_m"])
        assert comp == doc["objects"]["color_mix_max_component"]
        violations += comp > COLOR_MIX["max_component"]
        fallback += bool(doc["objects"]["color_mix_fallback"])
        redraw_eps += doc["objects"]["color_redraws"] > 0
    print(f"BINFILL_COLOR_MIX={'PASS' if violations == 0 and fallback == 0 else 'FAIL'} T=3 "
          f"violations={violations} fallback={fallback} redraw_episodes={redraw_eps}/{len(batch)}")
    assert violations == 0 and fallback == 0


def test_BINFILL_REDRAW_APPEND_ONLY(batch) -> None:
    """同 seed 关掉重排（max_redraws=0）与默认配置：槽位位置逐位相同，只有颜色标签可能不同。"""
    pos_equal = redrawn = 0
    for seed, env, _ in batch:
        off, _, _, _ = _run(seed, color_mix={**COLOR_MIX, "max_redraws": 0})
        a, b = env._spec.to_dict(), off._spec.to_dict()
        pos_equal += a["layout"]["slots"] == b["layout"]["slots"]
        if a["objects"]["color_redraws"]:
            redrawn += 1
            assert sorted(a["objects"]["slot_assignment"]) == sorted(b["objects"]["slot_assignment"])
        else:
            assert a["objects"]["slot_assignment"] == b["objects"]["slot_assignment"]
    print(f"BINFILL_REDRAW_APPEND_ONLY={'PASS' if pos_equal == len(batch) else 'FAIL'} "
          f"pos_equal={pos_equal}/{len(batch)} redrawn={redrawn}")
    assert pos_equal == len(batch)


def test_BINFILL_NOT_OVERMIXED(batch) -> None:
    """反聚集方向：观测的「最近邻同色比例」在颜色置换分布里偏低（p<0.05）的局占比不应明显超 5%。"""
    rng = np.random.default_rng(20260924)
    hits = 0
    for _, env, _ in batch:
        doc = env._spec.to_dict()
        P = np.array([s[:2] for s in _slots(env)])
        lab = np.array([ident.rsplit("_", 1)[0] for ident in doc["objects"]["slot_assignment"]])
        D = np.linalg.norm(P[:, None] - P[None], axis=-1)
        np.fill_diagonal(D, np.inf)
        nn = D.argmin(1)
        obs = np.mean(lab[nn] == lab)
        perms = np.array([rng.permutation(lab) for _ in range(300)])
        null = (perms[:, nn] == perms).mean(1)
        hits += (1 + np.sum(null <= obs)) / 301 < 0.05
    frac = hits / len(batch)
    print(f"BINFILL_NOT_OVERMIXED={'PASS' if frac <= 0.06 else 'FAIL'} anti_p05_frac={frac:.3f}")
    assert frac <= 0.06


# ---------------------------------------------------------------------------
# 结构性质
# ---------------------------------------------------------------------------
def test_slot_sampler_matches_spawn_random_cube_loop() -> None:
    """槽位几何与「spawn_random_cube + 精确 OBB 预制障碍」逐次相同（同一随机流、同一位姿）。"""
    from robomme.robomme_env.utils.xhard import cube_obb2d_exact
    for i in range(30):
        seed = 5600000 + 7 * i
        env, tasks, _, _ = _run(seed, color_mix={**COLOR_MIX, "max_redraws": 0})
        ref_env = _fake_env()
        ref_tasks, avoid, g = _pre_cube(seed, ref_env)
        cubes_cfg = ref_env._sampling["positions"]["cubes"]
        obst = list(avoid)
        got = []
        for _ in ref_tasks:
            cube = og.spawn_random_cube(
                ref_env, avoid=obst, include_existing=False, include_goal=False,
                region_center=list(cubes_cfg["region_center"]), region_half_size=list(cubes_cfg["region_half_size"]),
                half_size=HALF, min_gap=MIN_GAP, random_yaw=True, generator=g,
                recorder=ref_env._spec, spec_path=f"probe.{len(got)}",
            )
            xy_yaw = ref_env._spec.to_dict()["probe"][str(len(got))]
            got.append(tuple(xy_yaw))
            obst.append(cube_obb2d_exact(xy_yaw, HALF))
        assert got == _slots(env), seed


def test_actor_built_at_slot_with_assigned_color_and_lists_in_slot_order(batch) -> None:
    _, env, _ = batch[0]
    doc = env._spec.to_dict()
    slots = _slots(env)
    colors = {"red": (1, 0, 0, 1), "blue": (0, 0, 1, 1), "green": (0, 1, 0, 1)}
    for k, (actor, ident) in enumerate(zip(env.all_cubes, doc["objects"]["slot_assignment"])):
        assert actor.name == f"cube_{ident}"
        assert actor.color == colors[ident.rsplit("_", 1)[0]]
        x, y, _ = _cube_xy_yaw(actor)
        assert abs(x - slots[k][0]) < 1e-6 and abs(y - slots[k][1]) < 1e-6
        assert doc["layout"]["cubes"][ident] == list(slots[k])
    # 各色列表顺序＝槽位顺序
    for name, lst in (("red", env.red_cubes), ("blue", env.blue_cubes), ("green", env.green_cubes)):
        expect = [a for a in env.all_cubes if a.name.startswith(f"cube_{name}_")]
        assert lst == expect


def test_no_redraw_keeps_v4_spawn_order_assignment(batch) -> None:
    """不需重排的局：槽位 k 的身份就是 spawn_order 洗牌后的第 k 个任务（V4 语义）。"""
    checked = 0
    for seed, env, _ in batch[:80]:
        doc = env._spec.to_dict()
        if doc["objects"]["color_redraws"]:
            continue
        tasks, _, _ = _pre_cube(seed, _fake_env())
        assert doc["objects"]["slot_assignment"] == [f"{t['name']}_{t['idx']}" for t in tasks]
        checked += 1
    assert checked > 0


def test_redraw_draws_are_appended_after_slots() -> None:
    """找一局需要重排的：重排消耗的正是槽位之后的 randperm(12)，次数与 record 一致。"""
    for i in range(400):
        seed = 5700000 + 13 * i
        env, _, _, g = _run(seed)
        r = env._spec.to_dict()["objects"]["color_redraws"]
        if r == 0:
            continue
        off, _, _, g_off = _run(seed, color_mix={**COLOR_MIX, "max_redraws": 0})
        for _ in range(r):
            torch.randperm(12, generator=g_off)
        assert torch.equal(g.get_state(), g_off.get_state())
        return
    pytest.fail("400 局里没有需要重排的局")


def test_n18_single_value_for_assignment(batch) -> None:
    _, env, _ = batch[0]
    paths = [t["path"] for t in env._spec.trace if t["source"] in ("draw", "spec")]
    assert paths.count("objects.slot_assignment") == 1
    assert sum(p.startswith("layout.slots.") for p in paths) == 12
    assert not any(p.startswith("layout.cubes.") for p in paths)  # layout.cubes 只由 record 写
    recs = [t["path"] for t in env._spec.trace if t["source"] == "record"]
    assert {"objects.color_redraws", "objects.color_mix_fallback"} <= set(recs)


def test_fallback_takes_best_and_is_recorded(monkeypatch) -> None:
    """把上限压到 1（几乎不可能满足）：重排跑满 max_redraws，取最优并记兜底。"""
    env, _, _, _ = _run(5500000, color_mix={"max_component": 1, "link_m": 0.2, "max_redraws": 5})
    doc = env._spec.to_dict()
    assert doc["objects"]["color_redraws"] == 5
    assert doc["objects"]["color_mix_fallback"] is True
    assert doc["objects"]["color_mix_max_component"] > 1


# ---------------------------------------------------------------------------
# N17 回放复核
# ---------------------------------------------------------------------------
def _export(seed):
    env, _, _, _ = _run(seed)
    return env._spec.to_dict()


def test_faithful_replay_has_no_mismatch() -> None:
    doc = _export(5500000)
    env, _, _, _ = _run(5500000, spec_doc=doc)
    assert env._spec.mismatches == []
    assert env._spec.to_dict()["layout"]["cubes"] == doc["layout"]["cubes"]


def test_replay_rejects_slot_violating_gap() -> None:
    doc = copy.deepcopy(_export(5500000))
    s0 = doc["layout"]["slots"]["0"]
    doc["layout"]["slots"]["1"] = [s0[0] + 0.045, s0[1], s0[2]]  # 与槽位 0 只隔 < 2 cm
    with pytest.raises(EpisodeSpecError, match="槽位 1"):
        _run(5500000, spec_doc=doc)


def test_replay_rejects_slot_outside_region() -> None:
    doc = copy.deepcopy(_export(5500000))
    doc["layout"]["slots"]["0"] = [0.5, 0.0, 0.0]
    with pytest.raises(EpisodeSpecError, match="超出方块区域"):
        _run(5500000, spec_doc=doc)


def test_replay_rejects_bad_assignment() -> None:
    doc = copy.deepcopy(_export(5500000))
    doc["objects"]["slot_assignment"] = doc["objects"]["slot_assignment"][:-1] + ["red_99"]
    with pytest.raises(EpisodeSpecError, match="不是同一组"):
        _run(5500000, spec_doc=doc)


def test_replay_rejects_clustered_assignment() -> None:
    """把同色块全部挪到彼此 ≤ 0.09 的一串槽位上：成团超过 3 即报错。"""
    for i in range(200):
        seed = 5800000 + 17 * i
        doc = copy.deepcopy(_export(seed))
        P = np.array([doc["layout"]["slots"][str(k)][:2] for k in range(12)])
        assignment = doc["objects"]["slot_assignment"]
        names = [a.rsplit("_", 1)[0] for a in assignment]
        # 找一个 ≥4 个槽位的连通块，把最多的颜色塞进去
        D = np.linalg.norm(P[:, None] - P[None], axis=-1)
        comp = binfill._max_same_color_component(P, ["x"] * 12, 0.09)
        majority = max(set(names), key=names.count)
        if comp < 4 or names.count(majority) < 4:
            continue
        # 求出最大的全连通块的成员
        seen, best = set(), []
        for s in range(12):
            if s in seen:
                continue
            stack, member = [s], []
            seen.add(s)
            while stack:
                u = stack.pop()
                member.append(u)
                for v in range(12):
                    if v not in seen and D[u, v] <= 0.09:
                        seen.add(v)
                        stack.append(v)
            best = max(best, member, key=len)
        maj_ids = [a for a in assignment if a.startswith(majority + "_")]
        others = [a for a in assignment if not a.startswith(majority + "_")]
        new = [None] * 12
        for slot in best[:len(maj_ids)]:
            new[slot] = maj_ids.pop()
        rest = maj_ids + others
        for k in range(12):
            if new[k] is None:
                new[k] = rest.pop()
        labels = [a.rsplit("_", 1)[0] for a in new]
        if binfill._max_same_color_component(P, labels, 0.09) <= 3:
            continue
        doc["objects"]["slot_assignment"] = new
        with pytest.raises(EpisodeSpecError, match="最大同色团"):
            _run(seed, spec_doc=doc)
        return
    pytest.fail("200 局里没找到能构造成团的布局")


def test_slot_exhaustion_raises_scene_generation_error(monkeypatch) -> None:
    env = _fake_env()
    tasks, avoid, g = _pre_cube(5500000, env)
    cubes_cfg = copy.deepcopy(env._sampling["positions"]["cubes"])
    cubes_cfg["region_half_size"] = [0.05, 0.05]  # 小到放不下 12 块
    with pytest.raises(SceneGenerationError, match="槽位"):
        binfill.BinFill._spawn_cubes_xhard(env, tasks, avoid, cubes_cfg, MIN_GAP, g)
