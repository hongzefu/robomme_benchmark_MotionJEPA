"""用 OBB 分离轴和连续运动上界证明安全，无法证明时拒绝候选。

长度统一为米，四元数统一为 wxyz。容器使用朝上的世界坐标约定，
中央 box 的几何等价于原翻转坐标中局部 z=-0.005、半高 0.015。
这里不把有空腔的容器外包络当成实心物体。
"""

from dataclasses import dataclass
from itertools import combinations
import math


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


def box_components(actor, geometry=None):
    """返回 actor 局部坐标下用于视觉与碰撞共同构建的实心 box 列表。"""
    geometry = geometry or {}
    if "components" in actor:
        return tuple(actor["components"])
    kind = actor["kind"]
    if kind == "container":
        thickness = float(geometry.get("central_box_thickness", 0.030))
        if not 0 < thickness <= 0.040:
            raise ValueError("容器中央 box 厚度必须位于 (0,0.040]")
        # 容器 actor 中心 z=.036，顶部固定 world z=.072。
        return (
            {"name": "central", "position": [0, 0, .036-thickness/2], "half_size": [.020, .020, thickness/2]},
            {"name": "roof", "position": [0, 0, .014], "half_size": [.0275, .0275, .002]},
            {"name": "wall_x_minus", "position": [-.0275, 0, -.011], "half_size": [.0025, .0275, .025]},
            {"name": "wall_x_plus", "position": [.0275, 0, -.011], "half_size": [.0025, .0275, .025]},
            {"name": "wall_y_minus", "position": [0, -.0275, -.011], "half_size": [.0275, .0025, .025]},
            {"name": "wall_y_plus", "position": [0, .0275, -.011], "half_size": [.0275, .0025, .025]},
        )
    if kind == "board":
        hx, hy, hz = actor["half_size"]
        hole = float(actor.get("hole_half_size", geometry.get("hole_side", .080)/2))
        if not 0 < hole < min(hx, hy):
            raise ValueError("孔半宽必须小于板半宽且大于零")
        return (
            {"name": "top", "position": [0, (hy+hole)/2, 0], "half_size": [hx, (hy-hole)/2, hz]},
            {"name": "bottom", "position": [0, -(hy+hole)/2, 0], "half_size": [hx, (hy-hole)/2, hz]},
            {"name": "left", "position": [-(hx+hole)/2, 0, 0], "half_size": [(hx-hole)/2, hole, hz]},
            {"name": "right", "position": [(hx+hole)/2, 0, 0], "half_size": [(hx-hole)/2, hole, hz]},
        )
    if kind == "button":
        # 原按钮的帽为圆柱，使用包含圆柱的方盒提供保守证书；运行时仍由
        # 原构建器创建真实关节/圆柱，不能把此包络当作接触判定的实际形状。
        radius = float(geometry.get("button_cap_radius", .0225))
        half_length = float(geometry.get("button_cap_half_length", .009))
        half_base = actor["half_size"][2]
        return (
            {"name": "base", "position": [0, 0, 0], "half_size": list(actor["half_size"])},
            {"name": "cap_bound", "position": [0, 0, half_base+half_length], "half_size": [radius, radius, half_length]},
        )
    return ({"name": kind, "position": [0, 0, 0], "half_size": list(actor["half_size"])},)


def actor_boxes(actor, geometry=None, pose=None):
    """按照和仿真 builder 相同的局部 box 描述计算世界 OBB。"""
    pose = pose or actor
    p, q = pose["position"], pose["quaternion"]
    result = []
    for part in box_components(actor, geometry):
        part_q = _multiply(q, part.get("quaternion", (1, 0, 0, 0)))
        axes = tuple(zip(*quaternion_matrix(part_q)))
        result.append(Box(_add(p, rotate(q, part["position"])), axes, tuple(part["half_size"])))
    return tuple(result)


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


def _as_dict(spec):
    return spec.to_dict() if hasattr(spec, "to_dict") else spec


def _pose(actor):
    return {"position": list(actor["position"]), "quaternion": list(actor["quaternion"])}


def swap_poses(first, second, progress, lane_offset=.070):
    """连续 smoothstep 主进度和正弦双车道；端点由清单固定而非实时重选。"""
    t = min(1.0, max(0.0, float(progress)))
    u = t*t*(3-2*t)
    ap, bp = first["position"], second["position"]
    delta = _sub(bp, ap)
    length = math.hypot(delta[0], delta[1])
    if length < 1e-12:
        raise ValueError("交换双方不能位于同一 xy 位置")
    normal = (-delta[1]/length, delta[0]/length, 0)
    offset = _scale(normal, float(lane_offset)*math.sin(math.pi*u))
    aq, bq = first["quaternion"], second["quaternion"]
    return (
        {"position": list(_add(_add(ap, _scale(delta, u)), offset)), "quaternion": list(_slerp(aq, bq, u))},
        {"position": list(_sub(_add(bp, _scale(delta, -u)), offset)), "quaternion": list(_slerp(bq, aq, u))},
    )


