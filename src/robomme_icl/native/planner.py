"""沿用原版执行规划器的实例重试策略，不替换其动作路径。"""

from .imports import OraclePlannerDemonstrationWrapper
from robomme.robomme_env.utils.planner_fail_safe import (
    FailAwarePandaArmMotionPlanningSolver, FailAwarePandaStickMotionPlanningSolver, ScrewPlanFailure,
)


def make_execution_planner(env, task):
    options = dict(debug=False, vis=False, base_pose=env.unwrapped.agent.robot.pose,
                   visualize_target_grasp_pose=False, print_env_info=False)
    planner_class = FailAwarePandaArmMotionPlanningSolver
    if task == "RouteStick":
        planner_class = FailAwarePandaStickMotionPlanningSolver
        options["joint_vel_limits"] = .3
    planner = planner_class(env, **options)
    policy = OraclePlannerDemonstrationWrapper(env, env_id=task, gui_render=False)
    return policy._wrap_planner_with_screw_then_rrt_retry(planner, ScrewPlanFailure)
