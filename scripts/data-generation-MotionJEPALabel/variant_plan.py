#!/usr/bin/env python3
"""Swap 变体的枚举、编号与 seed 公式：纯函数层，不 import gym / sapien / 仿真。

规模推导（与方案文件一致）：

* 环境 ``__init__`` 里 ``torch.Generator().manual_seed(seed)`` 后第一笔
  ``randint(swap_min, swap_max+1)`` 就是 swap 次数 k —— 完全由 (seed, difficulty)
  决定，本模块用同样两行代码离线复算，不必起仿真。
* 难度决定 bin 数（easy=3，medium/hard=4）；每次交换是 bin 的**无序对**
  （对 ``swap_flat_two_lane`` 逐项代入可证 (i,j) 与 (j,i) 轨迹逐位相同），
  故每次有 P = C(bin数, 2) 种选法；k 次交换的完整序列共 P^k 种（含相邻重复）。

编号（派生 episode ↔ seed 一一对应）：

* ``staging_episode = src_episode * VARIANT_BLOCK + variant_idx``
* ``variant_seed   = env_seed    * VARIANT_BLOCK + variant_idx``
* 两者都可整除/取余反解；环境实际播种用的是 env_seed（同一源 episode 的
  所有变体共享，这正是布局不变的保证），variant_seed 只用于文件名与 metadata
  的唯一标识 —— 直接拿 variant_seed 去 gym.make 复现不了，须 env_seed + 注入。
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

# 本链路覆盖的两个 swap 环境与源 episode 范围（用户拍板：只做 ep90-93）
EVAL_TASKS = ("VideoUnmaskSwap", "ButtonUnmaskSwap")
DEFAULT_SRC_EPISODES = (90, 91, 92, 93)

# 与 VideoUnmaskSwap.py / ButtonUnmaskSwap.py 的 configs 类属性逐字一致
# （单测用 AST 解析两份 env 源码校验此表，不在此 import 重型模块）。
ENV_CONFIGS = {
    "easy": {"bin": 3, "swap_min": 1, "swap_max": 2},
    "medium": {"bin": 4, "swap_min": 1, "swap_max": 2},
    "hard": {"bin": 4, "swap_min": 2, "swap_max": 3},
}

# 帧窗口常量，与 _refresh_swap_schedule 硬编码同源：第 i 次交换占 [64+50i, 64+50(i+1))
SWAP_WINDOW_START = 64
SWAP_WINDOW_LEN = 50

# staging episode / variant seed 的编码基数；变体数最大 216 < 1000，不会越位
VARIANT_BLOCK = 1000


@dataclass(frozen=True)
class SourceEpisode:
    """一个源 episode 的全部静态事实（seed/difficulty 来自 train metadata）。"""

    task: str
    episode: int
    env_seed: int
    difficulty: str
    num_bins: int
    swap_times: int

    @property
    def num_pairs(self) -> int:
        return math.comb(self.num_bins, 2)


@dataclass(frozen=True)
class VariantSpec:
    """一条派生变体的完整计划。pairs 是 bin 下标的无序对序列，按字典序枚举。"""

    task: str
    src_episode: int
    variant_idx: int
    env_seed: int
    difficulty: str
    num_bins: int
    pairs: tuple[tuple[int, int], ...]

    @property
    def staging_episode(self) -> int:
        return staging_episode(self.src_episode, self.variant_idx)

    @property
    def variant_seed(self) -> int:
        return variant_seed(self.env_seed, self.variant_idx)

    @property
    def swap_times(self) -> int:
        return len(self.pairs)

    @property
    def signature(self) -> str:
        return variant_signature(self.pairs)

    @property
    def windows(self) -> tuple[tuple[int, int], ...]:
        return swap_windows(len(self.pairs))

    @property
    def net_permutation(self) -> tuple[int, ...]:
        return net_permutation(self.pairs, self.num_bins)

    @property
    def is_identity_net(self) -> bool:
        return self.net_permutation == tuple(range(self.num_bins))


# ── metadata 与 RNG 复算 ──────────────────────────────────────────────────────


def load_train_record(task: str, episode: int, repo_root: Path = REPO_ROOT) -> tuple[int, str]:
    """从 train metadata 读 (seed, difficulty)。必须读表：ep94/98 等 attempt≠0 的
    seed 公式算不出（本轮 ep90-93 虽全是规则值，口径仍统一走表）。"""
    path = (
        repo_root
        / "src"
        / "robomme"
        / "env_metadata"
        / "train"
        / f"record_dataset_{task}_metadata.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    for record in payload["records"]:
        if int(record["episode"]) == episode:
            return int(record["seed"]), str(record["difficulty"])
    raise KeyError(f"{task} 的 train metadata 里没有 episode {episode}")


def compute_swap_times(env_seed: int, difficulty: str) -> int:
    """逐字复刻 env __init__ 的 RNG 流第一笔（VideoUnmaskSwap.py:141-143）。"""
    import torch

    config = ENV_CONFIGS[difficulty]
    generator = torch.Generator()
    generator.manual_seed(env_seed)
    return int(
        torch.randint(config["swap_min"], config["swap_max"] + 1, (1,), generator=generator).item()
    )


def source_episode(task: str, episode: int, repo_root: Path = REPO_ROOT) -> SourceEpisode:
    env_seed, difficulty = load_train_record(task, episode, repo_root)
    config = ENV_CONFIGS[difficulty]
    return SourceEpisode(
        task=task,
        episode=episode,
        env_seed=env_seed,
        difficulty=difficulty,
        num_bins=config["bin"],
        swap_times=compute_swap_times(env_seed, difficulty),
    )


# ── 枚举 ─────────────────────────────────────────────────────────────────────


def bin_pairs(num_bins: int) -> list[tuple[int, int]]:
    """全部无序对，(i, j) i<j 按字典序；下标即 pair_id。"""
    return list(itertools.combinations(range(num_bins), 2))


def enumerate_pair_sequences(
    num_bins: int, swap_times: int, allow_repeat_adjacent: bool = True
) -> list[tuple[tuple[int, int], ...]]:
    """按字典序枚举全部长度 swap_times 的交换序列。

    allow_repeat_adjacent=False 时过滤相邻重复对（本轮用户拍板保留，参数仅供对照）。
    """
    sequences = itertools.product(bin_pairs(num_bins), repeat=swap_times)
    if allow_repeat_adjacent:
        return list(sequences)
    return [
        seq
        for seq in sequences
        if all(seq[i] != seq[i + 1] for i in range(len(seq) - 1))
    ]


def variant_specs(
    src: SourceEpisode, allow_repeat_adjacent: bool = True
) -> list[VariantSpec]:
    return [
        VariantSpec(
            task=src.task,
            src_episode=src.episode,
            variant_idx=idx,
            env_seed=src.env_seed,
            difficulty=src.difficulty,
            num_bins=src.num_bins,
            pairs=pairs,
        )
        for idx, pairs in enumerate(
            enumerate_pair_sequences(src.num_bins, src.swap_times, allow_repeat_adjacent)
        )
    ]


# ── 编号与派生量 ──────────────────────────────────────────────────────────────


def staging_episode(src_episode: int, variant_idx: int) -> int:
    if not 0 <= variant_idx < VARIANT_BLOCK:
        raise ValueError(f"variant_idx 越界：{variant_idx}")
    return src_episode * VARIANT_BLOCK + variant_idx


def variant_seed(env_seed: int, variant_idx: int) -> int:
    if not 0 <= variant_idx < VARIANT_BLOCK:
        raise ValueError(f"variant_idx 越界：{variant_idx}")
    return env_seed * VARIANT_BLOCK + variant_idx


def decode_staging_episode(staging: int) -> tuple[int, int]:
    return staging // VARIANT_BLOCK, staging % VARIANT_BLOCK


def decode_variant_seed(seed: int) -> tuple[int, int]:
    return seed // VARIANT_BLOCK, seed % VARIANT_BLOCK


def swap_windows(swap_times: int) -> tuple[tuple[int, int], ...]:
    """第 i 次交换的 env step 窗口 [start, end)，与 _refresh_swap_schedule 同源。"""
    return tuple(
        (
            SWAP_WINDOW_START + SWAP_WINDOW_LEN * i,
            SWAP_WINDOW_START + SWAP_WINDOW_LEN * (i + 1),
        )
        for i in range(swap_times)
    )


def variant_signature(pairs: Sequence[tuple[int, int]]) -> str:
    """如 [(0,1),(2,3)] → "01|23"。"""
    return "|".join(f"{i}{j}" for i, j in pairs)


def net_permutation(pairs: Sequence[tuple[int, int]], num_bins: int) -> tuple[int, ...]:
    """依次施加各交换后的净置换：第 b 位 = bin b 最终落在哪个初始位置槽。

    恒等置换意味着末态与「没发生 swap」完全相同（如同一对连换两次）。
    """
    slot = list(range(num_bins))
    for i, j in pairs:
        slot[i], slot[j] = slot[j], slot[i]
    return tuple(slot)


# ── 规模核算 ─────────────────────────────────────────────────────────────────


def plan_table(
    tasks: Sequence[str] = EVAL_TASKS,
    episodes: Sequence[int] = DEFAULT_SRC_EPISODES,
    allow_repeat_adjacent: bool = True,
    repo_root: Path = REPO_ROOT,
) -> dict:
    """全量枚举计划：逐 episode 行 + 总计，供 --dry-run 与单测对账。"""
    rows = []
    total = 0
    for task in tasks:
        for episode in episodes:
            src = source_episode(task, episode, repo_root)
            count = len(
                enumerate_pair_sequences(src.num_bins, src.swap_times, allow_repeat_adjacent)
            )
            total += count
            rows.append(
                {
                    "task": task,
                    "episode": episode,
                    "env_seed": src.env_seed,
                    "difficulty": src.difficulty,
                    "num_bins": src.num_bins,
                    "swap_times": src.swap_times,
                    "num_pairs": src.num_pairs,
                    "variant_count": count,
                }
            )
    return {"rows": rows, "total": total, "allow_repeat_adjacent": allow_repeat_adjacent}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打印 swap 变体枚举计划（不生成任何数据）")
    parser.add_argument("--tasks", default=",".join(EVAL_TASKS), help="逗号分隔的任务名")
    parser.add_argument(
        "--episodes",
        default=",".join(str(item) for item in DEFAULT_SRC_EPISODES),
        help="逗号分隔的源 episode 号",
    )
    parser.add_argument(
        "--no-repeat-adjacent",
        dest="allow_repeat_adjacent",
        action="store_false",
        help="过滤相邻重复对（默认保留）",
    )
    args = parser.parse_args(argv)

    table = plan_table(
        tasks=tuple(item.strip() for item in args.tasks.split(",") if item.strip()),
        episodes=tuple(int(item) for item in args.episodes.split(",") if item.strip()),
        allow_repeat_adjacent=args.allow_repeat_adjacent,
    )
    header = f"{'task':<18} {'ep':>4} {'env_seed':>9} {'难度':<7} {'bin':>3} {'k':>2} {'P':>3} {'变体数':>6}"
    print(header)
    for row in table["rows"]:
        print(
            f"{row['task']:<18} {row['episode']:>4} {row['env_seed']:>9} "
            f"{row['difficulty']:<7} {row['num_bins']:>3} {row['swap_times']:>2} "
            f"{row['num_pairs']:>3} {row['variant_count']:>6}"
        )
    print(f"合计 {table['total']} 条（相邻重复对：{'保留' if table['allow_repeat_adjacent'] else '禁止'}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
