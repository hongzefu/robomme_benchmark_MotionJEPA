#!/usr/bin/env python3
"""newtask-v2 三路对拍的进程内观察器（测试侧，产品代码不导入）。

生成走的是真实入口与真实 worker（spawn 出来的子进程），所以观察器不能只在测试进程里
打桩，必须随进程启动装好。做法是把 ``tests/_shared/parity_sitecustomize`` 放进
``PYTHONPATH``，由解释器启动时的 ``sitecustomize`` 调用本模块的 :func:`install`；
本模块只用标准库，装的是「导入后回调」，等目标模块真正被导入时才包装它们的属性。
A 路（基线 worktree）与 B/C 路（当前工作树）模块名相同，同一套观察器通用。

它只包装原有调用、只读状态，不新增 ``evaluate()``、reset、随机抽样、渲染或物理步。

打桩位置（方案第四步 4.0 点名）：

* ``torch.rand`` / ``torch.randint`` / ``torch.randperm``：④ 随机调用序列与流状态
* ``numpy.random.seed``：④ VideoRepick 的进程级全局播种副作用
* 四个任务**模块命名空间**里的 ``swap_flat_two_lane``、``highlight_obj``、
  ``lift_and_drop_objects_back_to_original``、``lift_and_drop_objectA_onto_objectB``：
  ②.3 事件。四任务用 ``from .utils import *`` 引入的是裸名，打在 ``statechange``
  上不生效且会静默产出零事件，必须打在任务模块属性上
* ``subgoal_evaluate_func.sequential_task_check``：②.2 求值返回细节
  （``evaluate()`` 内部的 ``current_task_name``、``task_failed`` 不存到实例上）
* ``RobommeRecordWrapper.reset`` 的返回值：①.1 初态（生成器丢弃了它）
* ``FailAwarePanda*MotionPlanningSolver.move_to_pose_with_RRTStar``：4.0 每局
  ``rrt_fallback_count``（screw→RRTStar 回退不可播种，触发局只能单独登记）

环境变量：

* ``PARITY_EVIDENCE_DIR``：证据根目录，不设则整个观察器不安装
* ``PARITY_LABEL``：三路标签（A / B / C 等）
* ``PARITY_STEPS``：``0`` 关闭逐步状态采集（默认开）
* ``PARITY_MAX_RNG``：随机调用记录上限，超出后只计数不记录（默认 400000）
"""

from __future__ import annotations

import atexit
import gzip
import hashlib
import importlib
import importlib.abc
import importlib.util
import json
import os
import re
import base64
import inspect
import zlib
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

EVIDENCE_VERSION = 3

_state: dict[str, Any] = {
    "installed": False,
    "root": None,
    "label": "",
    "record_steps": True,
    "max_rng": 400000,
    "episode": None,
    "episodes": [],
    "sequence": 0,
    "lock": threading.RLock(),
}


# ── 证据容器 ──────────────────────────────────────────────────────────────────


class _EpisodeEvidence:
    """一局（一个 env 实例）的全部证据；按 (task, seed) 切分。"""

    def __init__(self, task: str, seed: Any, difficulty: Any) -> None:
        self.task = str(task)
        self.seed = seed
        self.difficulty = difficulty
        self.rng: list[dict[str, Any]] = []
        self.rng_total = 0
        self.events: list[dict[str, Any]] = []
        self.boundaries: list[dict[str, Any]] = []
        self.steps: list[dict[str, Any]] = []
        self.initial_obs: dict[str, Any] | None = None
        self.recordings: list[dict[str, Any]] = []
        self.rrt_fallback_count = 0
        self.call_index = 0
        self.generator_ordinals: dict[int, int] = {}
        # 时间只写独立旁路文件，不进入 payload 或随机流计数。
        self.timing: dict[str, Any] | None = None
        if os.environ.get("PARITY_TIMING") == "1":
            self.timing = {"task": self.task, "seed": self.seed,
                           "difficulty": self.difficulty, "pid": os.getpid(),
                           "reset_ns": None, "first_step_ns": None,
                           "last_step_ns": None, "close_ns": None}

    def next_index(self) -> int:
        self.call_index += 1
        return self.call_index

    def payload(self) -> dict[str, Any]:
        return {
            "evidence_version": EVIDENCE_VERSION,
            "label": _state["label"],
            "pid": os.getpid(),
            "task": self.task,
            "seed": self.seed,
            "difficulty": self.difficulty,
            "rrt_fallback_count": self.rrt_fallback_count,
            "rng_total": self.rng_total,
            "rng_recorded": len(self.rng),
            "event_count": len(self.events),
            "step_count": len(self.steps),
            "rng": self.rng,
            "events": self.events,
            "boundaries": self.boundaries,
            "steps": self.steps,
            "initial_obs": self.initial_obs,
            "recordings": self.recordings,
        }


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:32]


