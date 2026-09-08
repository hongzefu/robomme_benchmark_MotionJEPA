"""新版四任务共享的纯状态判定接口。"""

from .evaluator import TaskEvaluator, TaskState
from .language import language_goal

__all__ = ["TaskEvaluator", "TaskState", "language_goal"]
