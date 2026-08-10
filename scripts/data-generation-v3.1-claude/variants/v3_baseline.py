"""对照基线：v3-claude 算法原样（无物体零误删保证、无黑指尖保留）。

只作为对照与渲染链路冒烟用——它**不满足** v3.1 的两条硬约束，不参与胜出评选。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cv_base import ArmRemovalParams, compute_arm_masks  # noqa: E402

NAME = "v3_baseline"
DESCRIPTION = "v3-claude 默认参数原样跑（对照基线，无零误删保证、无指尖保留）"

_PARAMS_PATH = Path(__file__).resolve().parents[1] / "cv_base_params.json"


def compute_masks(
    frames: np.ndarray, phase_flags: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    params = ArmRemovalParams.from_json(_PARAMS_PATH)
    masks, stats = compute_arm_masks(frames, phase_flags, params)
    tips = np.zeros_like(masks)
    return masks, tips, stats