_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]+")
# 连续 8 位以上数字只可能是 id()／内存地址；cube_red_10 这类真实序号不会被误伤
_OBJECT_ID_RE = re.compile(r"\d{8,}")


def _stable_repr(value: Any) -> str:
    """对象 repr 里的内存地址逐次运行必然不同，会造成假差异；抹掉地址、保留身份信息。"""
    return _ADDRESS_RE.sub("0xADDR", repr(value))[:200]


def _summarize(value: Any) -> Any:
    """把任意返回值压成可比较、可序列化的摘要；浮点保留位模式散列。"""
    try:
        import numpy as np
    except Exception:  # pragma: no cover - numpy 一定在
        np = None  # type: ignore[assignment]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        import struct

        return {"float_bits": struct.pack("<d", value).hex()}
    if isinstance(value, (list, tuple)):
        return [_summarize(item) for item in value[:64]]
    if isinstance(value, dict):
        return {str(key): _summarize(value[key]) for key in sorted(value, key=str)[:64]}
    module = type(value).__module__ or ""
    if module.startswith("torch") and hasattr(value, "detach"):
        try:
            array = value.detach().cpu().numpy()
        except Exception:
            return {"repr": _stable_repr(value)}
        return _summarize(array)
    if np is not None and isinstance(value, np.ndarray):
        if value.size <= 16:
            return {
                "dtype": str(value.dtype),
                "shape": list(value.shape),
                "values": value.reshape(-1).tolist(),
            }
        return {
            "dtype": str(value.dtype),
            "shape": list(value.shape),
            "sha256": _digest(value.tobytes()),
        }
    if np is not None and isinstance(value, np.generic):
        return {"dtype": str(value.dtype), "values": [value.item()]}
    return {"repr": _stable_repr(value)}


def _generator_ordinal(generator: Any) -> int:
    """本局内「第几个出现的随机源」；不能用 id()，内存地址跨进程必然不同。"""
    episode = _current()
    if episode is None:
        return -1
    key = id(generator)
    ordinal = episode.generator_ordinals.get(key)
    if ordinal is None:
        ordinal = len(episode.generator_ordinals)
        episode.generator_ordinals[key] = ordinal
    return ordinal


def _generator_state(generator: Any, device: Any = None) -> dict[str, Any]:
    """随机源身份与状态：不改状态，只读。"""
    if generator is None:
        import torch
        selected_device = torch.device(device or "cpu")
        if selected_device.type == "cuda":
            generator = torch.cuda.default_generators[selected_device.index or torch.cuda.current_device()]
        else:
            generator = torch.default_generator
        info: dict[str, Any] = {"source": "global", "device": str(selected_device)}
    else:
        info = {"source": "generator", "ordinal": _generator_ordinal(generator)}
    info["initial_seed"] = int(generator.initial_seed())
    info["state_sha256"] = _digest(generator.get_state().cpu().numpy().tobytes())
    return info


# ── 当前局的切换与落盘 ────────────────────────────────────────────────────────


