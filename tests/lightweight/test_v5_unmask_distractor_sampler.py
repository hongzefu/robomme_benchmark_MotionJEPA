#!/usr/bin/env python3
"""轻量测试：V5 四个 Unmask 环境的干扰容器统一采样器与独立停放点（NEWTASK_RELEASE_V5_PLAN 2.2 / L13 / L14）。

不起 sapien 场景，只测纯几何层与记录纪律：

* 四套预设（VU 15 / BU 14 / VUS 10 / BUS 10）在代表性随机内部布局下：数量对、全在环带内、全部精确 8 角点可见、
  干扰容器两两之间与对内环容器的**真实方形外廓**间距 ≥ min_gap、不压按钮 OBB、含 cube 数在区间内、
  颜色平衡（各色个数差 ≤ 1）、名字无重复，1024 次预算不耗尽；
* 同一 seed 可复现；不给回调时随机调用序列与 V4 VU/BU 逐项同构（逐容器 2 次/尝试 + 1 次 yaw → randint → randperm(N) → randperm(3)）；
* 额外拒绝回调生效且可复核；
* 记录纪律（N18）：整段重抽只在被接受的那次调 ``recorder.value``，尝试次数与失败原因用 ``record``；
  回放返回冻结值且复核规则，篡改的冻结布局被拒；
* 停放 helper（L14）：每个物体一个互不接触的画面外停放点，时间线与 statechange 对应函数逐步相同；
* 密度推导锁定（计划 2.2）：``N = floor(ρ·A_usable + 0.5)``，ρ = 50/m²，1 mm 网格上 VU → 15、BU → 14，环带 [0.2425, 0.3289]。

    uv run --no-sync python -m pytest tests/lightweight/test_v5_unmask_distractor_sampler.py -q
"""

from __future__ import annotations

import math
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

from robomme.robomme_env.utils import unmask_distractor_sampler as S  # noqa: E402
from robomme.robomme_env.utils.bin_collision import ObjectState, bin_actor_pose, bin_shape_specs  # noqa: E402
from robomme.robomme_env.utils.episode_spec import SpecRecorder  # noqa: E402
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402
from robomme.robomme_env.utils.unmask_distractors import (  # noqa: E402
    BASE_CAMERA_EYE,
    BASE_CAMERA_FOV,
    BASE_CAMERA_TARGET,
    _camera_axes,
    bin_geometry,
)
from robomme.robomme_env.utils.xhard import DISTRACTOR_COLORS  # noqa: E402

pytestmark = pytest.mark.lightweight

CHS = 0.02  # 四个环境的 cube_half_size
HALF, REACH_ANY_YAW, HEIGHT = bin_geometry(CHS)  # 0.0275 / 0.0424 / 0.054
OUTER = S.bin_outer_half(CHS)  # 0.03
MIN_GAP = CHS * 0.75  # 0.015
BTN_HALF = 0.025 * 1.5 * 1.5  # create_button_obb 半边（build_button scale 1.5）
ENVS = ("VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap")


# ── 纯几何小件 ───────────────────────────────────────────────────────────────────
def _rect_corners(c, a, h):
    return np.array([c + a @ (h * np.array([sx, sy])) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])


def _seg_point_dist(p, a, b):
    ab = b - a
    t = np.clip(float((p - a) @ ab) / float(ab @ ab), 0.0, 1.0)
    return float(np.linalg.norm(p - (a + t * ab)))


def _convex_overlap(p, q):
    for poly in (p, q):
        for i in range(len(poly)):
            edge = poly[(i + 1) % len(poly)] - poly[i]
            n = np.array([-edge[1], edge[0]])
            if (p @ n).max() < (q @ n).min() or (q @ n).max() < (p @ n).min():
                return False
    return True


def _poly_dist(p, q):
    """两个凸多边形的欧氏距离；相交为 0。"""
    if _convex_overlap(p, q):
        return 0.0
    best = float("inf")
    for a, b in ((p, q), (q, p)):
        for v in a:
            for i in range(len(b)):
                best = min(best, _seg_point_dist(v, b[i], b[(i + 1) % len(b)]))
    return best


def _bin_square(x, y, yaw):
    return _rect_corners(*S.bin_obb2d(x, y, yaw, CHS, pad=0.0))


