#!/usr/bin/env python3
"""在既有 RecordWrapper 上增量挂载 flow 与纯 CV 去机械臂图。

父类 ``src/robomme/env_record_wrapper/RecordWrapper.py`` 保持不变。本类只 override
``reset`` / ``step`` / ``close``：flow 沿用 v2 的仿真真值链路；``front_rgb_masked`` 则在
``super().close()`` 后，完全由本 episode 的 ``front_rgb`` 与 ``front_depth`` 后处理得到。

去臂链路刻意放在 ``close()``：它不进入仿真、控制与规划热路径，也不消费随机数，因此不会改变
``joint_action``。这条链路不读取 segmentation、不查询机器人 link，也不保留夹爪；桌面只有被
机械臂实际挡住的像素会用时序背景补回，其他桌面像素逐位不变。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import h5py


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from robomme.env_record_wrapper import RobommeRecordWrapper  # noqa: E402

from flow_tracker import FlowTracker, write_flow_groups  # noqa: E402
from masked_rgb import write_masked_rgb_groups  # noqa: E402


class RobommeRecordWrapperV3(RobommeRecordWrapper):
    """带 2D flow ground truth 与纯 CV 去机械臂图的薄 RecordWrapper。"""

    def __init__(
        self,
        env,
        *args: Any,
        record_flow: bool = False,
        record_masked_rgb: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(env, *args, **kwargs)
        self.record_flow = bool(record_flow)
        self.record_masked_rgb = bool(record_masked_rgb)
        self._flow_tracker: FlowTracker | None = None
        self.flow_capture_seconds = 0.0
        self.flow_capture_count = 0
        self.masked_rgb_seconds = 0.0
        self.masked_rgb_frames = 0

    def reset(self, **kwargs: Any):
        result = super().reset(**kwargs)
        if self.record_flow:
            # flow 仍需在场景建好后冻结物体清单；纯 CV 去臂不需要任何仿真对象信息。
            self._flow_tracker = FlowTracker(self.unwrapped)
        return result

    def step(self, action):
        buffered_before = len(self.buffer)
        result = super().step(action)
        if self.record_flow and self._flow_tracker is not None:
            if len(self.buffer) > buffered_before:
                started = time.perf_counter()
                self.buffer[-1]["_flow"] = self._flow_tracker.capture(
                    result[0], self.unwrapped
                )
                self.flow_capture_seconds += time.perf_counter() - started
                self.flow_capture_count += 1
        return result

    def close(self):
        # 父类会 clear buffer，先保留数组引用。去臂只拿 RGB-D，绝不拿 segmentation。
        if self.record_masked_rgb and self.buffer:
            first_obs = self.buffer[0]["obs"]
            for required in ("front_rgb", "front_depth"):
                if required not in first_obs:
                    raise RuntimeError(
                        f"父类 buffer 里没有 obs['{required}']，无法生成纯 CV 去臂图。"
                        "父类 step() 的缓冲字段变了，v3 链路需要同步跟进。"
                    )

        flow_frames = [record.get("_flow") for record in self.buffer]
        masked_sources = (
            [
                (record["obs"]["front_rgb"], record["obs"]["front_depth"])
                for record in self.buffer
            ]
            if self.record_masked_rgb
            else []
        )
        episode_success = bool(self.episode_success)
        dataset_path = self.dataset_path
        tracker = self._flow_tracker

        result = super().close()

        write_flow = self.record_flow and episode_success and tracker is not None
        write_masked = self.record_masked_rgb and episode_success and bool(masked_sources)
        if write_flow or write_masked:
            with h5py.File(dataset_path, "a") as handle:
                episode_name = f"episode_{self.episode}"
                if episode_name not in handle:
                    raise RuntimeError(
                        f"父类写盘后未找到 {episode_name}，无法追加：{dataset_path}"
                    )
                episode_group = handle[episode_name]
                if write_flow:
                    write_flow_groups(episode_group, flow_frames, tracker.meta)
                if write_masked:
                    started = time.perf_counter()
                    self.masked_rgb_frames = write_masked_rgb_groups(
                        episode_group, masked_sources
                    )
                    self.masked_rgb_seconds = time.perf_counter() - started

        return result

    @property
    def flow_capture_ms_per_step(self) -> float:
        """每个记录帧的 flow 采集平均耗时（毫秒），没有采集过则为 0。"""
        if self.flow_capture_count <= 0:
            return 0.0
        return self.flow_capture_seconds / self.flow_capture_count * 1000.0