def _carry_children(actors, poses, before, parent_ids):
    """藏块按父容器的刚体变换移动，保持空腔中的相对位置与方向。"""
    for actor in actors:
        parent = actor.get("parent_id")
        if parent not in parent_ids:
            continue
        previous, current = before[parent], poses[parent]
        local = _inverse_rotate(previous["quaternion"], _sub(before[actor["id"]]["position"], previous["position"]))
        w, x, y, z = previous["quaternion"]
        relative_q = _multiply((w, -x, -y, -z), before[actor["id"]]["quaternion"])
        poses[actor["id"]] = {
            "position": list(_add(current["position"], rotate(current["quaternion"], local))),
            "quaternion": list(_multiply(current["quaternion"], relative_q)),
        }


def pose_at_step(spec, step):
    """从初始位姿按清单顺序求任意实数控制步的位姿，不依赖调用历史。"""
    data = _as_dict(spec)
    actors = data["actors"]
    poses = {actor["id"]: _pose(actor) for actor in actors}
    for swap in data.get("swaps", []):
        start, end = swap["start_step"], swap["end_step"]
        if end <= start:
            raise ValueError("交换结束步必须晚于开始步")
        if step < start:
            break
        before = dict(poses)
        a, b = swap["a"], swap["b"]
        poses[a], poses[b] = swap_poses(before[a], before[b], (step-start)/(end-start), swap["lane_offset"])
        _carry_children(actors, poses, before, (a, b))
        if step < end:
            break
    return poses


def _pair_clearance(first, second, geometry, poses):
    return min(box_clearance(a, b) for a in actor_boxes(first, geometry, poses[first["id"]]) for b in actor_boxes(second, geometry, poses[second["id"]]))


def _bounds_clearance(actor, geometry, poses, bounds):
    minimum = math.inf
    for box in actor_boxes(actor, geometry, poses[actor["id"]]):
        for axis, key in enumerate(("x", "y")):
            unit = tuple(float(i == axis) for i in range(3))
            radius = box.radius_on(unit)
            low, high = bounds[key]
            minimum = min(minimum, box.center[axis]-radius-low, high-box.center[axis]-radius)
        # 桌面支撑允许零距离，地面穿透使用独立硬阈值。
        bottom = box.center[2]-box.radius_on((0, 0, 1))
        if bottom < float(bounds.get("z", 0))-1e-8:
            return bottom-float(bounds.get("z", 0))
    return minimum


def _motion_speed_bound(actor, geometry, start_poses, a, b, offset):
    """给出归一化交换进度上的任一点速度上界，含 slerp 旋转扫掠。"""
    parent = actor.get("parent_id", actor["id"])
    if parent not in (a, b):
        return 0.0
    p, q = start_poses[a], start_poses[b]
    angle = 2*math.acos(min(1.0, abs(_dot(_unit_quaternion(p["quaternion"]), _unit_quaternion(q["quaternion"])))))
    center = start_poses[parent]["position"]
    radius = max(_norm(_sub(box.center, center))+_norm(box.half_size) for box in actor_boxes(actor, geometry, start_poses[actor["id"]]))
    # smoothstep 的导数最大为 1.5；正弦车道导数界为 pi*offset。
    return 1.5*(_norm(_sub(p["position"], q["position"]))+math.pi*abs(offset)+angle*radius)


