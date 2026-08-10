#!/usr/bin/env python3
"""变体 arm_proof_gate：逐像素臂证据门控——锚定连通域只当搜索范围，不当删除决定。

## 核心思路

v3 的删除决定几乎完全交给"锚定连通域"（触边前景块整块删）+ 收尾无条件膨胀，
这是 v3.1 五个已知失败（PatternLock 白按钮、RouteStick 白缆线、StopCube 黑装置
误删、被移动物体的红边环、被夹彩色方块的边缘环）的共同根源：连通域本身不区分
"这块像素是臂"还是"这块像素是贴着臂的物体"。

本变体把锚定连通域降级为 **ROI**（搜索范围，只圈定"可能是臂的地方"），真正的
删除决定改为逐像素证据门控：

    删除 = ROI ∧ (前景新颖性 ∨ 静态占据豁免) ∧ 臂调色板证据 ∧ ¬任一否决

四条否决（背景板一致 / 纯白调色板 / 高饱和 / 静态物体登记）任一命中即保留，
均不设最小面积门槛——"删除多留一点机器人残留可以接受，删除物体不可接受"。
收尾环节的无条件膨胀（v3 的 arm_dilate=2，实测是最大的物体误删来源）替换成
一次"必须同时满足前景+臂调色板+无否决"的带守卫生长。

黑色指尖靠共用几何规则（无彩暗块 + 测地距离落在肢体远端 + 面积/宽度上限）从
ROI 里单独挑出来保留，两个 panda_stick 任务（PatternLock / RouteStick）没有
黑色指尖，规则天然对它们空判（面积/宽度双超限），无需任何按任务名分支。

依赖纪律与 variants/__init__.py 契约一致：只 import numpy / cv2 / 标准库 /
本目录 cv_base（含下划线开头的原语）。不直接调用 cv_base.compute_arm_masks，
本模块自己重写主循环。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cv_base import (  # noqa: E402
    _MIN_APPEARANCE_PIXELS,
    ArmRemovalParams,
    _anchored_components,
    _border_seed,
    _dilate,
    _erode,
    _fill_holes,
    _foreground,
    _shadow_mask,
    build_background_plate,
    detect_static_occluder,
    learn_arm_appearance,
    segment_bounds,
)

NAME = "arm_proof_gate"
DESCRIPTION = (
    "逐像素臂证据门控：锚定连通域降级为搜索范围（ROI），删除需同时满足前景新颖性/"
    "静态占据豁免与臂调色板正证据、且不命中背景板一致/纯白/高饱和/静态物体登记四条"
    "否决之一；无条件膨胀替换为带守卫生长；黑指尖用测地距离+厚度+面积几何规则保留"
)


# 本变体独有的数值旋钮，与 cv_base.ArmRemovalParams 分开管理（后者只装复用的
# 原语所需参数）。默认值取自方案设计者在 16 任务实测上调好的取值。
#
# 用 SimpleNamespace 而不是 @dataclass：render_variant_outputs.py 的
# load_variant() 用 importlib.util.module_from_spec + exec_module 动态加载本
# 文件，但没有像 tests/lightweight 的加载器那样先把模块注册进
# sys.modules——@dataclass 装饰器处理类型注解时会经 cls.__module__ 回查
# sys.modules 取模块命名空间，查不到就在导入期直接炸（AttributeError:
# 'NoneType' object has no attribute '__dict__'）。SimpleNamespace 不触发这条
# 装饰器逻辑，绕开这个渲染器加载器的已知限制。
GATE = types.SimpleNamespace(
    # --- 证据 ---
    diff_keep=6,  # 背景板一致否决阈值（<=6 永不删）
    guard_grow_iter=1,  # 带守卫生长的膨胀迭代数（替代 v3 的 arm_dilate=2）
    s_arm_hi_base=26.0,  # 臂饱和度上限下限值：max(2*s_thr, s_arm_hi_base)
    v_arm_lo_floor=25.0,
    v_arm_hi_pct=99.9,
    v_arm_hi_cap=229.0,
    occ_relax_novel=True,  # 常驻区（occ）内不要求前景新颖性，仍受四条否决约束
    # --- 否决 ---
    white_veto_s=20.0,
    white_veto_v=230.0,
    sat_veto_min=60.0,
    plate_white_v=200.0,  # 学 V 支撑时排除"贴着板上白物体"的判据
    registry_dilate=2,
    plate_anom_thresh=60.0,  # 实测校准值，见 _registry_veto 里的说明（方案初始值 14 会被木纹淹没）
    median_blur_ksize=31,
    # --- 黑指尖几何规则 ---
    tip_s_max=40.0,
    tip_v_max=100.0,
    tip_area_min=4,
    tip_area_max=90,
    tip_width_max=5.5,
    tip_geo_slack=12.0,
    tip_geo_frac=0.75,
    tip_geo_abs_min=15.0,
    tip_limb_geo_min=18.0,
)

# cv_base 原语所需的参数对象：无条件膨胀、碎片吸附、饱和保护三条机制在本变体里
# 整条不调用（stuck_fill / absorb_fragments 干脆不 import 对应函数，
# protect_saturated 的职能被否决 C 接管），这里显式关闭只是保持字段语义诚实。
CV_PARAMS = ArmRemovalParams(
    diff_threshold=8,
    close_iter=1,
    border_sides="top,left,right",
    border_band=3,
    occluder_sat_k=3.0,
    occluder_sat_cap=20.0,
    occluder_val_pct=2.0,
    static_occluder_mode="learned",
    occluder_top_rows=32,
    occluder_max_width=128,
    occluder_val_cap=160.0,
    occluder_area_min=60,
    occluder_area_max=6000,
    occluder_dilate=2,
    stuck_fill=False,
    shadow_mode="adjacent",
    shadow_ratio_lo=0.55,
    shadow_ratio_hi=0.97,
    shadow_chroma_tol=0.06,
    shadow_dilate=6,
    protect_saturated=False,
    arm_dilate=0,
)


def _registry_veto(plate: np.ndarray) -> np.ndarray:
    """否决 D：静态物体登记——背景板与其局部中值模糊版本的逐通道最大差 > 阈值处
    （物体边缘/轮廓），膨胀 registry_dilate px。只用背景板算一次，逐帧复用。

    实测校准（16 任务实测，非方案初始值）：桌面木纹本身在 medianBlur(ksize=31)
    下产生大量细纹理异常——MoveCube 单帧阈值 14 命中全图 48%、阈值 40 仍有 4.9%，
    全是散布的木纹细纹路而非物体轮廓（目视核对：真正的机器人底座/物体轮廓在阈值
    ≥60 时仍是完整实心块，木纹纹路则在阈值 60 + 开运算后基本消失，仅剩 ~1.1%
    像素、且都落在底座与两个物体的轮廓上）。因此把 plate_anom_thresh 从方案初始
    值 14 上调到 60（只保留强对比度的真实轮廓），并加一次 3×3 开运算去掉残余的
    细木纹纹路碎屑——两者都只是同一条否决 D 机制内的噪声抑制校准，机制本身
    （背景板局部中值异常→静止物体轮廓登记→膨胀）未变。
    """
    blurred = cv2.medianBlur(plate, GATE.median_blur_ksize)
    anomaly = np.abs(plate.astype(np.int16) - blurred.astype(np.int16)).max(axis=-1) > GATE.plate_anom_thresh
    anomaly = cv2.morphologyEx(
        anomaly.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1
    ).astype(bool)
    return _dilate(anomaly, GATE.registry_dilate)


def _learn_v_support(
    seg_frames: np.ndarray,
    foregrounds: np.ndarray,
    hsv_frames: list[np.ndarray],
    seed: np.ndarray,
    plate_hsv: np.ndarray,
) -> tuple[float, float]:
    """学臂调色板的 V 支撑区间 [v_arm_lo, v_arm_hi]。

    取样域：锚定连通域腐蚀 2 次（核心，排除边缘混色）∩ 远离板上白物体 5px
    （排除"臂压在白按钮上"这类样本污染）。跨整段累积 HSV 的 V 直方图后取
    p99.9 得 v_arm_hi（硬上限 229，与任务白物体的硬 231 平台留 1 档缓冲）。
    """
    plate_white = (plate_hsv[..., 1] <= GATE.white_veto_s) & (plate_hsv[..., 2] >= GATE.plate_white_v)
    far_from_white = ~_dilate(plate_white, 5)

    v_samples: list[np.ndarray] = []
    for index in range(seg_frames.shape[0]):
        core = _erode(_anchored_components(foregrounds[index], seed), 2) & far_from_white
        if core.any():
            v_samples.append(hsv_frames[index][..., 2][core])
    if not v_samples:
        # 退化：没有可信核心样本（例如整段都学不到臂），退到保守宽区间——
        # 不会误伤，因为后面四条否决仍然把关
        return float(GATE.v_arm_lo_floor), float(GATE.v_arm_hi_cap)
    v_all = np.concatenate(v_samples).astype(np.float64)
    v_arm_hi = min(float(np.percentile(v_all, GATE.v_arm_hi_pct)), GATE.v_arm_hi_cap)
    v_arm_lo = max(float(np.percentile(v_all, 0.1)), GATE.v_arm_lo_floor)
    return v_arm_lo, v_arm_hi


def _connectivity_close(proof: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """连通性收口：只留与 seed 8 连通的 proof 块，外加"面积>=25 且落在
    已保留块膨胀 3px 内"的块（找回被黑色关节等切断、但紧贴主体的臂段）。"""
    if not proof.any():
        return proof
    count, labels, stats, _ = cv2.connectedComponentsWithStats(proof.astype(np.uint8), connectivity=8)
    if count <= 1:
        return np.zeros_like(proof)
    touched = np.unique(labels[seed & proof])
    touched = touched[touched != 0]
    keep = set(int(v) for v in touched.tolist())
    anchored = np.isin(labels, touched) if touched.size else np.zeros_like(proof)
    if anchored.any():
        near = _dilate(anchored, 3)
        near_labels = np.unique(labels[near & (labels > 0)])
        for label in near_labels.tolist():
            label = int(label)
            if label in keep:
                continue
            if int(stats[label, cv2.CC_STAT_AREA]) >= 25:
                keep.add(label)
    if not keep:
        return np.zeros_like(proof)
    return np.isin(labels, list(keep))


