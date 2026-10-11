"""robomme_xhard：在原 16 任务母样本上派生 xhard12..xhard20 五级难度（不改 src/robomme）。

``import robomme_xhard`` 会注册 14 个 ``<Task>XHard`` 子类；必须在绑卡并
``import robomme.robomme_env`` 之后再导入（见生成器 _pool_init / _worker）。
"""

from .configs import (
    DIFFICULTIES,
    SOURCE_DIFFICULTY,
    TIER_CONFIGS,
    XHARD_TASKS,
    env_name,
    is_xhard,
    tier,
    valid_pairs,
)
from . import envs  # noqa: F401  导入即注册

__all__ = [
    "DIFFICULTIES",
    "SOURCE_DIFFICULTY",
    "TIER_CONFIGS",
    "XHARD_TASKS",
    "env_name",
    "is_xhard",
    "tier",
    "valid_pairs",
]
