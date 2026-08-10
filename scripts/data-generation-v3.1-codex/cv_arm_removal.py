#!/usr/bin/env python3
"""使用通用 RGB / RGB-D 规则删除固定相机画面中的机械臂。

本模块刻意不读取仿真 segmentation、物体名字、机器人句柄或任何任务语义。生产规则只使用：

1. Panda 机械臂在 RGB 中近似无彩色（HSV 低饱和度）；
2. 机械臂从画面顶部或左右边缘进入，而桌上独立物体通常不接触画面边缘；
3. 有深度图时，木桌可以由棕色像素拟合成平面，机械臂位于该平面前方；
4. 独立 RGB-D 前景的时序外观和细颈区域可以保护后来与机械臂接触的任务物体；
5. 普通双指夹爪的黑色指尖表现为稳定成对的小暗块轨迹，stick 没有该豁免；
6. 相机与桌面静止，同一 episode 的其他帧可以提供被机械臂遮挡处的真实桌面纹理。

顶层入口是 :func:`remove_robot_arm_sequence`。它返回删除后的 RGB、逐帧布尔 mask、时序背景图，
以及可以直接写入 JSON 的审计字典。实现保证 mask 之外的输入像素不经任何颜色转换或重采样，
而是从原数组复制后只给 mask 内位置赋值，因此逐位保持不变。

运行时依赖仅为 ``numpy`` 与 ``cv2``，所有阈值和审计结构均定义在本模块内。
"""

from __future__ import annotations

import math
import warnings
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import cv2
import numpy as np


SCHEMA_VERSION = "cv-arm-removal-v1"


@dataclass(frozen=True)
class ArmRemovalConfig:
    """机械臂检测与背景回填参数。

    比例参数相对输入分辨率解释，因此默认值既适用于原始 256×256 图，也适用于等比例尺寸。
    形态学核仍使用像素单位；默认值针对 256×256 原图，且强制要求为正奇数。
    """

    # 机械臂是近似灰色；OpenCV HSV 的 saturation 范围是 [0, 255]。
    arm_saturation_max: int = 30

    # 木桌颜色筛选，用来拟合深度平面。OpenCV HSV 的 hue 范围是 [0, 179]。
    table_hue_max: int = 25
    table_saturation_min: int = 110
    table_value_min: int = 60
    table_fit_min_y_ratio: float = 0.06
    table_fit_min_pixels: int = 512
    table_fit_trim_quantile: float = 0.75
    table_fit_iterations: int = 3

    # 深度单位沿用 RoboMME HDF5 的毫米。小于该高度差的不当作桌面前景。
    depth_front_margin_mm: float = 8.0

    # 机械臂必须接近上边缘，或直接接触左右边缘。上边缘留出一定容差来跨过灰色地面横带。
    top_anchor_ratio: float = 0.115
    side_anchor_ratio: float = 0.012
    min_component_area_ratio: float = 20.0 / (256.0 * 256.0)

    # 无深度时先忽略最顶部灰色远景，再从裁切后的边缘寻找机械臂，最后只在入口列附近向上补回。
    rgb_only_top_ignore_ratio: float = 0.065
    rgb_only_upper_recover_margin_ratio: float = 0.035

    # v3.1 默认不扩张候选，避免闭运算和膨胀吞入与夹爪接触的任务物体。
    close_kernel_size: int = 5
    close_iterations: int = 0
    dilate_kernel_size: int = 3
    dilate_iterations: int = 0

    # v2.1 的黑色色块定义：三个 uint8 通道之和不超过 3 * 100。
    black_luminance_max: int = 100

    # episode 类型只由稳定成对的小暗块判断，不读取任务或机器人类型。
    gripper_pair_component_area_max: int = 60
    gripper_pair_distance_min: float = 3.0
    gripper_pair_distance_max: float = 35.0
    gripper_pair_area_ratio_min: float = 0.30
    gripper_pair_minimum_frames: int = 12
    gripper_pair_minimum_frame_fraction: float = 0.05
    # stick 需要稳定的大型细长暗块作为正证据；不能把“未识别双指”直接等同 stick。
    stick_component_area_min: int = 80
    stick_component_aspect_ratio_min: float = 4.0
    stick_minimum_frames: int = 12
    stick_minimum_frame_fraction: float = 0.05

    # 高置信锚点比跟踪候选更严格；顶部特判覆盖末端停在入口带内的 episode。
    tip_candidate_area_max: int = 160
    tip_candidate_width_max: int = 12
    tip_candidate_height_max: int = 20
    tip_candidate_boundary_min: float = 0.10
    tip_candidate_terminal_min: float = 0.30
    tip_anchor_area_max: int = 100
    tip_anchor_width_max: int = 10
    tip_anchor_height_max: int = 16
    tip_anchor_boundary_min: float = 0.30
    tip_anchor_terminal_min: float = 0.45
    tip_anchor_pair_distance_min: float = 3.0
    tip_anchor_pair_distance_max: float = 45.0
    tip_anchor_pair_area_ratio_min: float = 0.50

    # 相邻帧只连接相互前 K 近邻，允许两块指尖短暂合并后再次分开。
    tip_motion_base_pixels: float = 3.0
    tip_motion_pixels_per_frame: float = 12.0
    tip_transition_area_ratio_min: float = 0.10
    tip_mutual_nearest_k: int = 2
    tip_minimum_track_anchor_frames: int = 2
    tip_minimum_track_frames: int = 12
    tip_minimum_track_frame_fraction: float = 0.05
    tip_maximum_tracks: int = 2
    # 独立 RGB-D 前景必须与机械臂保持间隔，才可作为物体外观证据。
    object_detached_arm_margin_radius: int = 3
    object_detached_area_min: int = 30
    object_detached_area_max: int = 4000
    object_detached_border_margin: int = 2

    # 高置信大细颈与更小的时序候选采用不同腐蚀半径和 core 面积。
    object_high_confidence_erosion_radius: int = 2
    object_high_confidence_core_area_min: int = 180
    object_temporal_erosion_radius: int = 3
    object_temporal_core_area_min: int = 20

    # 接触 basin 必须在多个分离帧中匹配 RGB 外观与二维形状。
    object_histogram_l1_max: float = 0.18
    object_mean_rgb_distance_max: float = 0.08
    object_log_area_delta_max: float = 0.45
    object_log_aspect_delta_max: float = 0.45
    object_extent_delta_max: float = 0.18
    object_minimum_match_frames: int = 8
    object_minimum_match_frame_fraction: float = 0.015
    object_minimum_match_frame_gap: int = 3
    # 精确颜色仅在多个独立帧重复出现后，才保护相近面积的同色连通分量。
    object_color_minimum_pixels: int = 20
    object_color_minimum_frames: int = 4
    object_color_minimum_frame_fraction: float = 0.01
    object_color_minimum_detached_fraction: float = 0.18
    object_color_minimum_detached_fraction_without_gripper: float = 0.60
    object_color_component_area_min: int = 8
    object_color_component_area_max_ratio: float = 4.0

    # episode 级背景板最多使用这些均匀抽样帧；从未显露的像素交给 Telea。
    temporal_sample_count: int = 64
    # 逐行木桌支持率连续达到该阈值后，认定进入桌面区域；桌面背景只接受木桌 HSV 像素。
    background_desktop_min_wood_fraction: float = 0.35
    background_desktop_required_rows: int = 3
    # 无时序样本的洞优先从同一行搜索完整纹理段；搜索半径相对图像宽度解释。
    background_patch_max_search_ratio: float = 0.50
    background_patch_distance_weight: float = 0.08
    inpaint_radius: float = 5.0


@dataclass(frozen=True)
class ArmRemovalResult:
    """一次 episode 机械臂删除的完整结果。"""

    frames: np.ndarray
    masks: np.ndarray
    background: np.ndarray
    stats: dict[str, Any]
    config: dict[str, Any]

    @property
    def removed_rgb(self) -> np.ndarray:
        """兼容描述性字段名；新调用统一使用 ``frames``。"""

        return self.frames

    @property
    def background_rgb(self) -> np.ndarray:
        """兼容描述性字段名；新调用统一使用 ``background``。"""

        return self.background

    @property
    def audit(self) -> dict[str, Any]:
        """把参数与统计合并成一份可直接 JSON 序列化的审计快照。"""

        return {
            "schema_version": SCHEMA_VERSION,
            "parameters": dict(self.config),
            **self.stats,
        }


