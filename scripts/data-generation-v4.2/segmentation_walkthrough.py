#!/usr/bin/env python3
"""分割过程走查出视频入口：拿真实帧，一格一格演示「这张图是怎么被分出来的」。

`render_outputs.py` 只给最终指标，看不出中间发生了什么。本入口把同一帧在
**颜色判决 → 四条形态学规则**上的每一步都画出来，并把每一步**删掉的像素单独标红**
——四条规则的设计原则是「合起来只会让标定区域变小或持平」，这段视频就是它的逐格证据。

⚠ 出的是**视频不是单帧图**：原来只挑一帧出 `<Task>_walkthrough.png`，看到的只是那一帧
的运气；现在整段 episode **逐帧**渲染同一套版面，出
`<Task>_ep<N>_walkthrough.mp4`（默认 ep0-5 × 16 任务 = 96 段），四条规则在整段上的行为
（尤其 ③ 时间平滑什么时候补像素）直接看得见。版面内容一格不减，另在标题栏补印该
episode 的 **metadata 难度**（`setup/difficulty`）。

每个任务每个 episode 出一段 `<Task>_ep<N>_walkthrough.mp4`：**逐阶段走查**，一行七格：

  | 格 | 内容 |
  |---|---|
  | 原图 | 未改动的 `front_rgb` |
  | 颜色判决 | 逐像素查表的结果（背景 / 混合 / 臂 / 未见色四色着色） |
  | 候选 | 判成臂的像素，即形态学的输入 |
  | ① 开运算 | 3×3 先腐蚀后膨胀，去抗锯齿与阴影噪点 |
  | ② 触顶连通域 | 只留碰到画面上边界的连通分量 |
  | ③ 时间平滑 | 3 帧滑动多数表决（按 `is_video_demo` 相位分段） |
  | ④ 保守收缩 | 与本帧判臂取交 + 腐蚀一次 = 最终 mask |

⚠ ③ 是四条里**唯一可能加像素**的一条（多数表决会把「本帧不在候选、前后帧在」的像素
补进来），所以它那一格的红色不一定只减不增；④ 的白名单交把它兜回来，整条链相对候选集
才是单调收缩的。走查视频把这件事逐帧画出来，而不是嘴上说。

再加一条参照带（GT 三类图 / GT 臂 / 红遮罩 / 误差图），以及底部一条**判决规则说明带**
（`RULE_NOTES`）——「颜色判决」那一格怎么算出来的直接印在图上，不用回翻 README。

整段逐帧出，所以不再需要选帧；`walkthrough.json` 里仍记一个**代表帧**（误标物体像素
最多的那一帧；整段无误标——按刚性原则这是常态——则取 GT 臂像素最多的一帧）的逐阶段
数字，口径与出图时代完全一致，方便与旧报告对拍。

用法：

    uv run --no-sync python scripts/data-generation-v4.2/segmentation_walkthrough.py \\
      --h5 'artifacts/generated/v4seg-16env-val20ep/record_dataset_*.h5' \\
      --model scripts/data-generation-v4.2/outputs/color_model.npz \\
      --episodes 0-5 --out scripts/data-generation-v4.2/outputs/walkthrough_val_ep0-5
"""

from __future__ import annotations

import argparse
import json
import subprocess
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

