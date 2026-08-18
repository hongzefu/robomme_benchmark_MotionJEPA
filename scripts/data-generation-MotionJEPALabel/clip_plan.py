#!/usr/bin/env python3
"""单事件 swap clip 的源筛选、枚举、槽位换算与编号：纯函数层，不 import gym/sapien/仿真。

宗旨（用户拍板）：**除了 bin 的初始位置和第一次 swap 的排列组合，其他全部保持一致。**
因此本模块把「变化」压缩到两个维度，其余一律钉死：

* 变化维度 1 —— bin 初始位置：由源 episode 的 env_seed 决定，跨源变化；
* 变化维度 2 —— 第一次 swap 的槽位对：每源恒 ``C(4,2)=6`` 种，穷举；
* 其余（后续 swap 窗口、机器人动作、bin 数、布局模板、类别体系）全部固定，见下。

三重源筛选（缺一不可）：

1. **4-bin（medium/hard）**：easy 是 3-bin，且 ``region3_tri`` / ``region3_line`` 两套模板
   随 seed 二选一，类别体系（半程/全程 vs 腰/底边）与 4-bin 的（长边/短边/对角）互不相通，
   三套几何无法合成统一的多类判别标签空间。只留 ``region4`` 后每源恒 6 条、模板唯一。
2. **swap_times ≥ 2**：VideoUnmaskSwap 的 demo 段长 = 最后一次 swap 结束（+0~4 帧），
   k=1 时 demo 只到 env step 114，clip 的后 30 帧会跌出 demo、机器人开始朝目标 bin 移动，
   「动作恒定」不再成立。
3. **两 env 取共同源号**：让 Video / Button 的条数与难度构成完全对称。
   注意共同源号 **不等于**共同布局 —— 两 env 的 seed 不同（如 ep91 是 14100 vs 16100），
   bin 位置本就不同；对称性只体现在条数与难度构成上。

编号（派生 episode ↔ seed 一一对应，与旧链路同公式）：

* ``staging_episode = src_episode * VARIANT_BLOCK + variant_idx``
* ``variant_seed    = env_seed    * VARIANT_BLOCK + variant_idx``

环境实际播种用的是 env_seed（同源变体共享，这正是布局不变的保证）；variant_seed 只做
唯一标识 —— 直接拿它去 gym.make 复现不了，须 env_seed + 注入。
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

EVAL_TASKS = ("VideoUnmaskSwap", "ButtonUnmaskSwap")
# 候选源范围：MotionJEPA 的 eval 集（train ep90-99）。三重筛选后实际入选 {91,95,98,99}。
CANDIDATE_EPISODES = tuple(range(90, 100))

# 与 VideoUnmaskSwap.py / ButtonUnmaskSwap.py 的 configs 类属性逐字一致
# （单测用 AST 解析两份 env 源码校验此表，不在此 import 重型模块）。
ENV_CONFIGS = {
    "easy": {"bin": 3, "swap_min": 1, "swap_max": 2},
    "medium": {"bin": 4, "swap_min": 1, "swap_max": 2},
    "hard": {"bin": 4, "swap_min": 2, "swap_max": 3},
}

# 源筛选门槛
REQUIRED_BINS = 4
MIN_SWAP_TIMES = 2

# 帧窗口常量，与 _refresh_swap_schedule 硬编码同源：第 i 次交换占 [64+50i, 64+50(i+1))
SWAP_WINDOW_START = 64
SWAP_WINDOW_LEN = 50

# clip 区间：第一次 swap 窗口 [64,114) 前后各 30 帧 → env step [34,144)，共 110 帧。
# 起点 34 落在 bin 落回原位（env step 32，见 lift_and_drop_objects_back_to_original(bin,0,64)
# 的 drop_step = 0 + 64//2 = 32）之后，所以 clip 内 cube 全程被容器盖住或已藏走 ——
# 颜色根本不进画面，与「颜色不管」天然吻合。
CLIP_MARGIN = 30
CLIP_START = SWAP_WINDOW_START - CLIP_MARGIN                      # 34
CLIP_END = SWAP_WINDOW_START + SWAP_WINDOW_LEN + CLIP_MARGIN      # 144
CLIP_LEN = CLIP_END - CLIP_START                                  # 110

# staging episode / variant seed 的编码基数；每源 6 条 < 1000，不会越位
VARIANT_BLOCK = 1000

# ── 槽位拓扑：两个 env 的 region4 模板写法不同，但槽位角色完全同构 ─────────────
#
# VideoUnmaskSwap（_load_scene:196-202）：模板是固定字面量，再整体随机旋转 α∈[0,180°)
#     region4 = [[-0.05,-0.1], [-0.05,0.1], [0.1,0.1], [0.1,-0.1]]
#     angle, region = rotate_points_random(region, (0,180), generator)
# ButtonUnmaskSwap（_load_scene:234-267）：两列各带一个 seed 随机 y 偏移，
#     且 rotate_points_random 那行**被注释掉了**（α 恒为 0）
#     y1, y2 = rand()*0.1, rand()*0.1
#     region4 = [[0,-0.1+y1], [0,0.1+y1], [0.1,0.1+y2], [0.1,-0.1+y2]]
#
# 两者同构：slot 0/1 = 左列的下/上，slot 2/3 = 右列的上/下；同列两槽 y 相差恒 0.2。
# 各 bin 还要在自己 region 中心 ±0.07 内做 rejection sampling。
REGION4_VIDEO = ((-0.05, -0.10), (-0.05, 0.10), (0.10, 0.10), (0.10, -0.10))
# 模板是否再整体随机旋转（决定 pair_azimuth_local 要不要减 α）
REGION_ROTATED = {"VideoUnmaskSwap": True, "ButtonUnmaskSwap": False}
# 槽位角色：slot → (列号, 侧)。这是拓扑类别的唯一依据，两 env 通用。
SLOT_ROLE = {0: (0, "low"), 1: (0, "high"), 2: (1, "high"), 3: (1, "low")}

# 拓扑类别 —— **按槽位角色定义，不按距离**。
# 距离分档只在 Video 下成立（0.15 / 0.20 / 0.25 三档分明）；Button 的跨列距离随 y1,y2
# 变化，对角可低至 0.141、比同列的 0.20 还短，距离序根本不成立。角色则两 env 一致。
TOPO_SAME_COLUMN = "same_column"        # (0,1) (2,3) —— 同一列内上下互换
TOPO_CROSS_ALIGNED = "cross_aligned"    # (1,2) (0,3) —— 跨列、同侧（同为上或同为下）
TOPO_CROSS_DIAGONAL = "cross_diagonal"  # (0,2) (1,3) —— 跨列、异侧


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
class ClipVariant:
    """一条 clip 变体的完整计划。

    ``slot_pairs``：每个窗口要移动的**槽位**对；窗口 1 是枚举维度，窗口 ≥2 恒等于源
    episode 原始跑实测到的槽位对 —— 这保证后 30 帧的 teleport 起止位置、被锁定旁观 bin
    的位置集合跨同源全部变体逐位相同。
    ``bin_pairs``：注入用的 **bin** 对序列，由 slot_pairs 逐窗换算而来（见
    ``bin_pairs_from_slot_pairs``）。窗口 1 之前 slot 是 identity，故两者的首项相同。
    """

    task: str
    src_episode: int
    variant_idx: int
    env_seed: int
    difficulty: str
    num_bins: int
    slot_pairs: tuple[tuple[int, int], ...]
    bin_pairs: tuple[tuple[int, int], ...]
    is_original: bool

    @property
    def staging_episode(self) -> int:
        return staging_episode(self.src_episode, self.variant_idx)

    @property
    def variant_seed(self) -> int:
        return variant_seed(self.env_seed, self.variant_idx)

    @property
    def swap_times(self) -> int:
        return len(self.slot_pairs)

    @property
    def event_slots(self) -> tuple[int, int]:
        """本轮唯一的事件：窗口 1 移动的槽位对。"""
        return self.slot_pairs[0]

    @property
    def topo_class(self) -> str:
        return topo_class(self.event_slots)

    @property
    def signature(self) -> str:
        return signature_of(self.slot_pairs)

    @property
    def windows_env(self) -> tuple[tuple[int, int], ...]:
        return swap_windows_env(self.swap_times)

    @property
    def windows_clip(self) -> tuple[tuple[int, int], ...]:
        return swap_windows_clip(self.swap_times)


# ── metadata 与 RNG 复算 ──────────────────────────────────────────────────────


def load_train_record(task: str, episode: int, repo_root: Path = REPO_ROOT) -> tuple[int, str]:
    """从 train metadata 读 (seed, difficulty)。

    **必须读表**：ep94/98 等 attempt≠0 的 seed 公式算不出（本轮入选源里 ButtonUnmaskSwap
    的 ep98 就是 16801，而非规则值 16800）。
    """
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


# ── 源三重筛选 ────────────────────────────────────────────────────────────────


def select_sources(
    tasks: Sequence[str] = EVAL_TASKS,
    episodes: Iterable[int] = CANDIDATE_EPISODES,
    repo_root: Path = REPO_ROOT,
    require_common: bool = True,
) -> dict[str, list[SourceEpisode]]:
    """4-bin → k≥2 → 两 env 共同源号。返回 {task: [SourceEpisode]}（按 episode 升序）。"""
    episodes = list(episodes)
    per_task: dict[str, list[SourceEpisode]] = {}
    for task in tasks:
        kept = []
        for episode in episodes:
            src = source_episode(task, episode, repo_root)
            if src.num_bins != REQUIRED_BINS:
                continue
            if src.swap_times < MIN_SWAP_TIMES:
                continue
            kept.append(src)
        per_task[task] = kept

    if require_common and len(per_task) > 1:
        common = set.intersection(
            *(set(src.episode for src in kept) for kept in per_task.values())
        )
        per_task = {
            task: [src for src in kept if src.episode in common]
            for task, kept in per_task.items()
        }
    return per_task


# ── 枚举与槽位换算 ────────────────────────────────────────────────────────────


def bin_pairs(num_bins: int = REQUIRED_BINS) -> list[tuple[int, int]]:
    """全部无序对，(i, j) i<j 按字典序；下标即 variant_idx。

    用无序对是因为对 ``swap_flat_two_lane`` 逐项代入可证 (i,j) 与 (j,i) 轨迹逐位相同。
    """
    return list(itertools.combinations(range(num_bins), 2))


def slot_pairs_from_bin_pairs(
    pairs: Sequence[tuple[int, int]], num_bins: int = REQUIRED_BINS
) -> tuple[tuple[int, int], ...]:
    """bin 对序列 → 每个窗口实际移动的**槽位**对序列。

    槽位 = bin 的初始位置下标（bin i 起始于 slot i）。窗口 i 移动的槽位对就是当时
    这两个 bin 各自所处的槽位。
    """
    slot_of = list(range(num_bins))  # slot_of[b] = bin b 当前所在槽位
    out = []
    for u, v in pairs:
        s1, s2 = slot_of[u], slot_of[v]
        out.append((min(s1, s2), max(s1, s2)))
        slot_of[u], slot_of[v] = s2, s1
    return tuple(out)


def bin_pairs_from_slot_pairs(
    slot_pairs: Sequence[tuple[int, int]], num_bins: int = REQUIRED_BINS
) -> tuple[tuple[int, int], ...]:
    """槽位对序列 → 注入用的 bin 对序列（``slot_pairs_from_bin_pairs`` 的逆）。

    这是「窗口 ≥2 按槽位固定」的实现核心：要让第 i 个窗口永远交换**同样两个位置**上的
    东西，就得按第一次 swap 造成的置换，动态换算出当前占据这两个槽的是哪两个 bin。
    """
    bin_at = list(range(num_bins))  # bin_at[s] = 槽位 s 上当前是哪个 bin
    out = []
    for s1, s2 in slot_pairs:
        u, v = bin_at[s1], bin_at[s2]
        out.append((min(u, v), max(u, v)))
        bin_at[s1], bin_at[s2] = v, u
    return tuple(out)


def net_permutation(
    slot_pairs: Sequence[tuple[int, int]], num_bins: int = REQUIRED_BINS
) -> tuple[int, ...]:
    """依次施加各窗口交换后的净置换：第 b 位 = bin b 最终落在哪个初始槽位。"""
    slot_of = list(range(num_bins))
    for u, v in bin_pairs_from_slot_pairs(slot_pairs, num_bins):
        slot_of[u], slot_of[v] = slot_of[v], slot_of[u]
    return tuple(slot_of)


def variant_specs(
    src: SourceEpisode, original_bin_pairs: Sequence[tuple[int, int]]
) -> list[ClipVariant]:
    """对一个源 episode 枚举全部 6 条 clip 变体。

    ``original_bin_pairs`` 是 Phase 0 控制跑实测到的原始 bin 对序列（窗口 ≥2 的 idx2 是
    进窗口时最近邻回填的，只能实测拿到）。窗口 ≥2 的槽位对从它换算，全体变体共用；
    窗口 1 换成枚举值。取到原始首对的那一条即 ``is_original``，其注入序列会退化成
    原始 bin 对序列 ⇒ 仍逐位复现官方 episode。
    """
    if len(original_bin_pairs) != src.swap_times:
        raise ValueError(
            f"{src.task}/ep{src.episode}: 原始序列 {len(original_bin_pairs)} 段 "
            f"≠ swap_times {src.swap_times}"
        )
    original_slots = slot_pairs_from_bin_pairs(original_bin_pairs, src.num_bins)
    tail = original_slots[1:]
    specs = []
    for idx, first in enumerate(bin_pairs(src.num_bins)):
        slots = (first,) + tail
        specs.append(
            ClipVariant(
                task=src.task,
                src_episode=src.episode,
                variant_idx=idx,
                env_seed=src.env_seed,
                difficulty=src.difficulty,
                num_bins=src.num_bins,
                slot_pairs=slots,
                bin_pairs=bin_pairs_from_slot_pairs(slots, src.num_bins),
                is_original=(first == original_slots[0]),
            )
        )
    return specs


# ── 拓扑类别（由槽位在两列里的角色推出，两 env 通用） ─────────────────────────


def topo_class(pair: tuple[int, int]) -> str:
    """槽位对 → 拓扑类别。同列 / 跨列同侧 / 跨列异侧，与实测距离无关。

    为什么不用距离：Video 的三档名义距离确实分明（0.15/0.20/0.25），但 Button 的
    region4 带 seed 随机 y 偏移，跨列对角距离 ∈[0.141,0.316]、跨列同侧 ∈[0.100,0.141]，
    对角完全可能短于同列的 0.20 —— 距离分档在 Button 下不成立。实测距离改作连续协变量
    （标签里的 pair_distance），类别只认生成机制里的槽位角色。
    """
    a, b = min(pair), max(pair)
    (column_a, side_a), (column_b, side_b) = SLOT_ROLE[a], SLOT_ROLE[b]
    if column_a == column_b:
        return TOPO_SAME_COLUMN
    return TOPO_CROSS_ALIGNED if side_a == side_b else TOPO_CROSS_DIAGONAL


def topo_table(num_bins: int = REQUIRED_BINS) -> dict[tuple[int, int], str]:
    return {pair: topo_class(pair) for pair in bin_pairs(num_bins)}


def nominal_distance_video(pair: tuple[int, int]) -> float:
    """两槽位在 **Video** 的 region4 模板上的名义中心距（不含 rejection 抖动与旋转）。

    只用于单测交叉验证「拓扑类别 ↔ Video 距离分档」一致；Button 没有这样的常量模板。
    """
    (x1, y1), (x2, y2) = REGION4_VIDEO[pair[0]], REGION4_VIDEO[pair[1]]
    return math.hypot(x2 - x1, y2 - y1)


# ── 编号与帧号换算 ────────────────────────────────────────────────────────────


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


def swap_windows_env(swap_times: int) -> tuple[tuple[int, int], ...]:
    """第 i 次交换的 **env step** 窗口 [start, end)，与 _refresh_swap_schedule 同源。"""
    return tuple(
        (
            SWAP_WINDOW_START + SWAP_WINDOW_LEN * i,
            SWAP_WINDOW_START + SWAP_WINDOW_LEN * (i + 1),
        )
        for i in range(swap_times)
    )


def swap_windows_clip(swap_times: int) -> tuple[tuple[int, int], ...]:
    """同样的窗口换算成 **clip 帧号**（clip 帧 = env step − CLIP_START）。

    返回的是**完整**窗口，可能整体或部分落在 [0, CLIP_LEN) 之外 —— 进度（smoothstep）
    必须按完整窗口算，只是可见部分被 clip 截断。窗口 1 = [30,80)，窗口 2 = [80,130)
    （clip 只露出前 30 帧），窗口 3 = [130,180)（完全不可见）。
    """
    return tuple(
        (start - CLIP_START, end - CLIP_START) for start, end in swap_windows_env(swap_times)
    )


def clip_visible_windows(swap_times: int) -> list[int]:
    """哪些窗口下标在 clip 内至少露出一帧 —— 对账与标签只能覆盖这些窗口。"""
    return [
        idx
        for idx, (start, end) in enumerate(swap_windows_clip(swap_times))
        if start < CLIP_LEN and end > 0
    ]


def signature_of(slot_pairs: Sequence[tuple[int, int]]) -> str:
    """如 [(0,1),(2,3)] → "01|23"（槽位口径）。"""
    return "|".join(f"{i}{j}" for i, j in slot_pairs)


# ── 规模核算 ─────────────────────────────────────────────────────────────────


def plan_table(
    tasks: Sequence[str] = EVAL_TASKS,
    episodes: Iterable[int] = CANDIDATE_EPISODES,
    repo_root: Path = REPO_ROOT,
    require_common: bool = True,
) -> dict:
    """筛选后的计划表：逐 episode 行 + 总计，供 --dry-run 与单测对账。"""
    selected = select_sources(tasks, episodes, repo_root, require_common)
    rows = []
    total = 0
    for task in tasks:
        for src in selected[task]:
            count = src.num_pairs
            total += count
            rows.append(
                {
                    "task": task,
                    "episode": src.episode,
                    "env_seed": src.env_seed,
                    "difficulty": src.difficulty,
                    "num_bins": src.num_bins,
                    "swap_times": src.swap_times,
                    "variant_count": count,
                }
            )
    return {
        "rows": rows,
        "total": total,
        "clip": {"start": CLIP_START, "end": CLIP_END, "length": CLIP_LEN},
        "topo_table": {f"{i}{j}": name for (i, j), name in topo_table().items()},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打印 clip 变体计划（不生成任何数据）")
    parser.add_argument("--tasks", default=",".join(EVAL_TASKS), help="逗号分隔的任务名")
    parser.add_argument(
        "--episodes",
        default=",".join(str(item) for item in CANDIDATE_EPISODES),
        help="逗号分隔的候选源 episode 号（筛选前）",
    )
    parser.add_argument(
        "--no-common",
        dest="require_common",
        action="store_false",
        help="不要求两 env 取共同源号（默认要求）",
    )
    args = parser.parse_args(argv)

    table = plan_table(
        tasks=tuple(item.strip() for item in args.tasks.split(",") if item.strip()),
        episodes=tuple(int(item) for item in args.episodes.split(",") if item.strip()),
        require_common=args.require_common,
    )
    print(
        f"clip 区间 env step [{CLIP_START},{CLIP_END}) 共 {CLIP_LEN} 帧；"
        f"窗口 1 在 clip 帧 {swap_windows_clip(1)[0]}"
    )
    print(f"{'task':<18} {'ep':>4} {'env_seed':>9} {'难度':<7} {'bin':>3} {'k':>2} {'变体数':>6}")
    for row in table["rows"]:
        print(
            f"{row['task']:<18} {row['episode']:>4} {row['env_seed']:>9} "
            f"{row['difficulty']:<7} {row['num_bins']:>3} {row['swap_times']:>2} "
            f"{row['variant_count']:>6}"
        )
    print(f"合计 {table['total']} 条")
    print("拓扑类别表：" + "  ".join(f"{k}={v}" for k, v in table["topo_table"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
