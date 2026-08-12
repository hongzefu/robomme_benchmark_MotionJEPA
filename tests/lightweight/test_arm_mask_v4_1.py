"""v4.1 两分布 + 臂颜色模型与形态学标定的逻辑测试（合成数据，秒级，不碰任何 h5 产物）。

与 test_arm_mask_v4.py 的关系：形态学四条规则与 GT 三类映射的契约原样继承；颜色表部分
按 v4.1 口径重写——三列 =（纯背景，背景∪物体混合，机械臂），判别是**各列归一化似然的
argmax**（类先验不参与）加**混合支撑否决**，未见颜色仍是 UNKNOWN。

覆盖四件事：

1. **GT 映射**（沿用 v4 契约）：`robot_link` 归机械臂、`background_prop` 加 seg_id 0
   归背景、`flow_objects` 归物体、`kind == "tcp"` 归机械臂；未覆盖 seg id 归物体并被
   单独计数。
2. **重叠计数**：背景像素必须同时进列 0 与列 1，物体像素只进列 1，臂像素只进列 2。
3. **判别规则**：归一化似然 argmax 不受类规模（先验）影响；混合支撑否决按「出现过 /
   没出现过」一刀切；未见颜色给 UNKNOWN；空列 fail-loud。
4. **四条形态学规则**：与 v4 逐字相同的行为契约。
"""

from __future__ import annotations

import importlib
import io
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
V41_DIR = REPO_ROOT / "scripts" / "data-generation-v4.1"


def _load_v41_modules():
    """隔离加载 v4.1 的 color_model / arm_mask_v4。

    v4 与 v4.1 的模块同名；若与 test_arm_mask_v4.py 跑在同一个 pytest 会话里，谁先
    import 谁就把名字占住，另一方会静默拿到错误目录的实现。这里把加载过程做成三步：
    暂存并清掉同名模块 → 用 V41_DIR 优先的 sys.path 导入 → 导入完把 sys.modules 与
    sys.path 恢复原样，只留下本文件持有的模块引用。两个测试文件以任意顺序运行都各自
    拿到自己目录的实现。
    """
    saved = {name: sys.modules.pop(name, None) for name in ("color_model", "arm_mask_v4")}
    sys.path.insert(0, str(V41_DIR))
    try:
        color_model = importlib.import_module("color_model")
        arm_mask = importlib.import_module("arm_mask_v4")
    finally:
        sys.path.remove(str(V41_DIR))
        for name in ("color_model", "arm_mask_v4"):
            sys.modules.pop(name, None)
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module
    return color_model, arm_mask


color_model, arm_mask_v4 = _load_v41_modules()

CLASS_ARM = color_model.CLASS_ARM
CLASS_BACKGROUND = color_model.CLASS_BACKGROUND
CLASS_MIX = color_model.CLASS_MIX
CLASS_OBJECT = color_model.CLASS_OBJECT
CLASS_UNKNOWN = color_model.CLASS_UNKNOWN
ColorModel = color_model.ColorModel
accumulate_frames = color_model.accumulate_frames
class_ids_from_setup = color_model.class_ids_from_setup
labels_from_segmentation = color_model.labels_from_segmentation
pack_rgb = color_model.pack_rgb
uncovered_mask = color_model.uncovered_mask

MaskParams = arm_mask_v4.MaskParams
apply_red_mask = arm_mask_v4.apply_red_mask
arm_masks_for_episode = arm_mask_v4.arm_masks_for_episode
arm_masks_for_segment = arm_mask_v4.arm_masks_for_segment
_keep_top_entering = arm_mask_v4._keep_top_entering
_temporal_majority = arm_mask_v4._temporal_majority


def _setup_group(handle: h5py.File, excluded, objects) -> h5py.Group:
    """按真实 h5 的结构造一个 setup group。"""
    setup = handle.create_group("setup")
    group = setup.create_group("flow_excluded")
    for name, reason, seg_id in excluded:
        entry = group.create_group(name)
        entry.create_dataset("reason", data=reason, dtype=h5py.string_dtype("utf-8"))
        entry.create_dataset("seg_id", data=seg_id)
    group = setup.create_group("flow_objects")
    for name, kind, seg_id in objects:
        entry = group.create_group(name)
        entry.create_dataset("kind", data=kind, dtype=h5py.string_dtype("utf-8"))
        entry.create_dataset("seg_id", data=seg_id)
    return setup


@pytest.fixture()
def setup_handle():
    handle = h5py.File(io.BytesIO(), "w")
    yield handle
    handle.close()


def test_GT映射按约定逐字成立(setup_handle):
    setup = _setup_group(
        setup_handle,
        excluded=[
            ("panda_link0__1", "robot_link", 1),
            ("camera_link__15", "robot_link", 15),
            ("table-workspace__16", "background_prop", 16),
            ("ground__17", "background_prop", 17),
        ],
        objects=[
            ("fixed_cube__22", "actor", 22),
            ("peg_head__18", "link", 18),
            ("panda_hand_tcp__11", "tcp", 11),
        ],
    )
    ids = class_ids_from_setup(setup)
    # tcp 是夹爪工具中心点，语义上属于机器人，不能算任务物体
    assert ids["arm"] == {1, 15, 11}
    assert ids["background"] == {0, 16, 17}
    assert ids["object"] == {22, 18}


