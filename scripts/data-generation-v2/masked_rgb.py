#!/usr/bin/env python3
"""纯色棕遮蔽图 ``front_rgb_masked`` 的生成与落盘（masked-rgb-v1）。

这张图的用途是给出一张**可控的干净底图**：把机械臂与桌面刷成单一棕色，只留下夹爪的接触部位
与任务物体。做 flow 目视检查时箭头不会淹没在木纹里，下游用它也不会被桌面纹理与臂杆外观干扰。

### 白名单，不是黑名单

只有两类东西会被涂棕：

1. **机器人 articulation 下的 link**（减去保留集，见下）；
2. **桌面 actor**（``table-workspace``）。

其余一律原样保留——地面 ``ground``、全部任务物体、以及任何没认出来的东西。之所以坚持白名单
而不是「除了 XX 都涂」，是因为黑名单遇到新出现的未知物体会默认涂掉它，而白名单遇到未知物体
默认保留。前者会静默毁掉数据，后者最多是少涂一块，肉眼一看就知道。

### 保留集的解析规则

```
若 agent.finger1_link 存在（有手指的机器人，如 panda_wristcam）：
    保留 = {finger1_link, finger2_link, finger1pad_link, finger2pad_link} 里非 None 的那些
否则（无手指的机器人，如 panda_stick）：
    保留 = {tcp 所在 joint 的 parent_link}
```

两条实测依据，决定了上面为什么必须这么写：

- **``panda_hand_tcp`` 恒为 0 像素**。urdf 里它确实有 ``<visual>``，但渲染不出任何像素
  （查既有产物里 ``flow/panda_hand_tcp__*`` 的 ``seg_pixel_count``，全 0）。所以拿 tcp 本身
  当「stick 末端」是彻底的空操作。
- **``panda_stick`` 的那根棍挂在 ``panda_hand`` 上**：``panda_stick.urdf`` 里 ``panda_hand``
  有两个 visual，手掌 mesh 加一个 ``radius=0.008 / length=0.1`` 的圆柱。segmentation 是
  **link 级**的，棍与手掌同属一个 link，因此「保留 stick 末端」在实现上唯一可行的粒度就是
  保留整个 ``panda_hand``，手掌会连着棍一起留下。

解析一律**优先走对象身份**而不是 ``"panda_"`` 字符串前缀：``camera_base_link`` / ``camera_link``
也是真实的机器人 link 却不带该前缀，用前缀规则会把腕部相机支架整个漏掉。名字兜底则必须限定在
「所属 articulation 是机器人」的 link 里找，否则任务物体一旦重名就会被误保留。每一项的解析途径
都写进 h5 的 ``resolved_by``——ManiSkill 升级后对象身份这条路静默失效时，那个字段就是唯一的探针。

### 为什么涂色发生在 close() 而不是 step()

见 ``record_wrapper_v2.py``。一句话：热路径零开销，规划器那 1 秒墙钟预算不受任何影响。

### h5 落点

``timestep_<k>/obs/front_rgb_masked``，与 ``front_rgb`` 并列、同 dtype 同 shape、不压缩。
episode 级元数据在 ``setup/masked_rgb_*``，``painted`` 与 ``kept`` 两个字典都写：白名单机制下，
日后要回答的审计问题是「``ground`` 到底涂没涂」「左手指是靠对象身份找到的还是退回字符串了」，
只记涂掉的那一半答不了。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

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


MASKED_RGB_SCHEMA_VERSION = "masked-rgb-v1"

# 桌面棕色区的实测中位 RGB：跨 MoveCube / ButtonUnmask / VideoPlaceOrder 与跨帧完全一致。
# 用它而不是随便挑一个「标准棕」，是为了让涂掉的机械臂无缝融进涂平的桌面，
# 而不是在画面里形成第二块颜色不同的色板。
DEFAULT_PAINT_COLOR = (179, 107, 67)

# 桌面 actor 名。ManiSkill 的 TableSceneBuilder 固定用这个名字，本仓库 16 个任务全部用它，
# 没有任何一个自定义了桌面。
DEFAULT_TABLE_NAMES = frozenset({"table-workspace"})

# 有手指的机器人：这四个属性对应的 link 保留原像素。
# pad 两项在 panda_v3.urdf（panda_wristcam 用的那份）里根本不存在，getattr 会拿到 None，
# 保留它们纯粹是为了 urdf 换版后规则不失效，当前是空操作。
GRIPPER_PRESERVE_SPECS = (
    ("finger1_link", "panda_leftfinger", "gripper_finger"),
    ("finger2_link", "panda_rightfinger", "gripper_finger"),
    ("finger1pad_link", "panda_leftfinger_pad", "gripper_finger_pad"),
    ("finger2pad_link", "panda_rightfinger_pad", "gripper_finger_pad"),
)

# 无手指的机器人（panda_stick）：保留 tcp 所在 joint 的 parent_link，实测就是 panda_hand
STICK_END_FALLBACK_NAME = "panda_hand"

# 涂色原因
REASON_ROBOT_LINK = "robot_link"
REASON_TABLE_ACTOR = "table_actor"

# 保留原因
REASON_GRIPPER_FINGER = "gripper_finger"
REASON_GRIPPER_FINGER_PAD = "gripper_finger_pad"
REASON_STICK_END_LINK = "stick_end_link"
REASON_NOT_WHITELISTED = "not_whitelisted"

# 解析途径，写进 setup/masked_rgb_kept/<key>/resolved_by
RESOLVED_BY_IDENTITY = "object_identity"
RESOLVED_BY_NAME = "name_fallback"
RESOLVED_BY_ABSENT = "absent"


@dataclass
class PaintedObject:
    """被涂成纯棕色的对象。"""

    key: str
    original_name: str
    seg_id: int
    kind: str  # "actor" / "link"
    articulation_name: str
    reason: str


@dataclass
class KeptObject:
    """保留原始像素的对象。"""

    key: str
    original_name: str
    seg_id: int
    kind: str
    articulation_name: str
    reason: str
    resolved_by: str  # 只有显式保留项才有意义，白名单外的对象写空串


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
    保留下来。
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


def _tcp_parent_link(agent: Any) -> Any:
    """取 tcp 所在 joint 的 parent_link；任何一环拿不到都返回 None。"""
    tcp = getattr(agent, "tcp", None)
    if tcp is None:
        return None
    joint = getattr(tcp, "joint", None)
    if joint is None:
        return None
    return getattr(joint, "parent_link", None)


class MaskPainter:
    """按 episode 冻结「该涂哪些 seg id」，并把单帧 rgb 涂成遮蔽图。

    冻结发生在 ``reset()`` 之后：那时场景已经建好，而枚举只读 ``segmentation_id_map`` 与
    ``agent`` 的几个属性，不消费任何随机数，也不改动仿真状态。
    """

    def __init__(
        self,
        env_unwrapped: Any,
        paint_color: Sequence[int] = DEFAULT_PAINT_COLOR,
        table_names: Iterable[str] = DEFAULT_TABLE_NAMES,
    ) -> None:
        color = np.asarray(paint_color, dtype=np.uint8)
        if color.shape != (3,):
            raise ValueError(f"paint_color 必须是 3 元 RGB，收到 {paint_color!r}")
        self.paint_color = color
        self.table_names = frozenset(table_names)
        self.painted: list[PaintedObject] = []
        self.kept: list[KeptObject] = []
        self._freeze(env_unwrapped)
        self._paint_ids = np.asarray(
            sorted(item.seg_id for item in self.painted), dtype=np.int64
        )

    # ------------------------------------------------------------------
    # 一、枚举与冻结
    # ------------------------------------------------------------------
    def _resolve_preserved(
        self, id_map: Mapping[int, Any], agent: Any, robot_name: Optional[str]
    ) -> dict[int, tuple[str, str]]:
        """解析出「保留原像素」的机器人部位，返回 seg_id -> (reason, resolved_by)。"""
        preserved: dict[int, tuple[str, str]] = {}

        has_fingers = getattr(agent, "finger1_link", None) is not None
        if has_fingers:
            specs = [
                (getattr(agent, attr, None), fallback_name, reason)
                for attr, fallback_name, reason in GRIPPER_PRESERVE_SPECS
            ]
        else:
            # 无手指的机器人（panda_stick）：棍的几何挂在 tcp 的父 link（panda_hand）上
            specs = [
                (_tcp_parent_link(agent), STICK_END_FALLBACK_NAME, REASON_STICK_END_LINK)
            ]

        for handle, fallback_name, reason in specs:
            seg_id = _lookup_by_identity(id_map, handle)
            resolved_by = RESOLVED_BY_IDENTITY
            if seg_id is None:
                seg_id = _lookup_robot_link_by_name(id_map, fallback_name, robot_name)
                resolved_by = RESOLVED_BY_NAME
            if seg_id is None:
                # 这一项在当前 urdf 里不存在（如 panda_v3 没有 finger pad），不是错误
                continue
            preserved[seg_id] = (reason, resolved_by)

        if not preserved:
            raise ValueError(
                "保留集解析为空：既没找到夹爪手指，也没找到 stick 末端 link。"
                "涂色口径不成立，拒绝生成 masked 图。"
            )
        return preserved

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

        preserved = self._resolve_preserved(id_map, agent, robot_name)

        for raw_seg_id, obj in sorted(id_map.items()):
            seg_id = int(raw_seg_id)
            name = _object_name(obj)
            articulation = _articulation_of(obj)
            is_link = articulation is not None
            kind = "link" if is_link else "actor"
            articulation_name = _object_name(articulation) if is_link else ""
            key = _make_key(name, seg_id)

            # 1. 显式保留的机器人部位
            if seg_id in preserved:
                reason, resolved_by = preserved[seg_id]
                self.kept.append(
                    KeptObject(
                        key, name, seg_id, kind, articulation_name, reason, resolved_by
                    )
                )
                continue

            # 2. 机器人 link：判据是「所属 articulation 是不是机器人」，不是名字前缀
            if is_link and robot_name is not None and articulation_name == robot_name:
                self.painted.append(
                    PaintedObject(
                        key, name, seg_id, kind, articulation_name, REASON_ROBOT_LINK
                    )
                )
                continue

            # 3. 桌面：必须是 actor（articulation is None）且名字在表里
            if not is_link and name in self.table_names:
                self.painted.append(
                    PaintedObject(key, name, seg_id, kind, "", REASON_TABLE_ACTOR)
                )
                continue

            # 4. 白名单之外一律原样保留：ground、任务物体、以及任何没认出来的东西
            self.kept.append(
                KeptObject(
                    key,
                    name,
                    seg_id,
                    kind,
                    articulation_name,
                    REASON_NOT_WHITELISTED,
                    "",
                )
            )

        if not self.painted:
            raise ValueError("涂色集为空：既没认出机器人 link，也没认出桌面")

    # ------------------------------------------------------------------
    # 二、单帧涂色
    # ------------------------------------------------------------------
    def paint(self, rgb: Any, segmentation: Any) -> np.ndarray:
        """把一帧 rgb 里属于涂色集的像素置成纯棕色，返回新数组。

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
            masked[np.isin(seg_2d, self._paint_ids)] = self.paint_color
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
            "painted": list(self.painted),
            "kept": list(self.kept),
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
