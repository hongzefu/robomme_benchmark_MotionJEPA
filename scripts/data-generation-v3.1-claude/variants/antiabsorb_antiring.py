"""变体 antiabsorb_antiring：拆掉 v3 的三把"杀物体"利器，逐处外科手术式改写。

设计思路（详见 scheme designer 的 spec，本文件是其落地实现）：v3 的臂删除算法在
四类场景下会误删/误圈任务物体——(1) 碎片吸附 `_absorb_fragments` 把静止白按钮
当"被切断的臂碎片"吸进 mask；(2) `stuck_fill` 把静止无彩物体当"被臂污染的背景"
误纳；(3) `detect_static_occluder` 把从未被臂真正扫过的常驻无彩块（黑色任务装置、
白色按钮座）当底座整块恒红；(4) 收尾的无条件 3×3 膨胀在物体贴着臂主体时描出一圈
红边、且对被夹物体只有饱和度保护、留不住低饱和/白色物体的边缘。

本变体保留 v3 的整体骨架（背景板/前景/锚定/外观模型/阴影仍是 `cv_base` 原语），
只在上述四个失效点各自加一道"证据门控"，并把物体保护面从"仅高饱和"扩到"高饱和
∪ 纯白 ∪ 板色一致 ∪ 过境证据不足的常驻块"，外加对最终 mask 做"贴边环显式释放"。
另外新增一条黑色指尖识别规则（基于测地距离——沿臂身连通路径到画面边缘的步数——
把手指末端的小黑色橡胶垫从手掌/腕部支架的其他黑色部件里挑出来），供 14 个夹爪
任务使用；两个 panda_stick 任务（PatternLock、RouteStick）里这条规则自然找不到
任何候选（工具杆本身没有黑色远端，候选块也会因面积/宽度超限被拒），机器人整体
可以全删。

## 算法结构（每个相位段独立执行，两遍扫描）

**第一遍（全段扫描，只算不涂）**：
- 背景板 `plate` + 众数占比 `mode_fraction`（复用 `build_background_plate`）；
- 每帧前景 `foregrounds[i]`（复用 `_foreground`）；
- 边带种子 `border`（复用 `_border_seed`）；
- 臂外观模型 `s_thr / v_min`（复用 `learn_arm_appearance`，边带种子）；
- 仅用边带种子的每帧锚定域 `anchored1[i]`，据此得到：
  - 逐帧"锚定域出现的列"矩阵 `anchored_col_present`（供常驻区过境判据的列重叠检验用）；
  - 锚定域并集 `anchored_union`（供 stuck 规则的空间闸门用）；
- 常驻区检测 `_detect_occluder_v2`：在 v3 原判据（无彩+触顶+宽度/面积上限）基础上
  新增"过境证据"——候选块至少 25% 像素众数占比 ≤0.9（确实被臂盖过/露出过）、且
  候选块列跨度至少在 30% 的帧里与该帧的锚定列有交集（确实见过臂从这附近经过）；
  两条都满足才接受为常驻区（`occluder_accepted`，涂法改为逐帧 `occ & armlike_t`
  条件涂，不再整段恒红）；不满足的候选块进入 `occluder_rejected`，转做物体保护的
  一条来源（"板异常静止物体块"）。必要时按 v3 原逻辑做二轮外观学习重试。
- 逐帧臂色掩膜 `frame_armlike[i]` 与其在全段的时间占比 `f_arm`（用于 stuck 规则的
  "既不是从不覆盖、也不是永远覆盖"窗口判据）；
- stuck 污染区 `stuck_zone`：在 v3"板上无彩+众数占比低"两条基础上，新增"f_arm 落在
  [0.15,0.90]（短段放宽到 [0.10,0.92]）"与"落在锚定域并集膨胀 6px 内"两条，四条
  全中才纳入（比 v3 更保守，专挑"确实是臂反复经过但暂时被板污染"的区域，静止无彩
  物体的 f_arm 恒为 0 或 1，天然被这条窗口滤掉）；
- 用 `stuck_zone` 与最终 `seed_final = border | dilate(occluder_accepted,1)` 算出
  每帧"吸附前主体" `main0[i]`（锚定域 ∪ 条件涂法的常驻区），供第二遍的碎片吸附
  时间连续性判据引用相邻帧。

**第二遍（逐帧组装）**：
- 碎片吸附 `_absorb_fragments_v2`：距离、臂色占比、面积三条 v3 原判据之外，新增
  "纯白像素占比 ≤2%"、"高饱和像素占比 ≤2%"（防止白色/彩色物体碎片被当臂碎片吸收）、
  "与 t-1 或 t+1 帧的 `main0` 重叠 ≥30%"（防止静止孤立物体因为偶然落在臂附近被
  一次性误吸——真臂碎片在相邻帧应仍与臂主体大致重叠，静止物体则不会）；
- 阴影（原样复用 `_shadow_mask`）；
- 物体保护集 `keepset`（逐帧高饱和∪纯白∪板色一致，加段级"过境证据不足的常驻块"）；
- 黑色指尖识别 `_detect_tip`：在吸附后、膨胀前的 `main` 上找小面积、窄、且测地距离
  接近本帧臂全局最远点的黑色连通块，候选还必须不与 `keepset` 相交；
- 收尾"带守卫膨胀"：`dilate(main|shadow,2)` 换成
  `dilate(main|shadow,2) & (前景∪板臂色) & ~dilate(keepset,1)`——膨胀只允许长进
  "确实是这帧前景或板上历史臂色区域"且不触碰保护集的方向，保护集本身直接把已经
  混进主体的物体像素也一并挖掉（这一步天然把"贴着臂的物体"抠成一个洞）；
- 显式贴边环释放：在膨胀结果里找形态学洞（`_fill_holes(m) & ~m`），洞内"非臂调色
  板"像素占比够高就判定是真物体洞，把洞边一圈释放回原始像素（撤销"贴边红环"）；
- 最终再显式 `& ~keepset` 兜底（大多数情况下已被膨胀守卫排除，这里只是双保险）。

## 依赖纪律
只 import numpy / cv2 / 标准库 / `cv_base`；不出现任何仿真分割相关标识符。
"""