def test_未知的_reason_直接报错(setup_handle):
    setup = _setup_group(
        setup_handle,
        excluded=[("mystery__9", "something_new", 9)],
        objects=[],
    )
    with pytest.raises(ValueError, match="reason 未知"):
        class_ids_from_setup(setup)


def test_setup_没覆盖的_seg_id_归物体并被单独数出来():
    ids = {"arm": {1}, "background": {0}, "object": {22}}
    segmentation = np.array([[0, 1], [22, 77]], dtype=np.int16)
    labels = labels_from_segmentation(segmentation, ids)
    assert labels[1, 1] == CLASS_OBJECT
    assert uncovered_mask(segmentation, ids).tolist() == [[False, False], [False, True]]


def test_标签图三类各就各位():
    ids = {"arm": {1, 15}, "background": {0, 16}, "object": {22}}
    segmentation = np.array([[0, 1], [22, 16]], dtype=np.int16)
    labels = labels_from_segmentation(segmentation, ids)
    assert labels.tolist() == [
        [CLASS_BACKGROUND, CLASS_ARM],
        [CLASS_OBJECT, CLASS_BACKGROUND],
    ]


def test_pack_rgb_是_24_位无损():
    rgb = np.array([[[0, 0, 0], [255, 255, 255], [1, 2, 3]]], dtype=np.uint8)
    packed = pack_rgb(rgb)
    assert packed.tolist() == [[0, 0xFFFFFF, 0x010203]]


def test_拟合是重叠计数_背景像素同进纯背景列与混合列():
    # 一帧 2×2：背景、物体、臂、背景
    rgb = np.array(
        [[[0, 0, 0], [1, 2, 3]], [[4, 5, 6], [0, 0, 0]]], dtype=np.uint8
    )
    labels = np.array(
        [[CLASS_BACKGROUND, CLASS_OBJECT], [CLASS_ARM, CLASS_BACKGROUND]], dtype=np.int8
    )
    colors, counts = accumulate_frames([(rgb, labels)])
    table = {int(c): tuple(int(v) for v in row) for c, row in zip(colors, counts)}
    # 背景色 0x000000 出现 2 次：列 0 与列 1 都是 2（重叠计数）
    assert table[0x000000] == (2, 2, 0)
    # 物体色只进混合列
    assert table[0x010203] == (0, 1, 0)
    # 臂色只进臂列
    assert table[0x040506] == (0, 0, 1)


def _model(entries: dict[int, tuple[int, int, int]]) -> ColorModel:
    """entries: 颜色 → (纯背景计数, 混合计数, 臂计数)。"""
    colors = np.array(sorted(entries), dtype=np.uint32)
    counts = np.array([entries[int(c)] for c in colors], dtype=np.int64)
    return ColorModel(colors=colors, counts=counts, source={})


def test_归一化似然argmax且未见颜色给_UNKNOWN():
    # 列总量：纯背景 100、混合 109、臂 40
    model = _model(
        {
            0x000000: (100, 100, 0),  # 纯背景色：P(bg)=1.0 > P(mix)=100/109
            0x010203: (0, 9, 0),  # 只在混合里出现（物体色的典型形态）
            0x040506: (0, 0, 40),  # 臂独有
        }
    )
    rgb = np.array([[[0, 0, 0], [1, 2, 3]], [[4, 5, 6], [9, 9, 9]]], dtype=np.uint8)
    labels = model.classify(rgb, veto_shared=False)
    assert labels.tolist() == [
        [CLASS_BACKGROUND, CLASS_MIX],
        [CLASS_ARM, CLASS_UNKNOWN],
    ]


def test_类先验不参与_小类可凭似然胜出大类():
    # 混合列总量 10000 >> 臂列总量 50：若拿原始计数比大小（隐含先验），颜色 X 的
    # 混合计数 5 > 臂计数 3 会判混合；归一化似然 P(X|臂)=3/50 >> P(X|混合)=5/10000，
    # 必须判臂。类规模不得影响判别，这是「先验未知、不参与」的直接判据。
    model = _model(
        {
            0x000000: (900, 9995, 0),  # 撑起两列的总量
            0x0A0B0C: (0, 5, 3),  # 颜色 X：臂似然占优但绝对计数劣势
            0x040506: (100, 0, 47),  # 纯背景与臂的填充，凑齐列总量
        }
    )
    rgb = np.array([[[10, 11, 12]]], dtype=np.uint8)
    assert model.classify(rgb, veto_shared=False).tolist() == [[CLASS_ARM]]
    # 混合支撑否决：X 在混合分布出现过（计数 5 > 0），无法排除属于物体 → 改判混合
    assert model.classify(rgb).tolist() == [[CLASS_MIX]]


