#!/usr/bin/env python3
"""场景对象 → segmentation id 枚举表的冻结与落盘。

这张表回答一个问题：**一帧 segmentation 图里，某个像素值（seg_id）到底是机械臂、
任务物体，还是背景道具**。没有它，逐帧落盘的 GT segmentation 就只是一堆无法解释的
整数，颜色表拟合与实测都无从谈起。

### 表是怎么来的

``reset()`` 之后场景才建好，这时从 ``env.unwrapped.segmentation_id_map`` 一次性枚举
全场景对象并冻结：

- 所属 articulation 是机器人的 link → 剔除，原因记 ``robot_link``；
- 名字命中背景黑名单（桌面、地面）→ 剔除，原因记 ``background_prop``；
- 其余一律留作**任务物体**；
- TCP 属于机器人 articulation，会被第一条剔掉，再单独加回来标成 ``kind == "tcp"``
  （它是夹爪工具中心点，通常没有视觉体，语义上属机器人）。

枚举纯读 ``segmentation_id_map``，**不消费任何随机数**，因此挂上它不会扰动仿真与
规划的随机数顺序。

### 下游怎么用

``color_model.class_ids_from_setup`` 直接读本模块落盘的两个 group，把 seg_id 映射成
「机械臂 / 物体 / 背景」三类：``segmentation_excluded`` 里 ``reason == "robot_link"``
的进机械臂、``reason == "background_prop"`` 的进背景，``segmentation_objects`` 里除
``kind == "tcp"`` 外全进物体（tcp 归机械臂）。**认不出的 seg_id 一律兜底归物体**，
方向偏保守。

### 字典 key 的口径

key 一律是 ``<原名>__<seg_id>``。ManiSkill 保证 actor 名全局唯一，但 link 名只在自己
articulation 内唯一（两个 button articulation 可以各有一个同名 link），带上 segmentation
id 才能保证 h5 里的 group 名不撞。

⚠ 代价是 ``per_scene_id`` 每个 episode 都可能不同，所以 **key 跨 episode 不稳定**。
下游若要按物体跨 episode 聚合，必须走 ``segmentation_objects/<key>/original_name``
反查，不能直接把 key 当稳定主键。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import h5py
import numpy as np


# 背景道具黑名单：桌面、地面这类既不会动、也不是任务对象的东西
DEFAULT_BACKGROUND_NAMES = frozenset(
    {
        "table-workspace",
        "table",
        "ground",
        "floor",
    }
)

# 剔除原因，落进 segmentation_excluded/<key>/reason，口径永远可回溯。
# ⚠ 这两个字符串是 color_model.class_ids_from_setup 的判据，改动即破坏三类映射。
REASON_ROBOT_LINK = "robot_link"
REASON_BACKGROUND = "background_prop"


@dataclass
class SegObject:
    """一个保留下来的场景对象（任务物体或 TCP）。"""

    key: str  # h5 里的字典 key，形如 <原名>__<seg_id>
    original_name: str  # 未拼接的原始 actor.name / link.name
    seg_id: int  # per_scene_id，与分割图像素值一一对应
    kind: str  # "actor" / "link" / "tcp"
    articulation_name: str  # link/tcp 所属 articulation 名；actor 写空串


@dataclass
class ExcludedObject:
    """被剔除的对象（机器人 link 或背景道具），原因随之落盘。"""

    key: str
    original_name: str
    seg_id: int
    kind: str
    reason: str


def _object_name(obj: Any) -> str:
    name = getattr(obj, "name", None)
    if isinstance(name, str) and name:
        return name
    return "unknown"


def _articulation_of(obj: Any) -> Any:
    """取对象所属的 articulation；普通 actor 返回 None。

    用 duck typing 而非 isinstance，避免为了一个判断把 ManiSkill 的结构体类型 import 进来。
    """
    return getattr(obj, "articulation", None)


def _make_key(original_name: str, seg_id: int) -> str:
    return f"{original_name}__{seg_id}"


class SegIdTable:
    """按 episode 冻结的「场景对象 → segmentation id」枚举表。"""

    def __init__(
        self,
        env_unwrapped: Any,
        background_names: Iterable[str] = DEFAULT_BACKGROUND_NAMES,
    ) -> None:
        self.background_names = frozenset(background_names)
        self.objects: list[SegObject] = []
        self.excluded: list[ExcludedObject] = []
        self._freeze(env_unwrapped)

    def _freeze(self, env_unwrapped: Any) -> None:
        """枚举全场景对象，套黑名单，加回 TCP，冻结成本 episode 的固定清单。"""
        id_map: Mapping[int, Any] = getattr(env_unwrapped, "segmentation_id_map", {}) or {}
        agent = getattr(env_unwrapped, "agent", None)
        robot = getattr(agent, "robot", None)
        robot_name = _object_name(robot) if robot is not None else None
        tcp = getattr(agent, "tcp", None)

        for seg_id, obj in sorted(id_map.items()):
            seg_id = int(seg_id)
            name = _object_name(obj)
            articulation = _articulation_of(obj)
            is_link = articulation is not None
            kind = "link" if is_link else "actor"
            articulation_name = _object_name(articulation) if is_link else ""
            key = _make_key(name, seg_id)

            # 机器人自身的 link 一律剔除。判据用「所属 articulation 是不是机器人」，
            # 而不是 panda_ 名字前缀——stick 环境的命名不同，靠前缀会漏。
            if is_link and robot_name is not None and articulation_name == robot_name:
                self.excluded.append(
                    ExcludedObject(key, name, seg_id, kind, REASON_ROBOT_LINK)
                )
                continue

            if name in self.background_names:
                self.excluded.append(
                    ExcludedObject(key, name, seg_id, kind, REASON_BACKGROUND)
                )
                continue

            self.objects.append(
                SegObject(
                    key=key,
                    original_name=name,
                    seg_id=seg_id,
                    kind=kind,
                    articulation_name=articulation_name,
                )
            )

        # TCP 属于机器人 articulation，上面必然把它剔掉了，这里单独加回来。
        # 它通常没有视觉体，在 segmentation 图里从不出现，属预期行为。
        if tcp is not None:
            tcp_name = _object_name(tcp)
            tcp_seg_id = self._lookup_seg_id(id_map, tcp, tcp_name)
            tcp_key = _make_key(tcp_name, tcp_seg_id)
            self.objects.append(
                SegObject(
                    key=tcp_key,
                    original_name=tcp_name,
                    seg_id=tcp_seg_id,
                    kind="tcp",
                    articulation_name=robot_name or "",
                )
            )
            self.excluded = [item for item in self.excluded if item.key != tcp_key]

        # 极端情况下仍可能撞名（同名同 seg_id 理论上不会发生，但不做假设）
        seen: set[str] = set()
        for item in self.objects:
            if item.key in seen:
                raise ValueError(f"场景对象 key 重复：{item.key}")
            seen.add(item.key)

    @staticmethod
    def _lookup_seg_id(id_map: Mapping[int, Any], target: Any, target_name: str) -> int:
        """在 segmentation_id_map 里反查某对象的 id：先按对象身份，再退回按名字。"""
        for seg_id, obj in id_map.items():
            if obj is target:
                return int(seg_id)
        for seg_id, obj in id_map.items():
            if _object_name(obj) == target_name:
                return int(seg_id)
        return -1


def _write_object_entry(parent: h5py.Group, name: str, fields: Mapping[str, Any]) -> None:
    """在字典 group 下写一个条目，字符串统一按 UTF-8 变长串落盘。"""
    entry = parent.create_group(name)
    for key, value in fields.items():
        if isinstance(value, str):
            entry.create_dataset(
                key, data=value, dtype=h5py.string_dtype(encoding="utf-8")
            )
        else:
            entry.create_dataset(key, data=np.int64(value))


def write_seg_id_table(setup_group: h5py.Group, table: SegIdTable) -> None:
    """把枚举表写进已存在的 setup group（两个字典 group，拒绝覆盖）。"""
    for existing in ("segmentation_objects", "segmentation_excluded"):
        if existing in setup_group:
            raise ValueError(f"setup 下已存在 {existing}，拒绝覆盖")

    objects_group = setup_group.create_group("segmentation_objects")
    for item in table.objects:
        _write_object_entry(
            objects_group,
            item.key,
            {
                "original_name": item.original_name,
                "seg_id": item.seg_id,
                "kind": item.kind,
                "articulation_name": item.articulation_name,
            },
        )

    excluded_group = setup_group.create_group("segmentation_excluded")
    for item in table.excluded:
        _write_object_entry(
            excluded_group,
            item.key,
            {
                "original_name": item.original_name,
                "seg_id": item.seg_id,
                "kind": item.kind,
                "reason": item.reason,
            },
        )