def _begin_episode(task: str, seed: Any, difficulty: Any) -> None:
    with _state["lock"]:
        _flush_current()
        _state["episode"] = _EpisodeEvidence(task, seed, difficulty)


def _current() -> _EpisodeEvidence | None:
    return _state["episode"]


def _write_timing(episode: _EpisodeEvidence) -> None:
    """按实际 PID 和局序号隔离旁路证据，超时残缺记录不能冒充完成。"""
    if episode.timing is None or not _state["root"]:
        return
    directory = Path(_state["root"]) / str(_state["label"]) / f"{episode.task}_seed{episode.seed}"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"pid{os.getpid()}-{_state['sequence']:02d}.timing.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(episode.timing, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(target)


def _flush_current() -> None:
    episode = _state["episode"]
    if episode is None:
        return
    root = _state["root"]
    if root is None:
        _state["episode"] = None
        return
    _write_timing(episode)
    directory = Path(root) / str(_state["label"]) / f"{episode.task}_seed{episode.seed}"
    directory.mkdir(parents=True, exist_ok=True)
    # 同一进程可能连续跑多局（⑤ 的甲→乙→甲），文件名必须带序号，否则后一局覆盖前一局；
    # 同一 (task, seed) 还可能因难度不同而多次出现，难度写在 payload 里供读取端消歧。
    sequence = _state["sequence"]
    _state["sequence"] = sequence + 1
    target = directory / f"pid{os.getpid()}-{sequence:02d}.json.gz"
    temporary = target.with_name(f".{target.name}.tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        json.dump(episode.payload(), handle, ensure_ascii=False, sort_keys=False)
    temporary.replace(target)
    _state["episodes"].append(str(target))
    _state["episode"] = None


# ── 包装器 ────────────────────────────────────────────────────────────────────


def _wrap_random(module: Any, name: str) -> None:
    original = getattr(module, name, None)
    if original is None or getattr(original, "_parity_wrapped", False):
        return

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        episode = _current()
        generator = kwargs.get("generator")
        record = episode is not None and len(episode.rng) < _state["max_rng"]
        before = _generator_state(generator, kwargs.get("device")) if record else None
        result = original(*args, **kwargs)
        if episode is not None:
            episode.rng_total += 1
            if record:
                episode.rng.append(
                    {
                        "i": episode.next_index(),
                        "fn": f"torch.{name}",
                        "args": [_summarize(item) for item in args],
                        "kwargs": {
                            key: _summarize(value)
                            for key, value in kwargs.items()
                            if key != "generator"
                        },
                        "rng_before": before,
                        "rng": _generator_state(generator, kwargs.get("device")),
                        "result": _summarize(result),
                    }
                )
        return result

    wrapper._parity_wrapped = True  # type: ignore[attr-defined]
    wrapper._parity_original = original  # type: ignore[attr-defined]
    setattr(module, name, wrapper)


def _wrap_numpy_seed(module: Any) -> None:
    original = getattr(module, "seed", None)
    if original is None or getattr(original, "_parity_wrapped", False):
        return

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        episode = _current()
        if episode is not None:
            episode.events.append(
                {
                    "i": episode.next_index(),
                    "kind": "global_numpy_seed",
                    "args": [_summarize(item) for item in args],
                }
            )
        return original(*args, **kwargs)

    wrapper._parity_wrapped = True  # type: ignore[attr-defined]
    setattr(module, "seed", wrapper)


def _wrap_event(module: Any, name: str) -> None:
    original = getattr(module, name, None)
    if not callable(original) or getattr(original, "_parity_wrapped", False):
        return
    signature = inspect.signature(original)

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        episode = _current()
        index = episode.next_index() if episode is not None else -1
        if episode is not None:
            arguments = signature.bind_partial(*args, **kwargs).arguments
            timing = {key: int(arguments[key]) for key in ("start_step", "end_step", "cur_step") if key in arguments}
            binding = None
            if name == "swap_flat_two_lane" and args:
                env = args[0]
                binding = {
                    "a": _actor_identity(env, kwargs.get("cube_a")),
                    "b": _actor_identity(env, kwargs.get("cube_b")),
                    "start_step": _summarize(kwargs.get("start_step")),
                    "end_step": _summarize(kwargs.get("end_step")),
                    "cur_step": _summarize(kwargs.get("cur_step")),
                }
                for number, pair in enumerate(getattr(env, "swap_schedule", [])):
                    if pair[0] is kwargs.get("cube_a") and pair[1] is kwargs.get("cube_b") and pair[2] == kwargs.get("start_step"):
                        binding["swap_index"] = number
                        break
            episode.events.append(
                {
                    "i": index,
                    "kind": "event_enter",
                    "name": name,
                    "module": getattr(module, "__name__", "?"),
                    "args": [_summarize(item) for item in args[:8]],
                    "kwargs": {key: _summarize(value) for key, value in list(kwargs.items())[:8]},
                    "swap_binding": binding,
                    "timing": timing,
                }
            )
        result = original(*args, **kwargs)
        if episode is not None:
            episode.events.append(
                {"i": episode.next_index(), "kind": "event_exit", "name": name, "result": _summarize(result)}
            )
        return result

    wrapper._parity_wrapped = True  # type: ignore[attr-defined]
    setattr(module, name, wrapper)


def _actor_snapshot(env: Any) -> dict[str, Any]:
    """读取场景内全部 actor 的位姿与速度；只读，不触发 GPU 同步之外的副作用。"""
    snapshot: dict[str, Any] = {}
    scene = getattr(env, "scene", None)
    actors = getattr(scene, "actors", None)
    if not isinstance(actors, dict):
        return snapshot
    aliased: dict[str, list[dict[str, Any]]] = {}
    for name in sorted(actors, key=str):
        actor = actors[name]
        # RouteStick 的高亮盘名字里直接嵌了 id(obj)（statechange.py:248,466），
        # 跨进程必然不同：这类 actor 的**身份**本就不可跨进程观测，抹掉 id 后还会同名相撞，
        # 于是把同一归一名下的若干个按内容排序成多重集合比较，位置与状态本身照常逐项比。
        raw_name = str(name)
        name = _OBJECT_ID_RE.sub("<ID>", raw_name)
        entry: dict[str, Any] = {}
        try:
            pose = actor.pose
            entry["p"] = _summarize(pose.p)
            entry["q"] = _summarize(pose.q)
        except Exception:
            entry["pose_error"] = True
        for attribute in ("linear_velocity", "angular_velocity"):
            try:
                entry[attribute] = _summarize(getattr(actor, attribute))
            except Exception:
                pass
        if name != raw_name:
            aliased.setdefault(name, []).append(entry)
        else:
            snapshot[name] = entry
    for name, entries in aliased.items():
        snapshot[name] = sorted(
            entries, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True)
        )
    return snapshot


