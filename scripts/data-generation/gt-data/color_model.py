#!/usr/bin/env python3
"""两分布 + 臂分布的像素颜色模型：唯一允许 ground truth 参与的地方。

口径刻意偏弱（用户拍板）：GT 不提供背景 / 物体 / 机械臂的**三类**分布，只允许提供
**两个场景级分布 + 臂自身的分布**：

- **纯背景像素**的颜色分布；
- **背景∪物体像素**（混合，物体不单独可见，物体在其中的类先验未知）的颜色分布；
- **机械臂像素**的颜色分布（用标定集的 10 个 episode 标定）。

等价的现实语义：你能拿到「没有臂的空场景」和「摆了物体但没有臂的场景」两种画面级
监督，外加臂自己的外观样本，但拿不到物体级的逐像素分割。本模块分两半：

- **拟合**（`fit_color_model`）：读带 GT segmentation 的 h5，统计每种 24 位颜色在三列
  里的计数——**列 0 = 纯背景**（GT 背景像素）、**列 1 = 背景∪物体混合**（GT 背景像素
  与 GT 物体像素都计入，故列 1 的支撑集 ⊇ 列 0）、**列 2 = 机械臂**；
- **推理**（`ColorModel.classify`）：逐像素查表，按**三段支撑判据**定类——只看每列
  「见过 / 没见过」，计数的数值大小不参与。之后的形态学、连通域、时间平滑全都只看
  这个标签图，再不碰 GT。

### 判别规则（纯支撑三段式，唯一口径，无开关）

设某颜色在三列的计数为 N₀（纯背景）、N₁（背景∪物体混合）、N₂（机械臂）：

| 判决 | 条件 | 语义 |
|---|---|---|
| 背景 | `N₀ > 0` | 在纯背景场景里出现过 |
| 机械臂 | `N₁ = 0` 且 `N₂ > 0` | 无臂场景里从未出现过，且在臂上出现过 |
| 混合 | 其余（等价于 `N₀ = 0` 且 `N₁ > 0`） | 只在摆了物体的场景里出现过 |
| UNKNOWN(−1) | 颜色不在表里 | 下游一律按「不是机械臂」处理 |

三条性质：

- **互斥且穷尽**。由重叠计数的构造有 `supp(N₀) ⊆ supp(N₁)`，故 `N₀ > 0` 蕴含 `N₁ > 0`，
  与判臂条件互斥；表内每行至少一列 > 0（`__post_init__` 断言），故不会漏。
- **一个超参都没有**。门限就是「出现过 / 没出现过」，即 0；不归一化、不比大小，也
  **不做「混合 − 背景」减法**——两列逐色可对减就等于变相恢复物体分布，违背「物体类
  先验未知」的设定。
- **臂那一段是往保守方向倒的**：某颜色只要在无臂场景里出现过，就无法排除它属于物体，
  按「绝不误标物体、允许少量机械臂没被标进去」一律不判臂。臂列的存在让「未见色」
  得以保留保守语义（若只有两个分布，臂只能定义为「未被解释的颜色」，未见色会被迫
  判臂，失效方向与宗旨相反）。

### ⚠ 判臂色在标定集上误标物体恒为 0，是恒等式不是经验数字

判臂的定义就是「混合列一次都没出现过」，而混合列已把 GT 物体像素全部计入，所以判臂
颜色在标定集上的物体像素恰为 0。**评估集上唯一可能的漏洞**是「标定集只在臂上见过、
评估集却出现在物体上」的颜色——这一格没有构造保证，必须逐次实测（见 arm-mask 的
实测入口，误标物体像素是刚性闸门）。

代价也是闭式的：臂列与混合列共享的颜色一律不判臂，这部分臂像素必然漏标。它们实测
全是 R=G=B 的中性灰白——臂的灰白外壳与灰白物体撞色，是本方案唯一的结构性漏标来源。
「计数值大小不参与判决」由 `tests/lightweight/test_arm_mask.py` 钉死。

### GT seg_id 到像素集合的约定（用户拍板，逐字执行）

| 集合 | 定义 |
|---|---|
| 机械臂 | `setup/segmentation_excluded` 中 `reason == "robot_link"` 的 link |
| 背景 | `setup/segmentation_excluded` 中 `reason == "background_prop"`（`table-workspace`、`ground`）+ seg_id 0 |
| 物体 | `setup/segmentation_objects` 里的 actor / link（只用于并入混合列与验证尺子，不再单独成列） |

`segmentation_objects` 里还有一项 `kind == "tcp"`（`panda_hand_tcp`）——它是夹爪的工具中心点，
一个不参与渲染的虚拟坐标点，语义上属于机器人而不是任务物体，因此**归到机械臂**而不是
物体。实测它的 seg_id 从未在 segmentation 图里出现过，这条分支是纯防御。

任何在图里出现、却不属于上面任何一类的 seg id 都会走「归物体」兜底（进混合列）并被
`uncovered_mask` 单独计数，详见 `labels_from_segmentation`。

### 为什么是「精确颜色」而不是直方图 bin 或高斯

因为它一个超参都不需要。ManiSkill 的渲染确定性极强（v3 实测 86% 的像素跨 291 帧逐位
重复），颜色本身就是天然的离散量，按 bin 归并或拟合成高斯反而要引入「bin 数」
「协方差正则」这类拍脑袋的量。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

import h5py
import numpy as np


# 类编号。预测标签图与颜色表列共用一套：0 = 纯背景、1 = 背景∪物体混合、2 = 机械臂。
# GT 验证尺子（labels_from_segmentation）里 1 号位仍是「物体」——CLASS_OBJECT 只用于
# GT 侧，与颜色表的 CLASS_MIX 数值相同但语义不同，两个名字刻意分开以免读串。
CLASS_BACKGROUND = 0
CLASS_MIX = 1  # 颜色表列 / 预测标签：背景∪物体混合（物体不单独可见）
CLASS_OBJECT = 1  # 仅 GT 尺子标签：物体（验证与 GT 出图用，不再是颜色表的列）
CLASS_ARM = 2
CLASS_UNKNOWN = -1
CLASS_NAMES = ("background", "bg_object_mix", "arm")
NUM_CLASSES = 3

# 落盘的模型文件里必须带上这个，口径变了立刻能认出来；v4 三类表的 npz 在 load 时报错
# ⚠ 这个字符串是**已落盘 color_model.npz 里存着的值**，加载时逐字校验（见 ColorModel.load）。
# 名字里的 v4.1 是历史版本号，与当前目录结构无关；改动它等于作废现有像素表、必须重新拟合。
COLOR_MODEL_SCHEMA_VERSION = "color-model-v4.1-2dist"


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
    excluded = setup_group.get("segmentation_excluded")
    objects = setup_group.get("segmentation_objects")
    if not isinstance(excluded, h5py.Group) or not isinstance(objects, h5py.Group):
        raise ValueError(
            "setup 下缺少 segmentation_excluded / segmentation_objects，无法建立三类映射："
            "该 h5 生成时没落 GT segmentation，seg_id 枚举表不存在"
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
            raise ValueError(f"segmentation_excluded/{name} 的 reason 未知：{reason}")

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

    `setup/segmentation_objects` 与 `segmentation_excluded` 是 `reset()` 那一刻对
    `segmentation_id_map` 的快照，**episode 运行中动态创建的对象不在里面**。实测有
    5 个任务会出现这种 id，逐帧目视核对过，全是任务的目标 / 路径标记物：
    InsertPeg 箱顶的插孔标记、PickHighlight 的绿色高亮块、SwingXtimes 的靶心圆盘、
    PatternLock 的图案连线节点（id 涨到 572）、RouteStick 的路线曲线（涨到 710）。

    机器人各 link 与桌面地面这些背景道具都是 `reset()` 之前就建好的、已被完整枚举，
    因此**运行中新出现的 id 必定是任务相关的可见物体**，归「物体」既符合语义，也让
    它们的颜色进入混合列——按判别规则，混合列见过的颜色永远不会被判成机械臂，
    正对应「绝不误标其他物体」的宗旨。

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
        # 下面两道守卫是纯支撑三段式判据的前提。旧的 argmax 写法靠数值比较隐式兜底，
        # 现在规则只看支撑集，前提破了会**静默判错**而不是报错，必须显式 fail-loud。
        if self.counts.size and not np.all(self.counts.sum(axis=1) > 0):
            bad = int(np.flatnonzero(self.counts.sum(axis=1) <= 0)[0])
            raise ValueError(
                f"颜色表存在三列全零行（第 {bad} 行，颜色 {int(self.colors[bad])}）："
                "这种行会被静默判成混合。表里只该收录真实出现过的颜色"
            )
        seen_background = self.counts[:, CLASS_BACKGROUND] > 0
        seen_mix = self.counts[:, CLASS_MIX] > 0
        if not np.all(seen_mix[seen_background]):
            bad = int(np.flatnonzero(seen_background & ~seen_mix)[0])
            raise ValueError(
                f"颜色表破坏了 supp(N₀) ⊆ supp(N₁)（第 {bad} 行，颜色 "
                f"{int(self.colors[bad])}：背景列 > 0 但混合列 = 0）："
                "拟合必须重叠计数（背景像素同时进列 0 与列 1），"
                "否则「判背景」与「判臂」不再互斥，整条判别规则失效"
            )

    @property
    def class_pixel_totals(self) -> np.ndarray:
        return self.counts.sum(axis=0)

    def classify(self, rgb: np.ndarray) -> np.ndarray:
        """(H, W, 3) uint8 → (H, W) int8 标签图；没见过的颜色给 CLASS_UNKNOWN。

        纯支撑三段式判据（模块 docstring 有完整表格与来历），**只看每列见过没见过，
        计数的数值大小不参与，没有任何开关也没有任何阈值**：

        1. **查表**：`searchsorted` 定位 + 命中校验，未命中直接 `CLASS_UNKNOWN`；
        2. **定类**：`N₀ > 0` 判背景；`N₁ = 0 且 N₂ > 0` 判臂；其余判混合。

        三段互斥且穷尽由 `__post_init__` 的两道守卫保证（每行至少一列 > 0、
        `supp(N₀) ⊆ supp(N₁)`），所以写成「先铺默认值再逐条覆盖」是安全的，
        两条覆盖不会互相打架。

        判臂那条为什么是「无臂场景里从未出现过」：无臂场景里出现过的颜色无法排除
        属于物体，而宗旨是「绝不误标物体、允许少量机械臂没被标进去」，必须往保守
        方向倒。（v4 三类表时代的实测背景：不带这条约束时的物体误标全是被夹爪按压的
        白色按钮顶面、灰白盒子高光——与灰白臂壳在 24 位 RGB 上完全同色，形态学救不了，
        只能在分类阶段挡掉。）
        """
        packed = pack_rgb(rgb)
        flat = packed.ravel()
        index = np.searchsorted(self.colors, flat)
        # searchsorted 可能给出 N（比表里所有颜色都大），先夹住再验命中
        clipped = np.clip(index, 0, self.colors.size - 1)
        hit = self.colors[clipped] == flat
        picked = self.counts[clipped]
        winner = np.full(flat.shape, CLASS_MIX, dtype=np.int8)
        winner[picked[:, CLASS_BACKGROUND] > 0] = CLASS_BACKGROUND
        winner[(picked[:, CLASS_MIX] == 0) & (picked[:, CLASS_ARM] > 0)] = CLASS_ARM
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
    """把若干 (rgb, GT 三类标签) 帧统计成一张两分布 + 臂的颜色表。

    输入标签是 GT 尺子的三类（背景 / 物体 / 机械臂），但落表刻意做**重叠计数**：
    背景像素同时计入列 0（纯背景）与列 1（背景∪物体混合），物体像素只计入列 1，
    臂像素只计入列 2。列 1 就是「无臂场景」能观察到的全部像素——物体在其中占多少
    （类先验）对模型不可见。

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
    selectors = (
        (CLASS_BACKGROUND, labels == CLASS_BACKGROUND),
        (CLASS_MIX, (labels == CLASS_BACKGROUND) | (labels == CLASS_OBJECT)),
        (CLASS_ARM, labels == CLASS_ARM),
    )
    for column, selected in selectors:
        if selected.any():
            counts[:, column] = np.bincount(
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
