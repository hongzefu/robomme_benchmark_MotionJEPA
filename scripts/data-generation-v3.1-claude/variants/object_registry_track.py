"""候选变体 object_registry_track：物体登记册 + 跨接触跟踪。

核心思路：先把任务物体显式建册（板异常 + 非锚定前景两路并集）、逐帧三级回退
跟踪（直接重叠 → 模板匹配 → 冻结不外推）、对附着丝状物（如 RouteStick 白缆线）
做颜色集合区域生长，最后把整本登记册的保护区从臂删除 mask 里做集合减法扣掉，
全程不依赖饱和度。臂主体（背景板/前景/锚定/外观模型/静止底座/阴影）照抄 v3
骨架，只把 `_absorb_fragments` 与 `_protect_saturated_regions` 两步替换成登记册
减法，收尾膨胀带守卫防止膨胀带咬到物体边缘。

黑指尖保留用共用的纯 CV 规则：无彩暗块 + 局部厚度薄 + 处于所在臂连通域的测地
远端（沿臂形状做多源环形膨胀 BFS 近似测地距离，而非直线欧氏距离），且从候选
ROI 里先扣掉登记册保护区，避免把黑色任务物体误判成指尖。
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
    _foreground,
    _shadow_mask,
    build_background_plate,
    detect_static_occluder,
    learn_arm_appearance,
    segment_bounds,
)

NAME = "object_registry_track"
DESCRIPTION = (
    "先按板异常与非锚定前景两路建物体登记册、逐帧三级回退跟踪（直接重叠/模板匹配/"
    "冻结不外推）并按颜色集合生长救援附着丝状物，再从臂删除 mask 里整体做集合减法"
    "扣除（全程不依赖饱和度）；臂主体照抄 v3 骨架，收尾膨胀带守卫防止咬到物体边缘，"
    "黑指尖用无彩薄块 + 测地远端的共用规则单独保留。"
)

_ARM_PARAMS_PATH = Path(__file__).resolve().parents[1] / "cv_base_params.json"
# 外观模型采样像素低于此数视为「学习失败」，触发二轮学习——与 cv_base.compute_arm_masks 同一常量
_MIN_APPEARANCE_PIXELS = 200
_KERNEL3 = np.ones((3, 3), np.uint8)
_KERNEL5 = np.ones((5, 5), np.uint8)  # 板异常去噪开运算专用（压木纹条纹，见 _build_registry）


class _RegistryParams:
    """登记册 + 跟踪专用参数，取值取自方案设计者给定的 params 字典。

    刻意不用 @dataclass：渲染器的变体加载器用 ``spec_from_file_location`` +
    ``exec_module`` 手动加载本模块、不经过标准 import 机制注册 ``sys.modules``，
    ``@dataclass`` 装饰器执行时会按 ``cls.__module__`` 回查 ``sys.modules`` 解析
    字段类型、查不到即崩——纯类属性容器没有这个依赖，效果等价（这里只需要一份
    只读常量命名空间，不需要 dataclass 的 `__init__`/`__eq__` 生成）。
    """

    median_blur_ksize: int = 31
    plate_anom_thresh: int = 14
    plate_anom_area_min: int = 12
    plate_anom_area_max: int = 4000
    plate_anom_top_rows_reject: int = 8
    restframe_arm_area_max: int = 400
    restframe_head_count: int = 6
    track_overlap_dilate: int = 4
    track_area_ratio_lo: float = 0.4
    track_area_ratio_hi: float = 2.5
    template_score_min: float = 0.62
    # 实测 MoveCube exec 段臂连通域质心逐帧（stride=4 采样）位移 p90≈13.5px、max≈26px
    # （被抓物体末端位移常更快）；给定值 14 在这个尺度下太窄、模板匹配经常够不着，
    # 跟丢后永久冻结在旧位置——加宽到 26px 覆盖到实测位移上界，减少「跟丢再也追不回」。
    template_search_pad: int = 26
    lost_halo_base: int = 4
    lost_halo_step: int = 2
    lost_halo_max_step: int = 4
    seam_protect_dilate: int = 10
    color_quant_shift: int = 5
    color_grow_iter: int = 25
    color_grow_area_mul: float = 6.0
    white_grow_s_max: int = 20
    white_grow_v_min: int = 200
    registry_dilate: int = 2
    registry_guard_dilate: int = 3
    arm_dilate_guarded: int = 2
    merge_iou_min: float = 0.3
    tip_s_max: int = 40
    tip_v_max: int = 100
    tip_area_min: int = 4
    tip_area_max: int = 90
    tip_width_max: float = 5.5
    tip_geo_frac: float = 0.75
    # 实测 RouteStick t=19：腕部相机黑支架（非指尖）在测地距离场上恰好卡在
    # gmax-12=56 这条线上（56>=56 险胜通过），被误判成指尖——12 px 余量对这条腕部
    # 支架而言太松。收紧到 8px 后该案例 56<60 被正确挡下；下面用全 16 任务复核
    # 收紧后 14 个夹爪任务的真实指尖命中率没有塌陷。
    tip_geo_margin: float = 8.0
    tip_geo_floor: float = 15.0
    tip_limb_geo_min: float = 18.0
    # 生长面积绝对上限（相对 6 倍初始面积之外再加一道保险，防止大型登记项——如
    # bin、按钮装置——颜色集合过泛时把颜色生长炸成近乎整张画面）
    color_grow_abs_frac: float = 0.35


_REG = _RegistryParams()


# ============================== 通用小工具 ==============================


def _pack_rgb(image: np.ndarray, shift: int) -> np.ndarray:
    """把 RGB 逐通道量化到 (8-shift) 位并打包成单个 uint16 键，供颜色集合匹配用。"""
    bits = 8 - shift
    q = image.astype(np.uint32) >> shift
    packed = (q[..., 0] << (2 * bits)) | (q[..., 1] << bits) | q[..., 2]
    return packed.astype(np.uint16)


def _color_membership(packed: np.ndarray, colorset: frozenset[int]) -> np.ndarray:
    if not colorset:
        return np.zeros(packed.shape, dtype=bool)
    keys = np.fromiter(colorset, dtype=np.uint16, count=len(colorset))
    return np.isin(packed, keys)


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = int(np.count_nonzero(a & b))
    if inter == 0:
        return 0.0
    union = int(np.count_nonzero(a | b))
    return inter / union if union else 0.0


def _bbox_from_mask(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if not rows.any():
        return None
    r_idx = np.flatnonzero(rows)
    c_idx = np.flatnonzero(cols)
    return int(r_idx[0]), int(r_idx[-1]) + 1, int(c_idx[0]), int(c_idx[-1]) + 1


def _shift_mask(mask: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """把 mask 平移 (dy,dx)，超出画面的部分丢弃，绝不环绕。"""
    h, w = mask.shape
    out = np.zeros_like(mask)
    if abs(dy) >= h or abs(dx) >= w:
        return out
    src_r0, src_r1 = max(0, -dy), h - max(0, dy)
    dst_r0, dst_r1 = max(0, dy), h - max(0, -dy)
    src_c0, src_c1 = max(0, -dx), w - max(0, dx)
    dst_c0, dst_c1 = max(0, dx), w - max(0, -dx)
    out[dst_r0:dst_r1, dst_c0:dst_c1] = mask[src_r0:src_r1, src_c0:src_c1]
    return out


def _max_consecutive(flags: list[bool]) -> int:
    best = cur = 0
    for flag in flags:
        cur = cur + 1 if flag else 0
        best = max(best, cur)
    return best


# ============================== 登记册构建 ==============================


def _make_entry(entry_id: int, mask: np.ndarray, source_image: np.ndarray, origin: str) -> dict[str, Any]:
    bbox = _bbox_from_mask(mask)
    area = int(mask.sum())
    r0, r1, c0, c1 = bbox
    height, width = source_image.shape[:2]
    patch = None
    pr0, pr1 = max(0, r0 - 2), min(height, r1 + 2)
    pc0, pc1 = max(0, c0 - 2), min(width, c1 + 2)
    if pr1 - pr0 >= 3 and pc1 - pc0 >= 3:
        patch = source_image[pr0:pr1, pc0:pc1].copy()
    colorset = frozenset(np.unique(_pack_rgb(source_image, _REG.color_quant_shift)[mask]).tolist())
    return {
        "id": entry_id,
        "mask": mask,
        "bbox": bbox,
        "area": area,
        "area_init": area,
        "colorset": colorset,
        "template": patch,
        "lost": 0,
        "touching_arm": False,
        "origin": origin,
        "lost_curve": [],
    }


def _add_or_merge(
    entries: list[dict[str, Any]],
    mask: np.ndarray,
    source_image: np.ndarray,
    origin: str,
    next_id: list[int],
) -> None:
    """新候选与已有登记项 IoU>merge_iou_min 时合并（并集 mask + 颜色集合并集），否则新开一项。"""
    for entry in entries:
        if _iou(mask, entry["mask"]) > _REG.merge_iou_min:
            entry["mask"] = entry["mask"] | mask
            entry["bbox"] = _bbox_from_mask(entry["mask"])
            entry["area"] = int(entry["mask"].sum())
            entry["area_init"] = entry["area"]
            entry["colorset"] = entry["colorset"] | frozenset(
                np.unique(_pack_rgb(source_image, _REG.color_quant_shift)[mask]).tolist()
            )
            return
    entries.append(_make_entry(next_id[0], mask, source_image, origin))
    next_id[0] += 1


def _build_registry(
    seg_frames: np.ndarray,
    plate: np.ndarray,
    foregrounds: np.ndarray,
    seed: np.ndarray,
    occluder: np.ndarray,
) -> list[dict[str, Any]]:
    """每相位段建一次登记册：A 路板异常抓静止物体，B 路非锚定前景抓会动物体。"""
    entries: list[dict[str, Any]] = []
    next_id = [0]
    height, width = plate.shape[:2]

    # ---- A 路：板异常——bg_model 是板的中值模糊，偏离板中值太多的连通块是静止物体 ----
    # 实测发现：本数据集木纹桌面的高频纹理本身就能让 >50% 像素超过 plate_anom_thresh=14
    # （677 个连通块，绝大多数是几像素宽的木纹条纹噪声，MoveCube 上实测把粉棍摔成碎片、
    # 碎片跟丢后棍尖失护）。木纹噪声在空间上是「细条纹」，真实物体是「实心块」，用一次
    # 形态学开运算（5x5）压掉细条纹、保留实心连通域——这不改变「偏离中值模糊即异常」这条
    # 核心机制本身，只是给它加一道通用去噪前处理，压噪后连通块从 677 降到数十量级。
    bg_model = cv2.medianBlur(plate, _REG.median_blur_ksize)
    anom_raw = np.abs(plate.astype(np.int16) - bg_model.astype(np.int16)).max(axis=-1) > _REG.plate_anom_thresh
    anom = cv2.morphologyEx(anom_raw.astype(np.uint8), cv2.MORPH_OPEN, _KERNEL5).astype(bool)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(anom.astype(np.uint8), connectivity=8)
    # 静止底座区（occluder）膨胀一圈作额外排除：它就是 cv_base 专门用来抓「烘进板、对
    # 差分天然失明」的臂常驻残留的检测器，语义与「排掉被烘进板的臂」这条初衷完全重合。
    # 实测：PatternLock 开运算后底座/臂残留会碎成不触第 0 行的子块（bbox 从设计者原始
    # 例子的 [0,53,91,169] 变成 [10,54,78,118]），单靠「顶部 8 行 + 触边」两条已挡不住，
    # 与 occluder 求交是比继续加大开运算核更精准的排除方式（不会误伤紧贴底座的真实物体，
    # 因为真实物体与 occluder 空间上不重叠，只有臂残留会重叠）。
    occluder_guard = _dilate(occluder, 4)
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        if area < _REG.plate_anom_area_min or area > _REG.plate_anom_area_max:
            continue
        if y < _REG.plate_anom_top_rows_reject:
            continue
        if x == 0 or y == 0 or (x + w) == width or (y + h) == height:
            continue
        comp_mask = labels == label
        if (comp_mask & occluder_guard).any():
            continue
        _add_or_merge(entries, comp_mask, plate, "plate_anomaly", next_id)

    # ---- B 路：非锚定前景——只在臂还小、或段首若干帧上累积，避免臂长期占画面时采不到干净候选 ----
    n = seg_frames.shape[0]
    for i in range(n):
        fg = foregrounds[i]
        main = _anchored_components(fg, seed) | occluder
        arm_area = int(main.sum())
        if not (arm_area < _REG.restframe_arm_area_max or i < _REG.restframe_head_count):
            continue
        non_anchored = fg & ~main
        if not non_anchored.any():
            continue
        bcount, blabels, bstats, _ = cv2.connectedComponentsWithStats(non_anchored.astype(np.uint8), connectivity=8)
        for label in range(1, bcount):
            if int(bstats[label, cv2.CC_STAT_AREA]) < 10:
                continue
            _add_or_merge(entries, blabels == label, seg_frames[i], "nonanchored_fg", next_id)

    return entries


# ============================== 颜色集合区域生长 ==============================


def _grow_by_color(
    entry: dict[str, Any],
    packed: np.ndarray,
    hsv: np.ndarray,
    table_floor: np.ndarray,
) -> np.ndarray:
    """按登记项颜色集合（或近白判据）做区域生长，救援附着丝状物（如白缆线）。

    生长严格限定在「plate 判定为桌面/地面」的像素上（排除底座常驻区与臂长驻污染
    区），且单项生长面积不超初始面积 6 倍，另加一道绝对面积保险，双重上限压住
    「颜色集合过泛导致大片桌面被误纳」的风险。每帧从登记项当前 mask 重新生长
    （不做跨帧累积），避免生长结果本身污染下一帧的跟踪参考形状。
    """
    seed_mask = entry["mask"]
    if not seed_mask.any():
        return np.zeros_like(seed_mask)
    bbox = entry["bbox"] or _bbox_from_mask(seed_mask)
    r0, r1, c0, c1 = bbox
    height, width = seed_mask.shape
    pad = _REG.color_grow_iter + 4
    pr0, pr1 = max(0, r0 - pad), min(height, r1 + pad)
    pc0, pc1 = max(0, c0 - pad), min(width, c1 + pad)

    cur = seed_mask[pr0:pr1, pc0:pc1].copy()
    packed_crop = packed[pr0:pr1, pc0:pc1]
    hsv_crop = hsv[pr0:pr1, pc0:pc1]
    table_crop = table_floor[pr0:pr1, pc0:pc1]

    color_pred = _color_membership(packed_crop, entry["colorset"])
    white_pred = (hsv_crop[..., 1] <= _REG.white_grow_s_max) & (hsv_crop[..., 2] >= _REG.white_grow_v_min)
    allowed = (color_pred | white_pred) & table_crop

    area_cap = min(
        entry["area_init"] * _REG.color_grow_area_mul,
        _REG.color_grow_abs_frac * height * width,
    )
    for _ in range(_REG.color_grow_iter):
        candidate = cur | (_dilate(cur, 1) & allowed)
        if int(candidate.sum()) > area_cap:
            break
        if np.array_equal(candidate, cur):
            break
        cur = candidate

    out = np.zeros_like(seed_mask)
    out[pr0:pr1, pc0:pc1] = cur
    return out


# ============================== 跨接触跟踪（三级回退） ==============================


def _track_entry(
    entry: dict[str, Any],
    frame: np.ndarray,
    packed: np.ndarray,
    non_anchored_masks: dict[int, np.ndarray],
    non_anchored_stats: np.ndarray,
    claimed: set[int],
    height: int,
    width: int,
) -> None:
    """三级回退就地更新 entry：①直接重叠 ②模板匹配 ③冻结（lost+=1，不外推）。"""
    prev_mask = entry["mask"]
    prev_area = max(entry["area"], 1)
    matched = False

    if non_anchored_masks:
        search_zone = _dilate(prev_mask, _REG.track_overlap_dilate)
        best_label, best_inter = 0, 0
        for label, comp in non_anchored_masks.items():
            if label in claimed:
                continue
            inter = int(np.count_nonzero(comp & search_zone))
            if inter == 0:
                continue
            area = int(non_anchored_stats[label, cv2.CC_STAT_AREA])
            ratio = area / prev_area
            if not (_REG.track_area_ratio_lo <= ratio <= _REG.track_area_ratio_hi):
                continue
            if inter > best_inter:
                best_inter, best_label = inter, label
        if best_label:
            claimed.add(best_label)
            comp_mask = non_anchored_masks[best_label]
            entry["mask"] = comp_mask
            entry["bbox"] = _bbox_from_mask(comp_mask)
            entry["area"] = int(comp_mask.sum())
            entry["lost"] = 0
            r0, r1, c0, c1 = entry["bbox"]
            pr0, pr1 = max(0, r0 - 2), min(height, r1 + 2)
            pc0, pc1 = max(0, c0 - 2), min(width, c1 + 2)
            if pr1 - pr0 >= 3 and pc1 - pc0 >= 3:
                entry["template"] = frame[pr0:pr1, pc0:pc1].copy()
            entry["colorset"] = entry["colorset"] | frozenset(np.unique(packed[comp_mask]).tolist())
            matched = True

    if not matched and entry["template"] is not None:
        r0, r1, c0, c1 = entry["bbox"]
        pad = _REG.template_search_pad
        sr0, sr1 = max(0, r0 - pad), min(height, r1 + pad)
        sc0, sc1 = max(0, c0 - pad), min(width, c1 + pad)
        search = frame[sr0:sr1, sc0:sc1]
        template = entry["template"]
        th, tw = template.shape[:2]
        if search.shape[0] >= th and search.shape[1] >= tw:
            result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= _REG.template_score_min:
                orig_r = max(0, r0 - 2) - sr0
                orig_c = max(0, c0 - 2) - sc0
                dy = max_loc[1] - orig_r
                dx = max_loc[0] - orig_c
                shifted = _shift_mask(prev_mask, dy, dx)
                if shifted.any():
                    entry["mask"] = shifted
                    entry["bbox"] = _bbox_from_mask(shifted)
                    entry["lost"] = 0
                    matched = True

    if not matched:
        entry["lost"] += 1
        # mask 保持不变：登记项是非刚体（缆线等），跟丢时绝不做位置外推


# ============================== 共用黑指尖规则（含测地距离） ==============================


def _geodesic_distance(component_mask: np.ndarray, seed_mask: np.ndarray) -> tuple[np.ndarray, float]:
    """以 seed_mask 为多源，沿 component_mask 做逐环膨胀 BFS，得到近似测地距离场。

    与直线欧氏距离不同：扩张被严格限制在 component_mask 内，因此距离沿臂的真实
    形状累积（1 环 ≈ 1 px），未被 BFS 覆盖到的像素记 -1。
    """
    dist = np.full(component_mask.shape, -1, dtype=np.int32)
    frontier = seed_mask & component_mask
    if not frontier.any():
        return dist, 0.0
    dist[frontier] = 0
    visited = frontier.copy()
    frontier_u8 = frontier.astype(np.uint8)
    h, w = component_mask.shape
    max_ring = h + w  # 保守上界：测地环数不会超过行数+列数
    ring = 0
    while ring < max_ring:
        grown = cv2.dilate(frontier_u8, _KERNEL3, iterations=1).astype(bool) & component_mask & ~visited
        if not grown.any():
            break
        ring += 1
        dist[grown] = ring
        visited |= grown
        frontier_u8 = grown.astype(np.uint8)
    return dist, float(dist.max()) if visited.any() else 0.0


def _shared_tip_mask(
    tip_roi: np.ndarray,
    hsv: np.ndarray,
    main_raw: np.ndarray,
    seed: np.ndarray,
) -> np.ndarray:
    """无彩暗块 + 局部薄 + 处于所在臂连通域测地远端——才判定为黑色指尖，予以保留。

    测地距离场用 main_raw（未经登记册减法的原始臂连通域）计算，代表物理臂形状，
    避免登记册减法造成的连通性割裂扭曲「远端」的定义。
    """
    height, width = tip_roi.shape
    dark = tip_roi & (hsv[..., 1] <= _REG.tip_s_max) & (hsv[..., 2] <= _REG.tip_v_max)
    if not dark.any():
        return np.zeros((height, width), bool)
    dcount, dlabels, dstats, _ = cv2.connectedComponentsWithStats(dark.astype(np.uint8), connectivity=8)

    area_ok = [
        label
        for label in range(1, dcount)
        if _REG.tip_area_min <= int(dstats[label, cv2.CC_STAT_AREA]) <= _REG.tip_area_max
    ]
    if not area_ok:
        return np.zeros((height, width), bool)

    width_ok = []
    for label in area_ok:
        x, y, w, h, _ = dstats[label]
        crop = (dlabels[y : y + h, x : x + w] == label).astype(np.uint8)
        dt = cv2.distanceTransform(crop, cv2.DIST_L2, 3)
        if float(dt.max()) <= _REG.tip_width_max:
            width_ok.append(label)
    if not width_ok:
        return np.zeros((height, width), bool)

    if not main_raw.any():
        return np.zeros((height, width), bool)
    mcount, mlabels, mstats, _ = cv2.connectedComponentsWithStats(main_raw.astype(np.uint8), connectivity=8)

    accepted = np.zeros((height, width), bool)
    limb_cache: dict[int, tuple[np.ndarray, float, tuple[int, int, int, int]]] = {}
    for label in width_ok:
        comp_full = dlabels == label
        overlap_labels = np.unique(mlabels[comp_full])
        overlap_labels = overlap_labels[overlap_labels != 0]
        if overlap_labels.size == 0:
            continue
        main_label = int(overlap_labels[0])

        if main_label not in limb_cache:
            x, y, w, h, _ = mstats[main_label]
            lr0, lr1 = max(0, y - 2), min(height, y + h + 2)
            lc0, lc1 = max(0, x - 2), min(width, x + w + 2)
            limb_crop = (mlabels == main_label)[lr0:lr1, lc0:lc1]
            seed_crop = (seed & main_raw)[lr0:lr1, lc0:lc1]
            gd_crop, gmax = _geodesic_distance(limb_crop, seed_crop)
            limb_cache[main_label] = (gd_crop, gmax, (lr0, lr1, lc0, lc1))
        gd_crop, gmax, (lr0, lr1, lc0, lc1) = limb_cache[main_label]
        if gmax < _REG.tip_limb_geo_min:
            continue

        comp_crop = comp_full[lr0:lr1, lc0:lc1]
        values = gd_crop[comp_crop]
        values = values[values >= 0]
        if values.size == 0:
            continue
        blob_gd_max = float(values.max())
        threshold = max(gmax - _REG.tip_geo_margin, _REG.tip_geo_frac * gmax, _REG.tip_geo_floor)
        if blob_gd_max >= threshold:
            accepted |= comp_full
    return accepted


# ============================== 主入口 ==============================


def compute_masks(
    frames: np.ndarray, phase_flags: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    frames = np.ascontiguousarray(frames)
    if frames.ndim != 4 or frames.shape[-1] != 3 or frames.dtype != np.uint8:
        raise ValueError(f"frames 必须是 (N,H,W,3) uint8，拿到 {frames.shape} {frames.dtype}")
    n, height, width = frames.shape[:3]
    phase_flags = np.asarray(phase_flags, dtype=bool)
    if phase_flags.shape != (n,):
        raise ValueError(f"phase_flags 形状 {phase_flags.shape} 与帧数 {n} 不符")

    arm_params = ArmRemovalParams.from_json(_ARM_PARAMS_PATH)

    remove_masks = np.zeros((n, height, width), dtype=bool)
    tip_masks = np.zeros((n, height, width), dtype=bool)
    segments_stats: list[dict[str, Any]] = []
    protected_pixel_total = 0
    arm_before_total = 0
    arm_after_total = 0
    tip_pixel_total = 0

    for seg_start, seg_end in segment_bounds(phase_flags):
        seg_frames = frames[seg_start:seg_end]
        plate, mode_fraction = build_background_plate(seg_frames, arm_params)
        foregrounds = np.stack(
            [_foreground(seg_frames[i], plate, arm_params) for i in range(seg_frames.shape[0])]
        )
        border = _border_seed((height, width), arm_params)
        s_thr, v_min, appearance_pixels = learn_arm_appearance(seg_frames, foregrounds, border, arm_params)
        occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, arm_params)
        if appearance_pixels < _MIN_APPEARANCE_PIXELS and occluder.any():
            retry = learn_arm_appearance(seg_frames, foregrounds, border | _dilate(occluder, 1), arm_params)
            if retry[2] > appearance_pixels:
                s_thr, v_min, appearance_pixels = retry
                occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, arm_params)
        seed = border | _dilate(occluder, 1)

        plate_hsv = cv2.cvtColor(plate, cv2.COLOR_RGB2HSV)
        v_floor = min(v_min, float(arm_params.occluder_val_cap))
        stuck_zone = (
            (plate_hsv[..., 1] <= s_thr)
            & (plate_hsv[..., 2] >= v_floor)
            & (mode_fraction < arm_params.stuck_max_mode_fraction)
            if arm_params.stuck_fill
            else np.zeros((height, width), bool)
        )
        # 颜色生长的「桌面/地面」限定域：排除静止底座常驻区与臂长驻污染区
        # （两者都是「plate 上不可信任为桌面」的区域），双重把关防止生长顺色沿臂爬
        table_floor = ~occluder & ~stuck_zone

        registry = _build_registry(seg_frames, plate, foregrounds, seed, occluder)

        # 首帧 stuck_zone 排除用的「上一帧」保护区，用刚建好的登记册近似给出
        prev_protected = np.zeros((height, width), bool)
        for entry in registry:
            prev_protected |= _dilate(entry["mask"], _REG.lost_halo_base)

        for t in range(seg_frames.shape[0]):
            frame = seg_frames[t]
            hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
            packed = _pack_rgb(frame, _REG.color_quant_shift)
            fg_t = foregrounds[t].copy()

            if arm_params.stuck_fill and stuck_zone.any():
                frame_armlike = (hsv[..., 1] <= max(2.0 * s_thr, 25.0)) & (hsv[..., 2] >= 25)
                stuck_zone_frame = stuck_zone & ~_dilate(prev_protected, _REG.registry_dilate)
                fg_t = fg_t | (stuck_zone_frame & frame_armlike)

            main_raw = _anchored_components(fg_t, seed) | occluder
            non_anchored = fg_t & ~main_raw
            arm_before_total += int(main_raw.sum())

            ncount, nlabels, nstats, _ = cv2.connectedComponentsWithStats(
                non_anchored.astype(np.uint8), connectivity=8
            )
            non_anchored_masks = {label: (nlabels == label) for label in range(1, ncount)}
            claimed: set[int] = set()

            # ---- 跟踪：捕获「上一帧」快照供接缝保护用，再逐项三级回退更新 ----
            prev_masks = {e["id"]: e["mask"] for e in registry}
            touching_before = {e["id"]: e["touching_arm"] for e in registry}
            for entry in registry:
                _track_entry(entry, frame, packed, non_anchored_masks, nstats, claimed, height, width)
                entry["grow_mask"] = _grow_by_color(entry, packed, hsv, table_floor)
                entry["lost_curve"].append(entry["lost"])

            # ---- 本帧保护区：halo（随 lost 单调增大）| 颜色生长 | 接缝保护 ----
            protected_raw = np.zeros((height, width), bool)
            for entry in registry:
                halo = _REG.lost_halo_base + _REG.lost_halo_step * min(entry["lost"], _REG.lost_halo_max_step)
                region = _dilate(entry["mask"], halo) | entry["grow_mask"]
                if touching_before[entry["id"]]:
                    region = region | (main_raw & _dilate(prev_masks[entry["id"]], _REG.seam_protect_dilate))
                protected_raw |= region
                entry["touching_arm"] = bool((entry["mask"] & main_raw).any())

            protected_pixel_total += int(protected_raw.sum())

            # ---- 登记册减法替换 v3 的 _absorb_fragments / _protect_saturated_regions ----
            main = main_raw & ~_dilate(protected_raw, _REG.registry_dilate)
            shadow = _shadow_mask(frame, plate, fg_t, main, arm_params)
            final = _dilate(main | shadow, _REG.arm_dilate_guarded)
            final = final & ~_dilate(protected_raw, _REG.registry_guard_dilate)  # 膨胀带守卫

            # ---- 黑指尖：先从 ROI 扣掉登记册保护区，再跑共用规则 ----
            tip_roi = final & ~_dilate(protected_raw, _REG.registry_dilate)
            tip = _shared_tip_mask(tip_roi, hsv, main_raw, seed)
            remove = final & ~tip

            remove_masks[seg_start + t] = remove
            tip_masks[seg_start + t] = tip
            arm_after_total += int(remove.sum())
            tip_pixel_total += int(tip.sum())

            prev_protected = protected_raw

        entries_stats = []
        for entry in registry:
            lost_flags = [x > 0 for x in entry["lost_curve"]]
            entries_stats.append(
                {
                    "id": entry["id"],
                    "origin": entry["origin"],
                    "bbox_init": list(entry["bbox"]) if entry["area_init"] else None,
                    "area_init": entry["area_init"],
                    "bbox_final": list(entry["bbox"]) if entry["bbox"] else None,
                    "area_final": entry["area"],
                    "template_available": entry["template"] is not None,
                    "colorset_size": len(entry["colorset"]),
                    "lost_frame_count": int(sum(lost_flags)),
                    "max_lost_streak": _max_consecutive(lost_flags),
                }
            )
        segments_stats.append(
            {
                "start": int(seg_start),
                "end": int(seg_end),
                "phase_is_video_demo": bool(phase_flags[seg_start]),
                "arm_sat_threshold": float(s_thr),
                "arm_value_min": float(v_min),
                "appearance_sample_pixels": int(appearance_pixels),
                "static_occluder": occluder_info,
                "registry_entry_count": len(registry),
                "entries": entries_stats,
            }
        )

    total_pixels = height * width
    stats: dict[str, Any] = {
        "note": "登记册条目 + 跟踪健康度概览（非逐帧全量曲线，供目视排查用）",
        "frame_count": int(n),
        "segment_count": len(segments_stats),
        "segments": segments_stats,
        "removed_fraction_mean": float(remove_masks.mean()) if n else 0.0,
        "protected_pixel_total": int(protected_pixel_total),
        "arm_pixels_before_registry_total": int(arm_before_total),
        "arm_pixels_after_registry_total": int(arm_after_total),
        "tip_pixel_total": int(tip_pixel_total),
        "total_pixels_per_frame": int(total_pixels),
    }
    return remove_masks, tip_masks, stats