def validate_spec_geometry(spec):
    """认证初始布局、整个交换序列、所有旁观物体和桌边的连续净距。

    对每个区间用中点 SAT 轴作分离证据，以速度上界扣除半区间内的
    最大扫掠位移；证据不足则二分，预算耗尽也拒绝，不能用漏采样放行。
    该函数只认证清单中的物体几何；机械臂接触需由真实仿真认证补齐。
    """
    data = _as_dict(spec)
    geometry = data.get("geometry", {})
    margin = float(geometry.get("safety_clearance", .005))
    bounds = geometry.get("table_bounds", {"x": [-.5, .5], "y": [-.5, .5], "z": 0.0})
    if margin < 0 or not math.isfinite(margin):
        raise ValueError("安全净距必须为非负有限值")
    actors = data["actors"]
    by_id = {a["id"]: a for a in actors}
    if len(by_id) != len(actors):
        raise ValueError("物体 ID 必须唯一")
    pairs = list(combinations(actors, 2))
    reasons, minimum, subdivisions = [], math.inf, 0
    poses = {a["id"]: _pose(a) for a in actors}
    for actor in actors:
        if "initial_support_rejection" in actor:
            # 编译器已证明该位置层没有正宽可采区间；几何触边容差不能把
            # 空交集或零宽层重新认证成合法的确定性聚点。
            reasons.append(f"初始支持层不可采样: {actor['id']} {actor['initial_support_rejection']}")
        support = actor.get("initial_xy_bounds")
        if support is not None:
            # 初始支持框是位置分布的外框，不是障碍物；角点只需位于框内，
            # 不另扣碰撞安全距离，也不能污染下方 min_clearance 的物理口径。
            # OBB 在 x/y 轴上的投影端点恰为全部实际 component 角点的极值。
            for box in actor_boxes(actor, geometry, poses[actor["id"]]):
                for axis, key in enumerate(("x", "y")):
                    unit = tuple(float(index == axis) for index in range(3))
                    radius = box.radius_on(unit)
                    lower, upper = support[key]
                    if box.center[axis]-radius < lower-1e-10 or box.center[axis]+radius > upper+1e-10:
                        reasons.append(f"初始完整物体越出位置支持框: {actor['id']} 轴={key}")
                        break
                else:
                    continue
                break
        clearance = _bounds_clearance(actor, geometry, poses, bounds)
        minimum = min(minimum, clearance)
        if clearance < margin-1e-10:
            reasons.append(f"初始桌边/桌面不安全: {actor['id']} 净距下界={clearance:.9g}")
    for a, b in pairs:
        clearance = _pair_clearance(a, b, geometry, poses)
        minimum = min(minimum, clearance)
        if clearance < margin-1e-10:
            reasons.append(f"初始物体间净距不足: {a['id']} / {b['id']} = {clearance:.9g}")
    if reasons:
        return {"ok": False, "reasons": reasons, "min_clearance": minimum, "subdivisions": 0, "coverage": "compound_geometry_only"}
    previous_end = -math.inf
    for index, swap in enumerate(data.get("swaps", [])):
        a, b = swap["a"], swap["b"]
        if a == b or a not in by_id or b not in by_id:
            raise ValueError("交换对象必须是两个已声明的不同 ID")
        if swap["end_step"]-swap["start_step"] != 50 or abs(swap["lane_offset"]-.07)>1e-12:
            raise ValueError("首版交换固定为 50 控制步、0.07 米双车道")
        if swap["start_step"] < previous_end:
            raise ValueError("交换序列必须按时间排序且不能重叠")
        previous_end = swap["end_step"]
        start_poses = pose_at_step(data, swap["start_step"])
        speeds = {actor["id"]: _motion_speed_bound(actor, geometry, start_poses, a, b, swap["lane_offset"]) for actor in actors}
        moving = {name for name, speed in speeds.items() if speed > 0}
        # 父容器和藏块始终刚体相对运动，初始的真实 component 证书保持有效。
        moving_pairs = [(x, y) for x, y in pairs if (x["id"] in moving or y["id"] in moving) and x.get("parent_id", x["id"]) != y.get("parent_id", y["id"])]
        intervals = [(0.0, 1.0, 0)]
        while intervals:
            low, high, depth = intervals.pop()
            middle, radius = (low+high)/2, (high-low)/2
            state = pose_at_step(data, swap["start_step"]+middle*50)
            safe = True
            for x, y in moving_pairs:
                clearance = _pair_clearance(x, y, geometry, state)
                bound = clearance-(speeds[x["id"]]+speeds[y["id"]])*radius
                if clearance < margin-1e-10:
                    reasons.append(f"交换 {index} 在进度 {middle:.9g} 不安全: {x['id']} / {y['id']} 净距下界={clearance:.9g}")
                    return {"ok": False, "reasons": reasons, "min_clearance": min(minimum, clearance), "subdivisions": subdivisions, "coverage": "compound_geometry_only"}
                if bound < margin:
                    safe = False
                else:
                    minimum = min(minimum, bound)
            for actor in actors:
                if actor["id"] not in moving:
                    continue
                clearance = _bounds_clearance(actor, geometry, state, bounds)
                bound = clearance-speeds[actor["id"]]*radius
                if clearance < margin-1e-10:
                    return {"ok": False, "reasons": [f"交换 {index} 越出安全桌面: {actor['id']}"], "min_clearance": min(minimum, clearance), "subdivisions": subdivisions, "coverage": "compound_geometry_only"}
                if bound < margin:
                    safe = False
                else:
                    minimum = min(minimum, bound)
            if not safe:
                if depth >= 18:
                    return {"ok": False, "reasons": [f"交换 {index} 连续净距证书未收敛，拒绝候选"], "min_clearance": minimum, "subdivisions": subdivisions, "coverage": "compound_geometry_only"}
                subdivisions += 1
                intervals.extend(((middle, high, depth+1), (low, middle, depth+1)))
    return {"ok": True, "reasons": [], "min_clearance": minimum, "subdivisions": subdivisions, "coverage": "compound_geometry_only"}
