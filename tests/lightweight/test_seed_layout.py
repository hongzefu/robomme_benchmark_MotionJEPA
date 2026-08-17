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
sys.path.insert(0, str(REPO_ROOT / "scripts" / "data-generation-newSeed"))

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
# train metadata 里 attempt != 0 的全部条目：(task, episode) -> attempt
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
    planned = plan_episodes(task, 100, cycle, layout)
    records = _train_records(task)

    assert len(records) == 100, f"{task} 的 train metadata 应有 100 条"

    for plan, record in zip(planned, records):
        episode = int(record["episode"])
        assert plan["episode"] == episode
        expected_attempt = EXPECTED_PROBES.get((task, episode), 0)
        expected_seed = int(plan["base_seed"]) + expected_attempt
        assert int(record["seed"]) == expected_seed, (
            f"{task}/episode_{episode}: seed 应为 {expected_seed}，"
            f"实际为 {record['seed']}（base_seed={plan['base_seed']}，"
            f"预期 attempt={expected_attempt}）"
        )
        assert str(record["difficulty"]) == plan["difficulty"], (
            f"{task}/episode_{episode}: 难度应为 {plan['difficulty']}，"
            f"实际为 {record['difficulty']}"
        )


def test_probe_set_is_exactly_the_nonzero_attempts() -> None:
    """反过来校验：除 8 个探针外，其余 392 条的 attempt 必须都是 0。"""
    layout = get_layout(DEFAULT_LAYOUT)
    found: dict[tuple[str, int], int] = {}
    for task in TARGET_TASKS:
        for record in _train_records(task):
            episode = int(record["episode"])
            attempt = int(record["seed"]) - layout.base_seed(task, episode)
            if attempt != 0:
                found[(task, episode)] = attempt
    assert found == EXPECTED_PROBES


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
