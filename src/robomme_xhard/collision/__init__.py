"""交换对象碰撞判据与结构化场景拒绝。"""

from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError
from .bin_collision import *  # noqa: F403
from .bin_collision import CollisionRejection


class SwapCollisionError(SceneGenerationError):
    """初始化几何证明失败，保留原始拒绝证据。"""

    def __init__(self, rejection: CollisionRejection, stage: str):
        self.rejection = rejection
        self.stage = stage
        self.detail = None
        super().__init__(rejection.summary())


class SwapBindingError(SceneGenerationError):
    """交换配对与实际最近邻不一致。"""

    def __init__(self, detail: dict):
        self.detail = detail
        self.stage = "segment_start"
        self.rejection = None
        super().__init__(f"交换配对绑定不一致：{detail}")
