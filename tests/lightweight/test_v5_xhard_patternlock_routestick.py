#!/usr/bin/env python3
"""轻量测试：V5 S3a PatternLock 与 RouteStick 的 xhard 改动（NEWTASK_RELEASE_V5_PLAN 2.10 / 2.11，L35～L38）。

纯 CPU：用 ``object.__new__`` 造一个不走 ``__init__`` 的实例，把 ``TableSceneBuilder`` 与
``build_gray_white_target`` 换成桩、``scene`` 换成 MagicMock，直接跑真实的 ``_load_scene``。
取值点、随机流、任务表与真实 reset 完全同一段代码，只是不建物理场景。

* PatternLock：``config_xhard.length == [25, 25]``；xhard 搜索预算 20000 冻进 ``decision.xhard``；
  ``PL_LEN_EXACT``——xhard reset 的路径恰为 25 节点；小预算下搜索耗尽抛真 ``SceneGenerationError``，
  原三档耗尽仍静默兜底；回放被改坏的规格被复核挡住；V4 形状的 decision 被守卫拒绝。
* RouteStick：``config_xhard.length == [15, 21]``；L 范围冻进 ``decision.xhard.segment_count_range``，
  回放按 header（传入的 sampling_config）取值而不是类属性；抽样点与顺序不变；V4 header 被拒。

    uv run --no-sync python -m pytest tests/lightweight/test_v5_xhard_patternlock_routestick.py -q
"""

from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme.robomme_env.utils.episode_spec import EpisodeSpecError, SpecRecorder  # noqa: E402
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402
from robomme.robomme_env.utils.sampling_config import SamplingConfigError, _strip_xhard  # noqa: E402

PL_MOD = importlib.import_module("robomme.robomme_env.PatternLock")
RS_MOD = importlib.import_module("robomme.robomme_env.RouteStick")
PL = PL_MOD.PatternLock
RS = RS_MOD.RouteStick

# 改动前（12.120）的原三档配置与 decision 原值（去掉 xhard 后），逐字抄录
PL_ORIGINAL_CONFIGS = {
    "easy": {"grid": 3, "length": [2, 4]},
    "medium": {"grid": 4, "length": [3, 5]},
    "hard": {"grid": 5, "length": [4, 8]},
}
PL_ORIGINAL_DECISION = {
    "demo_duration_seconds_range": None,
    "demonstration_duration_policy": "native",
    "grid": {"hard": 5, "easy": 3, "medium": 4},
    "path_length_range": {"hard": [4, 8], "easy": [2, 4], "medium": [3, 5]},
}
RS_ORIGINAL_CONFIGS = {
    "easy": {"length": [2, 3], "backtrack": False},
    "medium": {"length": [4, 5], "backtrack": False},
    "hard": {"length": [4, 7], "backtrack": True},
}
RS_ORIGINAL_DECISION = {
    "demo_duration_seconds_range": None,
    "demonstration_duration_policy": "native",
}

# 规划期探针 P3 与 V4 冻结规格里用过的 seed，外加几个新 seed
PL_SEEDS = [5500900, 5500000, 5500300, 5500600, 7100001]


def _fake_target(**kw):
    p = np.asarray(kw["initial_pose"].p, dtype=float)
    return SimpleNamespace(name=kw["name"], pose=SimpleNamespace(p=p.reshape(1, 3)))


def _load(mod, cls, seed, difficulty, sampling=None, spec=None, tweak=None):
    """不建物理场景地跑一次真实 ``_load_scene``；``tweak(env)`` 可在解析配置后改内存副本。"""
    env = object.__new__(cls)
    env.seed = seed
    env.difficulty = difficulty
    env.robot_init_qpos_noise = 0
    env._sampling = mod._resolve_sampling_config(cls, sampling)
    env._spec = SpecRecorder(spec, cls.__name__, {"seed": seed}, difficulty=difficulty)
    env._episode_spec = None
    env.scene = mock.MagicMock()
    if tweak is not None:
        tweak(env)
    with mock.patch.object(mod, "TableSceneBuilder"), \
            mock.patch.object(mod, "build_gray_white_target", _fake_target):
        cls._load_scene(env, {})
    return env


def _sampling_with(mod, cls, mutate):
    decision, native = mod.native_blocks(cls)
    mutate(decision)
    return {"decision": decision, "native": native}


