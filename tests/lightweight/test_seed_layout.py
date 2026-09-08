# -*- coding: utf-8 -*-
"""轻量测试：seed_layout 的 seed 公式与难度循环，与 train metadata 逐条比对。

不跑任何 rollout，纯函数层面校验，秒级完成。目的是在花掉小时级 rollout 之前
就排除 seed 公式、env_code 取值、难度循环写错。

运行（使用 uv）：
    uv run python tests/lightweight/test_seed_layout.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root

pytestmark = [pytest.mark.lightweight]

REPO_ROOT = find_repo_root(__file__)
sys.path.insert(0, str(REPO_ROOT / "scripts" / "legacy" / "data-generation-newSeed"))

from seed_layout import (  # noqa: E402
    DEFAULT_LAYOUT,
    env_code,
    get_layout,
    parse_difficulty_ratio,
    plan_episodes,
)


TARGET_TASKS = ("VideoUnmaskSwap", "VideoUnmask", "ButtonUnmaskSwap", "ButtonUnmask")
EXPECTED_ENV_CODES = {
    "VideoUnmaskSwap": 5,
    "VideoUnmask": 6,
    "ButtonUnmaskSwap": 7,
    "ButtonUnmask": 8,
}
# train metadata 原始 ep0–99 段里 attempt != 0 的全部条目：(task, episode) -> attempt。
# ep100 起是 2026-08 用当前环境代码接续生成的，允许出现新的 attempt != 0（失败演进属正常），
# 所以精确断言只覆盖 ep0–99，ep100+ 只验 attempt 落在合法域。
ORIGINAL_EPISODES = 100
EXPECTED_PROBES = {
    ("VideoUnmaskSwap", 32): 1,
    ("VideoUnmaskSwap", 61): 1,
    ("VideoUnmask", 10): 1,
    ("ButtonUnmaskSwap", 70): 1,
    ("ButtonUnmaskSwap", 94): 1,
    ("ButtonUnmaskSwap", 98): 1,
    ("ButtonUnmask", 5): 1,
    ("ButtonUnmask", 72): 1,
}


def _train_records(task: str) -> list[dict]:
    path = (
        REPO_ROOT
        / "src"
        / "robomme"
        / "env_metadata"
        / "train"
        / f"record_dataset_{task}_metadata.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return sorted(payload["records"], key=lambda item: int(item["episode"]))


def test_env_codes_match_canonical_order() -> None:
    for task, expected in EXPECTED_ENV_CODES.items():
        assert env_code(task) == expected, f"{task} 的 env_code 应为 {expected}"


def test_difficulty_ratio_211_expands_to_expected_cycle() -> None:
    assert parse_difficulty_ratio("211") == ("easy", "easy", "medium", "hard")


@pytest.mark.parametrize("task", TARGET_TASKS)
def test_base_seed_and_difficulty_match_train_metadata(task: str) -> None:
    """每条 train 记录的 seed 应等于 base_seed + 预期 attempt，难度应逐条相同。"""
    layout = get_layout(DEFAULT_LAYOUT)
    cycle = parse_difficulty_ratio("211")
    records = _train_records(task)
    planned = plan_episodes(task, len(records), cycle, layout)

    assert len(records) >= ORIGINAL_EPISODES, f"{task} 的 train metadata 至少应有原始 100 条"
    assert [int(record["episode"]) for record in records] == list(range(len(records))), (
        f"{task} 的 episode 序号必须连续（0..{len(records) - 1}）"
    )

    for plan, record in zip(planned, records):
        episode = int(record["episode"])
        assert plan["episode"] == episode
        attempt = int(record["seed"]) - int(plan["base_seed"])
        if episode < ORIGINAL_EPISODES:
            expected_attempt = EXPECTED_PROBES.get((task, episode), 0)
            assert attempt == expected_attempt, (
                f"{task}/episode_{episode}: seed 应为 {int(plan['base_seed']) + expected_attempt}，"
                f"实际为 {record['seed']}（base_seed={plan['base_seed']}，"
                f"预期 attempt={expected_attempt}）"
            )
        else:
            assert 0 <= attempt < 100, (
                f"{task}/episode_{episode}: attempt 反解为 {attempt}，超出合法域 [0, 100)"
            )
        assert str(record["difficulty"]) == plan["difficulty"], (
            f"{task}/episode_{episode}: 难度应为 {plan['difficulty']}，"
            f"实际为 {record['difficulty']}"
        )


def test_probe_set_is_exactly_the_nonzero_attempts() -> None:
    """反过来校验：原始 ep0–99 段里除 8 个探针外，其余 392 条的 attempt 必须都是 0。"""
    layout = get_layout(DEFAULT_LAYOUT)
    found: dict[tuple[str, int], int] = {}
    for task in TARGET_TASKS:
        for record in _train_records(task):
            episode = int(record["episode"])
            if episode >= ORIGINAL_EPISODES:
                continue
            attempt = int(record["seed"]) - layout.base_seed(task, episode)
            if attempt != 0:
                found[(task, episode)] = attempt
    assert found == EXPECTED_PROBES


def test_episode_start_extension_seeds() -> None:
    """接续生成段（ep100+）的 seed 与难度锚点：episode-start 链路依赖的公式值。"""
    layout = get_layout(DEFAULT_LAYOUT)
    cycle = parse_difficulty_ratio("211")
    # ep100 难度循环回到 easy（100 % 4 == 0），seed 直接跨过 ep0–99 段
    assert layout.base_seed("VideoUnmask", 100) == 16_000
    assert layout.base_seed("VideoUnmaskSwap", 100) == 15_000
    assert layout.base_seed("ButtonUnmaskSwap", 100) == 17_000
    assert layout.base_seed("ButtonUnmask", 100) == 18_000
    assert layout.base_seed("ButtonUnmask", 399) == 47_900
    from seed_layout import difficulty_for

    assert difficulty_for(100, cycle) == "easy"
    assert difficulty_for(101, cycle) == "easy"
    assert difficulty_for(102, cycle) == "medium"
    assert difficulty_for(103, cycle) == "hard"
    # 同 env 内新旧两段的 seed 空间不重叠：ep0–99 最大可能 seed < ep100 的起始 seed
    for task in TARGET_TASKS:
        assert layout.seed(task, 99, 99) < layout.base_seed(task, 100)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
