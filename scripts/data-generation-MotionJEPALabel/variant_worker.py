#!/usr/bin/env python3
"""probe_original 与 generate_swap_variants 共用的 rollout worker。

单次 attempt 的完整流程：
gym.make（kwargs 与 newSeed 骨架逐字相同，seed 用 env_seed）
→ RobommeRecordWrapper（episode/seed 用 staging 编号与 variant_seed，控制跑用原号）
→ reset → 布局指纹 → 挂位姿探针 → [变体跑：注入 + 读回第一道闸]
→ ScrewThenRRT planner solve（成功判定与骨架逐字相同）
→ rollout 后读回 swap_schedule（第二道闸/控制跑的原始序列来源）
→ close → trace 反解实测事件对账 → h5 追加写 swap_gt 逐帧标注 → trace 落 npz

与 newSeed 骨架的三处刻意偏离（方案定稿）：
1. FailRecover 恒不启用 —— 源 ep90-93 全部 ≥6，原始行为就是不启用；
2. 失败重试**不换 seed**（换 seed 会换布局，摧毁「其他配置不变」前提）；
3. difficulty 一律来自 train metadata，不用 difficulty_for() 循环。

每个 job 一次 gym.make，禁止跨变体复用 env ——
statechange.py 的两处缓存按 id(actor) 做键且 reset 不清理，复用有静默污染风险。
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import h5py
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from swap_inject import (  # noqa: E402
    attach_pose_probe,
    bystander_metrics,
    inject_pairs,
    layout_fingerprint,
    measured_events,
    min_clearance,
    readback_pairs,
)
from variant_plan import (  # noqa: E402
    net_permutation,
    swap_windows,
    variant_signature,
)


class VariantGenerationError(RuntimeError):
    """生成过程违反约定（对账不过、结构不符等），属可重试的任务性失败。"""


class PlannerExhausted(RuntimeError):
    """planner 的 screw 与 RRTStar 重试均已耗尽。"""


@dataclass(frozen=True)
class VariantJob:
    """一次 attempt。pairs=None 表示控制跑（无注入，读回原始序列）。"""

    task: str
    src_episode: int
    variant_idx: int  # 控制跑用 -1
    env_seed: int
    variant_seed: int  # 控制跑等于 env_seed
    wrapper_episode: int  # 控制跑等于 src_episode，变体跑是 staging_episode
    difficulty: str
    num_bins: int
    pairs: tuple[tuple[int, int], ...] | None
    original_pairs: tuple[tuple[int, int], ...] | None  # phase0 得到的原始序列（判 is_original）
    attempt: int
    output_root: str
    repo_root: str

    def bump(self) -> "VariantJob":
        """同 seed 重试：只加 attempt。绝不换 seed —— 换 seed 即换布局。"""
        from dataclasses import replace

        return replace(self, attempt=self.attempt + 1)


# 池进程私有：由 initializer 填，worker 回传供审计
_BOUND: dict[str, Any] = {}


def pool_init(gpu: str, src_root: str, limit_threads_env: str = "MJLABEL_LIMIT_THREADS") -> None:
    """池进程一生只跑一次：绑卡、压线程、预热 import（照抄 newSeed，绑卡必须早于 CUDA 初始化）。"""
    global _BOUND
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu
    limit = os.environ.get(limit_threads_env, "1") != "0"

    info: dict[str, Any] = {"gpu": gpu, "pid": os.getpid()}
    try:
        import cv2
        import torch

        if limit:
            torch.set_num_threads(1)
            try:
                torch.set_num_interop_threads(1)
            except RuntimeError:
                pass
            cv2.setNumThreads(0)

        import gymnasium  # noqa: F401
        import sapien

        import robomme.robomme_env  # noqa: F401
        from robomme.env_record_wrapper import RobommeRecordWrapper  # noqa: F401

        device = sapien.Device("cuda")
        info.update(
            {
                "cuda_id": getattr(device, "cuda_id", None),
                "pci": getattr(device, "pci_string", None),
                "torch_threads": torch.get_num_threads(),
            }
        )
    except Exception as exc:  # noqa: BLE001  initializer 抛异常会让整个池 broken
        info["error"] = repr(exc)
    _BOUND = info


def _planner_classes(arm_base: type, screw_error: type[BaseException]) -> type:
    """screw 三次 → RRTStar 三次的回退，与 newSeed 骨架逐字一致（两个 swap 环境都走 arm planner）。"""

    class ScrewThenRRT:
        def move_to_pose_with_screw(self, *args: Any, **kwargs: Any) -> Any:
            last_error: BaseException | None = None
            for _ in range(3):
                try:
                    result = super().move_to_pose_with_screw(*args, **kwargs)
                except screw_error as exc:
                    last_error = exc
                    continue
                if not _is_failure(result):
                    return result
            for _ in range(3):
                try:
                    result = super().move_to_pose_with_RRTStar(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    continue
                if not _is_failure(result):
                    return result
            suffix = f": {last_error}" if last_error is not None else ""
            raise PlannerExhausted("screw 三次与 RRTStar 三次均失败" + suffix)

    class NoPatchArm(ScrewThenRRT, arm_base):
        pass

    return NoPatchArm


def _is_failure(value: Any) -> bool:
    return isinstance(value, (int, np.integer)) and int(value) == -1


def _runtime_bool(value: Any, torch_module: Any) -> bool:
    if isinstance(value, torch_module.Tensor):
        return bool(value.detach().cpu().reshape(-1)[0].item())
    if isinstance(value, np.ndarray):
        return bool(value.reshape(-1)[0])
    return bool(value)


def _execute_tasks(
    record_env: Any,
    planner: Any,
    torch_module: Any,
    label: str,
    pickup_hold_step: int | None = None,
    hold_solver: Any | None = None,
) -> None:
    """成功判定与骨架逐字相同：跑完 task_list 且 evaluate 报 success 真、fail 假。

    pickup_hold_step：仅 ButtonUnmaskSwap 重试 attempt 使用 —— 在**首个抓取子目标
    之前的那个 entry（最后一个按钮）solve 完成后、post-solve evaluate 之前** hold 到
    该绝对步（= swap 全部结束 + 沉降余量）。背景（FAILED 视频 + 全量实测）：抓取
    子目标实测 step≈200 就开始而第三个 swap 窗口到 214 才结束，重叠期有两种确定性
    失败：(a) 多数情形 —— 抓取按移动中的目标 bin 位置规划而抓错（hold 挂在抓取
    entry 前即可治，85 条中 83 条）；(b) 少数情形 —— 按钮 2 完成的那次 evaluate 把
    子目标推进到抓取并即刻激活其 failure_func（其他 bin 高于 0.15 即败），恰逢对角
    teleport 把途经的旁观 bin 瞬时挤高过阈值，episode 在 step≈200 就被判失败、
    根本走不到抓取 entry（var61/var191）。hold 放在 post-solve evaluate 之前
    同时覆盖两种情形。attempt 0 一律不 hold，保证天然可成功的变体（含 is_original）
    轨迹与官方逐位可比。
    """
    task_list = list(getattr(record_env.unwrapped, "task_list", []) or [])
    if not task_list:
        raise VariantGenerationError(f"{label}: task_list 为空")
    first_pickup_idx = next(
        (
            index
            for index, entry in enumerate(task_list)
            if str(entry.get("name", "")).startswith("pick up the container")
        ),
        None,
    )
    for index, entry in enumerate(task_list):
        solve = entry.get("solve") if isinstance(entry, Mapping) else None
        if not callable(solve):
            raise VariantGenerationError(f"{label}: task 没有 solve 方法")
        record_env.unwrapped.evaluate(solve_complete_eval=True)
        result = solve(record_env, planner)
        if _is_failure(result):
            raise PlannerExhausted(f"{label}: solve 返回 -1")
        if (
            pickup_hold_step is not None
            and first_pickup_idx is not None
            and index == first_pickup_idx - 1
            and int(record_env.unwrapped.elapsed_steps) < pickup_hold_step
        ):
            hold_solver(record_env, planner, pickup_hold_step)
        evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
        if _runtime_bool(evaluation.get("fail", False), torch_module):
            raise VariantGenerationError(f"{label}: 环境报告失败")
        if _runtime_bool(evaluation.get("success", False), torch_module):
            return
    evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
    if not _runtime_bool(evaluation.get("success", False), torch_module):
        raise VariantGenerationError(f"{label}: 跑完整个 task_list 仍未成功")


def h5_path(output_root: Path, job: VariantJob) -> Path:
    """与 RecordWrapper 的命名约定一致：{task}_ep{episode}_seed{seed}.h5。"""
    return output_root / "hdf5_files" / f"{job.task}_ep{job.wrapper_episode}_seed{job.variant_seed}.h5"


def trace_path(output_root: Path, job: VariantJob) -> Path:
    return output_root / "traces" / f"{job.task}_ep{job.wrapper_episode}.npz"


def _smoothstep(alpha: float) -> float:
    alpha = min(max(alpha, 0.0), 1.0)
    return alpha * alpha * (3.0 - 2.0 * alpha)


def _sorted_timesteps(group: h5py.Group) -> list[str]:
    names = [name for name in group if name.startswith("timestep_")]
    return sorted(names, key=lambda name: int(name.rsplit("_", 1)[1]))


def _segment_lengths(episode_group: h5py.Group) -> tuple[int, int, int]:
    """(T, demo_prefix, exec_len)。口径与 MotionJEPA build_data_raw 同源：
    demo = is_video_demo 前缀长；exec = 段内首个 is_completed 真 + 2（截到段尾）。"""
    timesteps = _sorted_timesteps(episode_group)
    total = len(timesteps)
    demo_prefix = 0
    for name in timesteps:
        if bool(np.asarray(episode_group[name]["info"]["is_video_demo"])):
            demo_prefix += 1
        else:
            break
    exec_names = timesteps[demo_prefix:]
    first_completed = None
    for index, name in enumerate(exec_names):
        if bool(np.asarray(episode_group[name]["info"]["is_completed"])):
            first_completed = index
            break
    if first_completed is None:
        exec_len = len(exec_names)
    else:
        exec_len = min(first_completed + 2, len(exec_names))
    return total, demo_prefix, exec_len


def _write_swap_gt(
    path: Path,
    job: VariantJob,
    pairs: Sequence[tuple[int, int]],
    trace: Sequence[dict],
    fingerprint: Mapping[str, Any],
    is_original: int,
    clearance: float,
    bystanders: Mapping[str, Any],
) -> dict[str, Any]:
    """episode 落盘后以追加模式重开 h5，写 timestep 级与 setup 级 swap_gt 标注。

    返回段长信息。trace[t] 与 timestep_t 一一对应，数量不符即 fail-loud。
    """
    windows = swap_windows(len(pairs))
    num_bins = job.num_bins
    str_dtype = h5py.string_dtype(encoding="utf-8")
    bin_colors = [
        fingerprint["bin_to_color"].get(str(idx), "empty") for idx in range(num_bins)
    ]
    by_step = {item["step"]: item for item in trace}

    with h5py.File(path, "a") as handle:
        episode = handle[f"episode_{job.wrapper_episode}"]
        timesteps = _sorted_timesteps(episode)
        if len(timesteps) != len(trace):
            raise VariantGenerationError(
                f"{path.name}: h5 有 {len(timesteps)} 个 timestep，探针 trace 有 {len(trace)} 帧，"
                "帧对齐被破坏"
            )

        for name in timesteps:
            t = int(name.rsplit("_", 1)[1])
            sample = by_step[t]
            active_idx = -1
            progress = 0.0
            for w_idx, (start, end) in enumerate(windows):
                if start <= t < end:
                    active_idx = w_idx
                    progress = _smoothstep((t - start) / (end - start))
                    break
            if active_idx >= 0:
                pair = pairs[active_idx]
                pair_pos = np.stack([sample["bins"][pair[0]], sample["bins"][pair[1]]])
            else:
                pair = (-1, -1)
                pair_pos = np.full((2, 3), np.nan)

            group = episode[name].create_group("swap_gt")
            group.create_dataset("swap_active", data=bool(active_idx >= 0))
            group.create_dataset("swap_window_idx", data=np.int8(active_idx))
            group.create_dataset("swap_pair", data=np.asarray(pair, dtype=np.int8))
            group.create_dataset("swap_pair_pos", data=pair_pos.astype(np.float32))
            group.create_dataset("swap_progress", data=np.float32(progress))
            group.create_dataset("bins_pos", data=sample["bins"].astype(np.float32))
            group.create_dataset("cubes_pos", data=sample["cubes"].astype(np.float32))

        setup = episode["setup"] if "setup" in episode else episode.create_group("setup")
        gt = setup.create_group("swap_gt")
        gt.create_dataset("env_seed", data=np.int64(job.env_seed))
        gt.create_dataset("variant_seed", data=np.int64(job.variant_seed))
        gt.create_dataset("src_episode", data=np.int64(job.src_episode))
        gt.create_dataset("variant_idx", data=np.int64(job.variant_idx))
        gt.create_dataset("is_original", data=np.int8(is_original))
        gt.create_dataset("difficulty", data=job.difficulty, dtype=str_dtype)
        gt.create_dataset("signature", data=variant_signature(pairs), dtype=str_dtype)
        gt.create_dataset("pairs", data=np.asarray(pairs, dtype=np.int8))
        gt.create_dataset("windows", data=np.asarray(windows, dtype=np.int32))
        gt.create_dataset("candidates", data=np.arange(num_bins, dtype=np.int8))
        gt.create_dataset("bin_colors", data=bin_colors, dtype=str_dtype)
        gt.create_dataset(
            "net_permutation", data=np.asarray(net_permutation(pairs, num_bins), dtype=np.int8)
        )
        gt.create_dataset(
            "task_goal_color", data=fingerprint["color_names"][0], dtype=str_dtype
        )
        gt.create_dataset("min_clearance", data=np.float32(clearance))
        gt.create_dataset("bystander_net_max", data=np.float32(bystanders["bystander_net_max"]))
        gt.create_dataset("bystander_path_max", data=np.float32(bystanders["bystander_path_max"]))
        gt.create_dataset(
            "disturbed_bins", data=np.asarray(bystanders["disturbed_bins"], dtype=np.int8)
        )
        order = sorted(by_step)
        gt.create_dataset(
            "bins_pos_traj",
            data=np.stack([by_step[t]["bins"] for t in order]).astype(np.float32),
        )
        gt.create_dataset(
            "cubes_pos_traj",
            data=np.stack([by_step[t]["cubes"] for t in order]).astype(np.float32),
        )

        total, demo_prefix, exec_len = _segment_lengths(episode)
    return {"n_timesteps": total, "demo_prefix": demo_prefix, "exec_len": exec_len}


def _discard_empty_h5(path: Path, wrapper_episode: int) -> None:
    """删掉失败 attempt 留下的空 h5；确有内容则保留交人工判断（照抄 newSeed）。"""
    if not path.is_file():
        return
    try:
        with h5py.File(path, "r") as handle:
            if f"episode_{wrapper_episode}" in handle:
                return
    except Exception:  # noqa: BLE001
        pass
    try:
        path.unlink()
    except OSError:
        pass


def run_episode(job: VariantJob) -> dict[str, Any]:
    """跑一次 attempt。重试由父进程负责（同 seed 重新入队）。"""
    started = time.time()
    clock = time.monotonic()
    phases: dict[str, float] = {}
    output_root = Path(job.output_root)
    raw_path = h5_path(output_root, job)
    record_env: Any | None = None
    caught: BaseException | None = None
    error_traceback: str | None = None
    fingerprint: dict[str, Any] | None = None
    readback_after_inject: list | None = None
    readback_final: list | None = None
    trace: list[dict] = []

    try:
        source_root = Path(job.repo_root) / "src"
        if str(source_root) not in sys.path:
            sys.path.insert(0, str(source_root))
        import gymnasium as gym
        import torch
        import robomme.robomme_env  # noqa: F401
        from robomme.env_record_wrapper import FailsafeTimeout, RobommeRecordWrapper
        from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError
        from robomme.robomme_env.utils.planner_fail_safe import (
            FailAwarePandaArmMotionPlanningSolver,
            ScrewPlanFailure,
        )
        from robomme.robomme_env.utils.subgoal_planner_func import (
            solve_hold_obj_absTimestep,
        )

        arm_cls = _planner_classes(FailAwarePandaArmMotionPlanningSolver, ScrewPlanFailure)
    except Exception as exc:  # noqa: BLE001
        return {
            **_job_fields(job),
            "bound": dict(_BOUND),
            "ok": False,
            "failure_class": "code",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "finished_at": time.time(),
        }

    retryable = (
        SceneGenerationError,
        FailsafeTimeout,
        PlannerExhausted,
        ScrewPlanFailure,
        VariantGenerationError,
    )
    label = f"{job.task}/ep{job.src_episode}/var{job.variant_idx}"

    try:
        # env kwargs 与 newSeed 骨架逐字相同；seed 必须是 env_seed（布局之源）。
        # FailRecover 恒不启用（偏离点 1）。
        kwargs: dict[str, Any] = {
            "obs_mode": "rgb+depth+segmentation",
            "control_mode": "pd_joint_pos",
            "render_mode": "rgb_array",
            "reward_mode": "dense",
            "seed": job.env_seed,
            "difficulty": job.difficulty,
        }
        mark = time.monotonic()
        base_env = gym.make(job.task, **kwargs)
        record_env = RobommeRecordWrapper(
            base_env,
            dataset=str(output_root),
            env_id=job.task,
            episode=job.wrapper_episode,
            seed=job.variant_seed,
            save_video=True,
        )
        phases["make_s"] = time.monotonic() - mark

        mark = time.monotonic()
        record_env.reset()
        phases["reset_s"] = time.monotonic() - mark

        unwrapped = record_env.unwrapped
        fingerprint = layout_fingerprint(unwrapped)
        if len(unwrapped.spawned_bins) != job.num_bins:
            raise VariantGenerationError(
                f"{label}: 实际 bin 数 {len(unwrapped.spawned_bins)} ≠ 配置 {job.num_bins}"
            )
        trace = attach_pose_probe(unwrapped)

        if job.pairs is not None:
            inject_pairs(unwrapped, job.pairs)
            readback_after_inject = readback_pairs(unwrapped)
            planned = [tuple(sorted(pair)) for pair in job.pairs]
            if readback_after_inject != planned:
                raise VariantGenerationError(
                    f"{label}: 注入读回 {readback_after_inject} ≠ 计划 {planned}"
                )

        planner = arm_cls(
            record_env,
            debug=False,
            vis=False,
            base_pose=record_env.unwrapped.agent.robot.pose,
            visualize_target_grasp_pose=False,
            print_env_info=False,
        )

        # 重试 attempt 才启用抓取前 hold（详见 _execute_tasks docstring）；
        # +10 步沉降余量：被挤高的旁观 bin 需要几步自由落体回到阈值以下
        pickup_hold_step = None
        if job.task == "ButtonUnmaskSwap" and job.attempt >= 1 and job.pairs is not None:
            pickup_hold_step = int(unwrapped.swap_schedule[-1][3]) + 10

        mark = time.monotonic()
        _execute_tasks(
            record_env, planner, torch, label,
            pickup_hold_step=pickup_hold_step,
            hold_solver=solve_hold_obj_absTimestep,
        )
        phases["solve_s"] = time.monotonic() - mark

        # rollout 后、close 前读回：控制跑此刻 idx2 已被最近邻回填；
        # 变体跑必须仍等于计划（防最近邻逻辑意外覆写）。
        readback_final = readback_pairs(unwrapped)
        if job.pairs is not None:
            planned = [tuple(sorted(pair)) for pair in job.pairs]
            if readback_final != planned:
                raise VariantGenerationError(
                    f"{label}: rollout 后读回 {readback_final} ≠ 计划 {planned}，注入被覆写"
                )
        elif any(None in pair for pair in readback_final):
            raise VariantGenerationError(
                f"{label}: 控制跑结束后 swap_schedule 仍有 None：{readback_final}"
            )
    except Exception as exc:  # noqa: BLE001
        caught = exc
        error_traceback = traceback.format_exc()
    finally:
        if record_env is not None:
            mark = time.monotonic()
            try:
                record_env.close()  # h5 落盘与 mp4 编码都发生在 close 里
            except Exception as close_exc:  # noqa: BLE001
                if caught is None:
                    caught = close_exc
                    error_traceback = traceback.format_exc()
            phases["close_s"] = time.monotonic() - mark

    base = {
        **_job_fields(job),
        "bound": dict(_BOUND),
        "phases": {name: round(value, 3) for name, value in phases.items()},
        "wall_s": round(time.monotonic() - clock, 3),
        "started_at": started,
        "finished_at": time.time(),
    }

    if caught is not None:
        _discard_empty_h5(raw_path, job.wrapper_episode)
        return {
            **base,
            "ok": False,
            "failure_class": "task" if isinstance(caught, retryable) else "code",
            "error_type": type(caught).__name__,
            "error": str(caught),
            "traceback": error_traceback,
        }

    # ── 成功路径的后处理：对账 + swap_gt 写入。任何一步失败都按任务性失败重试 ──
    try:
        effective_pairs = (
            [tuple(sorted(pair)) for pair in job.pairs]
            if job.pairs is not None
            else [tuple(pair) for pair in readback_final]
        )
        windows = swap_windows(len(effective_pairs))
        events = measured_events(trace, windows, job.num_bins)
        for event, pair in zip(events, effective_pairs):
            # 计划的交换对必须按净位移真的换了位置；旁观 bin 被擦碰属质量问题，
            # 记 bystander 指标供下游过滤，不作废变体（对角交换的确定性现象）。
            missing = [b for b in sorted(pair) if b not in event["moved_bins"]]
            if missing:
                raise VariantGenerationError(
                    f"{label}: 窗口 {event['window']} 计划交换 {sorted(pair)}，"
                    f"但 bin {missing} 净位移不足（net_disp={event['net_disp']}）"
                )
        bystanders = bystander_metrics(events, effective_pairs, job.num_bins)
        clearance = min_clearance(trace, windows, effective_pairs, job.num_bins)

        if job.original_pairs is not None:
            is_original = int(
                effective_pairs == [tuple(sorted(pair)) for pair in job.original_pairs]
            )
        elif job.pairs is None:
            is_original = 1  # 控制跑本身就是原始序列
        else:
            is_original = -1  # 未提供 phase0 基线，未知

        segment = _write_swap_gt(
            raw_path, job, effective_pairs, trace, fingerprint, is_original, clearance,
            bystanders,
        )

        # 段覆盖硬断言：swap 必须完整落在 scope 段内
        swap_end = windows[-1][1]
        if job.task == "VideoUnmaskSwap" and segment["demo_prefix"] < swap_end:
            raise VariantGenerationError(
                f"{label}: demo 段 {segment['demo_prefix']} 帧 < swap 结束 {swap_end}"
            )
        if job.task == "ButtonUnmaskSwap" and segment["demo_prefix"] + segment["exec_len"] < swap_end:
            raise VariantGenerationError(
                f"{label}: exec 段截断后 {segment['exec_len']} 帧 < swap 结束 {swap_end}"
            )

        # trace 落 npz（bins_pos 等已内嵌 h5，npz 供不开 h5 的快速审计）
        tpath = trace_path(output_root, job)
        tpath.parent.mkdir(parents=True, exist_ok=True)
        order = sorted(item["step"] for item in trace)
        by_step = {item["step"]: item for item in trace}
        np.savez_compressed(
            tpath,
            steps=np.asarray(order, dtype=np.int32),
            bins_pos=np.stack([by_step[t]["bins"] for t in order]).astype(np.float32),
            cubes_pos=np.stack([by_step[t]["cubes"] for t in order]).astype(np.float32),
        )

        return {
            **base,
            "ok": True,
            "h5_path": str(raw_path),
            "trace_path": str(tpath),
            "pairs": [list(pair) for pair in effective_pairs],
            "signature": variant_signature(effective_pairs),
            "net_permutation": list(net_permutation(effective_pairs, job.num_bins)),
            "is_original": is_original,
            "readback_after_inject": readback_after_inject,
            "measured_events": events,
            "min_clearance": round(clearance, 4),
            "pickup_hold_step": pickup_hold_step,
            **bystanders,
            "fingerprint": fingerprint,
            **segment,
        }
    except Exception as exc:  # noqa: BLE001
        _discard_empty_h5(raw_path, job.wrapper_episode)
        return {
            **base,
            "ok": False,
            "failure_class": "task" if isinstance(exc, retryable) else "code",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def _job_fields(job: VariantJob) -> dict[str, Any]:
    return {
        "task": job.task,
        "src_episode": job.src_episode,
        "variant_idx": job.variant_idx,
        "wrapper_episode": job.wrapper_episode,
        "env_seed": job.env_seed,
        "variant_seed": job.variant_seed,
        "difficulty": job.difficulty,
        "attempt": job.attempt,
        "planned_pairs": [list(pair) for pair in job.pairs] if job.pairs is not None else None,
    }


def write_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    with path.open("a", buffering=1, encoding="utf-8") as sink:
        sink.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── 调度器（probe_original 与 generate_swap_variants 共用） ────────────────────
#
# 结构照抄 newSeed 的 _run_jobs：每卡一池、进程终身绑卡、BrokenProcessPool 重建、
# JSONL 边跑边写。唯一实质差异：重试走 job.bump()（同 seed、只加 attempt），
# 绝不换 seed。

MAX_NON_TASK_STRIKES = 3


def _synth_failure(job: VariantJob, exc: BaseException, failure_class: str) -> dict[str, Any]:
    return {
        **_job_fields(job),
        "ok": False,
        "failure_class": failure_class,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "finished_at": time.time(),
    }


def run_jobs(
    jobs: Sequence[VariantJob],
    gpu_ids: Sequence[str],
    workers: int,
    jsonl_path: Path,
    max_attempts: int = 3,
    max_tasks_per_child: int | None = 8,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import multiprocessing as mp
    from collections import deque
    from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
    from concurrent.futures.process import BrokenProcessPool

    context = mp.get_context("spawn")
    per_gpu = max(1, workers // len(gpu_ids))
    src_root = str(Path(jobs[0].repo_root) / "src")

    def new_pool(gpu: str) -> ProcessPoolExecutor:
        return ProcessPoolExecutor(
            max_workers=per_gpu,
            mp_context=context,
            initializer=pool_init,
            initargs=(gpu, src_root),
            max_tasks_per_child=max_tasks_per_child,
        )

    pools = {gpu: new_pool(gpu) for gpu in gpu_ids}
    capacity = {gpu: per_gpu for gpu in gpu_ids}
    pending: deque[VariantJob] = deque(jobs)
    inflight: dict[Future, tuple[str, VariantJob]] = {}
    succeeded: list[dict[str, Any]] = []
    exhausted: list[dict[str, Any]] = []
    total = len(jobs)
    strikes: dict[tuple[str, int, int], int] = {}

    with jsonl_path.open("a", buffering=1, encoding="utf-8") as sink:

        def record(result: Mapping[str, Any]) -> None:
            sink.write(json.dumps(result, ensure_ascii=False) + "\n")

        while pending or inflight:
            while pending and any(capacity[gpu] > 0 for gpu in gpu_ids):
                gpu = max(gpu_ids, key=lambda item: capacity[item])
                if capacity[gpu] <= 0:
                    break
                job = pending.popleft()
                inflight[pools[gpu].submit(run_episode, job)] = (gpu, job)
                capacity[gpu] -= 1

            if not inflight:
                break
            finished, _ = wait(list(inflight), return_when=FIRST_COMPLETED)

            broken: set[str] = set()
            for future in finished:
                gpu, job = inflight.pop(future)
                capacity[gpu] += 1
                try:
                    result = future.result()
                except BrokenProcessPool as exc:
                    broken.add(gpu)
                    result = _synth_failure(job, exc, "infra")
                except BaseException as exc:  # noqa: BLE001
                    result = _synth_failure(job, exc, "infra")
                record(result)
                key = (job.task, job.src_episode, job.variant_idx)
                if result.get("ok"):
                    strikes.pop(key, None)
                    succeeded.append(result)
                    print(
                        f"[{len(succeeded)}/{total}] {job.task}/ep{job.src_episode}"
                        f"/var{job.variant_idx} 成功（attempt {job.attempt}，"
                        f"{result.get('wall_s')}s）",
                        flush=True,
                    )
                    continue

                if result.get("failure_class") == "task":
                    strikes.pop(key, None)
                else:
                    strikes[key] = strikes.get(key, 0) + 1

                if strikes.get(key, 0) >= MAX_NON_TASK_STRIKES:
                    exhausted.append(result)
                    print(
                        f"    {job.task}/ep{job.src_episode}/var{job.variant_idx} "
                        f"连续 {MAX_NON_TASK_STRIKES} 次非任务性失败"
                        f"（{result.get('error_type')}），放弃",
                        flush=True,
                    )
                elif job.attempt + 1 < max_attempts:
                    print(
                        f"    {job.task}/ep{job.src_episode}/var{job.variant_idx} 失败"
                        f"（{result.get('error_type')}），同 seed 重试 attempt {job.attempt + 1}",
                        flush=True,
                    )
                    pending.append(job.bump())
                else:
                    exhausted.append(result)
                    print(
                        f"    {job.task}/ep{job.src_episode}/var{job.variant_idx} "
                        f"用尽 {max_attempts} 次 attempt，放弃",
                        flush=True,
                    )

            for gpu in broken:
                print(f"    GPU {gpu} 的进程池已损坏，正在重建", flush=True)
                for future, (owner, job) in list(inflight.items()):
                    if owner != gpu:
                        continue
                    inflight.pop(future)
                    capacity[gpu] += 1
                    record(_synth_failure(job, RuntimeError("池重建，任务退回队列"), "infra"))
                    if job.attempt + 1 < max_attempts:
                        pending.appendleft(job.bump())
                    else:
                        exhausted.append(
                            _synth_failure(job, RuntimeError("池重建且已用尽 attempt"), "infra")
                        )
                try:
                    pools[gpu].shutdown(wait=False, cancel_futures=True)
                except Exception:  # noqa: BLE001
                    pass
                pools[gpu] = new_pool(gpu)
                capacity[gpu] = per_gpu

    for pool in pools.values():
        try:
            pool.shutdown(wait=True)
        except Exception:  # noqa: BLE001
            pass
    return succeeded, exhausted
