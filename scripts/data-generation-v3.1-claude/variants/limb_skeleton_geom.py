#!/usr/bin/env python3
"""候选变体 limb_skeleton_geom：肢体几何——宽度单调测地生长，形状自证物体保护。

## 核心思路

其余候选变体大多靠颜色/时间一致性（背景板差分、饱和度、时序稳定性）逐像素
自证「这是臂还是物体」；本变体换一个正交的判据——**形状**。Franka 机械臂在
图上从基座到指尖天然逐段变细，而桌面上被夹/被推/被拖的任务物体（方块、按钮
座、缆线接触段）在接触点附近通常比该处的肢体宽。于是本变体不做「整块连通域
判定是不是臂」的粗粒度决策（cv_base 的 `_anchored_components` 语义），而是从
边界/底座种子出发，按测地层序逐层向外生长，**每一步都验证候选像素的局部宽度
不超过沿路径继承下来的宽度上限**——上限本身随生长向外单调不增（用 3×3 膨胀做
最大值传播、逐层取 min 收紧的棘轮）。物体在几何上「生长根本进不去」，而不是
「进去了再事后减法删掉」，因此不需要靠事后膨胀/腐蚀去描边，也就不会在物体
边缘留下 v3 那种贴边细红环。

## 物体保护的五层防线（对应 assigned spec 的 object_protection 1–5）

1. **宽度单调生长**（`_width_monotone_grow`，主防线）：像素 p 只有在
   `dt[p] <= wcap[q]`（q 为上一层已接受像素，wcap 沿路径取 min）时才被吸收。
2. **侧枝/丝状附着释放**（`_branch_release`）：肢体最后一次「够粗」的测地层
   之后长出的细长（中位 dt 小）、够长、相对入射方向转折剧烈的分支，判定为
   悬挂附着物（RouteStick 白缆线的几何签名：从 stick 末端垂下再回卷）释放出去。
3. **纯白调色板否决**（`white_veto`，S<=20 & V>=230）：臂的无彩高光尾巴到不了
   V=230，白按钮/白垫圈/白缆线是硬平台，命中即挡在 keepset 外，不看饱和度也能
   拦住这一类无彩接触物。
4. **背景板一致性否决**（`plate_consistent`，|frame-plate|<=6，且排除底座常驻
   占用区）：像素若与背景板几乎没差别，说明它没在动——静止装置/静止按钮的
   第二道保险；底座常驻区排除在外，否则常驻区会被这条顺手保护住，削弱清底座
   的软目标。
5. **高饱和否决**（`sat_veto`，S>=60，无面积门槛）：被夹的彩色物体直接挡驾。

以上四条 veto 的并集是 `keepset`；肢体生长完成后 `limb &= ~keepset` 一次性挖除，
guard growth（收尾的单次守卫生长）同样把 `keepset` 作为拒绝条件之一，因此
「挖出来的洞」不会被收尾膨胀重新吞回去。**全程不做无条件膨胀**——唯一的膨胀
是这一次三条件都要满足的 guard growth（plate-novel 且臂调色板 且非 keepset），
所以贴边细红环无从产生（v3 的环来自「先膨胀、再拿高饱和保护抠一部分回来」，
抠不干净的部分才留下环；本变体从不整体膨胀，自然没有环要抠）。

## 指尖保留（`_detect_tip`）

指尖 = 落在肢体末端 15% 测地区间内、局部窄（dt<=3.5）、面积 4..90 的无彩暗块
（S<=40、V<=100）；`gd[limb].max()` 太小（肢体没伸展）时整帧不认指尖，避免
把腕部/底座误判成指尖。stick 机器人自然 no-op：末端是灰杆（V≈143/144），
15% 测地尾区里没有暗块，天然不会产生 tip；腕部黑色支架落在测地近端（不在
尾 15% 区间内）且 dt 明显大于 3.5、面积明显大于 90，双重挡驾。

## 逃生舱（`_safe_blob_absorb`，保 SOFT 目标）

宽度单调假设在「腕→夹爪投影陡然变宽」处会失效——生长会在那个宽度跳变处
卡死，把整只手甩在肢体外。对 ROI 里被拒绝的连通块做纯度体检：臂调色板占比
高、纯白/高饱和占比低、且与已有肢体 8 连通，整块并入（不做逐像素宽度判定）。

依赖纪律：只 import numpy / cv2 / 标准库 / 同目录 `cv_base`；不 import
h5py/scipy/torch；源码不出现仿真分割相关标识符。
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# 注意：本文件刻意不用 `from __future__ import annotations`。渲染器
# render_variant_outputs.py 的 load_variant() 用 module_from_spec+exec_module
# 手动加载变体模块，没有像标准 import 机制那样把模块对象注册进 sys.modules；
# 若开启延迟求值，下面 GeomParams 的字段类型注解在 dataclass 装饰器眼里全是
# 字符串，Python 3.11 dataclass 实现判断 KW_ONLY 哨兵时会反查
# sys.modules[cls.__module__].__dict__，查不到就直接 AttributeError 崩溃
# （3.9+ 原生支持 list[str]/dict[str, Any] 这类内建泛型写法，不开延迟求值
# 也完全够用，故直接不开）。

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cv_base import (  # noqa: E402
    ArmRemovalParams,
    _MIN_APPEARANCE_PIXELS,
    _anchored_components,
    _border_seed,
    _dilate,
    _foreground,
    _shadow_mask,
    build_background_plate,
    detect_static_occluder,
    learn_arm_appearance,
    segment_bounds,
)

NAME = "limb_skeleton_geom"
DESCRIPTION = "肢体几何：从边界种子做宽度单调测地生长，越出肢体几何的一律判为物体"

_CV_PARAMS_PATH = Path(__file__).resolve().parents[1] / "cv_base_params.json"
_K3 = np.ones((3, 3), np.uint8)


@dataclass(frozen=True)
class GeomParams:
    """本变体新增的几何参数（与 cv_base 的 ArmRemovalParams 分开管理，字段名
    不重叠，避免 `ArmRemovalParams.from_dict` 的未知键校验报错）。默认值取自
    方案设计者给出的 assigned spec。"""

    grow_width_slack_mul: float = 1.35
    grow_width_slack_add: float = 1.0
    grow_width_floor: float = 3.0
    dt_thick_layer: float = 4.0
    branch_dt_median_max: float = 1.6
    branch_len_min: float = 8.0
    branch_turn_deg_min: float = 60.0
    branch_white_frac_min: float = 0.05
    safe_blob_arm_frac: float = 0.85
    safe_blob_white_frac_max: float = 0.01
    safe_blob_sat_frac_max: float = 0.01
    guard_grow_iter: int = 1
    plate_same_thresh: int = 6
    sat_veto_min: int = 60
    white_veto_s: int = 20
    white_veto_v: int = 230
    geodesic_max_iter: int = 400
    tip_s_max: int = 40
    tip_v_max: int = 100
    tip_area_min: int = 4
    tip_area_max: int = 90
    tip_dt_max: float = 3.5
    tip_geo_tail_frac: float = 0.15
    tip_limb_geo_min: int = 18


def _load_cv_params() -> ArmRemovalParams:
    """复用 cv_base 的背景板/前景/锚定/外观模型/底座检测/阴影默认参数；本
    变体不做收尾无条件膨胀（守卫生长已承担"补边"职责），显式把 arm_dilate 清零。"""
    base = ArmRemovalParams.from_json(_CV_PARAMS_PATH)
    return ArmRemovalParams.from_dict({**base.to_dict(), "arm_dilate": 0})


def _geodesic(mask: np.ndarray, seed: np.ndarray, max_iter: int) -> np.ndarray:
    """cv2.dilate 迭代 BFS 测地层数图：seed∩mask 记第 0 层，逐层 3×3 膨胀外扩；
    mask 外或未连通到 seed 的像素记 -1（不可达）。全数组运算，无逐像素 Python 循环。"""
    reach = seed & mask
    gd = np.full(mask.shape, -1, dtype=np.int32)
    gd[reach] = 0
    frontier = reach
    for layer in range(1, max_iter + 1):
        nxt = cv2.dilate(frontier.astype(np.uint8), _K3).astype(bool) & mask & (gd < 0)
        if not nxt.any():
            break
        gd[nxt] = layer
        frontier = nxt
    return gd


def _width_monotone_grow(
    roi: np.ndarray, seed: np.ndarray, dt: np.ndarray, gp: GeomParams
) -> np.ndarray:
    """按测地层序推进的宽度单调生长。

    wcap（宽度上限图）在种子处用种子自身的局部宽度初始化，此后每层用 3×3
    膨胀做「最大值传播」得到 wq（邻居能提供的最大上限），候选像素只有在
    `dt <= wq` 时才被接受，接受后把它自己的 wcap 收紧为
    `min(wq, max(dt*slack_mul+slack_add, floor))`——这是一个棘轮：宽度上限
    沿生长路径只能不增不减或收紧，绝不会因为局部宽度突然变大而放宽，物体在
    接触点因为比肢体末段宽而被直接卡死，一个像素都进不来。
    """
    roi = roi.astype(bool)
    seed = seed & roi
    own_cap = np.maximum(
        dt * gp.grow_width_slack_mul + gp.grow_width_slack_add, gp.grow_width_floor
    ).astype(np.float32)
    wcap = np.zeros(roi.shape, dtype=np.float32)  # 未访问处为 0（dilate 最大值传播时不会外溢）
    wcap[seed] = own_cap[seed]
    visited = seed.copy()
    frontier = seed.copy()
    for _ in range(gp.geodesic_max_iter):
        if not frontier.any():
            break
        wq = cv2.dilate(wcap, _K3)
        cand = cv2.dilate(frontier.astype(np.uint8), _K3).astype(bool) & roi & ~visited
        if not cand.any():
            break
        accept = cand & (dt <= wq)
        if not accept.any():
            break
        wcap[accept] = np.minimum(wq[accept], own_cap[accept])
        visited |= accept
        frontier = accept
    return visited


def _safe_blob_absorb(
    limb: np.ndarray,
    roi: np.ndarray,
    armlike: np.ndarray,
    white_veto: np.ndarray,
    sat_veto: np.ndarray,
    gp: GeomParams,
) -> np.ndarray:
    """逃生舱：宽度单调生长在腕→夹爪投影变宽处会卡死，把整只手甩在 limb 外。
    对生长拒绝的连通块做纯度体检——臂调色板占比高、纯白/高饱和占比低、且与
    已有 limb 8 连通——整块并入，不逐像素判宽度。多轮循环：吸附一块后，
    下一块可能因此新获得邻接资格。"""
    out = limb.copy()
    for _ in range(4):
        rejected = roi & ~out
        if not rejected.any():
            break
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            rejected.astype(np.uint8), connectivity=8
        )
        if count <= 1:
            break
        dil_limb = cv2.dilate(out.astype(np.uint8), _K3).astype(bool)
        absorbed_any = False
        for label in range(1, count):
            comp = labels == label
            if not (comp & dil_limb).any():
                continue
            arm_frac = float(armlike[comp].mean())
            white_frac = float(white_veto[comp].mean())
            sat_frac = float(sat_veto[comp].mean())
            if (
                arm_frac >= gp.safe_blob_arm_frac
                and white_frac <= gp.safe_blob_white_frac_max
                and sat_frac <= gp.safe_blob_sat_frac_max
            ):
                out |= comp
                absorbed_any = True
        if not absorbed_any:
            break
    return out


def _branch_turn_angle(comp_mask: np.ndarray, parent_centroid: np.ndarray) -> float:
    """分支自身 PCA 主轴与「分支质心指向父层质心」方向的夹角（0..90°，PCA
    主轴无方向性，取锐角）。0° = 分支沿着离开父层的方向直着延伸（自然的手指
    延伸，不该被释放）；越接近 90° 说明分支的走向与「离开父体」的方向偏离
    越大（侧向/回卷的悬挂附着物）。"""
    ys, xs = np.nonzero(comp_mask)
    if xs.size < 2:
        return 0.0
    comp_centroid = np.array([xs.mean(), ys.mean()])
    to_parent = parent_centroid - comp_centroid
    norm = float(np.linalg.norm(to_parent))
    if norm < 1e-6:
        return 0.0
    to_parent = to_parent / norm
    pts = np.stack([xs, ys], axis=1).astype(np.float64) - comp_centroid
    _, _, vt = np.linalg.svd(pts, full_matrices=False)
    axis = vt[0]
    axis_norm = float(np.linalg.norm(axis))
    if axis_norm < 1e-9:
        return 0.0
    axis = axis / axis_norm
    cos = min(1.0, abs(float(np.dot(axis, to_parent))))
    return float(np.degrees(np.arccos(cos)))


def _branch_release(
    limb: np.ndarray,
    gd: np.ndarray,
    dt: np.ndarray,
    white_veto: np.ndarray,
    keepset: np.ndarray,
    gp: GeomParams,
) -> np.ndarray:
    """侧枝/丝状附着释放：肢体最后一次「够粗」（dt>dt_thick_layer）之后的测地
    层里长出的连通块，若中位 dt 细、够长、相对父层的转折角够大，判定为悬挂
    附着物（RouteStick 白缆线的几何签名）并释放出去（从 limb 里减掉，即
    「不当作机器人删除」）。反向保险：候选分支若纯白占比很低、又不挨着已有
    keepset（白/高饱和否决区），判定它其实是 stick 本体的延伸而非悬挂附着物，
    不放行——避免细长的 stick 工具本体被误判成"分支"而被保留下来。"""
    thick_gd = gd[limb & (dt > gp.dt_thick_layer)]
    last_thick_layer = int(thick_gd.max()) if thick_gd.size else 0
    distal = limb & (gd > last_thick_layer)
    release = np.zeros_like(limb)
    if not distal.any():
        return release

    parent_zone = limb & (gd == last_thick_layer)
    if not parent_zone.any():
        parent_zone = limb & (gd >= max(last_thick_layer - 2, 0)) & (gd <= last_thick_layer)
    if not parent_zone.any():
        return release
    pys, pxs = np.nonzero(parent_zone)
    parent_centroid = np.array([pxs.mean(), pys.mean()])

    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        distal.astype(np.uint8), connectivity=8
    )
    for label in range(1, count):
        comp = labels == label
        comp_dt = dt[comp]
        comp_gd = gd[comp]
        median_dt = float(np.median(comp_dt))
        if median_dt > gp.branch_dt_median_max:
            continue
        length = float(comp_gd.max() - comp_gd.min())
        if length < gp.branch_len_min:
            continue
        turn = _branch_turn_angle(comp, parent_centroid)
        if turn < gp.branch_turn_deg_min:
            continue
        white_frac = float(white_veto[comp].mean())
        touches_keep = bool((comp & keepset).any())
        if white_frac < gp.branch_white_frac_min and not touches_keep:
            continue
        release |= comp
    return release


def _guard_grow(
    limb: np.ndarray,
    plate_novel: np.ndarray,
    armlike: np.ndarray,
    keepset: np.ndarray,
    iterations: int,
) -> np.ndarray:
    """收尾守卫生长：不是无条件膨胀，每轮新纳入的像素必须同时满足「与背景板
    有别（plate-novel）」「落在臂调色板」「不在 keepset」三条，只用来补齐
    宽度单调生长漏掉的 1px 混色边缘，不会往物体方向扩张（物体接触点要么落在
    keepset 里，要么本身色彩不落在臂调色板内，两条件之一就把它挡在外面）。"""
    out = limb.copy()
    for _ in range(max(iterations, 0)):
        cand = cv2.dilate(out.astype(np.uint8), _K3).astype(bool) & ~out
        accept = cand & plate_novel & armlike & ~keepset
        if not accept.any():
            break
        out |= accept
    return out


def _detect_tip(
    limb: np.ndarray, gd: np.ndarray, dt: np.ndarray, hsv: np.ndarray, gp: GeomParams
) -> np.ndarray:
    """指尖 = 肢体末端 15% 测地区间内、局部窄（dt<=tip_dt_max）、面积落在
    [tip_area_min, tip_area_max] 的无彩暗块（S<=tip_s_max、V<=tip_v_max）。
    肢体测地跨度太小（gmax<tip_limb_geo_min，意味着没怎么伸展进画面）时整帧
    不认指尖，避免把腕部/底座这类近端黑色结构误判成指尖。

    宽度/面积按**整块暗色连通域**判定，而不是先按测地尾区把候选裁一刀再判——
    腕部支架实测是一整块面积 108、dt 最大 6.97 的暗色连通域，但它的测地跨度
    很宽（从近端一直延伸到尾区边缘），只看「已经被尾区裁过的那一小片」会发现
    那一小片恰好又窄又小（腕部支架末梢的尖角），逐像素误判成指尖。改成先在
    `dark & limb` 上求整块连通域，只用「是否有一部分伸进尾区」作准入门槛，
    宽度/面积门槛在**整块**上判——腕部支架整体面积、整体最大 dt 都远超阈值，
    照样被挡在外面；真正的指尖本来就是孤立小块，整块判定和裁尾区判定结果一致。
    """
    if not limb.any():
        return np.zeros_like(limb)
    gmax = int(gd[limb].max())
    if gmax < gp.tip_limb_geo_min:
        return np.zeros_like(limb)
    tail_start = gmax - gmax * gp.tip_geo_tail_frac
    tail_zone = limb & (gd >= tail_start)
    dark = (hsv[..., 1] <= gp.tip_s_max) & (hsv[..., 2] <= gp.tip_v_max) & limb
    if not dark.any():
        return np.zeros_like(limb)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        dark.astype(np.uint8), connectivity=8
    )
    tip = np.zeros_like(limb)
    for label in range(1, count):
        comp = labels == label
        if not (comp & tail_zone).any():
            continue  # 整块暗色结构完全没伸进测地尾区，不是指尖候选
        area = int(stats[label, cv2.CC_STAT_AREA])
        if not (gp.tip_area_min <= area <= gp.tip_area_max):
            continue
        if float(dt[comp].max()) > gp.tip_dt_max:
            continue
        tip |= comp
    return tip


def compute_masks(
    frames: np.ndarray, phase_flags: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    cvp = _load_cv_params()
    gp = GeomParams()
    frames = np.ascontiguousarray(frames)
    if frames.ndim != 4 or frames.shape[-1] != 3 or frames.dtype != np.uint8:
        raise ValueError(f"frames 必须是 (N,H,W,3) uint8，拿到 {frames.shape} {frames.dtype}")
    n = frames.shape[0]
    phase_flags = np.asarray(phase_flags, dtype=bool)
    if phase_flags.shape != (n,):
        raise ValueError(f"phase_flags 形状 {phase_flags.shape} 与帧数 {n} 不符")

    remove_masks = np.zeros(frames.shape[:3], dtype=bool)
    tip_masks = np.zeros(frames.shape[:3], dtype=bool)

    segments_stats: list[dict[str, Any]] = []
    branch_released_total = 0
    safe_blob_absorbed_total = 0
    unreachable_total = 0
    shadow_total = 0

    for seg_start, seg_end in segment_bounds(phase_flags):
        seg_frames = frames[seg_start:seg_end]
        plate, mode_fraction = build_background_plate(seg_frames, cvp)
        foregrounds = np.stack(
            [_foreground(seg_frames[i], plate, cvp) for i in range(seg_frames.shape[0])]
        )
        border = _border_seed(frames.shape[1:3], cvp)
        s_thr, v_min, appearance_pixels = learn_arm_appearance(seg_frames, foregrounds, border, cvp)
        occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, cvp)
        # 二轮学习：臂根常驻画面顶部时纯边带锚定采不到核心样本，用检出的常驻区
        # 增强种子重学一遍（逻辑与 cv_base.compute_arm_masks 一致）。
        if appearance_pixels < _MIN_APPEARANCE_PIXELS and occluder.any():
            retry = learn_arm_appearance(seg_frames, foregrounds, border | _dilate(occluder, 1), cvp)
            if retry[2] > appearance_pixels:
                s_thr, v_min, appearance_pixels = retry
                occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, cvp)
        seed = border | _dilate(occluder, 1)

        # 条件常驻区（stuck zone）：背景板本身就呈臂色的污染区，只有当前帧仍是
        # 臂色时才并入前景候选——逻辑抄自 cv_base.compute_arm_masks，修臂根
        # 黑洞（臂回到常驻位姿时与板同色，背景差分天然失明）。
        plate_hsv = cv2.cvtColor(plate, cv2.COLOR_RGB2HSV)
        v_floor = min(v_min, float(cvp.occluder_val_cap))
        stuck_zone = (
            (plate_hsv[..., 1] <= s_thr)
            & (plate_hsv[..., 2] >= v_floor)
            & (mode_fraction < cvp.stuck_max_mode_fraction)
            if cvp.stuck_fill
            else np.zeros(plate.shape[:2], bool)
        )

        seg_branch = 0
        seg_absorb = 0
        seg_unreach = 0
        seg_shadow = 0

        for offset in range(seg_frames.shape[0]):
            idx = seg_start + offset
            frame = seg_frames[offset]
            hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
            fg = foregrounds[offset]
            if cvp.stuck_fill and stuck_zone.any():
                frame_armlike = (hsv[..., 1] <= max(2.0 * s_thr, 25.0)) & (hsv[..., 2] >= 25)
                fg = fg | (stuck_zone & frame_armlike)

            anchored = _anchored_components(fg, seed)
            roi = anchored | occluder
            if not roi.any():
                continue  # 整帧无锚定域（臂不在画面内），remove/tip 保持全 False

            dt = cv2.distanceTransform(roi.astype(np.uint8), cv2.DIST_L2, 3)
            gd = _geodesic(roi, seed, gp.geodesic_max_iter)
            seg_unreach += int(((gd < 0) & roi).sum())

            white_veto = (hsv[..., 1] <= gp.white_veto_s) & (hsv[..., 2] >= gp.white_veto_v)
            sat_veto = hsv[..., 1] >= gp.sat_veto_min
            plate_diff = np.abs(frame.astype(np.int16) - plate.astype(np.int16)).max(axis=-1)
            plate_consistent = plate_diff <= gp.plate_same_thresh
            # 底座常驻区排除在板一致性否决之外：常驻区本来就"永远等于背景板"，
            # 不排除会让底座整块被这条否决保护住，削弱清底座的软目标。
            keepset = white_veto | sat_veto | (plate_consistent & ~occluder)
            armlike_generous = (hsv[..., 1] <= max(2.0 * s_thr, 25.0)) & (hsv[..., 2] >= 20)

            limb = _width_monotone_grow(roi, seed, dt, gp)

            before_absorb = int(limb.sum())
            limb = _safe_blob_absorb(limb, roi, armlike_generous, white_veto, sat_veto, gp)
            seg_absorb += int(limb.sum()) - before_absorb

            branch = _branch_release(limb, gd, dt, white_veto, keepset, gp)
            seg_branch += int(branch.sum())
            limb = limb & ~branch

            limb = limb & ~keepset

            plate_novel = ~plate_consistent
            limb = _guard_grow(limb, plate_novel, armlike_generous, keepset, gp.guard_grow_iter)

            shadow = _shadow_mask(frame, plate, fg, limb, cvp)
            seg_shadow += int(shadow.sum())

            tip = _detect_tip(limb, gd, dt, hsv, gp)

            combined = limb | shadow
            remove = combined & ~tip
            # HARD A 最后一道防线：任何高饱和像素绝不进入 remove（keepset/guard
            # growth 里已经挡过一次，这里再冗余判一次，防止阴影计算引入例外）
            remove = remove & ~sat_veto

            remove_masks[idx] = remove
            tip_masks[idx] = tip

        branch_released_total += seg_branch
        safe_blob_absorbed_total += seg_absorb
        unreachable_total += seg_unreach
        shadow_total += seg_shadow

        segments_stats.append(
            {
                "start": int(seg_start),
                "end": int(seg_end),
                "phase_is_video_demo": bool(phase_flags[seg_start]),
                "arm_sat_threshold": float(s_thr),
                "arm_value_min": float(v_min),
                "appearance_sample_pixels": int(appearance_pixels),
                "static_occluder": occluder_info,
                "branch_released_pixels": int(seg_branch),
                "safe_blob_absorbed_pixels": int(seg_absorb),
                "roi_unreachable_pixels": int(seg_unreach),
                "shadow_pixels": int(seg_shadow),
            }
        )

    per_frame_fraction = remove_masks.reshape(n, -1).mean(axis=1) if n else np.zeros(0)
    stats: dict[str, Any] = {
        "frame_count": int(n),
        "segment_count": len(segments_stats),
        "segments": segments_stats,
        "removed_fraction_mean": float(per_frame_fraction.mean()) if n else 0.0,
        "removed_fraction_max": float(per_frame_fraction.max()) if n else 0.0,
        "branch_released_pixel_total": int(branch_released_total),
        "safe_blob_absorbed_pixel_total": int(safe_blob_absorbed_total),
        "roi_unreachable_pixel_total": int(unreachable_total),
        "shadow_pixel_total": int(shadow_total),
    }
    return remove_masks, tip_masks, stats
