"""外部规格生成器的采样基础设施（NEW_VALUE_INJECTION_TEST_PLAN 第四节）。

三类字段各有各的办法：

* **能独立选的离散量** —— :func:`quota_series`：按类数平分 100 条（两类 50/50、三类
  34/33/33、五类各 20），并且**按批均衡**：每批 10 条内也按同一比例分，因此前 3 批
  30 条（步骤 5 的实跑范围）本身就是一个均衡小样本。
* **连续量** —— :class:`Stratified`：10 个粗分箱 × 10 个细分层组织成 10 批，每批从每个
  粗分箱取一个细分层点。无几何拒绝时全部 100 条每箱恰 10 条，每批 10 条覆盖全部 10 箱。
* **受约束的耦合量** —— 只在合法候选内平衡，报实际频数，不声称严格均匀。

随机流由 :func:`derive_rng` 从固定 seed 与稳定的任务／难度标识派生，**不用受进程影响的
Python ``hash()``**，因此生成结果与进程调度、字典顺序、并行度都无关。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

#: 每组规格条数，也是粗分箱数 × 细分层数。
GROUP_SIZE = 100
#: 连续变量的粗分箱数；同时是批数（每批 10 条，每箱各取一条）。
COARSE_BINS = 10
#: 每个粗分箱内的细分层数。
FINE_LAYERS = 10


def derive_rng(seed: int, *labels: str) -> np.random.Generator:
    """按固定 seed 与稳定标识派生独立随机流。

    标识用 ``|`` 连接后取 SHA-256 的前 8 字节做子 seed；同一组标识在任何机器、任何
    进程顺序下都得到同一条流，因此 ``plan`` 跑两遍逐记录散列相同（``SPEC_REPRODUCIBLE``）。
    """
    payload = "|".join((str(seed), *labels)).encode("utf-8")
    sub_seed = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return np.random.Generator(np.random.PCG64(sub_seed))


def quota_counts(num_classes: int, total: int = GROUP_SIZE) -> list[int]:
    """``n_i ∈ {floor(total/k), ceil(total/k)}`` 且 ``sum(n_i) = total``。"""
    if num_classes < 1:
        raise ValueError("类别数必须大于 0")
    base, extra = divmod(total, num_classes)
    return [base + (1 if i < extra else 0) for i in range(num_classes)]


def quota_series(
    values: Sequence[Any],
    rng: np.random.Generator,
    *,
    total: int = GROUP_SIZE,
    batches: int = COARSE_BINS,
) -> list[Any]:
    """把 ``values`` 按配额铺满 ``total`` 条，并让每一批内部也按同一比例分配。

    先算全局配额（计数差不超过 1），再把每个类别的条数按 ``floor(n·(t+1)/B) −
    floor(n·t/B)`` 摊到 B 个批次里，最后每批内部打乱。这样：

    * 全局计数差 ≤ 1 —— ``COVERAGE_QUOTA`` 的独立类别判据；
    * 任意一批 10 条都是按比例的小样本 —— 实跑只取前 3 批时不至于偏到某一类。
    """
    counts = quota_counts(len(values), total)
    per_batch: list[list[Any]] = [[] for _ in range(batches)]
    for value, count in zip(values, counts):
        previous = 0
        for t in range(batches):
            current = (count * (t + 1)) // batches
            per_batch[t].extend([value] * (current - previous))
            previous = current
    series: list[Any] = []
    for bucket in per_batch:
        order = rng.permutation(len(bucket))
        series.extend(bucket[i] for i in order)
    if len(series) != total:
        raise AssertionError(f"配额铺设结果 {len(series)} 条，应为 {total} 条")
    return series


@dataclass
class Stratified:
    """一个连续变量在 ``[low, high)`` 上的分层采样计划。

    ``bin_of[e]`` / ``layer_of[e]`` 是 episode ``e`` 落在哪个粗箱、哪个细层，
    ``check`` 直接按这两个数组重算配额，不必反推数值。
    """

    low: float
    high: float
    values: list[float]
    bin_of: list[int]
    layer_of: list[int]

    def cell_bounds(self, episode: int) -> tuple[float, float]:
        """该 episode 所在细分层格的取值区间，供同格重采样使用。"""
        index = self.bin_of[episode] * FINE_LAYERS + self.layer_of[episode]
        span = (self.high - self.low) / (COARSE_BINS * FINE_LAYERS)
        return self.low + index * span, self.low + (index + 1) * span

    def coarse_bounds(self, episode: int) -> tuple[float, float]:
        """该 episode 所在**粗分箱**的取值区间。"""
        span = (self.high - self.low) / COARSE_BINS
        index = self.bin_of[episode]
        return self.low + index * span, self.low + (index + 1) * span

    def resample(self, episode: int, rng: np.random.Generator) -> float:
        """几何拒绝后的重采样：留在**同一个粗分箱**内重抽。

        ⚠ 粒度取粗箱而不是细分层格。配额判据（``COVERAGE_QUOTA``）验的是「10 个粗箱
        每箱恰 10 条、每批 10 条覆盖全部 10 箱」，粗箱不变就保住了全部判据；而细分层格
        只有粗箱的十分之一宽（``VideoRepick`` 的偏移量只有 0.001 米），一旦该格对应的
        布局必然碰撞就无解——实测 ``VideoRepick/medium/episode 79`` 正是这样耗尽 256 个
        候选的，且两个视频任务的「整组旋转」不改变对象间相对距离，救不回来。
        """
        lo, hi = self.coarse_bounds(episode)
        return float(rng.uniform(lo, hi))


def stratify(low: float, high: float, rng: np.random.Generator, *, total: int = GROUP_SIZE) -> Stratified:
    """构造分层采样计划：10 批 × 每批 10 条，每批覆盖全部 10 个粗箱。

    每个变量用自己的两组排列（批内的粗箱顺序、每个粗箱里细层的批次顺序），
    因此不同坐标不会一起落到同一条对角线上。
    """
    if total != COARSE_BINS * FINE_LAYERS:
        raise ValueError("分层采样目前只支持 10×10 的 100 条布置")
    # layer_order[b][t]：第 t 批在粗箱 b 里用第几个细层
    layer_order = [rng.permutation(FINE_LAYERS) for _ in range(COARSE_BINS)]
    values = [0.0] * total
    bin_of = [0] * total
    layer_of = [0] * total
    span = (high - low) / (COARSE_BINS * FINE_LAYERS)
    for t in range(COARSE_BINS):
        bin_order = rng.permutation(COARSE_BINS)
        for k in range(COARSE_BINS):
            episode = t * COARSE_BINS + k
            coarse = int(bin_order[k])
            fine = int(layer_order[coarse][t])
            cell = coarse * FINE_LAYERS + fine
            values[episode] = float(low + (cell + rng.random()) * span)
            bin_of[episode] = coarse
            layer_of[episode] = fine
    return Stratified(low=low, high=high, values=values, bin_of=bin_of, layer_of=layer_of)


def block_label(label: str, block: int) -> str:
    """第 ``block`` 个 100 条 block 的随机流标签（2026-09-12 每 env 400 条交付引入）。

    block 0 **原样返回**传入标签，因此 ``blocks=1`` 时派生的每一条流与此前逐位相同——
    这是「扩容后前 100 条与 07/09 冻结逐条散列不变」的根据；block ≥1 挂 ``@block<b>`` 后缀，
    与 block 0 完全独立、可单独复现、可追加而不动已冻结的 block。
    """
    if block < 0:
        raise ValueError(f"block 序号不能为负：{block}")
    return label if block == 0 else f"{label}@block{block}"


def concat_strata(parts: Sequence[Stratified]) -> Stratified:
    """把逐 block 各自 ``stratify`` 出来的计划按 block 顺序拼接成一份。

    ``values`` / ``bin_of`` / ``layer_of`` 直接首尾相接，全局 episode 号 ``b×100+i`` 就是拼接后的下标；
    ``cell_bounds`` / ``coarse_bounds`` / ``resample`` 只按下标查表，与总条数无关，拼接后照用。
    """
    if not parts:
        raise ValueError("至少要有一个 block")
    low, high = parts[0].low, parts[0].high
    for part in parts[1:]:
        if part.low != low or part.high != high:
            raise ValueError("各 block 的取值区间必须相同")
    return Stratified(
        low=low,
        high=high,
        values=[v for part in parts for v in part.values],
        bin_of=[b for part in parts for b in part.bin_of],
        layer_of=[l for part in parts for l in part.layer_of],
    )


def balanced_choice(rng: np.random.Generator, candidates: Sequence[Any], usage: dict[Any, int]) -> Any:
    """在合法候选里挑一个：优先用得最少的，平局随机。

    用于路线节点、交换对象对这类**受几何与动作耦合**的量——它们无法预先分配配额，
    只能边走边平衡，最终报实际频数而不声称严格均匀。
    """
    if not candidates:
        raise ValueError("候选为空")
    least = min(usage.get(item, 0) for item in candidates)
    tied = [item for item in candidates if usage.get(item, 0) == least]
    picked = tied[int(rng.integers(len(tied)))]
    usage[picked] = usage.get(picked, 0) + 1
    return picked