def _geodesic_layers(seed_mask: np.ndarray, region: np.ndarray) -> np.ndarray:
    """在 region 内、从 seed_mask 出发做 8 邻域 BFS，返回逐像素层号
    （-1=不在 region 内或从 seed 不可达）。裁到 region 的 bbox 内跑，region 通常
    只占全图一小块，这样单帧成本远小于全图尺寸的 dilate 循环。"""
    gd_full = np.full(region.shape, -1, dtype=np.int32)
    if not region.any():
        return gd_full
    rows = np.any(region, axis=1)
    cols = np.any(region, axis=0)
    r0, r1 = np.flatnonzero(rows)[[0, -1]]
    c0, c1 = np.flatnonzero(cols)[[0, -1]]
    region_sub = region[r0 : r1 + 1, c0 : c1 + 1]
    seed_sub = seed_mask[r0 : r1 + 1, c0 : c1 + 1] & region_sub
    gd_sub = np.full(region_sub.shape, -1, dtype=np.int32)
    if seed_sub.any():
        gd_sub[seed_sub] = 0
        current = seed_sub
        max_layers = region_sub.shape[0] + region_sub.shape[1]
        layer = 0
        while layer < max_layers:
            nxt = _dilate(current, 1) & region_sub & (gd_sub < 0)
            if not nxt.any():
                break
            layer += 1
            gd_sub[nxt] = layer
            current = nxt
    gd_full[r0 : r1 + 1, c0 : c1 + 1] = gd_sub
    return gd_full


