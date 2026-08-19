#!/usr/bin/env python3
"""单事件 swap clip 的源筛选、枚举、槽位换算与编号：纯函数层，不 import gym/sapien/仿真。

宗旨（用户拍板）：**除了 bin 的初始位置和第一次 swap 的排列组合，其他全部保持一致。**
因此本模块把「变化」压缩到两个维度，其余一律钉死：

* 变化维度 1 —— bin 初始位置：由源 episode 的 env_seed 决定，跨源变化；
* 变化维度 2 —— 第一次 swap 的槽位对：只枚举该源实测几何下的**最近邻可达对**，每源 2~3 种；
* 其余（后续 swap 窗口、机器人动作、bin 数、布局模板、类别体系）全部固定，见下。

★ 最近邻约束（2026-08-19 起）
--------------------------------
原版 env 选 swap 对的真实机制是两步：``swap_pair{k}_idx1`` 在 ``_load_scene`` 里定死，
``idx2`` 留 None，进入窗口首帧才在 ``step()`` 里对全部 ``spawned_bins`` 取**距 idx1 最近的
那一个**（严格单个 argmin，见两个 env 的 ``pair_idx2 is None`` 分支）。所以旧口径的
``C(4,2)=6`` 全枚举里，有一大半的对在原版数据中**结构上永不可能出现** —— 实测 8 个源里
对角对 (0,2)/(1,3) 从来不是任何 bin 的最近邻。

本轮口径：**第一主角 idx1 放宽为任意 bin**（不受原版 ``randperm(3)`` 与任务目标耦合的
限制），但 **idx2 只能是 idx1 当时的严格最近邻**。变体空间 = ``nearest_neighbor_pairs``。

⚠ 同一份 env 源码里的 ``_compute_dynamic_swap_candidates`` / ``_select_swap_pair_from_positions``
（取最近**两个**再随机挑一个）是**全仓无调用点的死代码**，不得采信 —— 按 top-2 口径复算
会得到每源 4~5 对，与真实机制不符。

源范围（2026-08-19 扩源）：**train ep90-99 + test ep0-49 + val ep0-49 三个 split**。
episode 号只在 split 内可比（test ep3 与 val ep3 是两条无关的 episode），因此 split 是
源身份的一部分，全链路以 ``(split, task, episode)`` 为源键。

三重源筛选（缺一不可，逐 split 独立执行）：

1. **4-bin（medium/hard）**：easy 是 3-bin，且 ``region3_tri`` / ``region3_line`` 两套模板
   随 seed 二选一，类别体系（半程/全程 vs 腰/底边）与 4-bin 的（长边/短边/对角）互不相通，
   三套几何无法合成统一的多类判别标签空间。只留 ``region4`` 后模板唯一、槽位角色统一。
2. **swap_times ≥ 2**：VideoUnmaskSwap 的 demo 段长 = 最后一次 swap 结束（+0~4 帧），
   k=1 时 demo 只到 env step 114，clip 的后 30 帧会跌出 demo、机器人开始朝目标 bin 移动，
   「动作恒定」不再成立。
3. **两 env 取共同源号（split 内）**：让 Video / Button 的条数与难度构成完全对称。
   注意共同源号 **不等于**共同布局 —— 两 env 的 seed 不同（如 train ep91 是 14100 vs
   16100），bin 位置本就不同；对称性只体现在条数与难度构成上。

编号（派生 episode ↔ seed 一一对应）：

* ``staging_episode = SPLIT_CODE[split] * SPLIT_BLOCK + src_episode * VARIANT_BLOCK + variant_idx``
* ``variant_seed    = env_seed * VARIANT_BLOCK + variant_idx``（**刻意不编码 split**）

环境实际播种用的是 env_seed（同源变体共享，这正是布局不变的保证）；variant_seed 只做
唯一标识 —— 直接拿它去 gym.make 复现不了，须 env_seed + 注入。

⚠ variant_seed 不编码 split 的理由：它的契约是「可逆到 env_seed」（``decode_variant_seed``），
且作为官方格式 metadata 的 ``seed`` 字段落盘，掺入 split 码会同时破坏逆与语义。
跨 split 唯一性来自三个 split 的 env_seed 数值域互不相交（train 万位、test 55-57 万、
val 105-107 万）—— 这是**待断言的性质而非可依赖的构造**，由三重守卫看住：
单测全组合断言、生成闸门唯一性断言、merge 闸门 metadata seed 列唯一性断言。
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]

EVAL_TASKS = ("VideoUnmaskSwap", "ButtonUnmaskSwap")

# split 全集与编码（train < test < val 的顺序同时是 merge 密集重编号的排序依据）。
SPLITS = ("train", "test", "val")
SPLIT_CODE = {"train": 0, "test": 1, "val": 2}
# staging_episode 的 split 位基数。取 1e6 而非 1e5：train metadata 已扩到 ep≤399，
# 1e6 给 src_episode < 1000 的余量，防止未来扩 episode 范围时 split 边界被静默串位。
SPLIT_BLOCK = 1_000_000

# 候选源范围（筛选前）：train 是 MotionJEPA 的 eval 集 ep90-99（三重筛选后恒入选
# {91,95,98,99}）；test/val 各 50 条全量参与筛选（实测入选 15/14 源）。
CANDIDATE_EPISODES_BY_SPLIT = {
    "train": tuple(range(90, 100)),
    "test": tuple(range(0, 50)),
    "val": tuple(range(0, 50)),
}

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

# staging episode / variant seed 的编码基数。variant_idx 是 bin_pairs() 的字典序下标
# （≤5，见 pair_index），远小于 1000，不会越位。
VARIANT_BLOCK = 1000

# 判据：argmin 余量（次近距离 − 最近距离）低于此值时，最近邻判定接近平局，值得人看一眼。
# 不作废数据，只进告警。实测 8 个源的全局最小余量是 0.0089 m（Video ep98）。
NN_MARGIN_WARN = 0.005

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
    """一个源 episode 的全部静态事实（seed/difficulty 来自所属 split 的 metadata）。"""

    task: str
    split: str
    episode: int
    env_seed: int
    difficulty: str
    num_bins: int
    swap_times: int

    @property
    def num_pairs_upper_bound(self) -> int:
        """全枚举上界 ``C(n,2)`` —— **不是**本轮的实际变体数。

        实际变体数受最近邻约束、取决于该源的实测布局，只能由
        ``nearest_neighbor_pairs(slot_xy)`` 算出（n=4 时恒为 2 或 3）。
        """
        return math.comb(self.num_bins, 2)


@dataclass(frozen=True)
class ClipVariant:
    """一条 clip 变体的完整计划。

    ``slot_pairs``：每个窗口要移动的**槽位**对；窗口 1 是枚举维度，窗口 ≥2 恒等于源
    episode 原始跑实测到的槽位对 —— 这保证后 30 帧的 teleport 起止位置、被锁定旁观 bin
    的位置集合跨同源全部变体逐位相同。
    ``bin_pairs``：注入用的 **bin** 对序列，由 slot_pairs 逐窗换算而来（见
    ``bin_pairs_from_slot_pairs``）。窗口 1 之前 slot 是 identity，故两者的首项相同。

    ``variant_idx``：事件槽位对在 ``bin_pairs()`` 里的**字典序下标**（见 ``pair_index``），
    不是列表位置。最近邻约束下取值稀疏（实测只出现 0/2/3/5，对角的 1/4 恒缺席），
    这是刻意的 —— 它让 variant_idx ↔ event_slots 成为双射、跨源可比。
    """

    task: str
    split: str
    src_episode: int
    variant_idx: int
    env_seed: int
    difficulty: str
    num_bins: int
    slot_pairs: tuple[tuple[int, int], ...]
    bin_pairs: tuple[tuple[int, int], ...]
    is_original: bool

    def __post_init__(self) -> None:
        # 编号自洽：任何构造路径都绕不过去，防止未来有人退回「列表位置即 variant_idx」
        expected = pair_index(self.slot_pairs[0], self.num_bins)
        if self.variant_idx != expected:
            raise ValueError(
                f"{self.task}/ep{self.src_episode}: variant_idx={self.variant_idx} "
                f"与事件槽位对 {self.slot_pairs[0]} 的字典序下标 {expected} 不符"
            )

    @property
    def staging_episode(self) -> int:
        return staging_episode(self.split, self.src_episode, self.variant_idx)

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


def load_metadata_record(
    task: str, episode: int, split: str, repo_root: Path = REPO_ROOT
) -> tuple[int, str]:
    """从所属 split 的 metadata 读 (seed, difficulty)。

    ``split`` **必填、无默认值** —— 给个默认 "train" 就等于给「漏传即静默读错 split」
    开后门，而 seed 数值域恰好不相交会让错误静默传播很远。

    **必须读表**：attempt≠0 的 seed 公式算不出（train Button ep98 是 16801 而非规则值
    16800；val Button ep39/ep43 是 1073901/1074301）。
    """
    if split not in SPLIT_CODE:
        raise ValueError(f"未知 split：{split!r}（合法值 {SPLITS}）")
    path = (
        repo_root
        / "src"
        / "robomme"
        / "env_metadata"
        / split
        / f"record_dataset_{task}_metadata.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    for record in payload["records"]:
        if int(record["episode"]) == episode:
            return int(record["seed"]), str(record["difficulty"])
    raise KeyError(f"{task} 的 {split} metadata 里没有 episode {episode}")


def compute_swap_times(env_seed: int, difficulty: str) -> int:
    """逐字复刻 env __init__ 的 RNG 流第一笔（VideoUnmaskSwap.py:141-143）。"""
    import torch

    config = ENV_CONFIGS[difficulty]
    generator = torch.Generator()
    generator.manual_seed(env_seed)
    return int(
        torch.randint(config["swap_min"], config["swap_max"] + 1, (1,), generator=generator).item()
    )


def source_episode(
    task: str, episode: int, split: str, repo_root: Path = REPO_ROOT
) -> SourceEpisode:
    env_seed, difficulty = load_metadata_record(task, episode, split, repo_root)
    config = ENV_CONFIGS[difficulty]
    return SourceEpisode(
        task=task,
        split=split,
        episode=episode,
        env_seed=env_seed,
        difficulty=difficulty,
        num_bins=config["bin"],
        swap_times=compute_swap_times(env_seed, difficulty),
    )


# ── 源三重筛选 ────────────────────────────────────────────────────────────────


def select_sources(
    tasks: Sequence[str] = EVAL_TASKS,
    splits: Sequence[str] = SPLITS,
    episodes_by_split: Mapping[str, Iterable[int]] | None = None,
    repo_root: Path = REPO_ROOT,
    require_common: bool = True,
) -> dict[str, list[SourceEpisode]]:
    """4-bin → k≥2 → 两 env 共同源号（**split 内**）。

    返回 {task: [SourceEpisode]}，按 ``(SPLIT_CODE[split], episode)`` 升序 ——
    与 merge 的密集重编号排序一致（train < test < val）。

    共同源号只在 split 内取交集：episode 号只在 split 内可比，test ep3 与 val ep3
    是两条无关的 episode，跨 split 求交没有意义。
    """
    if episodes_by_split is None:
        episodes_by_split = CANDIDATE_EPISODES_BY_SPLIT
    per_task: dict[str, list[SourceEpisode]] = {task: [] for task in tasks}
    for split in splits:
        if split not in SPLIT_CODE:
            raise ValueError(f"未知 split：{split!r}（合法值 {SPLITS}）")
        split_kept: dict[str, list[SourceEpisode]] = {}
        for task in tasks:
            kept = []
            for episode in episodes_by_split[split]:
                src = source_episode(task, episode, split, repo_root)
                if src.num_bins != REQUIRED_BINS:
                    continue
                if src.swap_times < MIN_SWAP_TIMES:
                    continue
                kept.append(src)
            split_kept[task] = kept
        if require_common and len(split_kept) > 1:
            common = set.intersection(
                *(set(src.episode for src in kept) for kept in split_kept.values())
            )
            split_kept = {
                task: [src for src in kept if src.episode in common]
                for task, kept in split_kept.items()
            }
        for task in tasks:
            per_task[task].extend(split_kept[task])
    for task in tasks:
        per_task[task].sort(key=lambda src: (SPLIT_CODE[src.split], src.episode))
    return per_task


def select_sources_by_split(
    tasks: Sequence[str] = EVAL_TASKS,
    splits: Sequence[str] = SPLITS,
    episodes_by_split: Mapping[str, Iterable[int]] | None = None,
    repo_root: Path = REPO_ROOT,
    require_common: bool = True,
) -> dict[str, dict[str, list[SourceEpisode]]]:
    """同 ``select_sources``，但按 {split: {task: [...]}} 嵌套返回（报表与单测用）。"""
    flat = select_sources(tasks, splits, episodes_by_split, repo_root, require_common)
    nested: dict[str, dict[str, list[SourceEpisode]]] = {
        split: {task: [] for task in tasks} for split in splits
    }
    for task, sources in flat.items():
        for src in sources:
            nested[src.split][task].append(src)
    return nested


# ── 枚举与槽位换算 ────────────────────────────────────────────────────────────


def bin_pairs(num_bins: int = REQUIRED_BINS) -> list[tuple[int, int]]:
    """全部无序对，(i, j) i<j 按字典序；下标即 ``pair_index``，也即本链路的 variant_idx。

    用无序对是因为对 ``swap_flat_two_lane`` 逐项代入可证 (i,j) 与 (j,i) 轨迹逐位相同。

    ⚠ **本函数返回的是「全部对」，绝不能缩成「合法对」。** 它同时被四处复用，其中
    ``swap_inject.slot_geometry`` 靠它枚举**全部 6 对**的距离/方位角写进 h5 协变量；
    一旦缩水，``merge_clip_h5`` 取 ``pairs[f"{i}{j}"]`` 会缺项、``pair_distance`` 变 None。
    要「只枚举可达对」请用 ``nearest_neighbor_pairs``。
    """
    return list(itertools.combinations(range(num_bins), 2))


def pair_index(pair: tuple[int, int], num_bins: int = REQUIRED_BINS) -> int:
    """槽位对 → 它在 ``bin_pairs()`` 里的字典序下标，即 variant_idx。是 bin_pairs 的逆。"""
    key = (min(pair), max(pair))
    return bin_pairs(num_bins).index(key)


# ── 最近邻约束：原版 env 唯一可达的 swap 对 ───────────────────────────────────


def _slot_distance(slot_xy: Sequence[Sequence[float]], i: int, j: int) -> float:
    """两个槽位的 xy 平面距离。多余的 z 维会被忽略，三维/二维输入都能吃。"""
    a, b = slot_xy[i], slot_xy[j]
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def nearest_neighbor(slot_xy: Sequence[Sequence[float]], index: int) -> int:
    """槽位 ``index`` 的严格最近邻下标。

    **逐字复刻 env 的运行时回填**（``VideoUnmaskSwap.step`` / ``ButtonUnmaskSwap.step`` 里
    ``pair_idx2 is None`` 分支的 closest_actor 扫描）：按 ``spawned_bins`` 升序遍历、跳过
    自身、判据是严格 ``dist < closest_dist`` —— 后来者**不覆盖**同距的前者，
    因此**平局取下标最小**者。写成 ``<=`` 就变成取下标最大，与 env 不符。

    ⚠ 不要采信同文件里的 ``_compute_dynamic_swap_candidates`` /
    ``_select_swap_pair_from_positions``（取最近两个再随机）—— 全仓无调用点的死代码。
    """
    best: int | None = None
    best_dist = float("inf")
    for candidate in range(len(slot_xy)):
        if candidate == index:
            continue
        dist = _slot_distance(slot_xy, index, candidate)
        if dist < best_dist:
            best_dist = dist
            best = candidate
    if best is None:
        raise ValueError("至少要有两个槽位才能取最近邻")
    return best


def nearest_neighbor_pairs(slot_xy: Sequence[Sequence[float]]) -> list[tuple[int, int]]:
    """该布局下**原版机制可达**的 swap 对全集：``{(i, NN(i))}`` 去重后按字典序。

    这就是本链路第一次 swap 的合法变体空间：idx1 放宽为任意槽位，idx2 只能是它的最近邻。

    n=4 时结果条数恒落在 [2, 3]：全局最近的那一对必然互为最近邻（占掉 2 个槽位并去重成
    1 对），剩下 2 个槽位各贡献至多 1 对 ⇒ 上界 3；每个槽位至少贡献 1 对 ⇒ 下界 2。
    """
    pairs = {
        (min(i, nearest_neighbor(slot_xy, i)), max(i, nearest_neighbor(slot_xy, i)))
        for i in range(len(slot_xy))
    }
    return sorted(pairs)


def native_window_slots(
    slot_xy: Sequence[Sequence[float]],
    idx1_bin: int,
    prior_slot_pairs: Sequence[tuple[int, int]],
    num_bins: int = REQUIRED_BINS,
) -> tuple[int, int]:
    """**原版规则下**某个后续窗口实际会交换的槽位对（用来量化本链路对它的偏离）。

    本链路对窗口 ≥2 用的是「按槽位固定」注入（见 bin_pairs_from_slot_pairs），那是后 30 帧
    跨变体一致的前提；而原版是拿该窗口在 ``_load_scene`` 里定死的 ``idx1``（一个 **bin**）
    去取当时的最近邻。两者不一定重合 —— 因为窗口 1 可能已经把那个 bin 挪到了别的槽位。

    关键前提：``swap_flat_two_lane`` 是两个 bin **互换位置**，所以被占用的位置集合恒不变
    ⇒ **槽位层面的最近邻图在整条 episode 里不变**，可以直接用初始 slot_xy 复算。

    参数：``idx1_bin`` 是该窗口的原版 idx1（Phase 0 的 ``original_idx1``）；
    ``prior_slot_pairs`` 是该窗口**之前**各窗口实际交换的槽位对序列。
    """
    slot_of = list(range(num_bins))
    for u, v in bin_pairs_from_slot_pairs(prior_slot_pairs, num_bins):
        slot_of[u], slot_of[v] = slot_of[v], slot_of[u]
    seat = slot_of[idx1_bin]
    other = nearest_neighbor(slot_xy, seat)
    return (min(seat, other), max(seat, other))


def nearest_neighbor_margin(slot_xy: Sequence[Sequence[float]]) -> list[float]:
    """逐槽位的 argmin 余量 = d(次近) − d(最近)。余量越小，最近邻判定越接近平局。"""
    margins = []
    for index in range(len(slot_xy)):
        dists = sorted(
            _slot_distance(slot_xy, index, other)
            for other in range(len(slot_xy))
            if other != index
        )
        margins.append(dists[1] - dists[0] if len(dists) >= 2 else float("inf"))
    return margins


def load_slot_xy_index(path: Path) -> dict[tuple[str, str, int], list[list[float]]]:
    """从 Phase 0 的 ``original_index.json`` 读出 {(split, task, episode): slot_xy}。

    只解析形状，不做任何几何判断 —— 供 ``plan_table`` 的 CLI 与单测共用。
    缺 ``split`` 字段的记录（旧版单 split 索引）直接跳过 —— 旧索引对新链路等同于
    「几何不可用」，绝不能默认回填 "train" 让旧数据冒充新真值。
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[tuple[str, str, int], list[list[float]]] = {}
    for record in payload.get("records", []):
        slot_xy = (record.get("geometry") or {}).get("slot_xy")
        split = record.get("split")
        if slot_xy and split:
            out[(str(split), str(record["task"]), int(record["episode"]))] = [
                [float(value) for value in row] for row in slot_xy
            ]
    return out


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
    src: SourceEpisode,
    original_bin_pairs: Sequence[tuple[int, int]],
    slot_xy: Sequence[Sequence[float]],
) -> list[ClipVariant]:
    """对一个源 episode 枚举它的全部 clip 变体（每源 2~3 条，受最近邻约束）。

    ``original_bin_pairs`` 是 Phase 0 控制跑实测到的原始 bin 对序列（窗口 ≥2 的 idx2 是
    进窗口时最近邻回填的，只能实测拿到）。窗口 ≥2 的槽位对从它换算，全体变体共用；
    窗口 1 换成枚举值。取到原始首对的那一条即 ``is_original``，其注入序列会退化成
    原始 bin 对序列 ⇒ 仍逐位复现官方 episode。

    ``slot_xy`` 是该源 reset 后的槽位 xy（Phase 0 的 ``geometry.slot_xy``），用来算出
    最近邻合法对集合。**刻意设成必填、无默认值**：给个默认值就等于给「漏传即静默退回
    C(4,2) 全枚举」开后门，而条数、is_original、尾部唯一性等既有闸门对此**全都自洽**、
    查不出来。

    fail-loud：原始首对必须落在合法集合内（原版 idx2 本就是最近邻回填，理应恒成立）。
    一旦不成立，说明本模块的最近邻复刻与 env 实际行为脱节，必须停机排查。
    """
    label = f"{src.task}/{src.split}/ep{src.episode}"
    if len(original_bin_pairs) != src.swap_times:
        raise ValueError(
            f"{label}: 原始序列 {len(original_bin_pairs)} 段 ≠ swap_times {src.swap_times}"
        )
    if len(slot_xy) != src.num_bins:
        raise ValueError(
            f"{label}: slot_xy 有 {len(slot_xy)} 个槽位 ≠ num_bins {src.num_bins}"
        )
    legal = nearest_neighbor_pairs(slot_xy)
    original_slots = slot_pairs_from_bin_pairs(original_bin_pairs, src.num_bins)
    if original_slots[0] not in legal:
        raise ValueError(
            f"{label}: 原始首对 {original_slots[0]} 不在最近邻合法集合 "
            f"{legal} 内 —— 最近邻复刻与 env 实际行为脱节，停机排查。"
            f"各槽位 argmin 余量 ={[round(m, 5) for m in nearest_neighbor_margin(slot_xy)]}"
        )
    tail = original_slots[1:]
    specs = []
    for first in legal:
        idx = pair_index(first, src.num_bins)
        slots = (first,) + tail
        specs.append(
            ClipVariant(
                task=src.task,
                split=src.split,
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


def staging_episode(split: str, src_episode: int, variant_idx: int) -> int:
    """split 位 + episode 位 + 变体位的三段编码；三段各自带范围守卫 fail-loud。"""
    if split not in SPLIT_CODE:
        raise ValueError(f"未知 split：{split!r}（合法值 {SPLITS}）")
    if not 0 <= variant_idx < VARIANT_BLOCK:
        raise ValueError(f"variant_idx 越界：{variant_idx}")
    if not 0 <= src_episode < SPLIT_BLOCK // VARIANT_BLOCK:
        raise ValueError(
            f"src_episode 越界：{src_episode}（须 < {SPLIT_BLOCK // VARIANT_BLOCK}）"
        )
    return SPLIT_CODE[split] * SPLIT_BLOCK + src_episode * VARIANT_BLOCK + variant_idx


def variant_seed(env_seed: int, variant_idx: int) -> int:
    if not 0 <= variant_idx < VARIANT_BLOCK:
        raise ValueError(f"variant_idx 越界：{variant_idx}")
    return env_seed * VARIANT_BLOCK + variant_idx


def decode_staging_episode(staging: int) -> tuple[str, int, int]:
    code = staging // SPLIT_BLOCK
    for split, split_code in SPLIT_CODE.items():
        if split_code == code:
            remainder = staging % SPLIT_BLOCK
            return split, remainder // VARIANT_BLOCK, remainder % VARIANT_BLOCK
    raise ValueError(f"staging_episode {staging} 的 split 位 {code} 不合法")


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
    splits: Sequence[str] = SPLITS,
    episodes_by_split: Mapping[str, Iterable[int]] | None = None,
    repo_root: Path = REPO_ROOT,
    require_common: bool = True,
    geometry: Mapping[tuple[str, str, int], Sequence[Sequence[float]]] | None = None,
) -> dict:
    """筛选后的计划表：逐 (split, episode) 行 + 总计，供 --dry-run 与单测对账。

    ``geometry``（{(split, task, episode): slot_xy}）决定这张表是真值还是上界：

    * **给了几何**：``variant_count`` / ``total`` 是最近邻约束下的**真实**变体数；
    * **没给几何**：真实变体数**算不出来**（它依赖实测布局）。此时 ``variant_count`` 与
      ``total`` 一律为 ``None``，只给 ``*_upper_bound``。**绝不返回一个看起来像真值的
      C(4,2) 全枚举总数** —— 那正是本轮要消灭的旧口径。
    """
    selected = select_sources(tasks, splits, episodes_by_split, repo_root, require_common)
    rows = []
    total = 0
    total_upper = 0
    for task in tasks:
        for src in selected[task]:
            upper = src.num_pairs_upper_bound
            total_upper += upper
            slot_xy = (
                None if geometry is None else geometry.get((src.split, task, src.episode))
            )
            row = {
                "task": task,
                "split": src.split,
                "episode": src.episode,
                "env_seed": src.env_seed,
                "difficulty": src.difficulty,
                "num_bins": src.num_bins,
                "swap_times": src.swap_times,
                "variant_count_upper_bound": upper,
            }
            if slot_xy is None:
                row.update({"variant_count": None, "legal_pairs": None, "nn_margin_min": None})
            else:
                legal = nearest_neighbor_pairs(slot_xy)
                total += len(legal)
                row.update(
                    {
                        "variant_count": len(legal),
                        "legal_pairs": [f"{i}{j}" for i, j in legal],
                        "nn_margin_min": min(nearest_neighbor_margin(slot_xy)),
                    }
                )
            rows.append(row)

    available = bool(rows) and all(row["variant_count"] is not None for row in rows)
    return {
        "rows": rows,
        "geometry_available": available,
        "total": total if available else None,
        "total_upper_bound": total_upper,
        "clip": {"start": CLIP_START, "end": CLIP_END, "length": CLIP_LEN},
        "topo_table": {f"{i}{j}": name for (i, j), name in topo_table().items()},
    }


def add_source_selection_args(parser: argparse.ArgumentParser) -> None:
    """probe/generate/plan 三个 CLI 共用的源选择参数（split 化后集中定义一处）。"""
    parser.add_argument(
        "--splits",
        default=",".join(SPLITS),
        help="逗号分隔的 split 集合（train/test/val）",
    )
    for split in SPLITS:
        parser.add_argument(
            f"--episodes-{split}",
            default=",".join(str(item) for item in CANDIDATE_EPISODES_BY_SPLIT[split]),
            help=f"{split} 的候选源 episode 号（筛选前）",
        )


def parse_source_selection(args: argparse.Namespace) -> tuple[tuple[str, ...], dict[str, tuple[int, ...]]]:
    """把 CLI 的 --splits / --episodes-* 解析成 (splits, episodes_by_split)。"""
    splits = tuple(item.strip() for item in args.splits.split(",") if item.strip())
    for split in splits:
        if split not in SPLIT_CODE:
            raise SystemExit(f"未知 split：{split!r}（合法值 {SPLITS}）")
    episodes_by_split = {
        split: tuple(
            int(item)
            for item in getattr(args, f"episodes_{split}").split(",")
            if item.strip()
        )
        for split in splits
    }
    return splits, episodes_by_split


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打印 clip 变体计划（不生成任何数据）")
    parser.add_argument("--tasks", default=",".join(EVAL_TASKS), help="逗号分隔的任务名")
    add_source_selection_args(parser)
    parser.add_argument(
        "--no-common",
        dest="require_common",
        action="store_false",
        help="不要求两 env 取共同源号（默认要求，split 内取交集）",
    )
    parser.add_argument(
        "--original-index",
        default=str(SCRIPT_DIR / "outputs" / "phase0" / "original_index.json"),
        help="Phase 0 索引；提供后才能算出最近邻约束下的真实变体数（否则只能给上界）",
    )
    args = parser.parse_args(argv)

    index_path = Path(args.original_index)
    geometry = load_slot_xy_index(index_path) if index_path.exists() else None
    splits, episodes_by_split = parse_source_selection(args)

    table = plan_table(
        tasks=tuple(item.strip() for item in args.tasks.split(",") if item.strip()),
        splits=splits,
        episodes_by_split=episodes_by_split,
        require_common=args.require_common,
        geometry=geometry,
    )
    print(
        f"clip 区间 env step [{CLIP_START},{CLIP_END}) 共 {CLIP_LEN} 帧；"
        f"窗口 1 在 clip 帧 {swap_windows_clip(1)[0]}"
    )
    has_geometry = table["geometry_available"]
    print(
        f"{'task':<18} {'split':<6} {'ep':>4} {'env_seed':>9} {'难度':<7} {'bin':>3} {'k':>2} "
        f"{'变体数':>6}  {'合法对':<14} {'argmin余量':>10}"
    )
    for row in table["rows"]:
        count = row["variant_count"]
        legal = row["legal_pairs"]
        margin = row["nn_margin_min"]
        print(
            f"{row['task']:<18} {row['split']:<6} {row['episode']:>4} {row['env_seed']:>9} "
            f"{row['difficulty']:<7} {row['num_bins']:>3} {row['swap_times']:>2} "
            f"{(str(count) if count is not None else '≤' + str(row['variant_count_upper_bound'])):>6}"
            f"  {(','.join(legal) if legal else '—'):<14} "
            f"{(f'{margin:.4f}' if margin is not None else '—'):>10}"
        )
    if has_geometry:
        print(f"合计 {table['total']} 条")
    else:
        print(f"合计 ≤{table['total_upper_bound']} 条（上界）")
        print(
            f"⚠ 未找到 Phase 0 几何（{index_path}），只能给出 C(n,2) 全枚举上界。"
            "真实变体数受最近邻约束（idx2 恒为 idx1 的严格最近邻），"
            "必须有实测 slot_xy 才能算出 —— 先跑 probe_original.py。"
        )
    print("拓扑类别表：" + "  ".join(f"{k}={v}" for k, v in table["topo_table"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