def _sample_inner(rng, n, lo_xy, hi_xy, gap, fixed):
    """仿 spawn_random_bin：中心在 [lo, hi] 均匀、到已放障碍 OBB 的点距 ≥ 0.0275 + gap，yaw u·90。"""
    obbs = list(fixed)
    bins = []
    for _ in range(n):
        for _t in range(4000):
            xy = rng.uniform(lo_xy, hi_xy)
            if not S.point_hits_obbs(xy, obbs, HALF + gap):
                yaw = float(rng.random() * 90.0)
                bins.append((float(xy[0]), float(xy[1]), yaw))
                obbs.append(S.bin_obb2d(xy[0], xy[1], yaw, CHS, pad=gap))
                break
        else:
            return None
    return bins


def _inner_scene(env, rng):
    """代表性内部布局：返回 (内环容器 [(x,y,yaw)], 预制按钮 OBB 列表)。"""
    buttons = []
    if env == "ButtonUnmask":
        c = np.array([-0.2, 0.0]) + (rng.random(2) - 0.5) * 0.1
        buttons = [(c, np.eye(2), np.array([BTN_HALF, BTN_HALF]))]
    if env == "ButtonUnmaskSwap":
        for base in ([-0.2, -0.1], [-0.2, 0.1]):
            c = np.array(base) + (rng.random(2) - 0.5) * 0.05
            buttons.append((c, np.eye(2), np.array([BTN_HALF, BTN_HALF])))
    if env in ("VideoUnmask", "ButtonUnmask"):
        # VU/BU xhard：8 个容器、region [-0.2,0.2]²（中心 ±0.1725）、G2 间距系数 0.75
        bins = _sample_inner(rng, 8, np.array([-0.1725, -0.1725]), np.array([0.1725, 0.1725]), MIN_GAP, buttons)
    elif env == "VideoUnmaskSwap":
        # 4 个容器落在旋转包络的切比雪夫半宽 0.2114 内
        bins = _sample_inner(rng, 4, np.array([-0.1839, -0.1839]), np.array([0.1839, 0.1839]), CHS, buttons)
    else:
        # BUS：中心 x∈[-0.0425,0.1425]、y∈[-0.1425,0.2425]
        bins = _sample_inner(rng, 4, np.array([-0.0425, -0.1425]), np.array([0.1425, 0.2425]), CHS, buttons)
    assert bins is not None
    return bins, buttons


def _obstacles(inner_bins, buttons):
    # 与 obstacle_obbs 对 actor 的口径一致：内环容器按 min_gap 外扩，按钮预制框原样
    return [S.bin_obb2d(x, y, yaw, CHS, pad=MIN_GAP) for x, y, yaw in inner_bins] + list(buttons)


def _gen(seed):
    g = torch.Generator()
    g.manual_seed(int(seed))
    return g


