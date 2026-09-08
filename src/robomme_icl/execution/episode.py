"""原版task_list决定动作；此处只编排solve及显式判定的调用顺序。"""

from ..errors import TaskExecutionError
from ..native.imports import OraclePlannerDemonstrationWrapper
from ..io.observations import scalar


def execution_planner(native_wrapper, task):
    """使用原版执行包装器建立规划器和三次screw／三次RRT回退。"""
    from ..native.planner import make_execution_planner
    return make_execution_planner(native_wrapper, task)


def execute_remaining(env):
    base = env.unwrapped
    planner = execution_planner(env.native_wrapper, env.task_kind)
    for entry in base.task_list:
        if entry.get("demonstration", False):
            continue
        env.recorder.evaluate(solve_complete_eval=True)
        result = entry["solve"](env.native_wrapper, planner)
        if isinstance(result, int) and result == -1:
            raise TaskExecutionError(f"原版规划失败：{entry['name']}")
        result = env.recorder.evaluate(solve_complete_eval=True)
        if bool(scalar(result["fail"])):
            raise TaskExecutionError(f"原版任务失败：{entry['name']}")
        if bool(scalar(result["success"])):
            return
    result = env.recorder.evaluate(solve_complete_eval=True)
    if not bool(scalar(result["success"])):
        raise TaskExecutionError("原版task_list执行后未完成")


def run_episode(env):
    env.reset()
    execute_remaining(env)
    return env.recorder.frames
