#!/usr/bin/env python3
"""在既有 RecordWrapper 之上增量落盘 GT segmentation 的薄子类。

本链路要回答的问题是「只用三类像素分布 + 形态学规则能不能把机械臂标出来」，
而三类（背景 / 物体 / 机械臂）的定义必须来自仿真真值，验证也要拿真值当尺子。
所以这个 wrapper 只多写两样东西，缺一不可：

1. **逐帧 segmentation 图** ``timestep_<k>/obs/front_camera_segmentation``——
   父类 ``RecordWrapper`` 在 ``step()`` 里本来就把它放进了 buffer
   （``episode_config_resolver`` 里 ``obs_mode="rgb+depth+segmentation"``），
   但写盘那行 ``create_dataset`` 是被注释掉的状态，所以它进不了 h5；
2. **seg_id 枚举表** ``setup/segmentation_objects`` 与 ``setup/segmentation_excluded``
   （见 ``seg_id_table.py``）——没有它，上面那张图只是一堆无法解释的整数。

### 设计前提：只增不改

**不复制、不重构、不修改** ``src/robomme/env_record_wrapper/RecordWrapper.py``，
而是继承它，只 override ``reset()`` 与 ``close()`` 两个方法，各自都先把活交给
``super()``，再在其后做纯增量的事情：

- **reset()**：父类 reset 走完之后场景才建好，这时才能枚举物体。枚举只读
  ``segmentation_id_map``，不消费随机数。
- **close()**：父类 ``close()`` 会原样写盘并关闭 h5 文件，一行都不用改。这里先把
  segmentation 从 buffer 里抄走（父类会 clear buffer），等父类写完之后再以追加模式
  重新打开同一个 raw h5 把内容加进去。生成入口的合并步用
  ``raw.copy(raw[name], merged, name=name)`` 整组拷贝 episode，新增内容作为该组的
  子内容会原样进入最终文件，合并逻辑同样不用动。

### ⚠ step() 一个字不动 —— 热路径零开销

历史上这一层还挂过逐帧稀疏物体轨迹采集（每步 0.5–1.0 ms）与纯色棕遮蔽图，两者本链路
都不消费，已于重构时整体删除。现在 ``step()`` 没有 override，于是「新增采集会不会挤掉
规划器那 1 秒墙钟预算、进而改变 RRTStar 的采样结果」这个风险结构性归零。

写盘放在 ``close()`` 还有两个好处：与 ``front_rgb`` **天然同帧**（写的就是父类即将
写盘的那帧 obs 里的同一个数组对象）；**故障隔离**——整段在 ``super().close()`` 之后
执行，这边出任何问题都不妨碍父类把 h5 与视频写完。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for _path in (SRC_ROOT, SCRIPT_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from robomme.env_record_wrapper import RobommeRecordWrapper  # noqa: E402

from seg_id_table import SegIdTable, write_seg_id_table  # noqa: E402


# 逐帧图与 seg_id 枚举表由本 wrapper 一起写，属同一套 schema，共用一个版本号
SEGMENTATION_SCHEMA_VERSION = "segmentation-v1"

# 落盘的 dataset 名，与 obs 下既有字段并列
SEGMENTATION_DATASET = "front_camera_segmentation"


def timestep_names(episode_group: h5py.Group) -> list[str]:
    """按数字顺序列出 episode 下的 timestep group 名。"""
    named: list[tuple[int, str]] = []
    for name in episode_group.keys():
        if not name.startswith("timestep_"):
            continue
        suffix = name[len("timestep_") :]
        if not suffix.isdigit():
            # 父类写盘遇到重名会退化成 timestep_<k>_dupN，正常路径不会出现，
            # 一旦出现就说明帧序无法可靠对齐，直接报错而不是猜。
            raise ValueError(f"无法解析的 timestep 名：{name}")
        named.append((int(suffix), name))
    named.sort()
    return [name for _, name in named]


def _as_2d_segmentation(segmentation: Any) -> np.ndarray:
    """把一帧 segmentation 规整成 2D 整数数组。

    obs 里这一项可能是 torch tensor、也可能带 batch 或通道维（如 ``(1, H, W, 1)``）。
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
    table: SegIdTable,
) -> int:
    """把逐帧图与 seg_id 枚举表一起写进已落盘的 episode group，返回写入帧数。

    流式处理：转完一帧立刻落盘再丢掉，峰值只多占一张图（256×256 int16 约 128 KB）。
    """
    names = timestep_names(episode_group)
    if len(names) != len(sources):
        raise ValueError(
            f"timestep 数量（{len(names)}）与 segmentation 源帧数（{len(sources)}）不一致"
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
    write_seg_id_table(setup_group, table)

    for name, segmentation in zip(names, sources):
        obs_group = episode_group[name].get("obs")
        if not isinstance(obs_group, h5py.Group):
            raise ValueError(f"{name} 下缺少 obs group")
        if SEGMENTATION_DATASET in obs_group:
            # 拒绝覆盖：走到这里说明同一个 episode 被写了两次，静默覆盖会掩盖真正的问题
            raise ValueError(f"{name}/obs 下已存在 {SEGMENTATION_DATASET}，拒绝覆盖")
        obs_group.create_dataset(
            SEGMENTATION_DATASET, data=_as_2d_segmentation(segmentation)
        )
    return len(names)


class RobommeRecordWrapperGT(RobommeRecordWrapper):
    """多落一份 GT segmentation（逐帧图 + seg_id 枚举表）的 RecordWrapper。

    开关关掉时行为与父类完全一致，可直接用作自对拍基线。
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
        self._seg_id_table: SegIdTable | None = None
        # 纯观测量：写盘发生在 close() 里，不占 step() 一丝一毫
        self.segmentation_frames = 0
        self.segmentation_seconds = 0.0

    def reset(self, **kwargs: Any):
        result = super().reset(**kwargs)
        if self.record_segmentation:
            # 场景已建好，此时枚举并冻结 seg_id 表；纯读，不消费随机数。
            # 必须在这里冻结：super().close() 会拆掉 SAPIEN 场景，
            # 之后再碰 segmentation_id_map 就是未定义行为了。
            self._seg_id_table = SegIdTable(self.unwrapped)
        return result

    def close(self):
        # 父类 close() 会 clear buffer，先把要用的东西抄走。抄的是**引用**不是数据：
        # buffer.clear() 只清空 list，数组本体被下面这个 list 引用着，仍然活着。
        segmentation_sources: list[Any] = []
        if self.record_segmentation and self.buffer:
            first_obs = self.buffer[0]["obs"]
            if SEGMENTATION_DATASET not in first_obs:
                raise RuntimeError(
                    f"父类 buffer 里没有 obs['{SEGMENTATION_DATASET}']，无法落盘 segmentation。"
                    "父类 step() 的缓冲字段变了，本链路需要同步跟进。"
                )
            segmentation_sources = [
                record["obs"][SEGMENTATION_DATASET] for record in self.buffer
            ]

        episode_success = bool(self.episode_success)
        dataset_path = self.dataset_path
        table = self._seg_id_table

        result = super().close()

        if (
            self.record_segmentation
            and episode_success
            and segmentation_sources
            and table is not None
        ):
            started = time.perf_counter()
            with h5py.File(dataset_path, "a") as handle:
                episode_name = f"episode_{self.episode}"
                if episode_name not in handle:
                    raise RuntimeError(
                        f"父类写盘后未找到 {episode_name}，无法追加：{dataset_path}"
                    )
                self.segmentation_frames = write_segmentation_groups(
                    handle[episode_name], segmentation_sources, table
                )
            self.segmentation_seconds = time.perf_counter() - started

        return result
