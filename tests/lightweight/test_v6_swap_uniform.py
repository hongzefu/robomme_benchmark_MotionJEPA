#!/usr/bin/env python3
"""轻量测试：V6 交换对象均匀化（0925-newtask-release-v6-plan.md 2.2 / 2.4 / 2.5，M6(a) S5、外环 O4）。

纯函数与假环境，不起 SAPIEN 场景：

* S5 离线均匀性：合成可行槽对图上各跑 10000 局，跨局边际卡方 p>0.05、局内极差 ≤1 的比例、立即撤销 0；
  G 为完全图时边际严格均匀、极差恒 ≤1；
* 复核函数 ``verify_swap_sequence``：可行 / 撤销 / 越界判得出；
* 外环 O4 分组：评分升序、上一对放最末；序号重排 ``relabel_distractor_layout`` 保几何、改 cube 映射；
* 配置：VUS/BUS/VR 的四档新值分别挂在 decision.<tier> 下；M5(b) 保留前三个藏物槽，bin_3 恒空；
* 源码结构：Unmask 两环境的 step 锁定循环里新值分支读预规划、原三档仍取最近邻。

    PYTHONPATH="$PWD/src" uv run --project /data/hongzefu/robomme_benchmark_MotionJEPANewTask --no-sync python -m pytest tests/lightweight/test_v6_swap_uniform.py -q
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from scipy.stats import chisquare

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

pytestmark = pytest.mark.lightweight

from robomme.robomme_env.utils import swap_uniform as su  # noqa: E402
from robomme.robomme_env.utils import unmask_swap_xhard as ux  # noqa: E402
from robomme.robomme_env.utils.episode_spec import SpecRecorder  # noqa: E402
from robomme.robomme_env.utils.unmask_distractor_sampler import DistractorLayout  # noqa: E402

ENV_DIR = REPO_ROOT / "src" / "robomme" / "robomme_env"
EPISODES = 10000


def _adj(n, edges):
    adj = [[False] * n for _ in range(n)]
    for a, b in edges:
        adj[a][b] = adj[b][a] = True
    return adj


# 合成 G 的抽样器。Unmask 两个用 V6 调查 P2 实测的 6 个槽对可行率（顺序 (0,1),(0,2),(0,3),(1,2),(1,3),(2,3)），
# 按「G 连通」作接受条件（与 reset 同口径）逐局独立抽边；VR 用 6 槽、每边 0.3 的随机图，按「无孤立槽」接受。
# 另留两个固定图：长方形（对角线不可行）与完全图。
PAIRS4 = [(a, b) for a in range(4) for b in range(a + 1, 4)]
PAIRS6 = [(a, b) for a in range(6) for b in range(a + 1, 6)]
P_VUS = [.863, .066, .994, .993, .066, .855]
P_BUS = [.370, .092, .951, .957, .090, .362]


def _edge_sampler(n, pairs, probs, accept):
    def draw(rng):
        while True:
            adj = _adj(n, [pair for pair, pr in zip(pairs, probs) if rng.random() < pr])
            if accept(adj):
                return adj
    return draw


def _fixed(adj):
    return lambda _rng: adj


GRAPHS = {
    "vus_probe": (_edge_sampler(4, PAIRS4, P_VUS, su.graph_connected), (8, 12), "max_sum"),
    "bus_probe": (_edge_sampler(4, PAIRS4, P_BUS, su.graph_connected), (6, 8), "max_sum"),
    "rect4": (_fixed(_adj(4, [(0, 1), (1, 2), (2, 3), (0, 3)])), (8, 12), "max_sum"),
    "full4": (_fixed(_adj(4, PAIRS4)), (8, 12), "max_sum"),
    "vr6_random": (_edge_sampler(6, PAIRS6, [0.3] * 15, lambda a: not su.isolated_slots(a)), (8, 12), "sum_max"),
}


def _simulate(draw, n_range, score, episodes=EPISODES, seed=0):
    rng = np.random.default_rng(seed)
    marginal = None
    spreads, undo = [], 0
    for e in range(episodes):
        adj = draw(rng)
        if marginal is None:
            marginal = np.zeros(len(adj))
        n_swaps = int(rng.integers(n_range[0], n_range[1] + 1))
        g = torch.Generator()
        g.manual_seed(int(rng.integers(0, 2 ** 62)))
        plan = su.plan_balanced_swaps(adj, n_swaps, g, score=score)
        assert plan is not None
        problems, stats = su.verify_swap_sequence(adj, plan.pairs)
        assert not problems
        marginal += np.asarray(stats.counts)
        spreads.append(stats.spread)
        undo += stats.undo + su.count_undo(plan.pairs)
    return marginal, np.asarray(spreads), undo


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_S5_离线均匀性_跨局卡方_局内极差_零撤销(name):
    draw, n_range, score = GRAPHS[name]
    marginal, spreads, undo = _simulate(draw, n_range, score)
    p = chisquare(marginal).pvalue
    le1 = float(np.mean(spreads <= 1))
    print(f"UNIFORM=REPORT graph={name} chi2_p={p:.3f} range_le1={le1:.4f} "
          f"range_hist={dict(zip(*np.unique(spreads, return_counts=True)))} undo={undo}")
    assert p > 0.05
    assert undo == 0
    assert le1 >= 0.89
    assert spreads.max() <= 2


def test_S5_固定非对称图上边际按度偏_但局内极差仍不超过1():
    """记录一个已知性质：G 固定且不对称（BUS 常见的三边路径）时，2n 不能被 4 整除的那一次参与会系统地落在
    固定位置，跨局边际不均匀；实际环境里 G 逐局变化，边际均匀由上面 bus_probe 的抽样验证。"""
    path = _adj(4, [(0, 1), (0, 3), (1, 2)])
    marginal, spreads, undo = _simulate(_fixed(path), (7, 7), "max_sum", episodes=5000, seed=3)
    assert spreads.max() <= 1 and undo == 0
    assert chisquare(marginal).pvalue < 0.05


def test_S5_完全图时边际严格均匀且极差恒不超过1():
    draw, n_range, score = GRAPHS["full4"]
    marginal, spreads, _undo = _simulate(draw, n_range, score, episodes=2000, seed=7)
    assert spreads.max() <= 1
    freq = marginal / marginal.sum()
    assert np.abs(freq - 0.25).max() < 0.005


def test_S5_同种子可复现_不同种子不同():
    adj = GRAPHS["rect4"][0](None)
    plans = []
    for seed in (5, 5, 6):
        g = torch.Generator()
        g.manual_seed(seed)
        plans.append(su.plan_balanced_swaps(adj, 12, g).pairs)
    assert plans[0] == plans[1]
    assert plans[0] != plans[2]


def test_S5_无边或禁止撤销后无候选返回None():
    g = torch.Generator().manual_seed(0)
    assert su.plan_balanced_swaps(_adj(4, []), 3, g) is None
    # 只有一条边：第二次只能撤销 ⇒ 无法规划
    assert su.plan_balanced_swaps(_adj(4, [(0, 1)]), 2, g) is None


def test_图连通与孤立槽判定():
    assert su.graph_connected(_adj(4, [(0, 1), (0, 3), (1, 2)]))
    assert not su.graph_connected(_adj(4, [(0, 3), (1, 2)]))
    assert su.isolated_slots(_adj(4, [(0, 1), (1, 2)])) == [3]


def test_复核函数判出不可行_撤销_越界():
    adj = GRAPHS["rect4"][0](None)
    problems, _ = su.verify_swap_sequence(adj, [(0, 2)])  # 对角线不可行
    assert any("不可行" in p for p in problems)
    problems, stats = su.verify_swap_sequence(adj, [(0, 1), (1, 0)])  # 立即换回
    assert any("撤销" in p for p in problems) and stats.undo == 1
    problems, _ = su.verify_swap_sequence(adj, [(0, 9)])
    assert any("越界" in p for p in problems)
    problems, stats = su.verify_swap_sequence(adj, [(0, 1), (1, 2), (0, 3)])
    # (0,1) 后 0 在槽 1、1 在槽 0；(1,2) 占槽 (0,2) 不可行
    assert problems and stats.counts == [2, 2, 1, 1]


def test_O4分组_评分升序且上一对放最末():
    groups = su.balanced_pair_groups(4, [1, 0, 0, 2], (1, 2))
    assert groups[-1] == [(1, 2)]
    flat = [p for g in groups[:-1] for p in g]
    assert (1, 2) not in flat and len(flat) == 5
    keys = [max(c) for c in ([ [1, 0, 0, 2][a], [1, 0, 0, 2][b] ] for a, b in groups[0])]
    assert max(keys) == 1  # 最小组只含评分 (1, ·)：(0,1)(0,2)


def test_外环序号重排保几何改cube映射():
    layout = DistractorLayout(bins=[(0.3, 0.0, 10.0), (0.0, 0.3, 20.0), (-0.3, 0.0, 30.0)], cube_count=1,
                              cube_bins=[2], color_order=[0, 1, 2], trials=[1, 2, 3])
    public = ux.relabel_distractor_layout(layout, [2, 0, 1])
    assert public.bins == [(-0.3, 0.0, 30.0), (0.3, 0.0, 10.0), (0.0, 0.3, 20.0)]
    assert public.cube_bins == [0]
    assert public.trials == [3, 1, 2]
    with pytest.raises(ValueError):
        ux.relabel_distractor_layout(layout, [0, 0, 1])


def test_V6外环配置可解析且规则名分派():
    for task in ux.V5_SWAP_TASKS:
        cfg = ux.parse_distractor_swap_cfg(ux.v6_distractor_swap_cfg(task))
        assert cfg.rule == ux.OUTER_BALANCED_RULE
        v5 = ux.parse_distractor_swap_cfg(ux.v5_distractor_swap_cfg(task))
        assert v5.rule == ux.OUTER_INITIATOR_RULE
        # 路径约束逐项沿用 V5（M7(a)）
        assert (cfg.camera_visible, cfg.min_inner_circle_clearance_m, cfg.min_button_center_dist_m) == (
            v5.camera_visible, v5.min_inner_circle_clearance_m, v5.min_button_center_dist_m)
    bad = ux.v6_distractor_swap_cfg("VideoUnmaskSwap")
    bad["fallback"] = ux.OUTER_FALLBACK_RULE
    with pytest.raises(ValueError):
        ux.parse_distractor_swap_cfg(bad)


@pytest.mark.parametrize("task", ["VideoUnmaskSwap", "ButtonUnmaskSwap"])
def test_Unmask两环境四档申报S5O4_M5b且原三档配置不动(task):
    module = importlib.import_module(f"robomme.robomme_env.{task}")
    cls = getattr(module, task)
    decision = module._native_decision(cls)
    native = module.native_blocks(cls)[1]
    ranges = ({"xhard1": (4, 5), "xhard2": (6, 7), "xhard3": (8, 9), "xhard4": (10, 12)}
              if task == "VideoUnmaskSwap" else
              {"xhard1": (4, 4), "xhard2": (5, 5), "xhard3": (6, 7), "xhard4": (8, 9)})
    for index, tier in enumerate(("xhard1", "xhard2", "xhard3", "xhard4"), start=1):
        swap_min, swap_max = ranges[tier]
        pick = 2 if index == 1 else 3
        counts = {"swap_min": swap_min, "swap_max": swap_max, "pick_min": pick, "pick_max": pick}
        outer_count = 2 + 2 * index
        speed = 1.0 if index == 1 else 1.5
        config = {"bin": 4, **counts}
        assert cls.configs[tier] == config
        assert native["parameters"]["configs"][tier] == config
        assert decision["swap_count_range"][tier] == [counts["swap_min"], counts["swap_max"]]
        assert decision["pick_count_range"][tier] == [counts["pick_min"], counts["pick_max"]]
        plan = decision[tier]["swap_plan_v6"]
        assert plan["rule"] == su.S5_RULE and plan["require_connected_graph"] is True
        assert "hidden_bin_permutation_size" not in plan
        assert decision[tier]["distractor_swap"]["initiator_rule"] == ux.OUTER_BALANCED_RULE
        assert decision[tier]["swap_speed_multiplier"] == speed
        assert decision[tier]["distractor"] == ux.v6_distractor_cfg(task, outer_count)
    if task == "VideoUnmaskSwap":
        assert native["parameters"]["object_selection"]["hidden_bin_permutation_size"] == 3
        assert native["parameters"]["object_selection"]["hidden_bin_count_max"] == 3
    else:
        assert native["parameters"]["hidden_rule"] == "前三容器藏三色，第四个为空"
    assert decision["swap_speed_multiplier"] == 1 and decision["distractor"] is None


def test_VR四档S5及难度配置():
    module = importlib.import_module("robomme.robomme_env.VideoRepick")
    decision = module._native_decision(module.VideoRepick)
    expected = {"xhard1": (4, 3, 4, 2, 3), "xhard2": (5, 5, 6, 3, 4),
                "xhard3": (6, 7, 8, 4, 5), "xhard4": (7, 9, 12, 5, 7)}
    for tier, (cubes, swap_min, swap_max, repeat_low, repeat_high) in expected.items():
        cfg = decision[tier]
        assert cfg["layout"]["cube_count"] == cubes
        assert cfg["layout"]["min_center_dist_m"] == 0.12
        assert decision["swap"][tier] == {"swap_min": swap_min, "swap_max": swap_max}
        assert decision["num_repeats_range"][tier] == {"low": repeat_low, "high_exclusive": repeat_high}
        plan = cfg["swap_plan"]
        assert plan["partner_rule"] == "s5_balanced_greedy" and plan["s5"]["score"] == "sum_max"
        assert plan["s5"]["require_connected_graph"] is False


def test_M5b容器选择保持前三个且拒绝空槽bin3():
    from robomme.robomme_env.utils.episode_spec import EpisodeSpecError

    assert ux.validate_hidden_bin_selection([2, 0, 1], permutation_size=3) == [2, 0, 1]
    for invalid in ([0, 1, 3], [0, 0, 1], [0, 1]):
        with pytest.raises(EpisodeSpecError, match="bin_3 恒空"):
            ux.validate_hidden_bin_selection(invalid, permutation_size=3)


@pytest.mark.parametrize("tier,cube_count,n_swaps", [
    ("xhard1", 4, 3), ("xhard2", 5, 5), ("xhard3", 6, 7), ("xhard4", 7, 9),
])
def test_VR_S5四档固定可行图规划与回放(tier, cube_count, n_swaps, monkeypatch):
    module = importlib.import_module("robomme.robomme_env.VideoRepick")
    cls = module.VideoRepick
    decision = module._native_decision(cls)
    class _CompleteGraph:
        def __init__(self, _states, statics):
            self.cache = {}
            self.statics = list(statics)

        def feasible(self, a, b):
            self.cache[(min(a, b), max(a, b))] = True
            return True

    monkeypatch.setattr(module, "_XhardSlotSweepFeasibility", _CompleteGraph)
    monkeypatch.setattr(
        module, "cube_obb2d_exact",
        lambda actor, half: (np.array([actor.index * 0.1, 0.0]), np.eye(2), np.array([half, half])),
    )

    def make_env(spec=None):
        env = SimpleNamespace(
            difficulty=tier,
            cube_half_size=0.02,
            spawned_cubes=[SimpleNamespace(index=i) for i in range(cube_count)],
            swap_times=n_swaps,
            _sampling={"decision": copy.deepcopy(decision), "positions": {"button": {"scale": 1.5}}},
            _spec=SpecRecorder(spec, "VideoRepick", {"seed": 8800}, difficulty=tier),
        )
        return env

    env = make_env()
    button_obb = (np.array([0.0, 0.0]), np.eye(2), np.array([0.05, 0.05]))
    pairs = cls._plan_swaps_newvalue_v6(env, 12345, button_obb)
    plan = env._newvalue_swap_plan_info["plan"]
    assert len(pairs) == n_swaps == len(plan)
    assert len(env.spawned_cubes) == cube_count and env.swap_times == n_swaps
    assert env._newvalue_swap_plan_info["summary"]["undo"] == 0
    assert max(env._newvalue_swap_plan_info["summary"]["counts"]) - min(
        env._newvalue_swap_plan_info["summary"]["counts"]
    ) <= 1
    spec = copy.deepcopy(env._spec.to_dict())
    replay = make_env(spec)
    cls._plan_swaps_newvalue_v6(replay, 12345, button_obb)
    assert replay._spec.mismatches == []
    assert replay._newvalue_swap_partners == env._newvalue_swap_partners


def test_V5快照SHA与三个环境旧版导出逐任务相同():
    snapshots = {
        "newtask-v4": REPO_ROOT / "scripts" / "configs" / "newtask-v4" / "sampling_config.json",
        "newtask-v5": REPO_ROOT / "scripts" / "configs" / "newtask-v5" / "sampling_config.json",
    }
    v5_snapshot = snapshots["newtask-v5"]
    assert hashlib.sha256(v5_snapshot.read_bytes()).hexdigest() == (
        "c45d4408a5b87d71a8be72d1724322f06d6801118bb53e4afdffd07b1eaf8315"
    )
    for release, snapshot in snapshots.items():
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        for task in ("VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick"):
            module = importlib.import_module(f"robomme.robomme_env.{task}")
            cls = getattr(module, task)
            decision, native = module.native_blocks(cls, release=release)
            assert {"decision": decision, "native": native} == payload["tasks"][task]


@pytest.mark.parametrize("task", ["VideoUnmaskSwap", "ButtonUnmaskSwap"])
def test_step锁定循环里新值档读预规划_原三档仍取最近邻(task):
    tree = ast.parse((ENV_DIR / f"{task}.py").read_text(encoding="utf-8"))
    step = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "step")
    loops = [n for n in ast.walk(step) if isinstance(n, ast.For) and ast.unparse(n.iter) == "range(len(self.swap_schedule))"]
    assert len(loops) == 1
    text = ast.unparse(loops[0])
    assert "if getattr(self, '_is_newvalue', False):" in text
    assert "closest_actor = self._newvalue_planned_partner(i, pair_idx1)" in text
    assert "dist < closest_dist" in text
