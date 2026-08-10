"""候选变体：watershed_barrier —— 分水岭区域标注：三类种子 + 真实图像边缘做屏障。

核心思路：把「删哪些像素」从阈值/膨胀问题改成区域归属问题。逐帧标三类种子
（1=背景、2=物体、3=臂），交给 ``cv2.watershed`` 用真实图像梯度当分界线，
分水岭线天然贴在物体与臂之间那条最强边上，从机制上消灭贴边红环，而不是
再叠一层「先膨胀再挖回」的减法。删除域完全不做形态学膨胀，只用一轮
「边缘受限闭合」（只往低梯度平坦区长一圈，长不过物体轮廓这条强边）收掉
零膨胀留下的抗锯齿混色边。

复用 ``cv_base`` 的分段 / 背景板（众数）/ 前景 / 边带种子 / 外观学习 /
常驻底座区（在本变体里只当锚定连通性的种子来源，不再像 v3 那样直接并入
臂 marker——直接并入实测会把「机械臂频繁经过」污染出的常驻区错当成物体
所在位置，在白色物体边缘啃出红环，见下方 ``_process_frame`` 内注释）/
阴影判定；``compute_arm_masks`` 整体不用，臂主体的最终归属改由
``cv2.watershed`` 决定，``_absorb_fragments`` / ``stuck_fill`` /
``_protect_saturated_regions`` / 收尾膨胀全部不用——是候选集里对 v3 主循环
依赖最少、换引擎程度最高的一个。

黑指尖保留：在分水岭结果之上做纯几何判定——臂标签内、无彩且暗、面积与
「宽度」（距离变换半径）都很小、且沿臂形状测地距离够远（贴近臂的测地远端）
的连通块判定为指尖，从删除域里扣出。整套判据不看任务名，panda_stick
任务（无黑色垫块、腕部支架又太粗太厚）天然拿不到指尖标记。

## 锦标赛终评后的第二轮修复（主会话，5 项，参数见 P 中带注释的新增段）

复验残余缺陷全部收敛（根因逐一像素级定位，依据见各实现处注释）：

1. **mid_sat 护栏**（HARD A）：S≥28 一律不判臂，堵住 S∈(20,60) 的低饱和物体
   真空带（InsertPeg 淡紫 peg t=136 实测 151 像素误删 → 0）。
2. **内嵌暗块释放**（HARD A）：小/窄/暗且四周多为亮无彩表面的连通块整块拒删
   （ButtonUnmaskSwap 白 cup 边缘沟槽蛇形误删 → 0；代价是 ≤130px 手掌小黑块
   偶尔漏删）。
3. **指尖成对补全 + 领跑者兜底**（HARD B）：修「成对垫块只保一枚/全灭」的系统
   性非对称（VideoRepick t=216 右垫整枚被删、PickHighlight t=216 全灭等 7 例
   实测全部恢复成对；成对补全每帧最多一枚、40px 上限——腕块与垫块 V 分布
   实测同平台不可分，只能靠距离几何卡）。
4. **带护栏 stuck 规则**（SOFT，v3 回迁）：臂长驻被烤进背景板导致的整块留灰
   （VideoUnmask 复验净度 2/10 的根因）由「污染板 + 当前帧仍与板同色 + 臂色 +
   全部物体判据让路」四条件救回，removed_fraction 0.048→0.103。
5. **底座部件级补涂**（SOFT/STICK）：occluder 中整部件完整落在顶部中央标准
   包络（行[0,56]×列[88,168]）内的才恒红补涂；StopCube 的 occluder 被黑色任务
   装置拉宽越界 → 自动拒涂，构造上不会碰装置。

已知有界残留：StopCube t=432 一块 33.5px 腕部黑块被成对规则误保（外观与垫块
不可分）；被夹白色物体的边缘暗沟槽可能以绿色「指尖」标注保留（像素结果正确，
语义标注不纯）；ButtonUnmaskSwap t=512 前缩指扇因整段停驻烤板且众数占比≈1
不触发 stuck，仍整块留灰（无廉价安全解，双验证者结论一致）。
"""

from __future__ import annotations

import sys
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
    _close,
    _dilate,
    _erode,
    _foreground,
    _shadow_mask,
    build_background_plate,
    detect_static_occluder,
    learn_arm_appearance,
    segment_bounds,
)

NAME = "watershed_barrier"
DESCRIPTION = (
    "分水岭区域标注：三类种子（背景/物体/臂）+ 真实图像边缘做屏障，"
    "零膨胀、只做一轮边缘受限闭合收边，指尖靠测地远端几何判据保留"
)

_CVB_PARAMS_PATH = Path(__file__).resolve().parents[1] / "cv_base_params.json"

