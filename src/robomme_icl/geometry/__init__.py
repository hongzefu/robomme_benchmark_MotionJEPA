"""不加载仿真库的真实碰撞形状、确定性交换轨迹与连续几何认证。"""

from .collision import (
    Box,
    actor_boxes,
    actor_occupies_binfill_hole,
    box_clearance,
    box_components,
    pose_at_step,
    quaternion_matrix,
    rotate,
    swap_poses,
    validate_spec_geometry,
)

__all__ = [
    "Box", "actor_boxes", "actor_occupies_binfill_hole", "box_clearance", "box_components", "pose_at_step",
    "quaternion_matrix", "rotate", "swap_poses", "validate_spec_geometry",
]