# 底部判决规则说明带。这段文案原来印在 `<Task>_pixels.png` 上，那张图已取消，文案搬来
# 走查图底部——「颜色判决」那一格怎么算出来的，看图的人不该被迫回翻 README。
# ⚠ 本文案只准用思源宋体有字形的字符：⟺ / ⊆ / 下标数字这类符号会渲染成豆腐块（实测），
#   所以三列一律写成 N0 / N1 / N2。
RULE_NOTES: tuple[tuple[str, tuple[int, int, int], int], ...] = (
    ("判别规则（逐像素、纯支撑三段式、与画面内容无关）", FG, 19),
    (
        "① 查表：把像素的 24 位 RGB 在颜色表里查出三列计数——N0 = 纯背景、"
        "N1 = 背景与物体混合、N2 = 机械臂；查不到 → 未见色，下游按「不是机械臂」处理。",
        DIM,
        16,
    ),
    (
        "② 定类：N0 > 0 判纯背景；N1 = 0 且 N2 > 0 判机械臂；其余判混合。"
        "只看每列见过没见过，计数的数值大小完全不参与，也没有任何阈值或开关。",
        DIM,
        16,
    ),
    (
        "③ 判臂那条是往保守方向倒的：某颜色只要在无臂场景里出现过一次，"
        "就无法排除它属于物体，一律不判臂。门限就是「出现过 / 没出现过」，即 0。",
        (255, 150, 150),
        16,
    ),
    (
        "　 由此判臂色在标定集上的非臂像素恒为 0——「绝不误标物体」这条红线在颜色阶段是"
        "构造保证的，不是调出来的；代价是灰白共享色上的臂像素被一并挡掉。",
        (255, 150, 150),
        16,
    ),
    ("④ 之后的四条形态学规则只看上面这张标签图，再不碰颜色，也再不碰 GT。", DIM, 16),
)

TILE = 256  # front_rgb 就是 256×256，走查图按原分辨率贴，不做任何缩放
GAP = 10
PAD = 16
TITLE_H = 62
ROW_LABEL_W = 132
HEAD_H = 34
FOOT_H = 30
LEGEND_H = 40
NOTE_LINE_H = 30
NOTE_H = NOTE_LINE_H * len(RULE_NOTES) + 18


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


def _draw_row_heads(
    draw: ImageDraw.ImageDraw, titles: Sequence[str], x0: int, y0: int
) -> None:
    """画一行的表头文字（静态，只在底板上画一次）。"""
    for index, title in enumerate(titles):
        x = x0 + index * (TILE + GAP)
        _center(draw, title, (x, y0, x + TILE, y0 + HEAD_H), _font(17), FG)


def _paste_row(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    tiles: Sequence[tuple[np.ndarray, str]],
    x0: int,
    y0: int,
) -> None:
    """贴一整行图块与脚注（逐帧变，表头由 `_draw_row_heads` 事先画在底板上）。"""
    for index, (image, foot) in enumerate(tiles):
        x = x0 + index * (TILE + GAP)
        canvas.paste(Image.fromarray(image), (x, y0))
        if foot:
            _center(
                draw, foot, (x, y0 + TILE, x + TILE, y0 + TILE + FOOT_H), _font(15), DIM
            )


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


STAGE_ROW_HEADS = ("原图 front_rgb", "颜色判决（查表 + 三段支撑判据）", *STAGE_NAMES)
REFERENCE_ROW_HEADS = ("GT 三类真值", "GT 机械臂", "红遮罩（产物）", "误差图")