from __future__ import annotations

import sys
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
    _fill_holes,
    _foreground,
    _shadow_mask,
    _MIN_APPEARANCE_PIXELS,
    build_background_plate,
    learn_arm_appearance,
    segment_bounds,
)

NAME = "antiabsorb_antiring"
DESCRIPTION = (
    "拆掉 v3 的三把杀物体利器（碎片吸附/常驻区恒红/无条件膨胀），全部改成需要"
    "过境证据或臂色自证才放行，并在收尾新增带守卫膨胀 + 贴边环显式释放 + "
    "高饱和∪纯白∪板色一致∪常驻区拒判块四路物体保护；另按测地距离新增黑色指尖识别"
)

_PARAMS_PATH = Path(__file__).resolve().parents[1] / "cv_base_params.json"
_KERNEL3 = np.ones((3, 3), np.uint8)


class _P:
    """本变体专属可调参数，取值取自 scheme designer 给定的 spec["params"]。

    注：渲染器用 ``importlib.util.spec_from_file_location`` 动态加载变体模块但不
    注册进 ``sys.modules``（见 ``render_variant_outputs.load_variant``），这会让
    ``@dataclass`` 装饰器在解析 ``cls.__module__`` 时因 ``sys.modules.get(...)``
    返回 ``None`` 而崩溃；本类无需实例可变性，改用普通类属性规避该问题。
    """

    stuck_max_mode_fraction = 0.9
    f_arm_lo = 0.15
    f_arm_hi = 0.9
    f_arm_lo_shortseg = 0.10
    f_arm_hi_shortseg = 0.92
    shortseg_frame_threshold = 20  # 段内帧数低于此值视为"短段"，f_arm 窗口放宽
    stuck_union_dilate = 6
    absorb_max_area = 200
    absorb_distance = 8.0
    absorb_arm_ratio = 0.9
    absorb_white_frac_max = 0.02
    absorb_sat_frac_max = 0.02
    absorb_temporal_overlap = 0.3
    occluder_transit_frac_min = 0.25
    occluder_col_overlap_min = 0.3
    arm_dilate = 2
    keep_guard_dilate = 1
    ring_hole_area_min = 20
    ring_nonarm_frac_min = 0.5
    ring_dilate = 3
    protect_sat_min = 60
    white_veto_s = 20
    white_veto_v = 230
    plate_same_thresh = 6
    tip_s_max = 40
    tip_v_max = 100
    tip_area_min = 4  # spec 正文给出、未列入 params 字典，此处按正文补入
    tip_area_max = 90
    tip_width_max = 5.5
    tip_geo_frac = 0.75
    tip_geo_margin = 12.0  # spec 正文 "gmax-12"，未列入 params 字典
    tip_limb_geo_min = 18.0  # 以 params 字典的 18 为准（正文写 15，字典优先）
    tip_gmax_min = 18.0


