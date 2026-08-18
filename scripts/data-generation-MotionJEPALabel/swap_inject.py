#!/usr/bin/env python3
"""swap 对象注入、读回校验、逐帧位姿探针、布局指纹。

所有函数针对 **unwrapped** 的 VideoUnmaskSwap / ButtonUnmaskSwap 实例。
注入原理（已实跑验证）：swap 对象选择位于 `_load_scene` RNG 流最末尾，且
`swap_pair{k}_idx2` 本就留 None、由运行时最近邻回填 —— 因此 reset 之后直接
覆写六个属性再 `_refresh_swap_schedule()`，不消耗任何随机数，布局/颜色/
任务目标逐比特不变。idx2 必须显式给出，否则会在窗口首帧被最近邻逻辑覆盖。

探针原理：`step()` 里的 swap teleport 发生在 `super().step(action)` 之前，
RecordWrapper 每次 step 调用记录一帧 —— 在实例上替换 `step`（实例属性遮蔽
类方法，零 src 改动），原 step 返回后采样各 actor 位置，`trace[t]` 与 h5 的
`timestep_t` 天然一一对应（同一次调用）。
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np


# 判定「该 bin 在本窗口真的交换了」的净位移阈值（米）：交换对的净位移=两 bin 间距
# （≥0.055 m），被 other_cube 锁定的旁观 bin 即便被对角路径擦碰、来回抖动
# （实测路径长可达 0.11 m），净位移也近乎为零 —— 所以判据必须用首末净位移，
# 不能用路径长。旁观扰动作为质量指标另行记录。
MOVED_NET_EPS = 0.03
# 旁观 bin 净位移超过此值记为「被扰动」（不作废变体，写进标签供下游过滤）
DISTURBED_NET_EPS = 0.02


def _xyz(actor: Any) -> np.ndarray:
    """actor 位置 → float64 (3,)。兼容 torch 张量与批量形状。"""
    pos = actor.pose.p
    if hasattr(pos, "detach"):
        pos = pos.detach().cpu().numpy()
    return np.asarray(pos, dtype=np.float64).reshape(-1)[:3]


def _quat(actor: Any) -> np.ndarray:
    quat = actor.pose.q
    if hasattr(quat, "detach"):
        quat = quat.detach().cpu().numpy()
    return np.asarray(quat, dtype=np.float64).reshape(-1)[:4]


def bin_index(task_env: Any, actor: Any) -> int:
    """按对象身份（is）在 spawned_bins 里定位下标；用 == 会踩 Actor 的自定义比较。"""
    for idx, candidate in enumerate(task_env.spawned_bins):
        if candidate is actor:
            return idx
    raise ValueError(f"actor {getattr(actor, 'name', actor)!r} 不在 spawned_bins 里")


def inject_pairs(task_env: Any, pairs: Sequence[tuple[int, int]]) -> None:
    """reset() 之后调用。把计划的交换序列写进 swap_pair{1,2,3}_idx1/idx2。"""
    bins = task_env.spawned_bins
    if len(pairs) != int(task_env.swap_times):
        raise ValueError(
            f"计划 {len(pairs)} 次交换，但该 seed 的 swap_times={task_env.swap_times}——"
            "本链路只换对象不换次数"
        )
    for k in range(1, 4):
        if k <= len(pairs):
            i, j = pairs[k - 1]
            setattr(task_env, f"swap_pair{k}_idx1", bins[i])
            setattr(task_env, f"swap_pair{k}_idx2", bins[j])
        else:
            setattr(task_env, f"swap_pair{k}_idx1", None)
            setattr(task_env, f"swap_pair{k}_idx2", None)
    task_env._refresh_swap_schedule()


def readback_pairs(task_env: Any) -> list[tuple[int | None, int | None]]:
    """从 swap_schedule 反查 bin 下标序列（无序对，规范化为 (小, 大)）。

    未注入时第 2/3 窗口的 idx2 在进入窗口前是 None —— 完整读回须在 rollout
    之后、close 之前进行。
    """
    result: list[tuple[int | None, int | None]] = []
    for actor_a, actor_b, _start, _end in task_env.swap_schedule:
        idx_a = bin_index(task_env, actor_a) if actor_a is not None else None
        idx_b = bin_index(task_env, actor_b) if actor_b is not None else None
        if idx_a is not None and idx_b is not None:
            result.append((min(idx_a, idx_b), max(idx_a, idx_b)))
        else:
            result.append((idx_a, idx_b))
    return result


def attach_pose_probe(task_env: Any) -> list[dict]:
    """实例级替换 step，逐帧采样 bin/cube 绝对位置。返回 trace 列表（原位追加）。

    trace[t] 采样于第 t 次 step 调用返回后（t = 调用入口时的 elapsed_steps），
    与 h5 的 timestep_t、swap 逻辑里的 cur_step 同一口径。
    """
    trace: list[dict] = []
    orig_step = task_env.step  # 绑定方法（类上的 step）

    def stepped(action: Any) -> Any:
        ts = int(task_env.elapsed_steps)
        result = orig_step(action)
        trace.append(
            {
                "step": ts,
                "bins": np.stack([_xyz(b) for b in task_env.spawned_bins]),
                "cubes": np.stack([_xyz(c) for c in task_env.spawned_dynamic_cubes]),
            }
        )
        return result

    task_env.step = stepped
    return trace


def layout_fingerprint(task_env: Any) -> dict:
    """reset 之后、注入之前采集。同一源 episode 的所有变体必须逐比特相同 ——
    这是「其他配置完全不变」的机器判据（浮点用精确相等，因为是同一 RNG 流）。"""
    return {
        "task": type(task_env).__name__,
        "env_seed": int(task_env.seed),
        "difficulty": str(task_env.difficulty),
        "swap_times": int(task_env.swap_times),
        "pick_times": int(task_env.pick_times),
        "color_names": list(task_env.color_names),
        "selected_bin_indices": [int(item) for item in task_env.selected_bin_indices],
        "bin_to_color": {str(key): str(value) for key, value in task_env.bin_to_color.items()},
        "bins": [
            {
                "name": str(getattr(actor, "name", f"bin_{idx}")),
                "p": [float(v) for v in _xyz(actor)],
                "q": [float(v) for v in _quat(actor)],
            }
            for idx, actor in enumerate(task_env.spawned_bins)
        ],
        "cubes": [
            {
                "name": str(getattr(actor, "name", f"cube_{idx}")),
                "p": [float(v) for v in _xyz(actor)],
                "q": [float(v) for v in _quat(actor)],
            }
            for idx, actor in enumerate(task_env.spawned_dynamic_cubes)
        ],
        "task_names": [str(entry.get("name")) for entry in task_env.task_list],
    }


# ── trace 反解与体检 ─────────────────────────────────────────────────────────


def measured_events(
    trace: Sequence[dict],
    windows: Sequence[tuple[int, int]],
    num_bins: int,
) -> list[dict]:
    """从 trace 反解每个窗口实际交换了哪些 bin。这是注入生效的第二道闸，也是标签真源。

    moved_bins 按**首末净位移**判定（窗口 (s,e) 的运动步是 s+1..e：插值从 s+1 起
    产生位移，e 步做终点吸附，故取 pos[e] − pos[s]）；path_len（逐步位移累计）与
    旁观扰动只作质量指标记录。
    """
    by_step = {item["step"]: item["bins"] for item in trace}
    events = []
    for start, end in windows:
        first, last = by_step.get(start), by_step.get(end)
        if first is None or last is None:
            raise ValueError(f"trace 缺窗口端点帧 {start}/{end}")
        net = np.linalg.norm(last[:, :2] - first[:, :2], axis=1)
        path = np.zeros(num_bins, dtype=np.float64)
        for t in range(start + 1, end + 1):
            prev, cur = by_step.get(t - 1), by_step.get(t)
            if prev is None or cur is None:
                continue
            path += np.linalg.norm(cur[:, :2] - prev[:, :2], axis=1)
        moved = sorted(int(idx) for idx in np.flatnonzero(net > MOVED_NET_EPS))
        events.append(
            {
                "window": [int(start), int(end)],
                "moved_bins": moved,
                "net_disp": [round(float(v), 4) for v in net],
                "path_len": [round(float(v), 4) for v in path],
            }
        )
    return events


def bystander_metrics(
    events: Sequence[dict], pairs: Sequence[tuple[int, int]], num_bins: int
) -> dict:
    """旁观 bin（不在当前窗口交换对里）的最大净位移/路径长，及被扰动名单。"""
    net_max = 0.0
    path_max = 0.0
    disturbed: set[int] = set()
    for event, pair in zip(events, pairs):
        for idx in range(num_bins):
            if idx in pair:
                continue
            net = event["net_disp"][idx]
            net_max = max(net_max, net)
            path_max = max(path_max, event["path_len"][idx])
            if net > DISTURBED_NET_EPS:
                disturbed.add(idx)
    return {
        "bystander_net_max": round(net_max, 4),
        "bystander_path_max": round(path_max, 4),
        "disturbed_bins": sorted(disturbed),
    }


def min_clearance(
    trace: Sequence[dict],
    windows: Sequence[tuple[int, int]],
    pairs: Sequence[tuple[int, int]],
    num_bins: int,
) -> float:
    """swap 期间，交换中的 bin 与被锁定的其他 bin 的最小 xy 中心距（米）。

    对角远距交换可能擦过第三个 bin —— 不修环境，量化后写进标签供下游过滤。
    """
    lowest = float("inf")
    by_step = {item["step"]: item["bins"] for item in trace}
    for (start, end), (i, j) in zip(windows, pairs):
        others = [b for b in range(num_bins) if b not in (i, j)]
        if not others:
            continue
        for t in range(start, end + 1):
            bins = by_step.get(t)
            if bins is None:
                continue
            for mover in (i, j):
                for other in others:
                    dist = float(np.linalg.norm(bins[mover, :2] - bins[other, :2]))
                    lowest = min(lowest, dist)
    return lowest
