#!/usr/bin/env python3
"""在既有 RecordWrapper 之上增量挂载 flow 采集的薄子类。

设计前提是「只增不改」：新增 flow 字段不得改变任何既有 h5 内容，`joint_action` 必须逐位一致。
因此这里**不复制、不重构、不修改** ``src/robomme/env_record_wrapper/RecordWrapper.py``，而是继承它，
只 override 三个方法，每个方法都先把活交给 ``super()``，再在其后做纯增量的事情。

三个 override 各自成立的理由：

- **reset()**：父类 reset 走完之后场景才建好，这时才能枚举物体。枚举只读
  ``segmentation_id_map``，不消费随机数。
- **step()**：父类 ``step()`` 里构造 ``record_data`` 并 append 进 buffer 的位置，本来就在
  ``super().step(action)`` **之后**，且整段包在 ``_video_should_record()`` 判断内（名为
  ``NO RECORD`` 的段天然不进 buffer）。所以这里比对 buffer 长度就能知道本帧是否被记录，
  记录了才采集 flow 并挂到 ``buffer[-1]`` 上。**全部 flow 逻辑都在 RNG 消费之后**，不可能
  影响仿真与规划的随机数顺序。父类写盘时只按固定键读 ``record_data``，多挂一个 ``_flow``
  键完全无害。
- **close()**：父类 ``close()`` 会原样写盘并关闭 h5 文件，一行都不用改。这里先把 flow 数据从
  buffer 里抄走（父类会 clear buffer），等父类写完之后再以追加模式重新打开同一个 raw h5，
  把 flow 内容加进去。生成入口的合并步用 ``raw.copy(raw[name], merged, name=name)`` 整组拷贝
  episode，flow 作为该组的子内容会原样进入最终文件，合并逻辑同样不用动。
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


class RobommeRecordWrapperV2(RobommeRecordWrapper):
    """带 2D flow ground truth 采集的 RecordWrapper。

    ``record_flow=False`` 时行为与父类完全一致，可直接用来做自对拍基线。
    """

    def __init__(self, env, *args: Any, record_flow: bool = False, **kwargs: Any) -> None:
        super().__init__(env, *args, **kwargs)
        self.record_flow = bool(record_flow)
        self._flow_tracker: FlowTracker | None = None
        # 采集耗时统计：RRTStar 兜底带墙钟预算，每步新增开销过大有可能改变规划结果，
        # 所以把这项开销做成可观测量，冒烟时核对。
        self.flow_capture_seconds = 0.0
        self.flow_capture_count = 0

    def reset(self, **kwargs: Any):
        result = super().reset(**kwargs)
        if self.record_flow:
            # 场景已建好，此时枚举并冻结物体清单；纯读，不消费随机数
            self._flow_tracker = FlowTracker(self.unwrapped)
        return result

    def step(self, action):
        buffered_before = len(self.buffer)
        result = super().step(action)
        if self.record_flow and self._flow_tracker is not None:
            if len(self.buffer) > buffered_before:
                # 本帧确实被父类记录了，才有对应的 timestep 需要挂 flow
                started = time.perf_counter()
                self.buffer[-1]["_flow"] = self._flow_tracker.capture(
                    result[0], self.unwrapped
                )
                self.flow_capture_seconds += time.perf_counter() - started
                self.flow_capture_count += 1
        return result

    def close(self):
        # 父类 close() 会 clear buffer，先把 flow 抄走；同时记下写盘要用到的状态
        flow_frames = [record.get("_flow") for record in self.buffer]
        episode_success = bool(self.episode_success)
        dataset_path = self.dataset_path
        tracker = self._flow_tracker

        result = super().close()

        if self.record_flow and episode_success and tracker is not None:
            with h5py.File(dataset_path, "a") as handle:
                episode_name = f"episode_{self.episode}"
                if episode_name not in handle:
                    raise RuntimeError(
                        f"父类写盘后未找到 {episode_name}，无法追加 flow：{dataset_path}"
                    )
                write_flow_groups(handle[episode_name], flow_frames, tracker.meta)

        return result

    @property
    def flow_capture_ms_per_step(self) -> float:
        """每个记录帧的 flow 采集平均耗时（毫秒），没有采集过则为 0。"""
        if self.flow_capture_count <= 0:
            return 0.0
        return self.flow_capture_seconds / self.flow_capture_count * 1000.0
