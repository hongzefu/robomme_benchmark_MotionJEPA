#!/usr/bin/env python3
"""在 v2.1 薄子类之上再叠一层：把父类本来就缓存着的 GT segmentation 落进 h5。

v4 链路要回答的问题是「只用三类像素分布 + 形态学规则能不能把机械臂标出来」，
而三类（背景 / 物体 / 机械臂）的定义必须来自仿真真值，验证也要拿真值当尺子。
现成产物里唯一缺的就是**逐帧 segmentation 图本身**：

- 父类 ``RecordWrapper`` 在 ``step()`` 里已经把 ``front_camera_segmentation``
  放进 buffer（``episode_config_resolver`` 里 ``obs_mode="rgb+depth+segmentation"``），
  但写盘那行 ``create_dataset`` 是被注释掉的状态，所以它进不了 h5；
- v2.1 的 ``front_rgb_masked`` 只是它的一个二值化派生物（机器人 vs 非机器人），
  分不出「物体」与「背景」，也因为黑指尖豁免而缺掉一部分机器人像素。

所以这里做的事只有一件：**把 buffer 里现成的那张图原样多写一个 dataset**。

### 为什么写在 close() 里

与 v2.1 的 ``front_rgb_masked`` 同理，见 ``record_wrapper_v2.py`` 的说明：

1. **热路径零开销**——``step()`` 一个字不动，规划器那 1 秒墙钟预算不受任何影响，
   于是「新增采集会不会改变 RRTStar 采样结果」这个风险直接归零；
2. **与 front_rgb 天然同帧**——写的就是父类即将写盘的那帧 obs 里的同一个数组对象；
3. **故障隔离**——整段在 ``super().close()`` 之后执行，出问题也不妨碍父类写完 h5。

### 只增不改

新增内容只有 ``timestep_<k>/obs/front_camera_segmentation`` 一个 dataset，
既有字段的数值、dtype、shape、group 层级、timestep 数量与写入时序全部不动，
仿真与规划的随机数消费顺序也完全不变（本文件不消费任何随机数）。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
# flow 采集、遮蔽图与物体枚举的口径只允许有一份，直接复用 v2.1 的模块，不拷贝不重写
V21_DIR = REPO_ROOT / "scripts" / "data-generation-v2.1"
for _path in (SRC_ROOT, V21_DIR, SCRIPT_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from record_wrapper_v2 import RobommeRecordWrapperV2  # noqa: E402

from flow_tracker import _timestep_names  # noqa: E402


SEGMENTATION_SCHEMA_VERSION = "segmentation-v4"

# 落盘的 dataset 名，与 obs 下既有字段并列
SEGMENTATION_DATASET = "front_camera_segmentation"


def _as_2d_segmentation(segmentation: Any) -> np.ndarray:
    """把一帧 segmentation 规整成 2D 整数数组。

    obs 里这一项可能是 torch tensor、也可能带 batch 或通道维（如 ``(1, H, W, 1)``）。
    squeeze 到 2D 与 v2.1 ``MaskPainter.paint`` 的消费口径完全一致，两处不会漂移。
    """
    array = np.squeeze(np.asarray(segmentation))
    if array.ndim != 2:
        raise ValueError(f"segmentation squeeze 后不是 2D：{array.shape}")
    if not np.issubdtype(array.dtype, np.integer):
        raise ValueError(f"segmentation 不是整数类型：{array.dtype}")
    return array


def write_segmentation_groups(
    episode_group: h5py.Group,
    sources: Sequence[Any],
) -> int:
    """逐帧写进已存在的 ``timestep_<k>/obs/``，返回写入帧数。

    流式处理：转完一帧立刻落盘再丢掉，峰值只多占一张图（256×256 int16 约 128 KB）。
    """
    timestep_names = _timestep_names(episode_group)
    if len(timestep_names) != len(sources):
        raise ValueError(
            f"timestep 数量（{len(timestep_names)}）与 segmentation 源帧数（{len(sources)}）不一致"
        )

    setup_group = episode_group.get("setup")
    if not isinstance(setup_group, h5py.Group):
        raise ValueError("episode 下缺少 setup group，无法写入 segmentation 元数据")
    if "segmentation_schema_version" in setup_group:
        raise ValueError("setup 下已存在 segmentation_schema_version，拒绝覆盖")
    setup_group.create_dataset(
        "segmentation_schema_version",
        data=SEGMENTATION_SCHEMA_VERSION,
        dtype=h5py.string_dtype("utf-8"),
    )

    for name, segmentation in zip(timestep_names, sources):
        obs_group = episode_group[name].get("obs")
        if not isinstance(obs_group, h5py.Group):
            raise ValueError(f"{name} 下缺少 obs group")
        if SEGMENTATION_DATASET in obs_group:
            # 拒绝覆盖：走到这里说明同一个 episode 被写了两次，静默覆盖会掩盖真正的问题
            raise ValueError(f"{name}/obs 下已存在 {SEGMENTATION_DATASET}，拒绝覆盖")
        obs_group.create_dataset(
            SEGMENTATION_DATASET, data=_as_2d_segmentation(segmentation)
        )
    return len(timestep_names)


class RobommeRecordWrapperV4(RobommeRecordWrapperV2):
    """在 v2.1 子类基础上多落一份 GT segmentation。

    三个开关全关时行为与父类 ``RecordWrapper`` 完全一致，可直接用作自对拍基线。
    """

    def __init__(
        self,
        env,
        *args: Any,
        record_segmentation: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(env, *args, **kwargs)
        self.record_segmentation = bool(record_segmentation)
        # 纯观测量：写盘发生在 close() 里，不占 step() 一丝一毫
        self.segmentation_frames = 0
        self.segmentation_seconds = 0.0

    def close(self):
        # 父类 close() 会 clear buffer，先把要用的东西抄走。抄的是**引用**不是数据：
        # buffer.clear() 只清空 list，数组本体被下面这个 list 引用着，仍然活着。
        segmentation_sources: list[Any] = []
        if self.record_segmentation and self.buffer:
            first_obs = self.buffer[0]["obs"]
            if SEGMENTATION_DATASET not in first_obs:
                raise RuntimeError(
                    f"父类 buffer 里没有 obs['{SEGMENTATION_DATASET}']，无法落盘 segmentation。"
                    "父类 step() 的缓冲字段变了，v4 链路需要同步跟进。"
                )
            segmentation_sources = [
                record["obs"][SEGMENTATION_DATASET] for record in self.buffer
            ]

        episode_success = bool(self.episode_success)
        dataset_path = self.dataset_path

        # super() 是 v2.1 子类：它自己也会先抄 flow / masked 再调父类写盘
        result = super().close()

        if self.record_segmentation and episode_success and segmentation_sources:
            started = time.perf_counter()
            with h5py.File(dataset_path, "a") as handle:
                episode_name = f"episode_{self.episode}"
                if episode_name not in handle:
                    raise RuntimeError(
                        f"父类写盘后未找到 {episode_name}，无法追加：{dataset_path}"
                    )
                self.segmentation_frames = write_segmentation_groups(
                    handle[episode_name], segmentation_sources
                )
            self.segmentation_seconds = time.perf_counter() - started

        return result
