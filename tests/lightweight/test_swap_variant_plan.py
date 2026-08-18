# -*- coding: utf-8 -*-
"""轻量测试：swap 变体枚举/编号/seed 公式，与 env 源码及 train metadata 逐条对账。

不跑任何 rollout，纯函数层面校验，秒级完成。目的是在花掉小时级 rollout 之前
就排除 swap_times 复算、难度→bin 数映射、编号公式写错。

运行（使用 uv）：
    uv run python tests/lightweight/test_swap_variant_plan.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root

pytestmark = [pytest.mark.lightweight]

REPO_ROOT = find_repo_root(__file__)
sys.path.insert(0, str(REPO_ROOT / "scripts" / "data-generation-MotionJEPALabel"))

from variant_plan import (  # noqa: E402
    DEFAULT_SRC_EPISODES,
    ENV_CONFIGS,
    EVAL_TASKS,
    VARIANT_BLOCK,
    bin_pairs,
    decode_staging_episode,
    decode_variant_seed,
    enumerate_pair_sequences,
    net_permutation,
    plan_table,
    source_episode,
    staging_episode,
    swap_windows,
    variant_seed,
    variant_signature,
    variant_specs,
)


# ── 与 env 源码对账：ENV_CONFIGS 必须与两个 env 类的 config_* 逐字一致 ─────────


def _env_configs_from_source(task: str) -> dict:
    """AST 解析 env 源码里的 config_easy/medium/hard 类属性（不 import 重型模块）。"""
    path = REPO_ROOT / "src" / "robomme" / "robomme_env" / f"{task}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in (
                "config_easy",
                "config_medium",
                "config_hard",
            ):
                found[target.id.removeprefix("config_")] = ast.literal_eval(node.value)
    assert set(found) == {"easy", "medium", "hard"}, f"{task}: 未解析到全部三档 config"
    return found


@pytest.mark.parametrize("task", EVAL_TASKS)
def test_env_configs_match_source(task: str) -> None:
    source_configs = _env_configs_from_source(task)
    for difficulty, expected in ENV_CONFIGS.items():
        actual = source_configs[difficulty]
        for key, value in expected.items():
            assert actual[key] == value, (
                f"{task}/{difficulty}: ENV_CONFIGS[{key!r}]={value} 与源码 {actual[key]} 不符"
            )


# ── 与 train metadata 对账：seed 与难度 ───────────────────────────────────────

EXPECTED_SOURCE = {
    # (task, episode): (env_seed, difficulty, num_bins, swap_times)
    ("VideoUnmaskSwap", 90): (14000, "medium", 4, 1),
    ("VideoUnmaskSwap", 91): (14100, "hard", 4, 2),
    ("VideoUnmaskSwap", 92): (14200, "easy", 3, 1),
    ("VideoUnmaskSwap", 93): (14300, "easy", 3, 2),
    ("ButtonUnmaskSwap", 90): (16000, "medium", 4, 2),
    ("ButtonUnmaskSwap", 91): (16100, "hard", 4, 3),
    ("ButtonUnmaskSwap", 92): (16200, "easy", 3, 1),
    ("ButtonUnmaskSwap", 93): (16300, "easy", 3, 2),
}


@pytest.mark.parametrize("key", sorted(EXPECTED_SOURCE))
def test_source_episode_facts(key: tuple[str, int]) -> None:
    task, episode = key
    env_seed, difficulty, num_bins, swap_times = EXPECTED_SOURCE[key]
    src = source_episode(task, episode)
    assert src.env_seed == env_seed
    assert src.difficulty == difficulty
    assert src.num_bins == num_bins
    assert src.swap_times == swap_times, (
        f"{task}/ep{episode}: swap_times 复算为 {src.swap_times}，与方案定稿的 {swap_times} 不符"
    )


# ── 规模：方案定稿的总量必须精确复现 ─────────────────────────────────────────


def test_plan_total_318() -> None:
    table = plan_table()
    per_task = {task: 0 for task in EVAL_TASKS}
    for row in table["rows"]:
        per_task[row["task"]] += row["variant_count"]
    assert per_task["VideoUnmaskSwap"] == 54
    assert per_task["ButtonUnmaskSwap"] == 264
    assert table["total"] == 318
    counts = [row["variant_count"] for row in table["rows"]]
    assert counts == [6, 36, 3, 9, 36, 216, 3, 9]


def test_plan_total_no_repeat_adjacent_234() -> None:
    table = plan_table(allow_repeat_adjacent=False)
    counts = [row["variant_count"] for row in table["rows"]]
    # P·(P-1)^(k-1)：Video [6,30,3,6]，Button [30,150,3,6]
    assert counts == [6, 30, 3, 6, 30, 150, 3, 6]
    assert table["total"] == 234


# ── 枚举语义 ─────────────────────────────────────────────────────────────────


def test_bin_pairs_lexicographic() -> None:
    assert bin_pairs(3) == [(0, 1), (0, 2), (1, 2)]
    assert bin_pairs(4) == [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]


def test_enumeration_deterministic_lexicographic() -> None:
    seqs = enumerate_pair_sequences(3, 2)
    assert len(seqs) == 9
    assert seqs[0] == ((0, 1), (0, 1))
    assert seqs[1] == ((0, 1), (0, 2))
    assert seqs[-1] == ((1, 2), (1, 2))
    # 无相邻重复的过滤只删对角
    no_repeat = enumerate_pair_sequences(3, 2, allow_repeat_adjacent=False)
    assert len(no_repeat) == 6
    assert all(seq[0] != seq[1] for seq in no_repeat)


def test_variant_specs_cover_original_space() -> None:
    """原始环境可能出现的任何 pair 序列都必须落在枚举集合内（穷尽性）。"""
    src = source_episode("ButtonUnmaskSwap", 91)  # hard，4 bin，k=3
    specs = variant_specs(src)
    assert len(specs) == 216
    all_sequences = {spec.pairs for spec in specs}
    # 任取一个合法序列（含最近邻式的重叠对）必在集合内
    assert ((0, 1), (1, 2), (0, 3)) in all_sequences
    assert ((2, 3), (2, 3), (2, 3)) in all_sequences
    # variant_idx 与枚举序一致且连续
    assert [spec.variant_idx for spec in specs] == list(range(216))


# ── 编号公式往返 ─────────────────────────────────────────────────────────────


def test_staging_and_seed_roundtrip() -> None:
    assert staging_episode(90, 5) == 90005
    assert variant_seed(14000, 5) == 14000005
    assert decode_staging_episode(90005) == (90, 5)
    assert decode_variant_seed(14000005) == (14000, 5)
    # 全域往返
    for src_ep in DEFAULT_SRC_EPISODES:
        for idx in (0, 1, 215, VARIANT_BLOCK - 1):
            assert decode_staging_episode(staging_episode(src_ep, idx)) == (src_ep, idx)
    with pytest.raises(ValueError):
        staging_episode(90, VARIANT_BLOCK)


def test_variant_seed_unique_and_disjoint_from_env_seeds() -> None:
    """variant_seed 全体互异，且不会与任何源 env_seed 撞号。"""
    seen: set[int] = set()
    for task in EVAL_TASKS:
        for episode in DEFAULT_SRC_EPISODES:
            for spec in variant_specs(source_episode(task, episode)):
                assert spec.variant_seed not in seen
                seen.add(spec.variant_seed)
    assert len(seen) == 318
    env_seeds = {value[0] for value in EXPECTED_SOURCE.values()}
    assert not seen & env_seeds


# ── 派生量 ───────────────────────────────────────────────────────────────────


def test_swap_windows() -> None:
    assert swap_windows(1) == ((64, 114),)
    assert swap_windows(3) == ((64, 114), (114, 164), (164, 214))


def test_signature_format() -> None:
    assert variant_signature([(0, 1), (2, 3)]) == "01|23"


def test_net_permutation() -> None:
    # 同一对连换两次 → 恒等（末态与没换相同）
    assert net_permutation([(0, 1), (0, 1)], 4) == (0, 1, 2, 3)
    # 不相交对交换顺序不影响净置换
    assert net_permutation([(0, 1), (2, 3)], 4) == net_permutation([(2, 3), (0, 1)], 4)
    # 单次交换
    assert net_permutation([(0, 2)], 3) == (2, 1, 0)
    # is_identity_net 属性
    src = source_episode("VideoUnmaskSwap", 93)  # easy，3 bin，k=2
    identity_specs = [spec for spec in variant_specs(src) if spec.is_identity_net]
    assert {spec.pairs for spec in identity_specs} == {
        ((0, 1), (0, 1)),
        ((0, 2), (0, 2)),
        ((1, 2), (1, 2)),
    }


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
