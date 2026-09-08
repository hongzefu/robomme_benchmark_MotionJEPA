"""仅供独立对照进程：固定原版源码，只注入获准覆盖的采样输入。

不得用于正式环境创建。本模块不调用新版任务子类或NativePlacements。
模块级替换仅存在于这个隔离验证进程的构造窗口，并在构造后恢复。
"""

from contextlib import contextmanager
import copy
import hashlib
import importlib
import inspect
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from ..io.paths import repository_root
from ..specs import NATIVE_REFERENCE


def load_reference(reference_root):
    """逐个git blob核对，不能把当前源码误作旧版证据。"""
    root = Path(reference_root).resolve()
    if any(name == "robomme" or name.startswith("robomme.") for name in sys.modules):
        raise RuntimeError("原版对照必须在尚未导入robomme的新进程中运行")
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "-z", NATIVE_REFERENCE, "--", "src/robomme"],
        cwd=repository_root(),
        check=True,
        capture_output=True,
    ).stdout
    count = 0
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        metadata, relative = entry.split(b"\t", 1)
        expected = metadata.split()[2].decode()
        path = root / relative.decode()
        data = path.read_bytes()
        actual = hashlib.sha1(
            b"blob " + str(len(data)).encode() + b"\0" + data
        ).hexdigest()
        if actual != expected:
            raise ValueError(f"参考源码偏离固定基线：{relative.decode()}")
        count += 1
    sys.path.insert(0, str(root / "src"))
    return {"commit": NATIVE_REFERENCE, "checked_files": count, "root": str(root)}


@contextmanager
def _fixed_sampling(module, spec):
    """只替换位置采样结果；旧版任务源码和任务函数保持不动。"""
    import sapien

    definition = spec.to_dict()
    parameters = definition["task_parameters"]
    positions = definition["placements"]
    counters = {}
    originals = {}

    def next_point(group):
        index = counters.get(group, 0)
        counters[group] = index + 1
        if group in ("button", "board"):
            field = group
        elif group == "cubes" and definition["layout"]["topology"] == "field":
            field = f"cube_{index}"
        else:
            field = f"{group}_{index}"
        return positions[group][index], definition["layout"]["supports"][field]

    def center(point, bounds):
        return [
            bounds[axis][0]
            + point[f"{axis}_fraction"] * (bounds[axis][1] - bounds[axis][0])
            for axis in ("x", "y")
        ]

    def fit_reference_actor(actor, point, bounds):
        # 几何来自已校验的旧构建器；此处不调用新版参数适配器。
        from ..validation.geometry import actual_boxes
        from mani_skill.utils.structs.pose import Pose

        boxes = actual_boxes(actor)
        pose = actor.pose.sp
        position = list(pose.p)
        for axis, key in enumerate(("x", "y")):
            direction = (1, 0, 0) if axis == 0 else (0, 1, 0)
            lower_offset = (
                min(box.center[axis] - box.radius_on(direction) for box in boxes)
                - position[axis]
            )
            upper_offset = (
                max(box.center[axis] + box.radius_on(direction) for box in boxes)
                - position[axis]
            )
            lower = bounds[key][0] - lower_offset
            upper = bounds[key][1] - upper_offset
            if lower > upper:
                raise ValueError("固定原版素材无法放入允许窗口")
            position[axis] = lower + point[f"{key}_fraction"] * (upper - lower)
        resolved = sapien.Pose(position, pose.q)
        actor.initial_pose = Pose.create(resolved)
        actor.set_pose(resolved)
        return actor

    def replace(name, replacement):
        originals[name] = getattr(module, name)
        setattr(module, name, replacement)

    if spec.task_kind in ("BinFill", "VideoRepick"):
        native_button = module.build_button
        native_cube = module.spawn_random_cube

        def button(env, **kwargs):
            point, bounds = next_point("button")
            if spec.task_kind == "BinFill":
                env.dynamic = parameters["dynamic"]
            else:
                env.num_repeats = parameters["repeat_count"]
            kwargs["center_xy"] = center(point, bounds)
            kwargs["randomize"] = False
            return native_button(env, **kwargs)

        def cube(env, **kwargs):
            point, bounds = next_point("cubes")
            size = kwargs["half_size"]
            provisional = [sum(bounds[axis]) / 2 for axis in ("x", "y")]
            kwargs.update(
                region_center=provisional,
                region_half_size=[size + 1e-9, size + 1e-9],
                avoid=[],
                include_existing=False,
                include_goal=False,
                min_gap=0.0,
                max_trials=1,
            )
            actor = native_cube(env, **kwargs)
            half_angle = math.radians(point["yaw_degrees"]) / 2
            actor.set_pose(
                sapien.Pose(
                    [*provisional, size],
                    [math.cos(half_angle), 0, 0, math.sin(half_angle)],
                )
            )
            return fit_reference_actor(actor, point, bounds)

        replace("build_button", button)
        replace("spawn_random_cube", cube)
    if spec.task_kind == "BinFill":
        native_board = module.build_board_with_hole

        def board(env, **kwargs):
            point, bounds = next_point("board")
            half_angle = math.radians(point["yaw_degrees"]) / 2
            kwargs.update(
                position=[*center(point, bounds), 0.0],
                rotation_quat=[math.cos(half_angle), 0, 0, math.sin(half_angle)],
            )
            return native_board(env, **kwargs)

        replace("build_board_with_hole", board)
    if spec.task_kind == "VideoUnmaskSwap":
        object_generation = importlib.import_module(
            "robomme.robomme_env.utils.object_generation"
        )

        def container(env, **kwargs):
            point, bounds = next_point("containers")
            provisional = [sum(bounds[axis]) / 2 for axis in ("x", "y")]
            actor = object_generation.build_bin(
                env,
                callsign=kwargs["name_prefix"],
                position=[*provisional, 0.002],
                z_rotation_deg=point["yaw_degrees"],
            )
            return fit_reference_actor(actor, point, bounds)

        replace("spawn_random_bin", container)
    if spec.task_kind == "RouteStick":
        proxy = SimpleNamespace(**{name: getattr(math, name) for name in dir(math)})
        proxy.radians = lambda _: math.radians(definition["layout"]["yaw_degrees"])
        replace("math", proxy)
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(module, name, value)