# 本变体自有参数，取值来自方案设计者给出的规格。除 cv_base 复用的背景板/前景/
# 外观学习/常驻区/阴影参数外（走 cv_base_params.json 的既有调优值），其余全部
# 集中在这里，方便日后单独调参。
P: dict[str, Any] = {
    "work_roi_dilate": 12,
    "bg_marker_erode": 2,
    "obj_marker_erode": 1,
    "arm_marker_erode": 2,
    "arm_marker_erode_thin": 1,
    "thin_dt_thresh": 3,
    "thin_dt_ultra_thresh": 1.5,  # 独立验证发现的修复：DT<=1.5（约半径 1px 的细杆/
                                  # 细指）直接用候选原始像素做种子、erode=0，见下方
                                  # marker3 三档腐蚀处注释；规格原文只给了两档，这一档
                                  # 是补丁新增，不改变规格给出的其余机制与参数取值。
    "plate_same_thresh": 6,
    "novel_thresh": 8,
    "sat_marker_min": 60,
    "white_marker_s": 20,
    "white_marker_v": 230,
    "plate_anom_thresh": 14,
    "plate_anom_area_min": 12,
    "plate_anom_area_max": 4000,
    "median_blur_ksize": 31,
    "closure_grad_pct": 30,
    "closure_iter": 1,
    "tip_s_max": 40,
    "tip_v_max": 100,
    "tip_area_min": 4,
    "tip_area_max": 90,
    "tip_width_max": 5.5,
    "tip_geo_slack": 12,
    "tip_geo_frac": 0.82,  # 规格给的 0.75 在 PatternLock 实测放过一个 88px/gd=23(gmax=30)
                           # 的腕部支架暗块（0.75*30=22.5<23，卡不住）；上调到 0.82 后
                           # 0.82*30=24.6>23，把它拦下，同时不影响真实指尖（应几乎贴着
                           # gmax，离阈值有充足余量）——实测细节见自检报告
    "tip_geo_abs_min": 15,
    "tip_limb_geo_min": 18,
    # --- 以下为锦标赛复验后的第二轮修复参数（主会话增补，逐条依据见对应实现处注释） ---
    "mid_sat_min": 28,             # 中饱和物体护栏：S≥28 一律不算臂（臂学习上限 20，淡紫
                                   # peg 实测 S≈35 落在 20–60 的旧护栏真空带）
    "emb_area_max": 130,           # 内嵌暗块释放的面积上限：cup 沟槽实测 15–112，腕部
                                   # 支架大黑块实测 174 起，130 是安全分界
    "emb_width_max": 5.5,          # 内嵌暗块宽度上限（距离变换峰值）
    "emb_v_max": 150,              # 「暗」的亮度上限（沟槽/指尖垫 V≤100，留裕量）
    "emb_s_max": 45,               # 「暗」的饱和度上限（无彩判据）
    "emb_ring_bright_frac": 0.55,  # 膨胀环内亮无彩（S≤45 且 V≥170）占比下限——「内嵌在
                                   # 亮色表面里」的结构性判据，cup 体与臂壳都满足
    "pair_dist_max": 40.0,         # 指尖成对补全：与已保留垫块的质心距离上限。真垫对
                                   # 实测间距 26–37px；腕部黑块误拉案例实测 40.3/43.4px
                                   # （StopCube t=432 / PickHighlight t=216），40 是分界。
                                   # 垫块与腕块的暗像素 V 分布实测完全重叠（同为 [38,60]
                                   # 平台），外观不可分，只能靠距离几何卡
    "pair_area_ratio": 3.5,        # 成对补全的面积比上限（实测 37 vs 73 的开指对）
    "leader_geo_frac": 0.55,       # 领跑者兜底：主判据全灭时，测地最远候选只要
                                   # geo ≥ max(0.55·gmax, 15) 即保留（PickHighlight t=216
                                   # 实测真垫块 geo=32、gmax=46，0.82 档全灭）
    "leader_width_max": 3.2,       # 领跑者兜底额外收紧宽度（真垫块实测宽度 ≤2.7）
    "stuck_frame_v_min": 25,       # stuck 规则当前帧臂色亮度下限（沿用 v3 取值）
    "base_paint_rows": (0, 56),    # 底座补涂包络（行）：13/16 任务底座 bbox 行[0,28]、
    "base_paint_cols": (88, 168),  # PatternLock 行[0,52] 列[91,168]，包络取并集加裕量；
                                   # StopCube 的 occluder 被黑色任务装置拉宽到列 37 起，
                                   # 整部件越界 → 自动拒涂，构造上不会碰装置
}
# arm_dilate=0 未在下方出现——这就是「完全不做膨胀」这条口径的字面兑现，
# 不是遗漏，留在这里只为让读者一眼看到「零膨胀」是显式决定而非疏漏。
_ARM_DILATE_INTENTIONALLY_ZERO = 0

# 指尖质心回填 patch 边长与测地 BFS 步数上限：规格文字里没给出具体数值，
# 由实现者按「小到 3×3 的白垫圈」这句描述与画面尺寸（256×256，对角线 ~362）
# 补齐，不改变规格里明确给出的机制与参数。
_OBJ_FALLBACK_PATCH = 3
_GEODESIC_MAX_STEPS = 400