def _is_king_path(nodes, n):
    if len(set(nodes)) != len(nodes):
        return False
    return all(max(abs(a // n - b // n), abs(a % n - b % n)) == 1 for a, b in zip(nodes, nodes[1:]))


# ── PatternLock ─────────────────────────────────────────────────────────────


def test_pl_original_three_and_xhard_config() -> None:
    for difficulty, expected in PL_ORIGINAL_CONFIGS.items():
        assert PL.configs[difficulty] == expected
    assert PL.config_xhard == {"grid": 5, "length": [25, 25]}
    assert PL.configs["xhard"] is PL.config_xhard


def test_pl_decision_and_native() -> None:
    decision, native = PL_MOD.native_blocks(PL)
    assert _strip_xhard(decision) == PL_ORIGINAL_DECISION
    assert decision["path_length_range"]["xhard"] == [25, 25]
    assert decision["grid"]["xhard"] == 5
    assert decision["xhard"] == {"path_search_max_attempts": 20000}
    # 原三档消费的 native 预算不变
    assert native["parameters"]["path_selection"]["max_attempts"] == 1000
    assert native["positions"] == {"grid_center": [-0.1, 0], "grid_spacing": 0.1,
                                   "node_position_expression": "center + (index - (n-1)/2) * spacing"}


@pytest.mark.parametrize("seed", PL_SEEDS)
def test_pl_len_exact(seed) -> None:
    """PL_LEN_EXACT：xhard reset 的路径恰为 25 节点、合法 8 邻接不重访，任务表按 25 节点展开。"""
    env = _load(PL_MOD, PL, seed, "xhard")
    doc = env._spec.to_dict()
    nodes = doc["actions"]["path_nodes"]
    assert len(nodes) == 25 and sorted(nodes) == list(range(25))
    assert _is_king_path(nodes, 5)
    assert 1 <= doc["actions"]["path_attempts"] <= 20000
    # 演示段：NO RECORD + 24 段 move；执行段：两个 NO RECORD + 24 段 move
    demo = [t for t in env.task_list if t["demonstration"] and t["name"] != "NO RECORD"]
    execute = [t for t in env.task_list if not t["demonstration"]]
    assert len(demo) == len(execute) == 24


def test_pl_exhaustion_raises_real_scene_generation_error() -> None:
    """xhard 预算来自 decision（header）；小预算下搜索耗尽抛真 SceneGenerationError（可被 except 接住）。"""
    sampling = _sampling_with(PL_MOD, PL, lambda d: d["xhard"].__setitem__("path_search_max_attempts", 3))
    with pytest.raises(SceneGenerationError, match="3 次搜索内"):
        _load(PL_MOD, PL, PL_SEEDS[0], "xhard", sampling=sampling)


def test_pl_exhaustion_via_native_budget_does_not_affect_xhard() -> None:
    """native 的 1000 只给原三档用：把它改小不影响 xhard（xhard 读 decision 的 20000）。"""
    def tweak(env):
        env._sampling["parameters"]["path_selection"]["max_attempts"] = 1
    env = _load(PL_MOD, PL, PL_SEEDS[0], "xhard", tweak=tweak)
    assert len(env._spec.to_dict()["actions"]["path_nodes"]) == 25


def test_pl_original_three_exhaustion_stays_silent() -> None:
    """原三档搜索耗尽仍静默沿用最后一条路径（行为不变），不抛错。"""
    def tweak(env):
        env._sampling["parameters"]["path_selection"]["max_attempts"] = 2
        env._sampling["decision"]["path_length_range"]["hard"] = [30, 30]  # 5×5 上不可能
    env = _load(PL_MOD, PL, 2, "hard", tweak=tweak)
    doc = env._spec.to_dict()
    assert doc["actions"]["path_attempts"] == 2
    assert len(doc["actions"]["path_nodes"]) < 30


def test_pl_replay_checks_frozen_path() -> None:
    seed = PL_SEEDS[1]
    spec = _load(PL_MOD, PL, seed, "xhard")._spec.to_dict()
    replay = _load(PL_MOD, PL, seed, "xhard", spec=copy.deepcopy(spec))
    assert replay._spec.mismatches == []
    # 冻结路径被截短 → 节点数不符
    bad = copy.deepcopy(spec)
    bad["actions"]["path_nodes"] = bad["actions"]["path_nodes"][:-1]
    with pytest.raises(EpisodeSpecError, match="节点数"):
        _load(PL_MOD, PL, seed, "xhard", spec=bad)
    # 冻结路径不相邻 → 拒绝
    bad = copy.deepcopy(spec)
    nodes = bad["actions"]["path_nodes"]
    far = next(i for i in range(2, 25) if max(abs(nodes[0] // 5 - nodes[i] // 5), abs(nodes[0] % 5 - nodes[i] % 5)) > 1)
    nodes[1], nodes[far] = nodes[far], nodes[1]
    with pytest.raises(EpisodeSpecError):
        _load(PL_MOD, PL, seed, "xhard", spec=bad)


def test_pl_v4_decision_rejected() -> None:
    """V4 形状的 decision（无 decision.xhard、节点 [20,24]）在 V5 代码上被守卫拒绝（口径 13）。"""
    decision, native = PL_MOD.native_blocks(PL)
    decision.pop("xhard")
    decision["path_length_range"]["xhard"] = [20, 24]
    with pytest.raises(SamplingConfigError):
        PL_MOD._resolve_sampling_config(PL, {"decision": decision, "native": native})


# ── RouteStick ──────────────────────────────────────────────────────────────


def test_rs_original_three_and_xhard_config() -> None:
    for difficulty, expected in RS_ORIGINAL_CONFIGS.items():
        assert RS.configs[difficulty] == expected
    assert RS.config_xhard == {"length": [15, 21], "backtrack": True}


def test_rs_decision_freezes_segment_range() -> None:
    decision, _ = RS_MOD.native_blocks(RS)
    assert _strip_xhard(decision) == RS_ORIGINAL_DECISION
    assert decision["xhard"] == {"segment_count_range": [15, 21]}


def test_rs_segment_range_and_draw_position() -> None:
    """L ∈ [15,21] 且 7 个值都出现；抽样点与顺序不变：theta、4 次障碍色之后的第一次 randint。"""
    seen = set()
    for seed in range(0, 160):
        env = _load(RS_MOD, RS, seed, "xhard")
        doc = env._spec.to_dict()
        steps = doc["objects"]["L"]
        assert 15 <= steps <= 21
        assert len(doc["actions"]["nodes"]) == steps + 1
        seen.add(steps)
        if seed < 20:
            g = torch.Generator()
            g.manual_seed(seed)
            torch.rand(1, generator=g)
            for _ in range(4):
                torch.rand(3, generator=g)
            assert steps == int(torch.randint(15, 22, (1,), generator=g).item())
    assert seen == set(range(15, 22))


def test_rs_segment_range_read_from_header_not_class() -> None:
    """回放时从 header（传入的 sampling_config.decision）读 L 范围，不读类属性。"""
    sampling = _sampling_with(RS_MOD, RS, lambda d: d["xhard"].__setitem__("segment_count_range", [21, 21]))
    for seed in (0, 1, 2):
        env = _load(RS_MOD, RS, seed, "xhard", sampling=sampling)
        assert env._sampling["parameters"]["configs"]["xhard"]["length"] == [15, 21]
        assert env._spec.to_dict()["objects"]["L"] == 21


def test_rs_v4_header_rejected_but_original_three_legacy_ok() -> None:
    """V4 header 的 RouteStick decision 没有 xhard 条目：xhard 直接报错；原三档照旧放行。"""
    decision, native = RS_MOD.native_blocks(RS)
    decision.pop("xhard")
    legacy = {"decision": decision, "native": native}
    with pytest.raises(ValueError, match="segment_count_range"):
        _load(RS_MOD, RS, 0, "xhard", sampling=copy.deepcopy(legacy))
    env = _load(RS_MOD, RS, 0, "hard", sampling=copy.deepcopy(legacy))
    assert 4 <= env._spec.to_dict()["objects"]["L"] <= 7


def test_rs_replay_checks_frozen_length() -> None:
    seed = 7
    spec = _load(RS_MOD, RS, seed, "xhard")._spec.to_dict()
    replay = _load(RS_MOD, RS, seed, "xhard", spec=copy.deepcopy(spec))
    assert replay._spec.mismatches == []
    bad = copy.deepcopy(spec)
    bad["objects"]["L"] = 22
    with pytest.raises(EpisodeSpecError, match="segment_count_range"):
        _load(RS_MOD, RS, seed, "xhard", spec=bad)
