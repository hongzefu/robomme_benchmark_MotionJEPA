# robomme_hard：本测试测新值档／改动行为，阶段 3 起 src/robomme 回到官方 1fadc0ec，故改测 robomme_hard（0927 计划 R8 第③类）
#!/usr/bin/env python3
"""轻量测试：V5 MoveCube 机制在 V6 xhard4 区域实现下的回归（L30～L34）。

离线部分纯 CPU、不起 sapien 场景：``TableSceneBuilder``、``build_peg``、方块与圆盘 builder 用假对象顶替，
直接跑真实的 ``MoveCube._load_scene``（随机调用、拒绝循环、规格记录全是真代码）。

* 原三档逐位不变：easy/medium/hard 的规格、物体位姿与调用后随机流哨兵的 SHA-256 与改动前代码
  （基线 12.120，删 ``corner_bias`` 之前）算出的金标准相同；
* V6（计划 2.6）：旧档已更名为 xhard4，V5 桌面中心圆禁区已换成统一区域 U，``MOVECUBE_CENTER_EXCLUSION`` /
  ``MOVECUBE_REJECTION_BUDGET`` 与禁区校验用例随之删除，新判据见 ``test_xhard_movecube_region.py``；
  本文件保留原三档金标准、杆几何、两段方块生成、回放复核（违规样例在 V6 下同样违规）；
* ``MOVECUBE_EXEC_SPAWN``：xhard4 两段方块都以 ``include_existing=False`` 生成（L34），seed 1000442 / 1000446
  生成成功；真实模拟器上的同名检查在带 ``gpu`` 标记的用例里；
* L33：``corner_bias`` 在 MoveCube 里删干净（配置、decision、方法、规格记录、``corner_push`` 调用）；
* N17：回放冻结规格时杆、goal、方块三处违规都报 ``EpisodeSpecError``；合规规格回放逐值一致。

    PYTHONPATH="$PWD/src" uv run --project /data/hongzefu/robomme_benchmark_MotionJEPANewTask --no-sync python -m pytest tests/lightweight/test_v5_xhard_movecube.py -q -s
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import inspect
import json
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

pytest.importorskip("sapien")

from mani_skill.utils.structs.pose import Pose  # noqa: E402

mc = importlib.import_module("robomme_hard.robomme_env.MoveCube")
og = importlib.import_module("robomme_hard.robomme_env.utils.object_generation")
from robomme_hard.robomme_env.utils.episode_spec import EpisodeSpecError, SpecRecorder  # noqa: E402
from robomme_hard.robomme_env.utils.sampling_config import SamplingConfigError  # noqa: E402
from robomme_hard.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402

CLS = mc.MoveCube
R = 0.05
# P2 在真实模拟器上实测的杆身范围（杆根坐标系、沿杆朝向）；这里作独立参照，不从被测代码取
PEG_EXTENT_MEASURED = (-0.15, 0.05)
# 改动前代码（12.120，MoveCube 仍带 corner_bias 时）在同一假场景、同一 seed 集上算出的原三档金标准
ORIGINAL_TIER_GOLDEN = "84326bef1a9bc8617d1bb208af7197bf76bdf02b173d8b8d43d6808200e3aa94"
GOLDEN_SEEDS = list(range(0, 40)) + [1000442, 1000446, 5400000, 5400500]
EXCLUSION_SEEDS = list(range(2000000, 2005000))


# ---------------------------------------------------------------------------
# 假场景
# ---------------------------------------------------------------------------
class _FakeActor:
    def __init__(self, name, pose):
        self.name = name
        self.pose = pose


def _as_ms_pose(sp):
    return Pose.create_from_pq(torch.tensor([list(sp.p)], dtype=torch.float32),
                               torch.tensor([list(sp.q)], dtype=torch.float32))


def _fake_build_cube(scene, half_size, color, name, initial_pose):
    return _FakeActor(name, initial_pose)


def _fake_build_target(scene, radius, thickness, name, body_type, add_collision, initial_pose):
    return _FakeActor(name, _as_ms_pose(initial_pose))


def _fake_build_peg(env, length, radius, initial_pose, name, head_color, tail_color):
    return _FakeActor(name, _as_ms_pose(initial_pose)), _FakeActor("peg_head", None), _FakeActor("peg_tail", None)


class _FakeTableSceneBuilder:
    def __init__(self, *args, **kwargs):
        pass

    def build(self):
        pass


class _SpawnSpy:
    """包住真实的 spawn_random_cube，记下每次调用的关键参数（不改行为）。"""

    def __init__(self, real):
        self.real = real
        self.calls = []

    def __call__(self, env, **kwargs):
        self.calls.append({"name": kwargs.get("name_prefix"), "region_center": list(kwargs.get("region_center")),
                           "extra": {k: kwargs[k] for k in ("include_existing", "center_exclusion", "corner_bias")
                                     if k in kwargs}})
        return self.real(env, **kwargs)


@pytest.fixture
def fake_scene(monkeypatch):
    monkeypatch.setattr(og.actors, "build_cube", _fake_build_cube)
    monkeypatch.setattr(og, "build_purple_white_target", _fake_build_target)
    monkeypatch.setattr(og, "build_gray_white_target", _fake_build_target)
    monkeypatch.setattr(mc, "build_peg", _fake_build_peg)
    monkeypatch.setattr(mc, "TableSceneBuilder", _FakeTableSceneBuilder)
    # 假杆没有 sapien 形状；实际几何复核在 gpu 用例里对真实模拟器做
    monkeypatch.setattr(CLS, "_xhard4_verify_peg_extent", lambda self, extent: None)
    spy = _SpawnSpy(mc.spawn_random_cube)
    monkeypatch.setattr(mc, "spawn_random_cube", spy)
    return spy


def _make(seed, difficulty, spec=None):
    env = object.__new__(CLS)
    env.device = "cpu"
    env.scene = None
    env._sampling = mc._resolve_sampling_config(CLS, None)
    env._spec = SpecRecorder(spec, "MoveCube", {"seed": seed}, difficulty=difficulty)
    env._hb_generator = torch.Generator()
    env._hb_generator.manual_seed(int(seed))
    env.difficulty = difficulty
    env.cube_half_size = 0.02
    return env


def _run(seed, difficulty, spec=None, tweak=None):
    env = _make(seed, difficulty, spec)
    if tweak is not None:
        tweak(env)
    try:
        env._load_scene({})
        err = None
    except Exception as exc:  # noqa: BLE001 — 原三档的 TypeError 也要进指纹
        err = type(exc).__name__
    return env, err


def _fingerprint(env, err):
    out = {"err": err, "spec": env._spec.to_dict()}
    for name in ("peg", "goal_site", "goal_site_2", "cube", "cube_2"):
        actor = getattr(env, name, None)
        if actor is not None:
            vals = list(actor.pose.p.reshape(-1).tolist()) + list(actor.pose.q.reshape(-1).tolist())
            out[name] = [float(v).hex() for v in vals]
    poses2 = getattr(env, "peg_init_poses_2", None)
    if poses2 is not None:
        out["peg_init_poses_2"] = [float(v).hex() for v in list(poses2[0].p) + list(poses2[0].q)]
    out["sentinel"] = float(torch.rand(1, generator=env._hb_generator).item()).hex()
    return out


def _seg_dist(root, yaw, extent):
    """独立实现：线段 root + t·u（t∈extent）到原点的最近距离。"""
    u = np.array([math.cos(yaw), math.sin(yaw)])
    t = float(np.clip(-(root @ u), extent[0], extent[1]))
    return float(np.linalg.norm(root + t * u))


def _peg_root(layout):
    base_y, xj, yj = layout["peg_offsets"]
    root = np.array([0.0, base_y], dtype=np.float32)
    root += np.array([xj, yj], dtype=np.float32)
    return root.astype(np.float64)


# ---------------------------------------------------------------------------
# 原三档逐位不变
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tier", ["easy", "medium", "hard"])
def test_original_tiers_bitwise_unchanged(fake_scene, tier) -> None:
    h = hashlib.sha256()
    for seed in GOLDEN_SEEDS:
        env, err = _run(seed, tier)
        h.update(json.dumps(_fingerprint(env, err), sort_keys=True, default=str).encode())
    assert h.hexdigest() == ORIGINAL_TIER_GOLDEN
    # 原三档调用 spawn_random_cube 时不带任何新参数
    assert fake_scene.calls and all(call["extra"] == {} for call in fake_scene.calls)


# ---------------------------------------------------------------------------
# L33：corner_bias 删干净
# ---------------------------------------------------------------------------
def test_corner_bias_removed_cleanly() -> None:
    src = inspect.getsource(mc)
    assert "corner_push" not in src
    assert not hasattr(CLS, "_xhard_corner_bias")
    assert "corner_bias" not in CLS.config_xhard4
    decision, _ = mc.native_blocks(CLS)
    for seg in ("demo_layout", "execution_layout"):
        # V6（计划 2.6）：V5 的 center_exclusion 已换成统一区域 region
        assert set(decision[seg]["xhard4"]) == {"region"}
    load_src = inspect.getsource(CLS._load_scene)
    assert "corner_bias" not in load_src.replace("corner_bias 已删除", "")


def test_peg_axis_extent_matches_measured_geometry() -> None:
    lo, hi = mc._peg_axis_extent(0.1)
    assert lo == pytest.approx(PEG_EXTENT_MEASURED[0], abs=1e-12)
    assert hi == pytest.approx(PEG_EXTENT_MEASURED[1], abs=1e-12)


def test_exec_spawn_offline_known_seeds(fake_scene) -> None:
    ok = 0
    for seed in (1000442, 1000446):
        start = len(fake_scene.calls)
        env, err = _run(seed, "xhard4")
        assert err is None, (seed, err)
        cube2 = [c for c in fake_scene.calls[start:] if c["name"] == "fixed_cube_2"]
        assert cube2 and cube2[0]["extra"]["include_existing"] is False
        ok += 1
    print(f"MOVECUBE_EXEC_SPAWN_OFFLINE=PASS seeds=2 ok={ok}")


# ---------------------------------------------------------------------------
# N17：回放冻结规格时复核
# ---------------------------------------------------------------------------
def _export(seed):
    env, err = _run(seed, "xhard4")
    assert err is None
    return env._spec.to_dict(), _fingerprint(env, err)


def test_replay_valid_spec_reproduces_layout(fake_scene) -> None:
    for seed in (2000000, 2000001, 1000446):
        spec, fp = _export(seed)
        env = _make(seed, "xhard4", spec=copy.deepcopy(spec))
        env._load_scene({})
        assert env._spec.mismatches == []
        fp2 = _fingerprint(env, None)
        for name in ("peg", "goal_site", "goal_site_2", "cube", "cube_2", "peg_init_poses_2"):
            assert fp2[name] == fp[name]


@pytest.mark.parametrize("seg", ["demo", "execution"])
def test_replay_rejects_peg_in_zone(fake_scene, seg) -> None:
    spec, _ = _export(2000000)
    # 杆根 (0, −0.15)、朝 −y：V6 下抓取点 (0, −0.05) 落进统一区域 U 的圆环内孔
    spec["layout"][seg]["peg_offsets"] = [-0.2, 0.0, 0.05]
    spec["layout"][seg]["peg_yaw"] = -math.pi / 2
    env = _make(2000000, "xhard4", spec=spec)
    with pytest.raises(EpisodeSpecError, match="统一区域 U"):
        env._load_scene({})


@pytest.mark.parametrize("path, value", [
    ("demo.goal_xy", [0.01, -0.02]),
    ("execution.goal_xy", [0.0, 0.03]),
    ("demo.cube_pose", [0.02, 0.01, 0.3]),
    ("execution.cube_pose", [-0.03, 0.0, 1.0]),
])
def test_replay_rejects_goal_and_cube_in_zone(fake_scene, path, value) -> None:
    spec, _ = _export(2000000)
    seg, key = path.split(".")
    spec["layout"][seg][key] = value
    env = _make(2000000, "xhard4", spec=spec)
    with pytest.raises(EpisodeSpecError):
        env._load_scene({})


# ---------------------------------------------------------------------------
# 真实模拟器（gpu）：MOVECUBE_EXEC_SPAWN 与杆几何实测
# ---------------------------------------------------------------------------
@pytest.mark.gpu
@pytest.mark.slow
def test_real_reset_exec_spawn_and_peg_geometry() -> None:
    gym = pytest.importorskip("gymnasium")
    import robomme_hard.robomme_env  # noqa: F401 注册环境

    ok = 0
    for seed in (1000442, 1000446):
        env = gym.make("MoveCube", obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                       render_mode="rgb_array", reward_mode="dense", seed=seed, difficulty="xhard4")
        try:
            env.reset()
            u = env.unwrapped
            lay = u._spec.to_dict()["layout"]
            from tests.lightweight.test_xhard_movecube_region import segment_violations
            for seg in ("demo", "execution"):
                # V6（计划 2.6）：按统一区域 U 独立复核
                assert segment_violations(lay[seg]) == []
            # 演示段杆的实测几何：head 中心 = 杆根，tail 中心 = 杆根 − 0.1·u
            head = u.peg_head.pose.p[0, :2].cpu().numpy()
            tail = u.peg_tail.pose.p[0, :2].cpu().numpy()
            assert float(np.linalg.norm(head - tail)) == pytest.approx(0.1, abs=1e-5)
            u._xhard4_verify_peg_extent(mc._peg_axis_extent(u.length))
            ok += 1
        finally:
            env.close()
    print(f"MOVECUBE_EXEC_SPAWN=PASS seeds=2 ok={ok}")
    assert ok == 2