def _erode_with_centroid_fallback(mask: np.ndarray, iterations: int) -> tuple[np.ndarray, int]:
    """按连通域腐蚀，某个分量腐蚀后整体消失时在其质心回填一个小 patch。

    这是规格里点名的「本变体最致命的实现坑」：白色按钮/垫圈/缆线常常只有
    几像素到几十像素，腐蚀一次就可能被削没，导致该物体在 marker 图里彻底
    失去物体种子、被邻近的臂区域吞掉。用「按连通域回填质心」而不是干脆
    不腐蚀，是为了让物体的核心种子依然经过一次腐蚀收紧（贴合分水岭对种子
    「越纯越好」的一般要求），只在腐蚀会把整个分量抹零时才兜底。
    """
    if not mask.any():
        return mask.copy(), 0
    eroded = _erode(mask, iterations)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    result = eroded.copy()
    half = _OBJ_FALLBACK_PATCH // 2
    height, width = mask.shape
    fallback_count = 0
    for label in range(1, count):
        component = labels == label
        if (eroded & component).any():
            continue
        cx, cy = centroids[label]
        row, col = int(round(cy)), int(round(cx))
        r0, r1 = max(0, row - half), min(height, row + half + 1)
        c0, c1 = max(0, col - half), min(width, col + half + 1)
        result[r0:r1, c0:c1] = True
        fallback_count += 1
    return result, fallback_count


def _plate_anomaly_region(plate: np.ndarray, occluder: np.ndarray) -> np.ndarray:
    """背景板上的「异常静止无彩物体块」——StopCube 黑色静态装置这类不靠饱和度、
    也不靠触边/触顶（常驻底座区要求触顶）区分的静止无彩物体，只能靠「板一致」
    本身当物体种子。与常驻底座区重叠的分量交给常驻区/臂种子处理，不重复标注。
    """
    plate_hsv = cv2.cvtColor(plate, cv2.COLOR_RGB2HSV)
    achromatic = _close(plate_hsv[..., 1] <= P["plate_anom_thresh"], 1)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        achromatic.astype(np.uint8), connectivity=8
    )
    region = np.zeros(plate.shape[:2], dtype=bool)
    occluder_present = occluder.any()
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if not (P["plate_anom_area_min"] <= area <= P["plate_anom_area_max"]):
            continue
        component = labels == label
        if occluder_present and (component & occluder).any():
            continue
        region |= component
    return region


def _geodesic_distance(region: np.ndarray, source: np.ndarray) -> np.ndarray:
    """在 region 内、从 source 出发做多源 BFS（逐圈 3x3 膨胀近似测地距离）。

    真正的测地最短路需要 scipy（禁用）；用「每轮只在 region 内膨胀一圈」的
    grassfire 近似同样能沿着弯曲的臂形状正确累积距离（不会像欧氏距离那样
    抄近路穿过 mask 外的区域），够用且纯 cv2/numpy。返回逐像素测地步数，
    region 外或不可达像素为 -1。
    """
    dist = np.full(region.shape, -1, dtype=np.int32)
    src = source & region
    if not src.any():
        return dist
    dist[src] = 0
    frontier = src
    remaining = region & ~src
    steps = 0
    while frontier.any() and remaining.any() and steps < _GEODESIC_MAX_STEPS:
        steps += 1
        grown = _dilate(frontier, 1) & region
        newly = grown & (dist < 0)
        if not newly.any():
            break
        dist[newly] = steps
        frontier = newly
        remaining = remaining & ~newly
    return dist


