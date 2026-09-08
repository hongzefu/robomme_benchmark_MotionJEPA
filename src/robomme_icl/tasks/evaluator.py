"""只消费确定性物理快照的任务状态机，不读取 RNG 或旧任务类。

调用协议：每个控制步调用一次 update，step 在单次 reset 内严格递增。
同一步重复调用幂等，倒退直接报错；演示阶段不计入评测次数。
快照包含 poses、linear_velocities、angular_velocities、grasped_ids、
button_pressed、tcp_position、forbidden_collision 和 phase。
"""

from dataclasses import dataclass, field
import math

from robomme_icl.geometry import actor_boxes, actor_occupies_binfill_hole, quaternion_matrix


# 阈值集中在此；清单 task_parameters.evaluation_thresholds 可固定覆写。
DEFAULT_THRESHOLDS = {
    "lift_height": .045,
    "table_tolerance": .004,
    "linear_speed": .030,
    "angular_speed": .50,
    "stable_steps": 3,
    "target_radius": .022,
    "route_target_height_min": .0,
    "route_target_height_max": .15,
    "route_side_tolerance": .002,
    "stick_radius": .003,
}


def _norm(vector):
    return math.sqrt(sum(float(x)**2 for x in vector))


def _subtract(a, b):
    return tuple(float(x)-float(y) for x, y in zip(a, b))


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _local(pose, point):
    rotation = quaternion_matrix(pose["quaternion"])
    delta = _subtract(point, pose["position"])
    return tuple(_dot(axis, delta) for axis in zip(*rotation))


def _color_name(actor):
    if "color_name" in actor:
        return actor["color_name"]
    color = actor["color"]
    # 名称缺失仅可由三个已声明原色精确识别，不能用目标列表猜颜色。
    index = max(range(3), key=lambda i: color[i])
    return ("red", "green", "blue")[index]


@dataclass
class TaskState:
    """所有可变判定状态都在此集中清零，禁止环境残留跨 reset 泄漏。"""

    failure_latched: bool = False
    failure_reasons: list = field(default_factory=list)
    completed: bool = False
    cursor: int = 0
    repeat_count: int = 0
    inserted_ids: set = field(default_factory=set)
    eligible_insert_ids: set = field(default_factory=set)
    color_counts: dict = field(default_factory=dict)
    stable_counts: dict = field(default_factory=dict)
    lifted: bool = False
    last_step: int = -1
    last_result: dict = field(default_factory=dict)
    last_tcp: tuple | None = None
    route_side_seen: bool = False
    phase: str = "demonstration"