def _armlike(hsv: np.ndarray, s_thr: float, v_floor: float) -> np.ndarray:
    """通用"臂调色板"判据：放宽后的无彩阈值，供 stuck/环释放/守卫膨胀共用。"""
    return (hsv[..., 1] <= max(2.0 * s_thr, 25.0)) & (hsv[..., 2] >= v_floor)


def _geodesic_dist(mask: np.ndarray, seed: np.ndarray, max_iter: int = 260) -> np.ndarray:
    """mask 内以 seed 为起点、沿 mask 连通路径的测地距离（8 邻域步数）。

    未连通到 seed 的像素记 -1。用重复膨胀做多源 BFS：每轮把前沿在 mask 内扩一圈，
    新覆盖的像素记为当前轮数。指尖必须是"沿臂身走到最远处"的判据，用直线欧氏距离
    在臂弯折时会算错，因此用这个而不是 cv2.distanceTransform。
    """
    dist = np.full(mask.shape, -1, dtype=np.int32)
    frontier = seed & mask
    if not frontier.any():
        return dist
    dist[frontier] = 0
    visited = frontier.copy()
    step = 0
    while step < max_iter:
        remaining = mask & ~visited
        if not remaining.any():
            break
        step += 1
        grown = cv2.dilate(frontier.astype(np.uint8), _KERNEL3, iterations=1).astype(bool)
        newly = grown & mask & ~visited
        if not newly.any():
            break
        dist[newly] = step
        visited |= newly
        frontier = newly
    return dist


