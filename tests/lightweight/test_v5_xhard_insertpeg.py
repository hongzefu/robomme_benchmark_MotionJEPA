#!/usr/bin/env python3
"""轻量测试：V5 InsertPeg 的 xhard 档（NEWTASK_RELEASE_V5_PLAN 2.8，L24～L29、L52），纯 CPU、不起 sapien 场景。

* ``footprint_gap``：有向矩形精确距离的解析样例、相交/接触恒为 0（严格不等号的必要性）、与密采样边界点的暴力距离一致；
* 轮廓几何常数从真实 ``build_peg`` / ``build_box_with_hole`` 的建模调用里量出来，与 ``peg_footprint`` / ``box_footprint`` 一致；
* ``_xhard_sample_pegs`` 在假环境上跑：两两轮廓间隔 > 0.03、离孔板 > 0.01、原生杆根判据仍成立、x ∈ [-0.2, 0.1]；
* 随机调用顺序与按计划伪码独立写的参考实现逐位一致（lazy yaw）；
* 回放（N17 / L29）：自导出规格回放零不等；冻结值违反间隔即抛 ``EpisodeSpecError``；V4 布局与 V4 header 都被拒；
* 原三档：``_xhard_sample_pegs`` 只在 ``if xhard`` 分支里被调用，原生循环不读任何 V5 新键。

    uv run --no-sync python -m pytest tests/lightweight/test_v5_xhard_insertpeg.py -q
"""

from __future__ import annotations

import ast
import copy
import importlib
import inspect
import math
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

sapien = pytest.importorskip("sapien")
torch = pytest.importorskip("torch")

insertpeg_mod = importlib.import_module("robomme.robomme_env.InsertPeg")
from robomme.robomme_env.utils import object_generation as og  # noqa: E402
from robomme.robomme_env.utils.episode_spec import EpisodeSpecError, SpecRecorder  # noqa: E402
from robomme.robomme_env.utils.sampling_config import SamplingConfigError  # noqa: E402
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402

CLS = insertpeg_mod.InsertPeg
footprint_gap = insertpeg_mod.footprint_gap
peg_footprint = insertpeg_mod.peg_footprint
box_footprint = insertpeg_mod.box_footprint

# 与 _load_scene 相同的取法：float32 张量 .item() 后的 length / radius
LENGTH = (0.05 + (0.01 - 0.01) * torch.rand(1)).item()
RADIUS = (0.01 + (0.005 - 0.005) * torch.rand(1)).item()


def _rect(c, yaw, half):
    return (np.asarray(c, dtype=np.float64), float(yaw), tuple(half))


# ── footprint_gap ────────────────────────────────────────────────────────────
def test_footprint_gap_analytic_cases() -> None:
    a = _rect((0, 0), 0.0, (0.05, 0.01))
    # 同轴平行，端对端 / 侧对侧
    assert footprint_gap(a, _rect((0.14, 0), 0.0, (0.05, 0.01))) == pytest.approx(0.04, abs=1e-12)
    assert footprint_gap(a, _rect((0, 0.06), 0.0, (0.05, 0.01))) == pytest.approx(0.04, abs=1e-12)
    # 垂直 T 形：b 的端面离 a 的长边 0.02
    assert footprint_gap(a, _rect((0, 0.08), math.pi / 2, (0.05, 0.01))) == pytest.approx(0.02, abs=1e-12)
    # 两个单位正方形，b 转 45°：b 的角点沿轴向，最近的是 b 的斜边到 a 的角点
    sq = _rect((0, 0), 0.0, (0.01, 0.01))
    b = _rect((0.03, 0.03), math.pi / 4, (0.01, 0.01))
    expect = (0.06 - 0.01 * math.sqrt(2) - 0.02) / math.sqrt(2)
    assert footprint_gap(sq, b) == pytest.approx(expect, abs=1e-12)
    # 对称
    assert footprint_gap(b, sq) == pytest.approx(expect, abs=1e-12)