def _validate_config(config: ArmRemovalConfig) -> None:
    """尽早拒绝会产生空 mask、非法 OpenCV 核或不可解释审计结果的参数。"""

    if not 0 <= config.arm_saturation_max <= 255:
        raise ValueError("arm_saturation_max 必须位于 [0, 255]")
    if not 0 <= config.table_hue_max <= 179:
        raise ValueError("table_hue_max 必须位于 [0, 179]")
    if not 0 <= config.table_saturation_min <= 255:
        raise ValueError("table_saturation_min 必须位于 [0, 255]")
    if not 0 <= config.table_value_min <= 255:
        raise ValueError("table_value_min 必须位于 [0, 255]")
    if not 0 <= config.black_luminance_max <= 255:
        raise ValueError("black_luminance_max 必须位于 [0, 255]")
    if config.table_fit_min_pixels < 3:
        raise ValueError("table_fit_min_pixels 至少为 3")
    if not 0.0 < config.table_fit_trim_quantile <= 1.0:
        raise ValueError("table_fit_trim_quantile 必须位于 (0, 1]")
    if config.table_fit_iterations < 0:
        raise ValueError("table_fit_iterations 不能为负数")
    if config.depth_front_margin_mm < 0.0:
        raise ValueError("depth_front_margin_mm 不能为负数")
    for name in (
        "table_fit_min_y_ratio",
        "top_anchor_ratio",
        "side_anchor_ratio",
        "min_component_area_ratio",
        "rgb_only_top_ignore_ratio",
        "rgb_only_upper_recover_margin_ratio",
        "background_desktop_min_wood_fraction",
        "background_patch_max_search_ratio",
        "gripper_pair_area_ratio_min",
        "gripper_pair_minimum_frame_fraction",
        "stick_minimum_frame_fraction",
        "tip_candidate_boundary_min",
        "tip_candidate_terminal_min",
        "tip_anchor_boundary_min",
        "tip_anchor_terminal_min",
        "tip_anchor_pair_area_ratio_min",
        "tip_transition_area_ratio_min",
        "tip_minimum_track_frame_fraction",
        "object_minimum_match_frame_fraction",
        "object_color_minimum_frame_fraction",
        "object_color_minimum_detached_fraction",
        "object_color_minimum_detached_fraction_without_gripper",
    ):
        value = float(getattr(config, name))
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} 必须位于 [0, 1]")
    for name in ("close_kernel_size", "dilate_kernel_size"):
        value = int(getattr(config, name))
        if value <= 0 or value % 2 == 0:
            raise ValueError(f"{name} 必须是正奇数")
    if config.close_iterations < 0 or config.dilate_iterations < 0:
        raise ValueError("形态学迭代次数不能为负数")
    for name in (
        "gripper_pair_component_area_max",
        "gripper_pair_minimum_frames",
        "stick_component_area_min",
        "stick_minimum_frames",
        "tip_candidate_area_max",
        "tip_candidate_width_max",
        "tip_candidate_height_max",
        "tip_anchor_area_max",
        "tip_anchor_width_max",
        "tip_anchor_height_max",
        "tip_mutual_nearest_k",
        "tip_minimum_track_anchor_frames",
        "tip_minimum_track_frames",
        "tip_maximum_tracks",
        "object_detached_arm_margin_radius",
        "object_detached_area_min",
        "object_detached_area_max",
        "object_high_confidence_erosion_radius",
        "object_high_confidence_core_area_min",
        "object_temporal_erosion_radius",
        "object_temporal_core_area_min",
        "object_minimum_match_frames",
        "object_minimum_match_frame_gap",
        "object_color_minimum_pixels",
        "object_color_minimum_frames",
        "object_color_component_area_min",
    ):
        value = int(getattr(config, name))
        if value <= 0:
            raise ValueError(f"{name} 必须为正数")

    if config.object_detached_border_margin < 0:
        raise ValueError("object_detached_border_margin 不能为负数")
    if config.object_detached_area_max < config.object_detached_area_min:
        raise ValueError("object_detached_area 范围非法")
    for name in (
        "object_histogram_l1_max",
        "object_mean_rgb_distance_max",
        "object_log_area_delta_max",
        "object_log_aspect_delta_max",
        "object_extent_delta_max",
    ):
        value = float(getattr(config, name))
        if value < 0.0:
            raise ValueError(f"{name} 不能为负数")
    if config.object_color_component_area_max_ratio <= 0.0:
        raise ValueError("object_color_component_area_max_ratio 必须为正数")
    if (
        config.gripper_pair_distance_min < 0.0
        or config.gripper_pair_distance_max < config.gripper_pair_distance_min
    ):
        raise ValueError("gripper_pair 距离范围非法")
    if (
        config.tip_anchor_pair_distance_min < 0.0
        or config.tip_anchor_pair_distance_max < config.tip_anchor_pair_distance_min
    ):
        raise ValueError("tip_anchor_pair 距离范围非法")
    if config.stick_component_aspect_ratio_min <= 0.0:
        raise ValueError("stick_component_aspect_ratio_min 必须为正数")
    if config.tip_motion_base_pixels < 0.0 or config.tip_motion_pixels_per_frame < 0.0:
        raise ValueError("tip 时序运动距离不能为负数")
    if config.temporal_sample_count <= 0:
        raise ValueError("temporal_sample_count 必须为正数")
    if config.background_desktop_required_rows <= 0:
        raise ValueError("background_desktop_required_rows 必须为正数")
    if config.background_patch_distance_weight < 0.0:
        raise ValueError("background_patch_distance_weight 不能为负数")
    if config.inpaint_radius <= 0.0:
        raise ValueError("inpaint_radius 必须为正数")


def normalize_episode_inputs(
    rgb_frames: np.ndarray | Sequence[np.ndarray],
    depth_frames: np.ndarray | Sequence[np.ndarray] | None = None,
) -> tuple[np.ndarray, np.ndarray | None]:
    """把 episode 输入规范成 ``RGB[T,H,W,3]`` 与可选 ``depth[T,H,W]``。

    RGB 必须已经是 ``uint8``；本模块不做隐式量化，因为隐式转换会破坏“未命中像素逐位不变”的
    契约。深度允许任意数值 dtype，逐帧拟合时才临时转成 float64。
    """

    rgb = np.asarray(rgb_frames)
    if rgb.ndim != 4 or rgb.shape[-1] != 3:
        raise ValueError(f"rgb_frames 必须是 [T,H,W,3]，收到 {rgb.shape}")
    if rgb.shape[0] <= 0 or rgb.shape[1] <= 0 or rgb.shape[2] <= 0:
        raise ValueError(f"rgb_frames 不能包含空维度，收到 {rgb.shape}")
    if rgb.dtype != np.uint8:
        raise ValueError(f"rgb_frames dtype 必须是 uint8，收到 {rgb.dtype}")

    if depth_frames is None:
        return rgb, None

    depth = np.asarray(depth_frames)
    if depth.ndim == 4 and depth.shape[-1] == 1:
        depth = depth[..., 0]
    if depth.ndim != 3:
        raise ValueError(f"depth_frames 必须是 [T,H,W] 或 [T,H,W,1]，收到 {depth.shape}")
    if depth.shape != rgb.shape[:3]:
        raise ValueError(
            "depth_frames 与 rgb_frames 的 T/H/W 不一致："
            f"{depth.shape} vs {rgb.shape[:3]}"
        )
    if not np.issubdtype(depth.dtype, np.number):
        raise ValueError(f"depth_frames 必须是数值 dtype，收到 {depth.dtype}")
    return rgb, depth


