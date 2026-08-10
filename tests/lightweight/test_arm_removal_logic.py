"""v3-claude 纯 CV 删臂模块的纯逻辑把关测试。

覆盖三类不需要仿真也能验证、但错了会静默毁掉整批可视化产物的事：

1. **口径防火墙（AST + 文本）**：``arm_removal.py`` 只准 import numpy / cv2 / 标准库，
   且源码不得出现任何仿真分割相关标识符——「纯 CV 定位、仿真真值不参与」这条用户
   口径靠测试在结构上兑现，不靠人记住。
2. **合成序列端到端**：静止渐变背景 + 顶部灰底座 + 移动灰臂 + 等比压暗阴影 +
   静止高饱和红方块 + 臂内高饱和被夹物。断言臂/阴影/底座全部入 mask、红方块与
   桌面绝不入 mask、protect 挖回被夹物、红遮罩应用后非 mask 像素逐位不变。
3. **关键子构件**：众数背景板在「遮挡超半程」下仍返回背景真值（这是选众数不选
   中值的回归护栏）、相位切段边界正确、退化输入（单帧 / 全常数 / 底座检测为空）不炸。

本文件是纯 numpy / cv2 计算，不需要 GPU 也不需要仿真，进默认档。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from tests._shared.repo_paths import find_repo_root

pytestmark = [pytest.mark.lightweight]

MODULE_RELATIVE_PATH = "scripts/data-generation-v3-claude/arm_removal.py"


def _load_module(module_name: str, relative_path: str):
    repo_root = find_repo_root(__file__)
    module_path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # 必须先注册进 sys.modules 再执行：@dataclass 装饰器会通过 cls.__module__
    # 回查 sys.modules 来解析类型注解，模块不在表里就会挂
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


arm_mod = _load_module("arm_removal_under_test", MODULE_RELATIVE_PATH)


def _module_source() -> str:
    return (find_repo_root(__file__) / MODULE_RELATIVE_PATH).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 一、口径防火墙
# ---------------------------------------------------------------------------

ALLOWED_TOP_IMPORTS = {
    "numpy",
    "cv2",
    # 标准库
    "json",
    "math",
    "dataclasses",
    "typing",
    "pathlib",
    "__future__",
}

# 「seg」裸词根会误伤合法的相位切段概念（segment_bounds），这里精确到仿真分割
# 相关的完整词根；h5py/scipy 只在 AST 标识符与 import 层禁（docstring 里描述纪律
# 本身会提到它们，文本级全禁会误伤）。
FORBIDDEN_IDENTIFIER_FRAGMENTS = ("segmentation", "seg_id", "id_map", "mani_skill", "robomme", "h5py", "scipy")
FORBIDDEN_TEXT_FRAGMENTS = ("segmentation", "seg_id", "id_map")


def test_import_whitelist():
    """arm_removal.py 只准 import numpy / cv2 / 标准库——依赖纪律靠测试钉死。"""
    tree = ast.parse(_module_source())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top in ALLOWED_TOP_IMPORTS, f"禁止 import {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            assert top in ALLOWED_TOP_IMPORTS, f"禁止 from {node.module} import ..."


def test_simulation_ground_truth_firewall():
    """源码不得出现仿真分割相关标识符（AST 标识符 + 源文本双保险）。"""
    source = _module_source()
    lowered = source.lower()
    for fragment in FORBIDDEN_TEXT_FRAGMENTS:
        assert fragment not in lowered, f"arm_removal.py 出现禁用词根：{fragment}"
    tree = ast.parse(source)
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.arg):
            name = node.arg
        if name is not None:
            for fragment in FORBIDDEN_IDENTIFIER_FRAGMENTS:
                assert fragment not in name.lower(), f"标识符 {name} 含禁用词根 {fragment}"


# ---------------------------------------------------------------------------
# 二、合成序列端到端
# ---------------------------------------------------------------------------

H = W = 64
N = 20
BASE_ROWS = slice(0, 9)
BASE_COLS = slice(28, 37)
ARM_COLS = slice(26, 39)
SHADOW_COLS = slice(39, 41)
# 红方块放在臂扫掠区（最深 row 40、dilate/阴影边缘至多蹭到 row41/col42）之外留安全边距
CUBE_ROWS = slice(46, 54)
CUBE_COLS = slice(46, 54)
HELD_ROWS = slice(20, 26)
HELD_COLS = slice(30, 36)
CUBE_COLOR = np.array([200, 30, 30], np.uint8)      # 高饱和红（静止任务物体）
HELD_COLOR = np.array([30, 60, 220], np.uint8)      # 高饱和蓝（被夹持物）
ARM_COLOR = np.array([200, 200, 205], np.uint8)     # 灰白臂
BASE_COLOR = np.array([200, 200, 200], np.uint8)    # 灰白底座


def _background() -> np.ndarray:
    """行向渐变的棕色桌面 + 顶部 6 行灰色地面带（模拟真实画面的光泽渐变）。"""
    bg = np.zeros((H, W, 3), np.uint8)
    rows = np.arange(H, dtype=np.float32)
    bg[..., 0] = (120 + rows * 0.8)[:, None].astype(np.uint8)
    bg[..., 1] = (80 + rows * 0.4)[:, None].astype(np.uint8)
    bg[..., 2] = 50
    bg[:6, :] = (128, 128, 128)
    return bg


def _arm_heights() -> list[int]:
    """臂长随时间 8→40→8 变化，保证每个被臂扫过的像素多数帧是背景。"""
    ups = np.linspace(8, 40, N // 2).round().astype(int)
    downs = np.linspace(40, 8, N - N // 2).round().astype(int)
    return [*ups.tolist(), *downs.tolist()]


def _synthetic_sequence(with_held_object: bool = True) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """返回 (frames, 臂真值掩码（含底座与阴影列）, 背景真值)。"""
    bg = _background()
    bg[CUBE_ROWS, CUBE_COLS] = CUBE_COLOR
    frames = np.empty((N, H, W, 3), np.uint8)
    truth = np.zeros((N, H, W), bool)
    for t, height in enumerate(_arm_heights()):
        frame = bg.copy()
        frame[BASE_ROWS, BASE_COLS] = BASE_COLOR
        # 臂色逐帧上下波动（真实臂亮度随姿态双向变化），幅度要超过 diff_threshold；
        # 波动必须双向：全部向上会让外观模型学出的 V 下限高过底座亮度，
        # 底座/常驻区检测失明后臂根恒驻区就没了兜底
        frame[:height, ARM_COLS] = (ARM_COLOR.astype(np.int16) + ((t % 5) - 2) * 7).astype(np.uint8)
        truth[t, :height, ARM_COLS] = True
        truth[t, BASE_ROWS, BASE_COLS] = True
        # 阴影：臂尖端附近右侧两列等比压暗，跟着臂尖移动（真实阴影不会在同一
        # 像素长驻——长驻阴影值会成为该像素的时间众数、被背景板吸收，那类
        # 「臂根长驻阴影」本就属于已知残留口径，不进查全断言）；因子逐帧微变
        factor = 0.78 + 0.01 * (t % 5)
        shadow_top = max(0, height - 6)
        shadow = (frame[shadow_top:height, SHADOW_COLS].astype(np.float32) * factor).astype(np.uint8)
        frame[shadow_top:height, SHADOW_COLS] = shadow
        truth[t, shadow_top:height, SHADOW_COLS] = True
        if with_held_object and height > HELD_ROWS.stop:
            frame[HELD_ROWS, HELD_COLS] = HELD_COLOR
        frames[t] = frame
    return frames, truth, bg


def _params(**overrides):
    payload = {
        "occluder_area_min": 40,    # 合成底座 9×9=81 像素，放宽下限
        "occluder_max_width": 32,   # 64 宽合成画幅里排除全宽地面带（默认 128 为 256 宽设计）
        "shadow_dilate": 3,
        "arm_dilate": 1,
    }
    payload.update(overrides)
    return arm_mod.ArmRemovalParams.from_dict(payload)


def test_synthetic_end_to_end():
    # 不放被夹物：protect 会把臂内高饱和区从 mask 挖掉，与 100% 查全断言相斥，
    # 被夹物的行为由下面的 protect 专项测试单独覆盖
    frames, truth, bg = _synthetic_sequence(with_held_object=False)
    phase = np.zeros(N, bool)
    masks, stats = arm_mod.compute_arm_masks(frames, phase, _params())

    # 臂+底座+阴影全部入 mask（查全率 100%）
    covered = masks & truth
    assert covered.sum() == truth.sum(), "臂/底座/阴影真值像素必须全部被 mask 覆盖"

    # 静止红方块与远处桌面绝不入 mask
    assert not masks[:, CUBE_ROWS, CUBE_COLS].any(), "静止高饱和红方块被误删"
    assert not masks[:, 55:, :20].any(), "远离臂的桌面区域被误删"

    # 顶部常驻无彩区（底座+臂根长驻痕迹连成的整块）必须检出并覆盖底座真值区
    occluder = stats["segments"][0]["static_occluder"]
    assert occluder["status"] == "ok"
    r0, r1, c0, c1 = occluder["bbox"]
    assert r0 <= 1 and r1 >= 8 and c0 <= 29 and c1 >= 36, f"常驻区 bbox 不覆盖底座真值：{occluder['bbox']}"


def test_protect_saturated_held_object():
    """臂内高饱和被夹物必须被 protect 挖回（用户口径：尽量保护高饱和物体）。"""
    frames, _, _ = _synthetic_sequence(with_held_object=True)
    phase = np.zeros(N, bool)
    masks, stats = arm_mod.compute_arm_masks(frames, phase, _params())
    held_frames = [t for t, h in enumerate(_arm_heights()) if h > HELD_ROWS.stop]
    assert held_frames, "合成序列必须存在被夹持帧"
    for t in held_frames:
        assert not masks[t, HELD_ROWS, HELD_COLS].any(), f"t={t} 被夹持高饱和物体未被保护"
    assert stats["protected_pixel_total"] > 0

    # 对照：关掉 protect 时被夹物应随臂一起入 mask
    masks_off, _ = arm_mod.compute_arm_masks(frames, phase, _params(protect_saturated=False))
    t = held_frames[0]
    assert masks_off[t, HELD_ROWS, HELD_COLS].all(), "关 protect 后被夹物应整体入 mask"


def test_apply_red_mask_bit_exact():
    frames, _, _ = _synthetic_sequence()
    phase = np.zeros(N, bool)
    masks, _ = arm_mod.compute_arm_masks(frames, phase, _params())
    red = arm_mod.apply_red_mask(frames, masks)
    assert np.array_equal(red[masks], np.broadcast_to(arm_mod.RED, red[masks].shape)), "mask 处必须是纯红"
    assert np.array_equal(red[~masks], frames[~masks]), "非 mask 像素必须与输入逐位相同"
    assert red is not frames and red.base is not frames, "禁止就地修改输入帧"


# ---------------------------------------------------------------------------
# 三、关键子构件与退化输入
# ---------------------------------------------------------------------------

def test_mode_plate_beats_median_under_long_occlusion():
    """某像素 70% 帧是散值、30% 帧是固定背景值 → 众数必须返回背景值。"""
    rng = np.random.default_rng(0)
    n = 30
    frames = np.zeros((n, 2, 2, 3), np.uint8)
    frames[:] = (10, 20, 30)
    occluded = rng.choice(n, size=int(n * 0.7), replace=False)
    for rank, t in enumerate(sorted(occluded)):
        # 散值逐帧不同（模拟臂扫过时颜色随姿态变化）
        frames[t, 0, 0] = (100 + rank, 150, 200 - rank)
    plate, fraction = arm_mod.build_background_plate(frames, _params())
    assert tuple(plate[0, 0]) == (10, 20, 30), "长时遮挡下众数板必须返回背景真值"
    assert abs(fraction[0, 0] - 0.3) < 0.05


def test_segment_bounds():
    flags = np.array([True] * 5 + [False] * 7 + [True] * 3)
    assert arm_mod.segment_bounds(flags) == [(0, 5), (5, 12), (12, 15)]
    assert arm_mod.segment_bounds(np.zeros(4, bool)) == [(0, 4)]
    assert arm_mod.segment_bounds(np.zeros(0, bool)) == []


def test_degenerate_inputs_do_not_crash():
    params = _params()
    # 全常数序列：无前景、无底座候选 → mask 全空
    constant = np.full((5, H, W, 3), 90, np.uint8)
    masks, stats = arm_mod.compute_arm_masks(constant, np.zeros(5, bool), params)
    assert not masks.any()
    assert stats["segments"][0]["static_occluder"]["status"] in ("none", "ok")
    # 单帧
    frames, _, _ = _synthetic_sequence()
    masks_single, _ = arm_mod.compute_arm_masks(frames[:1], np.zeros(1, bool), params)
    assert masks_single.shape == (1, H, W)
    # 底座检测关闭
    masks_off, stats_off = arm_mod.compute_arm_masks(frames, np.zeros(N, bool), _params(static_occluder_mode="off"))
    assert stats_off["segments"][0]["static_occluder"]["status"] == "off"