def _find_tip_mask(roi: np.ndarray, seed: np.ndarray, hsv: np.ndarray) -> tuple[np.ndarray, int]:
    """共用黑指尖几何规则：无彩暗块 + 落在肢体远端（测地距离）+ 细长（欧氏距离
    变换薄）+ 面积区间。stick 工具没有远端黑色，天然被面积/宽度双重拒绝
    （见方案 risks 段的 16 任务实测），无需按任务名分支。

    返回 (tip_mask, gmax)：gmax 是本帧 ROI 内从 seed 出发的最大测地层数，供
    stats 目视归因。
    """
    empty = np.zeros(roi.shape, dtype=bool)
    if not roi.any():
        return empty, 0
    sat = hsv[..., 1]
    val = hsv[..., 2]
    black = roi & (sat <= GATE.tip_s_max) & (val <= GATE.tip_v_max)
    if not black.any():
        return empty, 0

    gd = _geodesic_layers(seed, roi)
    valid_gd = gd[gd >= 0]
    gmax = int(valid_gd.max()) if valid_gd.size else 0
    if gmax < GATE.tip_limb_geo_min:
        # 肢体没有充分伸展进画面（测地层数太浅），本帧不认指尖
        return empty, gmax

    dist = cv2.distanceTransform(black.astype(np.uint8), cv2.DIST_L2, 3)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(black.astype(np.uint8), connectivity=8)
    geo_thr = max(gmax - GATE.tip_geo_slack, GATE.tip_geo_frac * gmax, GATE.tip_geo_abs_min)

    tip = np.zeros(roi.shape, dtype=bool)
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < GATE.tip_area_min or area > GATE.tip_area_max:
            continue
        component = labels == label
        if float(dist[component].max()) > GATE.tip_width_max:
            continue
        comp_gd = gd[component]
        comp_gd = comp_gd[comp_gd >= 0]
        if comp_gd.size == 0 or float(comp_gd.max()) < geo_thr:
            continue
        tip |= component
    return tip, gmax