def fit_table_depth_plane(
    rgb: np.ndarray,
    depth: np.ndarray,
    config: ArmRemovalConfig | None = None,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """用木桌颜色像素拟合整幅图的桌面深度，返回 ``[H,W]`` 毫米深度图。

    对固定针孔相机观察到的平面，逆深度可写成像素坐标的仿射函数，因此拟合
    ``1 / depth = a*x + b*y + c``。每轮只保留残差较小的分位数，降低彩色任务物体偶然落入
    木桌 HSV 阈值时的影响。拟合失败时返回 ``None``，调用方自动退回纯 RGB 规则。
    """

    cfg = config or ArmRemovalConfig()
    _validate_config(cfg)
    frame = np.asarray(rgb)
    depth_array = np.asarray(depth)
    if frame.ndim != 3 or frame.shape[-1] != 3 or frame.dtype != np.uint8:
        raise ValueError("rgb 必须是 uint8 [H,W,3]")
    if depth_array.ndim == 3 and depth_array.shape[-1] == 1:
        depth_array = depth_array[..., 0]
    if depth_array.shape != frame.shape[:2]:
        raise ValueError(f"depth 与 rgb 分辨率不一致：{depth_array.shape} vs {frame.shape[:2]}")

    depth_float = depth_array.astype(np.float64, copy=False)
    height, width = depth_float.shape
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    hue, saturation, value = cv2.split(hsv)
    y_grid, x_grid = np.indices((height, width), dtype=np.float64)
    min_y = min(height - 1, int(round(height * cfg.table_fit_min_y_ratio)))

    valid_depth = np.isfinite(depth_float) & (depth_float > 0.0)
    table_color = (
        (hue <= cfg.table_hue_max)
        & (saturation >= cfg.table_saturation_min)
        & (value >= cfg.table_value_min)
        & (y_grid >= min_y)
    )
    candidates = valid_depth & table_color
    candidate_count = int(np.count_nonzero(candidates))
    audit: dict[str, Any] = {
        "used": False,
        "candidate_pixels": candidate_count,
        "minimum_required": int(cfg.table_fit_min_pixels),
        "min_y": int(min_y),
        "reason": "",
    }
    if candidate_count < cfg.table_fit_min_pixels:
        audit["reason"] = "insufficient_table_color_pixels"
        return None, audit

    design = np.column_stack(
        (
            x_grid[candidates],
            y_grid[candidates],
            np.ones(candidate_count, dtype=np.float64),
        )
    )
    inverse_depth = 1.0 / depth_float[candidates]
    try:
        coefficients = np.linalg.lstsq(design, inverse_depth, rcond=None)[0]
        kept = np.ones(candidate_count, dtype=bool)
        for _ in range(cfg.table_fit_iterations):
            residual = np.abs(design @ coefficients - inverse_depth)
            threshold = float(np.quantile(residual, cfg.table_fit_trim_quantile))
            kept = residual <= threshold
            if int(np.count_nonzero(kept)) < 3:
                audit["reason"] = "too_few_inliers"
                return None, audit
            coefficients = np.linalg.lstsq(
                design[kept], inverse_depth[kept], rcond=None
            )[0]
    except np.linalg.LinAlgError:
        audit["reason"] = "linear_algebra_error"
        return None, audit

    fitted_inverse = (
        coefficients[0] * x_grid + coefficients[1] * y_grid + coefficients[2]
    )
    if not np.all(np.isfinite(fitted_inverse)) or np.any(fitted_inverse <= 0.0):
        audit["reason"] = "non_positive_fitted_inverse_depth"
        return None, audit

    fitted_depth = (1.0 / fitted_inverse).astype(np.float32)
    final_residual = np.abs(design[kept] @ coefficients - inverse_depth[kept])
    audit.update(
        {
            "used": True,
            "reason": "ok",
            "inlier_pixels": int(np.count_nonzero(kept)),
            "coefficients_inverse_depth": [float(item) for item in coefficients],
            "inverse_depth_residual_median": float(np.median(final_residual)),
            "inverse_depth_residual_p95": float(np.quantile(final_residual, 0.95)),
            "fitted_depth_min_mm": float(np.min(fitted_depth)),
            "fitted_depth_max_mm": float(np.max(fitted_depth)),
        }
    )
    return fitted_depth, audit


def _component_entry_labels(
    labels: np.ndarray,
    stats: np.ndarray,
    config: ArmRemovalConfig,
    *,
    top_offset: int = 0,
) -> tuple[list[int], list[dict[str, int]]]:
    """找出从顶部或左右画面边缘进入的候选连通分量。"""

    height, width = labels.shape
    full_height = height + top_offset
    top_limit = max(0, int(round(full_height * config.top_anchor_ratio)) - top_offset)
    side_limit = max(1, int(round(width * config.side_anchor_ratio)))
    minimum_area = max(
        1, int(round(full_height * width * config.min_component_area_ratio))
    )

    selected: list[int] = []
    details: list[dict[str, int]] = []
    for label in range(1, stats.shape[0]):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        component_width = int(stats[label, cv2.CC_STAT_WIDTH])
        component_height = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < minimum_area:
            continue
        right = x + component_width
        enters_top = y <= top_limit
        enters_left = x <= side_limit
        enters_right = right >= width - side_limit
        if not (enters_top or enters_left or enters_right):
            continue
        selected.append(label)
        details.append(
            {
                "label": int(label),
                "x": x,
                "y": y + top_offset,
                "width": component_width,
                "height": component_height,
                "area": area,
            }
        )
    return selected, details


def _recover_rgb_only_upper_entry(
    mask: np.ndarray,
    low_saturation: np.ndarray,
    ignored_rows: int,
    config: ArmRemovalConfig,
) -> np.ndarray:
    """无深度模式下，只沿已选机械臂的入口列向上补回顶部像素。

    直接把顶部低饱和区域加入 mask 会吞掉整条灰色远景。本函数从裁切边界附近已确认的机械臂像素
    推导横向入口区间，只在该区间内恢复顶部低饱和像素。
    """

    if ignored_rows <= 0 or not np.any(mask):
        return mask
    height, width = mask.shape
    probe_end = min(height, ignored_rows + max(2, int(round(height * 0.04))))
    probe = mask[ignored_rows:probe_end]
    columns = np.flatnonzero(np.any(probe, axis=0))
    if columns.size == 0:
        return mask
    margin = max(1, int(round(width * config.rgb_only_upper_recover_margin_ratio)))
    left = max(0, int(columns.min()) - margin)
    right = min(width, int(columns.max()) + margin + 1)
    recovered = mask.copy()
    recovered[:ignored_rows, left:right] |= low_saturation[:ignored_rows, left:right]
    return recovered


def detect_arm_mask(
    rgb: np.ndarray,
    depth: np.ndarray | None = None,
    config: ArmRemovalConfig | None = None,
    *,
    fitted_table_depth: np.ndarray | None = None,
    fitted_table_audit: Mapping[str, Any] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """检测一帧机械臂，返回 ``bool[H,W]`` mask 与逐帧审计信息。

    有深度时先用桌面平面排除木桌和顶部远景；没有深度或平面拟合失败时，退回“裁掉顶部灰带后
    从边缘选低饱和连通分量”的纯 RGB 规则。两条路径最后使用相同的闭运算和膨胀。
    """

    cfg = config or ArmRemovalConfig()
    _validate_config(cfg)
    frame = np.asarray(rgb)
    if frame.ndim != 3 or frame.shape[-1] != 3 or frame.dtype != np.uint8:
        raise ValueError("rgb 必须是 uint8 [H,W,3]")

    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    saturation = hsv[..., 1]
    low_saturation = saturation <= cfg.arm_saturation_max
    candidate = low_saturation.copy()
    table_fit_audit: dict[str, Any] = {
        "used": False,
        "reason": "depth_not_provided",
    }
    mode = "rgb_only"
    ignored_rows = 0

    if depth is not None:
        depth_array = np.asarray(depth)
        if depth_array.ndim == 3 and depth_array.shape[-1] == 1:
            depth_array = depth_array[..., 0]
        if depth_array.shape != (height, width):
            raise ValueError(
                f"depth 与 rgb 分辨率不一致：{depth_array.shape} vs {(height, width)}"
            )
        if fitted_table_depth is None:
            table_depth, table_fit_audit = fit_table_depth_plane(frame, depth_array, cfg)
        else:
            table_depth = np.asarray(fitted_table_depth)
            if table_depth.shape != (height, width):
                raise ValueError(
                    "fitted_table_depth 与 rgb 分辨率不一致："
                    f"{table_depth.shape} vs {(height, width)}"
                )
            table_fit_audit = dict(
                fitted_table_audit
                or {"used": True, "reason": "provided_fitted_table_depth"}
            )
        if table_depth is not None:
            depth_float = depth_array.astype(np.float64, copy=False)
            valid_depth = np.isfinite(depth_float) & (depth_float > 0.0)
            in_front_of_table = (
                valid_depth
                & ((table_depth.astype(np.float64) - depth_float) >= cfg.depth_front_margin_mm)
            )
            candidate &= in_front_of_table
            mode = "rgb_depth"

    if mode == "rgb_only":
        ignored_rows = min(
            height - 1, max(0, int(round(height * cfg.rgb_only_top_ignore_ratio)))
        )
        component_input = candidate[ignored_rows:]
        top_offset = ignored_rows
    else:
        component_input = candidate
        top_offset = 0

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        component_input.astype(np.uint8), connectivity=8
    )
    selected_labels, selected_details = _component_entry_labels(
        labels, stats, cfg, top_offset=top_offset
    )
    selected_crop = np.isin(labels, np.asarray(selected_labels, dtype=np.int32))
    mask = np.zeros((height, width), dtype=bool)
    mask[top_offset:] = selected_crop
    if mode == "rgb_only":
        mask = _recover_rgb_only_upper_entry(mask, low_saturation, ignored_rows, cfg)

    raw_mask_pixels = int(np.count_nonzero(mask))
    if cfg.close_iterations > 0 and raw_mask_pixels > 0:
        close_kernel = np.ones(
            (cfg.close_kernel_size, cfg.close_kernel_size), dtype=np.uint8
        )
        mask = cv2.morphologyEx(
            mask.astype(np.uint8),
            cv2.MORPH_CLOSE,
            close_kernel,
            iterations=cfg.close_iterations,
        ).astype(bool)
    if cfg.dilate_iterations > 0 and np.any(mask):
        dilate_kernel = np.ones(
            (cfg.dilate_kernel_size, cfg.dilate_kernel_size), dtype=np.uint8
        )
        mask = cv2.dilate(
            mask.astype(np.uint8),
            dilate_kernel,
            iterations=cfg.dilate_iterations,
        ).astype(bool)

    final_mask_pixels = int(np.count_nonzero(mask))
    audit = {
        "mode": mode,
        "candidate_pixels": int(np.count_nonzero(candidate)),
        "low_saturation_pixels": int(np.count_nonzero(low_saturation)),
        "connected_component_count": int(max(0, component_count - 1)),
        "selected_components": selected_details,
        "selected_component_count": len(selected_details),
        "raw_mask_pixels": raw_mask_pixels,
        "mask_pixels": final_mask_pixels,
        "mask_fraction": float(final_mask_pixels / (height * width)),
        "rgb_only_ignored_top_rows": int(ignored_rows),
        "table_depth_fit": table_fit_audit,
    }
    return mask, audit


@dataclass(frozen=True)
class _RegionFeature:
    """一个纯 RGB-D 前景区域的外观与二维形状特征。"""

    frame_index: int
    pixels: np.ndarray
    area: int
    histogram: np.ndarray
    mean_rgb: np.ndarray
    log_area: float
    log_aspect: float
    extent: float


@dataclass
class _ColorEvidence:
    """一种精确 RGB 颜色在独立物体区域内的跨帧证据。"""

    frames: set[int]
    total_pixels: int = 0
    minimum_patch_area: int = 2**31 - 1
    maximum_patch_area: int = 0


def _rgb_codes(rgb: np.ndarray) -> np.ndarray:
    """把 uint8 RGB 无损编码成单个 uint32，便于精确颜色匹配。"""

    values = rgb.astype(np.uint32)
    return (
        (values[..., 0] << 16)
        | (values[..., 1] << 8)
        | values[..., 2]
    )


def _record_detached_color_evidence(
    rgb: np.ndarray,
    component_mask: np.ndarray,
    frame_index: int,
    config: ArmRemovalConfig,
    evidence: dict[int, _ColorEvidence],
) -> None:
    """记录独立物体内重复出现的非黑色精确颜色连通块。"""

    codes = _rgb_codes(rgb)
    for raw_value in np.unique(codes[component_mask]):
        value = int(raw_value)
        red = (value >> 16) & 255
        green = (value >> 8) & 255
        blue = value & 255
        if red + green + blue <= 3 * config.black_luminance_max:
            continue
        selected = component_mask & (codes == value)
        component_count, _, stats, _ = cv2.connectedComponentsWithStats(
            selected.astype(np.uint8), connectivity=8
        )
        patch_areas = [
            int(stats[label, cv2.CC_STAT_AREA])
            for label in range(1, component_count)
        ]
        if not patch_areas:
            continue
        item = evidence.get(value)
        if item is None:
            item = _ColorEvidence(frames=set())
            evidence[value] = item
        item.frames.add(int(frame_index))
        item.total_pixels += int(sum(patch_areas))
        item.minimum_patch_area = min(
            item.minimum_patch_area, min(patch_areas)
        )
        item.maximum_patch_area = max(
            item.maximum_patch_area, max(patch_areas)
        )


def _extract_region_feature(
    rgb: np.ndarray,
    mask: np.ndarray,
    frame_index: int,
    *,
    keep_pixels: bool,
) -> _RegionFeature:
    """提取区域的量化颜色直方图、均值和形状，不使用任何语义标签。"""

    rows, columns = np.nonzero(mask)
    if rows.size == 0:
        raise ValueError("不能从空区域提取物体特征")
    colors = rgb[mask]
    area = int(colors.shape[0])
    width = int(columns.max() - columns.min() + 1)
    height = int(rows.max() - rows.min() + 1)
    histograms: list[np.ndarray] = []
    for channel in range(3):
        bins = np.bincount(
            (colors[:, channel].astype(np.int32) // 32).clip(0, 7),
            minlength=8,
        ).astype(np.float32)
        histograms.append(bins / float(area))
    pixels = (
        np.flatnonzero(mask).astype(np.int64, copy=False)
        if keep_pixels
        else np.empty(0, dtype=np.int64)
    )
    return _RegionFeature(
        frame_index=int(frame_index),
        pixels=pixels,
        area=area,
        histogram=np.concatenate(histograms),
        mean_rgb=np.mean(colors.astype(np.float32), axis=0) / 255.0,
        log_area=float(np.log(max(1, area))),
        log_aspect=float(np.log(width / max(1.0, float(height)))),
        extent=float(area / (width * height)),
    )


def _extract_detached_object_features(
    rgb: np.ndarray,
    depth: np.ndarray,
    table_depth: np.ndarray,
    raw_mask: np.ndarray,
    frame_index: int,
    config: ArmRemovalConfig,
    color_evidence: dict[int, _ColorEvidence],
) -> list[_RegionFeature]:
    """提取与候选机械臂保持间隔的独立 RGB-D 前景，作为物体外观证据。"""

    depth_float = np.asarray(depth).astype(np.float32, copy=False)
    valid_depth = np.isfinite(depth_float) & (depth_float > 0.0)
    foreground = valid_depth & (
        table_depth.astype(np.float32) - depth_float
        >= config.depth_front_margin_mm
    )
    radius = config.object_detached_arm_margin_radius
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1)
    )
    arm_margin = cv2.dilate(
        raw_mask.astype(np.uint8), kernel, iterations=1
    ).astype(bool)
    safe_foreground = foreground & ~arm_margin
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        safe_foreground.astype(np.uint8), connectivity=8
    )
    image_height, image_width = raw_mask.shape
    border = config.object_detached_border_margin
    features: list[_RegionFeature] = []
    for label in range(1, component_count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if not config.object_detached_area_min <= area <= config.object_detached_area_max:
            continue
        left = int(stats[label, cv2.CC_STAT_LEFT])
        top = int(stats[label, cv2.CC_STAT_TOP])
        right = left + int(stats[label, cv2.CC_STAT_WIDTH])
        bottom = top + int(stats[label, cv2.CC_STAT_HEIGHT])
        if (
            left <= border
            or top <= border
            or right >= image_width - border
            or bottom >= image_height - border
        ):
            continue
        component_mask = labels == label
        _record_detached_color_evidence(
            rgb,
            component_mask,
            frame_index,
            config,
            color_evidence,
        )
        features.append(
            _extract_region_feature(
                rgb,
                component_mask,
                frame_index,
                keep_pixels=False,
            )
        )
    return features


def _neck_basin_features(
    rgb: np.ndarray,
    raw_mask: np.ndarray,
    frame_index: int,
    config: ArmRemovalConfig,
    *,
    erosion_radius: int,
    minimum_core_area: int,
) -> list[_RegionFeature]:
    """腐蚀细颈后，把非入口 core 回溯为原始候选内的最近域 basin。"""

    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (2 * erosion_radius + 1, 2 * erosion_radius + 1),
    )
    interior = cv2.erode(
        raw_mask.astype(np.uint8), kernel, iterations=1
    ).astype(bool)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        interior.astype(np.uint8), connectivity=8
    )
    if component_count <= 2:
        return []

    image_height, image_width = raw_mask.shape
    top_limit = (
        int(round(image_height * config.top_anchor_ratio)) + erosion_radius
    )
    side_limit = (
        max(1, int(round(image_width * config.side_anchor_ratio)))
        + erosion_radius
    )
    root_labels: set[int] = set()
    for label in range(1, component_count):
        left = int(stats[label, cv2.CC_STAT_LEFT])
        top = int(stats[label, cv2.CC_STAT_TOP])
        right = left + int(stats[label, cv2.CC_STAT_WIDTH])
        if (
            top <= top_limit
            or left <= side_limit
            or right >= image_width - side_limit
        ):
            root_labels.add(label)
    if not root_labels:
        root_labels.add(
            1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        )

    candidate_labels = [
        label
        for label in range(1, component_count)
        if label not in root_labels
        and int(stats[label, cv2.CC_STAT_AREA]) >= minimum_core_area
    ]
    if not candidate_labels:
        return []

    distance_source = np.ones(raw_mask.shape, dtype=np.uint8)
    distance_source[interior] = 0
    _, nearest_labels = cv2.distanceTransformWithLabels(
        distance_source,
        cv2.DIST_L2,
        5,
        labelType=cv2.DIST_LABEL_CCOMP,
    )

    features: list[_RegionFeature] = []
    for core_label in candidate_labels:
        nearest_ids = np.unique(nearest_labels[labels == core_label])
        nearest_ids = nearest_ids[nearest_ids > 0]
        basin = raw_mask & np.isin(nearest_labels, nearest_ids)
        if not np.any(basin):
            continue
        features.append(
            _extract_region_feature(
                rgb,
                basin,
                frame_index,
                keep_pixels=True,
            )
        )
    return features