class TaskEvaluator:
    """四任务判定器；成功永远蕴含尚未发生历史失败。"""

    def __init__(self, spec):
        self.spec = spec.to_dict() if hasattr(spec, "to_dict") else spec
        self.kind = self.spec["task_kind"]
        self.parameters = self.spec["task_parameters"]
        self.geometry = self.spec.get("geometry", {})
        self.actors = {actor["id"]: actor for actor in self.spec["actors"]}
        self.thresholds = dict(DEFAULT_THRESHOLDS)
        self.thresholds.update(self.parameters.get("evaluation_thresholds", {}))
        if self.kind not in ("BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick"):
            raise ValueError(f"不支持的任务: {self.kind}")
        self.reset()

    def reset(self):
        """彻底复位计数器、转换标志、失败锁存与轨迹缓存。"""
        self.state = TaskState()
        return self._result()

    def _fail(self, reason):
        self.state.failure_latched = True
        if reason not in self.state.failure_reasons:
            self.state.failure_reasons.append(reason)

    def _result(self):
        state = self.state
        targets = (self.parameters.get("target_container_ids", []) if self.kind == "VideoUnmaskSwap"
                   else [f"target_{index}" for index in self.parameters.get("path_indices", [])])
        next_target = targets[state.cursor] if state.cursor < len(targets) else None
        if self.kind == "VideoRepick":
            next_target = self.parameters["target_ids"][0]
        return {
            "success": bool(state.completed and not state.failure_latched),
            "fail": bool(state.failure_latched),
            "completed": bool(state.completed),
            "failure_reasons": list(state.failure_reasons),
            "cursor": state.cursor,
            "repeat_count": state.repeat_count,
            "inserted_ids": sorted(state.inserted_ids),
            "color_counts": dict(sorted(state.color_counts.items())),
            "phase": state.phase,
            "next_target": next_target,
            "holding_phase": "lifted" if state.lifted else "ready",
            "required_count": self.parameters.get("repeat_count", self.parameters.get("pick_count", len(targets))),
        }

    def update(self, observation):
        """根据真实观测推进一次；接触检测失败必须作为 forbidden_collision 传入。"""
        step = int(observation["step"])
        if step < self.state.last_step:
            raise ValueError("判定步数倒退，请在环境 reset 时复位 TaskEvaluator")
        if step == self.state.last_step:
            return dict(self.state.last_result)
        self.state.last_step = step
        phase = observation.get("phase", "evaluation")
        if phase not in ("demonstration", "evaluation"):
            raise ValueError("phase 只能是 demonstration 或 evaluation")
        self.state.phase = phase
        if observation.get("forbidden_collision", False):
            self._fail("发生非预期碰撞或无法读取碰撞信息")
        for actor_id in self.actors:
            pose = observation["poses"][actor_id]
            values = list(pose["position"])+list(pose["quaternion"])
            if not all(math.isfinite(float(value)) for value in values):
                self._fail(f"物体位姿含非有限数值: {actor_id}")
        if phase == "evaluation" and not self.state.failure_latched:
            getattr(self, f"_update_{self.kind}")(observation)
        self.state.last_result = self._result()
        return dict(self.state.last_result)

    def _stable(self, actor_id, observation, in_place):
        """必须连续静止，缺速度字段时拒绝形成落稳证据。"""
        linear = observation.get("linear_velocities", {}).get(actor_id)
        angular = observation.get("angular_velocities", {}).get(actor_id)
        stable = (in_place and linear is not None and angular is not None
                  and _norm(linear) <= self.thresholds["linear_speed"]
                  and _norm(angular) <= self.thresholds["angular_speed"])
        self.state.stable_counts[actor_id] = self.state.stable_counts.get(actor_id, 0)+1 if stable else 0
        return self.state.stable_counts[actor_id] >= int(self.thresholds["stable_steps"])

    def _bottom(self, actor_id, observation):
        boxes = actor_boxes(self.actors[actor_id], self.geometry, observation["poses"][actor_id])
        return min(box.center[2]-box.radius_on((0, 0, 1)) for box in boxes)

    def _lifted(self, actor_id, observation):
        pose = observation["poses"][actor_id]
        return pose["position"][2] >= self.actors[actor_id]["position"][2]+self.thresholds["lift_height"]

    def _update_BinFill(self, observation):
        counts = self.parameters["target_counts"]
        board = self.actors["board"]
        board_pose = observation["poses"]["board"]
        hole = float(board.get("hole_half_size", self.geometry.get("hole_side", .080)/2))
        half_height = float(board["half_size"][2])
        grasped = set(observation.get("grasped_ids", ()))
        parked = set(observation.get("parked_ids", ()))
        for actor_id, actor in self.actors.items():
            if actor["kind"] != "cube" or actor_id in self.state.inserted_ids:
                continue
            if actor_id in parked:
                # 停车位不提供“曾在孔外”的证据；显现后必须重新取得资格。
                self.state.eligible_insert_ids.discard(actor_id)
                self.state.stable_counts.pop(actor_id, None)
                continue
            if not actor_occupies_binfill_hole(actor, board, self.geometry, observation["poses"]):
                self.state.eligible_insert_ids.add(actor_id)
            cube = actor_boxes(actor, self.geometry, observation["poses"][actor_id])[0]
            # 所有角点必须落在孔内，而非只看 cube 中心距离。
            vertices = []
            for sx in (-1, 1):
                for sy in (-1, 1):
                    for sz in (-1, 1):
                        vertex = tuple(cube.center[i]+sum(sign*h*axis[i] for sign, h, axis in zip((sx, sy, sz), cube.half_size, cube.axes)) for i in range(3))
                        vertices.append(_local(board_pose, vertex))
            in_hole = (all(abs(v[0]) <= hole-1e-5 and abs(v[1]) <= hole-1e-5 for v in vertices)
                       and max(v[2] for v in vertices) <= half_height+self.thresholds["table_tolerance"]
                       and self._bottom(actor_id, observation) >= -.001
                       and actor_id not in grasped)
            if self._stable(actor_id, observation, in_hole and actor_id in self.state.eligible_insert_ids):
                color = _color_name(actor)
                self.state.inserted_ids.add(actor_id)
                self.state.color_counts[color] = self.state.color_counts.get(color, 0)+1
                if self.state.color_counts[color] > int(counts.get(color, 0)):
                    self._fail(f"投入 {color} 数量超过目标")
        if observation.get("button_pressed", False):
            if any(self.state.color_counts.get(color, 0) != count for color, count in counts.items()):
                self._fail("按钮提前按下，逐色投入数量不匹配")
            elif grasped:
                self._fail("按按钮时仍抓持物体")
            else:
                self.state.completed = True

    def _update_VideoUnmaskSwap(self, observation):
        targets = self.parameters["target_container_ids"]
        grasped = set(observation.get("grasped_ids", ()))
        containers = {name for name, actor in self.actors.items() if actor["kind"] == "container"}
        if grasped-containers:
            self._fail("评测阶段抓取了容器以外的物体")
        current = targets[self.state.cursor] if self.state.cursor < len(targets) else None
        # 已完成的上一个容器可仍在手中，但不能用它再次推进下一个目标。
        allowed = set(targets[:self.state.cursor]) | ({current} if current else set())
        if (grasped & containers)-allowed:
            self._fail("抓取了错误容器或跳过目标顺序")
        if current and current in grasped and self._lifted(current, observation):
            self.state.cursor += 1
        self.state.completed = self.state.cursor == len(targets)

    def _update_VideoRepick(self, observation):
        target = self.parameters["target_ids"][0]
        required = int(self.parameters["repeat_count"])
        grasped = set(observation.get("grasped_ids", ()))
        cubes = {name for name, actor in self.actors.items() if actor["kind"] == "cube"}
        if (grasped & cubes)-{target}:
            self._fail("抓取了非目标方块")
        if target in grasped:
            self.state.stable_counts[target] = 0
            if self._lifted(target, observation):
                self.state.lifted = True
        else:
            bottom = self._bottom(target, observation)
            on_table = abs(bottom) <= self.thresholds["table_tolerance"]
            if self._stable(target, observation, self.state.lifted and on_table):
                self.state.repeat_count += 1
                self.state.lifted = False
                self.state.stable_counts[target] = 0
                if self.state.repeat_count > required:
                    self._fail("重复抓放次数超过目标")
        if observation.get("button_pressed", False):
            if self.state.repeat_count != required or self.state.lifted or target in grasped:
                self._fail("按钮提前按下，尚未完成规定抓放")
            else:
                self.state.completed = True

    def _update_RouteStick(self, observation):
        path = list(self.parameters["path_indices"])
        directions = self.parameters["directions"]
        tcp = tuple(float(x) for x in observation["tcp_position"])
        previous = self.state.last_tcp
        self.state.last_tcp = tcp
        poses = observation["poses"]
        targets = {i: tuple(poses[f"target_{i}"]["position"]) for i in range(5)}
        radius = self.thresholds["target_radius"]
        # 目标是桌面上的平面标记，其渲染中心高度不是棒端必须到达的高度。
        # 正确/错误目标共享同一个 XY 圆盘和独立世界高度范围。
        in_target_height = self.thresholds["route_target_height_min"] <= tcp[2] <= self.thresholds["route_target_height_max"]
        touched = [i for i, p in targets.items()
                   if in_target_height and math.hypot(tcp[0]-p[0], tcp[1]-p[1]) <= radius]
        cursor = self.state.cursor
        if cursor >= len(path):
            self.state.completed = True
            return
        allowed = {path[cursor]}
        if cursor:
            allowed.add(path[cursor-1])
        if set(touched)-allowed:
            self._fail("触达了顺序之外的目标点")
        if previous is not None:
            for actor_id, actor in self.actors.items():
                if actor["kind"] != "obstacle":
                    continue
                if self._segment_hits_box(previous, tcp, actor, poses[actor_id]):
                    self._fail(f"棒端轨迹穿越障碍: {actor_id}")
        if cursor:
            start, end = targets[path[cursor-1]], targets[path[cursor]]
            dx, dy = end[0]-start[0], end[1]-start[1]
            length = math.hypot(dx, dy)
            if length < 1e-12:
                raise ValueError("相邻路径目标不能重合")
            obstacle_id = f"obstacle_{min(path[cursor-1], path[cursor])}"
            obstacle = poses[obstacle_id]["position"]
            extent = _norm(self.actors[obstacle_id]["half_size"][:2])+self.thresholds["stick_radius"]
            # 连续检查相邻样本经过的整个障碍纵向区间，不允许稀疏采样漏掉反侧。
            segment_start = previous if previous is not None else tcp
            along_start = ((segment_start[0]-obstacle[0])*dx+(segment_start[1]-obstacle[1])*dy)/length
            along_end = ((tcp[0]-obstacle[0])*dx+(tcp[1]-obstacle[1])*dy)/length
            low, high = 0.0, 1.0
            delta_along = along_end-along_start
            if abs(delta_along) <= 1e-12:
                if abs(along_start) > extent:
                    low, high = 1.0, 0.0
            else:
                first, last = (-extent-along_start)/delta_along, (extent-along_start)/delta_along
                low, high = max(low, min(first, last)), min(high, max(first, last))
            if low <= high:
                signed_values, heights = [], []
                for progress in (low, high):
                    point = tuple(a+(b-a)*progress for a, b in zip(segment_start, tcp))
                    cross = (dx*(point[1]-obstacle[1])-dy*(point[0]-obstacle[0]))/length
                    signed_values.append(float(directions[cursor-1])*cross)
                    heights.append(abs(point[2]-obstacle[2]))
                if min(signed_values) < -self.thresholds["route_side_tolerance"]:
                    self._fail("从错误侧绕过障碍")
                elif min(signed_values) > extent and max(heights) <= .080:
                    self.state.route_side_seen = True
        if path[cursor] in touched:
            if cursor and not self.state.route_side_seen:
                self._fail("未观察到本段从规定侧完整绕过障碍")
            else:
                self.state.cursor += 1
                self.state.route_side_seen = False
        self.state.completed = self.state.cursor == len(path)

    def _segment_hits_box(self, start, end, actor, pose):
        """棒端相邻样本间也做扫掠，扩张障碍盒包含棒的半径。"""
        a, b = _local(pose, start), _local(pose, end)
        margin = self.thresholds["stick_radius"]
        low, high = 0.0, 1.0
        for i in range(3):
            half = float(actor["half_size"][i])+margin
            delta = b[i]-a[i]
            if abs(delta) < 1e-12:
                if abs(a[i]) > half:
                    return False
                continue
            u, v = (-half-a[i])/delta, (half-a[i])/delta
            low, high = max(low, min(u, v)), min(high, max(u, v))
            if low > high:
                return False
        return True
