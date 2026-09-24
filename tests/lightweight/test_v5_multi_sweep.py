"""V5 S2b：``bin_collision.check_multi_swap_sweep`` 与认证预筛的定向测试。

对应 NEWTASK_RELEASE_V5_PLAN 2.5「关键设计点」、L23（认证预筛开启）、L54（按钮底座作静止障碍）与
第二部分「一」S2 行。覆盖：

* 单对时与 ``check_swap_sweep`` 大量随机样例逐位等价（含接触拒绝）；
* 预筛开/关判定与拒绝证据一致，预筛的 Lipschitz 下界不高估真实圆柱间隙；
* 远处加第二对不改变结果、两对交叉必撞被拒；
* 静止矩形 / 二维 OBB / 按钮底座作 bystander 生效；
* ``check_swap_sweep`` 原函数从不走预筛。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme.robomme_env.utils import bin_collision as bc  # noqa: E402

CUBE_HALF = 0.02


def _bin_state(name: str, xy, yaw_deg: float = 0.0) -> bc.ObjectState:
    p, q = bc.bin_actor_pose(xy, yaw_deg, CUBE_HALF)
    return bc.ObjectState(name=name, p=p, q=q, shapes=bc.bin_shape_specs(CUBE_HALF))


def _cube_state(name: str, xy, yaw_rad: float = 0.0, half: float = CUBE_HALF) -> bc.ObjectState:
    p, q = bc.cube_actor_pose(xy, yaw_rad, half)
    return bc.ObjectState(name=name, p=p, q=q, shapes=bc.cube_shape_specs(half))


def _random_scene(rng: np.random.Generator) -> list[bc.ObjectState]:
    """2～5 个同类对象随机撒在 0.36 m 见方里：前两个交换，其余静止；会自然出现接触拒绝。"""
    kind = rng.choice(["bin", "cube"])
    count = int(rng.integers(2, 6))
    objects = []
    for i in range(count):
        xy = rng.uniform(-0.18, 0.18, 2)
        yaw_deg = float(rng.uniform(0.0, 360.0))
        if kind == "bin":
            objects.append(_bin_state(f"bin_{i}", xy, yaw_deg))
        else:
            objects.append(_cube_state(f"cube_{i}", xy, math.radians(yaw_deg)))
    return objects


def _as_dict(rejection):
    return None if rejection is None else rejection.as_dict()


def _same_gap(g1: float, g2: float) -> bool:
    return g1 == g2 or (math.isnan(g1) and math.isnan(g2))


# ── 单对与 check_swap_sweep 逐位等价 ──────────────────────────────────────────
def test_单对随机样例与原函数逐位相同且预筛不改判定():
    rng = np.random.default_rng(20260924)
    reasons = {"contact": 0, "pass": 0}
    for k in range(18):
        objects = _random_scene(rng)
        a, b, bystanders = objects[0], objects[1], objects[2:]
        ref_gap, ref_rej = bc.check_swap_sweep(a, b, bystanders, sweep_index=k)
        off_gap, off_rej = bc.check_multi_swap_sweep([(a, b)], bystanders, sweep_index=k, prefilter=False)
        on_gap, on_rej = bc.check_multi_swap_sweep([(a, b)], bystanders, sweep_index=k, prefilter=True)
        wrap_gap, wrap_rej = bc.check_swap_sweep_prefiltered(a, b, bystanders, sweep_index=k, prefilter=False)
        # 预筛关：返回值逐位相同（最小 g 与整份拒绝证据）
        assert _same_gap(ref_gap, off_gap), (k, ref_gap, off_gap)
        assert _as_dict(ref_rej) == _as_dict(off_rej), k
        assert _same_gap(ref_gap, wrap_gap) and _as_dict(ref_rej) == _as_dict(wrap_rej), k
        # 预筛开：判定与拒绝证据逐位相同；拒绝时 g 也相同（来自同一个被证否的盒对）
        assert _as_dict(ref_rej) == _as_dict(on_rej), k
        if ref_rej is not None:
            assert _same_gap(ref_gap, on_gap)
            reasons[ref_rej.reason] = reasons.get(ref_rej.reason, 0) + 1
        else:
            reasons["pass"] += 1
    # 样本里既要有接触拒绝，也要有通过，否则等价性没有覆盖到两条分支
    assert reasons["contact"] >= 4 and reasons["pass"] >= 4, reasons


def test_单对已知接触样例逐位相同():
    """复用 test_bin_collision 的中途压住旁观对象的样例：端点都分开、弯道顶点撞上。"""
    a = _bin_state("bin_0", [-0.05, -0.06])
    b = _bin_state("bin_1", [0.06, -0.06])
    bystander = _bin_state("bin_2", [0.005, 0.01])
    ref = bc.check_swap_sweep(a, b, [bystander], sweep_index=3)
    for prefilter in (False, True):
        got = bc.check_multi_swap_sweep([(a, b)], [bystander], sweep_index=3, prefilter=prefilter)
        assert _same_gap(ref[0], got[0]) and _as_dict(ref[1]) == _as_dict(got[1])
    assert ref[1].reason == "contact"


def test_二分耗尽时预筛不会替近处的对放行(monkeypatch):
    """贴着弯道的旁观对象离得太近，预筛证不出分离，仍交给精确证明报 uncertified。

    这里人为把 ``MAX_DEPTH`` 压到 1，也顺带演示了文档里写明的唯一理论分歧：交换双方自身其实相距很远
    （竖直圆柱间隙 > 1 mm），不预筛时精确证明因深度耗尽先在这一对上报 uncertified；预筛已证明它分离、
    直接跳过，于是拒绝落在下一个真正贴近的对（旁观对象）上。判定（拒绝、uncertified）不变，证据指向的
    对象对不同。真实常量（深度 20、区间 4096）下大样本未见此分歧（见 S2b 报告）。
    """
    monkeypatch.setattr(bc, "MAX_DEPTH", 1)
    a = _bin_state("bin_0", [-0.05, -0.06])
    b = _bin_state("bin_1", [0.06, -0.06])
    bystander = _bin_state("bin_2", [-0.01, 0.082])
    ref = bc.check_swap_sweep(a, b, [bystander])
    off = bc.check_multi_swap_sweep([(a, b)], [bystander], prefilter=False)
    got = bc.check_multi_swap_sweep([(a, b)], [bystander], prefilter=True)
    assert ref[1] is not None and ref[1].reason == "uncertified"
    assert _as_dict(ref[1]) == _as_dict(off[1])
    assert (ref[1].object_a, ref[1].object_b) == ("bin_0", "bin_1")
    assert got[1] is not None and got[1].reason == "uncertified"
    assert got[1].object_b == "bin_2"


def test_四元数退化时预筛开关结论相同():
    a = _bin_state("bin_0", [-0.05, 0.0])
    b = _bin_state("bin_1", [0.05, 0.0])
    b = bc.ObjectState(name=b.name, p=b.p, q=-a.q, shapes=b.shapes)
    far = _bin_state("bin_far", [0.0, 0.4])
    ref = bc.check_swap_sweep(a, b, [far])
    for prefilter in (False, True):
        got = bc.check_multi_swap_sweep([(a, b)], [far], prefilter=prefilter)
        assert _as_dict(ref[1]) == _as_dict(got[1])
    assert ref[1].reason == "uncertified"


def test_原函数从不走预筛(monkeypatch):
    """check_swap_sweep 与 prefilter=False 的新函数都不得调用预筛代码。"""

    def boom(*_args, **_kwargs):
        raise AssertionError("预筛被调用了")

    monkeypatch.setattr(bc, "_prefilter_track", boom)
    a = _bin_state("bin_0", [-0.05, -0.06])
    b = _bin_state("bin_1", [0.06, -0.06])
    by = [_bin_state("bin_2", [0.0, 0.2])]
    bc.check_swap_sweep(a, b, by)
    bc.check_multi_swap_sweep([(a, b)], by, prefilter=False)
    with pytest.raises(AssertionError, match="预筛被调用"):
        bc.check_multi_swap_sweep([(a, b)], by, prefilter=True)


# ── 多对：预筛开/关一致、远处第二对、交叉必撞 ─────────────────────────────────
def _swap_like_scene(rng: np.random.Generator):
    """内环 4 个容器（|x|,|y| ≤ 0.2）+ 外环 6 个干扰容器（max(|x|,|y|) ∈ [0.2675, 0.45]），各取一对交换。"""

    def place(n, sampler, min_dist, existing):
        out = []
        while len(out) < n:
            xy = sampler()
            if all(np.linalg.norm(xy - e) >= min_dist for e in existing + out):
                out.append(xy)
        return out

    def ring():
        while True:
            xy = rng.uniform(-0.45, 0.45, 2)
            if np.max(np.abs(xy)) >= 0.2675:
                return xy

    inner = place(4, lambda: rng.uniform(-0.2, 0.2, 2), 0.065, [])
    outer = place(6, ring, 0.07, inner)
    ib = [_bin_state(f"bin_{i}", xy, float(rng.uniform(0, 360))) for i, xy in enumerate(inner)]
    ob = [_bin_state(f"distractor_bin_{i}", xy, float(rng.uniform(0, 360))) for i, xy in enumerate(outer)]

    def nearest(pos, i):
        return int(np.argmin([np.linalg.norm(pos[i] - p) if j != i else np.inf for j, p in enumerate(pos)]))

    a = int(rng.integers(0, 4))
    p = nearest(inner, a)
    o = int(rng.integers(0, 6))
    q = nearest(outer, o)
    pairs = [(ib[a], ib[p]), (ob[o], ob[q])]
    bystanders = [s for j, s in enumerate(ib) if j not in (a, p)] + [s for j, s in enumerate(ob) if j not in (o, q)]
    return pairs, bystanders


def test_两对联合时预筛开关判定与证据一致():
    rng = np.random.default_rng(7)
    total_skipped = 0
    for k in range(4):
        pairs, bystanders = _swap_like_scene(rng)
        stats: dict[str, int] = {}
        off = bc.check_multi_swap_sweep(pairs, bystanders, sweep_index=k, prefilter=False)
        on = bc.check_multi_swap_sweep(pairs, bystanders, sweep_index=k, prefilter=True, stats=stats)
        assert _as_dict(off[1]) == _as_dict(on[1]), k
        total_skipped += stats["prefilter_skipped"]
        assert stats["object_pairs"] == stats["coarse_skipped"] + stats["prefilter_skipped"] + stats["proved_object_pairs"] or on[1] is not None
    assert total_skipped > 0  # 预筛确实在起作用


def test_远处加第二对不改变结果():
    rng = np.random.default_rng(11)
    far_pair = (_bin_state("distractor_bin_0", [5.0, 5.0], 10.0), _bin_state("distractor_bin_1", [5.15, 5.0], 30.0))
    # 远处那一对自身的交换也要精确证明，它的最小 g 会参与「通过时的最小 g」，所以通过时比较的是
    # min(近处单查, 远处单查)；判定与拒绝证据必须与近处单查逐位相同。
    far_gap = bc.check_multi_swap_sweep([far_pair], [], prefilter=False)[0]
    seen_reject = seen_pass = False
    for k in range(8):
        objects = _random_scene(rng)
        a, b, bystanders = objects[0], objects[1], objects[2:]
        ref = bc.check_swap_sweep(a, b, bystanders, sweep_index=k)
        for prefilter in (False, True):
            single = bc.check_multi_swap_sweep([(a, b)], bystanders, sweep_index=k, prefilter=prefilter)
            double = bc.check_multi_swap_sweep([(a, b), far_pair], bystanders, sweep_index=k, prefilter=prefilter)
            assert _as_dict(single[1]) == _as_dict(double[1]), (k, prefilter)
            if single[1] is not None:
                assert _same_gap(single[0], double[0])
            elif not prefilter:
                # 预筛开时远处那一对会被预筛跳过、不进最小 g，通过时的数值不作比较
                assert double[0] == min(single[0], far_gap)
        assert _as_dict(ref[1]) == _as_dict(double[1])
        seen_reject |= ref[1] is not None
        seen_pass |= ref[1] is None
    assert seen_reject and seen_pass


def _crossing_pairs():
    """两对平行交换，弦线相距 0.14：第一对 A 向 +y 鼓 0.07、第二对 B 向 −y 鼓 0.07，中点正好相撞。"""
    first = (_bin_state("bin_0", [-0.1, 0.0]), _bin_state("bin_1", [0.1, 0.0]))
    second = (_bin_state("distractor_bin_0", [-0.1, 0.14]), _bin_state("distractor_bin_1", [0.1, 0.14]))
    return first, second


def test_两对交叉必撞被拒而各自单查都通过():
    first, second = _crossing_pairs()
    # 各自单查：另一对在起点位置不动，两对都能证明分离
    assert bc.check_swap_sweep(*first, list(second))[1] is None
    assert bc.check_swap_sweep(*second, list(first))[1] is None
    for prefilter in (False, True):
        _, rejection = bc.check_multi_swap_sweep([first, second], [], sweep_index=5, prefilter=prefilter)
        assert rejection is not None and rejection.reason == "contact"
        assert {rejection.object_a, rejection.object_b} == {"bin_0", "distractor_bin_1"}
        assert rejection.stage == "sweep" and rejection.sweep_index == 5
        assert 0.0 < rejection.s < 1.0
    with pytest.raises(bc.BinCollisionError):
        bc.check_multi_swap_sweep([first, second], [], raise_on_reject=True)


def test_同一对象不能出现两次():
    first, second = _crossing_pairs()
    with pytest.raises(ValueError, match="重复"):
        bc.check_multi_swap_sweep([first, (first[0], second[0])], [])
    with pytest.raises(ValueError, match="重复"):
        bc.check_multi_swap_sweep([first], [first[1]])
    with pytest.raises(ValueError):
        bc.check_multi_swap_sweep([], [])


# ── 预筛下界的正确性 ─────────────────────────────────────────────────────────
def _true_cylinder_gap(left, right, s_values):
    """逐个 s 用 pose_at 精确算竖直圆柱间隙（对象全部顶点到原点竖直轴的最大水平距离）。"""
    verts_l = bc._local_vertices(left.shapes)
    verts_r = bc._local_vertices(right.shapes)
    out = []
    for s in s_values:
        pl, ql = left.pose_at(float(s))
        pr, qr = right.pose_at(float(s))
        rho_l = np.max(np.linalg.norm((verts_l @ bc.quat_to_matrix(ql).T)[:, :2], axis=1))
        rho_r = np.max(np.linalg.norm((verts_r @ bc.quat_to_matrix(qr).T)[:, :2], axis=1))
        out.append(float(np.linalg.norm(pl[:2] - pr[:2])) - rho_l - rho_r)
    return np.array(out)


def test_预筛下界不高估真实圆柱间隙():
    rng = np.random.default_rng(3)
    samples = bc._prefilter_samples()
    step = float(samples[1] - samples[0])
    dense = np.linspace(0.0, 1.0, 2001)
    for _ in range(6):
        a = _bin_state("a", rng.uniform(-0.2, 0.2, 2), float(rng.uniform(0, 360)))
        b = _bin_state("b", rng.uniform(-0.2, 0.2, 2), float(rng.uniform(0, 360)))
        other = _cube_state("c", rng.uniform(-0.3, 0.3, 2), float(rng.uniform(0, 6.28)))
        mover_a, mover_b = bc._swap_movers(a, b)
        static = bc._Static(name=other.name, shapes=other.shapes, radii=other.radii, p=other.p, q=other.q)
        for left, right in ((mover_a, mover_b), (mover_a, static), (mover_b, static)):
            bound = bc._prefilter_clearance(bc._prefilter_track(left, samples), bc._prefilter_track(right, samples), step)
            truth = _true_cylinder_gap(left, right, dense)
            assert bound <= float(np.min(truth)) + 1e-12


def test_预筛常量():
    assert bc.PREFILTER_SAMPLES == 401
    assert bc.PREFILTER_MARGIN_M == 1e-3
    assert bc._prefilter_samples().shape == (401,)


# ── 静止矩形 / OBB / 按钮底座 ────────────────────────────────────────────────
def test_静止盒体的几何与分离轴判定值():
    box = bc.static_box_state("box", [0.3, 0.0, 0.01], [0.05, 0.02, 0.01])
    cube = _cube_state("cube", [0.0, 0.0])
    gap, rejection = bc.check_bin_layout([box, cube], exhaustive=True)
    assert rejection is None
    assert pytest.approx(gap, abs=1e-12) == 0.3 - 0.05 - 0.02
    rect = bc.static_rect_state("rect", [0.3, 0.0], [0.05, 0.02], z_range=(0.0, 0.02))
    assert np.allclose(rect.p, box.p) and np.allclose(rect.shapes[0].half, box.shapes[0].half)
    with pytest.raises(ValueError):
        bc.static_rect_state("bad", [0.0, 0.0], [0.01, 0.01], z_range=(0.02, 0.0))
    with pytest.raises(ValueError):
        bc.static_box_state("bad", [0.0, 0.0, 0.0], [0.01, 0.0, 0.01])


def test_二维OBB三元组转静止盒体保持朝向():
    yaw = math.radians(30.0)
    axes = np.array([[math.cos(yaw), -math.sin(yaw)], [math.sin(yaw), math.cos(yaw)]])
    obb = (np.array([0.1, -0.2]), axes, np.array([0.04, 0.01]))
    state = bc.static_state_from_obb2d("obb", obb, z_range=(0.0, 0.05))
    expected = bc.static_rect_state("obb", [0.1, -0.2], [0.04, 0.01], yaw_rad=yaw, z_range=(0.0, 0.05))
    assert np.allclose(state.p, expected.p) and np.allclose(state.q, expected.q)
    # 左手系的轴（扣放容器投影）也接受，矩形关于轴对称
    flipped = (obb[0], axes * np.array([1.0, -1.0]), obb[2])
    assert np.allclose(bc.static_state_from_obb2d("obb", flipped, z_range=(0.0, 0.05)).q, expected.q)
    # create_button_obb 的格式：单位阵
    button_obb = (np.array([0.2, 0.1]), np.eye(2), np.array([0.0375, 0.0375]))
    assert bc.static_state_from_obb2d("btn", button_obb, z_range=(0.0, 0.01)).shapes[0].half[0] == pytest.approx(0.0375)
    with pytest.raises(ValueError, match="单位正交"):
        bc.static_state_from_obb2d("bad", (obb[0], np.array([[1.0, 0.5], [0.0, 1.0]]), obb[2]), z_range=(0.0, 0.05))


def test_按钮底座复刻build_button的碰撞盒():
    base = bc.button_base_state("button", [0.15, 0.1], scale=1.2)
    assert np.allclose(base.shapes[0].half, [0.03, 0.03, 0.006])
    assert np.allclose(base.p, [0.15, 0.1, 0.006])


def test_静止矩形作bystander生效():
    """方块交换（VideoRepick 的用法）：按钮底座压在 A 的弯道顶点上 → 被拒；挪远 → 通过。"""
    a = _cube_state("cube_0", [-0.1, 0.0])
    b = _cube_state("cube_1", [0.1, 0.0])
    assert bc.check_swap_sweep(a, b)[1] is None
    on_lane = bc.button_base_state("button", [0.0, 0.07])
    far = bc.button_base_state("button", [0.0, 0.3])
    for prefilter in (False, True):
        _, rejection = bc.check_multi_swap_sweep([(a, b)], [on_lane], prefilter=prefilter)
        assert rejection is not None and rejection.reason == "contact"
        assert rejection.object_a == "cube_0" and rejection.object_b == "button"
        assert bc.check_multi_swap_sweep([(a, b)], [far], prefilter=prefilter)[1] is None
    # 原函数同样认这个静止盒体（它只是一个 ObjectState）
    assert _as_dict(bc.check_swap_sweep(a, b, [on_lane])[1]) == _as_dict(
        bc.check_multi_swap_sweep([(a, b)], [on_lane], prefilter=True)[1]
    )
    # 二维 OBB 形式的有向矩形同样生效
    rect = bc.static_state_from_obb2d(
        "rect", (np.array([0.0, -0.07]), np.eye(2), np.array([0.01, 0.01])), z_range=(0.0, 0.01)
    )
    _, rejection = bc.check_multi_swap_sweep([(a, b)], [rect])
    assert rejection is not None and rejection.object_b == "rect"


def test_统计字典累加():
    first, second = _crossing_pairs()
    stats: dict[str, int] = {}
    far = _bin_state("bin_far", [0.0, 0.8])
    bc.check_multi_swap_sweep([first], [far], stats=stats)
    bc.check_multi_swap_sweep([first], [far], stats=stats)
    assert stats["object_pairs"] == 6 and stats["coarse_skipped"] == 4
    assert stats["proved_object_pairs"] + stats["prefilter_skipped"] == 2