# ── 配置 ────────────────────────────────────────────────────────────────────────
def test_预设与计划数值一致():
    from robomme.robomme_env.utils.unmask_swap_xhard import XHARD_DISTRACTOR as V4_SWAP

    expect = {
        "VideoUnmask": (15, (0.2425, 0.3289), (7, 8)),
        "ButtonUnmask": (14, (0.2425, 0.3289), (7, 7)),
        "VideoUnmaskSwap": (10, tuple(V4_SWAP["ring_half_extent"]), (5, 5)),
        "ButtonUnmaskSwap": (10, tuple(V4_SWAP["ring_half_extent"]), (5, 5)),
    }
    for env, (count, ring, cubes) in expect.items():
        c = S.parse_distractor_cfg(S.V5_DISTRACTOR_PRESETS[env])
        assert (c.count, c.ring, c.cube_count_range) == (count, ring, cubes), env
        assert c.max_trials == 1024 and c.min_gap_factor == 0.75 and c.color_rule == "balanced_cycle"
    # 含 cube 数 = [floor(N/2), ceil(N/2)]（L11）
    for env in ("VideoUnmask", "ButtonUnmask"):
        c = S.parse_distractor_cfg(S.V5_DISTRACTOR_PRESETS[env])
        assert c.cube_count_range == (c.count // 2, (c.count + 1) // 2)
    # 全局色板不许改（PickXtimes / SwingXtimes 也用）
    assert [c["name"] for c in DISTRACTOR_COLORS] == ["yellow", "cyan", "magenta"]


@pytest.mark.parametrize(
    "patch",
    [
        {"color_pool": ["yellow", "cyan"]},
        {"color_rule": "without_replacement"},
        {"cube_count_range": [3, 16]},
        {"cube_count_range": [5, 4]},
        {"ring_max_abs_xy": [0.3, 0.2]},
        {"max_trials": 0},
        {"extra_key": 1},
    ],
)
def test_非法配置直接报错(patch):
    cfg = dict(S.V5_DISTRACTOR_PRESETS["VideoUnmask"], **patch)
    with pytest.raises(ValueError):
        S.parse_distractor_cfg(cfg)


# ── 几何规则 ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("env", ENVS)
def test_代表性内部布局下全部规则成立且预算不耗尽(env):
    cfg = S.parse_distractor_cfg(S.V5_DISTRACTOR_PRESETS[env])
    rng = np.random.default_rng(20260924 + ENVS.index(env))
    max_trials = 0
    for k in range(40):
        inner, buttons = _inner_scene(env, rng)
        obstacles = _obstacles(inner, buttons)
        layout = S.sample_distractor_layout(cfg, obstacles=obstacles, generator=_gen(1000 + k), cube_half_size=CHS)
        max_trials = max(max_trials, max(layout.trials))
        assert S.verify_distractor_layout(layout, cfg, obstacles=obstacles, cube_half_size=CHS) == []
        assert layout.count == cfg.count
        squares = [_bin_square(*b) for b in layout.bins]
        for i, (x, y, yaw) in enumerate(layout.bins):
            assert cfg.ring[0] <= max(abs(x), abs(y)) <= cfg.ring[1]
            assert S.bin_visible(x, y, CHS)
            assert 0.0 <= yaw < 90.0
            for other in squares[i + 1:]:
                assert _poly_dist(squares[i], other) >= MIN_GAP - 1e-9
            for b in inner:
                assert _poly_dist(squares[i], _bin_square(*b)) >= MIN_GAP - 1e-9
            for c, a, h in buttons:
                assert _poly_dist(squares[i], _rect_corners(c, a, h)) > 0.0
        lo, hi = cfg.cube_count_range
        assert lo <= layout.cube_count <= hi
        assert len(layout.cube_bins) == layout.cube_count == len(set(layout.cube_bins))
        assert all(0 <= b < cfg.count for b in layout.cube_bins)
        counts = [layout.cube_colors.count(c["name"]) for c in DISTRACTOR_COLORS]
        assert max(counts) - min(counts) <= 1
        names = layout.bin_names + layout.cube_names
        assert len(set(names)) == len(names)
    assert max_trials <= cfg.max_trials


def test_颜色平衡轮转对任意个数都平衡():
    for order in ([0, 1, 2], [2, 0, 1], [1, 2, 0]):
        for n in range(0, 17):
            layout = S.DistractorLayout(bins=[(0.3, 0.0, 0.0)] * 16, cube_count=n, cube_bins=list(range(n)),
                                        color_order=order)
            counts = [layout.cube_colors.count(c["name"]) for c in DISTRACTOR_COLORS]
            assert max(counts) - min(counts) <= 1 and sum(counts) == n
            assert layout.cube_names == [f"distractor_cube_{j}_{c}" for j, c in enumerate(layout.cube_colors)]


def test_同一seed可复现且不同seed不同():
    cfg = S.V5_DISTRACTOR_PRESETS["VideoUnmask"]
    inner, buttons = _inner_scene("VideoUnmask", np.random.default_rng(7))
    obstacles = _obstacles(inner, buttons)
    a = S.sample_distractor_layout(cfg, obstacles=obstacles, generator=_gen(42), cube_half_size=CHS)
    b = S.sample_distractor_layout(cfg, obstacles=obstacles, generator=_gen(42), cube_half_size=CHS)
    c = S.sample_distractor_layout(cfg, obstacles=obstacles, generator=_gen(43), cube_half_size=CHS)
    assert a.to_spec() == b.to_spec() and a.trials == b.trials
    assert a.to_spec() != c.to_spec()


def test_随机调用序列与V4的VU_BU同构():
    """不给回调时：逐容器每次尝试 2 次 rand、通过后 1 次 rand(yaw) → randint → randperm(N) → randperm(3)。"""
    cfg = S.parse_distractor_cfg(S.V5_DISTRACTOR_PRESETS["ButtonUnmask"])
    inner, buttons = _inner_scene("ButtonUnmask", np.random.default_rng(11))
    layout = S.sample_distractor_layout(cfg, obstacles=_obstacles(inner, buttons), generator=(g := _gen(5)),
                                        cube_half_size=CHS)
    replay = _gen(5)
    n_rand = 2 * sum(layout.trials) + cfg.count
    torch.rand(n_rand, generator=replay)  # 按个数一次性抽，消耗与逐个抽相同
    lo, hi = cfg.cube_count_range
    assert int(torch.randint(lo, hi + 1, (1,), generator=replay).item()) == layout.cube_count
    assert torch.randperm(cfg.count, generator=replay)[: layout.cube_count].tolist() == layout.cube_bins
    assert torch.randperm(3, generator=replay).tolist() == layout.color_order
    assert torch.equal(torch.rand(4, generator=replay), torch.rand(4, generator=g))


def test_额外拒绝回调生效且可复核():
    cfg = S.V5_DISTRACTOR_PRESETS["VideoUnmaskSwap"]
    seen = []

    def reject_right_half(i, x, y, yaw, placed):
        seen.append((i, len(placed)))
        return x > 0.0

    layout = S.sample_distractor_layout(cfg, obstacles=[], generator=_gen(3), cube_half_size=CHS,
                                        extra_reject=reject_right_half)
    assert all(x <= 0.0 for x, _y, _yaw in layout.bins)
    assert all(i == n for i, n in seen)  # 回调拿到的「已放」列表长度 = 当前序号
    assert S.verify_distractor_layout(layout, cfg, obstacles=[], cube_half_size=CHS,
                                      extra_reject=reject_right_half) == []
    bad = S.DistractorLayout(bins=[(0.35, 0.0, 10.0)] + layout.bins[1:], cube_count=layout.cube_count,
                             cube_bins=layout.cube_bins, color_order=layout.color_order)
    assert S.verify_distractor_layout(bad, cfg, obstacles=[], cube_half_size=CHS, extra_reject=reject_right_half)


def test_放不下时抛候选级异常():
    cfg = dict(S.V5_DISTRACTOR_PRESETS["VideoUnmask"], max_trials=1, count=15)
    with pytest.raises(SceneGenerationError) as info:
        S.sample_distractor_layout(cfg, obstacles=[], generator=_gen(0), cube_half_size=CHS,
                                   extra_reject=lambda *a: True)
    assert isinstance(info.value, S.DistractorPlacementError) and info.value.placed == 0


def test_actor精确包围框与由位姿算出的一致(monkeypatch):
    """actor_obb2d_exact 读真实盒体：用容器的 6 个盒体与翻转位姿喂进去，应与 bin_obb2d 相同。"""
    x, y, yaw = 0.11, -0.07, 33.0
    p, q = bin_actor_pose([x, y], yaw, CHS)
    monkeypatch.setattr(S, "object_state_from_actor",
                        lambda actor, name=None: ObjectState(name="b", p=p, q=q, shapes=bin_shape_specs(CHS)))
    c1, a1, h1 = S.actor_obb2d_exact(object(), pad=MIN_GAP)
    c2, a2, h2 = S.bin_obb2d(x, y, yaw, CHS, pad=MIN_GAP)
    assert np.allclose(c1, c2, atol=1e-9) and np.allclose(h1, h2, atol=1e-9)
    assert np.allclose(np.abs(a1.T @ a2), np.eye(2), atol=1e-9) or np.allclose(np.abs(a1.T @ a2), np.eye(2)[::-1], atol=1e-9)


# ── 记录纪律（N18）与回放复核 ──────────────────────────────────────────────────────────
def _recorder(spec=None):
    return SpecRecorder(spec, task="VideoUnmaskSwap", difficulty="xhard")


def _value_paths(rec):
    return [t["path"] for t in rec.trace if t["source"] in ("draw", "spec")]


def test_整段重抽只在被接受的那次记录且回放逐值一致():
    cfg = S.V5_DISTRACTOR_PRESETS["VideoUnmaskSwap"]
    inner, buttons = _inner_scene("VideoUnmaskSwap", np.random.default_rng(3))
    obstacles = _obstacles(inner, buttons)

    def make_accept():
        calls = {"n": 0}

        def accept(layout):
            calls["n"] += 1
            perm = torch.randperm(layout.count, generator=gen).tolist()  # 接受回调可以接着抽同一条流
            if calls["n"] < 3:
                return False, f"window_infeasible_{calls['n']}"
            return True, {"perm": perm}

        return accept

    rec = _recorder()
    gen = _gen(99)
    layout, payload = S.resample_distractor_layout(cfg, obstacles=obstacles, generator=gen, cube_half_size=CHS,
                                                   recorder=rec, accept=make_accept(), max_attempts=16)
    paths = _value_paths(rec)
    assert paths.count("objects.distractors.cube_count") == 1
    assert sorted(p for p in paths if p.startswith("objects.distractors.bins.")) == sorted(
        f"objects.distractors.bins.{i}" for i in range(10))
    doc = rec.to_dict()
    assert doc["layout"]["distractor_layout_attempts"] == 3
    assert doc["layout"]["distractor_layout_failures"] == ["window_infeasible_1", "window_infeasible_2"]
    assert doc["objects"]["distractors"]["cube_names"] == layout.cube_names

    # 回放：同一条流重跑，返回冻结值，零不等
    replay = _recorder(doc)
    gen = _gen(99)
    layout2, payload2 = S.resample_distractor_layout(cfg, obstacles=obstacles, generator=gen, cube_half_size=CHS,
                                                     recorder=replay, accept=make_accept(), max_attempts=16)
    assert layout2.same_geometry(layout) and payload2 == payload and replay.mismatches == []


def test_回放篡改的冻结布局被拒():
    cfg = S.V5_DISTRACTOR_PRESETS["VideoUnmask"]
    inner, buttons = _inner_scene("VideoUnmask", np.random.default_rng(5))
    obstacles = _obstacles(inner, buttons)
    rec = _recorder()
    layout = S.sample_distractor_layout(cfg, obstacles=obstacles, generator=_gen(8), cube_half_size=CHS)
    S.commit_distractor_layout(layout, cfg=cfg, recorder=rec, obstacles=obstacles, cube_half_size=CHS)
    doc = rec.to_dict()
    doc["objects"]["distractors"]["bins"]["0"] = [0.0, 0.0, 0.0]  # 挪进内部
    with pytest.raises(SceneGenerationError):
        S.commit_distractor_layout(layout, cfg=cfg, recorder=_recorder(doc), obstacles=obstacles, cube_half_size=CHS)


def test_整段重抽全部失败抛错并留痕():
    rec = _recorder()
    with pytest.raises(SceneGenerationError):
        S.resample_distractor_layout(S.V5_DISTRACTOR_PRESETS["ButtonUnmaskSwap"], obstacles=[], generator=_gen(1),
                                     cube_half_size=CHS, recorder=rec, accept=lambda layout: (False, "no"),
                                     max_attempts=4)
    doc = rec.to_dict()
    assert doc["layout"]["distractor_layout_attempts"] == 4
    assert doc["layout"]["distractor_layout_failures"] == ["no"] * 4
    assert not any(p.startswith("objects.distractors.bins") for p in _value_paths(rec))


# ── 停放 helper（L14）──────────────────────────────────────────────────────────────
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
        return self.pose.p[0].numpy().astype(np.float64)


def test_停放点两两远离且不在旧停放点与场景附近():
    pts = [S.xhard_park_point(g, i) for g in S.XHARD_PARK_GROUPS for i in range(S.XHARD_PARK_GROUP_CAPACITY)]
    arr = np.asarray(pts, dtype=np.float64)
    d = np.linalg.norm(arr[:, None, :] - arr[None, :, :], axis=-1) + np.eye(len(arr)) * 1e9
    assert d.min() >= S.XHARD_PARK_PITCH_M - 1e-6
    assert S.XHARD_PARK_PITCH_M > 2 * 0.0425 + 0.1  # 远大于容器外接圆直径，下落一个控制步也碰不到
    assert np.linalg.norm(arr - np.array([10.0, 10.0, 10.0]), axis=1).min() > 5.0
    assert np.linalg.norm(arr, axis=1).min() > 10.0
    with pytest.raises(ValueError):
        S.xhard_park_point("distractor_bin", S.XHARD_PARK_GROUP_CAPACITY)
    with pytest.raises(ValueError):
        S.xhard_park_point("unknown", 0)


def test_揭示停放与statechange时间线逐步相同():
    from robomme.robomme_env.utils.statechange import lift_and_drop_objects_back_to_original

    class _Env:
        pass

    env_old, env_new = _Env(), _Env()
    origin = [0.3, -0.25, 0.052]
    old, new = _Actor(origin), _Actor(origin)
    park = S.xhard_park_point("distractor_bin", 3)
    for step in range(0, 70):
        lift_and_drop_objects_back_to_original(env_old, obj=old, start_step=0, end_step=64, cur_step=step)
        S.lift_and_park_back_to_original(env_new, new, 0, 64, step, park)
        away_old = np.allclose(old.xyz(), [10.0, 10.0, 10.0])
        away_new = np.allclose(new.xyz(), park)
        assert away_old == away_new, step
        if not away_old:
            assert np.allclose(old.xyz(), new.xyz()), step
    assert np.allclose(new.xyz(), origin, atol=1e-6)


def test_交换窗口cube停放与statechange时间线逐步相同():
    from robomme.robomme_env.utils.statechange import lift_and_drop_objectA_onto_objectB

    class _Env:
        cube_half_size = 0.02

    env_old, env_new = _Env(), _Env()
    cube_old, cube_new = _Actor([0.1, 0.1, 0.0167]), _Actor([0.1, 0.1, 0.0167])
    bin_actor = _Actor([0.1, 0.1, 0.052])
    park = S.xhard_park_point("distractor_cube", 4)
    for step in range(60, 140):
        if step == 100:
            bin_actor.pose = _Pose([-0.12, 0.2, 0.052])  # 交换中容器被挪走
        lift_and_drop_objectA_onto_objectB(env_old, obj_a=cube_old, obj_b=bin_actor, start_step=64, end_step=130,
                                           cur_step=step)
        S.lift_and_park_onto(env_new, cube_new, bin_actor, 64, 130, step, park)
        away_old = np.allclose(cube_old.xyz(), [10.0, 10.0, 10.0])
        assert away_old == np.allclose(cube_new.xyz(), park), step
        if not away_old:
            assert np.allclose(cube_old.xyz(), cube_new.xyz()), step
    assert np.allclose(cube_new.xyz(), [-0.12, 0.2, 0.0167], atol=1e-6)


def test_每个干扰容器与cube各停各的点():
    class _Env:
        pass

    env = _Env()
    env.distractor_bins = [_Actor([0.3, 0.05 * i, 0.052]) for i in range(15)]
    for step in range(0, 5):
        S.reveal_distractor_bins_parked(env, start_step=0, end_step=64, cur_step=step)
    parked = np.array([a.xyz() for a in env.distractor_bins])
    assert len({tuple(np.round(p, 4)) for p in parked}) == 15
    for i, p in enumerate(parked):
        assert np.allclose(p, S.xhard_park_point("distractor_bin", i))
    for step in range(5, 40):
        S.reveal_distractor_bins_parked(env, start_step=0, end_step=64, cur_step=step)
    assert np.allclose([a.xyz() for a in env.distractor_bins], [[0.3, 0.05 * i, 0.052] for i in range(15)], atol=1e-6)

    cubes = [_Actor([0.0, 0.0, 0.0167]) for _ in range(5)]
    bins = [_Actor([0.3, 0.1 * j, 0.052]) for j in range(5)]
    S.park_cubes_onto_bins(env, list(zip(cubes, bins)), group="distractor_cube", start_step=64, end_step=100,
                           cur_step=70)
    assert len({tuple(np.round(c.xyz(), 4)) for c in cubes}) == 5


# ── 密度推导锁定（计划 2.2：N = floor(ρ·A_usable + 0.5)，ρ = 50/m²，1 mm 网格）─────────────────────
def _vis_centers(x, y):
    """``visible_in_camera(bin_corners(x, y, 任意 yaw 外接半边, 高度))`` 的向量化版本。"""
    eye, fwd, right, up = _camera_axes(BASE_CAMERA_EYE, BASE_CAMERA_TARGET)
    tan = math.tan(BASE_CAMERA_FOV / 2)
    ok = np.ones(x.shape, bool)
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            for z in (0.0, HEIGHT):
                d = np.stack([x + sx * REACH_ANY_YAW - eye[0], y + sy * REACH_ANY_YAW - eye[1],
                              np.full_like(x, z - eye[2])], axis=-1)
                depth = d @ fwd
                ok &= depth > 1e-6
                safe = np.where(depth > 1e-6, depth, 1.0)
                ok &= np.abs((d @ right) / safe) / tan <= 1.0
                ok &= np.abs((d @ up) / safe) / tan <= 1.0
    return ok


def _usable_area(step, button):
    from scipy.ndimage import maximum_filter

    xs = np.arange(-0.6 + step / 2, 0.5, step)
    ys = np.arange(-0.6 + step / 2, 0.6, step)
    x, y = np.meshgrid(xs, ys, indexing="ij")
    cheb = np.maximum(np.maximum(np.abs(x) - 0.2, 0.0), np.maximum(np.abs(y) - 0.2, 0.0))  # 内部 [-0.2,0.2]²
    g, w = S.V5_RING_GAP_M, S.V5_RING_BAND_WIDTH_M
    centers = (cheb >= g + HALF) & (cheb <= g + w - HALF) & _vis_centers(x, y)
    footprint_band = (cheb >= g) & (cheb <= g + w)
    k = int(round(2 * HALF / step)) + 1
    footprint = (maximum_filter(centers.astype(np.uint8), size=k) > 0) & footprint_band
    block = 0.0
    if button:
        # 按钮中心 (-0.2, 0) + U(±0.05)²：用 21×21 中点网格取期望（计划用 300 次蒙特卡洛，结果 5.7%）
        cx, cy = x[centers], y[centers]
        acc = np.zeros(cx.shape)
        offsets = (np.arange(21) + 0.5) / 21 - 0.5
        for ox in offsets:
            for oy in offsets:
                bx, by = -0.2 + ox * 0.1, oy * 0.1
                dist = np.hypot(np.maximum(np.abs(cx - bx) - BTN_HALF, 0), np.maximum(np.abs(cy - by) - BTN_HALF, 0))
                acc += dist < HALF + MIN_GAP
        block = float(acc.sum() / (len(offsets) ** 2) / centers.sum())
    return float(footprint.sum() * step * step * (1.0 - block)), block


def test_VU_BU密度推导锁定15与14():
    g, w = S.V5_RING_GAP_M, S.V5_RING_BAND_WIDTH_M
    assert w == pytest.approx(0.1414, abs=1e-4)
    ring = [round(0.2 + g + HALF, 4), round(0.2 + g + w - HALF, 4)]
    for env in ("VideoUnmask", "ButtonUnmask"):
        assert S.V5_DISTRACTOR_PRESETS[env]["ring_max_abs_xy"] == ring == [0.2425, 0.3289]

    area_vu, _ = _usable_area(0.001, button=False)
    area_bu, block = _usable_area(0.001, button=True)
    n_vu = int(math.floor(S.V5_INNER_DENSITY_PER_M2 * area_vu + 0.5))
    n_bu = int(math.floor(S.V5_INNER_DENSITY_PER_M2 * area_bu + 0.5))
    assert area_vu == pytest.approx(0.3027, abs=5e-4)
    assert area_bu == pytest.approx(0.2853, abs=2e-3) and block == pytest.approx(0.057, abs=0.005)
    assert (n_vu, n_bu) == (15, 14)
    assert (S.V5_DISTRACTOR_PRESETS["VideoUnmask"]["count"], S.V5_DISTRACTOR_PRESETS["ButtonUnmask"]["count"]) == (15, 14)
    # 离取整边界足够远：口径小变动不会翻转
    for area in (area_vu, area_bu):
        assert abs((S.V5_INNER_DENSITY_PER_M2 * area) % 1.0 - 0.5) > 0.1
