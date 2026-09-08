"""集中导入原版类，防止任务行为散落成第二份实现。"""

from robomme.robomme_env.BinFill import BinFill as NativeBinFill
from robomme.robomme_env.RouteStick import RouteStick as NativeRouteStick
from robomme.robomme_env.VideoUnmaskSwap import VideoUnmaskSwap as NativeVideoUnmaskSwap
from robomme.robomme_env.VideoRepick import VideoRepick as NativeVideoRepick
from robomme.robomme_env.utils.object_generation import (
    build_bin,
    build_board_with_hole,
    build_button,
    spawn_random_cube,
)
from robomme.env_record_wrapper.DemonstrationWrapper import DemonstrationWrapper
from robomme.env_record_wrapper.OraclePlannerDemonstrationWrapper import (
    OraclePlannerDemonstrationWrapper,
)
from robomme.robomme_env.utils import reset_panda, task_goal

NATIVE_CLASSES = {
    "BinFill": NativeBinFill,
    "RouteStick": NativeRouteStick,
    "VideoUnmaskSwap": NativeVideoUnmaskSwap,
    "VideoRepick": NativeVideoRepick,
}