def compute_masks(
    frames: np.ndarray, phase_flags: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    frames = np.ascontiguousarray(frames)
    if frames.ndim != 4 or frames.shape[-1] != 3 or frames.dtype != np.uint8:
        raise ValueError(f"frames 必须是 (N,H,W,3) uint8，拿到 {frames.shape} {frames.dtype}")
    n, height, width = frames.shape[0], frames.shape[1], frames.shape[2]
    phase_flags = np.asarray(phase_flags, dtype=bool)
    if phase_flags.shape != (n,):
        raise ValueError(f"phase_flags 形状 {phase_flags.shape} 与帧数 {n} 不符")

    remove_masks = np.zeros((n, height, width), dtype=bool)
    tip_masks = np.zeros((n, height, width), dtype=bool)

    total_pixels = height * width
    removed_fraction: list[float] = []
    segments_stats: list[dict[str, Any]] = []
    veto_totals = {"plate_same": 0, "white": 0, "saturated": 0, "registry": 0}
    guard_grow_total = 0

    for seg_start, seg_end in segment_bounds(phase_flags):
        seg_frames = frames[seg_start:seg_end]
        seg_n = seg_frames.shape[0]

        plate, mode_fraction = build_background_plate(seg_frames, CV_PARAMS)
        foregrounds = np.stack([_foreground(seg_frames[i], plate, CV_PARAMS) for i in range(seg_n)])
        border = _border_seed((height, width), CV_PARAMS)

        s_thr, v_min, appearance_pixels = learn_arm_appearance(seg_frames, foregrounds, border, CV_PARAMS)
        occ, occ_info = detect_static_occluder(plate, s_thr, v_min, CV_PARAMS)
        # 二轮学习：臂根常驻画面顶部导致边带采不到核心样本时，用检出的常驻区
        # 增强种子重学一遍（原样搬自 cv_base.compute_arm_masks 的同一段逻辑）
        if appearance_pixels < _MIN_APPEARANCE_PIXELS and occ.any():
            retry = learn_arm_appearance(seg_frames, foregrounds, border | _dilate(occ, 1), CV_PARAMS)
            if retry[2] > appearance_pixels:
                s_thr, v_min, appearance_pixels = retry
                occ, occ_info = detect_static_occluder(plate, s_thr, v_min, CV_PARAMS)
        seed = border | _dilate(occ, 1)

        s_hi = max(2.0 * s_thr, GATE.s_arm_hi_base)
        registry_veto = _registry_veto(plate)
        plate_hsv = cv2.cvtColor(plate, cv2.COLOR_RGB2HSV)

        hsv_frames = [cv2.cvtColor(seg_frames[i], cv2.COLOR_RGB2HSV) for i in range(seg_n)]
        v_arm_lo, v_arm_hi = _learn_v_support(seg_frames, foregrounds, hsv_frames, seed, plate_hsv)

        seg_veto = {"plate_same": 0, "white": 0, "saturated": 0, "registry": 0}
        seg_grow = 0
        seg_tip_frames = 0
        seg_gmax_max = 0

        for i in range(seg_n):
            frame = seg_frames[i]
            hsv = hsv_frames[i]
            sat = hsv[..., 1]
            val = hsv[..., 2]
            fg = foregrounds[i]

            diff = np.abs(frame.astype(np.int16) - plate.astype(np.int16)).max(axis=-1)
            novel = diff > CV_PARAMS.diff_threshold
            plate_same = diff <= GATE.diff_keep

            armlike = (sat <= s_hi) & (val >= 25.0)
            roi = _anchored_components(fg, seed) | (occ & armlike)

            arm_pal = (sat <= s_hi) & (val >= v_arm_lo) & (val <= v_arm_hi)

            # occ（静态常驻区）内否决 A（背景板一致）同步放宽：occ 的定义就是
            # "背景板在这里已经是臂/底座的颜色"（detect_static_occluder 直接在
            # 板上找无彩常驻区），所以 occ 内 frame≈plate 是常态而非例外——用它
            # 判"这是静止真实物体"在 occ 内没有意义，反而会把"臂长期停留在
            # 同一姿态、把板烘成臂色"的常见情形（16 任务实测：StopCube 单任务
            # median 板占比=1.0，即多数像素在全部帧里取值恒定）系统性误判成
            # "静止物体"而整体放行。occ 外否决 A 不变（那里 plate 是真背景，
            # frame≈plate 才真正意味着"这是静止物体，不是臂"）。白/饱和/登记
            # 三条否决在 occ 内外一视同仁，继续兜底（白按钮/彩色物体即使落在
            # occ 附近也不受这条放宽影响）。
            if GATE.occ_relax_novel:
                proof = roi & arm_pal & (novel | occ)
                plate_same_veto = plate_same & ~occ
            else:
                proof = roi & arm_pal & novel
                plate_same_veto = plate_same

            white_veto = (sat <= GATE.white_veto_s) & (val >= GATE.white_veto_v)
            sat_veto = sat >= GATE.sat_veto_min
            keepset = plate_same_veto | white_veto | sat_veto | registry_veto
            proof = proof & ~keepset

            seg_veto["plate_same"] += int((roi & plate_same_veto).sum())
            seg_veto["white"] += int((roi & white_veto).sum())
            seg_veto["saturated"] += int((roi & sat_veto).sum())
            seg_veto["registry"] += int((roi & registry_veto).sum())

            proof = _connectivity_close(proof, seed)

            shadow = _shadow_mask(frame, plate, fg, proof, CV_PARAMS) & ~keepset

            holes = _fill_holes(proof) & ~proof
            proof = proof | (holes & _dilate(roi, 1) & ~keepset)

            # 带守卫生长：故意不再要求 novel。proof 本身已经是
            # roi & arm_pal & (novel|occ) & ~keepset，novel 恒推出 (novel|occ)，
            # 所以"grown 里再要求 novel"在数学上是 proof 的子集操作——16 任务
            # 实测 guard_grow_pixel_total 恒为 0，生长机制变成纯摆设，没有真正
            # 起到"替代 arm_dilate=2、把 1px 混色边缘像素捞回来"的设计目的。
            # 这里的判断：真正挡住误删物体的是 arm_pal（色彩） + keepset 四否决
            # （方案 risks 段原话："环消失，因为物体边缘像素不是高饱和就是纯白
            # 或物体色，不满足 arm_pal 或触发否决"——没提 novel），所以生长环
            # 去掉 novel 这一条不会打开物体保护的口子，只是把 1px 混色/弱对比
            # 边缘（本来因为 diff<=8 没通过 novel、但颜色和否决都判它是臂）纳回来。
            pre_growth = proof | shadow
            grown = _dilate(proof, GATE.guard_grow_iter) & roi & arm_pal & ~keepset
            seg_grow += int((grown & ~pre_growth).sum())

            remove = pre_growth | grown

            tip, gmax = _find_tip_mask(roi, seed, hsv)
            seg_gmax_max = max(seg_gmax_max, gmax)
            if tip.any():
                seg_tip_frames += 1
            remove = remove & ~tip

            remove_masks[seg_start + i] = remove
            tip_masks[seg_start + i] = tip
            removed_fraction.append(float(remove.sum()) / total_pixels)

        for key in veto_totals:
            veto_totals[key] += seg_veto[key]
        guard_grow_total += seg_grow

        segments_stats.append(
            {
                "start": int(seg_start),
                "end": int(seg_end),
                "frame_count": int(seg_n),
                "phase_is_video_demo": bool(phase_flags[seg_start]),
                "arm_sat_threshold": float(s_thr),
                "arm_value_min": float(v_min),
                "appearance_sample_pixels": int(appearance_pixels),
                "s_hi": float(s_hi),
                "v_arm_lo": float(v_arm_lo),
                "v_arm_hi": float(v_arm_hi),
                "static_occluder": occ_info,
                "plate_mode_fraction_min": float(mode_fraction.min()),
                "plate_mode_fraction_median": float(np.median(mode_fraction)),
                "veto_pixels": {k: int(v) for k, v in seg_veto.items()},
                "guard_grow_new_pixels": int(seg_grow),
                "tip_frames_in_segment": int(seg_tip_frames),
                "geo_layers_max": int(seg_gmax_max),
            }
        )

    stats: dict[str, Any] = {
        "frame_count": int(n),
        "segment_count": len(segments_stats),
        "segments": segments_stats,
        "removed_fraction_mean": float(np.mean(removed_fraction)) if removed_fraction else 0.0,
        "removed_fraction_max": float(np.max(removed_fraction)) if removed_fraction else 0.0,
        "veto_pixel_totals": {k: int(v) for k, v in veto_totals.items()},
        "guard_grow_pixel_total": int(guard_grow_total),
        "tip_pixel_total": int(tip_masks.sum()),
        "tip_frame_count": int(np.count_nonzero(tip_masks.reshape(n, -1).any(axis=1))),
    }
    return remove_masks, tip_masks, stats
