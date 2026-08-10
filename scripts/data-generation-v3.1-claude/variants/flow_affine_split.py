"""候选变体 flow_affine_split：稠密光流仿射一致性判臂。

核心思路：不用颜色/饱和度区分「臂」与「与臂接触的物体」，而用**运动**区分——
机械臂是刚性连杆，其在单帧尺度上的投影运动可以被一个全局仿射模型（6 参）很好
地近似；与臂接触/被夹持/被拖动的物体即使贴着臂，只要不是刚性连杆本身，运动上
要么是完全不同的仿射参数（如被拖动的柔性缆线），要么此刻根本不动（如静止的
按钮而臂在别处动），要么曾经独立出现过（如被夹起前先被单独看到的方块）。

## 算法结构

1. **背景板/前景/边带种子/外观模型/常驻底座区**：逐字复用 `cv_base` 对应函数，
   与 v3、其余 v3.1 变体共享同一套背景建模原语，只在“臂 vs 物体”判定这一层
   换成运动判据。
2. **前后向光流一致性**：Farneback 双向计算 + 前后一致性校验（误差<=1.5px）
   得到逐像素「可信位移」。末帧没有下一帧，借用上一对的反向流代替。
3. **锚定域仿射拟合**：在触边/触底座的前景连通域（= 候选臂区）上，用 Scharr
   梯度幅值加权的最小二乘拟合一个全局仿射运动，3 轮 RANSAC-lite（每轮按残差
   重选内点再拟合）。
4. **像素三分类**：
   - 仿射内点，或「实际位移与模型预测位移都接近零」的静止一致像素 → 判「臂」；
   - 可信流但残差超限 → 判「附着物体」外点候选，连通块面积达标**且多数像素
     饱和有彩色/纯白高亮（非臂色调）**才注册进本段的持久保护集，并随光流逐帧
     正向前推（即使后续与臂刚性同步，也因早先注册受保护）——多数像素仍是灰阶
     臂色调的外点块不注册，见「复核后修正」；
   - 不可信流（纹理不足）→ 回退到外观判据（无彩暗/亮阈值），不把「零流」直接
     当「不是臂」。
   - 臂整体静止或可信像素太少时，整帧回退到「外观 + 板新颖性」通道（没有仿射
     模型可用）。
5. **黑色指尖保留**：候选黑色小块除了满足几何规则（无彩暗、面积小、瘦长、
   测地意义上处于肢体远端）外，臂在动的帧还要求该候选是仿射内点——被夹的黑色
   小物体不会同时满足「肢体测地远端」与「随臂刚性运动」。
6. **兜底否决**：高饱和、纯白高亮（缆线/按钮材质特征）、与背景板几乎同色（连通
   块整体 ⊕2 保护边界）三类像素一律不删；持久保护集同理。
7. **收尾**：不用无条件膨胀，改成守卫生长——只允许最终 mask 向仍是前景、且不
   被否决/保护/指尖判定的相邻像素扩张 1 次。

## 复核后修正（独立视觉验证发现问题后的两处根因修复）

1. **外点注册加外观门槛**：全局单一仿射对多连杆臂只是粗糙近似，臂/工具自身
   在关节处或独立刚体末端（如 RouteStick 的 stick 工具相对前臂的独立旋转）
   天然会产生残差超限的「外点」，但这些像素多数仍是灰阶臂色，不是真正附着的
   外来物体。原实现不分青红皂白一律注册进持久保护集，实测 20~25 帧内即可
   滚雪球式吞掉当帧几乎整个臂/工具轮廓，独立验证抓到的 RouteStick
   stick_violation（"整个机械臂/工具持续原样不处理"）即源于此。现在只有
   块内多数像素满足饱和有彩色（S>=60）或纯白高亮（S<=20&V>=230）才注册——
   真正需要跨帧保护的外来物体（拖动的白缆线、被夹的彩色方块）本身已经分别由
   white_veto/sat_veto 逐帧独立兜底，收紧注册门槛不削弱 HARD A。
2. **前推补洞改闭运算**：`_advect_forward` 原来每帧对累计到当前为止的整个
   持久保护集做一次无条件膨胀来补散射空洞，但膨胀只增不减、逐帧复利式扩张，
   与上一条叠加共同导致了多个任务里"整帧完全不处理"的可靠性问题（StopCube /
   VideoRepick / VideoUnmask 指尖帧命中率不稳）。改用形态学闭运算（先膨胀后
   腐蚀）：小空洞照样补上，但对整体边界是净零增长，不再逐帧无界扩张。

## 依赖纪律

只 import numpy / cv2 / 标准库 / `cv_base`（本文件不修改 `cv_base.py`）。
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cv_base import (  # noqa: E402
    ArmRemovalParams,
    _anchored_components,
    _border_seed,
    _close,
    _dilate,
    _foreground,
    _KERNEL3,
    _shadow_mask,
    build_background_plate,
    detect_static_occluder,
    learn_arm_appearance,
    segment_bounds,
)

NAME = "flow_affine_split"
DESCRIPTION = (
    "前后向一致的 Farneback 光流拟合臂的单一仿射刚体运动，只删仿射内点/静止一致"
    "像素，非臂色调的外点块注册为随流前推的持久保护集（闭运算补洞，不无界膨胀）；"
    "黑色指尖额外要求仿射内点加固；臂静止或纹理不足时整帧回退到外观+背景板新颖性通道。"
)

_CV_PARAMS_PATH = Path(__file__).resolve().parents[1] / "cv_base_params.json"


@dataclass(frozen=True)
class FlowParams:
    """本变体专属参数。前 21 项取自方案设计者给定的 spec；后 6 项是实现补白
    （spec 未列出数值，语义已在各自出现处写明），默认值经小规模试跑校准。"""

    # --- Farneback 双向光流 ---
    farneback_pyr_scale: float = 0.5
    farneback_levels: int = 5
    farneback_winsize: int = 25
    farneback_iterations: int = 3
    farneback_poly_n: int = 5
    farneback_poly_sigma: float = 1.2
    fb_consistency_max: float = 1.5  # 前后向一致性误差上限（像素）
    # --- 仿射拟合（加权 LS + RANSAC-lite）---
    affine_rounds: int = 3
    affine_inlier_fit: float = 2.0    # 拟合轮内重选内点的残差阈值
    affine_inlier_keep: float = 2.5   # 最终分类「仿射内点」的残差阈值
    affine_min_valid_px: int = 200    # 锚定域内可信像素少于此数判「不可拟合」
    grad_weight_floor: float = 0.05   # 归一化梯度权重下限
    affine_refit_min_px: int = 30     # 重选内点后少于此数放弃继续重拟合（实现补白）
    # --- 静止一致像素 ---
    static_flow_max: float = 0.4      # 实际位移幅值上限
    static_model_max: float = 0.6     # 仿射模型预测位移幅值上限
    arm_static_median_flow: float = 0.5  # 锚定域中位位移低于此值：整帧回退/跳过指尖加固
    # --- 外点保护集 ---
    outlier_area_min: int = 12        # 外点连通块达到该面积才注册进持久保护集
    outlier_register_nonarm_frac: float = 0.5  # 外点块须有多大比例饱和/纯白像素才注册（实现补白，见下方说明）
    keep_warp_close: int = 1          # 保护集正向散射后补洞的闭运算迭代次数（原为膨胀，见 _advect_forward 注释）
    # --- 收尾守卫生长 ---
    guard_grow_iter: int = 1
    # --- 兜底否决 ---
    plate_same_thresh: int = 6
    sat_veto_min: int = 60
    white_veto_s: int = 20
    white_veto_v: int = 230
    static_block_min_area: int = 20   # 板同色连通块达到该面积才整体保护（实现补白）
    static_block_dilate: int = 2      # 板同色连通块保护的膨胀半径（"⊕2"）
    # --- 黑色指尖几何规则 ---
    tip_s_max: int = 40
    tip_v_max: int = 100
    tip_area_min: int = 4             # spec 文字给的下限，JSON 参数表未列出（实现补白）
    tip_area_max: int = 90
    tip_width_max: float = 5.5        # 候选块自身 distanceTransform 半径上限
    tip_geo_frac: float = 0.75
    tip_limb_geo_min: float = 18.0
    tip_inlier_frac_min: float = 0.5  # 候选块内仿射内点像素占比下限（实现补白）
    geo_max_iter: int = 120           # 测地距离 BFS 最大轮数（实现补白，控耗时）


# ---------------------------------------------------------------------------
# 光流：前后向计算 + 一致性校验
# ---------------------------------------------------------------------------


def _fb_consistency_error(flow_a: np.ndarray, flow_b: np.ndarray, grid_x: np.ndarray, grid_y: np.ndarray) -> np.ndarray:
    """按 flow_a 把 flow_b 采样过来，算前后向闭合误差 |flow_a + sampled(flow_b)|。

    采样点越界视为不可信（误差记极大值），不依赖 remap 的边界外推行为。
    """
    height, width = flow_a.shape[:2]
    sample_x = grid_x + flow_a[..., 0]
    sample_y = grid_y + flow_a[..., 1]
    sampled_b = cv2.remap(
        flow_b, sample_x, sample_y, interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=(1e6, 1e6),
    )
    err = np.hypot(flow_a[..., 0] + sampled_b[..., 0], flow_a[..., 1] + sampled_b[..., 1])
    out_of_bounds = (sample_x < 0) | (sample_x > width - 1) | (sample_y < 0) | (sample_y > height - 1)
    err[out_of_bounds] = 1e6
    return err


def _compute_flow_fields(gray: np.ndarray, fp: FlowParams) -> tuple[np.ndarray, np.ndarray]:
    """逐帧「自身流场」与前后向一致性有效位。

    每帧 i（i<n-1）取 forward 流 gray[i]->gray[i+1]；末帧没有下一帧，取上一对
    的 backward 流 gray[n-1]->gray[n-2] 代替（即「末帧用 t-1→t 的反向流代替」）。
    返回 (own_flow (n,H,W,2) float32, valid (n,H,W) bool)。
    """
    n, height, width = gray.shape
    own_flow = np.zeros((n, height, width, 2), np.float32)
    valid = np.zeros((n, height, width), bool)
    if n < 2:
        return own_flow, valid
    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32)
    )
    for i in range(n - 1):
        flow_f = cv2.calcOpticalFlowFarneback(
            gray[i], gray[i + 1], None,
            fp.farneback_pyr_scale, fp.farneback_levels, fp.farneback_winsize,
            fp.farneback_iterations, fp.farneback_poly_n, fp.farneback_poly_sigma,
            cv2.OPTFLOW_FARNEBACK_GAUSSIAN,
        )
        flow_b = cv2.calcOpticalFlowFarneback(
            gray[i + 1], gray[i], None,
            fp.farneback_pyr_scale, fp.farneback_levels, fp.farneback_winsize,
            fp.farneback_iterations, fp.farneback_poly_n, fp.farneback_poly_sigma,
            cv2.OPTFLOW_FARNEBACK_GAUSSIAN,
        )
        own_flow[i] = flow_f
        valid[i] = _fb_consistency_error(flow_f, flow_b, grid_x, grid_y) <= fp.fb_consistency_max
        if i == n - 2:
            own_flow[n - 1] = flow_b
            valid[n - 1] = _fb_consistency_error(flow_b, flow_f, grid_x, grid_y) <= fp.fb_consistency_max
    return own_flow, valid


# ---------------------------------------------------------------------------
# 仿射拟合：加权最小二乘 + RANSAC-lite 重选内点
# ---------------------------------------------------------------------------


def _fit_affine(
    fit_domain: np.ndarray,
    flow: np.ndarray,
    grad_weight: np.ndarray,
    xx: np.ndarray,
    yy: np.ndarray,
    fp: FlowParams,
) -> tuple[np.ndarray, np.ndarray]:
    """在 fit_domain（锚定域内可信像素）上拟合单一仿射运动，返回逐像素
    (残差图, 模型预测位移幅值图)——两者都在整幅图上算，供调用方按需索引。
    """
    height, width = flow.shape[:2]
    centroid_y = float(yy[fit_domain].mean())
    centroid_x = float(xx[fit_domain].mean())
    xc = xx - centroid_x
    yc = yy - centroid_y

    idx = fit_domain
    res_map = None
    pred_mag = None
    for round_i in range(fp.affine_rounds):
        if int(idx.sum()) < fp.affine_refit_min_px:
            break
        xs = xc[idx]
        ys = yc[idx]
        us = flow[..., 0][idx]
        vs = flow[..., 1][idx]
        ws = grad_weight[idx]
        design = np.stack([xs, ys, np.ones_like(xs)], axis=1)  # (K,3)
        weighted_design = design * ws[:, None]
        normal = design.T @ weighted_design  # 加权正规方程系数矩阵 (3,3)
        rhs_u = design.T @ (ws * us)
        rhs_v = design.T @ (ws * vs)
        coef_u, *_ = np.linalg.lstsq(normal, rhs_u, rcond=None)
        coef_v, *_ = np.linalg.lstsq(normal, rhs_v, rcond=None)
        pred_u = coef_u[0] * xc + coef_u[1] * yc + coef_u[2]
        pred_v = coef_v[0] * xc + coef_v[1] * yc + coef_v[2]
        res_map = np.hypot(pred_u - flow[..., 0], pred_v - flow[..., 1])
        pred_mag = np.hypot(pred_u, pred_v)
        if round_i < fp.affine_rounds - 1:
            idx = fit_domain & (res_map <= fp.affine_inlier_fit)

    if res_map is None:
        # 理论上不会发生：调用方已保证 fit_domain 计数 >= affine_min_valid_px
        res_map = np.full((height, width), np.inf, np.float32)
        pred_mag = np.zeros((height, width), np.float32)
    return res_map, pred_mag


# ---------------------------------------------------------------------------
# 测地距离（沿 mask 连通形状、以种子为源的 BFS 距离，非欧氏直线距离）
# ---------------------------------------------------------------------------


def _geodesic_distance(mask: np.ndarray, seed_in_mask: np.ndarray, max_iter: int) -> np.ndarray:
    """用逐轮膨胀近似「沿 mask 形状、以种子为源」的测地距离。

    未被 mask 覆盖到、或超过 max_iter 仍未被种子波及的像素记 -1。用膨胀步数
    近似距离足够本变体使用——只关心候选块相对于同一 mask 内其它点的相对深度，
    不需要精确像素单位。
    """
    dist = np.full(mask.shape, -1, np.int32)
    frontier = (seed_in_mask & mask).astype(np.uint8)
    if not frontier.any():
        return dist
    dist[frontier.astype(bool)] = 0
    mask_u8 = mask.astype(np.uint8)
    current = frontier
    step = 0
    while step < max_iter:
        step += 1
        grown = cv2.dilate(current, _KERNEL3, iterations=1) & mask_u8
        newly = grown.astype(bool) & (dist < 0)
        if not newly.any():
            break
        dist[newly] = step
        current = newly.astype(np.uint8)
    return dist


# ---------------------------------------------------------------------------
# 黑色指尖识别
# ---------------------------------------------------------------------------


def _detect_tip(
    main: np.ndarray,
    occluder: np.ndarray,
    seed: np.ndarray,
    hsv: np.ndarray,
    use_motion: bool,
    median_flow: float,
    valid: np.ndarray,
    res_map: np.ndarray | None,
    fp: FlowParams,
) -> np.ndarray:
    """几何规则找候选黑块（无彩暗 + 面积 + 瘦长 + 肢体测地远端），臂在动的帧
    额外要求候选是仿射内点（运动加固）；臂静止帧只用几何。"""
    height, width = main.shape
    if not main.any():
        return np.zeros((height, width), bool)

    dark = (hsv[..., 1] <= fp.tip_s_max) & (hsv[..., 2] <= fp.tip_v_max) & main & ~occluder
    if not dark.any():
        return np.zeros((height, width), bool)

    seed_in_main = seed & main
    geo = _geodesic_distance(main, seed_in_main, fp.geo_max_iter)
    reached = geo >= 0
    if not reached.any():
        return np.zeros((height, width), bool)
    gmax = float(geo[reached].max())
    if gmax < fp.tip_limb_geo_min:
        return np.zeros((height, width), bool)
    geo_floor = max(gmax - 12.0, fp.tip_geo_frac * gmax, fp.tip_limb_geo_min)

    dist_within_dark = cv2.distanceTransform(dark.astype(np.uint8), cv2.DIST_L2, 5)

    reinforce = use_motion and (median_flow >= fp.arm_static_median_flow) and (res_map is not None)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(dark.astype(np.uint8), connectivity=8)
    tip = np.zeros((height, width), bool)
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < fp.tip_area_min or area > fp.tip_area_max:
            continue
        blob = labels == label
        if float(dist_within_dark[blob].max()) > fp.tip_width_max:
            continue
        blob_reached = blob & reached
        if not blob_reached.any():
            continue
        if float(geo[blob_reached].max()) < geo_floor:
            continue
        if reinforce:
            inlier_frac = float((valid[blob] & (res_map[blob] <= fp.affine_inlier_keep)).mean())
            if inlier_frac < fp.tip_inlier_frac_min:
                continue
        tip |= blob
    return tip


# ---------------------------------------------------------------------------
# 保护集正向前推
# ---------------------------------------------------------------------------


def _advect_forward(keep: np.ndarray, flow: np.ndarray, close_iter: int) -> np.ndarray:
    """把当前保护集的每个像素按其光流位移正向散射到下一帧坐标，散射后补洞。

    补洞修复（v3.1 复核后修正）：散射是"每个源像素独立取整后落到一个目标像素"，
    相邻源像素的光流有细微差异时，目标点之间会漏出针孔状空洞——这才是"补洞"要
    处理的问题。原实现用纯 `_dilate` 补洞，但 `_dilate` 只增不减，且每帧都对
    **累计到当前为止的整个保护集**重新调用一次：同一批像素的边界每帧都会被
    无条件再向外推 `close_iter` 像素，25~300 帧的一段下来，早期注册的一小块
    外点会被复利式地越滚越大，最终吞掉整条机械臂的活动范围（实测 RouteStick
    到 segment 中段 persistent_keep 已膨胀到 15000+ 像素，几乎覆盖当帧整个
    臂/工具轮廓，导致该帧红遮罩几乎不删除任何东西——这正是独立验证抓到的
    RouteStick stick_violation 与多任务"整帧完全不处理"的根因）。改用形态学
    闭运算（先膨胀后腐蚀，`_close`）：小空洞被同样填补，但补洞操作对边界是
    净零增长，不会把"填洞"误用成"逐帧无界扩张的膨胀"。
    """
    height, width = keep.shape
    out = np.zeros((height, width), bool)
    if not keep.any():
        return out
    ys, xs = np.nonzero(keep)
    kx = np.clip(np.round(xs + flow[ys, xs, 0]).astype(np.int64), 0, width - 1)
    ky = np.clip(np.round(ys + flow[ys, xs, 1]).astype(np.int64), 0, height - 1)
    out[ky, kx] = True
    return _close(out, close_iter)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def compute_masks(
    frames: np.ndarray, phase_flags: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    frames = np.ascontiguousarray(frames)
    n_total, height, width = frames.shape[:3]
    total_pixels = height * width

    cvp = ArmRemovalParams.from_json(_CV_PARAMS_PATH)
    fp = FlowParams()

    remove_masks = np.zeros((n_total, height, width), bool)
    tip_masks = np.zeros((n_total, height, width), bool)

    grid = np.mgrid[0:height, 0:width].astype(np.float32)
    yy, xx = grid[0], grid[1]

    segments_info: list[dict[str, Any]] = []
    affine_pixel_total = 0
    fallback_pixel_total = 0
    outlier_registered_total = 0
    tip_pixel_total = 0
    per_frame_affine_fraction: list[float] = []
    per_frame_fallback_fraction: list[float] = []
    per_frame_use_motion: list[bool] = []

    for seg_start, seg_end in segment_bounds(phase_flags):
        seg_frames = frames[seg_start:seg_end]
        n = seg_frames.shape[0]

        plate, mode_fraction = build_background_plate(seg_frames, cvp)
        foregrounds = np.stack([_foreground(seg_frames[i], plate, cvp) for i in range(n)])
        border = _border_seed((height, width), cvp)
        s_thr, v_min, appearance_px = learn_arm_appearance(seg_frames, foregrounds, border, cvp)
        occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, cvp)
        if appearance_px < 200 and occluder.any():
            retry = learn_arm_appearance(seg_frames, foregrounds, border | _dilate(occluder, 1), cvp)
            if retry[2] > appearance_px:
                s_thr, v_min, appearance_px = retry
                occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, cvp)
        seed = border | _dilate(occluder, 1)

        plate_hsv = cv2.cvtColor(plate, cv2.COLOR_RGB2HSV)
        v_floor = min(v_min, float(cvp.occluder_val_cap))
        if cvp.stuck_fill:
            stuck_zone = (
                (plate_hsv[..., 1] <= s_thr)
                & (plate_hsv[..., 2] >= v_floor)
                & (mode_fraction < cvp.stuck_max_mode_fraction)
            )
        else:
            stuck_zone = np.zeros((height, width), bool)

        gray = np.stack([cv2.cvtColor(seg_frames[i], cv2.COLOR_RGB2GRAY) for i in range(n)])
        own_flow, flow_valid = _compute_flow_fields(gray, fp)

        persistent_keep = np.zeros((height, width), bool)
        seg_affine_px = 0
        seg_fallback_px = 0
        seg_outlier_registered = 0
        seg_tip_px = 0

        for offset in range(n):
            frame = seg_frames[offset]
            hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
            fg = foregrounds[offset]
            if cvp.stuck_fill and stuck_zone.any():
                frame_armlike = (hsv[..., 1] <= max(2.0 * s_thr, 25.0)) & (hsv[..., 2] >= 25)
                fg = fg | (stuck_zone & frame_armlike)

            anchored = _anchored_components(fg, seed)
            anchor_domain = anchored & ~occluder

            flow = own_flow[offset]
            valid = flow_valid[offset]
            flow_mag = np.hypot(flow[..., 0], flow[..., 1])

            valid_count = int((anchor_domain & valid).sum())
            median_flow = float(np.median(flow_mag[anchor_domain])) if anchor_domain.any() else 0.0
            use_motion = (
                anchor_domain.any()
                and valid_count >= fp.affine_min_valid_px
                and median_flow >= fp.arm_static_median_flow
            )

            appearance_ok = (hsv[..., 1] <= s_thr) & (hsv[..., 2] >= v_min)
            res_map = None

            if use_motion:
                gray_frame = gray[offset]
                gx = cv2.Scharr(gray_frame, cv2.CV_32F, 1, 0)
                gy = cv2.Scharr(gray_frame, cv2.CV_32F, 0, 1)
                grad_mag = np.hypot(gx, gy)
                gmax = float(grad_mag.max())
                grad_weight = (grad_mag / gmax if gmax > 1e-6 else np.zeros_like(grad_mag)) + fp.grad_weight_floor

                fit_domain = anchor_domain & valid
                res_map, pred_mag = _fit_affine(fit_domain, flow, grad_weight, xx, yy, fp)

                inlier = valid & (res_map <= fp.affine_inlier_keep)
                static_ok = (flow_mag < fp.static_flow_max) & (pred_mag < fp.static_model_max)
                motion_arm = anchor_domain & (inlier | static_ok)
                unresolved = anchor_domain & ~valid & ~static_ok
                fallback_arm = unresolved & appearance_ok
                arm_component_region = motion_arm | fallback_arm
                affine_px = int(motion_arm.sum())
                fallback_px = int(fallback_arm.sum())
            else:
                arm_component_region = anchor_domain & appearance_ok
                affine_px = 0
                fallback_px = int(arm_component_region.sum())

            outlier_raw = anchor_domain & ~arm_component_region

            seg_affine_px += affine_px
            seg_fallback_px += fallback_px
            per_frame_affine_fraction.append(affine_px / total_pixels)
            per_frame_fallback_fraction.append(fallback_px / total_pixels)
            per_frame_use_motion.append(bool(use_motion))

            if outlier_raw.any():
                oc_count, oc_labels, oc_stats, _ = cv2.connectedComponentsWithStats(
                    outlier_raw.astype(np.uint8), connectivity=8
                )
                # 外点块须多数像素满足"非臂外观"（饱和有彩色，或缆线/按钮那种
                # 纯白材质 S<=20&V>=230）才有资格注册进持久保护集（复核后新增
                # 判据，见下方说明）；面积达标但灰阶臂色调的块不注册——它这一帧
                # 该不该删仍由原有仿射内点/外观兜底逻辑决定（不受影响，最多只是
                # 这一帧漏删，即"牺牲删除"，绝不会把它错认成外来物体永久保护）。
                #
                # 动机：全局单一仿射对多连杆臂只是粗糙近似，臂/工具自身在关节处
                # 或末端刚体（如 stick 工具相对前臂的独立旋转）天然会产生残差
                # 超限的"外点"，但这些外点像素多数仍是灰阶臂色——不是真正附着的
                # 外来物体。若不设外观门槛，这些臂自身的仿射残差会被当作"附着物"
                # 逐帧注册进 persistent_keep 并随光流前推，多段实测（RouteStick /
                # StopCube / VideoRepick / VideoUnmask）显示这个保护集在 20~25
                # 帧内就能滚雪球式吞掉当帧几乎整个臂/工具轮廓，导致该帧红遮罩
                # 几乎不删除任何东西——这正是独立验证抓到的 RouteStick
                # stick_violation（"整个机械臂/工具持续原样不处理"）与其余三个
                # 任务指尖帧"整帧完全不处理"可靠性问题的根因。
                # 真正需要跨帧持久保护的外来物体（拖动的白缆线、被夹的彩色方块）
                # 本身就已经分别由 white_veto（S<=20&V>=230）与 sat_veto（S>=60）
                # 在【每一帧】独立兜底，不依赖 persistent_keep 也天然安全——这里
                # 收紧注册门槛不会削弱 HARD A 的物体保护，只是不再让臂自身的
                # 仿射拟合残差误诊为「附着物体」。
                newly_registered = np.zeros((height, width), bool)
                for label in range(1, oc_count):
                    if oc_stats[label, cv2.CC_STAT_AREA] < fp.outlier_area_min:
                        continue
                    comp = oc_labels == label
                    comp_s = hsv[..., 1][comp]
                    comp_v = hsv[..., 2][comp]
                    comp_nonarm = (comp_s >= fp.sat_veto_min) | (
                        (comp_s <= fp.white_veto_s) & (comp_v >= fp.white_veto_v)
                    )
                    if float(comp_nonarm.mean()) >= fp.outlier_register_nonarm_frac:
                        newly_registered |= comp
                if newly_registered.any():
                    persistent_keep = persistent_keep | newly_registered
                    seg_outlier_registered += int(newly_registered.sum())

            main = occluder | arm_component_region
            shadow = _shadow_mask(frame, plate, fg, main, cvp)

            tip = _detect_tip(
                main, occluder, seed, hsv, use_motion, median_flow, valid, res_map, fp
            )
            seg_tip_px += int(tip.sum())

            diff_plate = np.abs(frame.astype(np.int16) - plate.astype(np.int16)).max(axis=-1)
            plate_same_raw = diff_plate <= fp.plate_same_thresh
            sat_veto = hsv[..., 1] >= fp.sat_veto_min
            white_veto = (hsv[..., 1] <= fp.white_veto_s) & (hsv[..., 2] >= fp.white_veto_v)

            static_block_veto = np.zeros((height, width), bool)
            if plate_same_raw.any():
                sb_count, sb_labels, sb_stats, _ = cv2.connectedComponentsWithStats(
                    plate_same_raw.astype(np.uint8), connectivity=8
                )
                for label in range(1, sb_count):
                    if sb_stats[label, cv2.CC_STAT_AREA] >= fp.static_block_min_area:
                        static_block_veto |= _dilate(sb_labels == label, fp.static_block_dilate)

            # 常驻底座区（occluder）对背景差分天然失明——它逐帧与背景板同色本就是
            # detect_static_occluder 的判据来源，拿"与板同色"去否决它会直接废掉
            # occluder 存在的意义（cv_base 原语义是 `main = anchored | occluder`
            # 无条件强删）。但 occluder 是从"整段背景板"学出来的静态区域，某一帧里
            # 臂离开后完全可能露出真实桌面/物体——这时当前帧的饱和度/纯白度是
            # 仍然有效的信号，须继续生效；只有"与板同色"这一路否决专门用来在
            # 非 occluder 区域甄别"被并入背景板的静态物体"，天然不适用于 occluder。
            plate_specific_veto = (plate_same_raw | static_block_veto) & ~occluder
            veto = sat_veto | white_veto | plate_specific_veto
            protected = persistent_keep | veto

            candidate = main | shadow
            final_remove = candidate & ~protected & ~tip

            grown = _dilate(final_remove, fp.guard_grow_iter) & fg & ~protected & ~tip
            final_remove = final_remove | grown
            final_remove = final_remove & ~tip

            remove_masks[seg_start + offset] = final_remove
            tip_masks[seg_start + offset] = tip

            if offset < n - 1:
                persistent_keep = _advect_forward(persistent_keep, own_flow[offset], fp.keep_warp_close)

        affine_pixel_total += seg_affine_px
        fallback_pixel_total += seg_fallback_px
        outlier_registered_total += seg_outlier_registered
        tip_pixel_total += seg_tip_px
        segments_info.append(
            {
                "start": int(seg_start),
                "end": int(seg_end),
                "phase_is_video_demo": bool(phase_flags[seg_start]) if phase_flags.size else False,
                "arm_sat_threshold": float(s_thr),
                "arm_value_min": float(v_min),
                "appearance_sample_pixels": int(appearance_px),
                "static_occluder": occluder_info,
                "affine_pixel_total": seg_affine_px,
                "fallback_pixel_total": seg_fallback_px,
                "outlier_registered_pixel_total": seg_outlier_registered,
                "tip_pixel_total": seg_tip_px,
            }
        )

    stats: dict[str, Any] = {
        "frame_count": int(n_total),
        "segment_count": len(segments_info),
        "segments": segments_info,
        "affine_pixel_total": int(affine_pixel_total),
        "fallback_pixel_total": int(fallback_pixel_total),
        "outlier_registered_pixel_total": int(outlier_registered_total),
        "tip_pixel_total": int(tip_pixel_total),
        "frames_use_motion": int(sum(per_frame_use_motion)),
        "frames_fallback_only": int(n_total - sum(per_frame_use_motion)),
        "per_frame_affine_fraction": per_frame_affine_fraction,
        "per_frame_fallback_fraction": per_frame_fallback_fraction,
        "per_frame_use_motion": per_frame_use_motion,
    }
    return remove_masks, tip_masks, stats