def _detect_tips(arm_lbl: np.ndarray, hsv: np.ndarray, seed: np.ndarray) -> tuple[np.ndarray, int]:
    """在分水岭裁决出的臂标签之上，用几何判据挑出黑色指尖垫块。

    先用「无彩暗 + 面积 + 局部宽度（连通域自身的距离变换峰值）」粗筛候选，
    只有存在候选时才算测地距离图（省掉 stick 任务与大量无候选帧的 BFS 开销）；
    再要求候选块位于臂标签测地远端——这是区分「指尖」与「腕部支架黑色块」
    的关键：两者的无彩/暗/面积区间可能重叠，但指尖天然在肢体末梢，支架不是。

    锦标赛复验补丁（两条，针对「成对垫块只保一枚/全灭」的系统性非对称）：

    1. **领跑者兜底**：主判据（geo ≥ max(gmax−slack, frac·gmax, abs_min)）全灭时，
       取测地最远、且宽度更严（≤leader_width_max）的候选，只要
       geo ≥ max(leader_geo_frac·gmax, abs_min) 就保留。根因：gmax 是全臂标签的
       测地极值，不保证落在夹爪上——PickHighlight t=216 实测 gmax=46 出现在臂
       肘段，真垫块 geo=32 被 0.82 档整帧拒光。
    2. **成对补全**：垫块天然成对。凡与已保留垫块质心距离 ≤pair_dist_max、面积比
       ≤pair_area_ratio 的候选，免测地判据直接补进。根因：第二枚垫块的测地读数
       系统性偏低——BinFill t=468 右垫紧邻常驻底座 seed（geo=4 vs 左垫 30），
       VideoRepick t=216 两垫同高却差 9 步（BFS 绕行路径不对称）。
    """
    shape = arm_lbl.shape
    dark = arm_lbl & (hsv[..., 1] <= P["tip_s_max"]) & (hsv[..., 2] <= P["tip_v_max"])
    tip = np.zeros(shape, dtype=bool)
    if not dark.any():
        return tip, 0

    count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        dark.astype(np.uint8), connectivity=8
    )
    candidates: list[dict[str, Any]] = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if not (P["tip_area_min"] <= area <= P["tip_area_max"]):
            continue
        component = labels == label
        dt_component = cv2.distanceTransform(component.astype(np.uint8), cv2.DIST_L2, 3)
        width = float(dt_component.max())
        if width > P["tip_width_max"]:
            continue
        candidates.append(
            {"mask": component, "area": area, "width": width, "centroid": centroids[label]}
        )
    if not candidates:
        return tip, 0

    seed_touch = seed & arm_lbl
    geo = _geodesic_distance(arm_lbl, seed_touch)
    valid = geo >= 0
    if not valid.any():
        return tip, 0
    gmax = int(geo[valid].max())
    if gmax < P["tip_limb_geo_min"]:
        return tip, 0
    threshold_geo = max(gmax - P["tip_geo_slack"], P["tip_geo_frac"] * gmax, P["tip_geo_abs_min"])

    for cand in candidates:
        component_valid = cand["mask"] & valid
        cand["geo"] = float(geo[component_valid].max()) if component_valid.any() else -1.0
        cand["accepted"] = cand["geo"] >= threshold_geo

    # 领跑者兜底：主判据全灭时放宽到 0.55·gmax，宽度收紧到真垫块实测范围
    if not any(c["accepted"] for c in candidates):
        leader_floor = max(P["leader_geo_frac"] * gmax, P["tip_geo_abs_min"])
        narrow = [c for c in candidates if c["width"] <= P["leader_width_max"] and c["geo"] >= leader_floor]
        if narrow:
            max(narrow, key=lambda c: c["geo"])["accepted"] = True

    # 成对补全：与已保留垫块距离近、尺寸相当的候选免测地补进。垫块恰好一对，
    # 每帧最多补一枚、取最近邻——腕部黑块与垫块外观完全不可分（V 分布同平台），
    # 多补一枚就多一分把腕块拉进来的风险（StopCube t=432 实测一帧误拉两块腕块）。
    accepted_now = [c for c in candidates if c["accepted"]]
    best_pair: tuple[float, dict[str, Any]] | None = None
    for cand in candidates:
        if cand["accepted"]:
            continue
        for anchor in accepted_now:
            dist = float(np.hypot(*(np.asarray(cand["centroid"]) - np.asarray(anchor["centroid"]))))
            big, small = max(cand["area"], anchor["area"]), min(cand["area"], anchor["area"])
            if dist <= P["pair_dist_max"] and big <= P["pair_area_ratio"] * small:
                if best_pair is None or dist < best_pair[0]:
                    best_pair = (dist, cand)
    if best_pair is not None:
        best_pair[1]["accepted"] = True

    kept = 0
    for cand in candidates:
        if cand["accepted"]:
            tip |= cand["mask"]
            kept += 1
    return tip, kept


def _embedded_dark_release(arm_lbl: np.ndarray, hsv: np.ndarray) -> np.ndarray:
    """内嵌暗块释放：臂标签里「小面积 + 窄 + 暗无彩 + 四周多为亮无彩表面」的连通块
    从删除域整块释放（保留原像素、不打指尖标）。

    这是 ButtonUnmaskSwap t=364 HARD A 的机制修复：被夹的白灰 cup 与臂壳在外观上
    真不可分（同为无彩、V 同在 230 平台），cup 边缘沟槽（无彩暗、V≤100）落进
    arm_palette 成为臂种子后蛇形误删。「暗结构内嵌在亮表面里」是 cup 沟槽与黑指尖
    垫的共同结构签名——腕部支架黑块面积实测 ≥174、不中 emb_area_max=130 上限，
    仍照常删除；代价是 ≤130px 的手掌小黑块偶尔漏删（SOFT 让位 HARD A/B，符合
    口径）。指尖垫在桌面/物体上方时膨胀环亮无彩占比不足 0.55、不会被释放，仍走
    _detect_tips 的绿色标注路径；只有夹持白色物体时垫块才会被这里静默保留
    （不删也不标绿，语义上是「保守拒删」）。
    """
    dark = arm_lbl & (hsv[..., 1] <= P["emb_s_max"]) & (hsv[..., 2] <= P["emb_v_max"])
    if not dark.any():
        return np.zeros_like(arm_lbl)
    # 膨胀环的「亮无彩」判据：S 与暗判据同阈、V≥170（臂壳与 cup 体实测都在 180+）
    bright_achro = (hsv[..., 1] <= P["emb_s_max"]) & (hsv[..., 2] >= 170)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(dark.astype(np.uint8), connectivity=8)
    released = np.zeros_like(arm_lbl)
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area > P["emb_area_max"]:
            continue
        component = labels == label
        dt_component = cv2.distanceTransform(component.astype(np.uint8), cv2.DIST_L2, 3)
        if float(dt_component.max()) > P["emb_width_max"]:
            continue
        ring = _dilate(component, 2) & ~component
        if not ring.any():
            continue
        if float(bright_achro[ring].mean()) >= P["emb_ring_bright_frac"]:
            released |= component
    return released


