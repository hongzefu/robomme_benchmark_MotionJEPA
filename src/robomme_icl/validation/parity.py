"""原版与新版逐项对照；报告保留首个差异，不用最终success替代过程。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..io.hdf5 import assert_identical, read_episode, tree_hash
from ..io.paths import output_path
from ..specs import NATIVE_REFERENCE, canonical_json


def event_timeline(frames):
    """从真实状态提取subgoal、交换计划以及显示对象生命周期。"""
    events = []
    previous = {}
    previous_subgoal = None
    previous_schedule = None
    for operation_index, frame in enumerate(frames):
        info = frame["info"]
        state = frame["observation"].get("native_state", {})
        step = info["step"]
        subgoal = (
            info.get("subgoal_index"),
            info.get("subgoal"),
            info.get("is_demonstration"),
        )
        if subgoal != previous_subgoal:
            events.append(
                {
                    "operation_index": operation_index,
                    "step": step,
                    "kind": "subgoal",
                    "value": subgoal,
                }
            )
            previous_subgoal = subgoal
        schedule = state.get("task_state", {}).get("swap_schedule")
        if schedule != previous_schedule:
            events.append(
                {
                    "operation_index": operation_index,
                    "step": step,
                    "kind": "swap_schedule",
                    "value": schedule,
                }
            )
            previous_schedule = schedule
        current = {}
        for name, actor in state.get("actors", {}).items():
            position = np.asarray(actor["pose"]["position"]).reshape(-1, 3)[0]
            visible = max(abs(position)) < 5 and any(
                value > 0 for value in actor["visibility"]
            )
            current[name] = bool(visible)
            if name not in previous:
                events.append(
                    {
                        "operation_index": operation_index,
                        "step": step,
                        "kind": "created",
                        "actor": name,
                        "visible": bool(visible),
                    }
                )
            elif current[name] != previous[name]:
                events.append(
                    {
                        "operation_index": operation_index,
                        "step": step,
                        "kind": "visibility",
                        "actor": name,
                        "visible": bool(visible),
                    }
                )
        for name in sorted(previous.keys() - current.keys()):
            events.append(
                {
                    "operation_index": operation_index,
                    "step": step,
                    "kind": "removed",
                    "actor": name,
                }
            )
        previous = current
    return events


def compare_episodes(reference_path, actual_path, report_path):
    """同一配置输入、同一数值运行条件，比较全部操作及原始RGB。"""
    reference = read_episode(reference_path)
    actual = read_episode(actual_path)
    result = {
        "reference": str(Path(reference_path).resolve()),
        "actual": str(Path(actual_path).resolve()),
        "native_reference": NATIVE_REFERENCE,
        "checks": {},
        "passed": False,
    }
    checks = result["checks"]
    try:
        if reference.runtime_fingerprint.get("reference_commit") != NATIVE_REFERENCE:
            raise ValueError("对照记录不是已验证的固定原版")
        ignored = {"legacy_source_hash", "reference_commit"}
        assert_identical(
            {
                key: value
                for key, value in reference.runtime_fingerprint.items()
                if key not in ignored
            },
            {
                key: value
                for key, value in actual.runtime_fingerprint.items()
                if key not in ignored
            },
            path="数值运行条件与记录器版本",
        )
        checks["runtime"] = True
        assert_identical(reference.episode_spec, actual.episode_spec, path="场景输入")
        checks["spec"] = True
        left = next(
            frame["info"]
            for frame in reference.frames
            if frame["info"]["operation"] == "reset_complete"
        )
        right = next(
            frame["info"]
            for frame in actual.frames
            if frame["info"]["operation"] == "reset_complete"
        )
        for key in (
            "initial_assets",
            "initial_state",
            "initial_sensor_parameters",
            "task_inventory",
            "native_parameters",
        ):
            assert_identical(left[key], right[key], path=key)
            checks[key] = True
        left_events = event_timeline(reference.frames)
        right_events = event_timeline(actual.frames)
        assert_identical(left_events, right_events, path="事件时间线")
        checks["events"] = True
        assert_identical(reference.frames, actual.frames, path="全部操作含原始RGB")
        checks["all_frames_exact"] = True
        result.update(
            passed=True,
            operations=len(actual.frames),
            frame_hash=tree_hash(actual.frames),
            event_count=len(right_events),
            events=right_events,
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        destination = output_path(report_path, create_parent=True)
        if destination.exists():
            previous = json.loads(destination.read_text(encoding="utf-8"))
            if canonical_json(previous) != canonical_json(result):
                raise ValueError(
                    f"复核结果与已有报告不符，保留旧报告：{result.get('error', destination)}"
                )
        else:
            with destination.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
    return result
