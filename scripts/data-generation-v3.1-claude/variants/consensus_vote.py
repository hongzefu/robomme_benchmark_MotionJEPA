"""consensus_vote：五路证据一致才删、任一物体证据即一票否决。

判决结构本身就是「拿不准就保留」的落地：删除某像素需要五路正证据（逐像素布尔图）
全票通过，而任一路物体否决优先级高于全部正证据、不设最小面积门槛。

五路正证据：
    E1 连通性   —— 属于锚定连通域（触边前景连通域）或条件常驻区（底座 + 臂
                    home 长驻痕迹，由 ``detect_static_occluder`` 学出）；
    E2 板新颖性 —— 与背景板逐通道最大绝对差 > 8（原始差值，不做闭运算/填洞）；
    E3 外观     —— S <= max(2*s_thr, 26) 且 V ∈ [25, v_arm_hi]（v_arm_hi 从锚定
                    核心学出、封顶 229，天然把黑橡胶指尖 V≈38/59 与白灰臂身
                    V≈143–229 都圈进来，同时排除 231 的纯白物体材质）；
    E4 时间瞬态性 —— 当前像素不等于自己的时间众数（即不是「板一致」）且该像素
                    在本段内呈现「臂色」的帧占比 f_arm <= 0.90（短段放宽到
                    0.92）——永远呈臂色的像素是白物体或底座，不是掠过的臂；
    E5 邻域支撑 —— 5×5 邻域里 >= 50% 的像素同时满足 E1∧E2∧E3（灭孤立噪点/
                    1px 接缝，不递归叠加 E4/E5 自身）。

四路否决（任一命中即保留，优先级高于任何正证据，不设最小面积）：
    高饱和 S>=60；纯白材质 S<=20 且 V>=230；板一致 diff<=6；板上「异常静止
    物体」登记表（achromatic 且几乎全程恒定、但不与画面边/学到的底座相连——
    floor/checker/底座本体天然触边被排除，孤立在桌面中央的静态装置则被登记）。

常驻底座区（occluder）与阴影各自作为独立 OR 通道并入候选——两者都是背景差分
天然失明的情形（底座恒定不变，diff≈0；阴影是逐通道等比压暗，不满足 E2 的
「新颖」定义），因此绕过 E1∧E2∧E3∧E4∧E5 的全票要求直接进入候选，但仍必须
过全部四路否决（不然 StopCube 的静态装置若恰好触及底座连通域也会被误删）。

收尾只做一次「投票式生长」（不做无条件膨胀）：未删像素若 8 邻域里 >=6 个已删
且自身通过 E2∧E3∧无否决，才补进来。

指尖判定同样做成 T1/T2/T3 三取三一致投票（只在「本帧候选删除区域」内找）：
    T1 暗无彩  —— S<=40 且 V<=100；
    T2 远端    —— 块内「距入画边/底座的欧氏距离代理」gd_max 达到本帧整臂
                    gmax 的高位区间（gd_max >= max(gmax-12, 0.75*gmax, 15)
                    且 gmax>=18）——用 border∪occluder 的欧氏距离变换近似
                    「沿臂延展方向的深入程度」，不是严格测地距离，但对本数据
                    集里臂基本单调从边缘伸向桌面的姿态足够好用；
    T3 细小    —— 面积 ∈ [4,90] 且块自身的距离变换最大值（半宽代理）<=5.5。
    stick 机器人（PatternLock/RouteStick）上 T3 天然失败：候选块面积/半宽都
    超限；且 stick 末端灰杆 V≈143/144 连 T1 都过不了。本函数不接收/不判断
    任务名，两个 stick 任务的「零指尖」结果是判据本身推出来的，不是任务名
    分支挑出来的。

复用 ``cv_base`` 的 ``segment_bounds``/``build_background_plate``/``_foreground``/
``_border_seed``/``_anchored_components``/``learn_arm_appearance``/
``detect_static_occluder``/``_shadow_mask`` 作为各路证据的原料；
``compute_arm_masks`` 主流程不用，本模块自行组装投票逻辑；``_absorb_fragments``
与 ``stuck_fill`` 均不用——前者的职能由 E5 邻域支撑承接，后者的职能由 E1 的
「条件常驻区」（occluder）分支承接。
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
    _dilate,
    _erode,
    _foreground,
    _shadow_mask,
    build_background_plate,
    detect_static_occluder,
    learn_arm_appearance,
    segment_bounds,
)

NAME = "consensus_vote"
DESCRIPTION = (
    "五路正证据（连通性/板新颖性/外观/时间瞬态性/邻域支撑）全票通过才删、"
    "四路否决（高饱和/纯白材质/板一致/异常静止物体登记表）优先级最高一票保留；"
    "指尖判定同样做成暗无彩/远端/细小三取三一致投票。"
)

# ------------------------------------------------------------------
# 判决参数：数值与命名逐一对应方案设计 JSON 的 params 字段
# ------------------------------------------------------------------
E2_NOVEL_THRESH = 8.0           # E2：板新颖性阈值（原始 |frame-plate| 最大通道差）
E3_S_HI_BASE = 26.0             # E3：S 上限公式 max(2*s_thr, 26) 里的常数项
E3_V_LO = 25.0                  # E3：V 下限
E3_V_HI_PCT = 99.9              # v_arm_hi 学习用的分位数
E3_V_HI_CAP = 229.0             # v_arm_hi 硬上限（臂无彩上限，天然排除 231 纯白）
E4_F_ARM_MAX = 0.90             # E4：臂色占比上限（常规段）
E4_F_ARM_MAX_SHORTSEG = 0.92    # E4：短段放宽阈值
SHORTSEG_FRAME_THRESHOLD = 15   # 段内帧数不超过该值即视为「短段」（PatternLock 实测 12 帧）
E5_WINDOW = 5                   # E5：邻域支撑窗口边长
E5_NEIGHBOR_FRAC = 0.5          # E5：邻域内需同时满足 E1∧E2∧E3 的像素占比下限
VETO_SAT_MIN = 60.0             # 否决①：高饱和
VETO_WHITE_S = 20.0             # 否决②：纯白材质 S 上限
VETO_WHITE_V = 230.0            # 否决②：纯白材质 V 下限
VETO_PLATE_SAME = 6.0           # 否决③：板一致（几乎不新颖）
VETO_REGISTRY_DILATE = 2        # 否决④：登记表膨胀半径
VOTE_GROW_NEIGHBORS = 6         # 投票式生长：8 邻域已删数下限
FAR_FROM_WHITE_PX = 5.0         # v_arm_hi 采样：远离板上白物体的距离下限（px）

# --- 指尖三票参数 ---
TIP_S_MAX = 40.0
TIP_V_MAX = 100.0
TIP_AREA_MIN = 4
TIP_AREA_MAX = 90
TIP_WIDTH_MAX = 5.5
TIP_GEO_SLACK = 12.0
TIP_GEO_FRAC = 0.75
TIP_GEO_ABS_MIN = 15.0
TIP_LIMB_GEO_MIN = 18.0

# --- 「板上异常静止物体登记表」参数：方案只给了膨胀半径，achromatic 阈值/
# 面积上下限由本实现按 cv_base 自身注释里的安全分界补齐（见 _static_object_registry）---
REGISTRY_ACHROMATIC_S_MAX = 20.0   # 与 cv_base.occluder_sat_cap 默认值一致：
                                    # 地面棋盘带 S≈23，用 26+ 会把它也登记进来，
                                    # 20 是 cv_base 自己验证过的安全分界
REGISTRY_MODE_FRACTION_MIN = 0.90  # 「几乎全程恒定」的众数占比下限
REGISTRY_AREA_MIN = 20
REGISTRY_AREA_MAX = 20000

_BASE_PARAMS = ArmRemovalParams()  # 只借用其边带/形态学核等与 v3 一致的通用几何参数
_NEIGHBOR8_KERNEL = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.float32)
_CLOSE_KERNEL = np.ones((3, 3), np.uint8)

# 外观学习采样像素低于此数视为「学习失败」，与 cv_base.compute_arm_masks 的二轮
# 学习触发阈值保持一致，便于对照
_MIN_APPEARANCE_PIXELS = 200


def _to_py(value: Any) -> Any:
    """把 numpy 标量/数组递归转成原生 Python 类型，保证 stats 能被 json.dumps 序列化。"""
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {k: _to_py(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_py(v) for v in value]
    return value


def _learn_v_arm_hi(
    seg_frames: np.ndarray,
    foregrounds: np.ndarray,
    seed: np.ndarray,
    plate_hsv: np.ndarray,
) -> tuple[float, int]:
    """学臂 V 上支撑：锚定域腐蚀 2 次 ∩ 远离板上白物体 5px 的 V 直方图取 p99.9，封顶 229。

    「远离板上白物体」用背景板本身的纯白检测（S<=20 且 V>=230）做距离变换实现：
    白色任务物体（按钮座、缆线）若恰好与臂核心相邻，会把 V 直方图污染成虚高，
    5px 缓冲带滤掉这类邻接采样。核心样本与 ``learn_arm_appearance`` 完全同源
    （同一个 ``_anchored_components`` 腐蚀 2 次），采样为空时回退到硬上限 229，
    与 v3.1 说明九登记的「appearance_pixels=0 回退」一致。
    """
    white_on_plate = (plate_hsv[..., 1] <= VETO_WHITE_S) & (plate_hsv[..., 2] >= VETO_WHITE_V)
    if white_on_plate.any():
        dist = cv2.distanceTransform((~white_on_plate).astype(np.uint8), cv2.DIST_L2, 3)
        far_from_white = dist > FAR_FROM_WHITE_PX
    else:
        far_from_white = np.ones(white_on_plate.shape, dtype=bool)

    samples: list[np.ndarray] = []
    for index in range(seg_frames.shape[0]):
        core = _erode(_anchored_components(foregrounds[index], seed), 2) & far_from_white
        if not core.any():
            continue
        val = cv2.cvtColor(seg_frames[index], cv2.COLOR_RGB2HSV)[..., 2][core]
        samples.append(val)
    if not samples:
        return E3_V_HI_CAP, 0
    all_values = np.concatenate(samples).astype(np.float64)
    v_hi = float(np.percentile(all_values, E3_V_HI_PCT))
    return min(v_hi, E3_V_HI_CAP), int(all_values.size)


def _static_object_registry(
    plate_hsv: np.ndarray,
    mode_fraction: np.ndarray,
    touch_seed: np.ndarray,
) -> tuple[np.ndarray, int]:
    """板上「异常静止物体」登记表：achromatic 且几乎全程恒定、但不触边/不连底座。

    与 ``detect_static_occluder`` 互补而不重复：occluder 要求「必须触顶」以
    区分底座与桌面物体；这里反过来要求「必须不触边、不连学到的底座区」，专门
    捕获 StopCube 那类孤立坐在桌面中央、颜色又落在臂外观区间内的静态装置——
    这类装置的红轮廓正是 v3 基线的已知失败之一（HARD A 失败 ③）。

    只用 S<=20（而非 E3 的 26+）：地面棋盘带 S≈23，若沿用 E3 的宽阈值会把
    棋盘带一并登记，进而阻止该处真正被臂经过时删除；20 是 cv_base 自身注释
    验证过的安全分界，专门把棋盘带挡在外面。
    """
    achromatic = (plate_hsv[..., 1] <= REGISTRY_ACHROMATIC_S_MAX) & (
        mode_fraction >= REGISTRY_MODE_FRACTION_MIN
    )
    achromatic = cv2.morphologyEx(
        achromatic.astype(np.uint8), cv2.MORPH_CLOSE, _CLOSE_KERNEL
    ).astype(bool)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        achromatic.astype(np.uint8), connectivity=8
    )
    registry = np.zeros(plate_hsv.shape[:2], dtype=bool)
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < REGISTRY_AREA_MIN or area > REGISTRY_AREA_MAX:
            continue
        component = labels == label
        if (component & touch_seed).any():
            continue  # 触边/连底座：floor、棋盘带或底座本体，不是孤立装置
        registry |= component
    return registry, int(registry.sum())


def _classify_tips(
    saturation: np.ndarray,
    value: np.ndarray,
    candidate_region: np.ndarray,
    gd_map: np.ndarray,
    limb_region: np.ndarray,
) -> np.ndarray:
    """在本帧「候选删除区域」内做 T1/T2/T3 三取三，找出应保留的黑色指尖。"""
    tip = np.zeros(candidate_region.shape, dtype=bool)
    dark = (saturation <= TIP_S_MAX) & (value <= TIP_V_MAX)  # T1
    candidate_pixels = candidate_region & dark
    if not candidate_pixels.any():
        return tip
    gmax = float(gd_map[limb_region].max()) if limb_region.any() else 0.0
    if gmax < TIP_LIMB_GEO_MIN:
        return tip  # 整条臂都伸不远，谈不上「远端」，直接放弃（T2 的前提条件）
    geo_threshold = max(gmax - TIP_GEO_SLACK, TIP_GEO_FRAC * gmax, TIP_GEO_ABS_MIN)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        candidate_pixels.astype(np.uint8), connectivity=8
    )
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < TIP_AREA_MIN or area > TIP_AREA_MAX:
            continue  # T3 面积
        component = labels == label
        width_proxy = float(cv2.distanceTransform(component.astype(np.uint8), cv2.DIST_L2, 3).max())
        if width_proxy > TIP_WIDTH_MAX:
            continue  # T3 半宽
        block_gd_max = float(gd_map[component].max())
        if block_gd_max < geo_threshold:
            continue  # T2 远端
        tip |= component
    return tip


def compute_masks(
    frames: np.ndarray, phase_flags: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    frames = np.ascontiguousarray(frames)
    n = frames.shape[0]
    remove_masks = np.zeros(frames.shape[:3], dtype=bool)
    tip_masks = np.zeros(frames.shape[:3], dtype=bool)
    total_pixels = frames.shape[1] * frames.shape[2]

    segments_stats: list[dict[str, Any]] = []
    # 全片累积（用于 stats 里的整体可解释读数）
    agg = {
        key: []
        for key in (
            "e1", "e2", "e3", "e4", "e5", "vote_pass",
            "veto_sat", "veto_white", "veto_plate", "veto_registry",
            "full_vote_but_vetoed", "occluder_px", "shadow_px",
            "grow_added", "tip_px", "removed_fraction",
        )
    }

    for seg_start, seg_end in segment_bounds(phase_flags):
        seg_frames = frames[seg_start:seg_end]
        seg_len = seg_frames.shape[0]

        plate, mode_fraction = build_background_plate(seg_frames, _BASE_PARAMS)
        foregrounds = np.stack(
            [_foreground(seg_frames[i], plate, _BASE_PARAMS) for i in range(seg_len)]
        )
        border = _border_seed(frames.shape[1:3], _BASE_PARAMS)
        s_thr, v_min, appearance_pixels = learn_arm_appearance(seg_frames, foregrounds, border, _BASE_PARAMS)
        occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, _BASE_PARAMS)
        # 二轮学习：与 cv_base.compute_arm_masks 同一套逻辑，臂根常驻顶部时纯边带
        # 锚定采不到核心样本，用检出的常驻区增强种子重学
        if appearance_pixels < _MIN_APPEARANCE_PIXELS and occluder.any():
            retry = learn_arm_appearance(seg_frames, foregrounds, border | _dilate(occluder, 1), _BASE_PARAMS)
            if retry[2] > appearance_pixels:
                s_thr, v_min, appearance_pixels = retry
                occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, _BASE_PARAMS)
        seed = border | _dilate(occluder, 1)

        e3_s_hi = max(2.0 * s_thr, E3_S_HI_BASE)
        plate_hsv = cv2.cvtColor(plate, cv2.COLOR_RGB2HSV)
        v_arm_hi, v_hi_samples = _learn_v_arm_hi(seg_frames, foregrounds, seed, plate_hsv)

        registry, registry_area = _static_object_registry(plate_hsv, mode_fraction, seed)
        registry = _dilate(registry, VETO_REGISTRY_DILATE)

        # gd_map：从入画边界/底座出发的欧氏距离代理（非严格测地距离，见模块 docstring）
        seed_for_gd = border | occluder
        gd_map = cv2.distanceTransform((~seed_for_gd).astype(np.uint8), cv2.DIST_L2, 5)

        # f_arm 累积图：逐帧「臂色」命中次数 / 段内帧数；顺带缓存 hsv 供组装循环复用
        armlike_count = np.zeros(plate.shape[:2], dtype=np.float32)
        hsv_cache: list[np.ndarray] = []
        for index in range(seg_len):
            hsv_i = cv2.cvtColor(seg_frames[index], cv2.COLOR_RGB2HSV)
            hsv_cache.append(hsv_i)
            armlike = (
                (hsv_i[..., 1] <= e3_s_hi)
                & (hsv_i[..., 2] >= E3_V_LO)
                & (hsv_i[..., 2] <= v_arm_hi)
            )
            armlike_count += armlike
        f_arm = armlike_count / float(seg_len)
        e4_f_arm_max = E4_F_ARM_MAX_SHORTSEG if seg_len <= SHORTSEG_FRAME_THRESHOLD else E4_F_ARM_MAX

        seg_remove = np.zeros((seg_len, *plate.shape[:2]), dtype=bool)
        seg_tip = np.zeros_like(seg_remove)

        for index in range(seg_len):
            frame = seg_frames[index]
            hsv_i = hsv_cache[index]
            saturation = hsv_i[..., 1].astype(np.float32)
            value = hsv_i[..., 2].astype(np.float32)
            diff_max = np.abs(frame.astype(np.int16) - plate.astype(np.int16)).max(axis=-1).astype(np.float32)

            fg = foregrounds[index]
            main_component = _anchored_components(fg, seed)

            e1 = main_component | occluder
            e2 = diff_max > E2_NOVEL_THRESH
            e3 = (saturation <= e3_s_hi) & (value >= E3_V_LO) & (value <= v_arm_hi)
            pixel_eq_plate = np.all(frame == plate, axis=-1)
            e4 = (~pixel_eq_plate) & (f_arm <= e4_f_arm_max)
            base_e123 = (e1 & e2 & e3).astype(np.float32)
            neighbor_frac = cv2.boxFilter(base_e123, -1, (E5_WINDOW, E5_WINDOW), normalize=True)
            e5 = neighbor_frac >= E5_NEIGHBOR_FRAC

            vote_pass = e1 & e2 & e3 & e4 & e5

            shadow = _shadow_mask(frame, plate, fg, main_component | occluder, _BASE_PARAMS)

            veto_sat = saturation >= VETO_SAT_MIN
            veto_white = (saturation <= VETO_WHITE_S) & (value >= VETO_WHITE_V)
            veto_plate = diff_max <= VETO_PLATE_SAME
            # 板一致否决只对「常规投票通道」生效；常驻区/阴影两条 OR 通道豁免它——
            # occluder 的判定依据本来就是「与背景板长期一致」（底座恒定不变，diff≈0
            # 是它的定义特征，不是可疑信号），若仍用 veto_plate 卡它会自相矛盾地把
            # 整个底座判成「保留」，实测 StopCube 这类臂大部分时间缩在画面外的任务
            # 会因此把底座 2016px 砍到几乎全灭（removed_fraction 从预期的 ~3% 掉到
            # 0.4%）。其余三路否决（高饱和/纯白材质/异常静止登记表）仍然全额生效，
            # 作为「occluder 万一误圈到真实彩色/白色物体」时的兜底防线。
            any_veto_soft = veto_sat | veto_white | registry
            any_veto_full = any_veto_soft | veto_plate

            vote_component = vote_pass & ~any_veto_full
            resident_component = (occluder | shadow) & ~any_veto_soft
            candidate = vote_component | resident_component

            neighbor_count = cv2.filter2D(
                candidate.astype(np.float32), -1, _NEIGHBOR8_KERNEL, borderType=cv2.BORDER_CONSTANT
            )
            grow = (~candidate) & (neighbor_count >= VOTE_GROW_NEIGHBORS) & e2 & e3 & ~any_veto_full
            final = candidate | grow
            any_veto = any_veto_full

            tip = _classify_tips(saturation, value, final, gd_map, e1)
            final_no_tip = final & ~tip

            seg_remove[index] = final_no_tip
            seg_tip[index] = tip

            full_vote_but_vetoed = int((vote_pass & any_veto).sum())
            agg["e1"].append(int(e1.sum()))
            agg["e2"].append(int(e2.sum()))
            agg["e3"].append(int(e3.sum()))
            agg["e4"].append(int(e4.sum()))
            agg["e5"].append(int(e5.sum()))
            agg["vote_pass"].append(int(vote_pass.sum()))
            agg["veto_sat"].append(int(veto_sat.sum()))
            agg["veto_white"].append(int(veto_white.sum()))
            agg["veto_plate"].append(int(veto_plate.sum()))
            agg["veto_registry"].append(int(registry.sum()))
            agg["full_vote_but_vetoed"].append(full_vote_but_vetoed)
            agg["occluder_px"].append(int(occluder.sum()))
            agg["shadow_px"].append(int(shadow.sum()))
            agg["grow_added"].append(int(grow.sum()))
            agg["tip_px"].append(int(tip.sum()))
            agg["removed_fraction"].append(float(final_no_tip.sum()) / total_pixels)

        remove_masks[seg_start:seg_end] = seg_remove
        tip_masks[seg_start:seg_end] = seg_tip

        segments_stats.append(
            {
                "start": int(seg_start),
                "end": int(seg_end),
                "frame_count": int(seg_len),
                "phase_is_video_demo": bool(phase_flags[seg_start]),
                "arm_sat_threshold": float(s_thr),
                "arm_value_min": float(v_min),
                "appearance_sample_pixels": int(appearance_pixels),
                "e3_s_hi": float(e3_s_hi),
                "v_arm_hi": float(v_arm_hi),
                "v_arm_hi_sample_pixels": int(v_hi_samples),
                "e4_f_arm_max_used": float(e4_f_arm_max),
                "static_occluder": occluder_info,
                "registry_area_px": int(registry_area),
                "registry_area_after_dilate_px": int(registry.sum()),
            }
        )

    def _mean(key: str) -> float:
        return float(np.mean(agg[key])) if agg[key] else 0.0

    def _max(key: str) -> int:
        return int(np.max(agg[key])) if agg[key] else 0

    stats: dict[str, Any] = {
        "frame_count": int(n),
        "segment_count": len(segments_stats),
        "segments": segments_stats,
        "removed_fraction_mean": _mean("removed_fraction"),
        "removed_fraction_max": float(np.max(agg["removed_fraction"])) if agg["removed_fraction"] else 0.0,
        # 五路正证据逐帧通过像素数（均值/最大）
        "e1_connectivity_pixels_mean": _mean("e1"),
        "e2_novelty_pixels_mean": _mean("e2"),
        "e3_appearance_pixels_mean": _mean("e3"),
        "e4_transience_pixels_mean": _mean("e4"),
        "e5_neighbor_support_pixels_mean": _mean("e5"),
        "vote_pass_all5_pixels_mean": _mean("vote_pass"),
        "vote_pass_all5_pixels_max": _max("vote_pass"),
        # 四路否决逐帧命中像素数
        "veto_saturated_pixels_mean": _mean("veto_sat"),
        "veto_white_material_pixels_mean": _mean("veto_white"),
        "veto_plate_same_pixels_mean": _mean("veto_plate"),
        "veto_static_registry_pixels_mean": _mean("veto_registry"),
        # 核心可解释读数：全票通过但被否决砍掉的像素——否决实际拦下了多少
        "full_vote_but_vetoed_pixels_mean": _mean("full_vote_but_vetoed"),
        "full_vote_but_vetoed_pixels_max": _max("full_vote_but_vetoed"),
        # 常驻区/阴影两条 OR 通道与投票式生长、指尖的规模
        "occluder_pixels_mean": _mean("occluder_px"),
        "shadow_pixels_mean": _mean("shadow_px"),
        "vote_grow_added_pixels_mean": _mean("grow_added"),
        "tip_pixels_mean": _mean("tip_px"),
    }
    return remove_masks, tip_masks, _to_py(stats)