def _matching_detached_frame_count(
    basin: _RegionFeature,
    models: Sequence[_RegionFeature],
    config: ArmRemovalConfig,
) -> int:
    """统计与一个接触 basin 匹配、且和当前帧相隔足够远的独立证据帧。"""

    frames: set[int] = set()
    for model in models:
        if (
            abs(model.frame_index - basin.frame_index)
            < config.object_minimum_match_frame_gap
        ):
            continue
        histogram_distance = float(
            np.sum(np.abs(basin.histogram - model.histogram)) / 6.0
        )
        mean_rgb_distance = float(
            np.linalg.norm(basin.mean_rgb - model.mean_rgb)
        )
        if (
            histogram_distance <= config.object_histogram_l1_max
            and mean_rgb_distance <= config.object_mean_rgb_distance_max
            and abs(basin.log_area - model.log_area)
            <= config.object_log_area_delta_max
            and abs(basin.log_aspect - model.log_aspect)
            <= config.object_log_aspect_delta_max
            and abs(basin.extent - model.extent)
            <= config.object_extent_delta_max
        ):
            frames.add(model.frame_index)
    return len(frames)


def _build_color_component_exemption(
    rgb_frames: np.ndarray,
    raw_masks: np.ndarray,
    evidence: Mapping[int, _ColorEvidence],
    raw_color_counts: Mapping[int, int],
    config: ArmRemovalConfig,
    minimum_detached_fraction: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    """只保护在多个独立帧出现、且面积接近历史记录的精确同色分量。"""

    minimum_frames = max(
        config.object_color_minimum_frames,
        int(
            math.ceil(
                config.object_color_minimum_frame_fraction
                * rgb_frames.shape[0]
            )
        ),
    )
    eligible = {
        value: item
        for value, item in evidence.items()
        if item.total_pixels >= config.object_color_minimum_pixels
        and len(item.frames) >= minimum_frames
        and item.total_pixels
        / max(1, item.total_pixels + raw_color_counts.get(value, 0))
        >= minimum_detached_fraction
    }
    exemption = np.zeros_like(raw_masks)
    if not eligible:
        return exemption, {
            "eligible_color_count": 0,
            "minimum_detached_fraction": float(minimum_detached_fraction),
            "minimum_frames": int(minimum_frames),
            "selected_component_count": 0,
            "exempt_pixels": 0,
        }

    eligible_values = np.asarray(
        sorted(eligible), dtype=np.uint32
    )
    selected_component_count = 0
    for frame_index, frame_mask in enumerate(raw_masks):
        codes = _rgb_codes(rgb_frames[frame_index])
        candidate = frame_mask & np.isin(codes, eligible_values)
        component_count, labels, stats, _ = (
            cv2.connectedComponentsWithStats(
                candidate.astype(np.uint8), connectivity=8
            )
        )
        for label in range(1, component_count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < config.object_color_component_area_min:
                continue
            component = labels == label
            component_values = np.unique(codes[component])
            maximum_area = max(
                int(
                    math.ceil(
                        eligible[int(value)].maximum_patch_area
                        * config.object_color_component_area_max_ratio
                    )
                )
                for value in component_values
            )
            if area > maximum_area:
                continue
            exemption[frame_index] |= component
            selected_component_count += 1

    exemption &= raw_masks
    return exemption, {
        "eligible_color_count": len(eligible),
        "minimum_detached_fraction": float(minimum_detached_fraction),
        "minimum_frames": int(minimum_frames),
        "selected_component_count": int(selected_component_count),
        "exempt_pixels": int(np.count_nonzero(exemption)),
    }


def build_object_exemption(
    rgb_frames: np.ndarray,
    depth_frames: np.ndarray | None,
    table_depth: np.ndarray | None,
    raw_masks: np.ndarray,
    config: ArmRemovalConfig,
    color_minimum_detached_fraction: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    """用 RGB-D 分离外观和细颈最近域保护与机械臂接触的任务物体。"""

    exemption = np.zeros_like(raw_masks)
    if depth_frames is None or table_depth is None:
        return exemption, {
            "enabled": False,
            "reason": "rgb_depth_table_required",
            "detached_model_count": 0,
            "detached_color_count": 0,
            "high_confidence_basin_count": 0,
            "temporal_candidate_basin_count": 0,
            "temporal_selected_basin_count": 0,
            "color_component": None,
            "exempt_pixels": 0,
        }

    detached_models: list[_RegionFeature] = []
    color_evidence: dict[int, _ColorEvidence] = {}
    raw_color_counts: dict[int, int] = {}
    temporal_candidates: list[_RegionFeature] = []
    high_confidence_count = 0
    high_confidence_pixels = np.zeros_like(raw_masks)
    for frame_index in range(rgb_frames.shape[0]):
        rgb = rgb_frames[frame_index]
        depth = depth_frames[frame_index]
        raw_mask = raw_masks[frame_index]
        raw_values, raw_counts = np.unique(
            _rgb_codes(rgb)[raw_mask], return_counts=True
        )
        for value, count in zip(raw_values, raw_counts):
            key = int(value)
            raw_color_counts[key] = raw_color_counts.get(key, 0) + int(count)
        detached_models.extend(
            _extract_detached_object_features(
                rgb,
                depth,
                table_depth,
                raw_mask,
                frame_index,
                config,
                color_evidence,
            )
        )
        high_confidence = _neck_basin_features(
            rgb,
            raw_mask,
            frame_index,
            config,
            erosion_radius=config.object_high_confidence_erosion_radius,
            minimum_core_area=config.object_high_confidence_core_area_min,
        )
        high_confidence_count += len(high_confidence)
        flat_high = high_confidence_pixels[frame_index].reshape(-1)
        for region in high_confidence:
            flat_high[region.pixels] = True
        temporal_candidates.extend(
            _neck_basin_features(
                rgb,
                raw_mask,
                frame_index,
                config,
                erosion_radius=config.object_temporal_erosion_radius,
                minimum_core_area=config.object_temporal_core_area_min,
            )
        )

    minimum_match_frames = max(
        config.object_minimum_match_frames,
        int(
            math.ceil(
                config.object_minimum_match_frame_fraction
                * rgb_frames.shape[0]
            )
        ),
    )
    selected_temporal = [
        basin
        for basin in temporal_candidates
        if _matching_detached_frame_count(
            basin, detached_models, config
        )
        >= minimum_match_frames
    ]
    temporal_pixels = np.zeros_like(raw_masks)
    for region in selected_temporal:
        temporal_pixels[region.frame_index].reshape(-1)[region.pixels] = True

    color_pixels, color_audit = _build_color_component_exemption(
        rgb_frames,
        raw_masks,
        color_evidence,
        raw_color_counts,
        config,
        color_minimum_detached_fraction,
    )
    exemption = raw_masks & (
        high_confidence_pixels | temporal_pixels | color_pixels
    )
    return exemption, {
        "enabled": True,
        "reason": "rgb_depth_temporal_object_protection",
        "detached_model_count": len(detached_models),
        "detached_color_count": len(color_evidence),
        "high_confidence_basin_count": int(high_confidence_count),
        "temporal_candidate_basin_count": len(temporal_candidates),
        "temporal_selected_basin_count": len(selected_temporal),
        "minimum_match_frames": int(minimum_match_frames),
        "high_confidence_exempt_pixels": int(
            np.count_nonzero(high_confidence_pixels)
        ),
        "temporal_exempt_pixels": int(np.count_nonzero(temporal_pixels)),
        "color_component": color_audit,
        "exempt_pixels": int(np.count_nonzero(exemption)),
    }


@dataclass(frozen=True)
class _DarkComponent:
    """一帧内暗色连通分量的纯图像几何特征。"""

    frame_index: int
    pixels: np.ndarray
    area: int
    width: int
    height: int
    center_x: float
    center_y: float
    boundary_fraction: float
    terminal_mean_ratio: float
    near_top_entry: bool


class _UnionFind:
    """维护相邻帧暗块的无向轨迹连通分量。"""

    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        """返回节点根并做路径压缩。"""

        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        """按秩合并两个节点所在的轨迹。"""

        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def _component_distance(
    left: _DarkComponent, right: _DarkComponent
) -> float:
    """返回两个暗块质心的欧氏像素距离。"""

    return float(
        np.hypot(
            left.center_x - right.center_x,
            left.center_y - right.center_y,
        )
    )


def _component_area_ratio(
    left: _DarkComponent, right: _DarkComponent
) -> float:
    """返回两个暗块较小面积与较大面积之比。"""

    return float(min(left.area, right.area) / max(left.area, right.area))


def _extract_dark_components(
    masks: np.ndarray,
    rgb_frames: np.ndarray,
    config: ArmRemovalConfig,
) -> tuple[list[_DarkComponent], list[list[int]]]:
    """提取原始候选内符合 v2.1 黑色阈值的逐帧连通分量。"""

    dark = (
        rgb_frames.astype(np.uint16).sum(axis=-1)
        <= 3 * config.black_luminance_max
    )
    components: list[_DarkComponent] = []
    frame_nodes: list[list[int]] = [[] for _ in range(masks.shape[0])]
    boundary_kernel = np.ones((3, 3), dtype=np.uint8)

    for frame_index, frame_mask in enumerate(masks):
        boundary = frame_mask & ~cv2.erode(
            frame_mask.astype(np.uint8),
            boundary_kernel,
            iterations=1,
        ).astype(bool)
        image_height, image_width = frame_mask.shape
        top_limit = max(
            0, int(round(image_height * config.top_anchor_ratio))
        )
        side_limit = max(
            1, int(round(image_width * config.side_anchor_ratio))
        )
        entry_seed = np.zeros_like(frame_mask)
        entry_seed[: top_limit + 1] = frame_mask[: top_limit + 1]
        entry_seed[:, : side_limit + 1] |= frame_mask[:, : side_limit + 1]
        entry_seed[:, max(0, image_width - side_limit - 1) :] |= frame_mask[
            :, max(0, image_width - side_limit - 1) :
        ]
        entry_source = np.ones(frame_mask.shape, dtype=np.uint8)
        entry_source[entry_seed] = 0
        entry_distance = cv2.distanceTransform(
            entry_source, cv2.DIST_L2, 5
        )
        maximum_distance = (
            float(np.max(entry_distance[frame_mask]))
            if np.any(frame_mask)
            else 0.0
        )

        component_count, labels, stats, centroids = (
            cv2.connectedComponentsWithStats(
                (frame_mask & dark[frame_index]).astype(np.uint8),
                connectivity=8,
            )
        )
        for label in range(1, component_count):
            selected = labels == label
            area = int(stats[label, cv2.CC_STAT_AREA])
            center_y = float(centroids[label, 1])
            component = _DarkComponent(
                frame_index=int(frame_index),
                pixels=np.flatnonzero(selected).astype(
                    np.int64, copy=False
                ),
                area=area,
                width=int(stats[label, cv2.CC_STAT_WIDTH]),
                height=int(stats[label, cv2.CC_STAT_HEIGHT]),
                center_x=float(centroids[label, 0]),
                center_y=center_y,
                boundary_fraction=float(
                    np.count_nonzero(selected & boundary) / area
                ),
                terminal_mean_ratio=(
                    float(np.mean(entry_distance[selected]) / maximum_distance)
                    if maximum_distance > 0.0
                    else 0.0
                ),
                near_top_entry=center_y <= float(top_limit + 1),
            )
            frame_nodes[frame_index].append(len(components))
            components.append(component)
    return components, frame_nodes


def _loose_pair_frame_count(
    components: Sequence[_DarkComponent],
    frame_nodes: Sequence[Sequence[int]],
    config: ArmRemovalConfig,
) -> int:
    """计算具有一对相近小暗块的帧数，作为普通夹爪 episode 证据。"""

    matched_frames = 0
    for node_ids in frame_nodes:
        found = False
        eligible = [
            node_id
            for node_id in node_ids
            if 2 <= components[node_id].area
            <= config.gripper_pair_component_area_max
        ]
        for position, left_id in enumerate(eligible):
            left = components[left_id]
            for right_id in eligible[position + 1 :]:
                right = components[right_id]
                distance = _component_distance(left, right)
                if (
                    config.gripper_pair_distance_min
                    <= distance
                    <= config.gripper_pair_distance_max
                    and _component_area_ratio(left, right)
                    >= config.gripper_pair_area_ratio_min
                ):
                    found = True
                    break
            if found:
                break
        matched_frames += int(found)
    return matched_frames


def _stick_evidence_frame_count(
    components: Sequence[_DarkComponent],
    frame_nodes: Sequence[Sequence[int]],
    config: ArmRemovalConfig,
) -> int:
    """统计存在大型细长暗块的帧数，作为 stick 的正视觉证据。"""

    matched_frames = 0
    for node_ids in frame_nodes:
        found = False
        for node_id in node_ids:
            item = components[node_id]
            shorter = max(1, min(item.width, item.height))
            aspect_ratio = max(item.width, item.height) / float(shorter)
            if (
                item.area >= config.stick_component_area_min
                and aspect_ratio >= config.stick_component_aspect_ratio_min
            ):
                found = True
                break
        matched_frames += int(found)
    return matched_frames


def _is_tip_candidate(
    item: _DarkComponent, config: ArmRemovalConfig
) -> bool:
    """判断暗块是否进入相邻帧时序图。"""

    return (
        item.area <= config.tip_candidate_area_max
        and item.width <= config.tip_candidate_width_max
        and item.height <= config.tip_candidate_height_max
        and item.boundary_fraction >= config.tip_candidate_boundary_min
        and (
            item.terminal_mean_ratio >= config.tip_candidate_terminal_min
            or item.near_top_entry
        )
    )


def _tip_anchor_nodes(
    nodes: Sequence[_DarkComponent],
    config: ArmRemovalConfig,
) -> set[int]:
    """返回参与至少一组高置信帧内双暗块配对的候选节点。"""

    grouped: dict[int, list[int]] = defaultdict(list)
    for node_index, item in enumerate(nodes):
        if (
            2 <= item.area <= config.tip_anchor_area_max
            and item.width <= config.tip_anchor_width_max
            and item.height <= config.tip_anchor_height_max
            and item.boundary_fraction >= config.tip_anchor_boundary_min
            and (
                item.terminal_mean_ratio >= config.tip_anchor_terminal_min
                or item.near_top_entry
            )
        ):
            grouped[item.frame_index].append(node_index)

    anchors: set[int] = set()
    for node_ids in grouped.values():
        for position, left_id in enumerate(node_ids):
            left = nodes[left_id]
            for right_id in node_ids[position + 1 :]:
                right = nodes[right_id]
                distance = _component_distance(left, right)
                if (
                    config.tip_anchor_pair_distance_min
                    <= distance
                    <= config.tip_anchor_pair_distance_max
                    and _component_area_ratio(left, right)
                    >= config.tip_anchor_pair_area_ratio_min
                ):
                    anchors.update((left_id, right_id))
    return anchors


def _connect_tip_tracks(
    nodes: Sequence[_DarkComponent],
    config: ArmRemovalConfig,
) -> _UnionFind:
    """只连接相邻帧相互前 K 近邻，形成方向无关的暗块轨迹。"""

    union_find = _UnionFind(len(nodes))
    grouped: dict[int, list[int]] = defaultdict(list)
    for node_index, item in enumerate(nodes):
        grouped[item.frame_index].append(node_index)

    for frame_index, left_ids in grouped.items():
        right_ids = grouped.get(frame_index + 1)
        if not right_ids:
            continue
        gate = (
            config.tip_motion_base_pixels
            + config.tip_motion_pixels_per_frame
        )
        left_rankings: dict[int, list[int]] = {}
        right_rankings: dict[int, list[int]] = {}

        for left_id in left_ids:
            ranked = sorted(
                (
                    (_component_distance(nodes[left_id], nodes[right_id]), right_id)
                    for right_id in right_ids
                    if _component_area_ratio(nodes[left_id], nodes[right_id])
                    >= config.tip_transition_area_ratio_min
                ),
                key=lambda item: item[0],
            )
            left_rankings[left_id] = [
                node_id
                for distance, node_id in ranked[: config.tip_mutual_nearest_k]
                if distance <= gate
            ]
        for right_id in right_ids:
            ranked = sorted(
                (
                    (_component_distance(nodes[left_id], nodes[right_id]), left_id)
                    for left_id in left_ids
                    if _component_area_ratio(nodes[left_id], nodes[right_id])
                    >= config.tip_transition_area_ratio_min
                ),
                key=lambda item: item[0],
            )
            right_rankings[right_id] = [
                node_id
                for distance, node_id in ranked[: config.tip_mutual_nearest_k]
                if distance <= gate
            ]
        for left_id, neighbors in left_rankings.items():
            for right_id in neighbors:
                if left_id in right_rankings.get(right_id, []):
                    union_find.union(left_id, right_id)
    return union_find


def build_black_tip_exemption(
    masks: np.ndarray,
    rgb_frames: np.ndarray,
    config: ArmRemovalConfig,
) -> tuple[np.ndarray, dict[str, Any]]:
    """仅在稳定双指 episode 中豁免时序跟踪到的黑色指尖像素。"""

    empty = np.zeros_like(masks)
    components, frame_nodes = _extract_dark_components(
        masks, rgb_frames, config
    )
    loose_pair_frames = _loose_pair_frame_count(
        components, frame_nodes, config
    )
    classification_threshold = max(
        config.gripper_pair_minimum_frames,
        int(
            math.ceil(
                config.gripper_pair_minimum_frame_fraction * masks.shape[0]
            )
        ),
    )
    classified_gripper = loose_pair_frames >= classification_threshold
    stick_evidence_frames = _stick_evidence_frame_count(
        components, frame_nodes, config
    )
    stick_classification_threshold = max(
        config.stick_minimum_frames,
        int(
            math.ceil(
                config.stick_minimum_frame_fraction * masks.shape[0]
            )
        ),
    )
    classified_stick = (
        not classified_gripper
        and stick_evidence_frames >= stick_classification_threshold
    )
    classification_audit = {
        "classified_gripper": bool(classified_gripper),
        "classified_stick": bool(classified_stick),
        "loose_pair_frames": int(loose_pair_frames),
        "classification_threshold": int(classification_threshold),
        "stick_evidence_frames": int(stick_evidence_frames),
        "stick_classification_threshold": int(
            stick_classification_threshold
        ),
    }
    if not classified_gripper:
        return empty, {
            **classification_audit,
            "candidate_nodes": 0,
            "anchor_nodes": 0,
            "selected_tracks": 0,
            "selected_nodes": 0,
            "exempt_pixels": 0,
        }

    original_indices = [
        index
        for index, item in enumerate(components)
        if _is_tip_candidate(item, config)
    ]
    nodes = [components[index] for index in original_indices]
    anchors = _tip_anchor_nodes(nodes, config)
    if not anchors:
        return empty, {
            **classification_audit,
            "candidate_nodes": len(nodes),
            "anchor_nodes": 0,
            "selected_tracks": 0,
            "selected_nodes": 0,
            "exempt_pixels": 0,
        }

    union_find = _connect_tip_tracks(nodes, config)
    track_nodes: dict[int, list[int]] = defaultdict(list)
    track_anchor_frames: dict[int, set[int]] = defaultdict(set)
    for node_index, item in enumerate(nodes):
        root = union_find.find(node_index)
        track_nodes[root].append(node_index)
        if node_index in anchors:
            track_anchor_frames[root].add(item.frame_index)

    minimum_track_frames = max(
        config.tip_minimum_track_frames,
        int(
            math.ceil(
                config.tip_minimum_track_frame_fraction * masks.shape[0]
            )
        ),
    )
    ranked_tracks: list[tuple[tuple[float, ...], int]] = []
    for root, node_ids in track_nodes.items():
        anchor_frames = track_anchor_frames.get(root, set())
        if (
            len(anchor_frames) < config.tip_minimum_track_anchor_frames
        ):
            continue
        unique_frames = len(
            {nodes[node_id].frame_index for node_id in node_ids}
        )
        if unique_frames < minimum_track_frames:
            continue
        score = (
            float(len(anchor_frames)),
            float(
                np.median(
                    [
                        nodes[node_id].terminal_mean_ratio
                        for node_id in node_ids
                    ]
                )
            ),
            float(
                np.median(
                    [
                        nodes[node_id].boundary_fraction
                        for node_id in node_ids
                    ]
                )
            ),
            float(unique_frames),
        )
        ranked_tracks.append((score, root))

    ranked_tracks.sort(reverse=True)
    selected_roots = {
        root
        for _, root in ranked_tracks[: config.tip_maximum_tracks]
    }
    selected_node_ids = {
        node_id
        for root in selected_roots
        for node_id in track_nodes[root]
    }
    selected_original = {
        original_indices[node_id] for node_id in selected_node_ids
    }
    exemption = np.zeros_like(masks)
    for component_index in selected_original:
        item = components[component_index]
        exemption[item.frame_index].reshape(-1)[item.pixels] = True
    exemption &= masks

    return exemption, {
        **classification_audit,
        "candidate_nodes": len(nodes),
        "anchor_nodes": len(anchors),
        "selected_tracks": len(selected_roots),
        "selected_nodes": len(selected_node_ids),
        "minimum_track_frames": int(minimum_track_frames),
        "track_scores": [
            [float(value) for value in score]
            for score, _ in ranked_tracks[: config.tip_maximum_tracks]
        ],
        "exempt_pixels": int(np.count_nonzero(exemption)),
    }


def _wood_pixel_masks(
    rgb_frames: np.ndarray, config: ArmRemovalConfig
) -> np.ndarray:
    """批量计算木桌 HSV mask，返回 ``bool[T,H,W]``。"""

    masks = np.zeros(rgb_frames.shape[:3], dtype=bool)
    for frame_index, frame in enumerate(rgb_frames):
        hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
        hue, saturation, value = cv2.split(hsv)
        masks[frame_index] = (
            (hue <= config.table_hue_max)
            & (saturation >= config.table_saturation_min)
            & (value >= config.table_value_min)
        )
    return masks


def _infer_desktop_start_row(
    wood_available: np.ndarray, config: ArmRemovalConfig
) -> tuple[int, dict[str, Any]]:
    """从各行可找到木桌样本的比例推断桌面从哪一行开始。"""

    if wood_available.ndim != 2:
        raise ValueError("wood_available 必须是 [H,W]")
    height, width = wood_available.shape
    row_fraction = np.count_nonzero(wood_available, axis=1) / float(width)
    required_rows = min(height, config.background_desktop_required_rows)
    start_row = height
    for row in range(0, height - required_rows + 1):
        window = row_fraction[row : row + required_rows]
        if np.all(window >= config.background_desktop_min_wood_fraction):
            start_row = row
            break
    return start_row, {
        "start_row": int(start_row),
        "found": bool(start_row < height),
        "minimum_wood_fraction": float(
            config.background_desktop_min_wood_fraction
        ),
        "required_consecutive_rows": int(required_rows),
        "row_wood_fraction_at_start": (
            None if start_row >= height else float(row_fraction[start_row])
        ),
        "row_wood_fraction_max": float(np.max(row_fraction)),
    }


def _contiguous_true_runs(row_mask: np.ndarray) -> list[tuple[int, int]]:
    """把一行布尔 mask 拆成左闭右开的连续区间。"""

    positions = np.flatnonzero(row_mask)
    if positions.size == 0:
        return []
    split_points = np.flatnonzero(np.diff(positions) > 1) + 1
    groups = np.split(positions, split_points)
    return [(int(group[0]), int(group[-1]) + 1) for group in groups]


def _choose_horizontal_patch_start(
    background_row: np.ndarray,
    eligible_row: np.ndarray,
    known_row: np.ndarray,
    target_start: int,
    target_end: int,
    max_search: int,
    distance_weight: float,
) -> int | None:
    """为一个未知横向区间选择同一行的完整来源 patch。

    候选区间必须逐像素完整且不与目标重叠。代价同时考虑到目标的横向距离和左右接缝色差，避免
    简单复制最近 patch 时把明显不同亮度的木纹硬接在一起。
    """

    width = int(eligible_row.size)
    patch_width = int(target_end - target_start)
    if patch_width <= 0 or patch_width > width:
        return None
    window_counts = np.convolve(
        eligible_row.astype(np.int32),
        np.ones(patch_width, dtype=np.int32),
        mode="valid",
    )
    candidate_starts = np.flatnonzero(window_counts == patch_width)
    if candidate_starts.size == 0:
        return None

    target_center = (target_start + target_end - 1) / 2.0
    best_start: int | None = None
    best_cost = float("inf")
    for raw_start in candidate_starts:
        source_start = int(raw_start)
        source_end = source_start + patch_width
        if source_start < target_end and source_end > target_start:
            continue
        interval_distance = max(
            target_start - source_end, source_start - target_end, 0
        )
        if interval_distance > max_search:
            continue

        source = background_row[source_start:source_end].astype(np.float32)
        seam_cost = 0.0
        seam_count = 0
        if target_start > 0 and bool(known_row[target_start - 1]):
            seam_cost += float(
                np.mean(
                    np.abs(
                        source[0]
                        - background_row[target_start - 1].astype(np.float32)
                    )
                )
            )
            seam_count += 1
        if target_end < width and bool(known_row[target_end]):
            seam_cost += float(
                np.mean(
                    np.abs(
                        source[-1]
                        - background_row[target_end].astype(np.float32)
                    )
                )
            )
            seam_count += 1
        if seam_count:
            seam_cost /= seam_count

        source_center = (source_start + source_end - 1) / 2.0
        center_distance = abs(source_center - target_center)
        cost = seam_cost + distance_weight * center_distance
        if cost < best_cost:
            best_cost = cost
            best_start = source_start
    return best_start


def _fill_unknown_with_horizontal_patches(
    background: np.ndarray,
    unknown: np.ndarray,
    desktop_start_row: int,
    config: ArmRemovalConfig,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """按连通区域逐行搬运邻近完整横向纹理，返回图像、剩余洞和审计统计。

    桌面行的来源 patch 必须仍满足木桌 HSV 规则；顶部非桌面区域只要求来源已知。这样既不会把
    蓝块、白块或目标环带进桌面背景，也能用同一行的灰色远景修复永久遮挡的机器人基座。
    """

    if background.ndim != 3 or background.shape[-1] != 3:
        raise ValueError("background 必须是 [H,W,3]")
    if unknown.shape != background.shape[:2]:
        raise ValueError("unknown 与 background 分辨率不一致")

    filled = background.copy()
    remaining = unknown.astype(bool, copy=True)
    known = ~remaining
    height, width = remaining.shape
    background_hsv = cv2.cvtColor(filled, cv2.COLOR_RGB2HSV)
    hue, saturation, value = cv2.split(background_hsv)
    wood_source = (
        (hue <= config.table_hue_max)
        & (saturation >= config.table_saturation_min)
        & (value >= config.table_value_min)
    )
    source_eligible = known.copy()
    if desktop_start_row < height:
        source_eligible[desktop_start_row:] &= wood_source[desktop_start_row:]

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        remaining.astype(np.uint8), connectivity=8
    )
    component_order = sorted(
        range(1, component_count),
        key=lambda label: int(stats[label, cv2.CC_STAT_AREA]),
        reverse=True,
    )
    max_search = max(
        1, int(round(width * config.background_patch_max_search_ratio))
    )
    copied_pixels = 0
    copy_operations = 0
    fully_filled_components = 0

    for label in component_order:
        y_start = int(stats[label, cv2.CC_STAT_TOP])
        y_end = y_start + int(stats[label, cv2.CC_STAT_HEIGHT])
        for row in range(y_start, y_end):
            target_runs = _contiguous_true_runs(labels[row] == label)
            for target_start, target_end in target_runs:
                source_start = _choose_horizontal_patch_start(
                    filled[row],
                    source_eligible[row],
                    known[row],
                    target_start,
                    target_end,
                    max_search,
                    config.background_patch_distance_weight,
                )
                if source_start is None:
                    continue
                patch_width = target_end - target_start
                source_end = source_start + patch_width
                filled[row, target_start:target_end] = filled[
                    row, source_start:source_end
                ]
                remaining[row, target_start:target_end] = False
                known[row, target_start:target_end] = True
                source_eligible[row, target_start:target_end] = True
                if row >= desktop_start_row:
                    wood_source[row, target_start:target_end] = True
                copied_pixels += patch_width
                copy_operations += 1
        if not np.any(remaining[labels == label]):
            fully_filled_components += 1

    remaining_count = int(np.count_nonzero(remaining))
    return filled, remaining, {
        "initial_connected_components": int(max(0, component_count - 1)),
        "fully_filled_components": int(fully_filled_components),
        "copy_operations": int(copy_operations),
        "copied_pixels": int(copied_pixels),
        "remaining_pixels": remaining_count,
        "max_horizontal_search_pixels": int(max_search),
    }


def build_temporal_background(
    rgb_frames: np.ndarray | Sequence[np.ndarray],
    masks: np.ndarray | Sequence[np.ndarray],
    config: ArmRemovalConfig | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """从未被机械臂 mask 命中的时序像素构建静态背景图。

    最多均匀抽取 ``temporal_sample_count`` 帧。桌面区域只允许木桌 HSV 像素参与中位数，避免
    移动物体的旧位置进入背景板；顶部非桌面区域仍接受全部非机械臂像素。无有效样本的洞先从
    同一行搬运邻近完整纹理，只有横向找不到来源的残余才交给 Telea。
    """

    cfg = config or ArmRemovalConfig()
    _validate_config(cfg)
    rgb = np.asarray(rgb_frames)
    mask_array = np.asarray(masks)
    if rgb.ndim != 4 or rgb.shape[-1] != 3 or rgb.dtype != np.uint8:
        raise ValueError("rgb_frames 必须是 uint8 [T,H,W,3]")
    if mask_array.shape != rgb.shape[:3]:
        raise ValueError(f"masks 形状必须是 {rgb.shape[:3]}，收到 {mask_array.shape}")
    mask_array = mask_array.astype(bool, copy=False)

    frame_count = rgb.shape[0]
    sample_count = min(frame_count, cfg.temporal_sample_count)
    sample_indices = np.unique(
        np.rint(np.linspace(0, frame_count - 1, sample_count)).astype(np.int64)
    )
    sampled_rgb_uint8 = rgb[sample_indices]
    sampled_rgb = sampled_rgb_uint8.astype(np.float32)
    base_valid = ~mask_array[sample_indices]
    sampled_wood = _wood_pixel_masks(sampled_rgb_uint8, cfg)
    wood_available = np.any(base_valid & sampled_wood, axis=0)
    desktop_start_row, desktop_audit = _infer_desktop_start_row(
        wood_available, cfg
    )

    sampled_valid = base_valid.copy()
    if desktop_start_row < rgb.shape[1]:
        sampled_valid[:, desktop_start_row:] &= sampled_wood[:, desktop_start_row:]
    rejected_nonwood_desktop = int(
        np.count_nonzero(base_valid & ~sampled_valid)
    )
    sampled_rgb[~sampled_valid] = np.nan

    # 某些像素全程被机械臂覆盖时 nanmedian 会发出 All-NaN slice 告警；这是预期路径，随后 Telea。
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        background_float = np.nanmedian(sampled_rgb, axis=0)

    valid_counts = np.count_nonzero(sampled_valid, axis=0)
    never_observed = valid_counts == 0
    finite_background = np.all(np.isfinite(background_float), axis=-1)
    if not np.array_equal(never_observed, ~finite_background):
        # 三个通道共享同一个 mask，理论上必须同时有值或同时为 NaN；不满足说明输入/NumPy 行为异常。
        raise RuntimeError("时序背景三个颜色通道的有效性不一致")

    background = np.nan_to_num(background_float, nan=0.0)
    background = np.rint(background).clip(0, 255).astype(np.uint8)
    never_observed_count = int(np.count_nonzero(never_observed))
    background, telea_remaining, horizontal_audit = (
        _fill_unknown_with_horizontal_patches(
            background, never_observed, desktop_start_row, cfg
        )
    )
    telea_count = int(np.count_nonzero(telea_remaining))
    if telea_count > 0:
        inpaint_mask = telea_remaining.astype(np.uint8) * 255
        # OpenCV 对三个通道独立处理；数组虽然是 RGB 顺序，输出仍保持相同通道顺序。
        background = cv2.inpaint(
            background, inpaint_mask, cfg.inpaint_radius, cv2.INPAINT_TELEA
        )

    audit = {
        "sample_indices": [int(index) for index in sample_indices],
        "sample_count": int(sample_indices.size),
        "desktop": desktop_audit,
        "desktop_nonwood_samples_rejected": rejected_nonwood_desktop,
        "never_observed_pixels": never_observed_count,
        "never_observed_fraction": float(never_observed_count / never_observed.size),
        "horizontal_patch_fill": horizontal_audit,
        "telea_pixels": telea_count,
        "valid_sample_count_min": int(np.min(valid_counts)),
        "valid_sample_count_median": float(np.median(valid_counts)),
        "valid_sample_count_max": int(np.max(valid_counts)),
    }
    return background, audit


def apply_background_to_masks(
    rgb_frames: np.ndarray | Sequence[np.ndarray],
    masks: np.ndarray | Sequence[np.ndarray],
    background_rgb: np.ndarray,
) -> np.ndarray:
    """仅在 mask 内用背景图替换像素，mask 外逐位保持输入值。"""

    rgb = np.asarray(rgb_frames)
    mask_array = np.asarray(masks)
    background = np.asarray(background_rgb)
    if rgb.ndim != 4 or rgb.shape[-1] != 3 or rgb.dtype != np.uint8:
        raise ValueError("rgb_frames 必须是 uint8 [T,H,W,3]")
    if mask_array.shape != rgb.shape[:3]:
        raise ValueError(f"masks 形状必须是 {rgb.shape[:3]}，收到 {mask_array.shape}")
    if background.shape != rgb.shape[1:] or background.dtype != np.uint8:
        raise ValueError(
            f"background_rgb 必须是 uint8 {rgb.shape[1:]}，收到 {background.shape}/{background.dtype}"
        )

    mask_array = mask_array.astype(bool, copy=False)
    output = rgb.copy()
    for frame_index in range(rgb.shape[0]):
        frame_mask = mask_array[frame_index]
        output[frame_index][frame_mask] = background[frame_mask]
    return output


def remove_robot_arm_sequence(
    rgb_frames: np.ndarray | Sequence[np.ndarray],
    depth_frames: np.ndarray | Sequence[np.ndarray] | None = None,
    config: ArmRemovalConfig | None = None,
) -> ArmRemovalResult:
    """删除同一 episode 全部 RGB 帧中的机械臂。

    参数：
        rgb_frames: ``uint8 [T,H,W,3]`` RGB 帧序列。
        depth_frames: 可选的 ``[T,H,W]`` 或 ``[T,H,W,1]`` 毫米深度序列。
        config: 可选配置；默认偏向完整删除臂杆、腕部和夹爪。

    返回：
        :class:`ArmRemovalResult`。``frames`` 是删除后的图像，``masks`` 是 bool 数组，
        ``background`` 是 episode 背景板，``stats`` 与 ``config`` 只含 JSON 可序列化值。
    """

    cfg = config or ArmRemovalConfig()
    _validate_config(cfg)
    rgb, depth = normalize_episode_inputs(rgb_frames, depth_frames)

    # 固定相机下桌面平面在整个 episode 内不变。优先从首帧开始尝试少量均匀帧，成功后全序列复用，
    # 避免对最长 1200 帧的 episode 重复做同一轮最小二乘。逐帧深度仍然参与前景高度判断。
    shared_table_depth: np.ndarray | None = None
    shared_table_fit_audit: dict[str, Any] = {
        "used": False,
        "reason": "depth_not_provided",
    }
    compact_shared_table_audit: dict[str, Any] | None = None
    if depth is not None:
        probe_count = min(int(rgb.shape[0]), 8)
        probe_indices = np.unique(
            np.rint(np.linspace(0, rgb.shape[0] - 1, probe_count)).astype(np.int64)
        )
        failed_probes: list[dict[str, Any]] = []
        for probe_index in probe_indices:
            fitted, fit_audit = fit_table_depth_plane(
                rgb[int(probe_index)], depth[int(probe_index)], cfg
            )
            if fitted is not None:
                shared_table_depth = fitted
                shared_table_fit_audit = {
                    **fit_audit,
                    "source_frame_index": int(probe_index),
                    "probe_indices": [int(item) for item in probe_indices],
                    "failed_probes_before_success": failed_probes,
                }
                compact_shared_table_audit = {
                    "used": True,
                    "reason": "episode_shared_table_fit",
                    "source_frame_index": int(probe_index),
                }
                break
            failed_probes.append(
                {
                    "frame_index": int(probe_index),
                    "reason": str(fit_audit.get("reason", "unknown")),
                    "candidate_pixels": int(fit_audit.get("candidate_pixels", 0)),
                }
            )
        if shared_table_depth is None:
            shared_table_fit_audit = {
                "used": False,
                "reason": "all_episode_table_fit_probes_failed",
                "probe_indices": [int(item) for item in probe_indices],
                "failed_probes": failed_probes,
            }

    masks = np.zeros(rgb.shape[:3], dtype=bool)
    frame_audits: list[dict[str, Any]] = []
    for frame_index in range(rgb.shape[0]):
        frame_depth = None if depth is None else depth[frame_index]
        frame_mask, frame_audit = detect_arm_mask(
            rgb[frame_index],
            frame_depth,
            cfg,
            fitted_table_depth=shared_table_depth,
            fitted_table_audit=compact_shared_table_audit,
        )
        masks[frame_index] = frame_mask
        frame_audit["frame_index"] = int(frame_index)
        frame_audits.append(frame_audit)
    raw_masks = masks
    black_tip_exemption, black_tip_audit = build_black_tip_exemption(
        raw_masks,
        rgb,
        cfg,
    )
    if bool(black_tip_audit["classified_gripper"]):
        color_minimum_detached_fraction = (
            cfg.object_color_minimum_detached_fraction
        )
    else:
        color_minimum_detached_fraction = (
            cfg.object_color_minimum_detached_fraction_without_gripper
        )
    object_exemption, object_audit = build_object_exemption(
        rgb,
        depth,
        shared_table_depth,
        raw_masks,
        cfg,
        color_minimum_detached_fraction,
    )
    combined_exemption = object_exemption | black_tip_exemption
    masks = raw_masks & ~combined_exemption

    for frame_index, frame_audit in enumerate(frame_audits):
        frame_audit["raw_mask_pixels"] = int(
            np.count_nonzero(raw_masks[frame_index])
        )
        frame_audit["object_exempt_pixels"] = int(
            np.count_nonzero(object_exemption[frame_index])
        )
        frame_audit["black_tip_exempt_pixels"] = int(
            np.count_nonzero(black_tip_exemption[frame_index])
        )
        frame_audit["final_mask_pixels"] = int(
            np.count_nonzero(masks[frame_index])
        )

    background, background_audit = build_temporal_background(rgb, masks, cfg)
    removed = apply_background_to_masks(rgb, masks, background)

    mask_pixels_per_frame = np.count_nonzero(masks, axis=(1, 2))
    total_mask_pixels = int(np.sum(mask_pixels_per_frame, dtype=np.int64))
    total_raw_mask_pixels = int(np.count_nonzero(raw_masks))
    total_object_exempt_pixels = int(np.count_nonzero(object_exemption))
    total_black_tip_exempt_pixels = int(np.count_nonzero(black_tip_exemption))
    total_combined_exempt_pixels = int(np.count_nonzero(combined_exemption))
    depth_fit_frames = sum(
        bool(item["table_depth_fit"].get("used", False)) for item in frame_audits
    )
    stats: dict[str, Any] = {
        "input": {
            "frame_count": int(rgb.shape[0]),
            "height": int(rgb.shape[1]),
            "width": int(rgb.shape[2]),
            "rgb_dtype": str(rgb.dtype),
            "depth_provided": depth is not None,
            "depth_dtype": None if depth is None else str(depth.dtype),
        },
        "summary": {
            "total_mask_pixels": total_mask_pixels,
            "total_raw_mask_pixels": total_raw_mask_pixels,
            "total_object_exempt_pixels": total_object_exempt_pixels,
            "total_black_tip_exempt_pixels": total_black_tip_exempt_pixels,
            "total_combined_exempt_pixels": total_combined_exempt_pixels,
            "overall_mask_fraction": float(total_mask_pixels / masks.size),
            "mask_pixels_per_frame_min": int(np.min(mask_pixels_per_frame)),
            "mask_pixels_per_frame_median": float(np.median(mask_pixels_per_frame)),
            "mask_pixels_per_frame_max": int(np.max(mask_pixels_per_frame)),
            "nonempty_mask_frames": int(np.count_nonzero(mask_pixels_per_frame)),
            "depth_table_fit_frames": int(depth_fit_frames),
            "rgb_only_fallback_frames": int(rgb.shape[0] - depth_fit_frames),
            # 由 apply_background_to_masks 的单一赋值位置保证；保留为机器可读契约声明。
            "untouched_pixels_bitwise_preserved": True,
        },
        "object_protection": object_audit,
        "black_tip_protection": black_tip_audit,
        "background": background_audit,
        "episode_table_depth_fit": shared_table_fit_audit,
        "frames": frame_audits,
    }
    return ArmRemovalResult(
        frames=removed,
        masks=masks,
        background=background,
        stats=stats,
        config=asdict(cfg),
    )


def remove_arm_from_episode(
    rgb_frames: np.ndarray | Sequence[np.ndarray],
    depth_frames: np.ndarray | Sequence[np.ndarray] | None = None,
    config: ArmRemovalConfig | None = None,
) -> ArmRemovalResult:
    """兼容别名；新代码请使用 :func:`remove_robot_arm_sequence`。"""

    return remove_robot_arm_sequence(rgb_frames, depth_frames, config)


def audit_parameters(config: ArmRemovalConfig | None = None) -> Mapping[str, Any]:
    """返回默认或给定配置的 JSON 友好参数快照，便于外层提前写运行清单。"""

    cfg = config or ArmRemovalConfig()
    _validate_config(cfg)
    return {"schema_version": SCHEMA_VERSION, "parameters": asdict(cfg)}


__all__ = [
    "SCHEMA_VERSION",
    "ArmRemovalConfig",
    "ArmRemovalResult",
    "apply_background_to_masks",
    "audit_parameters",
    "build_temporal_background",
    "detect_arm_mask",
    "fit_table_depth_plane",
    "normalize_episode_inputs",
    "remove_arm_from_episode",
    "remove_robot_arm_sequence",
]
