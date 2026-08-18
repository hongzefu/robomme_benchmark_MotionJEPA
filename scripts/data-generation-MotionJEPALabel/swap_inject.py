#!/usr/bin/env python3
"""swap 对象注入、读回校验、逐帧位姿探针、布局指纹与槽位几何。

所有函数针对 **unwrapped** 的 VideoUnmaskSwap / ButtonUnmaskSwap 实例。

注入原理（已实跑验证）：swap 对象选择位于 `_load_scene` RNG 流最末尾，且
`swap_pair{k}_idx2` 本就留 None、由运行时最近邻回填 —— 因此 reset 之后直接覆写六个
属性再 `_refresh_swap_schedule()`，不消耗任何随机数，布局/颜色/任务目标逐比特不变。
idx2 必须显式给出，否则会在窗口首帧被最近邻逻辑覆盖。

探针原理：`step()` 里的 swap teleport 发生在 `super().step(action)` 之前，
RecordWrapper 每次 step 调用记录一帧 —— 在实例上替换 `step`（实例属性遮蔽类方法，
零 src 改动），原 step 返回后采样各 actor 位置，`trace[t]` 与 h5 的 `timestep_t`
天然一一对应（同一次调用）。

本轮（单事件 clip）相对旧链路的两处新增：

* **槽位几何**：`slot_geometry` 从布局指纹算出各槽位 xy、参考轴 α、以及每个槽位对的
  距离与方位角 —— 标签里「物体的相对位置」那一半。
* **分段对账**：clip 只覆盖 env step [34,144)，所以窗口 1 用完整净位移对账，
  窗口 2 只能用 clip 末帧的部分位移做方向性校验，窗口 3 完全不对账。
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence

import numpy as np


# 判定「该 bin 在本窗口真的交换了」的净位移阈值（米）：交换对的净位移 = 两 bin 间距
# （≥0.055 m），被 other_cube 锁定的旁观 bin 即便被对角路径擦碰、来回抖动
# （实测路径长可达 0.11 m），净位移也近乎为零 —— 所以判据必须用首末净位移，
# 不能用路径长。旁观扰动作为质量指标另行记录。
MOVED_NET_EPS = 0.03
# 旁观 bin 净位移超过此值记为「被扰动」（不作废变体，写进标签供下游过滤）
DISTURBED_NET_EPS = 0.02
# 窗口 2 在 clip 内只露出前 30 帧，此时交换对已推进过半 —— 部分位移的下限放宽到这里
PARTIAL_MOVED_EPS = 0.01
# 接触冲量下限：PhysX 会把「贴得很近但没使上力」的物体也配成接触对（impulse 恒 0），
# 实测 48 条 clip 里容器之间几乎每帧都有这种零冲量候选。判「真的撞上了」必须看冲量。
FORCEFUL_IMPULSE_EPS = 1e-9


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


# ── 注入与读回 ───────────────────────────────────────────────────────────────


def inject_pairs(task_env: Any, pairs: Sequence[tuple[int, int]]) -> None:
    """reset() 之后调用。把计划的 **bin 对**序列写进 swap_pair{1,2,3}_idx1/idx2。

    注意传进来的是 bin 对，不是槽位对 —— 槽位→bin 的换算由
    `clip_plan.bin_pairs_from_slot_pairs` 在纯函数层完成。
    """
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

    未注入时第 2/3 窗口的 idx2 在进入窗口前是 None —— 控制跑要拿到完整原始序列，
    必须在 rollout **走完全部窗口之后**、close 之前读回。
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


# sapien 的 entity.name 会带子场景前缀（如 "scene-0_bin_0"），而 spawned_bins 的 .name
# 是裸名（"bin_0"）—— 匹配前必须先剥掉前缀，否则容器一侧永远匹配不上、接触统计恒为 0。
_SCENE_PREFIX = re.compile(r"^scene-\d+_")


def _strip_scene(name: str) -> str:
    return _SCENE_PREFIX.sub("", str(name))


def _contact_snapshot(
    task_env: Any, bin_names: dict[str, int], robot_links: set[str]
) -> dict:
    """一帧的接触分类统计（sapien `scene.get_contacts()` 全量扫一次）。

    分三类，因为它们的含义完全不同：

    * **robot_bin** —— 机械臂连杆 ↔ 容器。这是「机器人被 swap 中的容器碰到」的直接证据。
      2026-08-18 实测：**全 48 条 clip 共 0 帧**，从未发生。
    * **bin_bin** —— 容器 ↔ 容器，即交换中的两个 bin 互相撞上，或撞到被锁定的旁观 bin。
      这才是实际发生的物理接触（20/48 条），也是 ButtonUnmaskSwap 动作分叉的**真正源头**：
      它改变 PhysX 的接触求解规模与顺序，进而让机械臂-按钮的接触力数值解发生变化
      （ep95/var2 实测：env 70 起 bin_0↔bin_3 持续接触 → env 79 button_cap↔panda_finger
      的冲量出现差异 → qpos 偏离 4.7e-5 → 指数放大 → 规划分叉）。
      实测规律：cross_aligned 0/16 从不撞、cross_diagonal 13/16、same_column 7/16。
    * **robot_button** —— 机械臂 ↔ 按钮，任务本身的接触，作为对照基线记录。

    impulse 为 0 的接触点是 PhysX 的接触候选（已配对但当帧无力），所以同时记
    `*_count`（接触点数）与 `*_impulse`（冲量范数之和），下游可按需选判据。
    """
    stats = {
        "robot_bin_count": 0, "robot_bin_impulse": 0.0,
        "bin_bin_count": 0, "bin_bin_impulse": 0.0,
        "robot_button_count": 0, "robot_button_impulse": 0.0,
        "bin_bin_pairs": set(), "bin_bin_forceful_pairs": set(),
    }
    try:
        contacts = task_env.scene.get_contacts()
    except Exception:  # noqa: BLE001  拿不到接触不该拖垮生成
        stats["bin_bin_pairs"] = []
        stats["bin_bin_forceful_pairs"] = []
        return stats
    for contact in contacts:
        try:
            name_a = _strip_scene(contact.bodies[0].entity.name)
            name_b = _strip_scene(contact.bodies[1].entity.name)
            impulse = float(
                np.linalg.norm(sum(np.asarray(point.impulse) for point in contact.points))
            )
            points = len(contact.points)
        except Exception:  # noqa: BLE001
            continue
        in_bin = [name for name in (name_a, name_b) if name in bin_names]
        in_robot = [name for name in (name_a, name_b) if name in robot_links]
        is_button = any("button" in name for name in (name_a, name_b))
        if len(in_bin) == 2:
            stats["bin_bin_count"] += points
            stats["bin_bin_impulse"] += impulse
            pair = tuple(sorted((bin_names[in_bin[0]], bin_names[in_bin[1]])))
            stats["bin_bin_pairs"].add(pair)
            if impulse > FORCEFUL_IMPULSE_EPS:
                stats["bin_bin_forceful_pairs"].add(pair)
        elif in_bin and in_robot:
            stats["robot_bin_count"] += points
            stats["robot_bin_impulse"] += impulse
        elif in_robot and is_button:
            stats["robot_button_count"] += points
            stats["robot_button_impulse"] += impulse
    stats["bin_bin_pairs"] = sorted(stats["bin_bin_pairs"])
    stats["bin_bin_forceful_pairs"] = sorted(stats["bin_bin_forceful_pairs"])
    return stats


def attach_pose_probe(task_env: Any, with_contacts: bool = True) -> list[dict]:
    """实例级替换 step，逐帧采样 bin/cube 绝对位置与接触统计。返回 trace（原位追加）。

    trace[t] 采样于第 t 次 step 调用返回后（t = 调用入口时的 elapsed_steps），
    与 h5 的 timestep_t、swap 逻辑里的 cur_step 同一口径。
    """
    trace: list[dict] = []
    orig_step = task_env.step  # 绑定方法（类上的 step）

    bin_names: dict[str, int] = {}
    robot_links: set[str] = set()
    if with_contacts:
        bin_names = {
            _strip_scene(getattr(actor, "name", f"bin_{idx}")): idx
            for idx, actor in enumerate(task_env.spawned_bins)
        }
        try:
            robot_links = {_strip_scene(link.name) for link in task_env.agent.robot.links}
        except Exception:  # noqa: BLE001
            robot_links = set()

    def stepped(action: Any) -> Any:
        ts = int(task_env.elapsed_steps)
        result = orig_step(action)
        sample = {
            "step": ts,
            "bins": np.stack([_xyz(b) for b in task_env.spawned_bins]),
            "cubes": np.stack([_xyz(c) for c in task_env.spawned_dynamic_cubes]),
        }
        if with_contacts:
            sample["contacts"] = _contact_snapshot(task_env, bin_names, robot_links)
        trace.append(sample)
        return result

    task_env.step = stepped
    return trace


def contact_summary(
    trace: Sequence[dict], lo: int, hi: int, event_window: tuple[int, int] | None = None
) -> dict:
    """把逐帧接触统计汇总成 clip 级结论（只统计 env step ∈ [lo, hi) 的帧）。

    每类接触给两套数：`*_frames` 是有接触**候选**的帧数（含零冲量），
    `*_forceful_frames` 是冲量真正大于 0 的帧数 —— **判「发生了接触」要用后者**。
    `event_window` 给定时额外统计事件窗口（第一次 swap）内的有力接触。
    """
    frames = [item for item in trace if lo <= item["step"] < hi and "contacts" in item]
    if not frames:
        return {}

    def _agg(prefix: str) -> dict:
        forceful = [
            item for item in frames if item["contacts"][f"{prefix}_impulse"] > FORCEFUL_IMPULSE_EPS
        ]
        return {
            f"{prefix}_frames": sum(1 for i in frames if i["contacts"][f"{prefix}_count"] > 0),
            f"{prefix}_forceful_frames": len(forceful),
            f"{prefix}_impulse_max": round(
                max(i["contacts"][f"{prefix}_impulse"] for i in frames), 6
            ),
            f"{prefix}_onset_env_step": forceful[0]["step"] if forceful else -1,
        }

    out: dict = {}
    for prefix in ("robot_bin", "bin_bin", "robot_button"):
        out.update(_agg(prefix))
    pairs: set[tuple[int, int]] = set()
    forceful_pairs: set[tuple[int, int]] = set()
    for item in frames:
        pairs.update(tuple(pair) for pair in item["contacts"]["bin_bin_pairs"])
        forceful_pairs.update(
            tuple(pair) for pair in item["contacts"].get("bin_bin_forceful_pairs", [])
        )
    out["bin_bin_pairs"] = sorted(pairs)
    out["bin_bin_forceful_pairs"] = sorted(forceful_pairs)

    if event_window is not None:
        a, b = event_window
        inside = [item for item in frames if a <= item["step"] < b]
        for prefix in ("robot_bin", "bin_bin"):
            out[f"{prefix}_event_forceful_frames"] = sum(
                1
                for i in inside
                if i["contacts"][f"{prefix}_impulse"] > FORCEFUL_IMPULSE_EPS
            )
    return out


# ── 布局指纹 ─────────────────────────────────────────────────────────────────


def button_positions(task_env: Any) -> dict[str, list[float]]:
    """ButtonUnmaskSwap 的两个按钮位置（协变量：跨源必变，零 src 改动无法固定）。

    非 Button 环境返回空 dict。按钮在本链路里是**机器人动作的唯一决定因素** ——
    同源变体间逐位一致，跨源不同，所以必须记录下来供下游分层。
    """
    out: dict[str, list[float]] = {}
    for name in ("button_left", "button_right"):
        actor = getattr(task_env, name, None)
        if actor is None:
            continue
        try:
            out[name] = [float(v) for v in _xyz(actor)]
        except Exception:  # noqa: BLE001  articulation 取位姿失败不该拖垮生成
            continue
    return out


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
        "buttons": button_positions(task_env),
        "task_names": [str(entry.get("name")) for entry in task_env.task_list],
    }


# ── 槽位几何：标签里「物体的相对位置」那一半 ─────────────────────────────────


def _wrap_deg(angle: float) -> float:
    """归一化到 [-180, 180)。"""
    return (angle + 180.0) % 360.0 - 180.0


def slot_geometry(fingerprint: Mapping[str, Any]) -> dict:
    """从布局指纹算出槽位 xy、参考轴 α、以及全部槽位对的距离与方位角。

    槽位 = bin 的**初始**位置（bin i 起始于 slot i），所以直接取指纹里的 bins[i].p。

    参考轴 α 取「列方向」的实测均值：模板里 slot0→slot1 与 slot3→slot2 名义上都是
    列内的 +y 方向，两者平均即该 episode 布局的主轴。用实测向量而不是去拟合
    `rotate_points_random` 的角度，是因为：Video 的 angle 是 `_load_scene` 的局部变量、
    没存到 self 取不到；Button 压根没旋转（那行被注释）但两列有各自的随机 y 偏移。
    实测均值对两个 env 都成立，且天然把 ±0.07 的 rejection 抖动一并吸收。
    """
    from clip_plan import bin_pairs, topo_class

    slot_xy = np.asarray([entry["p"][:2] for entry in fingerprint["bins"]], dtype=np.float64)
    num_slots = len(slot_xy)

    column_vectors = [slot_xy[1] - slot_xy[0]]
    if num_slots >= 4:
        column_vectors.append(slot_xy[2] - slot_xy[3])
    axis = np.mean(np.stack(column_vectors), axis=0)
    alpha = math.degrees(math.atan2(float(axis[1]), float(axis[0])))

    pairs = {}
    for pair in bin_pairs(num_slots):
        delta = slot_xy[pair[1]] - slot_xy[pair[0]]
        azimuth = math.degrees(math.atan2(float(delta[1]), float(delta[0])))
        pairs[pair] = {
            "slots": list(pair),
            "distance": float(np.linalg.norm(delta)),
            "azimuth": _wrap_deg(azimuth),
            "azimuth_local": _wrap_deg(azimuth - alpha),
            "topo_class": topo_class(pair),
        }
    return {
        "slot_xy": [[float(x), float(y)] for x, y in slot_xy],
        "reference_axis_deg": _wrap_deg(alpha),
        "pairs": pairs,
    }


# ── trace 反解与体检（按 clip 覆盖范围分段） ─────────────────────────────────


def _by_step(trace: Sequence[dict]) -> dict[int, dict]:
    return {item["step"]: item for item in trace}


def measure_window(
    trace: Sequence[dict], window: tuple[int, int], num_bins: int
) -> dict:
    """完整窗口的净位移与路径长（要求两个端点帧都在 trace 里）。

    moved_bins 按**首末净位移**判定（窗口 (s,e) 的运动步是 s+1..e：插值从 s+1 起产生
    位移，e 步做终点吸附，故取 pos[e] − pos[s]）；path_len 与旁观扰动只作质量指标。
    """
    start, end = window
    frames = _by_step(trace)
    first, last = frames.get(start), frames.get(end)
    if first is None or last is None:
        raise ValueError(f"trace 缺窗口端点帧 {start}/{end}")
    net = np.linalg.norm(last["bins"][:, :2] - first["bins"][:, :2], axis=1)
    path = np.zeros(num_bins, dtype=np.float64)
    for t in range(start + 1, end + 1):
        prev, cur = frames.get(t - 1), frames.get(t)
        if prev is None or cur is None:
            continue
        path += np.linalg.norm(cur["bins"][:, :2] - prev["bins"][:, :2], axis=1)
    return {
        "window": [int(start), int(end)],
        "complete": True,
        "moved_bins": sorted(int(idx) for idx in np.flatnonzero(net > MOVED_NET_EPS)),
        "net_disp": [round(float(v), 4) for v in net],
        "path_len": [round(float(v), 4) for v in path],
    }


def measure_window_partial(
    trace: Sequence[dict], window: tuple[int, int], upto_step: int, num_bins: int
) -> dict:
    """窗口被 clip 截断时的部分位移：端点用 min(window_end, upto_step)。

    窗口 2 在 clip 内只露出前 30 帧（进度 smoothstep(30/50)=0.648），交换对已明显在动，
    但远未走完 —— 所以判据只能是「该动的在动」，阈值用 PARTIAL_MOVED_EPS。
    """
    start, end = window
    stop = min(end, upto_step)
    frames = _by_step(trace)
    first, last = frames.get(start), frames.get(stop)
    if first is None or last is None:
        raise ValueError(f"trace 缺部分窗口端点帧 {start}/{stop}")
    net = np.linalg.norm(last["bins"][:, :2] - first["bins"][:, :2], axis=1)
    return {
        "window": [int(start), int(end)],
        "complete": False,
        "measured_to": int(stop),
        "moved_bins": sorted(int(idx) for idx in np.flatnonzero(net > PARTIAL_MOVED_EPS)),
        "net_disp": [round(float(v), 4) for v in net],
    }


def bystander_metrics(
    events: Sequence[Mapping[str, Any]],
    bin_pairs_seq: Sequence[tuple[int, int]],
    num_bins: int,
) -> dict:
    """旁观 bin（不在当前窗口交换对里）的最大净位移/路径长，及被扰动名单。"""
    net_max = 0.0
    path_max = 0.0
    disturbed: set[int] = set()
    for event, pair in zip(events, bin_pairs_seq):
        for idx in range(num_bins):
            if idx in pair:
                continue
            net_max = max(net_max, event["net_disp"][idx])
            if "path_len" in event:
                path_max = max(path_max, event["path_len"][idx])
            if event["net_disp"][idx] > DISTURBED_NET_EPS:
                disturbed.add(idx)
    return {
        "bystander_net_max": round(net_max, 4),
        "bystander_path_max": round(path_max, 4),
        "disturbed_bins": sorted(disturbed),
    }


def min_clearance(
    trace: Sequence[dict],
    windows: Sequence[tuple[int, int]],
    bin_pairs_seq: Sequence[tuple[int, int]],
    num_bins: int,
    upto_step: int | None = None,
) -> float:
    """swap 期间，交换中的 bin 与被锁定的其他 bin 的最小 xy 中心距（米）。

    对角远距交换可能擦过第三个 bin —— 不修环境，量化后写进标签供下游过滤。
    `upto_step` 限制只统计 clip 覆盖到的帧。
    """
    lowest = float("inf")
    frames = _by_step(trace)
    for (start, end), (i, j) in zip(windows, bin_pairs_seq):
        others = [b for b in range(num_bins) if b not in (i, j)]
        if not others:
            continue
        stop = end if upto_step is None else min(end, upto_step)
        for t in range(start, stop + 1):
            sample = frames.get(t)
            if sample is None:
                continue
            for mover in (i, j):
                for other in others:
                    distance = float(
                        np.linalg.norm(sample["bins"][mover, :2] - sample["bins"][other, :2])
                    )
                    lowest = min(lowest, distance)
    return lowest if lowest != float("inf") else float("nan")
