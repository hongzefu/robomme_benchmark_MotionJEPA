"""四个新版任务共用物理基类，各自使用独立任务判定器。"""

from mani_skill.utils.registration import register_env

from .base import ICLBaseEnv


@register_env("RoboMME-ICL/BinFill-v0")
class BinFill(ICLBaseEnv):
    """按颜色数量填充容器的新版任务。"""
    TASK_KIND = "BinFill"


@register_env("RoboMME-ICL/RouteStick-v0")
class RouteStick(ICLBaseEnv):
    """按演示绕过障碍并访问目标的新版任务。"""
    TASK_KIND = "RouteStick"


@register_env("RoboMME-ICL/VideoUnmaskSwap-v0")
class VideoUnmaskSwap(ICLBaseEnv):
    """追踪交换后的容器身份并抓取的新版任务。"""
    TASK_KIND = "VideoUnmaskSwap"


@register_env("RoboMME-ICL/VideoRepick-v0")
class VideoRepick(ICLBaseEnv):
    """记忆示范目标并完成指定次数抓放的新版任务。"""
    TASK_KIND = "VideoRepick"
