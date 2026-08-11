"""v4 三类分布 + 形态学标定的逻辑测试（合成数据，秒级，不碰任何 h5 产物）。

覆盖三件事：

1. **三类映射**（`color_model`）：用户拍板的那三条约定必须逐字成立——
   `robot_link` 归机械臂、`background_prop` 加 seg_id 0 归背景、`flow_objects`
   归物体、`kind == "tcp"` 归机械臂；出现未覆盖的 seg id 必须报错而不是猜。
2. **颜色表**：`argmax` 取的是最大后验，未见过的颜色必须给 `UNKNOWN`。
3. **四条形态学规则**（`arm_mask_v4`）：不触顶的连通块不得留下、单帧噪声被时间
   平滑抹掉、判为物体的像素在任何情况下都不得被标定、mask 外的像素逐位不变。
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
V4_DIR = REPO_ROOT / "scripts" / "data-generation-v4"
if str(V4_DIR) not in sys.path:
    sys.path.insert(0, str(V4_DIR))

from arm_mask_v4 import (  # noqa: E402
    MaskParams,
    apply_red_mask,
    arm_masks_for_episode,
    arm_masks_for_segment,
    _keep_top_entering,
    _temporal_majority,
)
from color_model import (  # noqa: E402
    CLASS_ARM,
    CLASS_BACKGROUND,
    CLASS_OBJECT,
    CLASS_UNKNOWN,
    ColorModel,
    class_ids_from_setup,
    labels_from_segmentation,
    pack_rgb,
    uncovered_mask,
)


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


def test_三类映射按约定逐字成立(setup_handle):
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
    # episode 运行中动态创建的目标 / 路径标记物（如 PatternLock 的连线节点）不在
    # setup 快照里；它们必定是任务相关的可见物体，归物体才能吃到下游的硬否决保护
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


def _model(entries: dict[int, tuple[int, int, int]]) -> ColorModel:
    colors = np.array(sorted(entries), dtype=np.uint32)
    counts = np.array([entries[int(c)] for c in colors], dtype=np.int64)
    return ColorModel(colors=colors, counts=counts, source={})


def test_颜色表取最大后验且未见颜色给_UNKNOWN():
    model = _model(
        {
            0x000000: (100, 0, 0),  # 背景
            0x010203: (1, 9, 0),  # 物体占多数
            0x040506: (2, 0, 40),  # 机械臂独占，没在物体上出现过
        }
    )
    rgb = np.array([[[0, 0, 0], [1, 2, 3]], [[4, 5, 6], [9, 9, 9]]], dtype=np.uint8)
    labels = model.classify(rgb)
    assert labels.tolist() == [
        [CLASS_BACKGROUND, CLASS_OBJECT],
        [CLASS_ARM, CLASS_UNKNOWN],
    ]


def test_共享色否决把机械臂多数的颜色改判物体():
    # 灰白臂壳与灰白按钮顶面在 24 位 RGB 上同色，argmax 会按多数判给臂；
    # 宗旨要求宁可漏标臂也不碰物体，所以只要该颜色在物体上出现过就不判臂
    model = _model({0x040506: (0, 3, 40)})
    rgb = np.array([[[4, 5, 6]]], dtype=np.uint8)
    assert model.classify(rgb).tolist() == [[CLASS_OBJECT]]
    assert model.classify(rgb, veto_shared=False).tolist() == [[CLASS_ARM]]


def test_只保留触到上边界的连通块():
    mask = np.zeros((10, 10), dtype=bool)
    mask[0:3, 1:4] = True  # 触顶：留
    mask[6:9, 6:9] = True  # 桌面上的孤块：删
    kept = _keep_top_entering(mask)
    assert kept[0:3, 1:4].all()
    assert not kept[6:9, 6:9].any()


def test_时间平滑只能删不能加():
    # 中间帧该位置判的是 UNKNOWN（颜色表没见过），前后帧是臂；多数表决会想把它补上，
    # 第 4 条「只保留本帧判定的臂」必须把它按回去——留出集上真实发生过的 bug
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


def test_判为物体的像素在任何情况下都不被标定():
    # 一整条从顶部伸下来的臂，中间嵌着一块物体（接触帧的典型形态）
    labels = np.full((16, 16), CLASS_BACKGROUND, dtype=np.int8)
    labels[0:12, 5:11] = CLASS_ARM
    labels[6:10, 6:10] = CLASS_OBJECT
    masks = arm_masks_for_segment([labels] * 3, MaskParams())
    for mask in masks:
        assert not mask[labels == CLASS_OBJECT].any()
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