@pytest.mark.parametrize("other", [
    ((0.1, 0.0), 0.0, (0.05, 0.01)),      # 端面恰好接触
    ((0.0, 0.0), 1.0, (0.05, 0.01)),      # 十字交叉
    ((0.0, 0.0), 0.3, (0.01, 0.005)),     # 完全包含
    ((0.04, 0.015), 0.2, (0.05, 0.01)),   # 部分重叠
])
def test_footprint_gap_zero_when_touching_or_overlapping(other) -> None:
    a = _rect((0, 0), 0.0, (0.05, 0.01))
    gap = footprint_gap(a, _rect(*other))
    assert gap == 0.0
    # ⚠ 严格不等号的必要性：重叠时 gap 恒为 0，``gap >= 0`` 永真、等于没有约束
    assert not gap > 0.0 and gap >= 0.0


def _boundary_points(rect, n=400):
    c, yaw, half = rect
    corners = insertpeg_mod._rect_corners(c, yaw, half)
    t = np.linspace(0.0, 1.0, n)[:, None]
    return np.concatenate([corners[k] + t * (corners[(k + 1) % 4] - corners[k]) for k in range(4)])


def test_footprint_gap_matches_bruteforce_on_random_pairs() -> None:
    rng = np.random.default_rng(1234)
    checked = 0
    for _ in range(300):
        a = _rect(rng.uniform(-0.1, 0.1, 2), rng.uniform(-np.pi, np.pi), (0.05, 0.01))
        b = _rect(rng.uniform(-0.1, 0.1, 2), rng.uniform(-np.pi, np.pi), rng.uniform(0.005, 0.05, 2))
        gap = footprint_gap(a, b)
        pa, pb = _boundary_points(a), _boundary_points(b)
        brute = float(np.min(np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=-1)))
        if gap == 0.0:
            continue  # 相交（边界上的暴力距离在此无意义）
        checked += 1
        # 精确值不大于任何边界点对距离；密采样上界与精确值相差不超过采样步长
        assert gap <= brute + 1e-12
        assert brute - gap < 2.6e-4
    assert checked > 100


# ── 轮廓几何常数：从真实建模调用里量 ────────────────────────────────────────────
class _CaptureLinkBuilder:
    def __init__(self, log, parent=None):
        self.log, self.parent = log, parent
        self.visual, self.collision, self.pose_in_parent = [], [], None

    def set_name(self, name):
        self.name = name

    def set_joint_name(self, name):
        pass

    def set_joint_properties(self, **kw):
        self.pose_in_parent = kw["pose_in_parent"]

    def add_box_collision(self, pose=None, half_size=None, density=None, **kw):
        if half_size is None:  # build_peg 用关键字只传 half_size
            half_size, pose = pose, None
        self.collision.append((pose, list(half_size)))

    def add_box_visual(self, pose=None, half_size=None, material=None, **kw):
        if half_size is None:
            half_size, pose = pose, None
        self.visual.append((pose, list(half_size)))


class _CaptureArticulationBuilder:
    def __init__(self):
        self.links = []
        self.initial_pose = None

    def create_link_builder(self, parent=None):
        link = _CaptureLinkBuilder(self.links, parent)
        self.links.append(link)
        return link

    def set_name(self, name):
        pass

    def build(self, *a, **kw):
        return SimpleNamespace(links=[SimpleNamespace(name=l.name) for l in self.links])


def test_peg_footprint_matches_build_peg_geometry() -> None:
    art = _CaptureArticulationBuilder()
    scene = SimpleNamespace(create_articulation_builder=lambda: art)
    try:
        og.build_peg(scene, length=LENGTH, radius=RADIUS, name="peg_probe")
    except Exception:  # noqa: BLE001  构建阶段之后的 sapien 调用不关心，只要建模调用已记录
        pass
    head, tail = art.links[0], art.links[1]
    assert head.parent is None and tail.parent is head  # 根链接 = 杆头，位姿 p 即采样的 xy
    tail_offset = float(tail.pose_in_parent.p[0])
    assert tail_offset == pytest.approx(-LENGTH)
    # 视觉盒在各自链接原点、沿链接 x 轴；取 x 方向并集
    (_, hv), (_, tv) = head.visual[0], tail.visual[0]
    lo = min(-hv[0], tail_offset - tv[0])
    hi = max(hv[0], tail_offset + tv[0])
    half_w = max(hv[1], tv[1])
    # 碰撞盒被视觉轮廓包住（按视觉量更保守）
    for (_, hc), off in ((head.collision[0], 0.0), (tail.collision[0], tail_offset)):
        assert lo <= off - hc[0] and off + hc[0] <= hi and hc[1] <= half_w
    for yaw in (0.0, 0.7, -2.4):
        root = np.array([0.03, -0.12])
        c, fyaw, half = peg_footprint(root, yaw, LENGTH, RADIUS)
        u = np.array([math.cos(yaw), math.sin(yaw)])
        assert np.allclose(c, root + 0.5 * (lo + hi) * u, atol=1e-9)
        assert half == pytest.approx(((hi - lo) / 2, half_w))
    # 计划 2.8 写的数：中心 root − 0.025u、半尺寸 (0.05, 0.01)
    assert (hi - lo) / 2 == pytest.approx(0.05, abs=1e-7) and 0.5 * (lo + hi) == pytest.approx(-0.025, abs=1e-7)
    assert half_w == pytest.approx(0.01, abs=1e-7)


