"""读取原版实际碰撞组件进行初态筛选，不定义任务素材或运行时失败。"""

from dataclasses import dataclass
from itertools import combinations
import math

import numpy as np

from .assets import array_copy

def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _scale(a, scale):
    return tuple(x * scale for x in a)


def _norm(a):
    return math.sqrt(_dot(a, a))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit_quaternion(q):
    q = tuple(float(x) for x in q)
    if len(q) != 4 or not all(math.isfinite(x) for x in q):
        raise ValueError("四元数必须是四个有限值")
    length = _norm(q)
    if length < 1e-12:
        raise ValueError("不能使用零四元数")
    return _scale(q, 1 / length)


def quaternion_matrix(q):
    """返回单位 wxyz 四元数的旋转矩阵。"""
    w, x, y, z = _unit_quaternion(q)
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
        (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
        (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
    )


def rotate(q, vector):
    """将局部三维向量变换到世界系。"""
    return tuple(_dot(row, vector) for row in quaternion_matrix(q))


def _inverse_rotate(q, vector):
    w, x, y, z = _unit_quaternion(q)
    return rotate((w, -x, -y, -z), vector)


def _multiply(q, r):
    w, x, y, z = q
    a, b, c, d = r
    return (w*a-x*b-y*c-z*d, w*b+x*a+y*d-z*c, w*c-x*d+y*a+z*b, w*d+x*c-y*b+z*a)


def _slerp(q, r, t):
    q, r = _unit_quaternion(q), _unit_quaternion(r)
    cosine = _dot(q, r)
    if cosine < 0:
        r, cosine = _scale(r, -1), -cosine
    if cosine > 1 - 1e-12:
        return _unit_quaternion(_add(_scale(q, 1-t), _scale(r, t)))
    angle = math.acos(min(1.0, cosine))
    return _add(_scale(q, math.sin((1-t)*angle)/math.sin(angle)), _scale(r, math.sin(t*angle)/math.sin(angle)))


@dataclass(frozen=True)
class Box:
    """一个实心有向长方体；axes 的三行分别为局部轴在世界系的方向。"""

    center: tuple
    axes: tuple
    half_size: tuple

    def radius_on(self, axis):
        return sum(h * abs(_dot(v, axis)) for h, v in zip(self.half_size, self.axes))



def box_clearance(first, second):
    """返回真实距离的保守下界；负值表示 SAT 所有轴重叠，零表示接触。

    正数是最大分离投影，不冒充精确欧氏距离；距离下界超过阈值才放行。
    对不相交的凸 OBB，轴向移动扰动的上界也适用于该证书。
    """
    axes = list(first.axes) + list(second.axes)
    axes += [_cross(a, b) for a in first.axes for b in second.axes]
    delta = _sub(second.center, first.center)
    gaps = []
    for raw in axes:
        size = _norm(raw)
        if size <= 1e-12:
            continue
        axis = _scale(raw, 1/size)
        gaps.append(abs(_dot(delta, axis)) - first.radius_on(axis) - second.radius_on(axis))
    return max(gaps)



def actual_boxes(actor):
    """把实际shape局部坐标变换到世界坐标；圆柱使用保守外包络。"""
    position = array_copy(actor.pose.p).reshape(-1, 3)[0]
    quaternion = array_copy(actor.pose.q).reshape(-1, 4)[0]
    boxes = []
    for body in actor._bodies:
        for shape in body.collision_shapes:
            local = shape.local_pose
            if hasattr(shape, "half_size"):
                half_size = tuple(float(value) for value in shape.half_size)
            elif hasattr(shape, "radius") and hasattr(shape, "half_length"):
                half_size = (float(shape.half_length), float(shape.radius), float(shape.radius))
            else:
                raise ValueError(f"任务素材存在尚未支持的碰撞形状：{type(shape).__name__}")
            world_quaternion = _multiply(quaternion, local.q)
            center = _add(position, rotate(quaternion, local.p))
            axes = tuple(zip(*quaternion_matrix(world_quaternion)))
            boxes.append(Box(center, axes, half_size))
    return boxes


def validate_scene_geometry(base, spec):
    """只筛选初始布局。原版运行中的碰撞由其原始判定处理。"""
    definition = spec.to_dict()
    clearance = definition["layout"]["safety_clearance"]
    bounds = definition["layout"]["table_bounds"]
    objects = {name: actor for name, actor in base.scene.actors.items()
               if name not in {"table-workspace", "ground"}}
    for name, articulation in base.scene.articulations.items():
        if name.startswith("button"):
            for link in articulation.get_links():
                objects[f"{name}/{link.name}"] = link
    boxes = {name: actual_boxes(actor) for name, actor in objects.items()}
    allowed = {frozenset((cube.name, container.name))
               for cube, container in getattr(base, "cube_bin_pairs", [])}
    reasons = []
    minimum = None
    for first, second in combinations(boxes, 2):
        if not boxes[first] or not boxes[second]:
            continue
        if first.split("/")[0] == second.split("/")[0] and "/" in first:
            continue
        if frozenset((first, second)) in allowed:
            continue
        gap = min(box_clearance(a, b) for a in boxes[first] for b in boxes[second])
        minimum = gap if minimum is None else min(minimum, gap)
        if gap < clearance:
            reasons.append(f"{first}/{second} 初始净距{gap:.8f}小于{clearance}")
    for name, parts in boxes.items():
        for box in parts:
            for index, axis in enumerate(("x", "y")):
                direction = (1, 0, 0) if index == 0 else (0, 1, 0)
                radius = box.radius_on(direction)
                if box.center[index] - radius < bounds[axis][0] or box.center[index] + radius > bounds[axis][1]:
                    reasons.append(f"{name} 超出桌面{axis}边界")
    layout = definition["layout"]
    supports = layout.get("supports", {})
    if spec.task_kind == "BinFill":
        placed = base.all_cubes
    elif spec.task_kind == "VideoRepick":
        placed = base.spawned_cubes
    elif spec.task_kind == "VideoUnmaskSwap":
        placed = base.spawned_bins
    else:
        placed = []
    for number, actor in enumerate(placed):
        if layout["topology"] == "field":
            prefix = f"cube_{number}"
        else:
            group = "containers" if spec.task_kind == "VideoUnmaskSwap" else "cubes"
            prefix = f"{group}_{number}"
        for index, axis in enumerate(("x", "y")):
            support = supports.get(prefix)
            if support is None:
                continue
            low, high = support[axis]
            direction = (1, 0, 0) if index == 0 else (0, 1, 0)
            for box in boxes[actor.name]:
                radius = box.radius_on(direction)
                if box.center[index] - radius < low or box.center[index] + radius > high:
                    reasons.append(f"{actor.name} 完整碰撞形状超出配置{axis}外框")
    return {"ok": not reasons, "reasons": reasons, "minimum_clearance": minimum,
            "required_clearance": clearance, "source": "native_collision_shapes",
            "scope": "initial_layout", "object_count": len(objects)}