def _detect_occluder_v2(
    plate: np.ndarray,
    mode_fraction: np.ndarray,
    s_thr: float,
    v_min: float,
    anchored_col_present: np.ndarray,
    base_params: ArmRemovalParams,
    params: _P,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """常驻区检测：v3 原判据 + 过境证据（众数占比 + 列重叠）双门控。

    返回 (accepted, rejected, info)。accepted 只用于逐帧条件涂法（`occ & armlike_t`），
    不再整段恒红；rejected 是"无彩但从未被真正扫过的常驻块"，转做物体保护的一条
    来源（`keepset` 条件 4）。
    """
    height, width = plate.shape[:2]
    info: dict[str, Any] = {
        "status": "off",
        "bbox": None,
        "area": 0,
        "rejected_oversize": 0,
        "rejected_no_transit": 0,
    }
    zeros = np.zeros((height, width), bool)
    if base_params.static_occluder_mode == "off":
        return zeros, zeros, info
    if base_params.static_occluder_mode == "box":
        if base_params.static_occluder_box is None:
            raise ValueError("static_occluder_mode=box 时必须提供 static_occluder_box")
        r0, r1, c0, c1 = base_params.static_occluder_box
        region = zeros.copy()
        region[r0:r1, c0:c1] = True
        info.update(status="box", bbox=[int(r0), int(r1), int(c0), int(c1)], area=int(region.sum()))
        return region, zeros, info  # box 模式是人工划定，信任用户，不做过境证据否决
    if base_params.static_occluder_mode != "learned":
        raise ValueError(f"未知 static_occluder_mode：{base_params.static_occluder_mode}")

    hsv = cv2.cvtColor(plate, cv2.COLOR_RGB2HSV)
    v_floor = min(v_min, float(base_params.occluder_val_cap))
    achromatic = (hsv[..., 1] <= s_thr) & (hsv[..., 2] >= v_floor)
    achromatic = _close(achromatic, 1)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(achromatic.astype(np.uint8), connectivity=8)
    accepted = zeros.copy()
    rejected = zeros.copy()
    rejected_oversize = 0
    rejected_no_transit = 0
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        if y >= base_params.occluder_top_rows:
            continue  # 不触顶：既不是候选常驻区也不纳入保护，避免整张桌面被囫囵纳入
        if w > base_params.occluder_max_width or area > base_params.occluder_area_max:
            rejected_oversize += 1
            continue
        if area < base_params.occluder_area_min:
            continue
        comp = labels == label
        transit_frac = float((mode_fraction[comp] <= params.stuck_max_mode_fraction).mean())
        col_mask = comp.any(axis=0)
        cols = np.flatnonzero(col_mask)
        col_lo, col_hi = int(cols.min()), int(cols.max()) + 1
        col_overlap = float(anchored_col_present[:, col_lo:col_hi].any(axis=1).mean())
        if transit_frac < params.occluder_transit_frac_min or col_overlap < params.occluder_col_overlap_min:
            rejected_no_transit += 1
            rejected |= comp
            continue
        accepted |= comp
    info["rejected_oversize"] = rejected_oversize
    info["rejected_no_transit"] = rejected_no_transit
    rejected = _fill_holes(rejected) if rejected.any() else rejected
    if not accepted.any():
        info["status"] = "none"
        return accepted, rejected, info
    region = _dilate(_fill_holes(accepted), base_params.occluder_dilate)
    rows, cols = np.nonzero(region)
    info.update(
        status="ok",
        bbox=[int(rows.min()), int(rows.max()) + 1, int(cols.min()), int(cols.max()) + 1],
        area=int(region.sum()),
    )
    return region, rejected, info


def _absorb_fragments_v2(
    main: np.ndarray,
    foreground: np.ndarray,
    hsv: np.ndarray,
    s_thr: float,
    v_min: float,
    arm_prev: np.ndarray | None,
    arm_next: np.ndarray | None,
    params: _P,
) -> tuple[np.ndarray, int, dict[str, int]]:
    """碎片吸附六条门控：面积/距离/臂色占比（v3 原三条）+ 纯白占比/高饱和占比/
    时间连续性（本变体新增三条）。六条全中才吸，逐条拒绝计数进 stats。"""
    reject = {"area": 0, "dist": 0, "armratio": 0, "white": 0, "sat": 0, "temporal": 0}
    leftover = foreground & ~main
    if not leftover.any():
        return main, 0, reject
    dist = cv2.distanceTransform((~main).astype(np.uint8), cv2.DIST_L2, 3)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(leftover.astype(np.uint8), connectivity=8)
    armlike = (hsv[..., 1] <= 2.0 * s_thr) & (hsv[..., 2] >= v_min)
    white = (hsv[..., 2] >= params.white_veto_v) & (hsv[..., 1] <= params.white_veto_s)
    sat = hsv[..., 1] >= params.protect_sat_min
    neighbor_union = np.zeros_like(main)
    if arm_prev is not None:
        neighbor_union |= arm_prev
    if arm_next is not None:
        neighbor_union |= arm_next
    absorbed = 0
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area > params.absorb_max_area:
            reject["area"] += 1
            continue
        comp = labels == label
        if float(dist[comp].min()) > params.absorb_distance:
            reject["dist"] += 1
            continue
        if float(armlike[comp].mean()) < params.absorb_arm_ratio:
            reject["armratio"] += 1
            continue
        if float(white[comp].mean()) > params.absorb_white_frac_max:
            reject["white"] += 1
            continue
        if float(sat[comp].mean()) > params.absorb_sat_frac_max:
            reject["sat"] += 1
            continue
        overlap = float((comp & neighbor_union).sum()) / float(comp.sum()) if neighbor_union.any() else 0.0
        if overlap < params.absorb_temporal_overlap:
            reject["temporal"] += 1
            continue
        main = main | comp
        absorbed += 1
    return main, absorbed, reject


def _release_rings(m: np.ndarray, armlike: np.ndarray, params: _P) -> tuple[np.ndarray, int]:
    """在 m 内部找洞，洞内非臂色像素占比够高就判定是真物体洞，释放洞边一圈。"""
    if not m.any():
        return m, 0
    filled = _fill_holes(m)
    holes = filled & ~m
    if not holes.any():
        return m, 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(holes.astype(np.uint8), connectivity=8)
    out = m.copy()
    released = 0
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < params.ring_hole_area_min:
            continue
        hole_comp = labels == label
        nonarm_frac = 1.0 - float(armlike[hole_comp].mean())
        if nonarm_frac < params.ring_nonarm_frac_min:
            continue
        ring = cv2.dilate(hole_comp.astype(np.uint8), _KERNEL3, iterations=params.ring_dilate).astype(bool) & out
        released += int(ring.sum())
        out &= ~ring
    return out, released


def _detect_tip(
    main: np.ndarray,
    hsv: np.ndarray,
    keepset: np.ndarray,
    border: np.ndarray,
    params: _P,
) -> np.ndarray:
    """黑色指尖识别：main 上的小面积、窄、贴近本帧臂全局最远测地距离的黑色连通块。

    candidate 必须不与 keepset 相交（防止把被夹的暗色物体误当指尖）。stick 任务
    自然无命中：末端灰杆 V 远高于 tip_v_max=100，根本进不了 black 候选。
    """
    zeros = np.zeros(main.shape, bool)
    if not main.any():
        return zeros
    black = main & (hsv[..., 1] <= params.tip_s_max) & (hsv[..., 2] <= params.tip_v_max)
    if not black.any():
        return zeros
    seed_px = border & main
    if not seed_px.any():
        return zeros
    dist = _geodesic_dist(main, seed_px)
    reached = dist >= 0
    if not reached.any():
        return zeros
    gmax = float(dist[reached].max())
    if gmax < params.tip_gmax_min:
        return zeros
    gd_floor = max(gmax - params.tip_geo_margin, params.tip_geo_frac * gmax, params.tip_limb_geo_min)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(black.astype(np.uint8), connectivity=8)
    tip = zeros.copy()
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < params.tip_area_min or area > params.tip_area_max:
            continue
        comp = labels == label
        if (comp & keepset).any():
            continue
        dt = cv2.distanceTransform(comp.astype(np.uint8), cv2.DIST_L2, 3)
        if float(dt.max()) > params.tip_width_max:
            continue
        comp_dist = dist[comp]
        valid = comp_dist >= 0
        if not valid.any():
            continue
        if float(comp_dist[valid].max()) < gd_floor:
            continue
        tip |= comp
    return tip


def compute_masks(
    frames: np.ndarray, phase_flags: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    frames = np.ascontiguousarray(frames)
    n = frames.shape[0]
    phase_flags = np.asarray(phase_flags, dtype=bool)
    base_params = ArmRemovalParams.from_json(_PARAMS_PATH)
    params = _P()

    remove_masks = np.zeros(frames.shape[:3], dtype=bool)
    tip_masks = np.zeros(frames.shape[:3], dtype=bool)
    total_pixels = frames.shape[1] * frames.shape[2]

    removed_fraction: list[float] = []
    segments_stats: list[dict[str, Any]] = []
    absorbed_total = 0
    absorb_reject_total = {"area": 0, "dist": 0, "armratio": 0, "white": 0, "sat": 0, "temporal": 0}
    shadow_total = 0
    stuck_gated_out_total = 0
    ring_released_total = 0
    occluder_rejected_no_transit_total = 0
    occluder_rejected_oversize_total = 0
    tip_pixel_total = 0

    for seg_start, seg_end in segment_bounds(phase_flags):
        seg_frames = frames[seg_start:seg_end]
        n_seg = seg_frames.shape[0]

        # ---------- 第一遍：全段扫描 ----------
        plate, mode_fraction = build_background_plate(seg_frames, base_params)
        foregrounds = np.stack([_foreground(seg_frames[i], plate, base_params) for i in range(n_seg)])
        border = _border_seed(frames.shape[1:3], base_params)
        s_thr, v_min, appearance_pixels = learn_arm_appearance(seg_frames, foregrounds, border, base_params)

        anchored1 = [_anchored_components(foregrounds[i], border) for i in range(n_seg)]
        anchored_col_present = np.stack([a.any(axis=0) for a in anchored1])  # (n_seg, W)
        anchored_union = np.zeros(frames.shape[1:3], bool)
        for a in anchored1:
            anchored_union |= a

        occluder_accepted, occluder_rejected, occluder_info = _detect_occluder_v2(
            plate, mode_fraction, s_thr, v_min, anchored_col_present, base_params, params
        )
        if appearance_pixels < _MIN_APPEARANCE_PIXELS and occluder_accepted.any():
            retry = learn_arm_appearance(seg_frames, foregrounds, border | _dilate(occluder_accepted, 1), base_params)
            if retry[2] > appearance_pixels:
                s_thr, v_min, appearance_pixels = retry
                occluder_accepted, occluder_rejected, occluder_info = _detect_occluder_v2(
                    plate, mode_fraction, s_thr, v_min, anchored_col_present, base_params, params
                )
        occluder_rejected_no_transit_total += occluder_info["rejected_no_transit"]
        occluder_rejected_oversize_total += occluder_info["rejected_oversize"]

        seed_final = border | _dilate(occluder_accepted, 1)

        plate_hsv = cv2.cvtColor(plate, cv2.COLOR_RGB2HSV)
        v_floor = min(v_min, float(base_params.occluder_val_cap))
        plate_achromatic_vok = (plate_hsv[..., 1] <= s_thr) & (plate_hsv[..., 2] >= v_floor)
        plate_armlike = _armlike(plate_hsv, s_thr, 25.0)
        # "板色一致"保护（keep_plate_same）的一个致命陷阱：臂如果在本段内长时间停在
        # 同一姿态，板的众数会直接学成臂自己的颜色，届时"当前帧≈板"在臂的整个静止
        # 轮廓上永远成立，会把臂本体误当"静止物体"整体保出去（实测 StopCube 臂全程
        # 停在 home 附近，removed_fraction 从 v3 基线 3.5% 崩到 0.18%）。真正的物体
        # 与臂的本质区别是"是否连到画面边缘"——臂/底座是唯一会触边的东西，桌上任务
        # 物体从不触边。用板上无彩轮廓与边带种子的连通性把"臂自己的常驻轮廓"摘出来，
        # 从 keep_plate_same 的保护范围里排除；孤立的静止无彩物体（不触边）不受影响。
        plate_arm_body = _anchored_components(plate_achromatic_vok, border)

        hsv_list = [cv2.cvtColor(seg_frames[i], cv2.COLOR_RGB2HSV) for i in range(n_seg)]
        frame_armlike = [_armlike(hsv_list[i], s_thr, 25.0) for i in range(n_seg)]
        f_arm_count = np.zeros(frames.shape[1:3], np.uint16)
        for fa in frame_armlike:
            f_arm_count += fa.astype(np.uint16)
        f_arm = f_arm_count.astype(np.float32) / float(max(n_seg, 1))

        transit_gate = _dilate(anchored_union, params.stuck_union_dilate)
        if n_seg < params.shortseg_frame_threshold:
            lo, hi = params.f_arm_lo_shortseg, params.f_arm_hi_shortseg
        else:
            lo, hi = params.f_arm_lo, params.f_arm_hi
        stuck_zone_loose = plate_achromatic_vok & (mode_fraction < params.stuck_max_mode_fraction)
        f_arm_window = (f_arm >= lo) & (f_arm <= hi)
        stuck_zone = stuck_zone_loose & f_arm_window & transit_gate
        stuck_gated_out_total += int((stuck_zone_loose & ~stuck_zone).sum())

        fg_aug = [foregrounds[i] | (stuck_zone & frame_armlike[i]) for i in range(n_seg)]
        main0 = [
            _anchored_components(fg_aug[i], seed_final) | (occluder_accepted & frame_armlike[i])
            for i in range(n_seg)
        ]

        keepset_static = occluder_rejected  # "板异常静止物体块"：过境证据不足的常驻候选块

        # ---------- 第二遍：逐帧组装 ----------
        for i in range(n_seg):
            frame = seg_frames[i]
            hsv = hsv_list[i]
            prev0 = main0[i - 1] if i > 0 else None
            next0 = main0[i + 1] if i < n_seg - 1 else None

            main1, absorbed_i, reject_i = _absorb_fragments_v2(
                main0[i], fg_aug[i], hsv, s_thr, v_min, prev0, next0, params
            )
            absorbed_total += absorbed_i
            for k, v in reject_i.items():
                absorb_reject_total[k] += v

            shadow = _shadow_mask(frame, plate, fg_aug[i], main1, base_params)
            shadow_total += int(shadow.sum())
            m = main1 | shadow

            diff_plate = np.abs(frame.astype(np.int16) - plate.astype(np.int16)).max(axis=-1)
            keep_sat = hsv[..., 1] >= params.protect_sat_min
            keep_white = (hsv[..., 1] <= params.white_veto_s) & (hsv[..., 2] >= params.white_veto_v)
            keep_plate_same = (diff_plate <= params.plate_same_thresh) & ~plate_arm_body
            # keepset_static（条件 4）是段级、按像素坐标划死的一块区域，语义是"过境
            # 证据不足、姑且当静止物体保护"。若不加限定，臂真的短暂经过这片坐标时
            # （前景证据确凿）也会被这块静止保护网连坐误伤——实测 StopCube 臂在
            # 前 12 帧刚好停在被拒判的常驻区坐标上，main（859px）100% 落进
            # keepset_static，guarded dilation 直接清零。用"本帧是否是前景"做门控：
            # 前景本身就是"这里此刻确实和板不一样"的帧级证据，应当压过段级的"缺过境
            # 证据"默认判断；只在本帧无前景异动（真正静止的时刻）才生效保护。
            keepset_static_frame = keepset_static & ~fg_aug[i]
            keepset = keep_sat | keep_white | keep_plate_same | keepset_static_frame

            tip_i = _detect_tip(main1, hsv, keepset, border, params)
            tip_pixel_total += int(tip_i.sum())

            m_no_tip = m & ~tip_i
            grown = (
                _dilate(m_no_tip, params.arm_dilate)
                & (fg_aug[i] | plate_armlike)
                & ~_dilate(keepset, params.keep_guard_dilate)
            )
            grown, ring_px = _release_rings(grown, frame_armlike[i], params)
            ring_released_total += ring_px

            final = grown & ~keepset & ~tip_i

            gidx = seg_start + i
            remove_masks[gidx] = final
            tip_masks[gidx] = tip_i
            removed_fraction.append(float(final.sum()) / total_pixels)

        segments_stats.append(
            {
                "start": int(seg_start),
                "end": int(seg_end),
                "phase_is_video_demo": bool(phase_flags[seg_start]),
                "frame_count": int(n_seg),
                "f_arm_window": [lo, hi],
                "arm_sat_threshold": float(s_thr),
                "arm_value_min": float(v_min),
                "appearance_sample_pixels": int(appearance_pixels),
                "static_occluder": occluder_info,
            }
        )

    stats: dict[str, Any] = {
        "frame_count": int(n),
        "segment_count": len(segments_stats),
        "segments": segments_stats,
        "removed_fraction_mean": float(np.mean(removed_fraction)) if removed_fraction else 0.0,
        "removed_fraction_max": float(np.max(removed_fraction)) if removed_fraction else 0.0,
        "absorbed_fragment_count": int(absorbed_total),
        "absorb_rejected": absorb_reject_total,
        "shadow_pixel_total": int(shadow_total),
        "stuck_gated_out_pixels": int(stuck_gated_out_total),
        "occluder_rejected_no_transit_blocks": int(occluder_rejected_no_transit_total),
        "occluder_rejected_oversize_blocks": int(occluder_rejected_oversize_total),
        "ring_released_pixels": int(ring_released_total),
        "tip_pixel_total": int(tip_pixel_total),
    }
    return remove_masks, tip_masks, stats
