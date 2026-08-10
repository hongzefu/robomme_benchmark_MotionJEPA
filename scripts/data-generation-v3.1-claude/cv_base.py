#!/usr/bin/env python3
"""v3.1 共享 CV 基座：v3-claude 删臂算法原样拷贝，供各候选变体 import 复用。

⚠ 本文件是 `scripts/data-generation-v3-claude/arm_removal.py` 的逐字拷贝（仅改本
docstring 开头），作为 v3.1 各变体的**共同底座**——变体在 `variants/` 里各自成模块，
按需 import 这里的原语（背景板、前景、锚定、外观模型、底座检测等）并叠加自己的
物体保护 / 黑指尖保留机制。**变体不得修改本文件**：需要不同行为时把函数拷进自己的
模块改。v3.1 的新口径（物体零误删、夹爪黑指尖保留、panda_stick 任务全删）由变体
层实现，本基座保持 v3 原语义（多删向）不动，便于对照。

以下为 v3 原始文档：本模块回答一件事——**只靠通用图像规则**（不碰任何仿真真值），
在静止相机的 RoboMME `front_rgb` 序列里逐帧找出机械臂（含夹爪）与其阴影的像素。
找到的像素由调用方涂成纯红遮罩——本模块只产 mask，不做任何填充。

## 算法结构（按相位段独立执行）

1. **背景板（众数，不是中值）**：相机与光源全程静止、渲染确定性极强（实测 86% 像素
   跨 291 帧逐位重复、无 ±1 噪声），因此背景是时间轴上唯一高频重复值，而臂扫过同一
   像素时颜色随姿态散布在许多低频取值上。逐像素取**众数**天然免疫「被臂遮挡超过
   半程」的情形——中值在这类像素上会给出错值（实测 1.35% 像素众数占比 < 0.5，
   最坏 0.309，中值在这些像素上不可靠）。
2. **前景**：与背景板的逐通道最大绝对差 > 阈值。信噪比极高（阈值 4→20 前景占比
   仅 3.64%→3.35%，曲线极平），默认 8 是安全中间档。
3. **臂外观模型（从数据学，非硬编码）**：第一遍触边连通域腐蚀取核心，取 HSV 饱和度
   的 median + 3·MAD 并设硬上限——上限的依据是实测：臂核心 S≈4、底座 S≈8–10、
   地面棋盘带 S≈23、桌面 S≈160，上限 20 是唯一安全分界。不用 95 分位：臂夹着
   高饱和物体时分位数会被污染（MoveCube 实测给出 158 的荒谬阈值）。
4. **静止底座区**：机器人底座固定在画面顶部中央、全程被自己占据，背景差分对它
   天然失明，必须在背景板上专门检测：「无彩且够亮 + 触顶 + 宽度上限 + 面积区间」。
   白色任务物体（按钮座、白方块）全部靠「必须触顶」这一条排除（实测 5 个无彩候选
   只有底座过筛）。
5. **逐帧臂判定三级**：①锚定——与 top/left/right 边带或底座区接触的前景连通域
   （臂不一定从顶边入画：RouteStick 首帧夹爪从右缘探入，实测只锚 top 会漏整只手）；
   ②碎片吸附——被前景任务物体切断的臂小碎片按「距主体近 + 臂色一致 + 面积小」
   吸附回来；③阴影——阴影是背景的逐通道**等比**压暗，用比值均值区间 + 通道比值
   一致性判定（暗色真实物体会改变色度比、不会被误纳），并限定在臂的近邻域内。
6. **高饱和保护（用户口径：尽量保护被夹持物体）**：臂 mask 内的高饱和连通子区域
   （被夹起的红/蓝方块等）从 mask 里挖掉、保留原像素。低饱和被夹物（粉棕棍、
   白按钮）与臂不可分，保护不了，属已知口径。

## 依赖纪律（tests/lightweight/test_arm_removal_logic.py 用 AST 钉死）

- 只准 import numpy / cv2 / 标准库。h5py、scipy（仅传递依赖，未声明进 pyproject）、
  ManiSkill、仓库内模块一律禁止。
- 源码不得出现任何仿真分割相关标识符——「纯 CV 定位」这条口径靠测试在结构上兑现，
  不靠人记住。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class ArmRemovalParams:
    """全部可调参数。默认值来自在 v21-16env 现成数据上的原型实测。"""

    # --- 背景板 ---
    plate_mode: str = "mode"           # "mode"（众数，默认）/ "median"（仅对照实验用）
    plate_min_fraction: float = 0.15   # 众数占比低于此值的像素记入告警计数（不改控制流）
    # --- 前景 ---
    diff_threshold: int = 8            # 与背景板逐通道最大绝对差的阈值
    close_iter: int = 1                # 前景 3×3 闭运算次数
    # --- 锚定 ---
    border_sides: str = "top,left,right"  # 参与锚定的画面边；bottom 默认关（桌面延伸到底边）
    border_band: int = 3               # 边带宽度（行/列数）
    # --- 臂外观模型 ---
    occluder_sat_k: float = 3.0        # S 阈值 = median + k·MAD + 6
    occluder_sat_cap: float = 20.0     # S 阈值硬上限（臂 S≈4 / 地面带 S≈23 / 桌面 S≈160）
    occluder_val_pct: float = 2.0      # V 下限取臂核心像素的该分位
    # --- 静止底座区 ---
    static_occluder_mode: str = "learned"  # "learned" / "box"（手动 ROI 兜底）/ "off"
    static_occluder_box: tuple[int, int, int, int] | None = None  # box 模式的 [r0,r1,c0,c1)
    occluder_top_rows: int = 32        # 候选连通域必须触及的顶部行带
    occluder_max_width: int = 128      # 宽度上限（排除整条地面棋盘带）
    occluder_val_cap: float = 160.0    # 底座检测亮度下限的上限：该下限只为排除暗色
                                       # 背景物，不得高到把灰白底座本身挡在外面
                                       # （外观模型 v_min 可能被采样偏差推高，见单测）
    occluder_area_min: int = 60
    occluder_area_max: int = 6000      # 语义是「顶部常驻无彩区」（底座+臂 home 长驻
                                       # 痕迹连成的整块，PatternLock 实测可达数千像素），
                                       # 不是纯底座；超限说明检测失控（半张图无彩）。
                                       # 曾试过按众数占比把污染区从候选里剔掉、只留纯
                                       # 底座——被臂划过的底座本体 fraction 同样偏低，
                                       # 会被一并剔碎成 None，弃用
    occluder_dilate: int = 2
    # --- 臂长驻污染区（stuck）规则 ---
    stuck_fill: bool = True            # 背景板被臂长驻污染的区域里，当前帧仍是臂色的
                                       # 像素并入前景候选（修臂根黑洞与漏检）
    stuck_max_mode_fraction: float = 0.95  # 众数占比低于此值才视为污染区（保护恒定的
                                           # 无彩静止物：白按钮、底座本体）
    # --- 碎片吸附 ---
    absorb_distance: float = 12.0      # 碎片到臂主体的最大距离（px）
    absorb_arm_ratio: float = 0.60     # 碎片内「臂色」（S≤2·s_thr 且 V≥v_min）像素占比下限
    absorb_max_area: int = 1500
    # --- 阴影 ---
    shadow_mode: str = "adjacent"      # "adjacent"（限臂邻域，默认）/ "global" / "off"
    shadow_ratio_lo: float = 0.55      # 比值均值下限（更暗的多半是真实物体而非阴影）
    shadow_ratio_hi: float = 0.97
    shadow_chroma_tol: float = 0.06    # 通道比值标准差上限（等比压暗 ⇒ 各通道比值一致）
    shadow_dilate: int = 6             # 阴影只在臂主体膨胀该半径的邻域内认定
    # --- 高饱和保护（被夹持物体） ---
    protect_saturated: bool = True
    protect_sat_min: int = 60          # OpenCV S 域（0–255）
    protect_min_area: int = 20
    # --- 收尾 ---
    arm_dilate: int = 2                # 最终 mask 3×3 膨胀次数（吞掉边缘混色）

    @property
    def border_side_set(self) -> frozenset[str]:
        return frozenset(part.strip() for part in self.border_sides.split(",") if part.strip())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArmRemovalParams":
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"未知参数：{sorted(unknown)}")
        payload = dict(data)
        if payload.get("static_occluder_box") is not None:
            payload["static_occluder_box"] = tuple(int(v) for v in payload["static_occluder_box"])
        return cls(**payload)

    @classmethod
    def from_json(cls, path: Path) -> "ArmRemovalParams":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


# 3×3 结构元，全模块唯一的形态学核
_KERNEL3 = np.ones((3, 3), np.uint8)


def _close(mask: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0:
        return mask
    return cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, _KERNEL3, iterations=iterations).astype(bool)


def _dilate(mask: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0:
        return mask
    return cv2.dilate(mask.astype(np.uint8), _KERNEL3, iterations=iterations).astype(bool)


def _erode(mask: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0:
        return mask
    return cv2.erode(mask.astype(np.uint8), _KERNEL3, iterations=iterations).astype(bool)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """floodFill 填洞：从某个确定是背景的角点灌水，未被灌到的背景就是洞。

    臂内部偶有像素恰好与背景板同色（白臂压在白按钮上），不填洞会在臂身上留针孔。
    种子取四角里第一个非前景角（桌面延伸到画面下缘，右下角几乎永远是背景）；
    四角全是前景时放弃填洞（几乎不可能发生，放弃也只是少填几个针孔）。
    """
    height, width = mask.shape
    seed = None
    for corner in ((height - 1, width - 1), (height - 1, 0), (0, width - 1), (0, 0)):
        if not mask[corner]:
            seed = corner
            break
    if seed is None:
        return mask
    flood = (mask.astype(np.uint8) * 255).copy()
    ff_mask = np.zeros((height + 2, width + 2), np.uint8)
    cv2.floodFill(flood, ff_mask, (seed[1], seed[0]), 255)
    holes = flood == 0
    return mask | holes


def segment_bounds(phase_flags: np.ndarray) -> list[tuple[int, int]]:
    """按相位标志翻转切段，返回左闭右开区间列表。

    demo 相位与执行相位之间发生过场景重置、物体摆位不同，背景板必须分段建
    （实测 VideoPlaceOrder 940+260 帧两相位，单一背景板会被 demo 段主导）。
    """
    flags = np.asarray(phase_flags, dtype=bool)
    if flags.size == 0:
        return []
    change_points = np.flatnonzero(flags[1:] != flags[:-1]) + 1
    bounds = [0, *change_points.tolist(), flags.size]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def build_background_plate(frames: np.ndarray, params: ArmRemovalParams) -> tuple[np.ndarray, np.ndarray]:
    """逐像素求时间轴众数背景板。返回 (板 (H,W,3) uint8, 众数占比 (H,W) float32)。"""
    n, height, width, _ = frames.shape
    if params.plate_mode == "median":
        plate = np.median(frames.astype(np.float32), axis=0).round().astype(np.uint8)
        return plate, np.ones((height, width), np.float32)
    if params.plate_mode != "mode":
        raise ValueError(f"未知 plate_mode：{params.plate_mode}")

    pixels = height * width
    packed = (
        (frames[..., 0].astype(np.uint32) << 16)
        | (frames[..., 1].astype(np.uint32) << 8)
        | frames[..., 2].astype(np.uint32)
    ).reshape(n, pixels)

    mode_packed = np.empty(pixels, np.uint32)
    mode_count = np.empty(pixels, np.int32)
    chunk = 4096  # 分块控内存：块内峰值 ≈ N×4096×16B ≈ 20MB（N=1200）
    positions = np.arange(n, dtype=np.int32)[:, None]
    for start in range(0, pixels, chunk):
        block = np.sort(packed[:, start : start + chunk], axis=0)
        # 最长游程即众数：change 标记游程起点，run_start 累计到当前行的游程起点，
        # run_len 是到当前行为止的游程长度，argmax 落在最长游程的末行上。
        change = np.empty_like(block, dtype=bool)
        change[0] = True
        change[1:] = block[1:] != block[:-1]
        pos = np.broadcast_to(positions, block.shape)
        run_start = np.where(change, pos, 0)
        run_start = np.maximum.accumulate(run_start, axis=0)
        run_len = pos - run_start + 1
        best = np.argmax(run_len, axis=0)
        cols = np.arange(block.shape[1])
        mode_packed[start : start + chunk] = block[best, cols]
        mode_count[start : start + chunk] = run_len[best, cols]

    plate = np.empty((pixels, 3), np.uint8)
    plate[:, 0] = (mode_packed >> 16) & 0xFF
    plate[:, 1] = (mode_packed >> 8) & 0xFF
    plate[:, 2] = mode_packed & 0xFF
    fraction = (mode_count.astype(np.float32) / float(n)).reshape(height, width)
    return plate.reshape(height, width, 3), fraction


def _foreground(frame: np.ndarray, plate: np.ndarray, params: ArmRemovalParams) -> np.ndarray:
    diff = np.abs(frame.astype(np.int16) - plate.astype(np.int16)).max(axis=-1)
    mask = diff > params.diff_threshold
    mask = _close(mask, params.close_iter)
    return _fill_holes(mask)


def _border_seed(shape: tuple[int, int], params: ArmRemovalParams) -> np.ndarray:
    """锚定边带。臂只会从画面边缘探入，触边是它与桌面上任务物体最本质的区别。"""
    height, width = shape
    band = params.border_band
    seed = np.zeros(shape, dtype=bool)
    sides = params.border_side_set
    if "top" in sides:
        seed[:band, :] = True
    if "bottom" in sides:
        seed[height - band :, :] = True
    if "left" in sides:
        seed[:, :band] = True
    if "right" in sides:
        seed[:, width - band :] = True
    return seed


def _anchored_components(foreground: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """前景里与锚定种子相触的连通域并集。"""
    count, labels = cv2.connectedComponents(foreground.astype(np.uint8), connectivity=8)
    if count <= 1:
        return np.zeros_like(foreground)
    touched = np.unique(labels[seed & foreground])
    touched = touched[touched != 0]
    if touched.size == 0:
        return np.zeros_like(foreground)
    return np.isin(labels, touched)


# 外观模型采样像素低于此数视为「学习失败」，触发用底座区增强种子的二轮学习
_MIN_APPEARANCE_PIXELS = 200


def learn_arm_appearance(
    frames: np.ndarray,
    foregrounds: np.ndarray,
    seed: np.ndarray,
    params: ArmRemovalParams,
) -> tuple[float, float, int]:
    """从「触种子前景连通域的腐蚀核心」学臂的无彩外观模型。

    返回 (s_thr, v_min, 采样像素数)。核心像素不足时退化为硬上限（记入 stats，
    由目视把关）。median+MAD 而不是高分位：臂夹着高饱和物体时分位数会被污染。
    """
    sat_samples: list[np.ndarray] = []
    val_samples: list[np.ndarray] = []
    for index in range(frames.shape[0]):
        core = _erode(_anchored_components(foregrounds[index], seed), 2)
        if not core.any():
            continue
        hsv = cv2.cvtColor(frames[index], cv2.COLOR_RGB2HSV)
        sat_samples.append(hsv[..., 1][core])
        val_samples.append(hsv[..., 2][core])
    if not sat_samples:
        return float(params.occluder_sat_cap), 40.0, 0
    sat = np.concatenate(sat_samples).astype(np.float64)
    val = np.concatenate(val_samples).astype(np.float64)
    med = float(np.median(sat))
    mad = float(np.median(np.abs(sat - med))) * 1.4826
    s_thr = min(med + params.occluder_sat_k * mad + 6.0, float(params.occluder_sat_cap))
    v_min = float(np.percentile(val, params.occluder_val_pct))
    return s_thr, v_min, int(sat.size)


def detect_static_occluder(
    plate: np.ndarray,
    s_thr: float,
    v_min: float,
    params: ArmRemovalParams,
) -> tuple[np.ndarray, dict[str, Any]]:
    """在背景板上检测顶部常驻无彩区（底座 + 臂 home 长驻痕迹连成的整块）。

    背景差分对全程不动的底座天然失明，这里用「无彩且够亮 + 触顶 + 宽度/面积上限」
    在背景板上找它。该区整块恒红：那里的背景信息已被臂污染、无法恢复，恒红比
    「臂离开时露出的假背景闪烁误差分」视觉上更稳、语义上更诚实。白色任务物体
    （按钮座、白方块）靠「必须触顶」排除，地面棋盘带靠宽度上限排除。
    超限候选直接拒绝并记入 stats（红遮罩是可视化产物，误检/漏检都会在目视里
    一眼暴露，不采取 raise 中断整批的策略）。
    """
    height, width = plate.shape[:2]
    info: dict[str, Any] = {"status": "off", "bbox": None, "area": 0, "rejected_oversize": 0}
    if params.static_occluder_mode == "off":
        return np.zeros((height, width), bool), info
    if params.static_occluder_mode == "box":
        if params.static_occluder_box is None:
            raise ValueError("static_occluder_mode=box 时必须提供 static_occluder_box")
        r0, r1, c0, c1 = params.static_occluder_box
        region = np.zeros((height, width), bool)
        region[r0:r1, c0:c1] = True
        info.update(status="box", bbox=[int(r0), int(r1), int(c0), int(c1)], area=int(region.sum()))
        return region, info
    if params.static_occluder_mode != "learned":
        raise ValueError(f"未知 static_occluder_mode：{params.static_occluder_mode}")

    hsv = cv2.cvtColor(plate, cv2.COLOR_RGB2HSV)
    v_floor = min(v_min, float(params.occluder_val_cap))
    achromatic = (hsv[..., 1] <= s_thr) & (hsv[..., 2] >= v_floor)
    achromatic = _close(achromatic, 1)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(achromatic.astype(np.uint8), connectivity=8)
    accepted = np.zeros((height, width), bool)
    rejected_oversize = 0
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        touches_top = y < params.occluder_top_rows
        if not touches_top:
            continue
        if w > params.occluder_max_width or area > params.occluder_area_max:
            rejected_oversize += 1
            continue
        if area < params.occluder_area_min:
            continue
        accepted |= labels == label
    info["rejected_oversize"] = rejected_oversize
    if not accepted.any():
        info["status"] = "none"
        return accepted, info
    region = _dilate(_fill_holes(accepted), params.occluder_dilate)
    rows, cols = np.nonzero(region)
    info.update(
        status="ok",
        bbox=[int(rows.min()), int(rows.max()) + 1, int(cols.min()), int(cols.max()) + 1],
        area=int(region.sum()),
    )
    return region, info


def _absorb_fragments(
    main: np.ndarray,
    foreground: np.ndarray,
    hsv: np.ndarray,
    s_thr: float,
    v_min: float,
    params: ArmRemovalParams,
) -> tuple[np.ndarray, int]:
    """吸附被任务物体切断的臂碎片：距主体近、臂色一致、面积小，三条全中才吸。"""
    leftover = foreground & ~main
    if not leftover.any():
        return main, 0
    # distanceTransform 算的是「到零像素的距离」，把主体设为 0、其余设为 1
    dist = cv2.distanceTransform((~main).astype(np.uint8), cv2.DIST_L2, 3)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(leftover.astype(np.uint8), connectivity=8)
    armlike = (hsv[..., 1] <= 2.0 * s_thr) & (hsv[..., 2] >= v_min)
    absorbed = 0
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area > params.absorb_max_area:
            continue
        component = labels == label
        if float(dist[component].min()) > params.absorb_distance:
            continue
        ratio = float(armlike[component].mean())
        if ratio < params.absorb_arm_ratio:
            continue
        main = main | component
        absorbed += 1
    return main, absorbed


def _shadow_mask(
    frame: np.ndarray,
    plate: np.ndarray,
    foreground: np.ndarray,
    main: np.ndarray,
    params: ArmRemovalParams,
) -> np.ndarray:
    """阴影 = 背景的逐通道等比压暗：比值均值落在区间内且通道间比值一致。"""
    if params.shadow_mode == "off":
        return np.zeros_like(main)
    ratio = (frame.astype(np.float32) + 1.0) / (plate.astype(np.float32) + 1.0)
    mean = ratio.mean(axis=-1)
    std = ratio.std(axis=-1)
    shadow = (
        (mean >= params.shadow_ratio_lo)
        & (mean <= params.shadow_ratio_hi)
        & (std < params.shadow_chroma_tol)
        & foreground
    )
    if params.shadow_mode == "adjacent":
        shadow &= _dilate(main, params.shadow_dilate)
    elif params.shadow_mode != "global":
        raise ValueError(f"未知 shadow_mode：{params.shadow_mode}")
    return shadow


def _protect_saturated_regions(
    mask: np.ndarray,
    candidate_base: np.ndarray,
    hsv: np.ndarray,
    params: ArmRemovalParams,
) -> tuple[np.ndarray, int]:
    """从臂 mask 里挖掉高饱和连通子区域（被夹持的彩色物体），保留原像素。

    候选域必须限定在 ``candidate_base``（膨胀前的臂主体、且排除阴影）：
    - 桌面阴影是「等比压暗的棕色」，饱和度不降，放进候选会把阴影系统性
      「保护」回来，与「连阴影一起删」的口径直接冲突；
    - 最终 mask 的膨胀扩张带里是臂边缘与桌面的混色像素，同样高饱和，
      放进候选会在臂边缘挖出一圈残留。
    """
    if not params.protect_saturated:
        return mask, 0
    candidate = candidate_base & (hsv[..., 1] >= params.protect_sat_min)
    if not candidate.any():
        return mask, 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate.astype(np.uint8), connectivity=8)
    protected = np.zeros_like(mask)
    for label in range(1, count):
        if int(stats[label, cv2.CC_STAT_AREA]) >= params.protect_min_area:
            protected |= labels == label
    if not protected.any():
        return mask, 0
    return mask & ~protected, int(protected.sum())


def compute_arm_masks(
    frames: np.ndarray,
    phase_flags: np.ndarray,
    params: ArmRemovalParams,
) -> tuple[np.ndarray, dict[str, Any]]:
    """主入口：逐帧臂（含阴影）mask。

    frames: (N,H,W,3) uint8 RGB；phase_flags: (N,) bool（demo/执行相位标志）。
    返回 (masks (N,H,W) bool, stats 字典（全部可 JSON 序列化）)。
    """
    frames = np.ascontiguousarray(frames)
    if frames.ndim != 4 or frames.shape[-1] != 3 or frames.dtype != np.uint8:
        raise ValueError(f"frames 必须是 (N,H,W,3) uint8，拿到 {frames.shape} {frames.dtype}")
    n = frames.shape[0]
    phase_flags = np.asarray(phase_flags, dtype=bool)
    if phase_flags.shape != (n,):
        raise ValueError(f"phase_flags 形状 {phase_flags.shape} 与帧数 {n} 不符")

    masks = np.zeros(frames.shape[:3], dtype=bool)
    removed_fraction: list[float] = []
    segments_stats: list[dict[str, Any]] = []
    total_pixels = frames.shape[1] * frames.shape[2]
    absorbed_total = 0
    shadow_total = 0
    protected_total = 0

    for seg_start, seg_end in segment_bounds(phase_flags):
        seg_frames = frames[seg_start:seg_end]
        plate, mode_fraction = build_background_plate(seg_frames, params)
        foregrounds = np.stack(
            [_foreground(seg_frames[i], plate, params) for i in range(seg_frames.shape[0])]
        )
        border = _border_seed(frames.shape[1:3], params)
        s_thr, v_min, appearance_pixels = learn_arm_appearance(seg_frames, foregrounds, border, params)
        occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, params)
        # 二轮学习：臂根常驻画面顶部时，背景板在浅行就是臂色、差分为零，纯边带
        # 锚定会采不到核心样本。此时用检出的底座/常驻区增强种子重学一遍，并用
        # 学到的更紧阈值重检底座区。
        if appearance_pixels < _MIN_APPEARANCE_PIXELS and occluder.any():
            retry = learn_arm_appearance(seg_frames, foregrounds, border | _dilate(occluder, 1), params)
            if retry[2] > appearance_pixels:
                s_thr, v_min, appearance_pixels = retry
                occluder, occluder_info = detect_static_occluder(plate, s_thr, v_min, params)
        seed = border | _dilate(occluder, 1)

        # 臂长驻污染区：背景板呈臂色（无彩）且时间不稳定的像素。背景差分在这里
        # 天然失明——臂回到常驻位姿时与板同色（黑洞漏检），臂离开时露出的真背景
        # 反而差分大。当前帧仍是臂色的污染区像素并入前景候选（由锚定的连通性
        # 把关）；露出真背景的误差分保持「多删」——本链路口径是删干净优先。
        plate_hsv = cv2.cvtColor(plate, cv2.COLOR_RGB2HSV)
        v_floor = min(v_min, float(params.occluder_val_cap))
        stuck_zone = (
            (plate_hsv[..., 1] <= s_thr)
            & (plate_hsv[..., 2] >= v_floor)
            & (mode_fraction < params.stuck_max_mode_fraction)
            if params.stuck_fill
            else np.zeros(plate.shape[:2], bool)
        )

        for offset in range(seg_frames.shape[0]):
            frame = seg_frames[offset]
            hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
            fg = foregrounds[offset]
            if params.stuck_fill and stuck_zone.any():
                # 臂色判据放宽到 max(2·s_thr, 25) 并放低亮度下限：要把黑色关节
                # 与地面带亮度的臂段都涵盖进来；误纳由「必须落在污染区内」兜住
                frame_armlike = (hsv[..., 1] <= max(2.0 * s_thr, 25.0)) & (hsv[..., 2] >= 25)
                fg = fg | (stuck_zone & frame_armlike)
            main = _anchored_components(fg, seed) | occluder
            main, absorbed = _absorb_fragments(main, fg, hsv, s_thr, v_min, params)
            absorbed_total += absorbed
            shadow = _shadow_mask(frame, plate, fg, main, params)
            shadow_total += int(shadow.sum())
            final = _dilate(main | shadow, params.arm_dilate)
            final, protected = _protect_saturated_regions(final, main & ~shadow, hsv, params)
            protected_total += protected
            masks[seg_start + offset] = final
            removed_fraction.append(float(final.sum()) / total_pixels)

        segments_stats.append(
            {
                "start": int(seg_start),
                "end": int(seg_end),
                "phase_is_video_demo": bool(phase_flags[seg_start]),
                "plate_mode_fraction_min": float(mode_fraction.min()),
                "plate_mode_fraction_median": float(np.median(mode_fraction)),
                "plate_unreliable_pixels": int((mode_fraction < params.plate_min_fraction).sum()),
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
        "shadow_pixel_total": int(shadow_total),
        "protected_pixel_total": int(protected_total),
    }
    return masks, stats


RED = np.array([255, 0, 0], dtype=np.uint8)


def apply_red_mask(frames: np.ndarray, masks: np.ndarray) -> np.ndarray:
    """mask 处涂纯红 (255,0,0)，其余像素与输入逐位相同。绝不就地改。"""
    out = frames.copy()
    out[masks] = RED
    return out