def make_reference_env(spec, render_gpu):
    import gymnasium as gym
    import sapien

    module = importlib.import_module(f"robomme.robomme_env.{spec.task_kind}")
    cls = getattr(module, spec.task_kind)
    if "reference-v1" not in Path(inspect.getfile(cls)).parts:
        raise RuntimeError("实际加载的任务类不是固定参考副本")
    params = spec.task_parameters
    original_configs = cls.configs
    configs = copy.deepcopy(original_configs)
    if spec.task_kind == "BinFill":
        configs[spec.difficulty] = dict(
            color=params["scene_color_count"],
            spawn_cubes=[params["spawn_count"]] * 2,
            put_in_color=[params["target_color_count"]] * 2,
            put_in_numbers=[params["pick_count"]] * 2,
        )
    elif spec.task_kind == "RouteStick":
        configs[spec.difficulty] = dict(
            length=[params["walk_steps"]] * 2, backtrack=params["allow_backtracking"]
        )
    elif spec.task_kind == "VideoUnmaskSwap":
        configs[spec.difficulty] = dict(
            bin=params["container_count"],
            pick_min=params["pick_count"],
            pick_max=params["pick_count"],
            swap_min=params["swap_count"],
            swap_max=params["swap_count"],
        )
    else:
        configs[spec.difficulty] = dict(
            cube=params["spawn_count"],
            swap_min=params["swap_count"],
            swap_max=params["swap_count"],
        )
    cls.configs = configs
    try:
        with _fixed_sampling(module, spec):
            raw = gym.make(
                spec.task_kind,
                seed=spec.seed,
                difficulty=spec.difficulty,
                num_envs=1,
                obs_mode="rgb+depth+segmentation",
                control_mode="pd_joint_pos",
                render_mode="rgb_array",
                sim_backend="physx_cpu",
                render_backend=f"cuda:{render_gpu}",
                reward_mode="dense",
            )
    finally:
        cls.configs = original_configs
    if spec.task_kind == "RouteStick":
        layout = spec.to_dict()["layout"]
        angle = math.radians(layout["yaw_degrees"])
        for index, target in enumerate(raw.unwrapped.buttons_grid):
            x = layout["center"][0]
            y = layout["center"][1] + (index - 4) * layout["spacing"]
            position = [
                x * math.cos(angle) - y * math.sin(angle),
                x * math.sin(angle) + y * math.cos(angle),
            ]
            target.set_pose(
                sapien.Pose(
                    [*position, 0.01 if index % 2 == 0 else -0.01],
                    target.pose.q[0].cpu().numpy(),
                )
            )
            if index % 2:
                obstacle = raw.unwrapped.target_cubes[index]
                obstacle.set_pose(
                    sapien.Pose([*position, 0.05], obstacle.pose.q[0].cpu().numpy())
                )
    return raw


