"""容器／方块交换的碰撞判据（vendoring 自 newtask-v2.1refractor，见 ``VENDORED.md``）。

``bin_collision.py`` 逐字节拷贝自 ``hongzefu/robomme_benchmark_MotionJEPA`` 分支 ``newtask-v2.1refractor``
commit ``ce72b04fdb7806dbc98de2baa3c92118b98e6902`` 的 ``src/robomme/robomme_env/utils/bin_collision.py``，
不作任何修改；本包只补两个异常类，让检测失败走生成器既有的 ``SceneGenerationError`` 失败通道
（``failure_class=task``、固定 seed 不重试）。
"""

from __future__ import annotations

from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError

from .bin_collision import *  # noqa: F401,F403  再导出全部公开接口
from .bin_collision import (  # noqa: F401  显式列出常用项，便于静态检查
    EPS_M,
    MAX_DEPTH,
    MAX_INTERVALS,
    BinCollisionError,
    CollisionRejection,
    ObjectState,
    ShapeSpec,
    check_bin_layout,
    check_bin_state,
    check_swap_sweep,
    nearest_partner_index,
    object_state_from_actor,
    shape_specs_from_actor,
)

__all__ = list(globals().get("__all__", [])) + ["SwapCollisionError", "SwapBindingError"]


class SwapCollisionError(SceneGenerationError):
    """碰撞判据拒绝（初态、路径或子步）。``rejection`` 带结构化证据，``stage`` 记在哪一步被拒。"""

    def __init__(self, rejection: CollisionRejection, stage: str) -> None:
        super().__init__(f"[{stage}] {rejection.summary()}")
        self.rejection = rejection
        self.stage = stage


class SwapBindingError(SceneGenerationError):
    """运行时实际最近邻与 reset 时写死的搭档不一致。``detail`` 带距离表等证据。"""

    def __init__(self, detail: dict) -> None:
        super().__init__(
            f"第 {detail.get('sweep_index')} 段实际最近邻 {detail.get('recomputed_partner')} "
            f"≠ 预写搭档 {detail.get('expected_partner')}"
        )
        self.detail = detail