_TASK_STATE_FIELDS = (
    "difficulty",
    "dynamic",
    "seed",
    "num_repeats",
    "swap_times",
    "pick_times",
    "static_flag",
    "start_step",
    "color_names",
    "selected_bin_indices",
    "route_button_indices",
    "target_cube_indices",
    "red_cubes_target_number",
    "blue_cubes_target_number",
    "green_cubes_target_number",
    "red_cubes_spawn_number",
    "blue_cubes_spawn_number",
    "green_cubes_spawn_number",
    "binfill_language_sequence",
    "current_task_index",
    "task_index",
    "match",
    "after_demo",
    "achieved_list",
)


def _actor_identity(env: Any, actor: Any) -> dict[str, Any] | None:
    """以生成序号绑定物体身份；颜色不能代替身份，位置不能用于重排。"""
    if actor is None:
        return None
    for field in ("spawned_bins", "spawned_cubes", "buttons_grid", "spawned_dynamic_cubes"):
        for index, item in enumerate(getattr(env, field, [])):
            if item is actor:
                result = {"collection": field, "index": index, "name": _stable_repr(getattr(actor, "name", ""))}
                if field == "spawned_bins":
                    result["color"] = getattr(env, "bin_to_color", {}).get(index)
                return result
    return None


def _action_bindings(env: Any) -> dict[str, Any]:
    """同时适用于原基线和新版，只读已建立的任务与对象，不调用求解器。"""
    pickup_targets = []
    route_tasks = []
    for index, entry in enumerate(getattr(env, "task_list", [])):
        if not isinstance(entry, dict):
            continue
        if "pick up" in entry.get("choice_label", "") and "segment" in entry:
            pickup_targets.append({"task_index": index, "demonstration": entry.get("demonstration"),
                "target": _actor_identity(env, entry["segment"]), "role": entry.get("choice_label")})
        if "expected_dir" in entry:
            defaults = getattr(entry.get("solve"), "__defaults__", ()) or ()
            targets = [identity for value in defaults if (identity := _actor_identity(env, value)) is not None]
            route_tasks.append({"task_index": index, "demonstration": entry.get("demonstration"),
                "targets": targets, "expected_dir": entry["expected_dir"]})
    return {
        "pickup_targets": pickup_targets,
        "swap_pairs": [{"swap_index": index, "a": _actor_identity(env, pair[0]),
            "b": _actor_identity(env, pair[1]), "start_step": _summarize(pair[2]), "end_step": _summarize(pair[3])}
            for index, pair in enumerate(getattr(env, "swap_schedule", []))],
        "route": {"nodes": [_actor_identity(env, actor) for actor in getattr(env, "selected_buttons", [])],
            "directions": list(getattr(env, "swing_directions", [])), "tasks": route_tasks},
    }


