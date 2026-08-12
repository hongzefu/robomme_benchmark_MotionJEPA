#!/usr/bin/env python3
"""分割过程走查出图入口：拿真实帧，一格一格演示「这张图是怎么被分出来的」。

`compare_gt.py` 只给最终结果，看不出中间发生了什么。本入口把同一帧在
**颜色判决 → 四条形态学规则**上的每一步都画出来，并把每一步**删掉的像素单独标红**
——四条规则的设计原则是「合起来只会让标定区域变小或持平」，这张图就是它的逐格证据。

每个任务出两张：

- `<Task>_walkthrough.png`：**逐阶段走查**，一行七格：

  | 格 | 内容 |
  |---|---|
  | 原图 | 未改动的 `front_rgb` |
  | 颜色判决 | 逐像素查表的结果（背景 / 混合 / 臂 / 未见色四色着色） |
  | 候选 | 判成臂的像素，即形态学的输入 |
  | ① 开运算 | 3×3 先腐蚀后膨胀，去抗锯齿与阴影噪点 |
  | ② 触顶连通域 | 只留碰到画面上边界的连通分量 |
  | ③ 时间平滑 | 3 帧滑动多数表决（按 `is_video_demo` 相位分段） |
  | ④ 保守收缩 | 与本帧判臂取交 + 腐蚀一次 = 最终 mask |

  ⚠ ③ 是四条里**唯一可能加像素**的一条（多数表决会把「本帧不在候选、前后帧在」的
  像素补进来），所以它那一格的红色不一定只减不增；④ 的白名单交把它兜回来，整条链
  相对候选集才是单调收缩的。走查图把这件事画出来，而不是嘴上说。

  再加底部一条参照带：GT 三类图 / GT 臂 / 红遮罩 / 误差图。

- `<Task>_pixels.png`：**逐像素举例**。在原图上点几个代表性像素（标到的真臂、落在
  臂∩混合共享色上被否决挡掉的真臂、被正确挡下的真物体、未见色 UNKNOWN、判臂但被
  形态学收掉的真臂），逐个列出它的 24 位颜色、三列归一化似然、判决与 GT 真身
  ——把「查表 argmax + 否决」这条规则落到具体数字上。

选帧规则：优先取该 episode 里**误标物体像素最多的那一帧**（红线若被击穿，图上直接
看得到）；整段都没有误标时——按刚性原则这是常态——退化成取 GT 臂像素最多的一帧。
选中的帧号写在图注里。

用法：

    uv run --no-sync python scripts/data-generation-v4.2/segmentation_walkthrough.py \\
      --h5 'artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5' \\
      --model scripts/data-generation-v4.2/outputs/color_model.npz \\
      --episode 10 --out scripts/data-generation-v4.2/outputs/walkthrough
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Sequence

import h5py
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from arm_mask_v4 import (  # noqa: E402
    MaskParams,
    _erode,
    _keep_top_entering,
    _open,
    _temporal_majority,
    apply_red_mask,
    arm_masks_for_episode,
)
from color_model import (  # noqa: E402
    CLASS_ARM,
    CLASS_BACKGROUND,
    CLASS_MIX,
    CLASS_OBJECT,
    CLASS_UNKNOWN,
    ColorModel,
    class_ids_from_setup,
    iter_episode_frames,
    labels_from_segmentation,
    pack_rgb,
)
from fit_color_model import resolve_h5  # noqa: E402
from render_outputs import _error_image  # noqa: E402

FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
BG = (24, 24, 28)
FG = (240, 240, 240)
DIM = (170, 170, 178)
LINE = (90, 90, 96)

# 颜色判决图的四色着色（与似然无关，纯粹为了肉眼分辨类别）
LABEL_COLORS = {
    CLASS_BACKGROUND: (62, 84, 120),
    CLASS_MIX: (232, 150, 60),
    CLASS_ARM: (86, 220, 112),
    CLASS_UNKNOWN: (214, 62, 196),
}
LABEL_LEGEND = (
    ((62, 84, 120), "判纯背景"),
    ((232, 150, 60), "判背景∪物体混合"),
    ((86, 220, 112), "判机械臂"),
    ((214, 62, 196), "未见色 UNKNOWN"),
)

KEEP = (96, 226, 240)  # 当前阶段保留下来的像素
DROP = (255, 66, 66)  # 相对上一阶段被删掉的像素

STAGE_NAMES = (
    "候选：判臂像素",
    "① 开运算",
    "② 触顶连通域",
    "③ 时间平滑",
    "④ 保守收缩 + 腐蚀",
)

TILE = 256  # front_rgb 就是 256×256，走查图按原分辨率贴，不做任何缩放
GAP = 10
PAD = 16
TITLE_H = 62
ROW_LABEL_W = 132
HEAD_H = 34
FOOT_H = 30
LEGEND_H = 40


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def stagewise_masks(
    labels: Sequence[np.ndarray],
    is_video_demo: Sequence[bool],
    params: MaskParams,
) -> list[list[np.ndarray]]:
    """整段 episode 的逐阶段 mask：返回 5 个阶段，每个阶段是逐帧 mask 列表。

    ⚠ 这里**必须**与 `arm_mask_v4.arm_masks_for_segment` 是同一套运算，否则走查图画的
    就不是生产链路。做法是直接 import 那四个私有算子（`_open` / `_keep_top_entering` /
    `_temporal_majority` / `_erode`）并保持调用顺序不变，相位分段逻辑也照抄
    `arm_masks_for_episode`；函数末尾再拿 `arm_masks_for_episode` 的输出逐位断言最后
    一个阶段，任何一处走样都会当场炸掉。
    """
    if len(labels) != len(is_video_demo):
        raise ValueError(
            f"标签帧数（{len(labels)}）与相位标记数（{len(is_video_demo)}）不一致"
        )
    stages: list[list[np.ndarray | None]] = [
        [None] * len(labels) for _ in range(len(STAGE_NAMES))
    ]
    start = 0
    for index in range(1, len(labels) + 1):
        if index == len(labels) or bool(is_video_demo[index]) != bool(
            is_video_demo[start]
        ):
            piece = labels[start:index]
            candidate = [np.asarray(item) == CLASS_ARM for item in piece]
            opened = [_open(item, params.open_iterations) for item in candidate]
            topped = [_keep_top_entering(item) for item in opened]
            smoothed = _temporal_majority(topped, params.temporal_window)
            shrunk = [
                _erode(mask & (np.asarray(label_map) == CLASS_ARM), params.final_erode)
                for mask, label_map in zip(smoothed, piece)
            ]
            for stage_index, produced in enumerate(
                (candidate, opened, topped, smoothed, shrunk)
            ):
                for offset, mask in enumerate(produced):
                    stages[stage_index][start + offset] = mask
            start = index

    if any(mask is None for stage in stages for mask in stage):
        raise RuntimeError("相位切段没有覆盖全部帧")
    resolved = [[mask for mask in stage if mask is not None] for stage in stages]

    reference = arm_masks_for_episode(labels, is_video_demo, params)
    for produced, expected in zip(resolved[-1], reference):
        if not np.array_equal(produced, expected):
            raise RuntimeError("逐阶段复算与 arm_masks_for_episode 不一致，走查图不可信")
    return resolved


def _label_image(labels: np.ndarray) -> np.ndarray:
    image = np.zeros((*labels.shape, 3), np.uint8)
    for value, color in LABEL_COLORS.items():
        image[labels == value] = color
    return image


def _mask_on_frame(
    rgb: np.ndarray, mask: np.ndarray, previous: np.ndarray | None
) -> np.ndarray:
    """暗底原图 + 当前 mask 涂青 + 相对上一阶段被删的像素涂红。"""
    image = (np.asarray(rgb).astype(np.float32) * 0.32).astype(np.uint8)
    if previous is not None:
        image[np.asarray(previous) & ~np.asarray(mask)] = DROP
    image[np.asarray(mask)] = KEEP
    return image


def _binary_image(mask: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    image = np.zeros((*mask.shape, 3), np.uint8)
    image[np.asarray(mask)] = color
    return image


def _pick_frame(
    masks: Sequence[np.ndarray], truth: Sequence[np.ndarray]
) -> tuple[int, int]:
    """选走查帧：误标物体最多的一帧；整段无误标则取 GT 臂像素最多的一帧。

    ⚠ 按刚性原则，误标物体恒为 0，所以实际上总是走后一支（取臂最大的帧，最有内容）。
    前一支保留不删：它是异常暴露通道——万一红线被击穿，走查图会自动切到出事的那一帧。
    """
    false_object = np.array(
        [int((mask & (gt == CLASS_OBJECT)).sum()) for mask, gt in zip(masks, truth)]
    )
    if false_object.max() > 0:
        index = int(false_object.argmax())
        return index, int(false_object[index])
    sizes = np.array([int((gt == CLASS_ARM).sum()) for gt in truth])
    return int(sizes.argmax()), 0


def _paste_row(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    tiles: Sequence[tuple[str, np.ndarray, str]],
    x0: int,
    y0: int,
    head: bool,
) -> int:
    """贴一整行图块，返回该行占用的高度（含标题条与脚注条）。"""
    y = y0
    if head:
        for index, (title, _, _) in enumerate(tiles):
            x = x0 + index * (TILE + GAP)
            _center(draw, title, (x, y, x + TILE, y + HEAD_H), _font(17), FG)
        y += HEAD_H
    for index, (_, image, foot) in enumerate(tiles):
        x = x0 + index * (TILE + GAP)
        canvas.paste(Image.fromarray(image), (x, y))
        if foot:
            _center(
                draw, foot, (x, y + TILE, x + TILE, y + TILE + FOOT_H), _font(15), DIM
            )
    return (HEAD_H if head else 0) + TILE + FOOT_H


def _center(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int] = FG,
) -> None:
    x0, y0, x1, y1 = box
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((x0 + x1 - (right - left)) / 2 - left, (y0 + y1 - (bottom - top)) / 2 - top),
        text,
        font=font,
        fill=fill,
    )


def _render_walkthrough(
    task: str,
    episode_name: str,
    frame_index: int,
    rgb: np.ndarray,
    gt: np.ndarray,
    predicted: np.ndarray,
    stages: list[np.ndarray],
    out_path: Path,
) -> None:
    """一行走查 + 一行参照带。"""
    columns = 2 + len(STAGE_NAMES)
    width = PAD * 2 + ROW_LABEL_W + columns * TILE + (columns - 1) * GAP
    row_h = HEAD_H + TILE + FOOT_H
    height = PAD * 2 + TITLE_H + row_h + GAP + LEGEND_H + row_h + GAP

    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    y = PAD
    _center(
        draw,
        f"{task} · {episode_name} · 第 {frame_index} 帧 —— 分割过程逐格走查",
        (0, y, width, y + TITLE_H - 22),
        _font(28),
    )
    _center(
        draw,
        "每格：暗底原图 + 青色 = 该阶段保留的像素 + 红色 = 相对上一阶段被删掉的像素；脚注是该阶段的像素数与增量",
        (0, y + TITLE_H - 24, width, y + TITLE_H),
        _font(16),
        DIM,
    )
    y += TITLE_H

    x0 = PAD + ROW_LABEL_W
    tiles: list[tuple[str, np.ndarray, str]] = [
        ("原图 front_rgb", np.asarray(rgb), ""),
        (
            "颜色判决（查表 argmax + 否决）",
            _label_image(predicted),
            f"判臂 {int((predicted == CLASS_ARM).sum())} px",
        ),
    ]
    previous: np.ndarray | None = None
    for stage_index, name in enumerate(STAGE_NAMES):
        mask = stages[stage_index]
        kept = int(mask.sum())
        # ⚠ 增量必须带符号：③ 时间平滑是多数表决，**会补像素**（本帧不在候选、
        # 前后帧在）。写死成「−」会打出「−−4」，也会掩盖 ③ 非单调这个关键事实。
        delta = ""
        if previous is not None:
            change = kept - int(previous.sum())
            delta = "（±0）" if change == 0 else f"（{'+' if change > 0 else '−'}{abs(change)}）"
        tiles.append((name, _mask_on_frame(rgb, mask, previous), f"{kept} px{delta}"))
        previous = mask
    used = _paste_row(canvas, draw, tiles, x0, y, head=True)
    draw.multiline_text(
        (PAD, y + HEAD_H + TILE // 2 - 24),
        "判别 + 四条\n形态学规则",
        font=_font(19),
        fill=(120, 235, 140),
        align="center",
        spacing=6,
    )
    y += used + GAP

    font = _font(16)
    widths = [draw.textlength(text, font=font) + 36 for _, text in LABEL_LEGEND]
    widths += [draw.textlength(text, font=font) + 36 for text in ("保留", "被本步删除")]
    x = (width - sum(widths)) / 2
    for color, text in (
        *LABEL_LEGEND,
        (KEEP, "保留"),
        (DROP, "被本步删除"),
    ):
        draw.rectangle([x, y + 12, x + 17, y + 29], fill=color, outline=LINE)
        draw.text((x + 25, y + 10), text, font=font, fill=FG)
        x += draw.textlength(text, font=font) + 36
    y += LEGEND_H

    final_mask = stages[-1]
    reference: list[tuple[str, np.ndarray, str]] = [
        ("GT 三类真值", _gt_image(gt), "白=臂 橙=物体 蓝=背景"),
        (
            "GT 机械臂",
            _binary_image(gt == CLASS_ARM, (255, 255, 255)),
            f"{int((gt == CLASS_ARM).sum())} px",
        ),
        (
            "红遮罩（产物）",
            apply_red_mask(rgb, final_mask),
            f"标定 {int(final_mask.sum())} px",
        ),
        (
            "误差图",
            _error_image(final_mask, gt),
            f"误标物体 {int((final_mask & (gt == CLASS_OBJECT)).sum())} px（红线）",
        ),
    ]
    _paste_row(canvas, draw, reference, x0, y, head=True)
    draw.multiline_text(
        (PAD, y + HEAD_H + TILE // 2 - 24),
        "参照带\nGT 与产物",
        font=_font(19),
        fill=(140, 190, 255),
        align="center",
        spacing=6,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


def _gt_image(gt: np.ndarray) -> np.ndarray:
    image = np.zeros((*gt.shape, 3), np.uint8)
    image[gt == CLASS_BACKGROUND] = (62, 84, 120)
    image[gt == CLASS_OBJECT] = (232, 150, 60)
    image[gt == CLASS_ARM] = (255, 255, 255)
    return image


def _sample_pixels(
    rgb: np.ndarray,
    gt: np.ndarray,
    model: ColorModel,
    predicted: np.ndarray,
    final_mask: np.ndarray,
) -> list[dict[str, Any]]:
    """挑一组能讲清规则的代表性像素，每类最多两个，按「解释力」排序。

    刻意不随机采样——要的是把两段代价与两段保护各摆一个到台面上：
    ①标到的真臂（成功）②落在臂∩混合共享色上、被否决挡掉的真臂（**颜色阶段**的漏标
    代价，纯支撑集判定）③判臂但被形态学收掉的真臂（**形态学阶段**的漏标代价）
    ④被判混合、正确挡下的真物体（红线怎么守住的）⑤未见色 UNKNOWN 的真臂
    ⑥判纯背景的真背景（对照）。
    """
    packed = pack_rgb(rgb)
    shared_support = set(
        int(color)
        for color in model.colors[
            (model.counts[:, CLASS_ARM] > 0) & (model.counts[:, CLASS_MIX] > 0)
        ].tolist()
    )
    on_shared = np.isin(packed, list(shared_support)) if shared_support else np.zeros_like(packed, bool)
    rows, cols = np.indices(gt.shape)
    picks: list[dict[str, Any]] = []

    def take(mask: np.ndarray, note: str, limit: int = 1) -> None:
        found = np.flatnonzero(mask.ravel())
        if found.size == 0:
            return
        # 取该集合里出现次数最多的颜色的代表点，避免挑到孤立的抗锯齿噪点
        colors, inverse = np.unique(packed.ravel()[found], return_inverse=True)
        top = np.argsort(-np.bincount(inverse, minlength=colors.size))[:limit]
        for choice in top:
            index = int(found[np.flatnonzero(inverse == choice)[0]])
            picks.append(
                {
                    "y": int(rows.ravel()[index]),
                    "x": int(cols.ravel()[index]),
                    "note": note,
                }
            )

    is_arm = gt == CLASS_ARM
    is_object = gt == CLASS_OBJECT
    take(is_arm & final_mask, "真臂 · 标到了", 2)
    take(is_arm & on_shared, "真臂 · 落在臂∩混合共享色（否决挡掉，颜色阶段代价）", 2)
    take(
        is_arm & (predicted == CLASS_ARM) & ~final_mask,
        "真臂 · 判臂但被形态学收掉（形态学阶段代价）",
        2,
    )
    take(is_object & (predicted == CLASS_MIX), "真物体 · 判混合（红线就是这么守住的）", 2)
    take(is_arm & (predicted == CLASS_UNKNOWN), "真臂 · 未见色 UNKNOWN")
    take(gt == CLASS_BACKGROUND, "真背景 · 判纯背景")

    totals = model.counts.sum(axis=0).astype(np.float64)
    detailed: list[dict[str, Any]] = []
    for item in picks:
        y, x = item["y"], item["x"]
        color = int(packed[y, x])
        index = int(np.searchsorted(model.colors, color))
        hit = index < model.colors.size and int(model.colors[index]) == color
        likelihood = (
            (model.counts[index].astype(np.float64) / totals).tolist()
            if hit
            else [0.0, 0.0, 0.0]
        )
        detailed.append(
            {
                **item,
                "rgb": [int(value) for value in rgb[y, x]],
                "counts": model.counts[index].tolist() if hit else [0, 0, 0],
                "likelihood": likelihood,
                "判决": int(predicted[y, x]),
                "gt": int(gt[y, x]),
                "最终标定": bool(final_mask[y, x]),
            }
        )
    return detailed


DECISION_NAMES = {
    CLASS_BACKGROUND: "纯背景",
    CLASS_MIX: "混合",
    CLASS_ARM: "机械臂",
    CLASS_UNKNOWN: "未见色",
}
GT_NAMES = {CLASS_BACKGROUND: "背景", CLASS_OBJECT: "物体", CLASS_ARM: "机械臂"}


def _render_pixels(
    task: str,
    episode_name: str,
    frame_index: int,
    rgb: np.ndarray,
    samples: Sequence[dict[str, Any]],
    out_path: Path,
) -> None:
    """逐像素举例图：左边标点的放大原图，右边一张表。"""
    scale = 3
    picture = np.asarray(
        Image.fromarray(rgb).resize((TILE * scale, TILE * scale), Image.NEAREST)
    )
    columns = (
        ("#", 46),
        ("颜色", 76),
        ("RGB", 150),
        ("P(色|背景)", 150),
        ("P(色|混合)", 150),
        ("P(色|臂)", 150),
        ("判决", 108),
        ("最终标定", 108),
        ("GT 真身", 108),
        ("这个像素说明什么", 430),
    )
    table_w = sum(item[1] for item in columns)
    row_h = 46
    width = PAD * 3 + picture.shape[1] + table_w
    # 右侧列高 = 表头 + 数据行 + 空一行 + 底部七行规则说明；与左边放大图取较高者
    table_h = (len(samples) + 2) * row_h + 7 * 30 + 24
    height = max(picture.shape[0], table_h) + PAD * 2 + TITLE_H

    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    _center(
        draw,
        f"{task} · {episode_name} · 第 {frame_index} 帧 —— 逐像素举例：这个颜色为什么被判成这一类",
        (0, PAD, width, PAD + TITLE_H - 20),
        _font(26),
    )
    y0 = PAD + TITLE_H
    canvas.paste(Image.fromarray(picture), (PAD, y0))

    # 采样点常常挤在夹爪那一小块，编号直接贴圆圈右上会互相压住。这里对每个编号试八个
    # 方位，挑第一个既不压住别的编号、也不压住任何一个圆圈的落点；八个都不行就用最后
    # 一个方位硬放（宁可重叠也不能把编号丢了）。
    centers = [
        (PAD + item["x"] * scale + scale // 2, y0 + item["y"] * scale + scale // 2)
        for item in samples
    ]
    placed: list[tuple[int, int]] = []
    for index, (cx, cy) in enumerate(centers):
        draw.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], outline=(255, 255, 0), width=3)
        draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(255, 255, 0))
    for index, (cx, cy) in enumerate(centers):
        spot = (cx + 13, cy - 13)
        for offset_x, offset_y in (
            (13, -13),
            (-28, -13),
            (13, 6),
            (-28, 6),
            (13, -34),
            (-28, -34),
            (13, 26),
            (-28, 26),
        ):
            spot = (cx + offset_x, cy + offset_y)
            clear_of_labels = all(
                abs(spot[0] - other[0]) > 22 or abs(spot[1] - other[1]) > 22
                for other in placed
            )
            clear_of_dots = all(
                abs(spot[0] + 7 - other[0]) > 20 or abs(spot[1] + 11 - other[1]) > 20
                for other in centers
            )
            if clear_of_labels and clear_of_dots:
                break
        placed.append(spot)
        draw.text(spot, str(index + 1), font=_font(22), fill=(255, 255, 0))

    x0 = PAD * 2 + picture.shape[1]
    font_head = _font(16)
    font_cell = _font(15)
    x = x0
    for title, column_w in columns:
        _center(draw, title, (x, y0, x + column_w, y0 + row_h), font_head, DIM)
        x += column_w
    draw.line([(x0, y0 + row_h), (x0 + table_w, y0 + row_h)], fill=LINE, width=1)

    for index, item in enumerate(samples):
        y = y0 + (index + 1) * row_h
        values = [
            str(index + 1),
            None,
            "({:>3}, {:>3}, {:>3})".format(*item["rgb"]),
            f"{item['likelihood'][0]:.3e}",
            f"{item['likelihood'][1]:.3e}",
            f"{item['likelihood'][2]:.3e}",
            DECISION_NAMES[item["判决"]],
            "是" if item["最终标定"] else "否",
            GT_NAMES[item["gt"]],
            item["note"],
        ]
        x = x0
        for (title, column_w), value in zip(columns, values):
            if value is None:
                draw.rectangle(
                    [x + column_w // 2 - 17, y + 11, x + column_w // 2 + 17, y + 35],
                    fill=tuple(item["rgb"]),
                    outline=LINE,
                )
            else:
                color = FG
                # 真臂却没被标进去 = 漏标代价，标红提示（漏标可接受，但要看得见）
                if title == "最终标定" and not item["最终标定"] and item["gt"] == CLASS_ARM:
                    color = (255, 120, 120)
                if title == "这个像素说明什么":
                    color = DIM
                _center(draw, value, (x, y, x + column_w, y + row_h), font_cell, color)
            x += column_w
        draw.line([(x0, y + row_h), (x0 + table_w, y + row_h)], fill=(52, 52, 58), width=1)

    # 表格通常比左边那张放大图矮一大截，剩下的空白正好写清楚判决规则本身，
    # 免得读者要跳回 color_model.py 的 docstring 才知道这几列数字怎么用。
    note_y = y0 + (len(samples) + 2) * row_h
    for offset, (line, color) in enumerate(
        (
            ("判决规则（逐像素、与画面内容无关）", FG),
            ("① 查表：把像素的 24 位 RGB 在颜色表里查出三列计数；三列都没见过 → UNKNOWN，下游按「不是机械臂」处理。", DIM),
            ("② 归一化似然 argmax：每列先除以本列像素总量得 P(色|类) 再取最大者。类先验刻意不参与——", DIM),
            ("　 混合列里物体占多少是未知的，任何用计数绝对量对比的规则都在偷用先验。列序（背景, 混合, 臂）使平手偏向非臂。", DIM),
            ("③ 混合支撑否决（v4.2 唯一口径，无开关）：argmax 判臂后，凡混合列计数 > 0（= 该色在无臂场景里出现过）一律改判混合。", (255, 150, 150)),
            # ⚠ 这行文案只准用思源宋体有字形的字符：⟺ / ⊆ 这类数学符号会渲染成豆腐块（实测）
            ("　 门限就是「出现过 / 没出现过」，不引入任何新阈值。由此「判臂」等价于「该色只在臂列见过」，误标物体在拟合集上恒为 0。", (255, 150, 150)),
            ("④ 之后的四条形态学规则只看这张标签图，再不碰颜色，也再不碰 GT（见同目录 <Task>_walkthrough.png）。", DIM),
        )
    ):
        draw.text(
            (x0 + 6, note_y + offset * 30),
            line,
            font=_font(18 if offset == 0 else 16),
            fill=color,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


def process_task(
    h5_path: str,
    episode_name: str,
    model_path: str,
    out_dir: str,
    params: MaskParams,
) -> dict[str, Any]:
    model = ColorModel.load(model_path)
    task = Path(h5_path).stem.replace("record_dataset_", "")

    with h5py.File(h5_path, "r") as handle:
        episode = handle[episode_name]
        class_ids = class_ids_from_setup(episode["setup"])
        frames = list(iter_episode_frames(episode))
    truth = [labels_from_segmentation(seg, class_ids) for _, _, seg, _ in frames]
    demo_flags = [flag for _, _, _, flag in frames]

    predicted = [model.classify(rgb) for _, rgb, _, _ in frames]
    stages = stagewise_masks(predicted, demo_flags, params)

    index, false_object = _pick_frame(stages[-1], truth)
    rgb = frames[index][1]
    _render_walkthrough(
        task,
        episode_name,
        index,
        rgb,
        truth[index],
        predicted[index],
        [stage[index] for stage in stages],
        Path(out_dir) / f"{task}_walkthrough.png",
    )
    samples = _sample_pixels(
        rgb, truth[index], model, predicted[index], stages[-1][index]
    )
    _render_pixels(
        task, episode_name, index, rgb, samples, Path(out_dir) / f"{task}_pixels.png"
    )

    return {
        "task": task,
        "episode": episode_name,
        "frames": len(frames),
        "走查帧": index,
        "该帧误标物体": false_object,
        "该帧各阶段像素数": {
            name: int(stage[index].sum()) for name, stage in zip(STAGE_NAMES, stages)
        },
        "该帧最终标定": int(stages[-1][index].sum()),
        # ③ 时间平滑相对 ② 的增量：为正即「多数表决补了像素」，是 ③ 非单调的直接证据。
        # 报告里「时间平滑真的会补像素」那条实证就读这个字段，不许凭印象写。
        "该帧时间平滑增量": int(stages[3][index].sum()) - int(stages[2][index].sum()),
        "逐像素举例": samples,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--h5",
        nargs="+",
        default=["artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5"],
        help="h5 路径或 glob（默认 train split 的 v4seg 数据集）",
    )
    parser.add_argument(
        "--model",
        default=str(SCRIPT_DIR / "outputs" / "color_model.npz"),
        help="fit_color_model.py 产出的颜色表",
    )
    parser.add_argument(
        "--episode", type=int, default=10, help="走查用的 episode（默认留出集 ep10）"
    )
    parser.add_argument(
        "--out", default=str(SCRIPT_DIR / "outputs" / "walkthrough"), help="产物目录"
    )
    parser.add_argument("--workers", type=int, default=8, help="并行进程数")
    parser.add_argument("--open-iterations", type=int, default=1)
    parser.add_argument("--temporal-window", type=int, default=3)
    parser.add_argument("--final-erode", type=int, default=1)
    args = parser.parse_args(argv)

    paths = resolve_h5(args.h5)
    params = MaskParams(
        open_iterations=args.open_iterations,
        temporal_window=args.temporal_window,
        final_erode=args.final_erode,
    )
    episode_name = f"episode_{args.episode}"
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"分割走查：{len(paths)} 个任务 × {episode_name}，并行 {args.workers}")

    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                process_task, str(path), episode_name, args.model, str(out_dir), params
            )
            for path in paths
        ]
        for future in as_completed(futures):
            records.append(future.result())
    elapsed = time.perf_counter() - started

    records.sort(key=lambda item: item["task"])
    payload = {
        "参数": {
            "颜色表": args.model,
            "episode": episode_name,
            "判别规则": "归一化似然 argmax + 混合支撑否决（v4.2 唯一口径，无开关）",
            "开运算次数": params.open_iterations,
            "时间窗": params.temporal_window,
            "最终腐蚀次数": params.final_erode,
        },
        "耗时秒": round(elapsed, 1),
        "逐任务": records,
    }
    (out_dir / "walkthrough.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for record in records:
        print(
            f"{record['task']}: 走查帧 {record['走查帧']}，"
            f"标定 {record['该帧最终标定']} px，"
            f"该帧误标物体 {record['该帧误标物体']} px，"
            f"③ 时间平滑增量 {record['该帧时间平滑增量']:+d} px"
        )
    grew = [item for item in records if item["该帧时间平滑增量"] > 0]
    print(
        f"③ 时间平滑在 {len(grew)}/{len(records)} 个任务的走查帧上**补了**像素"
        "（多数表决非单调的直接证据；④ 白名单交把它兜回来）"
    )
    print(f"共 {len(records) * 2} 张 → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
