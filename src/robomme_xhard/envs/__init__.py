"""导入即注册 14 个派生子类（本文件归主会话）。"""

from .bin_fill import BinFillXHard
from .pick_xtimes import PickXtimesXHard
from .swing_xtimes import SwingXtimesXHard
from .stop_cube import StopCubeXHard
from .video_unmask import VideoUnmaskXHard
from .button_unmask import ButtonUnmaskXHard
from .video_unmask_swap import VideoUnmaskSwapXHard
from .button_unmask_swap import ButtonUnmaskSwapXHard
from .pick_highlight import PickHighlightXHard
from .video_repick import VideoRepickXHard
from .video_place_button import VideoPlaceButtonXHard
from .video_place_order import VideoPlaceOrderXHard
from .pattern_lock import PatternLockXHard
from .route_stick import RouteStickXHard

__all__ = [
    "BinFillXHard",
    "PickXtimesXHard",
    "SwingXtimesXHard",
    "StopCubeXHard",
    "VideoUnmaskXHard",
    "ButtonUnmaskXHard",
    "VideoUnmaskSwapXHard",
    "ButtonUnmaskSwapXHard",
    "PickHighlightXHard",
    "VideoRepickXHard",
    "VideoPlaceButtonXHard",
    "VideoPlaceOrderXHard",
    "PatternLockXHard",
    "RouteStickXHard",
]