def _prepare_segment(seg_frames: np.ndarray, cvb_params: ArmRemovalParams) -> dict[str, Any]:
    """相位段级别的一次性准备：背景板、前景、边带种子、外观模型、常驻底座区、
    背景板异常物体块。逐字复用 cv_base 对应原语，只是不再走
    ``compute_arm_masks`` 的整段主循环。
    """
    plate, mode_fraction = build_background_plate(seg_frames, cvb_params)
    foregrounds = np.stack(
        [_foreground(seg_frames[i], plate, cvb_params) for i in range(seg_frames.shape[0])]
    )
    border = _border_seed(seg_frames.shape[1:3], cvb_params)
    s_thr, v_min, appearance_pixels = learn_arm_appearance(seg_frames, foregrounds, border, cvb_params)
    occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, cvb_params)
    if appearance_pixels < _MIN_APPEARANCE_PIXELS and occluder.any():
        retry = learn_arm_appearance(seg_frames, foregrounds, border | _dilate(occluder, 1), cvb_params)
        if retry[2] > appearance_pixels:
            s_thr, v_min, appearance_pixels = retry
            occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, cvb_params)
    seed = border | _dilate(occluder, 1)
    anom_region = _plate_anomaly_region(plate, occluder)

    # 臂长驻污染区（v3 stuck 规则的加护栏回迁）：背景板呈臂色且时间不稳定的像素。
    # VideoUnmask t=136–236 实测臂在段内长时间停驻，被众数烤进背景板，前景差分
    # 在整段停驻区恒为零、臂大块留灰（复验净度 2/10 的根因）。众数占比 <0.95 才算
    # 污染（保护恒定的无彩静止物：白按钮、装置——它们占比 ≈1.0）。
    plate_hsv = cv2.cvtColor(plate, cv2.COLOR_RGB2HSV)
    v_floor = min(v_min, float(cvb_params.occluder_val_cap))
    stuck_zone = (
        (plate_hsv[..., 1] <= s_thr)
        & (plate_hsv[..., 2] >= v_floor)
        & (mode_fraction < cvb_params.stuck_max_mode_fraction)
    )

    # 底座补涂区（部件级白名单）：occluder 中「整个连通部件完整落在顶部中央标准
    # 包络内」的部件才允许逐帧补涂成红。依据：13/16 任务底座 bbox 恒为
    # 行[0,28]×列[110,145]、PatternLock 行[0,52]×列[91,168]（同一机器人同一相机的
    # 自证）；StopCube 的 occluder 被左侧黑色任务装置拉宽到列 37 起，整部件越界
    # → 自动拒涂——构造上保证任务装置永远不会被这条规则涂到（HARD A 优先）。
    r0, r1 = P["base_paint_rows"]
    c0, c1 = P["base_paint_cols"]
    base_zone = np.zeros(plate.shape[:2], dtype=bool)
    if occluder.any():
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            occluder.astype(np.uint8), connectivity=8
        )
        for label in range(1, count):
            x, y, w, h, _area = stats[label]
            if y >= r0 and y + h <= r1 and x >= c0 and x + w <= c1:
                base_zone |= labels == label
    return {
        "plate": plate,
        "foregrounds": foregrounds,
        "seed": seed,
        "s_thr": s_thr,
        "v_min": v_min,
        "appearance_pixels": appearance_pixels,
        "occluder": occluder,
        "occluder_info": occluder_info,
        "anom_region": anom_region,
        "stuck_zone": stuck_zone,
        "base_zone": base_zone,
    }


