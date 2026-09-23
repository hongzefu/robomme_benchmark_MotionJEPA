#!/usr/bin/env python3
"""轻量测试：V4 步 3b VideoPlaceButton / VideoPlaceOrder 的 xhard（计划 2.14 / 2.15）。

全部纯 CPU、不起 sapien 场景：

* 原三档 ``config_*`` 与 decision 可见部分逐字不变；xhard 从 hard 派生、只多 ``xhard`` 子键；
* 守卫放行已申报的 xhard 条目、拒绝申报外的键；
* ``validate_demo_plan`` 的合法组合；
* VideoPlaceOrder 按钮插点公式：单对象退化为原 ``k*2+2``，两对象永不切进 pick 与 drop 之间；
* ``build_home_sites`` 的两条验收（落点位姿逐位相等、建 actor 前后 generator 状态逐字节相等），
  用替身 builder 验证其自检逻辑；
* ``vqa_options`` 的 drop 候选：原三档原样返回 ``env.targets``，xhard 追加落点；
* 审计 ``NEUTRAL_KEYS`` 里两条 ``demo_object_count`` 豁免已撤销。

    uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_videoplace.py -q
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import importlib  # noqa: E402

# 包的 __init__ 用 `from .VideoPlaceButton import *` 把同名类盖在了子模块属性上，只能按模块路径取
vpb_mod = importlib.import_module("robomme.robomme_env.VideoPlaceButton")
vpo_mod = importlib.import_module("robomme.robomme_env.VideoPlaceOrder")
xhard_home_site = importlib.import_module("robomme.robomme_env.utils.xhard_home_site")
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402
from robomme.robomme_env.utils.sampling_config import SamplingConfigError, assert_native_decision  # noqa: E402
from robomme.robomme_env.utils.vqa_options import _videoplace_drop_available  # noqa: E402

MODULES = {
    "VideoPlaceButton": (vpb_mod, vpb_mod.VideoPlaceButton),
    "VideoPlaceOrder": (vpo_mod, vpo_mod.VideoPlaceOrder),
}

# 改动前（00e2ef4）原三档的类属性，逐字抄录
ORIGINAL_CONFIGS = {
    "VideoPlaceButton": {
        "easy": {"color": 1, "additional_place": False, "swap": False, "targets": 3},
        "medium": {"color": 3, "additional_place": False, "swap": False, "targets": 4},
        "hard": {"color": 3, "additional_place": False, "swap": True, "targets": 4},
    },
    "VideoPlaceOrder": {
        "easy": {"color": 1, "swap": False, "targets": 4},
        "medium": {"color": 3, "swap": False, "targets": 4},
        "hard": {"color": 3, "swap": True, "targets": 4},
    },
}


def _original_decision(task: str) -> dict:
    cfgs = ORIGINAL_CONFIGS[task]
    decision = {
        "demo_object_count": 1,
        "demo_return_policy": "native_random_goal_site",
        "targets": {d: c["targets"] for d, c in cfgs.items()},
        "swap": {d: c["swap"] for d, c in cfgs.items()},
    }
    if task == "VideoPlaceButton":
        decision["additional_place"] = {d: c["additional_place"] for d, c in cfgs.items()}
    return decision


def _strip(node):
    if isinstance(node, dict):
        return {k: _strip(v) for k, v in node.items() if k != "xhard"}
    return node


@pytest.mark.parametrize("task", sorted(MODULES))
def test_original_three_configs_unchanged(task: str) -> None:
    _, cls = MODULES[task]
    for difficulty, expected in ORIGINAL_CONFIGS[task].items():
        assert cls.configs[difficulty] == expected


@pytest.mark.parametrize("task", sorted(MODULES))
def test_xhard_derived_from_hard(task: str) -> None:
    _, cls = MODULES[task]
    assert cls.configs["xhard"] == cls.configs["hard"]  # color 3、targets 4、swap True 全部不变


@pytest.mark.parametrize("task", sorted(MODULES))
def test_decision_visible_part_equals_original(task: str) -> None:
    module, cls = MODULES[task]
    decision = module._native_decision(cls)
    assert _strip(decision) == _original_decision(task)
    assert decision["xhard"] == {"demo_object_count": 2, "demo_return_policy": "return_to_origin"}
    assert decision["targets"]["xhard"] == 4 and decision["swap"]["xhard"] is True


@pytest.mark.parametrize("task", sorted(MODULES))
def test_guard_accepts_declared_and_rejects_undeclared(task: str) -> None:
    module, cls = MODULES[task]
    default = module._native_decision(cls)
    assert_native_decision(copy.deepcopy(default), default, task)
    narrowed = copy.deepcopy(default)
    narrowed["xhard"]["demo_object_count"] = 1  # 组合扫描可收窄已申报的 xhard 值
    assert_native_decision(narrowed, default, task)
    extra = copy.deepcopy(default)
    extra["xhard"]["home_radius"] = 0.1
    with pytest.raises(SamplingConfigError):
        assert_native_decision(extra, default, task)
    touched = copy.deepcopy(default)
    touched["demo_object_count"] = 2  # 原三档可见部分不许动
    with pytest.raises(SamplingConfigError):
        assert_native_decision(touched, default, task)


def test_validate_demo_plan() -> None:
    v = xhard_home_site.validate_demo_plan
    assert v(1, "native_random_goal_site", "hard", 3) == (1, "native_random_goal_site")
    assert v(2, "return_to_origin", "xhard", 3) == (2, "return_to_origin")
    for args in ((2, "native_random_goal_site", "hard", 3), (2, "native_random_goal_site", "xhard", 3),
                 (4, "return_to_origin", "xhard", 3), (0, "return_to_origin", "xhard", 3)):
        with pytest.raises(SceneGenerationError):
            v(*args)


def _symbolic_sequence(visit_counts, button_after_visit):
    """按 _build_xhard_task_list 的拼法生成符号序列，用于核对按钮插点。"""
    pairs = []
    for obj, count in enumerate(visit_counts):
        for v in range(count):
            pairs += [("pick", obj), ("drop", obj, v)]
        pairs += [("pick", obj), ("home", obj)]
    index = vpo_mod.VideoPlaceOrder.xhard_button_task_index(visit_counts, button_after_visit)
    return pairs[:index] + [("button",)] + pairs[index:], index


@pytest.mark.parametrize("n", [2, 3, 4])
def test_button_index_single_object_matches_original(n: int) -> None:
    for k in range(n):
        assert vpo_mod.VideoPlaceOrder.xhard_button_task_index([n], k) == k * 2 + 2


@pytest.mark.parametrize("counts", [[2, 2], [2, 4], [4, 2], [3, 3], [4, 4]])
def test_button_index_two_objects_after_nth_visit_drop(counts) -> None:
    for k in range(sum(counts)):
        seq, index = _symbolic_sequence(counts, k)
        assert index % 2 == 0
        before = seq[index - 1]
        # 按钮前一条永远是一次「访问放置」，且恰好是全局第 k+1 次
        assert before[0] == "drop"
        assert sum(1 for item in seq[:index] if item[0] == "drop") == k + 1
        assert seq[index + 1][0] in ("pick",) if index + 1 < len(seq) else True
    with pytest.raises(ValueError):
        vpo_mod.VideoPlaceOrder.xhard_button_task_index(counts, sum(counts))


class _FakeActor:
    def __init__(self, name, raw_pose):
        self.name = name
        self.initial_pose = SimpleNamespace(raw_pose=raw_pose)
        self.pose = SimpleNamespace(raw_pose=raw_pose.clone())


def _fake_env():
    return SimpleNamespace(
        scene=SimpleNamespace(gpu_sim_enabled=False),
        cube_half_size=0.02,
        _hidden_objects=[],
    )


def _cube(name, x, y, yaw_q):
    raw = torch.tensor([[x, y, 0.02, *yaw_q]], dtype=torch.float32)
    return _FakeActor(name, raw)


def test_build_home_sites_pose_equal_and_rng_untouched(monkeypatch) -> None:
    built = []

    def fake_builder(scene, radius, thickness, name, body_type, add_collision, initial_pose):
        actor = _FakeActor(name, initial_pose.raw_pose.clone())
        built.append((radius, thickness, body_type, add_collision))
        return actor

    monkeypatch.setattr(xhard_home_site, "build_gray_white_target", fake_builder)
    env = _fake_env()
    cubes = [_cube("cube_red_0", 0.0123, -0.0456, (0.9, 0.0, 0.0, 0.4359)),
             _cube("cube_blue_0", -0.1, 0.07, (1.0, 0.0, 0.0, 0.0))]
    generator = torch.Generator()
    generator.manual_seed(7)
    torch.rand(3, generator=generator)
    before = generator.get_state().clone()
    homes, checks = xhard_home_site.build_home_sites(env, cubes, generator)
    assert torch.equal(before, generator.get_state())  # 验收②：逐字节相等
    assert checks == {"pose_equal": [True, True], "rng_state_equal": True}
    for cube, home in zip(cubes, homes):
        assert torch.equal(home.initial_pose.raw_pose, cube.initial_pose.raw_pose)  # 验收①
        assert home.name == f"home_site_{cube.name}" and home._home_of is cube
    assert env._hidden_objects == homes
    assert all(b[2] == "kinematic" and b[3] is False for b in built)
    record = xhard_home_site.home_pose_record(cubes, homes)
    assert list(record) == ["cube_red_0", "cube_blue_0"] and len(record["cube_red_0"]) == 7


def test_build_home_sites_rejects_pose_drift(monkeypatch) -> None:
    def drifting_builder(scene, radius, thickness, name, body_type, add_collision, initial_pose):
        raw = initial_pose.raw_pose.clone()
        raw[0, 0] += 1e-6
        return _FakeActor(name, raw)

    monkeypatch.setattr(xhard_home_site, "build_gray_white_target", drifting_builder)
    with pytest.raises(SceneGenerationError):
        xhard_home_site.build_home_sites(_fake_env(), [_cube("c", 0.0, 0.0, (1, 0, 0, 0))], torch.Generator())


def test_build_home_sites_rejects_rng_use(monkeypatch) -> None:
    generator = torch.Generator()

    def greedy_builder(scene, radius, thickness, name, body_type, add_collision, initial_pose):
        torch.rand(1, generator=generator)
        return _FakeActor(name, initial_pose.raw_pose.clone())

    monkeypatch.setattr(xhard_home_site, "build_gray_white_target", greedy_builder)
    with pytest.raises(SceneGenerationError):
        xhard_home_site.build_home_sites(_fake_env(), [_cube("c", 0.0, 0.0, (1, 0, 0, 0))], generator)


def test_vqa_drop_available() -> None:
    targets = ["t0", "t1", "t2", "t3"]
    env = SimpleNamespace(targets=targets)
    assert _videoplace_drop_available(env, SimpleNamespace()) is targets  # 原三档：同一对象
    assert _videoplace_drop_available(env, SimpleNamespace(xhard_home_sites=[])) is targets
    homes = ["h0", "h1"]
    assert _videoplace_drop_available(env, SimpleNamespace(xhard_home_sites=homes)) == targets + homes
    assert targets == ["t0", "t1", "t2", "t3"]  # 不改原列表


def test_audit_exemptions_revoked() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from parity import train_split_audit

    assert "VideoPlaceButton.decision.demo_object_count" not in train_split_audit.NEUTRAL_KEYS
    assert "VideoPlaceOrder.decision.demo_object_count" not in train_split_audit.NEUTRAL_KEYS