class WalkthroughCanvas:
    """走查画布：静态底板（表头 / 图例 / 行标签 / 规则说明带）建一次，逐帧只重画会变的部分。

    逐帧变的只有三样：标题栏那两行字、12 个图块、每个图块的脚注。整段 episode 几百帧，
    把不变的部分每帧重画一遍纯属浪费，所以底板 `copy()` 一份再补动态内容。⚠ 底板上
    标题栏与脚注条必须留空——它们每帧重画，底板若先写了字就会叠成糊字。
    """

    def __init__(self) -> None:
        columns = 2 + len(STAGE_NAMES)
        self.width = PAD * 2 + ROW_LABEL_W + columns * TILE + (columns - 1) * GAP
        row_h = HEAD_H + TILE + FOOT_H
        self.height = PAD * 2 + TITLE_H + row_h + GAP + LEGEND_H + row_h + GAP + NOTE_H

        base = Image.new("RGB", (self.width, self.height), BG)
        draw = ImageDraw.Draw(base)
        x0 = PAD + ROW_LABEL_W

        self.title_y = PAD
        y = PAD + TITLE_H

        _draw_row_heads(draw, STAGE_ROW_HEADS, x0, y)
        draw.multiline_text(
            (PAD, y + HEAD_H + TILE // 2 - 24),
            "判别 + 四条\n形态学规则",
            font=_font(19),
            fill=(120, 235, 140),
            align="center",
            spacing=6,
        )
        self.stage_row_y = y + HEAD_H
        y += row_h + GAP

        font = _font(16)
        widths = [draw.textlength(text, font=font) + 36 for _, text in LABEL_LEGEND]
        widths += [draw.textlength(text, font=font) + 36 for text in ("保留", "被本步删除")]
        x = (self.width - sum(widths)) / 2
        for color, text in (*LABEL_LEGEND, (KEEP, "保留"), (DROP, "被本步删除")):
            draw.rectangle([x, y + 12, x + 17, y + 29], fill=color, outline=LINE)
            draw.text((x + 25, y + 10), text, font=font, fill=FG)
            x += draw.textlength(text, font=font) + 36
        y += LEGEND_H

        _draw_row_heads(draw, REFERENCE_ROW_HEADS, x0, y)
        draw.multiline_text(
            (PAD, y + HEAD_H + TILE // 2 - 24),
            "参照带\nGT 与产物",
            font=_font(19),
            fill=(140, 190, 255),
            align="center",
            spacing=6,
        )
        self.reference_row_y = y + HEAD_H
        y += row_h + GAP

        # 底部规则说明带：把「颜色判决」那一格的算法原地写清楚
        draw.line([(PAD, y), (self.width - PAD, y)], fill=LINE, width=1)
        for offset, (line, color, size) in enumerate(RULE_NOTES):
            draw.text(
                (PAD + 6, y + 12 + offset * NOTE_LINE_H),
                line,
                font=_font(size),
                fill=color,
            )
        self.base = base
        self.x0 = x0

    def render_frame(
        self,
        task: str,
        episode_name: str,
        difficulty: str,
        frame_index: int,
        total_frames: int,
        rgb: np.ndarray,
        gt: np.ndarray,
        predicted: np.ndarray,
        stages: Sequence[np.ndarray],
    ) -> Image.Image:
        """渲染某一帧：一行走查 + 一行参照带（表头等静态件来自底板）。"""
        canvas = self.base.copy()
        draw = ImageDraw.Draw(canvas)
        y = self.title_y
        _center(
            draw,
            f"{task} · {episode_name} · 难度 {difficulty} · "
            f"第 {frame_index}/{total_frames - 1} 帧 —— 分割过程逐格走查",
            (0, y, self.width, y + TITLE_H - 22),
            _font(28),
        )
        _center(
            draw,
            "每格：暗底原图 + 青色 = 该阶段保留的像素 + 红色 = 相对上一阶段被删掉的像素；脚注是该阶段的像素数与增量",
            (0, y + TITLE_H - 24, self.width, y + TITLE_H),
            _font(16),
            DIM,
        )

        tiles: list[tuple[np.ndarray, str]] = [
            (np.asarray(rgb), ""),
            (
                _label_image(predicted),
                f"判臂 {int((predicted == CLASS_ARM).sum())} px",
            ),
        ]
        previous: np.ndarray | None = None
        for mask in stages:
            kept = int(mask.sum())
            # ⚠ 增量必须带符号：③ 时间平滑是多数表决，**会补像素**（本帧不在候选、
            # 前后帧在）。写死成「−」会打出「−−4」，也会掩盖 ③ 非单调这个关键事实。
            delta = ""
            if previous is not None:
                change = kept - int(previous.sum())
                delta = (
                    "（±0）"
                    if change == 0
                    else f"（{'+' if change > 0 else '−'}{abs(change)}）"
                )
            tiles.append((_mask_on_frame(rgb, mask, previous), f"{kept} px{delta}"))
            previous = mask
        _paste_row(canvas, draw, tiles, self.x0, self.stage_row_y)

        final_mask = stages[-1]
        reference: list[tuple[np.ndarray, str]] = [
            (_gt_image(gt), "白=臂 橙=物体 蓝=背景"),
            (
                _binary_image(gt == CLASS_ARM, (255, 255, 255)),
                f"{int((gt == CLASS_ARM).sum())} px",
            ),
            (
                apply_red_mask(rgb, final_mask),
                f"标定 {int(final_mask.sum())} px",
            ),
            (
                _error_image(final_mask, gt),
                f"误标物体 {int((final_mask & (gt == CLASS_OBJECT)).sum())} px（红线）",
            ),
        ]
        _paste_row(canvas, draw, reference, self.x0, self.reference_row_y)
        return canvas


def _open_writer(out_path: Path, width: int, height: int, fps: int) -> subprocess.Popen:
    """起一个 rawvideo → H.264 的 ffmpeg 管道。

    走查画幅 2016×992（宽高均为偶数，yuv420p 可用）。`+faststart` 把 moov 前置，
    否则 VS Code / 浏览器的流式播放器可能直接拒播（实测踩过）。
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    return subprocess.Popen(command, stdin=subprocess.PIPE)


def _gt_image(gt: np.ndarray) -> np.ndarray:
    image = np.zeros((*gt.shape, 3), np.uint8)
    image[gt == CLASS_BACKGROUND] = (62, 84, 120)
    image[gt == CLASS_OBJECT] = (232, 150, 60)
    image[gt == CLASS_ARM] = (255, 255, 255)
    return image


def process_task(
    h5_path: str,
    episode_name: str,
    model_path: str,
    out_dir: str,
    params: MaskParams,
    fps: int,
) -> dict[str, Any]:
    model = ColorModel.load(model_path)
    task = Path(h5_path).stem.replace("record_dataset_", "")

    with h5py.File(h5_path, "r") as handle:
        episode = handle[episode_name]
        class_ids = class_ids_from_setup(episode["setup"])
        # metadata 写的难度：随 episode 存进 h5 的 setup/difficulty，逐帧印在标题栏上
        difficulty = episode["setup"]["difficulty"][()]
        if isinstance(difficulty, bytes):
            difficulty = difficulty.decode("utf-8")
        difficulty = str(difficulty)
        frames = list(iter_episode_frames(episode))
    truth = [labels_from_segmentation(seg, class_ids) for _, _, seg, _ in frames]
    demo_flags = [flag for _, _, _, flag in frames]

    predicted = [model.classify(rgb) for _, rgb, _, _ in frames]
    stages = stagewise_masks(predicted, demo_flags, params)

    suffix = episode_name.replace("episode_", "ep")
    out_path = Path(out_dir) / f"{task}_{suffix}_walkthrough.mp4"
    canvas = WalkthroughCanvas()
    writer = _open_writer(out_path, canvas.width, canvas.height, fps)
    assert writer.stdin is not None
    try:
        for index, (_, rgb, _, _) in enumerate(frames):
            image = canvas.render_frame(
                task,
                episode_name,
                difficulty,
                index,
                len(frames),
                rgb,
                truth[index],
                predicted[index],
                [stage[index] for stage in stages],
            )
            writer.stdin.write(image.tobytes())
    finally:
        writer.stdin.close()
        code = writer.wait()
    if code != 0:
        raise RuntimeError(f"{out_path}: ffmpeg 退出码 {code}")

    # 代表帧：与出图时代同一套选帧规则，留着与旧报告对拍（不再影响出什么内容）
    index, false_object = _pick_frame(stages[-1], truth)
    smooth_delta = [
        int(later.sum()) - int(earlier.sum())
        for earlier, later in zip(stages[2], stages[3])
    ]
    return {
        "task": task,
        "episode": episode_name,
        "难度": difficulty,
        "frames": len(frames),
        "视频": out_path.name,
        "整段误标物体": int(
            sum((mask & (gt == CLASS_OBJECT)).sum() for mask, gt in zip(stages[-1], truth))
        ),
        # ③ 时间平滑在整段上补了像素的帧数：出视频之后这条实证不再依赖单帧运气
        "时间平滑补像素帧数": int(sum(1 for value in smooth_delta if value > 0)),
        "走查帧": index,
        "该帧误标物体": false_object,
        "该帧各阶段像素数": {
            name: int(stage[index].sum()) for name, stage in zip(STAGE_NAMES, stages)
        },
        "该帧最终标定": int(stages[-1][index].sum()),
        # ③ 时间平滑相对 ② 的增量：为正即「多数表决补了像素」，是 ③ 非单调的直接证据。
        # 报告里「时间平滑真的会补像素」那条实证就读这个字段，不许凭印象写。
        "该帧时间平滑增量": smooth_delta[index],
    }


def _parse_episodes(spec: str) -> list[int]:
    """解析 `--episodes`：`0-5` 区间、`0,3,7` 列表，两种写法可混用（`0-2,7`）。"""
    numbers: list[int] = []
    for piece in spec.split(","):
        piece = piece.strip()
        if not piece:
            continue
        if "-" in piece:
            low, _, high = piece.partition("-")
            start, stop = int(low), int(high)
            if stop < start:
                raise ValueError(f"episode 区间上界小于下界：{piece}")
            numbers.extend(range(start, stop + 1))
        else:
            numbers.append(int(piece))
    if not numbers:
        raise ValueError(f"没有解析出任何 episode：{spec!r}")
    return sorted(dict.fromkeys(numbers))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--h5",
        nargs="+",
        default=["artifacts/generated/v4seg-16env-val20ep/record_dataset_*.h5"],
        help="h5 路径或 glob（默认 val split 的 v4seg 数据集）",
    )
    parser.add_argument(
        "--model",
        default=str(SCRIPT_DIR / "outputs" / "color_model.npz"),
        help="fit_color_model.py 产出的颜色表",
    )
    parser.add_argument(
        "--episodes",
        default="0-5",
        help="走查用的 episode，支持 `0-5` 区间与 `0,3,7` 列表（默认 ep0-5）",
    )
    parser.add_argument(
        "--out",
        default=str(SCRIPT_DIR / "outputs" / "walkthrough_val_ep0-5"),
        help="产物目录",
    )
    parser.add_argument("--fps", type=int, default=10, help="输出视频帧率")
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
    episodes = _parse_episodes(args.episodes)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"分割走查视频：{len(paths)} 个任务 × {len(episodes)} 个 episode "
        f"= {len(paths) * len(episodes)} 段，{args.fps} fps，并行 {args.workers}"
    )

    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                process_task,
                str(path),
                f"episode_{number}",
                args.model,
                str(out_dir),
                params,
                args.fps,
            )
            for path in paths
            for number in episodes
        ]
        for future in as_completed(futures):
            records.append(future.result())
    elapsed = time.perf_counter() - started

    records.sort(key=lambda item: (item["task"], int(item["episode"].split("_")[1])))
    payload = {
        "参数": {
            "颜色表": args.model,
            "episodes": [f"episode_{number}" for number in episodes],
            "帧率": args.fps,
            "判别规则": "纯支撑三段式判据：N0>0 判背景 / N1=0 且 N2>0 判臂 / 其余判混合（唯一口径，无开关）",
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
            f"{record['视频']}: 难度 {record['难度']}，{record['frames']} 帧，"
            f"整段误标物体 {record['整段误标物体']} px，"
            f"③ 时间平滑补像素 {record['时间平滑补像素帧数']}/{record['frames']} 帧"
        )
    grew = [item for item in records if item["时间平滑补像素帧数"] > 0]
    print(
        f"③ 时间平滑在 {len(grew)}/{len(records)} 段视频里**补过**像素"
        "（多数表决非单调的直接证据；④ 白名单交把它兜回来）"
    )
    print(f"共 {len(records)} 段视频 → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
