"""区分候选不可行、运行失败与复现失败，禁止用换 seed 掩盖错误。"""


class SceneRejected(RuntimeError):
    """当前确定性布局或轨迹不可行，认证阶段可检查同槽下一候选。"""


class TaskExecutionError(SceneRejected):
    """本条候选未能在固定动作规划下正确完成。"""


class ReproducibilityError(RuntimeError):
    """同一场景重复运行不一致，必须停止发布。"""


class CandidateRejected(SceneRejected):
    """认证时的候选布局或任务失败，不可冒充基础设施重试。"""


class InfrastructureError(OSError):
    """工作进程或设备异常，只允许重试同一个规格。"""