def test_box_footprint_matches_build_box_with_hole_geometry() -> None:
    captured = []

    class _ActorBuilder:
        def add_box_collision(self, pose, half_size):
            captured.append((np.asarray(pose.p, dtype=np.float64), np.asarray(half_size, dtype=np.float64)))

        def add_box_visual(self, pose, half_size, material=None):
            pass

        def build_kinematic(self, name):
            return name

    env = SimpleNamespace(scene=SimpleNamespace(create_actor_builder=lambda: _ActorBuilder()))
    box_cfg = insertpeg_mod.NATIVE_SAMPLING["positions"]["box"]
    og.build_box_with_hole(env, inner_radius=RADIUS * box_cfg["inner_radius_factor"],
                           outer_radius=RADIUS * box_cfg["outer_radius_factor"], depth=LENGTH,
                           center=list(box_cfg["base_translation"]))
    xs = [(p[0] - h[0], p[0] + h[0]) for p, h in captured]
    ys = [(p[1] - h[1], p[1] + h[1]) for p, h in captured]
    half_x = max(abs(v) for pair in xs for v in pair)
    half_y = max(abs(v) for pair in ys for v in pair)
    _, _, half = box_footprint((0, 0), 0.0, LENGTH, RADIUS * box_cfg["outer_radius_factor"])
    assert half == pytest.approx((half_x, half_y))
    assert half == pytest.approx((0.05, 0.04), abs=1e-7)


# ── 采样器：假环境 ─────────────────────────────────────────────────────────────
class _FakePeg:
    def __init__(self):
        self.pose = None

    def set_pose(self, pose):
        self.pose = pose


def _fake_env(seed, spec=None, sampling_config=None, n_pegs=4):
    env = SimpleNamespace()
    env.pegs = [_FakePeg() for _ in range(n_pegs)]
    env._hb_generator = torch.Generator()
    env._hb_generator.manual_seed(int(seed))
    env._spec = SpecRecorder(spec, "InsertPeg", {"seed": seed}, difficulty="xhard")
    env._sampling = insertpeg_mod._resolve_sampling_config(CLS, sampling_config)
    env.length, env.radius = LENGTH, RADIUS
    env._native_init_index = 0
    return env


def _box_for(seed):
    """与 _initialize_episode 相同的孔板取法（先于杆抽 3 个 rand）。"""
    g = torch.Generator()
    g.manual_seed(int(seed) + 7919)
    box_cfg = insertpeg_mod.NATIVE_SAMPLING["positions"]["box"]
    jx = (torch.rand(1, generator=g).item() - 0.5) * box_cfg["jitter_span"]
    jy = (torch.rand(1, generator=g).item() - 0.5) * box_cfg["jitter_span"]
    yaw = np.pi / 2 + (torch.rand(1, generator=g).item() * 2 - 1) * np.radians(box_cfg["yaw_half_span_deg"])
    return np.array([jx, jy], dtype=np.float32), yaw


def _run(seed, spec=None, box=None):
    env = _fake_env(seed, spec=spec)
    box_xy, box_yaw = box if box is not None else _box_for(seed)
    CLS._xhard_sample_pegs(env, box_xy, box_yaw, env._sampling["decision"]["xhard"])
    return env, box_xy, box_yaw


def _pose_xy_yaw(peg):
    p = np.asarray(peg.pose.p, dtype=np.float64)
    w, x, y, z = np.asarray(peg.pose.q, dtype=np.float64)
    return p[:2], math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


