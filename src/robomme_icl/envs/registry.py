"""四个独立ID显式注册；不覆盖原版十六任务。"""

from mani_skill.utils.registration import REGISTERED_ENVS, register_env

from .bin_fill import ICLBinFill
from .route_stick import ICLRouteStick
from .video_unmask_swap import ICLVideoUnmaskSwap
from .video_repick import ICLVideoRepick

ENVIRONMENT_CLASSES = {
    "BinFill": ICLBinFill,
    "RouteStick": ICLRouteStick,
    "VideoUnmaskSwap": ICLVideoUnmaskSwap,
    "VideoRepick": ICLVideoRepick,
}


def register_envs():
    for task, cls in ENVIRONMENT_CLASSES.items():
        identifier = f"RoboMME-ICL/{task}-v0"
        existing = REGISTERED_ENVS.get(identifier)
        if existing is None:
            register_env(identifier)(cls)
        elif existing.cls is not cls:
            raise RuntimeError(f"注册ID已被其他实现占用：{identifier}")