def _process_frame(
    frame: np.ndarray,
    plate: np.ndarray,
    foreground: np.ndarray,
    seed: np.ndarray,
    s_thr: float,
    v_min: float,
    occluder: np.ndarray,
    anom_region: np.ndarray,
    stuck_zone: np.ndarray,
    base_zone: np.ndarray,
    cvb_params: ArmRemovalParams,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """单帧主流程：组三类 marker → cv2.watershed 裁决 → 物体护栏 → 边缘受限闭合 →
    内嵌暗块释放 → 底座补涂 → 阴影 → 指尖扣除。"""
    shape = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    diff_max = np.abs(frame.astype(np.int16) - plate.astype(np.int16)).max(axis=-1)

    anchored_fg = _anchored_components(foreground, seed)
    unanchored_fg = foreground & ~anchored_fg

    # --- marker 2：物体 ---
    sat_mask = hsv[..., 1] >= P["sat_marker_min"]
    white_mask = (hsv[..., 1] <= P["white_marker_s"]) & (hsv[..., 2] >= P["white_marker_v"])
    marker2_raw = sat_mask | white_mask | anom_region | unanchored_fg
    marker2, obj_fallback_count = _erode_with_centroid_fallback(marker2_raw, P["obj_marker_erode"])

    # --- marker 3：臂（锚定前景∩臂调色板∩板新颖），细结构少腐蚀一次 ---
    # 注意：常驻底座区 occluder 特意不直接并入这里（只经 seed 参与锚定连通性判定，
    # 见 _prepare_segment）。实测踩过一次坑：occluder 是在整段背景板上学出来的
    # 「顶部无彩常驻区」，一旦某个白色任务物体长时间停留/被机械臂频繁经过同一
    # 片顶部区域，该像素的众数会被判成「机器人常驻」，occluder 就会覆盖到物体
    # 位置——若直接把 occluder 并入 marker3，物体会在这些帧里被贴分水岭种子，
    # 复现出 v3 那种「物体被吞」的红环（VideoUnmask 实测：白色方块贴着 occluder
    # 边界出现一圈红环，红环消失需要去掉这行 union）。occluder 因此退化为「只在
    # 当前帧确有新证据（板新颖 + 臂调色板 + 与种子锚定连通）时才帮着连通」的角色，
    # 代价是底座在多数帧里因板一致而留白未删（SOFT 让位于 HARD A，符合优先级）。
    arm_palette = (hsv[..., 1] <= s_thr) & (hsv[..., 2] >= v_min)
    novel = diff_max > P["novel_thresh"]
    marker3_candidate = anchored_fg & arm_palette & novel

    # 带护栏的 stuck 规则（v3 回迁）：污染区里当前帧仍与污染板同色（~novel）且呈
    # 臂色的像素并入臂候选，专修「臂长驻被烤进背景板 → 前景恒零 → 整块留灰」。
    # 三重护栏使它比 v3 版更难伤物体：①~novel——物体移入/移出污染区的帧里当前帧
    # 必与板不同（novel 为真），被排除；只有「此刻看起来就是板上那条停驻臂」的像素
    # 才进；②~marker2_raw——高饱和/纯白/板异常块/非锚定前景全部让路；③后续仍要过
    # 锚定连通性 + 分水岭后的全部物体护栏。
    if stuck_zone.any():
        frame_armlike = (hsv[..., 1] <= max(2.0 * s_thr, 25.0)) & (
            hsv[..., 2] >= P["stuck_frame_v_min"]
        )
        stuck_candidate = stuck_zone & frame_armlike & ~novel & ~marker2_raw
        marker3_candidate = marker3_candidate | stuck_candidate

    if marker3_candidate.any():
        # 独立验证发现的第二个坑（连着上面三档腐蚀一起修，同一根因链）：原实现在
        # 腐蚀之后的碎片图 eroded3 上才做 _anchored_components 判连通。腐蚀在细长
        # 结构（panda_stick 细杆、细手指）上凿出的缺口会把本来完整的一块候选切成
        # 好几个孤岛，只有贴着 seed 的那一小块能通过「腐蚀后再判连通」，其余孤岛
        # （哪怕就在原候选里跟 seed 是连着的）被整体丢弃——RouteStick t=112 实测
        # 三档腐蚀改完仍有虚线状缺口，根因就在这里，不是腐蚀档位不够细。
        # marker3_candidate 本身 ⊆ anchored_fg（= _anchored_components(foreground,
        # seed) 的结果），这一步改到在腐蚀之前、原始候选上先做一次锚定判连通：
        # 候选与 seed 的连通性只判一次、判在信息最完整的原始候选图上，腐蚀之后只
        # 管收边、不再重新裁决「这一块算不算连通」，缺口造成的顶多是细一点，不会
        # 再把整段远端孤岛判丢。
        marker3_candidate = _anchored_components(marker3_candidate, seed)

    if marker3_candidate.any():
        e_thin = _erode(marker3_candidate, P["arm_marker_erode_thin"])
        e_thick = _erode(marker3_candidate, P["arm_marker_erode"])
        dt = cv2.distanceTransform(marker3_candidate.astype(np.uint8), cv2.DIST_L2, 3)
        # 三档腐蚀（比规格原始的两档多切一档「超细」）：panda_stick 的细杆实测半径
        # 只有约 1px（DT<=1.5），沿对角线走的 1px 宽结构对 3x3 结构元哪怕只腐蚀 1 次
        # 也几乎必然被整段抹零（对角阶梯线的大多数像素本就只有 2 个对角同类邻居，
        # 一腐蚀就断）——RouteStick t=112 实测正是这样：细杆在候选阶段（marker3_
        # candidate）连续完整，腐蚀成 eroded3 后只剩零星孤岛。
        # 超细区（DT<=thin_dt_ultra_thresh）直接用原始候选像素做种子、不腐蚀——
        # 这里没有「腐蚀去掉不确定混色边界像素」的余地可让：候选本身已经过
        # arm_palette（无彩）+ novel（板新颖）双重过滤，本就是高置信度的臂/工具
        # 像素，不腐蚀只是不再额外自残，不会引入新的物体误判风险。
        ultra_thin_zone = marker3_candidate & (dt <= P["thin_dt_ultra_thresh"])
        thin_zone = marker3_candidate & (dt < P["thin_dt_thresh"]) & ~ultra_thin_zone
        marker3 = e_thick | (e_thin & thin_zone) | ultra_thin_zone
    else:
        marker3 = np.zeros(shape, dtype=bool)

    if not marker3.any():
        # 本帧真的没有臂（或臂种子在腐蚀+测地过滤后彻底消失）：整帧判「无臂」，
        # 臂路径一个像素都不删；但底座部件仍然可见、仍是机器人，照常补涂
        # （同样让全部物体判据先行让路）。
        no_arm_mid_sat = hsv[..., 1] >= P["mid_sat_min"]
        no_arm_base = base_zone & ~no_arm_mid_sat & ~marker2_raw
        return (
            no_arm_base,
            np.zeros(shape, dtype=bool),
            {
                "no_arm": True,
                "obj_fallback_count": obj_fallback_count,
                "tip_component_count": 0,
                "released_pixels": 0,
            },
        )

    # --- marker 1：背景（板一致像素，腐蚀 2 次） ---
    marker1 = _erode(diff_max <= P["plate_same_thresh"], P["bg_marker_erode"])

    markers = np.zeros(shape, dtype=np.int32)
    markers[marker1] = 1
    if marker2.any():
        markers[marker2] = 2
    markers[marker3] = 3  # 最后写、覆盖前两类，臂优先级最高

    if not (markers == 1).any():
        # 兜底：背景种子彻底缺失时至少强制 2px 画面边框为背景，防止三类标签坍缩成
        # 只有臂一类、watershed 无法定界。正常情形（桌面必然大片可见）几乎不会触发。
        border_ring = np.zeros(shape, dtype=bool)
        border_ring[:2, :] = True
        border_ring[-2:, :] = True
        border_ring[:, :2] = True
        border_ring[:, -2:] = True
        border_ring &= markers != 3
        markers[border_ring] = 1

    # work_roi 外一律强制背景，防止分水岭在无纹理桌面上漫灌（桌面木纹的中等强度
    # 边缘足以让分水岭在缺乏种子约束时切出奇怪形状）。marker3 恒 ⊆ work_roi
    # （它的来源 anchored_fg/occluder 本就是 work_roi 的膨胀前底集），所以这一行
    # 只会把落在 roi 外的 1/2/未知收紧成背景，不会误伤臂。
    work_roi = _dilate(anchored_fg | occluder, P["work_roi_dilate"])
    markers[~work_roi] = 1

    bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    # 分水岭输入做一次中值模糊：桌面木纹的中等强度纹理边缘会在原图梯度场里制造
    # 大量虚假局部边界，模糊后这些纹理噪声被平滑掉，真正的臂/物体轮廓（对比度
    # 远高于木纹）基本不受影响。注意：只模糊喂给 watershed 的图像，第 5 步「边缘
    # 受限闭合」仍用原始灰度图算梯度分位数——那一步只在已确定的臂边界 1px 邻域内
    # 生效，需要真实的边界梯度强度做参照，模糊会把这个参照值系统性拉低。
    ws_input = cv2.medianBlur(bgr, P["median_blur_ksize"])
    ws_markers = markers.copy()
    cv2.watershed(ws_input, ws_markers)
    arm_lbl = ws_markers == 3  # 分水岭线(-1)与其余标签一律判保留

    # 独立验证发现的修复：marker2（物体）只腐蚀 1 次收紧种子，物体与臂直接贴合/
    # 被抓取的帧里，这一圈被腐蚀掉的物体边界像素会退化成 markers==0（未知）——
    # marker-controlled watershed 不会覆盖已标记的种子像素（marker2 命中的像素
    # 分水岭后恒为 2，不会被这里过滤误伤），但这圈「未知」像素紧贴着旁边更强的
    # 臂标签，flood 时被判给 3。SwingXtimes t=204 实测正是这样：被抓的红方块贴
    # 夹爪一侧的边缘像素（S=255 纯红高饱和物体像素）因腐蚀丢种子被分水岭划给臂，
    # 红方块啃出一圈缺口。这里做最后一道兜底：任何像素只要本身仍满足高置信度、
    # 当帧直接测得的物体判据（高饱和 sat_mask / 纯白 white_mask / 不锚定前景
    # unanchored_fg——这三者都是「这一帧此刻看，它就是物体」的强证据），就绝不
    # 算作臂。
    #
    # 注意：这里特意不把 marker2_raw 整体（含 anom_region 板异常静止块）都拿来
    # 保护——anom_region 是从整段背景板（众数）反推出的「板上有块静止无彩物体」
    # 弱先验，专为 StopCube 这类真正静止的黑色装置设计；但它只看 PLATE 本身，不看
    # 当帧。若细工具（如 panda_stick 的杆）在某段时间反复经过同一片屏幕位置，
    # 该处众数也可能被烤成类似的「静止无彩块」，与 StopCube 撞到同一条判据——
    # RouteStick t=112 实测就是这样：杆尖处 anom_region 命中，若也拿来保护会把
    # marker3 已经用当帧强证据（锚定前景∩臂调色板∩板新颖）正确判给臂的杆尖像素
    # 重新剥回去，STICK 口径「整根都删」又失守。真正静止的 StopCube 装置本身
    # novel（与板比对）恒为假，从不会进入 marker3_candidate 参与竞争，不受此收窄
    # 影响，见下方 StopCube 回归复核。
    # 锦标赛复验补丁：护栏新增 mid_sat_mask（S≥28 一律不算臂）。旧护栏
    # sat_mask(S≥60) 与臂外观上限（s_thr≤20）之间存在 S∈(20,60) 的真空带——
    # InsertPeg 淡紫 peg（S≈35）被夹起后既非高饱和、又非纯白、又已锚定，
    # 分水岭把它的一角灌给臂种子（t=136 实测 151 像素被删）。臂本体 S≤20，
    # 28 的下限对臂零误伤，只影响臂-桌交界 1–2px 混色带（本就属「保守拒删」边）。
    mid_sat_mask = hsv[..., 1] >= P["mid_sat_min"]
    object_strong_signal = mid_sat_mask | white_mask | unanchored_fg
    arm_lbl = arm_lbl & ~object_strong_signal

    # --- 边缘受限闭合：只往低梯度平坦区长一圈，长不过物体轮廓这条强边 ---
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    grad_x = cv2.Scharr(gray, cv2.CV_32F, 1, 0)
    grad_y = cv2.Scharr(gray, cv2.CV_32F, 0, 1)
    grad = np.abs(grad_x) + np.abs(grad_y)
    for _ in range(P["closure_iter"]):
        boundary = _dilate(arm_lbl, 1) & ~arm_lbl
        if not boundary.any():
            break
        threshold = float(np.percentile(grad[boundary], P["closure_grad_pct"]))
        closure_add = boundary & (grad < threshold) & work_roi & ~marker2_raw & ~object_strong_signal
        if not closure_add.any():
            break
        arm_lbl = arm_lbl | closure_add

    # 内嵌暗块释放（HARD A：cup 沟槽蛇形误删的机制修复，见函数 docstring）
    released = _embedded_dark_release(arm_lbl, hsv)
    arm_lbl = arm_lbl & ~released

    # 底座补涂：部件级白名单（见 _prepare_segment 注释）恒红，恢复 v3 的「常驻区
    # 恒红」语义但只对「确认是纯底座」的部件生效。臂划过底座时这些像素本就是
    # 机器人（底座被臂挡住），照涂不误；全部物体护栏与释放区仍然让路。
    base_paint = base_zone & ~object_strong_signal & ~marker2_raw & ~released

    shadow = _shadow_mask(frame, plate, foreground, arm_lbl, cvb_params) & ~marker2_raw & ~object_strong_signal
    tip, tip_component_count = _detect_tips(arm_lbl, hsv, seed)
    remove = (arm_lbl | shadow | base_paint) & ~tip

    return (
        remove,
        tip,
        {
            "no_arm": False,
            "obj_fallback_count": obj_fallback_count,
            "tip_component_count": tip_component_count,
            "released_pixels": int(released.sum()),
        },
    )


def compute_masks(
    frames: np.ndarray, phase_flags: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    frames = np.ascontiguousarray(frames)
    if frames.ndim != 4 or frames.shape[-1] != 3 or frames.dtype != np.uint8:
        raise ValueError(f"frames 必须是 (N,H,W,3) uint8，拿到 {frames.shape} {frames.dtype}")
    n = frames.shape[0]
    phase_flags = np.asarray(phase_flags, dtype=bool)
    if phase_flags.shape != (n,):
        raise ValueError(f"phase_flags 形状 {phase_flags.shape} 与帧数 {n} 不符")

    cvb_params = ArmRemovalParams.from_json(_CVB_PARAMS_PATH)

    remove_masks = np.zeros(frames.shape[:3], dtype=bool)
    tip_masks = np.zeros(frames.shape[:3], dtype=bool)
    removed_fraction: list[float] = []
    total_pixels = frames.shape[1] * frames.shape[2]

    segments_stats: list[dict[str, Any]] = []
    no_arm_frames_total = 0
    obj_fallback_total = 0
    tip_component_total = 0

    for seg_start, seg_end in segment_bounds(phase_flags):
        seg_frames = frames[seg_start:seg_end]
        prep = _prepare_segment(seg_frames, cvb_params)

        seg_no_arm = 0
        seg_obj_fallback = 0
        seg_tip_components = 0
        seg_released = 0

        for offset in range(seg_frames.shape[0]):
            idx = seg_start + offset
            remove, tip, frame_stats = _process_frame(
                seg_frames[offset],
                prep["plate"],
                prep["foregrounds"][offset],
                prep["seed"],
                prep["s_thr"],
                prep["v_min"],
                prep["occluder"],
                prep["anom_region"],
                prep["stuck_zone"],
                prep["base_zone"],
                cvb_params,
            )
            remove_masks[idx] = remove
            tip_masks[idx] = tip
            removed_fraction.append(float(remove.sum()) / total_pixels)
            seg_no_arm += int(frame_stats["no_arm"])
            seg_obj_fallback += frame_stats["obj_fallback_count"]
            seg_tip_components += frame_stats["tip_component_count"]
            seg_released += frame_stats["released_pixels"]

        no_arm_frames_total += seg_no_arm
        obj_fallback_total += seg_obj_fallback
        tip_component_total += seg_tip_components

        segments_stats.append(
            {
                "start": int(seg_start),
                "end": int(seg_end),
                "phase_is_video_demo": bool(phase_flags[seg_start]),
                "arm_sat_threshold": float(prep["s_thr"]),
                "arm_value_min": float(prep["v_min"]),
                "appearance_sample_pixels": int(prep["appearance_pixels"]),
                "static_occluder": prep["occluder_info"],
                "plate_anomaly_area": int(prep["anom_region"].sum()),
                "stuck_zone_area": int(prep["stuck_zone"].sum()),
                "base_zone_area": int(prep["base_zone"].sum()),
                "no_arm_frames": seg_no_arm,
                "object_marker_fallback_count": seg_obj_fallback,
                "tip_component_count": seg_tip_components,
                "released_pixel_total": seg_released,
            }
        )

    stats: dict[str, Any] = {
        "frame_count": int(n),
        "segment_count": len(segments_stats),
        "segments": segments_stats,
        "no_arm_frames_total": int(no_arm_frames_total),
        "object_marker_fallback_total": int(obj_fallback_total),
        "tip_component_total": int(tip_component_total),
        "removed_fraction_mean": float(np.mean(removed_fraction)) if removed_fraction else 0.0,
        "removed_fraction_max": float(np.max(removed_fraction)) if removed_fraction else 0.0,
    }
    return remove_masks, tip_masks, stats
