#!/usr/bin/env python3
"""seed 布局与难度循环：不读 metadata，按公式自算每个 episode 的 seed 与 difficulty。

四代数据集共用同一形式的 seed 公式：

    seed = offset + env_code * env_block + episode * EPISODE_STRIDE + attempt

其中 ``env_code`` 是任务在 16 任务规范序里的 1-indexed 位置，``attempt`` 从 0 开始，
每失败一次加 1。train 那一代对应 ``offset=0, env_block=1000``，已用四个 Unmask 系 env
的 train metadata 逐条反解验证。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


# 复用既有的 16 任务规范序，不在本文件重复定义
SCRIPT_DIR = Path(__file__).resolve().parent
CONTRACT_DIR = SCRIPT_DIR.parent / "data-generation"
if str(CONTRACT_DIR) not in sys.path:
    sys.path.insert(0, str(CONTRACT_DIR))

from validate_generated_dataset_contract import ALL_TASKS  # noqa: E402


EPISODE_STRIDE = 100
MAX_ATTEMPTS = 100
DIFFICULTY_ORDER = ("easy", "medium", "hard")


class SeedLayoutError(RuntimeError):
    """seed 布局参数或任务名非法。"""


@dataclass(frozen=True)
class SeedLayout:
    """一代数据集的 seed 布局。"""

    offset: int
    env_block: int

    def base_seed(self, task: str, episode: int) -> int:
        """该 episode 的 attempt=0 起始 seed。"""
        return self.offset + env_code(task) * self.env_block + episode * EPISODE_STRIDE

    def seed(self, task: str, episode: int, attempt: int) -> int:
        if not 0 <= attempt < MAX_ATTEMPTS:
            raise SeedLayoutError(f"attempt 必须落在 [0, {MAX_ATTEMPTS})，当前为 {attempt}")
        return self.base_seed(task, episode) + attempt


LAYOUTS = {
    "train": SeedLayout(offset=0, env_block=1_000),
    "test": SeedLayout(offset=500_000, env_block=10_000),
    "val": SeedLayout(offset=1_000_000, env_block=10_000),
    "heldout": SeedLayout(offset=1_500_000, env_block=100_000),
}
DEFAULT_LAYOUT = "train"


def env_code(task: str) -> int:
    """任务在 16 任务规范序里的 1-indexed 位置。"""
    try:
        return ALL_TASKS.index(task) + 1
    except ValueError as exc:
        raise SeedLayoutError(f"未知环境名：{task}") from exc


def get_layout(name: str) -> SeedLayout:
    try:
        return LAYOUTS[name]
    except KeyError as exc:
        raise SeedLayoutError(
            f"未知 seed 布局：{name}；可选 {sorted(LAYOUTS)}"
        ) from exc


def parse_difficulty_ratio(ratio: str) -> tuple[str, ...]:
    """把 ratio 字符串展开成一个难度循环。

    ``"211"`` → ``("easy", "easy", "medium", "hard")``，即每 4 个 episode 里
    2 个 easy、1 个 medium、1 个 hard，按 ``episode % 4`` 取。
    """
    text = ratio.strip()
    if len(text) != len(DIFFICULTY_ORDER) or not text.isdigit():
        raise SeedLayoutError(
            f"difficulty ratio 必须是 {len(DIFFICULTY_ORDER)} 位数字（easy/medium/hard 各一位），当前为 {ratio!r}"
        )
    counts = [int(char) for char in text]
    if sum(counts) < 1:
        raise SeedLayoutError(f"difficulty ratio 至少要有一个难度，当前为 {ratio!r}")
    cycle: list[str] = []
    for name, count in zip(DIFFICULTY_ORDER, counts):
        cycle.extend([name] * count)
    return tuple(cycle)


def difficulty_for(episode: int, cycle: tuple[str, ...]) -> str:
    return cycle[episode % len(cycle)]


def plan_episodes(
    task: str,
    episodes: int,
    cycle: tuple[str, ...],
    layout: SeedLayout,
) -> list[dict[str, object]]:
    """给出一个任务下每个 episode 的起始 seed 与难度（不含重试演进）。"""
    return [
        {
            "task": task,
            "episode": episode,
            "base_seed": layout.base_seed(task, episode),
            "difficulty": difficulty_for(episode, cycle),
        }
        for episode in range(episodes)
    ]
