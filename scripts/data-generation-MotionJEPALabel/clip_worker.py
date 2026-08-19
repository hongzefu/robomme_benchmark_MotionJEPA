#!/usr/bin/env python3
"""probe_original 与 generate_swap_clips 共用的 rollout worker（两种模式）。

**control 模式**（Phase 0，每源一条）：不注入、跑**完整** task_list、要求任务成功、不裁剪。
唯一目的是拿到「原始 bin 对序列」—— 窗口 2/3 的 `idx2` 是运行时进窗口那一刻按最近邻
回填的，静态算不出，只能实跑读回；顺带产出布局基线、槽位几何、按钮位置、子目标边界，
以及与官方 h5 的逐元素 joint_action 比对。

**clip 模式**（正式产物，每源 2~3 条）：注入 + **截断** rollout + 裁剪成 110 帧 clip。

    Video  只 solve task_list[0]（static 子目标，hold 到最后一次 swap 结束 ≥164）
    Button 只 solve task_list[0..1]（两个按钮，跑到 ≥198）

clip 只到 env step 143，抓取段完全用不上。截断带来三个好处：绕开抓取/swap 时序冲突
（旧链路为此加过 hold 补救）、绕开 min_clearance 擦碰触发的 `is_any_bin_pickup` 失败
（press/static 两段的 `failure_func` 都是 None ⇒ 理论零任务性失败）、以及约 2 倍加速。

代价是 `RecordWrapper.close()` 里 `if self.episode_success:` 才落盘，而 `episode_success`
只在 `terminated` 时置真 —— 所以截断跑必须在 close 前**显式**置位。这是有意为之的
「录制部分轨迹」，不是绕过失败判定：截断点之前的每一帧都真实跑过且没有任何失败条件。

与 newSeed 骨架（scripts/data-generation-newSeed/generate_dataset_newseed.py）的偏离：

1. FailRecover 恒不启用 —— 骨架按 episode 号分档，本链路的 staging 编号会让分档乱套。
   train 源 ep91-99 全部 ≥6、原始行为本就不启用；test/val 的低号源（如 ep3 ≤5）在
   原版生成器里**可能**启用过分档恢复，但两 split 没有官方 h5 可逐位比对，本链路统一
   不启用是唯一自洽口径（Phase 0 的原始序列即本链路自己的控制跑真值）；
2. 失败重试**不换 seed** —— 换 seed 即换布局，摧毁「其他配置不变」的前提；
3. difficulty 一律来自所属 split 的 metadata，不用 difficulty_for() 循环。

每个 job 一次 gym.make，**禁止跨变体复用 env** —— statechange.py 的 `_two_lane_swaps` 与
`_lift_drop_onto_cache` 按 id(actor) 做键且 reset 不清理，复用有静默污染风险。
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

from clip_plan import (  # noqa: E402
    CLIP_END,
    CLIP_LEN,
    CLIP_START,
    clip_visible_windows,
    net_permutation,
    signature_of,
    slot_pairs_from_bin_pairs,
    swap_windows_env,
    topo_class,
)
from swap_inject import (  # noqa: E402
    MOVED_NET_EPS,
    PARTIAL_MOVED_EPS,
    attach_pose_probe,
    bystander_metrics,
    contact_summary,
    inject_pairs,
    layout_fingerprint,
    measure_window,
    measure_window_partial,
    min_clearance,
    readback_idx1,
    readback_pairs,
    slot_geometry,
)

# 截断模式下每个 env 要 solve 的子目标个数（够覆盖 env step 143 即可）
TRUNCATED_SUBGOALS = {"VideoUnmaskSwap": 1, "ButtonUnmaskSwap": 2}
# clip 内每一帧的 is_video_demo 强制值：Video 全 demo、Button 全 exec
CLIP_IS_DEMO = {"VideoUnmaskSwap": True, "ButtonUnmaskSwap": False}


class ClipGenerationError(RuntimeError):
    """生成过程违反约定（对账不过、帧数不够、结构不符等），属可重试的任务性失败。"""


class PlannerExhausted(RuntimeError):
    """planner 的 screw 与 RRTStar 重试均已耗尽。"""


@dataclass(frozen=True)
class ClipJob:
    """一次 attempt。mode='control' 表示 Phase 0 控制跑（无注入、完整 rollout、不裁剪）。"""

    task: str
    split: str  # 源所属 split（train/test/val）—— episode 号只在 split 内可比
    src_episode: int
    variant_idx: int  # 控制跑用 -1
    env_seed: int
    variant_seed: int  # 控制跑等于 env_seed
    wrapper_episode: int  # 控制跑等于 src_episode，clip 跑是 staging_episode
    difficulty: str
    num_bins: int
    mode: str  # "control" | "clip"
    bin_pairs: tuple[tuple[int, int], ...] | None  # 注入用；control 模式为 None
    slot_pairs: tuple[tuple[int, int], ...] | None  # 标签用；control 模式为 None
    is_original: bool
    attempt: int
    output_root: str
    repo_root: str

    def bump(self) -> "ClipJob":
        """同 seed 重试：只加 attempt。绝不换 seed —— 换 seed 即换布局。"""
        from dataclasses import replace

        return replace(self, attempt=self.attempt + 1)

    @property
    def label(self) -> str:
        suffix = "control" if self.mode == "control" else f"var{self.variant_idx}"
        return f"{self.task}/{self.split}/ep{self.src_episode}/{suffix}"


# 池进程私有：由 initializer 填，worker 回传供审计
_BOUND: dict[str, Any] = {}


def pool_init(gpu: str, src_root: str, limit_threads_env: str = "MJLABEL_LIMIT_THREADS") -> None:
    """池进程一生只跑一次：绑卡、压线程、预热 import（绑卡必须早于 CUDA 初始化）。"""
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
    """screw 三次 → RRTStar 三次的回退，与 newSeed 骨架逐字一致。"""

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


def _task_list(record_env: Any, label: str) -> list:
    task_list = list(getattr(record_env.unwrapped, "task_list", []) or [])
    if not task_list:
        raise ClipGenerationError(f"{label}: task_list 为空")
    return task_list


def _solve_one(record_env: Any, planner: Any, entry: Mapping[str, Any], label: str) -> None:
    solve = entry.get("solve") if isinstance(entry, Mapping) else None
    if not callable(solve):
        raise ClipGenerationError(f"{label}: task 没有 solve 方法")
    record_env.unwrapped.evaluate(solve_complete_eval=True)
    if _is_failure(solve(record_env, planner)):
        raise PlannerExhausted(f"{label}: solve 返回 -1")


def execute_full(record_env: Any, planner: Any, torch_module: Any, label: str) -> None:
    """control 模式：跑完整 task_list，成功判定与 newSeed 骨架逐字相同。"""
    for entry in _task_list(record_env, label):
        _solve_one(record_env, planner, entry, label)
        evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
        if _runtime_bool(evaluation.get("fail", False), torch_module):
            raise ClipGenerationError(f"{label}: 环境报告失败")
        if _runtime_bool(evaluation.get("success", False), torch_module):
            return
    evaluation = record_env.unwrapped.evaluate(solve_complete_eval=True)
    if not _runtime_bool(evaluation.get("success", False), torch_module):
        raise ClipGenerationError(f"{label}: 跑完整个 task_list 仍未成功")


def execute_truncated(record_env: Any, planner: Any, label: str, task: str) -> int:
    """clip 模式：只 solve 覆盖 clip 所需的前几个子目标，不做成功判定。

    这几个子目标的 `failure_func` 都是 None（Video 的 static、Button 的两次 press），
    所以「不判成功」不等于「放过失败」—— 这段里根本不存在失败条件。
    返回结束时的 elapsed_steps。
    """
    task_list = _task_list(record_env, label)
    wanted = TRUNCATED_SUBGOALS[task]
    if len(task_list) < wanted:
        raise ClipGenerationError(f"{label}: task_list 只有 {len(task_list)} 项，不足 {wanted}")
    for entry in task_list[:wanted]:
        _solve_one(record_env, planner, entry, label)
        record_env.unwrapped.evaluate(solve_complete_eval=True)
    return int(record_env.unwrapped.elapsed_steps)


# ── h5 结构工具 ──────────────────────────────────────────────────────────────


def sorted_timesteps(group: h5py.Group) -> list[str]:
    names = [name for name in group if name.startswith("timestep_")]
    return sorted(names, key=lambda name: int(name.rsplit("_", 1)[1]))


def segment_lengths(episode_group: h5py.Group) -> tuple[int, int, int]:
    """(T, demo_prefix, exec_len)。口径与 MotionJEPA build_data_raw 同源：
    demo = is_video_demo 前缀长；exec = 段内首个 is_completed 真 + 2（截到段尾）。"""
    timesteps = sorted_timesteps(episode_group)
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
    exec_len = len(exec_names) if first_completed is None else min(
        first_completed + 2, len(exec_names)
    )
    return total, demo_prefix, exec_len


def subgoal_boundaries(episode_group: h5py.Group) -> list[dict]:
    """从 h5 提取 simple_subgoal 的切换步 —— Phase 0 用来记录 press 段边界。"""
    boundaries = []
    previous = None
    for name in sorted_timesteps(episode_group):
        raw = episode_group[name]["info"]["simple_subgoal"][()]
        value = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        if value != previous:
            boundaries.append({"step": int(name.rsplit("_", 1)[1]), "subgoal": value})
            previous = value
    return boundaries


def raw_h5_path(output_root: Path, job: ClipJob) -> Path:
    """RecordWrapper 的命名约定：{task}_ep{episode}_seed{seed}.h5。"""
    return (
        output_root / "hdf5_files" / f"{job.task}_ep{job.wrapper_episode}_seed{job.variant_seed}.h5"
    )


def clip_h5_path(output_root: Path, job: ClipJob) -> Path:
    return (
        output_root / "clips" / f"{job.task}_ep{job.wrapper_episode}_seed{job.variant_seed}.h5"
    )


def trace_path(output_root: Path, job: ClipJob) -> Path:
    # 文件名带 seed 是结构性去重：control 模式的 wrapper_episode = src_episode 会在
    # test/val 之间同号（如双方都有 ep3），variant_seed（= env_seed）则全局唯一。
    return (
        output_root / "traces" / f"{job.task}_ep{job.wrapper_episode}_seed{job.variant_seed}.npz"
    )


# ── clip 裁剪：raw 的 timestep_34..143 → 110 帧、帧号重编号 0..109 ─────────────


def write_clip(
    raw_path: Path,
    clip_path: Path,
    job: ClipJob,
    slot_pairs: Sequence[tuple[int, int]],
    bin_pairs_seq: Sequence[tuple[int, int]],
    trace: Sequence[dict],
    fingerprint: Mapping[str, Any],
    geometry: Mapping[str, Any],
) -> dict[str, Any]:
    """裁剪 + 改写 info + 写 swap_gt。返回 clip 的段长信息。

    info 改写的用意（口径与 MotionJEPA `build_data_raw_from_h5` / `segment_lengths` 对齐）：
    整段 clip 必须**恰好**构成该 env 的 scope 段，下游才能把 110 帧当一个完整片段读。

    * Video（scope=demo）：全部 `is_video_demo=True` → demo_prefix=110、exec_len=0；
    * Button（scope=exec）：全部 `is_video_demo=False` + **末帧 `is_completed=True`**
      → exec_len = min(109+2, 110) = 110。

    ⚠ Button 末帧的 `is_completed=True` 是**人为置位**，语义不是「任务完成」而是
    「clip 到此为止」—— 截断 rollout 时任务确实没做完。下游只把它当段尾标记用。
    """
    frames = {item["step"]: item for item in trace}
    str_dtype = h5py.string_dtype(encoding="utf-8")
    demo_flag = CLIP_IS_DEMO[job.task]
    episode_name = f"episode_{job.wrapper_episode}"

    clip_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(raw_path, "r") as raw, h5py.File(clip_path, "w") as clip:
        raw_episode = raw[episode_name]
        missing = [
            step for step in range(CLIP_START, CLIP_END) if f"timestep_{step}" not in raw_episode
        ]
        if missing:
            raise ClipGenerationError(
                f"{job.label}: raw h5 缺 clip 区间的 timestep {missing[:5]}（共 {len(missing)} 帧）"
            )
        if any(step not in frames for step in range(CLIP_START, CLIP_END)):
            raise ClipGenerationError(f"{job.label}: 位姿探针 trace 未覆盖整个 clip 区间")

        clip_episode = clip.create_group(episode_name)
        if "setup" in raw_episode:
            raw.copy(raw_episode["setup"], clip_episode, name="setup")
        setup = clip_episode["setup"] if "setup" in clip_episode else clip_episode.create_group("setup")

        for step in range(CLIP_START, CLIP_END):
            index = step - CLIP_START
            raw.copy(raw_episode[f"timestep_{step}"], clip_episode, name=f"timestep_{index}")
            group = clip_episode[f"timestep_{index}"]

            info = group["info"]
            for key, value in (
                ("is_video_demo", demo_flag),
                ("is_completed", (not demo_flag) and index == CLIP_LEN - 1),
            ):
                if key in info:
                    del info[key]
                info.create_dataset(key, data=bool(value))

            # 逐帧只写**物理引擎实测量**：位置与三类接触。窗口归属与交换对
            # （swap_active / swap_window_idx / swap_progress / swap_slots / swap_bins /
            # swap_pair_pos / env_step）一律不落盘 —— 全部可由 setup 的 bin_pairs + 帧号
            # 复算（windows = swap_windows_clip(len(bin_pairs))，进度是 smoothstep 解析式，
            # env_step = 帧号 + clip_start_env_step）。
            sample = frames[step]
            gt = group.create_group("swap_gt")
            gt.create_dataset("bins_pos", data=sample["bins"].astype(np.float32))
            gt.create_dataset("cubes_pos", data=sample["cubes"].astype(np.float32))
            # 逐帧接触分类（见 swap_inject._contact_snapshot）
            frame_contacts = sample.get("contacts") or {}
            for key in (
                "robot_bin_count", "bin_bin_count", "robot_button_count",
            ):
                gt.create_dataset(
                    f"contact_{key}", data=np.int32(frame_contacts.get(key, 0))
                )
            for key in (
                "robot_bin_impulse", "bin_bin_impulse", "robot_button_impulse",
            ):
                gt.create_dataset(
                    f"contact_{key}", data=np.float32(frame_contacts.get(key, 0.0))
                )

        # ── setup 级：只留**不可复算**的 10 个字段 ──
        # 判据：一个字段只有在「用本组其余字段 + clip_plan.py 的纯函数算不出来」时才落盘。
        # 被删掉的 37 个（topo_class / pair_* / legal_event_slots / slot_nn_margin /
        # net_permutation / signature / variant_seed / windows_* / slot_pairs /
        # bins_pos_traj / cubes_pos_traj / min_clearance / bystander_* / contact_* 聚合量）
        # 的复算路径逐项列在 CLAUDE.md §六；派生标签与协变量一律去 episode_map_{Task}.json 取。
        event_slots = tuple(slot_pairs[0])
        gt = setup.create_group("swap_gt")
        # 复现根：必须用 env_seed 建环境再按 bin_pairs 注入（variant_seed 只是编号，复现不了）
        gt.create_dataset("env_seed", data=np.int64(job.env_seed))
        gt.create_dataset("bin_pairs", data=np.asarray(bin_pairs_seq, dtype=np.int8))
        # ★ 主标签轴：窗口 1 移动的槽位对（受最近邻约束，取值域 4 类）。
        # 它 == slot_pairs[0]，但标签不靠推、必须显式落盘。
        gt.create_dataset("event_slots", data=np.asarray(event_slots, dtype=np.int8))
        # 全部几何的复算根：最近邻集合、topo_class、pair_distance/azimuth、reference_axis_deg
        gt.create_dataset("slot_xy", data=np.asarray(geometry["slot_xy"], dtype=np.float32))
        # 同源分组的键（判据 3/4/5/7 都是同源变体之间的比较）与跨源可比的变体编号。
        # split 必须显式落盘：episode 号只在 split 内可比，且 env_seed 反查 split 需要
        # 翻三份 metadata —— 不可复算，符合「只留不可复算的」口径。
        gt.create_dataset("split", data=job.split, dtype=str_dtype)
        gt.create_dataset("src_episode", data=np.int64(job.src_episode))
        gt.create_dataset("variant_idx", data=np.int64(job.variant_idx))
        # 需与原版序列比对才知道 —— h5 内没有原版序列，静态算不出
        gt.create_dataset("is_original", data=np.int8(int(job.is_original)))
        # 读 train metadata 得来（ep98 的 seed 是历史 attempt 值 16801，公式反推不出）
        gt.create_dataset("difficulty", data=job.difficulty, dtype=str_dtype)
        # clip 帧 ↔ env step 的换算基准与段长，保证 h5 自解释
        gt.create_dataset("clip_start_env_step", data=np.int32(CLIP_START))
        gt.create_dataset("clip_len", data=np.int32(CLIP_LEN))

        # ── setup/meta：颜色等纯 metadata，**不进标签**（宗旨：颜色不管） ──
        meta = setup.create_group("meta")
        meta.create_dataset("bin_colors", data=[
            fingerprint["bin_to_color"].get(str(idx), "empty") for idx in range(job.num_bins)
        ], dtype=str_dtype)
        meta.create_dataset("color_names", data=list(fingerprint["color_names"]), dtype=str_dtype)
        meta.create_dataset("task_goal_color", data=fingerprint["color_names"][0], dtype=str_dtype)
        # 协变量：按钮位置跨源必变（零 src 改动无法固定），同源变体间逐位一致
        for name, position in (fingerprint.get("buttons") or {}).items():
            meta.create_dataset(name, data=np.asarray(position, dtype=np.float32))

        total, demo_prefix, exec_len = segment_lengths(clip_episode)

    return {"n_timesteps": total, "demo_prefix": demo_prefix, "exec_len": exec_len}


def _discard_empty_h5(path: Path, wrapper_episode: int) -> None:
    """删掉失败 attempt 留下的空 h5；确有内容则保留交人工判断。"""
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


# ── 单次 attempt ─────────────────────────────────────────────────────────────


def run_episode(job: ClipJob) -> dict[str, Any]:
    """跑一次 attempt。重试由父进程负责（同 seed 重新入队）。"""
    started = time.time()
    clock = time.monotonic()
    phases: dict[str, float] = {}
    output_root = Path(job.output_root)
    raw_path = raw_h5_path(output_root, job)
    record_env: Any | None = None
    caught: BaseException | None = None
    error_traceback: str | None = None
    fingerprint: dict[str, Any] | None = None
    readback_idx1_final: list[int | None] | None = None
    readback_after_inject: list | None = None
    readback_final: list | None = None
    last_step: int | None = None
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
        ClipGenerationError,
    )
    label = job.label

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
            raise ClipGenerationError(
                f"{label}: 实际 bin 数 {len(unwrapped.spawned_bins)} ≠ 配置 {job.num_bins}"
            )
        trace = attach_pose_probe(unwrapped)

        if job.mode == "clip":
            inject_pairs(unwrapped, job.bin_pairs)
            readback_after_inject = readback_pairs(unwrapped)
            planned = [tuple(sorted(pair)) for pair in job.bin_pairs]
            if readback_after_inject != planned:
                raise ClipGenerationError(
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

        mark = time.monotonic()
        if job.mode == "control":
            execute_full(record_env, planner, torch, label)
        else:
            last_step = execute_truncated(record_env, planner, label, job.task)
            if len(trace) < CLIP_END:
                raise ClipGenerationError(
                    f"{label}: 截断后只录到 {len(trace)} 帧 < clip 所需的 {CLIP_END}"
                )
            # RecordWrapper 只在 episode_success 为真时落盘，而截断跑永远不会 terminated。
            # 这里显式置位 = 有意录制部分轨迹；截断点之前不存在任何失败条件（见 docstring）。
            record_env.episode_success = True
        phases["solve_s"] = time.monotonic() - mark

        # rollout 后、close 前读回：control 模式此刻 idx2 已被最近邻全部回填（原始序列之源）；
        # clip 模式必须仍等于计划（防最近邻逻辑意外覆写）。
        readback_final = readback_pairs(unwrapped)
        # 控制跑额外读回第一主角 idx1 —— 验收才能做「原版 idx2 == NN(idx1)」的有方向判据
        readback_idx1_final = readback_idx1(unwrapped) if job.mode == "control" else None
        if job.mode == "clip":
            planned = [tuple(sorted(pair)) for pair in job.bin_pairs]
            if readback_final != planned:
                raise ClipGenerationError(
                    f"{label}: rollout 后读回 {readback_final} ≠ 计划 {planned}，注入被覆写"
                )
        elif any(None in pair for pair in readback_final):
            raise ClipGenerationError(
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
        "last_env_step": last_step,
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

    try:
        return _postprocess(
            job, raw_path, trace, fingerprint, readback_final,
            readback_after_inject, readback_idx1_final, base,
        )
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


def _measure_events(
    job: ClipJob, trace: Sequence[dict], bin_pairs_seq: Sequence[tuple[int, int]]
) -> tuple[list[int], list[dict]]:
    """按模式决定对账哪些窗口、用完整还是部分位移。返回 (窗口下标, 事件)。

    clip 模式只覆盖 env step [34,144)，所以：窗口 1（env [64,114)）两个端点都在 clip 内，
    走完整净位移；窗口 2（env [114,164)）末端点 164 在 clip 外，只能量到 clip 末帧 143
    （进度 smoothstep(29/50)≈0.62，交换对已明显在动）；窗口 3 完全在 clip 外，不对账。
    """
    windows = swap_windows_env(len(bin_pairs_seq))
    if job.mode == "control":
        indices = list(range(len(windows)))
        events = [measure_window(trace, windows[i], job.num_bins) for i in indices]
    else:
        indices = clip_visible_windows(len(bin_pairs_seq))
        events = []
        for i in indices:
            start, end = windows[i]
            if end <= CLIP_END - 1:
                events.append(measure_window(trace, (start, end), job.num_bins))
            else:
                events.append(
                    measure_window_partial(trace, (start, end), CLIP_END - 1, job.num_bins)
                )
    for index, event in zip(indices, events):
        pair = bin_pairs_seq[index]
        missing = [b for b in sorted(pair) if b not in event["moved_bins"]]
        if missing:
            threshold = MOVED_NET_EPS if event.get("complete") else PARTIAL_MOVED_EPS
            raise ClipGenerationError(
                f"{job.label}: 窗口 {event['window']} 计划交换 bin {sorted(pair)}，"
                f"但 bin {missing} 位移不足 {threshold}（net_disp={event['net_disp']}）"
            )
    return indices, events


def _postprocess(
    job: ClipJob,
    raw_path: Path,
    trace: Sequence[dict],
    fingerprint: Mapping[str, Any],
    readback_final: Sequence[tuple[int, int]],
    readback_after_inject: Sequence | None,
    readback_idx1_final: Sequence[int | None] | None,
    base: Mapping[str, Any],
) -> dict[str, Any]:
    """成功路径的后处理：对账 → 槽位几何 → 裁剪/落 swap_gt → trace 落 npz。"""
    output_root = Path(job.output_root)
    if job.mode == "control":
        bin_pairs_seq = [tuple(pair) for pair in readback_final]
    else:
        bin_pairs_seq = [tuple(sorted(pair)) for pair in job.bin_pairs]
    slot_pairs = list(slot_pairs_from_bin_pairs(bin_pairs_seq, job.num_bins))

    indices, events = _measure_events(job, trace, bin_pairs_seq)
    covered_pairs = [bin_pairs_seq[i] for i in indices]
    covered_windows = [swap_windows_env(len(bin_pairs_seq))[i] for i in indices]
    bystanders = bystander_metrics(events, covered_pairs, job.num_bins)
    clearance = min_clearance(
        trace,
        covered_windows,
        covered_pairs,
        job.num_bins,
        upto_step=None if job.mode == "control" else CLIP_END - 1,
    )
    geometry = slot_geometry(fingerprint)
    # 接触统计只看 clip 覆盖的区间（control 模式看全程）
    contacts = contact_summary(
        trace,
        CLIP_START if job.mode == "clip" else 0,
        CLIP_END if job.mode == "clip" else 10 ** 9,
        event_window=swap_windows_env(len(bin_pairs_seq))[0],
    )

    result: dict[str, Any] = {
        **base,
        "ok": True,
        "bin_pairs": [list(pair) for pair in bin_pairs_seq],
        "slot_pairs": [list(pair) for pair in slot_pairs],
        "signature": signature_of(slot_pairs),
        "event_slots": list(slot_pairs[0]),
        "topo_class": topo_class(tuple(slot_pairs[0])),
        "net_permutation": list(net_permutation(slot_pairs, job.num_bins)),
        "is_original": int(job.is_original),
        "readback_after_inject": readback_after_inject,
        "measured_window_indices": indices,
        "measured_events": events,
        "min_clearance": None if clearance != clearance else round(clearance, 4),
        **bystanders,
        "contacts": contacts,
        "fingerprint": fingerprint,
        "original_idx1": (
            None if readback_idx1_final is None else list(readback_idx1_final)
        ),
        "geometry": {
            "slot_xy": geometry["slot_xy"],
            "reference_axis_deg": geometry["reference_axis_deg"],
            "pairs": {
                f"{i}{j}": info for (i, j), info in geometry["pairs"].items()
            },
            "slot_nearest_neighbor": geometry["slot_nearest_neighbor"],
            "slot_nn_margin": geometry["slot_nn_margin"],
            "legal_event_pairs": geometry["legal_event_pairs"],
        },
    }

    if job.mode == "control":
        with h5py.File(raw_path, "r") as handle:
            episode = handle[f"episode_{job.wrapper_episode}"]
            total, demo_prefix, exec_len = segment_lengths(episode)
            result["subgoal_boundaries"] = subgoal_boundaries(episode)
        result.update(
            {"h5_path": str(raw_path), "n_timesteps": total,
             "demo_prefix": demo_prefix, "exec_len": exec_len}
        )
        steps = sorted(item["step"] for item in trace)
    else:
        clip_path = clip_h5_path(output_root, job)
        segment = write_clip(
            raw_path, clip_path, job, slot_pairs, bin_pairs_seq, trace,
            fingerprint, geometry,
        )
        if segment["n_timesteps"] != CLIP_LEN:
            raise ClipGenerationError(
                f"{job.label}: clip 帧数 {segment['n_timesteps']} ≠ {CLIP_LEN}"
            )
        scope_frames = segment["demo_prefix"] if CLIP_IS_DEMO[job.task] else segment["exec_len"]
        if scope_frames != CLIP_LEN:
            raise ClipGenerationError(
                f"{job.label}: scope 段 {scope_frames} 帧 ≠ 整段 clip {CLIP_LEN} —— info 改写没生效"
            )
        # raw 已无用（clip 是唯一产物），删掉省磁盘
        try:
            raw_path.unlink()
        except OSError:
            pass
        result.update({"h5_path": str(clip_path), **segment})
        steps = list(range(CLIP_START, CLIP_END))

    tpath = trace_path(output_root, job)
    tpath.parent.mkdir(parents=True, exist_ok=True)
    frames = {item["step"]: item for item in trace}
    np.savez_compressed(
        tpath,
        steps=np.asarray(steps, dtype=np.int32),
        bins_pos=np.stack([frames[t]["bins"] for t in steps]).astype(np.float32),
        cubes_pos=np.stack([frames[t]["cubes"] for t in steps]).astype(np.float32),
    )
    result["trace_path"] = str(tpath)
    return result


def _job_fields(job: ClipJob) -> dict[str, Any]:
    return {
        "task": job.task,
        "split": job.split,
        "src_episode": job.src_episode,
        "variant_idx": job.variant_idx,
        "wrapper_episode": job.wrapper_episode,
        "env_seed": job.env_seed,
        "variant_seed": job.variant_seed,
        "difficulty": job.difficulty,
        "mode": job.mode,
        "attempt": job.attempt,
        "planned_bin_pairs": (
            [list(pair) for pair in job.bin_pairs] if job.bin_pairs is not None else None
        ),
        "planned_slot_pairs": (
            [list(pair) for pair in job.slot_pairs] if job.slot_pairs is not None else None
        ),
    }


# ── 调度器（probe_original 与 generate_swap_clips 共用） ──────────────────────
#
# 结构照抄 newSeed 的 _run_jobs：每卡一池、进程终身绑卡、BrokenProcessPool 重建、
# JSONL 边跑边写。唯一实质差异：重试走 job.bump()（同 seed、只加 attempt），绝不换 seed。

MAX_NON_TASK_STRIKES = 3


def _synth_failure(job: ClipJob, exc: BaseException, failure_class: str) -> dict[str, Any]:
    return {
        **_job_fields(job),
        "ok": False,
        "failure_class": failure_class,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "finished_at": time.time(),
    }


def run_jobs(
    jobs: Sequence[ClipJob],
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
    pending: deque[ClipJob] = deque(jobs)
    inflight: dict[Future, tuple[str, ClipJob]] = {}
    succeeded: list[dict[str, Any]] = []
    exhausted: list[dict[str, Any]] = []
    total = len(jobs)
    strikes: dict[tuple[str, str, int, int], int] = {}

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
                key = (job.task, job.split, job.src_episode, job.variant_idx)
                if result.get("ok"):
                    strikes.pop(key, None)
                    succeeded.append(result)
                    print(
                        f"[{len(succeeded)}/{total}] {job.label} 成功"
                        f"（attempt {job.attempt}，{result.get('wall_s')}s）",
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
                        f"    {job.label} 连续 {MAX_NON_TASK_STRIKES} 次非任务性失败"
                        f"（{result.get('error_type')}），放弃",
                        flush=True,
                    )
                elif job.attempt + 1 < max_attempts:
                    print(
                        f"    {job.label} 失败（{result.get('error_type')}: "
                        f"{str(result.get('error'))[:160]}），同 seed 重试 attempt {job.attempt + 1}",
                        flush=True,
                    )
                    pending.append(job.bump())
                else:
                    exhausted.append(result)
                    print(f"    {job.label} 用尽 {max_attempts} 次 attempt，放弃", flush=True)

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
