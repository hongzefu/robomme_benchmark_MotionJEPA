"""v4.1 出图链路（颜色分布 + 分割走查）的逻辑测试（合成数据，秒级，不碰任何 h5 产物）。

出图脚本本身不产生数据，但它们**重算了两件生产路径上的事**，一旦算歪，图上画的就不是
真实链路——这才是本文件要护住的东西：

1. `color_distribution.decide` 在颜色表上直接复算判决（`ColorModel.classify` 吃的是图像、
   还要处理未见色，不方便直接用）。它必须与 `classify` 在同一批颜色上**逐位一致**，
   veto / noveto 两版都要一致。
2. `segmentation_walkthrough.stagewise_masks` 把四条形态学规则拆成逐阶段中间态。它必须与
   `arm_mask_v4.arm_masks_for_episode` 的最终输出**逐位一致**，相位分段也要一致。

外加统计口径的自洽性：像素量口径不许把重叠计数的背景像素重复计一遍；veto 版「判臂颜色上
的真实非臂像素」必须恒等于 0——这是「零物体误标」在颜色阶段的构造性来源。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
V41_DIR = REPO_ROOT / "scripts" / "data-generation-v4.1"

# matplotlib 在无显示环境必须先切 Agg，且要在 color_distribution 被 import 之前生效
pytest.importorskip("matplotlib")


def _load_v41_modules():
    """隔离加载 v4.1 的四个模块，理由同 test_arm_mask_v4_1.py。

    v4 与 v4.1 目录下有同名的 `color_model` / `arm_mask_v4`；谁先 import 谁把名字占住。
    这里把 v4.1 目录顶到 sys.path 最前、清掉同名模块再导入，导完恢复原样，只留本文件
    持有的引用。`color_distribution` 与 `segmentation_walkthrough` 内部还会 import 上面
    两个模块，所以必须在同一个窗口里一起导完。
    """
    names = (
        "color_model",
        "arm_mask_v4",
        "fit_color_model",
        "render_outputs",
        "color_distribution",
        "segmentation_walkthrough",
    )
    saved = {name: sys.modules.pop(name, None) for name in names}
    sys.path.insert(0, str(V41_DIR))
    try:
        loaded = {name: importlib.import_module(name) for name in names}
    finally:
        sys.path.remove(str(V41_DIR))
        for name in names:
            sys.modules.pop(name, None)
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module
    return loaded


_MODULES = _load_v41_modules()
color_model = _MODULES["color_model"]
arm_mask_v4 = _MODULES["arm_mask_v4"]
color_distribution = _MODULES["color_distribution"]
walkthrough = _MODULES["segmentation_walkthrough"]

CLASS_ARM = color_model.CLASS_ARM
CLASS_BACKGROUND = color_model.CLASS_BACKGROUND
CLASS_MIX = color_model.CLASS_MIX
ColorModel = color_model.ColorModel
pack_rgb = color_model.pack_rgb
MaskParams = arm_mask_v4.MaskParams
arm_masks_for_episode = arm_mask_v4.arm_masks_for_episode


def _model(rows: list[tuple[tuple[int, int, int], int, int, int]]) -> ColorModel:
    """按 [(RGB, 背景计数, 混合计数, 臂计数), ...] 造一张升序颜色表。"""
    packed = np.array(
        [pack_rgb(np.array([[list(rgb)]], dtype=np.uint8))[0, 0] for rgb, *_ in rows],
        dtype=np.uint32,
    )
    counts = np.array([[bg, mix, arm] for _, bg, mix, arm in rows], dtype=np.int64)
    order = np.argsort(packed)
    return ColorModel(colors=packed[order], counts=counts[order], source={})


# 一张覆盖全部四种情形的小表：臂独有色 / 臂与混合共享色 / 纯背景色 / 物体独有色
TABLE = [
    ((10, 10, 10), 0, 0, 900),  # 臂独有：混合列没见过，veto 也带不走
    ((200, 200, 200), 0, 40, 600),  # 共享灰白：argmax 判臂，但混合见过 → 被否决
    ((30, 60, 90), 5000, 5000, 0),  # 纯背景
    ((240, 120, 20), 0, 3000, 0),  # 只在混合列出现的物体色
    ((77, 77, 77), 10, 12, 300),  # 三列都见过的共享色
]


def test_decide_与_classify_两版逐位一致():
    model = _model(TABLE)
    rgb = color_distribution.unpack_rgb(model.colors).reshape(1, -1, 3)
    for veto in (False, True):
        assert np.array_equal(
            color_distribution.decide(model.counts, veto), model.classify(rgb, veto)[0]
        )


def test_decide_空列时炸掉():
    model = _model([((10, 10, 10), 0, 0, 5)])
    with pytest.raises(ValueError, match="空列"):
        color_distribution.decide(model.counts, True)


def test_unpack_rgb_是_pack_rgb_的逆():
    rgb = np.array(
        [[[0, 0, 0], [255, 255, 255], [12, 200, 7], [1, 2, 3]]], dtype=np.uint8
    )
    assert np.array_equal(color_distribution.unpack_rgb(pack_rgb(rgb).ravel()), rgb[0])


def test_veto_只会把判臂改成混合():
    model = _model(TABLE)
    noveto = color_distribution.decide(model.counts, False)
    veto = color_distribution.decide(model.counts, True)
    changed = noveto != veto
    assert np.all(noveto[changed] == CLASS_ARM)
    assert np.all(veto[changed] == CLASS_MIX)
    # 被翻的恰是「argmax 判臂 且 混合列见过」的那些，一个不多一个不少
    assert np.array_equal(
        changed, (noveto == CLASS_ARM) & (model.counts[:, CLASS_MIX] > 0)
    )


def test_统计口径自洽():
    model = _model(TABLE)
    stats = color_distribution.compute_stats(model)
    # 像素量口径 = 混合列 + 臂列（背景列与混合列是重叠计数，不许三列直接相加）
    assert stats["总像素数"] == int(
        model.counts[:, CLASS_MIX].sum() + model.counts[:, CLASS_ARM].sum()
    )
    for side in ("noveto", "veto"):
        assert sum(stats[side]["各类像素数"].values()) == stats["总像素数"]
    # veto 的构造性保证：判臂的颜色在标定集里一个非臂像素都没有
    assert stats["veto"]["判臂颜色上的真实非臂像素"] == 0
    assert stats["veto"]["颜色阶段精确率上界"] == 1.0
    # noveto 放进来的共享色必然带进非臂像素
    assert stats["noveto"]["判臂颜色上的真实非臂像素"] > 0
    assert stats["veto"]["翻转带走的臂像素"] == int(
        model.counts[:, CLASS_ARM].sum()
    ) - stats["veto"]["判臂颜色上的真实臂像素"]


def _labels(frames: int = 7, size: int = 24) -> list[np.ndarray]:
    """造一段标签图：一条从顶部伸下来的臂 + 一块不触顶的物体色斑 + 一帧闪烁噪点。"""
    labels = []
    for index in range(frames):
        frame = np.full((size, size), CLASS_BACKGROUND, dtype=np.int8)
        frame[0 : 12 + index, 9:15] = CLASS_ARM  # 触顶的臂，逐帧变长
        frame[17:22, 3:9] = CLASS_ARM  # 不触顶的色斑，应被规则 ② 全部删掉
        if index == 3:
            frame[20, 20] = CLASS_ARM  # 单点噪声，应被规则 ① 开运算抹掉
        frame[frame == CLASS_BACKGROUND] = CLASS_BACKGROUND
        labels.append(frame)
    return labels


def test_逐阶段复算与生产路径最终输出逐位一致():
    labels = _labels()
    flags = [False] * 4 + [True] * 3  # 故意跨一次相位边界
    params = MaskParams()
    stages = walkthrough.stagewise_masks(labels, flags, params)
    assert len(stages) == len(walkthrough.STAGE_NAMES)
    for produced, expected in zip(stages[-1], arm_masks_for_episode(labels, flags, params)):
        assert np.array_equal(produced, expected)


def test_逐阶段单调收缩():
    """开运算、触顶连通域、保守收缩三步只许变小或持平；时间平滑是多数表决可能补像素，
    但补进来的会被第 4 条「只保留本帧判臂」扣回去，所以最终 mask 必须是候选的子集。"""
    labels = _labels()
    flags = [False] * 7
    stages = walkthrough.stagewise_masks(labels, flags, MaskParams())
    candidate, opened, topped, _, final = stages
    for smaller, larger in ((opened, candidate), (topped, opened), (final, candidate)):
        for lhs, rhs in zip(smaller, larger):
            assert not (lhs & ~rhs).any()


def test_逐阶段复算按相位分段():
    """相位边界两侧不许互相投票：把第二段整段改成无臂，第一段的臂不能渗过去。"""
    labels = _labels()
    for index in (4, 5, 6):
        labels[index] = np.full_like(labels[index], CLASS_BACKGROUND)
    flags = [False] * 4 + [True] * 3
    stages = walkthrough.stagewise_masks(labels, flags, MaskParams())
    assert not any(mask.any() for mask in stages[-1][4:])
    assert stages[-1][0].any()


def test_逐阶段复算帧数不匹配时炸掉():
    with pytest.raises(ValueError, match="不一致"):
        walkthrough.stagewise_masks(_labels(3), [False, False], MaskParams())


def test_色板与色带不越界():
    rgb = np.array([[10, 20, 30], [200, 100, 50], [255, 255, 255]], dtype=np.uint8)
    swatch = color_distribution._swatch_image(rgb, np.array([2, 0, 1]), 2, 2)
    assert swatch.shape == (2, 2, 3)
    assert np.array_equal(swatch[0, 0], rgb[2])
    bar = color_distribution._weighted_bar(rgb, np.array([1.0, 1.0, 2.0]), width=100)
    assert bar.shape == (1, 100, 3)
    # 权重为 0 的一批颜色不许把色带画成花的
    blank = color_distribution._weighted_bar(rgb, np.zeros(3), width=20)
    assert blank.shape == (1, 20, 3)