def _task_state(env: Any) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for field in _TASK_STATE_FIELDS:
        if hasattr(env, field):
            try:
                state[field] = _summarize(getattr(env, field))
            except Exception:
                state[field] = {"unreadable": True}
    task_list = getattr(env, "task_list", None)
    if isinstance(task_list, list):
        names = []
        for entry in task_list:
            if isinstance(entry, dict):
                names.append(str(entry.get("name", "?")))
            else:
                names.append(repr(entry)[:60])
        state["task_list"] = names
    state["action_bindings"] = _action_bindings(env)
    return state


def _wrap_task_class(task_class: Any, task_name: str) -> None:
    if getattr(task_class, "_parity_wrapped", False):
        return
    task_class._parity_wrapped = True

    original_init = task_class.__init__

    def init(self: Any, *args: Any, **kwargs: Any) -> Any:
        _begin_episode(task_name, kwargs.get("seed", None), kwargs.get("difficulty", None))
        cache_empty = not bool(getattr(self, "_spawned_cubes", []))
        result = original_init(self, *args, **kwargs)
        episode = _current()
        if episode is not None:
            episode.difficulty = getattr(self, "difficulty", episode.difficulty)
            episode.boundaries.append(
                {
                    "i": episode.next_index(),
                    "stage": "after_init",
                    "spawn_cache_empty_on_entry": cache_empty,
                    "task_state": _task_state(self),
                }
            )
        return result

    task_class.__init__ = init

    for method_name, stage in (("_load_scene", "after_load_scene"), ("_initialize_episode", "after_initialize_episode")):
        original = getattr(task_class, method_name, None)
        if original is None:
            continue

        def make(original: Callable[..., Any], stage: str) -> Callable[..., Any]:
            def method(self: Any, *args: Any, **kwargs: Any) -> Any:
                result = original(self, *args, **kwargs)
                episode = _current()
                if episode is not None:
                    episode.boundaries.append(
                        {
                            "i": episode.next_index(),
                            "stage": stage,
                            "task_state": _task_state(self),
                            "actors": _actor_snapshot(self),
                        }
                    )
                return result

            return method

        setattr(task_class, method_name, make(original, stage))

    original_step = getattr(task_class, "step", None)
    if original_step is not None:

        def step(self: Any, *args: Any, **kwargs: Any) -> Any:
            episode = _current()
            if episode is not None and _state["record_steps"]:
                episode.steps.append(
                    {
                        "i": episode.next_index(),
                        "phase": "before_step",
                        "action": _summarize(args[0]) if args else None,
                        "task_state": _task_state(self),
                        "actors": _actor_snapshot(self),
                    }
                )
            result = original_step(self, *args, **kwargs)
            if episode is not None and _state["record_steps"]:
                episode.steps.append(
                    {
                        "i": episode.next_index(),
                        "phase": "after_step",
                        "task_state": _task_state(self),
                        "actors": _actor_snapshot(self),
                    }
                )
            return result

        task_class.step = step