def run_reference_episode(spec, render_gpu, *, probe=None):
    """独立编排固定原版包装器；不调用新版环境适配或执行模块。"""
    from robomme.env_record_wrapper.DemonstrationWrapper import DemonstrationWrapper
    from robomme.env_record_wrapper.OraclePlannerDemonstrationWrapper import (
        OraclePlannerDemonstrationWrapper,
    )
    from robomme.robomme_env.utils.planner_fail_safe import (
        FailAwarePandaArmMotionPlanningSolver,
        FailAwarePandaStickMotionPlanningSolver,
        ScrewPlanFailure,
    )
    from ..execution.recording import RecordingEnv
    from ..validation.geometry import validate_scene_geometry

    raw = make_reference_env(spec, render_gpu)
    recorder = RecordingEnv(raw)
    wrapper = DemonstrationWrapper(
        recorder,
        max_steps_without_demonstration=10000,
        gui_render=False,
        include_maniskill_obs=True,
    )
    recorder.delivery_context = wrapper
    try:
        geometry = validate_scene_geometry(raw.unwrapped, spec)
        if not geometry["ok"]:
            raise ValueError(f"参考场景不满足配置筛选：{geometry}")
        wrapper.reset(seed=spec.seed)
        marker = recorder.reset_marker()
        marker["info"]["geometry_report"] = geometry
        if probe is not None:
            from .probes import execute_probe

            adapter = SimpleNamespace(
                unwrapped=raw.unwrapped,
                native_wrapper=wrapper,
                recorder=recorder,
                task_kind=spec.task_kind,
            )
            execute_probe(adapter, probe)
            return recorder.frames, dict(recorder.runtime_names)
        options = dict(
            debug=False,
            vis=False,
            base_pose=raw.unwrapped.agent.robot.pose,
            visualize_target_grasp_pose=False,
            print_env_info=False,
        )
        planner_cls = FailAwarePandaArmMotionPlanningSolver
        if spec.task_kind == "RouteStick":
            planner_cls = FailAwarePandaStickMotionPlanningSolver
            options["joint_vel_limits"] = 0.3
        planner = planner_cls(wrapper, **options)
        policy = OraclePlannerDemonstrationWrapper(
            wrapper, env_id=spec.task_kind, gui_render=False
        )
        policy._wrap_planner_with_screw_then_rrt_retry(planner, ScrewPlanFailure)
        for task in raw.unwrapped.task_list:
            if task["demonstration"]:
                continue
            recorder.evaluate(solve_complete_eval=True)
            result = task["solve"](wrapper, planner)
            if isinstance(result, int) and result == -1:
                raise RuntimeError(f"原版solve失败：{task['name']}")
            evaluated = recorder.evaluate(solve_complete_eval=True)
            if bool(evaluated["fail"].item()):
                raise RuntimeError(f"原版失败：{task['name']}")
            if bool(evaluated["success"].item()):
                return recorder.frames, dict(recorder.runtime_names)
        raise RuntimeError("原版全部subgoal执行后未完成")
    finally:
        wrapper.close()
