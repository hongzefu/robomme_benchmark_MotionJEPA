#!/usr/bin/env python3
"""三类像素分布：唯一允许 ground truth 参与的地方。

v4 的口径是「GT 只用来得到背景 / 物体 / 机械臂三类的像素分布，此外一律不看 GT」。
本模块就是这句话的全部实现，分两半：

- **拟合**（`fit_color_model`）：读带 GT segmentation 的 h5，按下面的三类约定把每个
  像素打上类标签，统计**每种颜色在三类里各出现了多少次**，落成一张表；
- **推理**（`ColorModel.classify`）：逐像素查这张表，取计数最大的那一类。之后的
  形态学、连通域、时间平滑全都只看这个标签图，再不碰 GT。

### 三类约定（用户拍板，逐字执行）

| 类 | 定义 |
|---|---|
| 机械臂 | `setup/flow_excluded` 中 `reason == "robot_link"` 的 link |
| 背景 | `setup/flow_excluded` 中 `reason == "background_prop"`（`table-workspace`、`ground`）+ seg_id 0 |
| 物体 | `setup/flow_objects` 里的 actor / link |

`flow_objects` 里还有一项 `kind == "tcp"`（`panda_hand_tcp`）——它是夹爪的工具中心点，
一个不参与渲染的虚拟坐标点，语义上属于机器人而不是任务物体，因此**归到机械臂**而不是
物体。实测它的 seg_id 从未在 segmentation 图里出现过，这条分支是纯防御。

任何在图里出现、却不属于上面任何一类的 seg id 都会**直接报错**而不是猜：三类映射一旦
漏了东西，后面所有数字都失去意义，静默兜底比报错危险得多。

### 为什么是「精确颜色」而不是直方图 bin 或高斯

因为它一个超参都不需要。ManiSkill 的渲染确定性极强（v3 实测 86% 的像素跨 291 帧逐位
重复），一个 episode 抽样 107 帧只有 12761 种不同颜色——颜色本身就是天然的离散量，
按 bin 归并或拟合成高斯反而要引入「bin 数」「协方差正则」这类拍脑袋的量。直接按 24 位
RGB 精确统计，模型就是一张 `颜色 → (背景计数, 物体计数, 机械臂计数)` 的表。

取 `argmax` 就是最大后验：`P(类 | 颜色) ∝ count(颜色, 类)`，类先验已经隐含在计数里，
不需要再乘任何系数。

没见过的颜色返回 `UNKNOWN`（-1）。下游一律按「不是机械臂」处理——本链路的宗旨是宁可
漏标机械臂，也绝不误标别的东西，未知颜色当然要往保守方向倒。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

import h5py
import numpy as np


# 类编号：下游的标签图、混淆矩阵、统计口径全部按这个顺序
CLASS_BACKGROUND = 0
CLASS_OBJECT = 1
CLASS_ARM = 2
CLASS_UNKNOWN = -1
CLASS_NAMES = ("background", "object", "arm")
NUM_CLASSES = 3

# 落盘的模型文件里必须带上这个，口径变了立刻能认出来
COLOR_MODEL_SCHEMA_VERSION = "color-model-v4"


def pack_rgb(rgb: np.ndarray) -> np.ndarray:
    """把 (H, W, 3) uint8 打包成 (H, W) uint32，24 位精确无损。"""
    array = np.asarray(rgb)
    if array.ndim != 3 or array.shape[2] != 3:
        raise ValueError(f"rgb 形状不是 (H, W, 3)：{array.shape}")
    if array.dtype != np.uint8:
        raise ValueError(f"rgb 不是 uint8：{array.dtype}")
    wide = array.astype(np.uint32)
    return (wide[..., 0] << 16) | (wide[..., 1] << 8) | wide[..., 2]


def class_ids_from_setup(setup_group: h5py.Group) -> dict[str, set[int]]:
    """按上面的三类约定，从 setup 的 seg_id 枚举表推出三类 seg id 集合。"""
    excluded = setup_group.get("flow_excluded")
    objects = setup_group.get("flow_objects")
    if not isinstance(excluded, h5py.Group) or not isinstance(objects, h5py.Group):
        raise ValueError(
            "setup 下缺少 flow_excluded / flow_objects，无法建立三类映射："
            "该 h5 生成时没开 flow，seg_id 枚举表不存在"
        )

    arm: set[int] = set()
    background: set[int] = {0}  # seg_id 0 = 没有任何几何体命中的像素
    task_objects: set[int] = set()

    for name in excluded:
        entry = excluded[name]
        reason = entry["reason"][()].decode()
        seg_id = int(entry["seg_id"][()])
        if reason == "robot_link":
            arm.add(seg_id)
        elif reason == "background_prop":
            background.add(seg_id)
        else:
            raise ValueError(f"flow_excluded/{name} 的 reason 未知：{reason}")

    for name in objects:
        entry = objects[name]
        seg_id = int(entry["seg_id"][()])
        kind = entry["kind"][()].decode()
        if kind == "tcp":
            # 夹爪工具中心点：语义上属于机器人，且实测从不出现在 segmentation 图里
            arm.add(seg_id)
        else:
            task_objects.add(seg_id)

    overlap = (arm & background) | (arm & task_objects) | (background & task_objects)
    if overlap:
        raise ValueError(f"三类 seg id 出现重叠：{sorted(overlap)}")
    return {"arm": arm, "background": background, "object": task_objects}


def uncovered_mask(
    segmentation: np.ndarray,
    class_ids: Mapping[str, set[int]],
) -> np.ndarray:
    """标出不在 setup 三类表里的 seg id 所在的像素，供统计与诊断。"""
    seg = np.asarray(segmentation)
    known = class_ids["background"] | class_ids["object"] | class_ids["arm"]
    return ~np.isin(seg, list(known))


def labels_from_segmentation(
    segmentation: np.ndarray,
    class_ids: Mapping[str, set[int]],
) -> np.ndarray:
    """把 GT segmentation 图翻译成三类标签图。

    ### setup 表没覆盖的 seg id 一律归「物体」

    `setup/flow_objects` 与 `flow_excluded` 是 `reset()` 那一刻对
    `segmentation_id_map` 的快照，**episode 运行中动态创建的对象不在里面**。实测有
    5 个任务会出现这种 id，逐帧目视核对过，全是任务的目标 / 路径标记物：
    InsertPeg 箱顶的插孔标记、PickHighlight 的绿色高亮块、SwingXtimes 的靶心圆盘、
    PatternLock 的图案连线节点（id 涨到 572）、RouteStick 的路线曲线（涨到 710）。

    机器人各 link 与桌面地面这些背景道具都是 `reset()` 之前就建好的、已被完整枚举，
    因此**运行中新出现的 id 必定是任务相关的可见物体**，归「物体」既符合语义，也让它们
    享受到下游的物体硬否决保护——正对应「绝不误标其他物体」的宗旨。

    这条兜底不是静默的：`uncovered_mask` 把这部分像素单独数出来，写进验证指标。
    """
    seg = np.asarray(segmentation)
    labels = np.full(seg.shape, CLASS_OBJECT, dtype=np.int8)
    labels[np.isin(seg, list(class_ids["background"]))] = CLASS_BACKGROUND
    labels[np.isin(seg, list(class_ids["object"]))] = CLASS_OBJECT
    labels[np.isin(seg, list(class_ids["arm"]))] = CLASS_ARM
    return labels


@dataclass(frozen=True)
class ColorModel:
    """`颜色 → 三类计数` 的表。`colors` 升序排列，供 searchsorted 查。"""

    colors: np.ndarray  # (N,) uint32，升序
    counts: np.ndarray  # (N, 3) int64，列顺序 = CLASS_NAMES
    source: Mapping[str, object]  # 拟合口径（任务、episode 范围、帧数等），纯留档

    def __post_init__(self) -> None:
        if self.colors.ndim != 1 or self.counts.shape != (self.colors.size, NUM_CLASSES):
            raise ValueError(
                f"颜色表形状不自洽：colors={self.colors.shape} counts={self.counts.shape}"
            )
        if not np.all(np.diff(self.colors) > 0):
            raise ValueError("colors 必须严格升序且不重复")

    @property
    def class_pixel_totals(self) -> np.ndarray:
        return self.counts.sum(axis=0)

    def classify(self, rgb: np.ndarray, veto_shared: bool = True) -> np.ndarray:
        """(H, W, 3) uint8 → (H, W) int8 标签图；没见过的颜色给 CLASS_UNKNOWN。

        `veto_shared` 打开时多一条**共享色否决**：某颜色只要在拟合集里被观察为「物体」
        过（物体计数 > 0），就一律不判机械臂，改判物体。

        这条规则是留出集实测逼出来的，不是拍脑袋加的。纯 `argmax` 版本的物体误标率是
        0.203%，逐帧看下来全是同一种形态：**被夹爪按压或抓握的白色按钮顶面、灰白盒子
        高光**，它们与灰白臂壳在 24 位 RGB 上完全同色，`argmax` 按多数把这些颜色判给了
        机械臂。形态学救不了——那些像素在分类阶段就已经错了。

        代价是实测量化过的：被否决的只有 **80 种颜色，全是 R=G=B 的灰阶**，带走 8.6%
        的机械臂像素、**0 个背景像素**。用 8.6% 的漏标换掉几乎全部物体误标，正是
        「绝不误标其他物体、允许少量机械臂没被标进去」这条宗旨要的取舍。

        它仍然只用同一张分布表，没有引入任何新的判据来源，也没有引入阈值——门限就是
        「出现过 / 没出现过」，即 0。
        """
        packed = pack_rgb(rgb)
        flat = packed.ravel()
        index = np.searchsorted(self.colors, flat)
        # searchsorted 可能给出 N（比表里所有颜色都大），先夹住再验命中
        clipped = np.clip(index, 0, self.colors.size - 1)
        hit = self.colors[clipped] == flat
        picked = self.counts[clipped]
        winner = np.argmax(picked, axis=1).astype(np.int8)
        if veto_shared:
            winner[(winner == CLASS_ARM) & (picked[:, CLASS_OBJECT] > 0)] = CLASS_OBJECT
        winner[~hit] = CLASS_UNKNOWN
        return winner.reshape(packed.shape)

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            target,
            schema_version=COLOR_MODEL_SCHEMA_VERSION,
            colors=self.colors,
            counts=self.counts,
            source=np.array(repr(dict(self.source)), dtype=object),
        )
        return target

    @classmethod
    def load(cls, path: str | Path) -> "ColorModel":
        with np.load(Path(path), allow_pickle=True) as data:
            version = str(data["schema_version"])
            if version != COLOR_MODEL_SCHEMA_VERSION:
                raise ValueError(
                    f"颜色模型 schema 版本不符：{version} != {COLOR_MODEL_SCHEMA_VERSION}"
                )
            return cls(
                colors=data["colors"],
                counts=data["counts"],
                source={"repr": str(data["source"])},
            )


def _merge_counts(
    base_colors: np.ndarray,
    base_counts: np.ndarray,
    new_colors: np.ndarray,
    new_counts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """把两张 `颜色 → 计数` 表并成一张，颜色升序去重、计数相加。"""
    colors = np.concatenate([base_colors, new_colors])
    counts = np.concatenate([base_counts, new_counts])
    unique, inverse = np.unique(colors, return_inverse=True)
    merged = np.zeros((unique.size, NUM_CLASSES), dtype=np.int64)
    for class_index in range(NUM_CLASSES):
        merged[:, class_index] = np.bincount(
            inverse, weights=counts[:, class_index], minlength=unique.size
        ).astype(np.int64)
    return unique, merged


def accumulate_frames(
    frames: Iterable[tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    """把若干 (rgb, labels) 帧统计成一张颜色表。

    整段一次性 `np.unique`，比逐帧合并快得多：一个 episode 500 帧也就 3300 万个
    uint32（约 131 MB），单次 unique 只要一两秒。
    """
    packed_chunks: list[np.ndarray] = []
    label_chunks: list[np.ndarray] = []
    for rgb, labels in frames:
        packed_chunks.append(pack_rgb(rgb).ravel())
        label_chunks.append(np.asarray(labels).ravel())
    if not packed_chunks:
        return np.zeros(0, dtype=np.uint32), np.zeros((0, NUM_CLASSES), dtype=np.int64)

    packed = np.concatenate(packed_chunks)
    labels = np.concatenate(label_chunks)
    unique, inverse = np.unique(packed, return_inverse=True)
    counts = np.zeros((unique.size, NUM_CLASSES), dtype=np.int64)
    for class_index in range(NUM_CLASSES):
        selected = labels == class_index
        if selected.any():
            counts[:, class_index] = np.bincount(
                inverse[selected], minlength=unique.size
            )
    return unique, counts


def iter_episode_frames(
    episode_group: h5py.Group,
) -> Iterator[tuple[str, np.ndarray, np.ndarray, bool]]:
    """按 timestep 顺序产出 (timestep 名, front_rgb, segmentation, is_video_demo)。"""
    named: list[tuple[int, str]] = []
    for name in episode_group:
        if not name.startswith("timestep_"):
            continue
        suffix = name[len("timestep_") :]
        if not suffix.isdigit():
            raise ValueError(f"无法解析的 timestep 名：{name}")
        named.append((int(suffix), name))
    named.sort()
    for _, name in named:
        group = episode_group[name]
        obs = group["obs"]
        yield (
            name,
            obs["front_rgb"][()],
            obs["front_camera_segmentation"][()],
            bool(group["info"]["is_video_demo"][()]),
        )


def episode_names(handle: h5py.File) -> list[str]:
    """按 episode 编号顺序列出 h5 里的 episode。"""
    named: list[tuple[int, str]] = []
    for name in handle:
        if not name.startswith("episode_"):
            continue
        suffix = name[len("episode_") :]
        if not suffix.isdigit():
            raise ValueError(f"无法解析的 episode 名：{name}")
        named.append((int(suffix), name))
    named.sort()
    return [name for _, name in named]


def fit_color_model(
    h5_paths: Sequence[str | Path],
    episodes: Sequence[int],
    verbose: bool = False,
) -> ColorModel:
    """在指定 h5 的指定 episode 上拟合一张全局共享的三类颜色表。"""
    colors = np.zeros(0, dtype=np.uint32)
    counts = np.zeros((0, NUM_CLASSES), dtype=np.int64)
    wanted = set(int(item) for item in episodes)
    used: list[dict[str, object]] = []

    for path in h5_paths:
        with h5py.File(str(path), "r") as handle:
            for episode_name in episode_names(handle):
                if int(episode_name[len("episode_") :]) not in wanted:
                    continue
                episode = handle[episode_name]
                class_ids = class_ids_from_setup(episode["setup"])
                frames: list[tuple[np.ndarray, np.ndarray]] = []
                for _, rgb, segmentation, _ in iter_episode_frames(episode):
                    frames.append(
                        (rgb, labels_from_segmentation(segmentation, class_ids))
                    )
                new_colors, new_counts = accumulate_frames(frames)
                colors, counts = _merge_counts(colors, counts, new_colors, new_counts)
                used.append(
                    {
                        "h5": Path(path).name,
                        "episode": episode_name,
                        "frames": len(frames),
                    }
                )
                if verbose:
                    print(
                        f"[{len(used)}] {Path(path).stem.replace('record_dataset_', '')}"
                        f"/{episode_name} 帧={len(frames)} 累计颜色数={colors.size}",
                        flush=True,
                    )

    if colors.size == 0:
        raise ValueError("拟合集为空：没有任何 episode 命中")
    return ColorModel(
        colors=colors,
        counts=counts,
        source={"episodes": sorted(wanted), "used": used},
    )