def test_臂独有颜色不受否决影响():
    model = _model(
        {
            0x000000: (100, 100, 0),
            0x040506: (0, 0, 40),  # 混合列计数为 0：否决不碰它
        }
    )
    rgb = np.array([[[4, 5, 6]]], dtype=np.uint8)
    assert model.classify(rgb).tolist() == [[CLASS_ARM]]


def test_空列直接报错不静默():
    # 臂列全零：归一化没有意义，必须 fail-loud 而不是除零或静默判非臂
    model = _model({0x000000: (10, 10, 0)})
    rgb = np.array([[[0, 0, 0]]], dtype=np.uint8)
    with pytest.raises(ValueError, match="空列"):
        model.classify(rgb)


def test_只保留触到上边界的连通块():
    mask = np.zeros((10, 10), dtype=bool)
    mask[0:3, 1:4] = True  # 触顶：留
    mask[6:9, 6:9] = True  # 桌面上的孤块：删
    kept = _keep_top_entering(mask)
    assert kept[0:3, 1:4].all()
    assert not kept[6:9, 6:9].any()


def test_时间平滑只能删不能加():
    # 中间帧该位置判的是 UNKNOWN（颜色表没见过），前后帧是臂；多数表决会想把它补上，
    # 第 4 条「只保留本帧判定的臂」必须把它按回去——v4 留出集上真实发生过的 bug
    arm = np.full((16, 16), CLASS_BACKGROUND, dtype=np.int8)
    arm[0:12, 5:11] = CLASS_ARM
    middle = arm.copy()
    middle[6:9, 6:9] = CLASS_UNKNOWN
    masks = arm_masks_for_segment([arm, middle, arm], MaskParams())
    assert not masks[1][middle == CLASS_UNKNOWN].any()


def test_时间平滑抹掉单帧噪声也保住连续区域():
    steady = np.zeros((4, 4), dtype=bool)
    steady[1, 1] = True
    blink = np.zeros((4, 4), dtype=bool)
    blink[3, 3] = True
    masks = [steady, steady | blink, steady]
    smoothed = _temporal_majority(masks, 3)
    assert all(item[1, 1] for item in smoothed)
    assert not any(item[3, 3] for item in smoothed)


def test_判为混合的像素在任何情况下都不被标定():
    # 一整条从顶部伸下来的臂，中间嵌着一块判为混合的像素（接触帧的典型形态）
    labels = np.full((16, 16), CLASS_BACKGROUND, dtype=np.int8)
    labels[0:12, 5:11] = CLASS_ARM
    labels[6:10, 6:10] = CLASS_MIX
    masks = arm_masks_for_segment([labels] * 3, MaskParams())
    for mask in masks:
        assert not mask[labels == CLASS_MIX].any()
    assert masks[0].any(), "臂本体不应该被整体抹掉"


def test_桌面上不触顶的臂色块不会被标定():
    labels = np.full((16, 16), CLASS_BACKGROUND, dtype=np.int8)
    labels[8:13, 8:13] = CLASS_ARM  # 悬空的一块臂色，不触顶
    masks = arm_masks_for_segment([labels] * 3, MaskParams())
    assert not any(mask.any() for mask in masks)


def test_相位切段不跨段平滑():
    demo = np.full((16, 16), CLASS_BACKGROUND, dtype=np.int8)
    arm = np.full((16, 16), CLASS_BACKGROUND, dtype=np.int8)
    arm[0:12, 5:11] = CLASS_ARM
    # 第一段（demo 相位）全是空场景，第二段有臂；跨段平滑会让空场景那帧沾上臂
    labels = [demo, demo, arm, arm, arm]
    flags = [True, True, False, False, False]
    masks = arm_masks_for_episode(labels, flags, MaskParams())
    assert not masks[0].any() and not masks[1].any()
    assert masks[2].any() and masks[3].any()


def test_相位标记数量对不上直接报错():
    labels = [np.zeros((4, 4), dtype=np.int8)] * 3
    with pytest.raises(ValueError, match="不一致"):
        arm_masks_for_episode(labels, [True, False], MaskParams())


def test_涂红只动_mask_内像素():
    rng = np.random.default_rng(0)
    rgb = rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)
    mask = np.zeros((8, 8), dtype=bool)
    mask[2:4, 2:4] = True
    painted = apply_red_mask(rgb, mask)
    assert (painted[mask] == (255, 0, 0)).all()
    assert (painted[~mask] == rgb[~mask]).all()
    assert (rgb == rgb).all(), "原图不得被就地改写"


def test_形态学参数只接受正奇数时间窗():
    with pytest.raises(ValueError, match="正奇数"):
        MaskParams(temporal_window=2)
    with pytest.raises(ValueError, match="不能为负"):
        MaskParams(final_erode=-1)
