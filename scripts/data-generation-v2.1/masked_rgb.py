#!/usr/bin/env python3
"""纯色棕遮蔽图 ``front_rgb_masked`` 的生成与落盘（masked-rgb-v2）。

这张图的用途是给出一张**可控的干净底图**：把机械臂整根刷成单一棕色，画面里与机器人有关的
东西只剩夹爪指尖那一小块黑色接触面。做 flow 目视检查时，机械臂不会在画面里晃来晃去抢戏，
下游用它也不会被臂杆外观干扰。

### 与 v1（``scripts/data-generation-v2/``）的三处口径差别

| 方面 | v1（masked-rgb-v1） | v2.1（masked-rgb-v2） |
|---|---|---|
| 机器人 | 涂全部 link，但**整根手指 link 保留原像素** | 涂全部 link，只在手指 link 内**按像素**豁免黑色指尖 |
| panda_stick | 保留整个 ``panda_hand``（手掌连着棍一起留下） | **不保留任何东西**，整个机器人连棍一起涂掉 |
| 桌面 | ``table-workspace`` 涂成纯棕 | **不涂**，木纹原样保留 |

### 白名单，不是黑名单

只有一类东西会被涂棕：**机器人 articulation 下的 link**。其余一律原样保留——桌面
``table-workspace``、地面 ``ground``、全部任务物体、以及任何没认出来的东西。之所以坚持白名单
而不是「除了 XX 都涂」，是因为黑名单遇到新出现的未知物体会默认涂掉它，而白名单遇到未知物体
默认保留。前者会静默毁掉数据，后者最多是少涂一块，肉眼一看就知道。

### 「gripper 头部的黑色部分」为什么只能按像素判定

``panda_v3.urdf`` 里 ``panda_leftfinger`` 只有**一个** visual（``franka_description/meshes/
visual/finger.glb``），白色指身与黑色指尖是同一个 mesh 上的两种材质；而 ManiSkill 的
segmentation 是 **link 级**的。也就是说 seg id 这一层根本切不开指身与指尖，唯一可行的粒度
就是「先按 seg id 圈出手指 link，再在这块像素里按颜色挑黑的」。

阈值取三通道均值 ``≤ 100``，依据是在既有 16 任务产物上实测的手指像素亮度分布：**暗簇落在
38–59、亮簇落在 142–231，中间 60–141 是完全的空档**。阈值落在空档正中，往两边挪 40 个灰度级
结果都不变，不是拍脑袋定的。判定用整数和 ``R+G+B ≤ 3×阈值`` 算，与「均值 ≤ 阈值」严格等价，
省掉一次浮点除法。

黑色豁免**只作用于手指 link**，不是对整个机器人做亮度判定：手掌 ``panda_hand`` 与腕部相机
支架上也有几块黑色方块，那些不属于「gripper 头部的接触面」，按口径应当一起涂掉。

### 黑色豁免集的解析规则

```
若 agent.finger1_link 存在（有手指的机器人，如 panda_wristcam）：
    豁免 = {finger1_link, finger2_link, finger1pad_link, finger2pad_link} 里非 None 的那些
否则（无手指的机器人，如 panda_stick）：
    豁免 = 空集，整个机器人全涂
```

两条实测依据，决定了上面为什么必须这么写：

- **``panda_stick`` 的那根棍挂在 ``panda_hand`` 上**：``panda_stick.urdf`` 里 ``panda_hand``
  有两个 visual，手掌 mesh 加一个 ``radius=0.008 / length=0.1`` 的圆柱。segmentation 是
  **link 级**的，棍与手掌同属一个 link，因此想单独留棍是做不到的。v1 的做法是连手掌一起留，
  v2.1 按「对 robot stick 就不管了全部 mask」的口径反过来处理：连棍一起涂掉。
- **``panda_leftfinger_pad`` / ``rightfinger_pad`` 在 ``panda_v3.urdf`` 里根本不存在**，
  ``agent.finger1pad_link`` 是 ``None``。规则里留着它们纯粹是为了 urdf 换版后不失效，
  当前是空操作。

解析一律**优先走对象身份**而不是 ``"panda_"`` 字符串前缀：``camera_base_link`` / ``camera_link``
也是真实的机器人 link 却不带该前缀，用前缀规则会把腕部相机支架整个漏掉。名字兜底则必须限定在
「所属 articulation 是机器人」的 link 里找，否则任务物体一旦重名就会被误豁免。每一项的解析途径
都写进 h5 的 ``resolved_by``——ManiSkill 升级后对象身份这条路静默失效时，那个字段就是唯一的探针。

### 为什么涂色发生在 close() 而不是 step()

见 ``record_wrapper_v2.py``。一句话：热路径零开销，规划器那 1 秒墙钟预算不受任何影响。

### h5 落点

``timestep_<k>/obs/front_rgb_masked``，与 ``front_rgb`` 并列、同 dtype 同 shape、不压缩。
episode 级元数据在 ``setup/masked_rgb_*``，``painted`` / ``kept`` / ``black_exempt`` 三个字典
都写：白名单机制下，日后要回答的审计问题是「桌面到底涂没涂」「左手指是靠对象身份找到的还是
退回字符串了」，只记涂掉的那一部分答不了。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import h5py
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 对象枚举语义只允许有一份：直接复用 flow_tracker 的辅助函数，避免两处口径漂移
from flow_tracker import (  # noqa: E402
    _articulation_of,
    _make_key,
    _object_name,
    _timestep_names,
    _write_object_entry,
)


MASKED_RGB_SCHEMA_VERSION = "masked-rgb-v2"

# 桌面棕色区的实测中位 RGB：跨 MoveCube / ButtonUnmask / VideoPlaceOrder 与跨帧完全一致。
# v2.1 已经不涂桌面了，但涂色仍沿用这个值——机械臂在画面里几乎总是压在桌面上，用桌面的中位色
# 涂它，涂掉的部分会融进木纹底色而不是形成第二块扎眼的色板。
DEFAULT_PAINT_COLOR = (179, 107, 67)

# 黑色指尖的判定阈值：手指 link 内三通道均值 ≤ 该值的像素豁免涂色。
# 实测手指像素亮度双峰，暗簇 38–59、亮簇 142–231，中间 60–141 全空，100 落在空档正中。
DEFAULT_BLACK_LUMINANCE_MAX = 100

# 有手指的机器人：这四个属性对应的 link 内，黑色像素豁免涂色。
# pad 两项在 panda_v3.urdf（panda_wristcam 用的那份）里根本不存在，getattr 会拿到 None，
# 保留它们纯粹是为了 urdf 换版后规则不失效，当前是空操作。
GRIPPER_BLACK_SPECS = (
    ("finger1_link", "panda_leftfinger", "gripper_finger"),
    ("finger2_link", "panda_rightfinger", "gripper_finger"),
    ("finger1pad_link", "panda_leftfinger_pad", "gripper_finger_pad"),
    ("finger2pad_link", "panda_rightfinger_pad", "gripper_finger_pad"),
)

# 涂色原因
REASON_ROBOT_LINK = "robot_link"
REASON_ROBOT_LINK_BLACK_EXEMPT = "robot_link_black_exempt"

# 保留原因
REASON_NOT_WHITELISTED = "not_whitelisted"

# 黑色豁免原因
REASON_GRIPPER_FINGER = "gripper_finger"
REASON_GRIPPER_FINGER_PAD = "gripper_finger_pad"

# 解析途径，写进 setup/masked_rgb_black_exempt/<key>/resolved_by
RESOLVED_BY_IDENTITY = "object_identity"
RESOLVED_BY_NAME = "name_fallback"


@dataclass
class PaintedObject:
    """被涂成纯棕色的对象。

    ``reason`` 为 ``robot_link_black_exempt`` 的条目仍然属于涂色集，只是它的黑色像素会被
    逐像素豁免——整块 link 并没有被整体保留，这与 v1 的语义不同。
    """

    key: str
    original_name: str
    seg_id: int
    kind: str  # "actor" / "link"
    articulation_name: str
    reason: str


@dataclass
class KeptObject:
    """保留原始像素的对象（白名单之外的一切：桌面、地面、任务物体）。"""

    key: str
    original_name: str
    seg_id: int
    kind: str
    articulation_name: str
    reason: str


@dataclass
class BlackExemptObject:
    """参与黑色像素豁免的机器人 link。"""

    key: str
    original_name: str
    seg_id: int
    kind: str
    articulation_name: str
    reason: str
    resolved_by: str


def _lookup_by_identity(id_map: Mapping[int, Any], handle: Any) -> Optional[int]:
    """按对象身份在 segmentation_id_map 里反查 seg id。"""
    if handle is None:
        return None
    for seg_id, obj in id_map.items():
        if obj is handle:
            return int(seg_id)
    return None


def _lookup_robot_link_by_name(
    id_map: Mapping[int, Any], name: str, robot_name: Optional[str]
) -> Optional[int]:
    """按名字反查 seg id，**但只在机器人自己的 link 里找**。

    限定范围是必需的：一旦某个任务物体恰好叫 ``panda_leftfinger``，不限定就会把它误当成夹爪
    豁免掉。
    """
    if robot_name is None:
        return None
    for seg_id, obj in id_map.items():
        articulation = _articulation_of(obj)
        if articulation is None:
            continue
        if _object_name(articulation) != robot_name:
            continue
        if _object_name(obj) == name:
            return int(seg_id)
    return None


class MaskPainter:
    """按 episode 冻结「该涂哪些 seg id、哪些 seg id 内的黑色像素豁免」，并把单帧 rgb 涂成遮蔽图。

    冻结发生在 ``reset()`` 之后：那时场景已经建好，而枚举只读 ``segmentation_id_map`` 与
    ``agent`` 的几个属性，不消费任何随机数，也不改动仿真状态。
    """

    def __init__(
        self,
        env_unwrapped: Any,
        paint_color: Sequence[int] = DEFAULT_PAINT_COLOR,
        black_luminance_max: int = DEFAULT_BLACK_LUMINANCE_MAX,
    ) -> None:
        color = np.asarray(paint_color, dtype=np.uint8)
        if color.shape != (3,):
            raise ValueError(f"paint_color 必须是 3 元 RGB，收到 {paint_color!r}")
        if not 0 <= int(black_luminance_max) <= 255:
            raise ValueError(
                f"black_luminance_max 必须落在 [0, 255]，收到 {black_luminance_max!r}"
            )
        self.paint_color = color
        self.black_luminance_max = int(black_luminance_max)
        self.painted: list[PaintedObject] = []
        self.kept: list[KeptObject] = []
        self.black_exempt: list[BlackExemptObject] = []
        # 逐帧累计的像素计数。只进日志与生成报告，不写 h5——它是「黑色指尖到底留住了没有」
        # 的唯一自动信号：豁免像素恒为 0 就说明阈值或 seg id 解析出了问题，光看涂色总数
        # 是发现不了的（手指本来就只占几十个像素）。
        self.painted_pixel_total = 0
        self.black_exempt_pixel_total = 0
        self._freeze(env_unwrapped)
        self._paint_ids = np.asarray(
            sorted(item.seg_id for item in self.painted), dtype=np.int64
        )
        self._black_exempt_ids = np.asarray(
            sorted(item.seg_id for item in self.black_exempt), dtype=np.int64
        )
        # 三通道和的阈值，与「均值 ≤ black_luminance_max」严格等价
        self._black_sum_max = 3 * self.black_luminance_max

    # ------------------------------------------------------------------
    # 一、枚举与冻结
    # ------------------------------------------------------------------
    def _resolve_black_exempt(
        self, id_map: Mapping[int, Any], agent: Any, robot_name: Optional[str]
    ) -> dict[int, tuple[str, str]]:
        """解析出「黑色像素豁免涂色」的机器人部位，返回 seg_id -> (reason, resolved_by)。

        无手指的机器人（panda_stick）直接返回空字典：按 v2.1 口径它整个都涂掉，连棍带手掌，
        **空集是合法结果，不是错误**。有手指却一个都解析不到才是真出了问题。
        """
        if getattr(agent, "finger1_link", None) is None:
            return {}

        exempt: dict[int, tuple[str, str]] = {}
        for attr, fallback_name, reason in GRIPPER_BLACK_SPECS:
            handle = getattr(agent, attr, None)
            seg_id = _lookup_by_identity(id_map, handle)
            resolved_by = RESOLVED_BY_IDENTITY
            if seg_id is None:
                seg_id = _lookup_robot_link_by_name(id_map, fallback_name, robot_name)
                resolved_by = RESOLVED_BY_NAME
            if seg_id is None:
                # 这一项在当前 urdf 里不存在（如 panda_v3 没有 finger pad），不是错误
                continue
            exempt[seg_id] = (reason, resolved_by)

        if not exempt:
            raise ValueError(
                "机器人有 finger1_link 却一个手指 link 都没解析到，"
                "黑色豁免口径不成立，拒绝生成 masked 图。"
            )
        return exempt

    def _freeze(self, env_unwrapped: Any) -> None:
        id_map: Mapping[int, Any] = (
            getattr(env_unwrapped, "segmentation_id_map", {}) or {}
        )
        if not id_map:
            raise ValueError("segmentation_id_map 为空，无法确定涂色范围")
        if 0 in id_map:
            # seg id 0 是背景/无实体。它要是进了 id_map，说明 ManiSkill 的 id 口径变了，
            # 继续往下走的后果是整片背景被涂棕。宁可在这里炸掉。
            raise ValueError("segmentation_id_map 里出现了 seg_id 0，涂色口径不成立")

        agent = getattr(env_unwrapped, "agent", None)
        robot = getattr(agent, "robot", None)
        robot_name = _object_name(robot) if robot is not None else None

        exempt = self._resolve_black_exempt(id_map, agent, robot_name)

        for raw_seg_id, obj in sorted(id_map.items()):
            seg_id = int(raw_seg_id)
            name = _object_name(obj)
            articulation = _articulation_of(obj)
            is_link = articulation is not None
            kind = "link" if is_link else "actor"
            articulation_name = _object_name(articulation) if is_link else ""
            key = _make_key(name, seg_id)

            # 1. 机器人 link：判据是「所属 articulation 是不是机器人」，不是名字前缀。
            #    手指 link 同样进涂色集，只是额外登记进 black_exempt，涂的时候黑像素跳过。
            if is_link and robot_name is not None and articulation_name == robot_name:
                if seg_id in exempt:
                    reason, resolved_by = exempt[seg_id]
                    self.painted.append(
                        PaintedObject(
                            key,
                            name,
                            seg_id,
                            kind,
                            articulation_name,
                            REASON_ROBOT_LINK_BLACK_EXEMPT,
                        )
                    )
                    self.black_exempt.append(
                        BlackExemptObject(
                            key,
                            name,
                            seg_id,
                            kind,
                            articulation_name,
                            reason,
                            resolved_by,
                        )
                    )
                else:
                    self.painted.append(
                        PaintedObject(
                            key, name, seg_id, kind, articulation_name, REASON_ROBOT_LINK
                        )
                    )
                continue

            # 2. 白名单之外一律原样保留：桌面、ground、任务物体、以及任何没认出来的东西
            self.kept.append(
                KeptObject(
                    key,
                    name,
                    seg_id,
                    kind,
                    articulation_name,
                    REASON_NOT_WHITELISTED,
                )
            )

        if not self.painted:
            raise ValueError("涂色集为空：一个机器人 link 都没认出来")

    # ------------------------------------------------------------------
    # 二、单帧涂色
    # ------------------------------------------------------------------
    def paint(self, rgb: Any, segmentation: Any) -> np.ndarray:
        """把一帧 rgb 里属于涂色集的像素置成纯棕色，返回新数组。

        手指 link 里三通道均值 ``≤ black_luminance_max`` 的像素从涂色集里扣掉——那就是夹爪
        头部的黑色接触面，是全画面唯一保留下来的机器人部位。

        **绝不就地改**：传进来的 ``rgb`` 正是父类要原样写盘的 ``front_rgb``，就地改会直接
        破坏「只增不改」——那是这条链路的生命线。
        """
        rgb_array = np.asarray(rgb)
        if rgb_array.ndim != 3 or rgb_array.shape[2] != 3:
            raise ValueError(f"front_rgb 形状非法：{rgb_array.shape}")
        if rgb_array.dtype != np.uint8:
            raise ValueError(f"front_rgb dtype 非法：{rgb_array.dtype}，应为 uint8")

        seg_2d = np.squeeze(np.asarray(segmentation))
        if seg_2d.ndim != 2:
            raise ValueError(f"segmentation squeeze 后不是 2D：{seg_2d.shape}")
        if seg_2d.shape != rgb_array.shape[:2]:
            raise ValueError(
                f"segmentation 与 rgb 分辨率不一致：{seg_2d.shape} vs {rgb_array.shape[:2]}"
            )

        masked = rgb_array.copy()
        if self._paint_ids.size:
            paint_mask = np.isin(seg_2d, self._paint_ids)
            if self._black_exempt_ids.size:
                # uint16 求和：255×3 = 765 不会溢出，全整数运算，无浮点除法
                luminance_sum = rgb_array.astype(np.uint16).sum(axis=-1)
                exempt_mask = np.isin(seg_2d, self._black_exempt_ids) & (
                    luminance_sum <= self._black_sum_max
                )
                paint_mask &= ~exempt_mask
                self.black_exempt_pixel_total += int(exempt_mask.sum())
            self.painted_pixel_total += int(paint_mask.sum())
            masked[paint_mask] = self.paint_color
        return masked

    # ------------------------------------------------------------------
    # 三、setup 元数据
    # ------------------------------------------------------------------
    @property
    def meta(self) -> dict[str, Any]:
        """写 setup/ 需要的元数据快照。"""
        return {
            "schema_version": MASKED_RGB_SCHEMA_VERSION,
            "paint_color": self.paint_color,
            "black_luminance_max": self.black_luminance_max,
            "painted": list(self.painted),
            "kept": list(self.kept),
            "black_exempt": list(self.black_exempt),
        }


# ----------------------------------------------------------------------
# 四、写盘
# ----------------------------------------------------------------------
def write_masked_rgb_setup(setup_group: h5py.Group, meta: Mapping[str, Any]) -> None:
    """把 masked rgb 的 episode 级元数据写进已存在的 setup group。"""
    setup_group.create_dataset(
        "masked_rgb_schema_version",
        data=meta["schema_version"],
        dtype=h5py.string_dtype(encoding="utf-8"),
    )
    setup_group.create_dataset(
        "masked_rgb_paint_color",
        data=np.asarray(meta["paint_color"], dtype=np.uint8),
    )
    setup_group.create_dataset(
        "masked_rgb_black_luminance_max",
        data=np.int64(meta["black_luminance_max"]),
    )

    painted_group = setup_group.create_group("masked_rgb_painted")
    for item in meta["painted"]:
        _write_object_entry(
            painted_group,
            item.key,
            {
                "original_name": item.original_name,
                "seg_id": item.seg_id,
                "kind": item.kind,
                "articulation_name": item.articulation_name,
                "reason": item.reason,
            },
        )

    kept_group = setup_group.create_group("masked_rgb_kept")
    for item in meta["kept"]:
        _write_object_entry(
            kept_group,
            item.key,
            {
                "original_name": item.original_name,
                "seg_id": item.seg_id,
                "kind": item.kind,
                "articulation_name": item.articulation_name,
                "reason": item.reason,
            },
        )

    # 空 group 也照写：panda_stick 任务的「豁免集为空」本身就是要记录的事实，
    # group 缺失与「有 group 但没条目」在审计时是两回事。
    black_group = setup_group.create_group("masked_rgb_black_exempt")
    for item in meta["black_exempt"]:
        _write_object_entry(
            black_group,
            item.key,
            {
                "original_name": item.original_name,
                "seg_id": item.seg_id,
                "kind": item.kind,
                "articulation_name": item.articulation_name,
                "reason": item.reason,
                "resolved_by": item.resolved_by,
            },
        )


def write_masked_rgb_groups(
    episode_group: h5py.Group,
    sources: Sequence[tuple[Any, Any]],
    painter: MaskPainter,
) -> int:
    """逐帧算、逐帧写进已存在的 ``timestep_<k>/obs/``，返回写入帧数。

    流式处理：算完一帧立刻落盘再丢掉，峰值只多占一张图（约 197 KB），而不是把整个 episode
    的遮蔽图先在内存里堆成一个列表（最长的 VideoPlaceOrder 有 1200 帧，那样要多占 236 MB）。
    """
    timestep_names = _timestep_names(episode_group)
    if len(timestep_names) != len(sources):
        raise ValueError(
            f"timestep 数量（{len(timestep_names)}）与 masked 源帧数（{len(sources)}）不一致"
        )

    setup_group = episode_group.get("setup")
    if not isinstance(setup_group, h5py.Group):
        raise ValueError("episode 下缺少 setup group，无法写入 masked_rgb 元数据")
    write_masked_rgb_setup(setup_group, painter.meta)

    for name, (rgb, segmentation) in zip(timestep_names, sources):
        obs_group = episode_group[name].get("obs")
        if not isinstance(obs_group, h5py.Group):
            raise ValueError(f"{name} 下缺少 obs group")
        if "front_rgb_masked" in obs_group:
            # 拒绝覆盖：走到这里说明同一个 episode 被写了两次，静默覆盖会掩盖真正的问题
            raise ValueError(f"{name}/obs 下已存在 front_rgb_masked，拒绝覆盖")
        obs_group.create_dataset(
            "front_rgb_masked", data=painter.paint(rgb, segmentation)
        )

    return len(timestep_names)
