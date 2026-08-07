#!/usr/bin/env python3
"""稀疏逐物体 2D flow ground truth 的采集与落盘。

这份 flow 全部来自仿真真值：物体的 3D 世界坐标直接取自仿真状态，再用仓库里唯一的投影
入口反投影到 base_camera 像素平面。链路中**不存在任何从像素估计的成分**（没有光流网络、
没有特征点匹配），GT 就是 GT。

模块干四件事：

1. **枚举与冻结**：从 ``env.unwrapped.segmentation_id_map`` 取全场景对象，套黑名单剔除
   机械臂各 link 与桌面地面等背景道具，再单独把 TCP 加回来。物体清单在 ``reset()`` 之后
   一次性冻结，episode 内 key 集合固定不变。
2. **逐帧采集**：在 ``env.step()`` 之后纯读仿真状态与已有的渲染缓冲，算出每个物体的
   3D 位置、子像素投影、相机系深度、画幅内标志、分割像素数与投影点遮挡标志。
3. **位移计算**：episode 结束、buffer 完整之后，按物体 key 跨帧配对算出到**下一个记录帧**
   的 2D 位移（delta = 1 帧）。
4. **写盘**：把上述结果写进 h5 的 ``setup/flow_*`` 与 ``timestep_<k>/flow/``。

### h5 落点与编码

``setup/`` 下是两个字典 group：``flow_objects``（保留对象 → segmentation id + 种类）与
``flow_excluded``（黑名单对象 → 剔除原因），外加一个 ``flow_schema_version``。

``timestep_<k>/flow/<key>`` 是一个 **compound dtype 的标量 dataset**，字段名就是各个物理量，
读法仍然是字典式的 ``f[".../flow/button__42"]["pos_3d"]``。之所以不用「每个字段一个
dataset」，是因为那样 dataset 总数会变成 N物体 × T帧 × 9，光元数据就能把 h5 撑大三四成。

### 字典 key 的口径

key 一律是 ``<原名>__<seg_id>``。ManiSkill 保证 actor 名全局唯一，但 link 名只在自己
articulation 内唯一（两个 button articulation 可以各有一个同名 link），带上 segmentation id
才能保证 h5 里的 group 名不撞。

⚠ 代价是 ``per_scene_id`` 每个 episode 都可能不同，所以 **key 跨 episode 不稳定**。下游若要
按物体跨 episode 聚合，必须走 ``setup/flow_objects/<key>/original_name`` 反查，不能直接把 key
当成稳定主键。

### 为什么 z_cam 是必备字段

只有 ``(u, v)`` 是没法反解 3D 的——一个像素对应一整条射线，是一对多映射。必须同时存下相机系
深度，``(u, v, z_cam) ↔ (X, Y, Z)_world`` 才构成严格双射。这是「正反转换一一对应」这个主张
成立的唯一前提，所以 z_cam 属于必备字段而不是附加信息。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

import h5py
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from robomme.robomme_env.utils.choice_action_mapping import (  # noqa: E402
    project_world_to_pixel_subpixel,
)


FLOW_SCHEMA_VERSION = "flow-2d-v1"

# 逐帧逐物体的落盘结构。位移两套都保 float——帧间位移常常小于 1 像素，
# 整数化会把它直接量化成 0。
FLOW_DTYPE = np.dtype(
    [
        ("pos_3d", "<f8", (3,)),  # 世界系参考点（米），取自物体位姿的平移分量
        ("pos_2d_uv", "<f8", (2,)),  # [u=列, v=行]，OpenCV 约定，子像素、不裁剪
        ("pos_2d_yx", "<i4", (2,)),  # [y=行, x=列] 整数，与 action/choice_action 同口径
        ("z_cam", "<f8"),  # 相机系深度（米），反投影必需
        ("in_frame", "?"),  # 深度为正且投影落在画幅内
        ("seg_pixel_count", "<i4"),  # 该物体在 front 分割图里的像素数（0 = 整体不可见）
        ("point_unoccluded", "?"),  # 投影点所在像素的分割 id 恰为该物体自身
        ("flow_2d_uv", "<f8", (2,)),  # 到下一个记录帧的 (Δu, Δv)；无效写 NaN
        ("flow_2d_yx", "<f8", (2,)),  # 同一位移的 [Δy, Δx] 轴序；无效写 NaN
    ]
)

# 背景道具黑名单：桌面、地面这类既不会动、也不是任务对象的东西
DEFAULT_BACKGROUND_NAMES = frozenset(
    {
        "table-workspace",
        "table",
        "ground",
        "floor",
    }
)

# 剔除原因，落进 setup/flow_excluded/<key>/reason，口径永远可回溯
REASON_ROBOT_LINK = "robot_link"
REASON_BACKGROUND = "background_prop"

_INVALID_PIXEL = -1  # pos_2d_yx 的无效哨兵；浮点字段一律用 NaN


@dataclass
class FlowObject:
    """一个参与 flow 统计的对象。"""

    key: str  # h5 里的字典 key，形如 <原名>__<seg_id>
    original_name: str  # 未拼接的原始 actor.name / link.name
    seg_id: int  # per_scene_id，与分割图像素值一一对应
    kind: str  # "actor" / "link" / "tcp"
    articulation_name: str  # link/tcp 所属 articulation 名；actor 写空串
    handle: Any = field(repr=False, default=None)  # 运行时句柄，用来逐帧读位姿


@dataclass
class ExcludedObject:
    """被黑名单剔除的对象，只为可回溯而记录。"""

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


def _to_numpy(value: Any) -> np.ndarray:
    """把 torch tensor / numpy / list 统一成 numpy 数组，不做 dtype 转换。"""
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    return np.asarray(value)


def _position_of(obj: Any) -> Optional[np.ndarray]:
    """读对象位姿的平移分量，返回 (3,) float64；读不到返回 None。"""
    pose = getattr(obj, "pose", None)
    if pose is None:
        return None
    position = getattr(pose, "p", None)
    if position is None:
        return None
    array = _to_numpy(position).reshape(-1)
    if array.size < 3:
        return None
    result = array[:3].astype(np.float64)
    if not np.all(np.isfinite(result)):
        return None
    return result


class FlowTracker:
    """按 episode 冻结物体清单，并逐帧采集 flow 所需的全部原始量。"""

    def __init__(
        self,
        env_unwrapped: Any,
        background_names: Iterable[str] = DEFAULT_BACKGROUND_NAMES,
    ) -> None:
        self.background_names = frozenset(background_names)
        self.objects: list[FlowObject] = []
        self.excluded: list[ExcludedObject] = []
        self._freeze(env_unwrapped)

    # ------------------------------------------------------------------
    # 一、枚举与冻结
    # ------------------------------------------------------------------
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
                FlowObject(
                    key=key,
                    original_name=name,
                    seg_id=seg_id,
                    kind=kind,
                    articulation_name=articulation_name,
                    handle=obj,
                )
            )

        # TCP 属于机器人 articulation，上面必然把它剔掉了，这里单独加回来。
        # 它通常没有视觉体，seg_pixel_count 会恒为 0，属预期行为。
        if tcp is not None:
            tcp_name = _object_name(tcp)
            tcp_seg_id = self._lookup_seg_id(id_map, tcp, tcp_name)
            tcp_key = _make_key(tcp_name, tcp_seg_id)
            self.objects.append(
                FlowObject(
                    key=tcp_key,
                    original_name=tcp_name,
                    seg_id=tcp_seg_id,
                    kind="tcp",
                    articulation_name=robot_name or "",
                    handle=tcp,
                )
            )
            self.excluded = [item for item in self.excluded if item.key != tcp_key]

        # 极端情况下仍可能撞名（同名同 seg_id 理论上不会发生，但不做假设）
        seen: set[str] = set()
        for item in self.objects:
            if item.key in seen:
                raise ValueError(f"flow 物体 key 重复：{item.key}")
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

    # ------------------------------------------------------------------
    # 二、逐帧采集
    # ------------------------------------------------------------------
    def capture(self, obs: Any, env_unwrapped: Any) -> dict[str, Any]:
        """采集单个记录帧。只读仿真状态与已有渲染缓冲，不触发随机数、不额外渲染。

        返回的 dict 里除了逐物体记录，还带上 ``elapsed_steps`` 与 ``is_video_demo``——
        这两个量只用于事后判断相邻记录帧之间是不是断点，本身不落盘。
        """
        sensor_param = obs["sensor_param"]["base_camera"]
        intrinsic = _to_numpy(sensor_param["intrinsic_cv"]).reshape(3, 3).astype(np.float64)
        extrinsic = _to_numpy(sensor_param["extrinsic_cv"]).reshape(3, 4).astype(np.float64)

        segmentation = _to_numpy(obs["sensor_data"]["base_camera"]["segmentation"])
        segmentation_2d = np.squeeze(segmentation)
        if segmentation_2d.ndim != 2:
            segmentation_2d = segmentation_2d.reshape(
                segmentation_2d.shape[-2], segmentation_2d.shape[-1]
            )
        height, width = segmentation_2d.shape

        # 一次 bincount 得到所有 id 的像素数，比逐物体全图扫描 N 次快一个量级
        flat = segmentation_2d.reshape(-1)
        counts = np.bincount(flat[flat >= 0].astype(np.int64))

        records: dict[str, dict[str, Any]] = {}
        for item in self.objects:
            records[item.key] = self._capture_one(
                item, intrinsic, extrinsic, segmentation_2d, counts, height, width
            )

        return {
            "elapsed_steps": int(getattr(env_unwrapped, "elapsed_steps", -1) or 0),
            "is_video_demo": bool(
                getattr(env_unwrapped, "current_task_demonstration", False)
            ),
            "records": records,
        }

    def _capture_one(
        self,
        item: FlowObject,
        intrinsic: np.ndarray,
        extrinsic: np.ndarray,
        segmentation_2d: np.ndarray,
        counts: np.ndarray,
        height: int,
        width: int,
    ) -> dict[str, Any]:
        position = _position_of(item.handle)
        seg_pixel_count = (
            int(counts[item.seg_id])
            if 0 <= item.seg_id < counts.size
            else 0
        )

        if position is None:
            return {
                "pos_3d": np.full(3, np.nan, dtype=np.float64),
                "pos_2d_uv": np.full(2, np.nan, dtype=np.float64),
                "pos_2d_yx": np.full(2, _INVALID_PIXEL, dtype=np.int32),
                "z_cam": float("nan"),
                "in_frame": False,
                "seg_pixel_count": seg_pixel_count,
                "point_unoccluded": False,
            }

        projected = project_world_to_pixel_subpixel(
            world_xyz=position,
            intrinsic_cv=intrinsic,
            extrinsic_cv=extrinsic,
        )
        if projected is None:
            # 深度非正（物体在相机后方）——此时双射不成立，像素与位移一律写哨兵
            return {
                "pos_3d": position,
                "pos_2d_uv": np.full(2, np.nan, dtype=np.float64),
                "pos_2d_yx": np.full(2, _INVALID_PIXEL, dtype=np.int32),
                "z_cam": float("nan"),
                "in_frame": False,
                "seg_pixel_count": seg_pixel_count,
                "point_unoccluded": False,
            }

        u, v, z_cam = projected
        row = int(np.rint(v))
        column = int(np.rint(u))
        in_frame = 0 <= row < height and 0 <= column < width

        if in_frame:
            pixel_yx = np.asarray([row, column], dtype=np.int32)
            point_unoccluded = bool(int(segmentation_2d[row, column]) == item.seg_id)
        else:
            pixel_yx = np.full(2, _INVALID_PIXEL, dtype=np.int32)
            point_unoccluded = False

        return {
            "pos_3d": position,
            "pos_2d_uv": np.asarray([u, v], dtype=np.float64),
            "pos_2d_yx": pixel_yx,
            "z_cam": float(z_cam),
            "in_frame": in_frame,
            "seg_pixel_count": seg_pixel_count,
            "point_unoccluded": point_unoccluded,
        }

    # ------------------------------------------------------------------
    # 三、setup 元数据
    # ------------------------------------------------------------------
    @property
    def meta(self) -> dict[str, Any]:
        """写 setup/ 需要的元数据快照。"""
        return {
            "schema_version": FLOW_SCHEMA_VERSION,
            "objects": list(self.objects),
            "excluded": list(self.excluded),
        }


# ----------------------------------------------------------------------
# 四、位移计算与写盘
# ----------------------------------------------------------------------
def _is_breakpoint(previous: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    """判断相邻两个**记录帧**之间是不是断点，断点两侧的差分是假位移。

    两种断点：

    - ``elapsed_steps`` 差不等于 1：中间隔了名为 ``NO RECORD`` 的段，那些物理步既不进
      buffer 也不落 h5，相邻记录帧之间可能隔了任意多个真实步；
    - ``is_video_demo`` 翻转：demo 相位与执行相位之间发生过场景重置，物体会瞬移。
    """
    if bool(previous["is_video_demo"]) != bool(current["is_video_demo"]):
        return True
    return int(current["elapsed_steps"]) - int(previous["elapsed_steps"]) != 1


def _timestep_names(episode_group: h5py.Group) -> list[str]:
    """按数字顺序列出 episode 下的 timestep group 名。"""
    named: list[tuple[int, str]] = []
    for name in episode_group.keys():
        if not name.startswith("timestep_"):
            continue
        suffix = name[len("timestep_") :]
        if not suffix.isdigit():
            # 父类写盘遇到重名会退化成 timestep_<k>_dupN，正常路径不会出现，
            # 一旦出现就说明帧序与 flow 帧序无法可靠对齐，直接报错而不是猜。
            raise ValueError(f"无法解析的 timestep 名：{name}")
        named.append((int(suffix), name))
    named.sort()
    return [name for _, name in named]


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


def write_flow_setup(setup_group: h5py.Group, meta: Mapping[str, Any]) -> None:
    """把 flow 的 episode 级元数据写进已存在的 setup group。"""
    setup_group.create_dataset(
        "flow_schema_version",
        data=meta["schema_version"],
        dtype=h5py.string_dtype(encoding="utf-8"),
    )

    objects_group = setup_group.create_group("flow_objects")
    for item in meta["objects"]:
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

    excluded_group = setup_group.create_group("flow_excluded")
    for item in meta["excluded"]:
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


def build_frame_arrays(
    frames: Sequence[Mapping[str, Any]],
    object_keys: Sequence[str],
) -> list[dict[str, np.ndarray]]:
    """把逐帧采集结果补上 delta = 1 帧的 2D 位移，转成可直接落盘的 compound 记录。

    位移的无效判定一律用 NaN 哨兵（与既有 ``action/waypoint_action`` 的体例一致），三种情况
    写 NaN：最后一帧、本帧或下一帧深度非正、两帧之间是断点。
    """
    built: list[dict[str, np.ndarray]] = []
    for index, frame in enumerate(frames):
        next_frame = frames[index + 1] if index + 1 < len(frames) else None
        breakpoint_ahead = (
            next_frame is None or _is_breakpoint(frame, next_frame)
        )

        per_object: dict[str, np.ndarray] = {}
        for key in object_keys:
            current = frame["records"][key]
            record = np.zeros((), dtype=FLOW_DTYPE)
            record["pos_3d"] = current["pos_3d"]
            record["pos_2d_uv"] = current["pos_2d_uv"]
            record["pos_2d_yx"] = current["pos_2d_yx"]
            record["z_cam"] = current["z_cam"]
            record["in_frame"] = current["in_frame"]
            record["seg_pixel_count"] = current["seg_pixel_count"]
            record["point_unoccluded"] = current["point_unoccluded"]

            flow_uv = np.full(2, np.nan, dtype=np.float64)
            flow_yx = np.full(2, np.nan, dtype=np.float64)
            if not breakpoint_ahead:
                following = next_frame["records"][key]
                current_uv = np.asarray(current["pos_2d_uv"], dtype=np.float64)
                next_uv = np.asarray(following["pos_2d_uv"], dtype=np.float64)
                if np.all(np.isfinite(current_uv)) and np.all(np.isfinite(next_uv)):
                    delta = next_uv - current_uv
                    flow_uv = delta
                    flow_yx = np.asarray([delta[1], delta[0]], dtype=np.float64)
            record["flow_2d_uv"] = flow_uv
            record["flow_2d_yx"] = flow_yx
            per_object[key] = record
        built.append(per_object)
    return built


def write_flow_groups(
    episode_group: h5py.Group,
    frames: Sequence[Optional[Mapping[str, Any]]],
    meta: Mapping[str, Any],
) -> int:
    """把 flow 追加写进已经落盘的 episode group，返回写入的帧数。

    这是「二次打开」路径：父类 RecordWrapper 已经原样写完并关闭了 h5，这里以追加模式重新
    打开同一个文件，只往里加 flow 内容，既有字段一律不碰。
    """
    if any(frame is None for frame in frames):
        raise ValueError("存在没有采集到 flow 的记录帧，无法与 timestep 对齐")

    timestep_names = _timestep_names(episode_group)
    if len(timestep_names) != len(frames):
        raise ValueError(
            f"timestep 数量({len(timestep_names)})与 flow 帧数({len(frames)})不一致"
        )

    setup_group = episode_group.get("setup")
    if not isinstance(setup_group, h5py.Group):
        raise ValueError("episode 下缺少 setup group，无法写入 flow 元数据")
    write_flow_setup(setup_group, meta)

    object_keys = [item.key for item in meta["objects"]]
    built = build_frame_arrays(frames, object_keys)

    for name, per_object in zip(timestep_names, built):
        flow_group = episode_group[name].create_group("flow")
        for key, record in per_object.items():
            flow_group.create_dataset(key, data=record)

    return len(built)
