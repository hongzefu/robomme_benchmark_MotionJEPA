"""``bin_collision`` 的定向测试：几何同源、SAT 判据、连续区间证明与具名拒绝。

覆盖 NEW_VALUE_INJECTION_TEST_PLAN 第 5.7 节 ``COLLISION_GEOMETRY``／``COLLISION_SWEEP``
两项判据的可测部分：真实盒体数与半尺寸、旋转角点接触、相切、帧间穿越、深度与区间上限
耗尽、四元数退化，以及已获用户目视确认的四容器三例判定值。
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


# ── 几何同源 ────────────────────────────────────────────────────────────────
def test_容器是六个盒体而不是注释说的五个():
    shapes = bc.bin_shape_specs(CUBE_HALF)
    assert len(shapes) == 6
    # 第 0 个是 build_bin 里注释没提、但源码确实建了的中央方块
    assert np.allclose(shapes[0].local_p, [0.0, 0.0, 0.0])
    assert np.allclose(shapes[0].half, [0.02, 0.02, 0.02])


def test_容器盒体半尺寸与局部中心对齐计划第八点一节的表():
    expected = [
        ([0.0, 0.0, 0.0], [0.02, 0.02, 0.02]),
        ([0.0, 0.0, 0.002], [0.0275, 0.0275, 0.002]),
        ([-0.0275, 0.0, 0.027], [0.0025, 0.0275, 0.025]),
        ([0.0275, 0.0, 0.027], [0.0025, 0.0275, 0.025]),
        ([0.0, -0.0275, 0.027], [0.0275, 0.0025, 0.025]),
        ([0.0, 0.0275, 0.027], [0.0275, 0.0025, 0.025]),
    ]
    for shape, (p, half) in zip(bc.bin_shape_specs(CUBE_HALF), expected):
        assert np.allclose(shape.local_p, p, atol=1e-12)
        assert np.allclose(shape.half, half, atol=1e-12)


def test_方块是单个盒体且边长零点零四():
    shapes = bc.cube_shape_specs(CUBE_HALF)
    assert len(shapes) == 1
    assert np.allclose(shapes[0].half, [0.02, 0.02, 0.02])


def test_容器外宽零点零六且由前后壁给出():
    """外宽 2×(0.0275+0.0025)=0.06；前后壁在 y 上延伸最远，不是底板。"""
    shapes = bc.bin_shape_specs(CUBE_HALF)
    reach = [abs(s.local_p[1]) + s.half[1] for s in shapes]
    assert pytest.approx(max(reach), abs=1e-12) == 0.03
    assert reach.index(max(reach)) in (4, 5)


def test_容器落点高度与四容器案例的零点零五二一致():
    p, _ = bc.bin_actor_pose([0.0, 0.0], 0.0, CUBE_HALF)
    assert pytest.approx(float(p[2]), abs=1e-12) == 0.052


def test_欧拉转四元数与_maniskill_的实现逐值一致():
    torch = pytest.importorskip("torch")
    from mani_skill.utils.geometry.rotation_conversions import (
        euler_angles_to_matrix,
        matrix_to_quaternion,
    )

    for angles in ([math.pi, 0.0, 0.3], [0.0, 0.0, 1.7], [math.pi, 0.0, -0.9], [0.2, 0.3, 0.4]):
        mine = bc.euler_xyz_to_quat(angles)
        ref_mat = euler_angles_to_matrix(torch.tensor([angles], dtype=torch.float64), convention="XYZ")
        ref = matrix_to_quaternion(ref_mat)[0].numpy()
        if ref[0] < 0:
            ref = -ref
        assert np.allclose(mine, ref, atol=1e-12), (angles, mine, ref)


# ── 静态判据 ────────────────────────────────────────────────────────────────
def test_分离的两个容器判定值等于实际间隙():
    a = _bin_state("bin_0", [0.0, 0.0])
    b = _bin_state("bin_1", [0.0, 0.12])
    gap, rejection = bc.check_bin_layout([a, b])
    assert rejection is None
    assert pytest.approx(gap, abs=1e-12) == 0.12 - 0.06


def test_相切一样排除():
    """外壁正好贴合，理论 g == 0，落在 ε 带内必须排除。

    ⚠ 这里不断言 ``reason`` 具体是哪一个：g 的浮点实算是 ±1e-18 量级的噪声，
    落在 ``contact``（g<0）还是 ``numerical_boundary``（0≤g≤ε）取决于最后一位舍入。
    计划真正要保证的是「相切不放行」，两个标签在 ε 带内等价。
    """
    a = _bin_state("bin_0", [0.0, 0.0])
    b = _bin_state("bin_1", [0.0, 0.06])
    gap, rejection = bc.check_bin_layout([a, b])
    assert rejection is not None
    assert rejection.reason in {"contact", "numerical_boundary"}
    assert abs(gap) <= bc.EPS_M


def test_拒绝证据指向判定值最小的盒对而不是遍历里第一个():
    """中心距 0.04：中央方块与前壁那一对恰好 g==0，但真正的穿入是 g=−0.01 的壁对壁。"""
    a = _bin_state("bin_0", [0.0, 0.0])
    b = _bin_state("bin_1", [0.0, 0.04])
    gap, rejection = bc.check_bin_layout([a, b])
    assert pytest.approx(gap, abs=1e-12) == -0.01
    assert rejection.reason == "contact"
    assert pytest.approx(rejection.gap_m, abs=1e-12) == -0.01


def test_落在数值边界带内也排除():
    a = _bin_state("bin_0", [0.0, 0.0])
    b = _bin_state("bin_1", [0.0, 0.06 + bc.EPS_M / 2])
    _, rejection = bc.check_bin_layout([a, b])
    assert rejection is not None and rejection.reason == "numerical_boundary"


def test_刚过阈值就放行():
    a = _bin_state("bin_0", [0.0, 0.0])
    b = _bin_state("bin_1", [0.0, 0.06 + 2 * bc.EPS_M])
    _, rejection = bc.check_bin_layout([a, b])
    assert rejection is None


def test_穿入记为接触类拒绝():
    """中心距 0.04 < 外宽 0.06，前后壁真的插进去；⚠ 0.05 只会让两侧壁相切，不是穿入。"""
    a = _bin_state("bin_0", [0.0, 0.0])
    b = _bin_state("bin_1", [0.0, 0.04])
    gap, rejection = bc.check_bin_layout([a, b])
    assert rejection is not None and rejection.reason == "contact"
    assert gap < 0


def test_旋转四十五度后的角点接触能被查出来():
    """中心距沿 x 是 0.062 > 0.06，不转时分开；转 45° 后角点伸到 0.0424 会撞上。"""
    straight = bc.check_bin_layout([_bin_state("a", [0.0, 0.0]), _bin_state("b", [0.062, 0.0])])
    assert straight[1] is None
    turned = bc.check_bin_layout(
        [_bin_state("a", [0.0, 0.0], yaw_deg=45.0), _bin_state("b", [0.062, 0.0], yaw_deg=45.0)]
    )
    assert turned[1] is not None and turned[1].reason == "contact"


def test_全部对象对都查而不是只查交换双方():
    """0 与 1 分开、0 与 2 撞上：必须由第三对触发拒绝。"""
    states = [
        _bin_state("bin_0", [0.0, 0.0]),
        _bin_state("bin_1", [0.0, 0.2]),
        _bin_state("bin_2", [0.03, 0.0]),
    ]
    _, rejection = bc.check_bin_layout(states)
    assert rejection is not None
    assert {rejection.object_a, rejection.object_b} == {"bin_0", "bin_2"}


def test_三个方块两两之间也查():
    states = [
        _cube_state("cube_0", [0.0, 0.0]),
        _cube_state("cube_1", [0.1, 0.0]),
        _cube_state("cube_2", [0.0, 0.03]),
    ]
    _, rejection = bc.check_bin_layout(states)
    assert rejection is not None and {rejection.object_a, rejection.object_b} == {"cube_0", "cube_2"}


# ── 四容器三例（用户已目视确认的固定案例）─────────────────────────────────────
@pytest.mark.parametrize(
    ("delta", "expected_gap", "should_reject"),
    [
        (0.012, 0.012, False),
        (0.0002, 0.0002, False),
        (-0.0002, -0.0002, True),
    ],
)
def test_四容器三例在路程中点的判定值可复现(delta: float, expected_gap: float, should_reject: bool):
    """artifacts/collision-preplan/20260909-bin-contact-v2 的 bin4-* 三例。

    交换 0↔1、旁观 2/3；最接近姿态在第 25/50 步，即 smoothstep 后 s=0.5、侧移 0.07 米。
    此处直接按 s=0.5 复算 0 号与 2 号的分离值，检查判据方向与量级，
    保存证据里的 float32 位姿会带 ~5e-9 的偏差，故用 1e-8 容差。
    """
    moving_a = _bin_state("bin_0", [-0.05, -0.06])
    moving_b = _bin_state("bin_1", [0.06, -0.06])
    bystander = _bin_state("bin_2", [-0.01, 0.07 + delta])

    a_xy = moving_a.p[:2]
    b_xy = moving_b.p[:2]
    dxy = b_xy - a_xy
    normal = np.array([-dxy[1], dxy[0]])
    normal = normal / np.linalg.norm(normal)
    s = 0.5
    mid_xy = a_xy + dxy * s + normal * (bc.LANE_OFFSET * math.sin(math.pi * s))
    moved = _bin_state("bin_0", mid_xy)

    gap, rejection = bc.check_pair_static(moved, bystander)
    assert pytest.approx(gap, abs=1e-8) == expected_gap
    assert (rejection is not None) is should_reject


# ── 连续判据 ────────────────────────────────────────────────────────────────
def test_端点都通过但中途穿过旁观对象必须被拒():
    """0↔1 沿 y 正向弯道交换，旁观 2 正好压在弯道顶点上；两端都分开。"""
    moving_a = _bin_state("bin_0", [-0.05, -0.06])
    moving_b = _bin_state("bin_1", [0.06, -0.06])
    bystander = _bin_state("bin_2", [0.005, 0.01])  # 恰好是 s=0.5 时 A 的位置

    assert bc.check_bin_layout([moving_a, moving_b, bystander])[1] is None
    _, rejection = bc.check_swap_sweep(moving_a, moving_b, [bystander], sweep_index=0)
    assert rejection is not None and rejection.reason == "contact"
    assert rejection.stage == "sweep" and rejection.sweep_index == 0


def test_旁观对象离得够远时整段路径能被证明分离():
    moving_a = _bin_state("bin_0", [-0.05, -0.06])
    moving_b = _bin_state("bin_1", [0.06, -0.06])
    bystander = _bin_state("bin_2", [-0.01, 0.30])
    gap, rejection = bc.check_swap_sweep(moving_a, moving_b, [bystander])
    assert rejection is None and gap > bc.EPS_M


def test_交换双方自身在弯道中段互相错开():
    """A 走上弯道、B 走下弯道，中段侧移 2×0.07 足以让两个容器错开。"""
    gap, rejection = bc.check_swap_sweep(
        _bin_state("bin_0", [-0.05, 0.0]), _bin_state("bin_1", [0.05, 0.0])
    )
    assert rejection is None and gap > bc.EPS_M


def test_起终点重合时法向取零并保留端点检查():
    """原函数在 XY 距离 ≤1e-9 时法向取零，此时两个对象重叠，端点即判拒。"""
    a = _bin_state("bin_0", [0.0, 0.0])
    b = _bin_state("bin_1", [0.0, 0.0])
    _, rejection = bc.check_swap_sweep(a, b)
    assert rejection is not None and rejection.reason == "contact"


def test_深度上限耗尽记为无法证明安全而不是通过(monkeypatch):
    monkeypatch.setattr(bc, "MAX_DEPTH", 1)
    moving_a = _bin_state("bin_0", [-0.05, -0.06])
    moving_b = _bin_state("bin_1", [0.06, -0.06])
    bystander = _bin_state("bin_2", [-0.01, 0.082])  # 贴着弯道但仍分开，必须细分才能证明
    _, rejection = bc.check_swap_sweep(moving_a, moving_b, [bystander])
    assert rejection is not None and rejection.reason == "uncertified"
    assert "深度" in rejection.detail


def test_区间数上限耗尽记为无法证明安全(monkeypatch):
    monkeypatch.setattr(bc, "MAX_INTERVALS", 3)
    moving_a = _bin_state("bin_0", [-0.05, -0.06])
    moving_b = _bin_state("bin_1", [0.06, -0.06])
    bystander = _bin_state("bin_2", [-0.01, 0.082])
    _, rejection = bc.check_swap_sweep(moving_a, moving_b, [bystander])
    assert rejection is not None and rejection.reason == "uncertified"
    assert "区间数" in rejection.detail


def test_四元数线性混合退化时按无法证明安全拒绝():
    """qa0 与 qb0 互为相反数时，中点混合范数为 0，算不出角速度上界。"""
    a = _bin_state("bin_0", [-0.05, 0.0])
    b = _bin_state("bin_1", [0.05, 0.0])
    b = bc.ObjectState(name=b.name, p=b.p, q=-a.q, shapes=b.shapes)
    _, rejection = bc.check_swap_sweep(a, b)
    assert rejection is not None and rejection.reason == "uncertified"


def test_拒绝证据带齐身份形状与判定值():
    moving_a = _bin_state("bin_0", [-0.05, -0.06])
    moving_b = _bin_state("bin_1", [0.06, -0.06])
    bystander = _bin_state("bin_2", [0.005, 0.01])
    _, rejection = bc.check_swap_sweep(moving_a, moving_b, [bystander], sweep_index=2)
    payload = rejection.as_dict()
    for key in ("reason", "stage", "object_a", "object_b", "shape_a", "shape_b", "gap_m", "s", "sweep_index"):
        assert key in payload
    assert payload["sweep_index"] == 2
    assert 0.0 <= payload["s"] <= 1.0


def test_抛错模式带结构化证据():
    a = _bin_state("bin_0", [0.0, 0.0])
    b = _bin_state("bin_1", [0.0, 0.04])
    with pytest.raises(bc.BinCollisionError) as excinfo:
        bc.check_bin_layout([a, b], raise_on_reject=True)
    assert excinfo.value.rejection.reason == "contact"


def test_判据常量按计划定死():
    assert bc.EPS_M == 1e-6
    assert bc.MAX_DEPTH == 20
    assert bc.MAX_INTERVALS == 4096
    assert bc.LANE_OFFSET == 0.07