@pytest.mark.parametrize("seed", range(0, 2000, 10))
def test_sampler_spacing_region_and_native_rules(seed) -> None:
    env, box_xy, box_yaw = _run(seed)
    poses = [_pose_xy_yaw(p) for p in env.pegs]
    fps = [peg_footprint(xy, yaw, LENGTH, RADIUS) for xy, yaw in poses]
    box_fp = box_footprint(box_xy, box_yaw, LENGTH, RADIUS * 4)
    for i, (xy, _yaw) in enumerate(poses):
        assert -0.2 - 1e-6 <= xy[0] <= 0.1 + 1e-6  # L52：x 上界 0.1
        assert -0.3 - 1e-6 <= xy[1] <= 0.3 + 1e-6
        assert np.linalg.norm(xy - box_xy) > RADIUS * 6  # 原生规则保留
        assert footprint_gap(fps[i], box_fp) > 0.01
        for j in range(i):
            assert np.linalg.norm(xy - poses[j][0]) > LENGTH * 1.5
            assert footprint_gap(fps[i], fps[j]) > 0.03
    doc = env._spec.to_dict()["initializations"]["0"]
    assert len(doc["peg_attempts"]) == 4 and all(1 <= a <= 512 for a in doc["peg_attempts"])
    assert doc["min_pair_gap_m"] > 0.03 and doc["min_box_gap_m"] > 0.01
    assert sorted(doc["pegs"]) == ["0", "1", "2", "3"]


def _reference_sampler(seed, box_xy, box_yaw):
    """按计划 2.8 伪码独立写的参考实现：只用来锁随机调用顺序（lazy yaw、x 上界、4 根一个循环）。"""
    g = torch.Generator()
    g.manual_seed(int(seed))
    box_fp = box_footprint(box_xy, box_yaw, LENGTH, RADIUS * 4)
    out = []
    for _i in range(4):
        for _attempt in range(512):
            x = torch.rand(1, generator=g).item() * (0.1 - (-0.2)) + (-0.2)
            y = torch.rand(1, generator=g).item() * 0.6 + (-0.3)
            xy = np.array([x, y], dtype=np.float32)
            if np.linalg.norm(xy - box_xy) <= RADIUS * 6:
                continue
            if any(np.linalg.norm(xy - pxy) <= LENGTH * 1.5 for pxy, _ in out):
                continue
            yaw = (torch.rand(1, generator=g).item() * 2 - 1) * np.radians(180)
            fp = peg_footprint(xy, yaw, LENGTH, RADIUS)
            if footprint_gap(fp, box_fp) <= 0.01:
                continue
            if any(footprint_gap(fp, peg_footprint(pxy, pyaw, LENGTH, RADIUS)) <= 0.03 for pxy, pyaw in out):
                continue
            out.append((xy, yaw))
            break
        else:
            raise AssertionError("参考实现耗尽")
    return out, torch.rand(1, generator=g).item()


@pytest.mark.parametrize("seed", [5300000, 5300100, 5300300, 17, 99991, 123456, 7, 424242, 31337, 2024,
                                  11, 12, 13, 14, 15, 16, 18, 19, 20, 21])
def test_rng_order_matches_reference(seed) -> None:
    env, box_xy, box_yaw = _run(seed)
    ref, ref_next = _reference_sampler(seed, box_xy, box_yaw)
    frozen = env._spec.to_dict()["initializations"]["0"]["pegs"]
    for i, (xy, yaw) in enumerate(ref):
        assert frozen[str(i)] == [[float(xy[0]), float(xy[1])], yaw]
    # 采样结束后的随机流位置也相同（后面的 obj/dir 抽样因此逐位可预期）
    assert torch.rand(1, generator=env._hb_generator).item() == ref_next


def test_exhaustion_raises_scene_generation_error() -> None:
    # 把孔板放在杆区中心且间隔要求大到放不下第 2 根 → 真 SceneGenerationError（不静默少放）
    env = _fake_env(3)
    cfg = copy.deepcopy(env._sampling["decision"]["xhard"])
    cfg["peg_min_pair_gap_m"] = 1.0
    with pytest.raises(SceneGenerationError):
        CLS._xhard_sample_pegs(env, np.array([0.0, 0.0], dtype=np.float32), np.pi / 2, cfg)