def _patch_task_module(module: Any, task_name: str) -> None:
    task_class = getattr(module, task_name, None)
    if task_class is not None:
        _wrap_task_class(task_class, task_name)
    for name in (
        "swap_flat_two_lane",
        "highlight_obj",
        "lift_and_drop_objects_back_to_original",
        "lift_and_drop_objectA_onto_objectB",
    ):
        _wrap_event(module, name)


def _patch_record_wrapper(module: Any) -> None:
    wrapper_class = getattr(module, "RobommeRecordWrapper", None)
    if wrapper_class is None or getattr(wrapper_class, "_parity_reset_wrapped", False):
        return
    wrapper_class._parity_reset_wrapped = True
    original_reset = wrapper_class.reset

    def reset(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_reset(self, *args, **kwargs)
        episode = _current()
        if episode is not None:
            if episode.timing is not None:
                episode.timing.update(reset_ns=time.monotonic_ns(), first_step_ns=None,
                                      last_step_ns=None, close_ns=None)
                _write_timing(episode)
            episode.initial_obs = {
                "i": episode.next_index(),
                "note": "外层 reset 的返回观测；生成器丢弃了它，HDF5 中没有对应帧",
                "value": _summarize(result),
            }
            # 保留原 reset 返回的 RGB，供目视；只转存已有数组，不额外渲染。
            obs = result[0]
            rgb = {}
            for camera, source in (("front_rgb", "base_camera"), ("wrist_rgb", "hand_camera")):
                array = obs["sensor_data"][source]["rgb"][0].detach().cpu().numpy()
                rgb[camera] = {"dtype": str(array.dtype), "shape": list(array.shape),
                    "zlib_base64": base64.b64encode(zlib.compress(array.tobytes())).decode("ascii")}
            episode.initial_obs["rgb"] = rgb
        return result

    wrapper_class.reset = reset
    original_step = wrapper_class.step

    def step(self: Any, *args: Any, **kwargs: Any) -> Any:
        episode = _current()
        event_begin = len(episode.events) if episode is not None else 0
        record_begin = len(self.buffer)
        before = int(self.unwrapped.elapsed_steps)
        if episode is not None and episode.timing is not None:
            if episode.timing["first_step_ns"] is None:
                episode.timing["first_step_ns"] = time.monotonic_ns()
                _write_timing(episode)
        result = original_step(self, *args, **kwargs)
        if episode is not None and episode.timing is not None:
            episode.timing["last_step_ns"] = time.monotonic_ns()
        if episode is not None:
            episode.recordings.append({"env_step_before": before, "env_step_after": int(self.unwrapped.elapsed_steps),
                "record_begin": record_begin, "record_end": len(self.buffer),
                "event_begin": event_begin, "event_end": len(episode.events)})
        return result

    wrapper_class.step = step

    if os.environ.get("PARITY_TIMING") == "1":
        original_close = wrapper_class.close

        def close(self: Any, *args: Any, **kwargs: Any) -> Any:
            episode = _current()
            if episode is not None and episode.timing is not None:
                if episode.timing["close_ns"] is None:
                    episode.timing["close_ns"] = time.monotonic_ns()
                _write_timing(episode)
            return original_close(self, *args, **kwargs)

        wrapper_class.close = close


def _patch_planner(module: Any) -> None:
    for class_name in (
        "FailAwarePandaArmMotionPlanningSolver",
        "FailAwarePandaStickMotionPlanningSolver",
    ):
        planner_class = getattr(module, class_name, None)
        if planner_class is None or getattr(planner_class, "_parity_rrt_wrapped", False):
            continue
        original = getattr(planner_class, "move_to_pose_with_RRTStar", None)
        if original is None:
            continue
        planner_class._parity_rrt_wrapped = True

        def make(original: Callable[..., Any]) -> Callable[..., Any]:
            def method(self: Any, *args: Any, **kwargs: Any) -> Any:
                episode = _current()
                if episode is not None:
                    episode.rrt_fallback_count += 1
                    episode.events.append(
                        {"i": episode.next_index(), "kind": "rrt_fallback", "name": "move_to_pose_with_RRTStar"}
                    )
                return original(self, *args, **kwargs)

            return method

        planner_class.move_to_pose_with_RRTStar = make(original)


def _patch_subgoal_evaluate(module: Any) -> None:
    _wrap_event(module, "sequential_task_check")


_TARGETS: dict[str, Callable[[Any], None]] = {
    "torch": lambda module: [_wrap_random(module, name) for name in ("rand", "randint", "randperm")],
    "numpy.random": _wrap_numpy_seed,
    "robomme.env_record_wrapper": _patch_record_wrapper,
    "robomme.robomme_env.utils.planner_fail_safe": _patch_planner,
    "robomme.robomme_env.utils.subgoal_evaluate_func": _patch_subgoal_evaluate,
    "robomme.robomme_env.BinFill": lambda module: _patch_task_module(module, "BinFill"),
    "robomme.robomme_env.RouteStick": lambda module: _patch_task_module(module, "RouteStick"),
    "robomme.robomme_env.VideoUnmaskSwap": lambda module: _patch_task_module(module, "VideoUnmaskSwap"),
    "robomme.robomme_env.VideoRepick": lambda module: _patch_task_module(module, "VideoRepick"),
}

_busy: set[str] = set()


class _ObservedLoader(importlib.abc.Loader):
    def __init__(self, inner: Any, name: str) -> None:
        self._inner = inner
        self._name = name

    def create_module(self, spec: Any) -> Any:
        return self._inner.create_module(spec)

    def exec_module(self, module: Any) -> None:
        self._inner.exec_module(module)
        handler = _TARGETS.get(self._name)
        if handler is not None:
            try:
                handler(module)
            except Exception as exc:  # 观察器绝不能让被观察的进程崩掉
                sys.stderr.write(f"[parity-observer] 包装 {self._name} 失败：{exc!r}\n")

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


class _ObservedFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname not in _TARGETS or fullname in _busy:
            return None
        _busy.add(fullname)
        try:
            spec = importlib.util.find_spec(fullname)
        except Exception:
            return None
        finally:
            _busy.discard(fullname)
        if spec is None or spec.loader is None:
            return None
        spec.loader = _ObservedLoader(spec.loader, fullname)
        return spec


def install() -> bool:
    """装好观察器；未设 ``PARITY_EVIDENCE_DIR`` 时什么也不做并返回 False。"""
    if _state["installed"]:
        return True
    root = os.environ.get("PARITY_EVIDENCE_DIR")
    if not root:
        return False
    _state["installed"] = True
    _state["root"] = root
    _state["label"] = os.environ.get("PARITY_LABEL", "unknown")
    _state["record_steps"] = os.environ.get("PARITY_STEPS", "1") != "0"
    _state["max_rng"] = int(os.environ.get("PARITY_MAX_RNG", "400000"))
    sys.meta_path.insert(0, _ObservedFinder())
    # 已经被导入过的目标（正常情况下不会有）立即补打
    for name, handler in _TARGETS.items():
        module = sys.modules.get(name)
        if module is not None:
            try:
                handler(module)
            except Exception as exc:
                sys.stderr.write(f"[parity-observer] 补打 {name} 失败：{exc!r}\n")
    atexit.register(_flush_current)
    return True