# ── 回放守卫（N17 / L29）───────────────────────────────────────────────────────
def test_replay_own_export_is_exact_and_passes_guard() -> None:
    env, box_xy, box_yaw = _run(5300200)
    spec = env._spec.to_dict()
    env2, _, _ = _run(5300200, spec=spec, box=(box_xy, box_yaw))
    assert env2._spec.mismatches == []
    for a, b in zip(env.pegs, env2.pegs):
        assert np.allclose(a.pose.p, b.pose.p) and np.allclose(a.pose.q, b.pose.q)


def test_replay_tampered_spec_rejected() -> None:
    env, box_xy, box_yaw = _run(5300400)
    spec = env._spec.to_dict()
    pegs = spec["initializations"]["0"]["pegs"]
    (x0, y0), yaw0 = pegs["0"]
    # peg_1 挪到 peg_0 旁边、同向平行，侧面间隔 0.02 < 0.03（杆根距 0.04 同时违反原生规则也无所谓，只看守卫）
    ux, uy = math.cos(yaw0), math.sin(yaw0)
    pegs["1"] = [[x0 - 0.04 * uy, y0 + 0.04 * ux], yaw0]
    with pytest.raises(EpisodeSpecError, match="peg_1"):
        _run(5300400, spec=spec, box=(box_xy, box_yaw))
    # 杆压孔板
    spec2 = env._spec.to_dict()
    spec2["initializations"]["0"]["pegs"]["0"] = [[float(box_xy[0]), float(box_xy[1])], 0.0]
    with pytest.raises(EpisodeSpecError, match="孔板"):
        _run(5300400, spec=spec2, box=(box_xy, box_yaw))


def test_v4_layout_rejected_on_replay() -> None:
    """V4 v4-01 里 InsertPeg seed 5300000 第 0 次初始化的冻结布局（逐字抄录）：第 4 根贴近目标杆，轮廓重叠。"""
    spec = {
        "spec_kind": "native-newvalue/1", "task": "InsertPeg",
        "initializations": {"0": {"pegs": {
            "0": [[0.1344267576932907, -0.033931732177734375], -0.5979094588374843],
            "1": [[0.08544471114873886, 0.17761626839637756], 1.4553032278608904],
            "2": [[-0.050762079656124115, 0.27050912380218506], 0.7366665598619855],
            "3": [[0.14730623364448547, -0.11177679151296616], 3.073836467524105],
        }}},
    }
    box = (np.array([0.03148742914199829, 0.033135962486267094], dtype=np.float32), 1.6805025015158366)
    with pytest.raises(EpisodeSpecError):
        _run(5300000, spec=spec, box=box)


V4_XHARD_DECISION = {
    "peg_count": 4,
    "peg_offsets": [0.1, 0, -0.1, -0.2],
    "near_target_distractor": {"anchor_peg_index": 0, "max_center_distance_m": 0.085},
    "peg_yaw_range": {"half_span_deg": 180},
}


def test_v4_header_rejected_by_shape_check() -> None:
    decision, native = insertpeg_mod.native_blocks(CLS)
    v4 = copy.deepcopy(decision)
    v4["xhard"] = copy.deepcopy(V4_XHARD_DECISION)
    with pytest.raises(SamplingConfigError):
        insertpeg_mod._resolve_sampling_config(CLS, {"decision": v4, "native": native})


# ── 原三档不受影响 ─────────────────────────────────────────────────────────────
def _method_ast(name):
    src = textwrap.dedent(inspect.getsource(getattr(CLS, name)))
    return ast.parse(src)


def test_new_sampler_only_called_under_xhard_branch() -> None:
    tree = _method_ast("_initialize_episode")
    calls = []
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_xhard_sample_pegs":
            calls.append(node)
    assert len(calls) == 1
    node = calls[0]
    while node in parents and not isinstance(node, ast.If):
        node = parents[node]
    assert isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "xhard"
    # V4 的近目标干扰杆已删除
    assert not hasattr(CLS, "_xhard_place_near_target_peg")
    # 原生循环体不读任何 V5 新键
    src = inspect.getsource(CLS._initialize_episode)
    for key in ("peg_min_pair_gap_m", "peg_box_min_gap_m", "peg_x_max_m", "footprint_gap"):
        assert key not in src
