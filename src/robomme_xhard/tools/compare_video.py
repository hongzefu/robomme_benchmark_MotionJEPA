"""对比视频：每个“任务＋母 seed”一段，母档与五个 difficulty 六栏同屏，接成一个 MP4。

口径（计划首页“视频怎么比较”）：
- 六栏依次为母档、xhard12、xhard14、xhard16、xhard18、xhard20；统一尺寸与帧率，从 t=0 原速播放，
  不做时间拉伸（每个输出帧对应每栏的同一个 timestep 下标）。
- 短轨迹播完后停在末帧并标“结束”；缺档（配置表里没有该档）标“缺档”，失败标“失败”，
  有效档但没有任何产物标“无产物”；一律不用其他档补位。
- 各段按 TASK_ORDER、再按母 seed 顺序（给 --seeds 时按清单 rank，否则 seed 升序）接成一个 MP4。

帧来源：优先读 H5 ``episode_<E>/timestep_<i>/obs/front_rgb``（256×256×3 uint8，无叠字）；
没有 H5 时读生成器保存的 mp4（成功视频或 ``FAILED_`` 视频）。只读已有产物，不重放仿真。
依赖：h5py、imageio（imageio-ffmpeg 写 libx264）、cv2（缩放）、PIL（中文标注；找不到中文字体时退回英文标注）。

用法::

    python -m robomme_xhard.tools.compare_video --root <输出根> --out <总对比.mp4> [--seeds <清单.json>]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np

from ..configs import SOURCE_DIFFICULTY, TASK_ORDER, TIER_CONFIGS
from .layout import LEVELS, MOTHER, Artifact, episode_group, read_run_results, scan, task_rank

DEFAULT_FPS = 30  # RecordWrapper._video_write_mp4 的 fps
DEFAULT_PANEL = 256  # 官方 front_rgb 分辨率
TITLE_H = 40
LABEL_H = 24

# 状态
OK = "ok"
FAILED = "failed"
MISSING = "missing"  # 配置表里没有该档
ABSENT = "absent"  # 有效档但没有任何产物

TAG_TEXT = {"end": "结束", FAILED: "失败", MISSING: "缺档", ABSENT: "无产物"}
TAG_TEXT_ASCII = {"end": "END", FAILED: "FAILED", MISSING: "NO TIER", ABSENT: "NO OUTPUT"}

FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
)


# ---------------------------------------------------------------- 帧源


class ArraySource:
    """内存帧序列（测试与小数据用）。"""

    def __init__(self, frames: Sequence[np.ndarray]):
        self._frames = list(frames)

    def __len__(self) -> int:
        return len(self._frames)

    def frame(self, index: int) -> np.ndarray:
        return self._frames[index]

    def close(self) -> None:
        pass


class H5Source:
    """按下标逐帧读 H5 的 obs/front_rgb，不整段载入内存。"""

    def __init__(self, path: Path, episode: int | None = None, key: str = "front_rgb"):
        import h5py

        self._handle = h5py.File(path, "r")
        group = episode_group(self._handle, episode)
        if group is None:
            self._handle.close()
            raise ValueError(f"{path}: 没有 episode 组")
        self._group = group
        self._key = key
        self._keys = sorted(
            (k for k in group.keys() if k.startswith("timestep_")),
            key=lambda k: int(k.split("_", 1)[1]),
        )

    def __len__(self) -> int:
        return len(self._keys)

    def frame(self, index: int) -> np.ndarray:
        return np.asarray(self._group[self._keys[index]]["obs"][self._key][()])

    def close(self) -> None:
        self._handle.close()


class Mp4Source:
    """顺序读 mp4；只支持下标递增访问（合成时 t 单调递增）。"""

    def __init__(self, path: Path):
        import imageio.v2 as imageio

        self._reader = imageio.get_reader(str(path))
        self._length = self._reader.count_frames()
        self._iter = iter(self._reader)
        self._pos = -1
        self._last: np.ndarray | None = None

    def __len__(self) -> int:
        return self._length

    def frame(self, index: int) -> np.ndarray:
        while self._pos < index:
            try:
                self._last = next(self._iter)
            except StopIteration:
                break
            self._pos += 1
        if self._last is None:
            raise IndexError(index)
        return self._last

    def close(self) -> None:
        self._reader.close()


# ---------------------------------------------------------------- 栏与状态


@dataclass
class Column:
    label: str
    status: str
    source: object | None = None

    @property
    def length(self) -> int:
        return len(self.source) if self.source is not None else 0


def column_state(column: Column, t: int) -> tuple[str, int | None]:
    """第 t 帧该栏显示什么：("play", t) / ("end", 末帧下标) / ("blank", None)。"""
    n = column.length
    if n == 0:
        return "blank", None
    if t < n:
        return "play", t
    return "end", n - 1


def segment_length(columns: Sequence[Column]) -> int:
    return max([c.length for c in columns] + [1])


def level_label(task: str, level: str) -> str:
    if level == MOTHER:
        return f"母档 {SOURCE_DIFFICULTY.get(task, 'hard')}"
    return level


def build_columns(
    task: str,
    seed: int,
    artifacts: dict[tuple[str, int, str], Artifact],
    results: dict[tuple[str, int, str], dict] | None = None,
) -> list[Column]:
    """按 LEVELS 顺序建六栏；只用本 (task, seed, level) 自己的产物，不跨档补位。

    ``results`` 是 ``layout.read_run_results`` 读出的生成器结果（run_summary.json cards[] 优先）：
    其中 ok=false 的卡一律标“失败”（有 FAILED_ 视频就播，没有任何产物也标“失败”而不是“无产物”）。
    """
    results = results or {}
    columns = []
    for level in LEVELS:
        label = level_label(task, level)
        if level != MOTHER and level not in TIER_CONFIGS.get(task, {}):
            columns.append(Column(label, MISSING))
            continue
        art = artifacts.get((task, seed, level))
        rec = results.get((task, seed, level))
        failed = rec is not None and not rec.get("ok")
        if art is None:
            columns.append(Column(label, FAILED if failed else ABSENT))
            continue
        if art.h5 is not None and not failed:
            try:
                columns.append(Column(label, OK, H5Source(art.h5, art.episode)))
                continue
            except Exception:
                pass
        video = _open_mp4(art.video) if not failed else None
        if video is not None:
            columns.append(Column(label, OK, video))
            continue
        failed_video = _open_mp4(art.failed_video)
        if failed_video is not None:
            columns.append(Column(label, FAILED, failed_video))
        else:
            columns.append(Column(label, FAILED if (failed or art.h5 is not None or art.failed_video is not None) else ABSENT))
    return columns


def _open_mp4(path: Path | None) -> Mp4Source | None:
    """打不开（缺文件、空文件、损坏）就返回 None，由调用方按状态标注，不让整支视频失败。"""
    if path is None:
        return None
    try:
        return Mp4Source(path)
    except Exception:
        return None


# ---------------------------------------------------------------- 绘制


class _Painter:
    def __init__(self):
        self.font_path = None
        try:
            from PIL import ImageFont  # noqa: F401

            for path in FONT_CANDIDATES:
                if Path(path).exists():
                    self.font_path = path
                    break
        except Exception:
            self.font_path = None
        self._fonts: dict[int, object] = {}

    @property
    def cjk(self) -> bool:
        return self.font_path is not None

    def tag(self, key: str) -> str:
        return (TAG_TEXT if self.cjk else TAG_TEXT_ASCII)[key]

    def text(self, img: np.ndarray, xy: tuple[int, int], text: str, size: int, color=(255, 255, 255)) -> np.ndarray:
        if self.cjk:
            from PIL import Image, ImageDraw, ImageFont

            font = self._fonts.get(size)
            if font is None:
                font = self._fonts[size] = ImageFont.truetype(self.font_path, size)
            pil = Image.fromarray(img)
            ImageDraw.Draw(pil).text(xy, text, font=font, fill=color)
            return np.asarray(pil).copy()
        import cv2

        ascii_text = text.encode("ascii", "replace").decode("ascii")
        cv2.putText(img, ascii_text, (xy[0], xy[1] + size), cv2.FONT_HERSHEY_SIMPLEX, size / 30, color, 1, cv2.LINE_AA)
        return img


def fit_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """等比缩放后居中黑边，统一显示尺寸（渲染帧缩放，不受 patch 特征图最近邻约束）。"""
    import cv2

    frame = np.asarray(frame)
    if frame.ndim == 2:
        frame = np.repeat(frame[..., None], 3, axis=2)
    frame = frame[..., :3].astype(np.uint8, copy=False)
    h, w = frame.shape[:2]
    scale = min(width / w, height / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = frame if (nw, nh) == (w, h) else cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    y0, x0 = (height - nh) // 2, (width - nw) // 2
    canvas[y0 : y0 + nh, x0 : x0 + nw] = resized
    return canvas


def _text_into(canvas: np.ndarray, painter: _Painter, x: int, y: int, w: int, h: int, text: str, size: int, color=(255, 255, 255)) -> None:
    """只在 canvas 的一个小矩形内画字（避免整帧来回转换）。"""
    H, W = canvas.shape[:2]
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x or y1 <= y:
        return
    crop = np.ascontiguousarray(canvas[y:y1, x:x1])
    canvas[y:y1, x:x1] = painter.text(crop, (0, 0), text, size, color)


def render_header(columns: Sequence[Column], title: str, panel: int, painter: _Painter) -> np.ndarray:
    """每段只画一次的静态表头：标题底色 + 各栏档名。"""
    width = panel * len(columns)
    header = np.zeros((TITLE_H + LABEL_H, width, 3), dtype=np.uint8)
    header[:TITLE_H] = (30, 30, 30)
    for i, col in enumerate(columns):
        x0 = i * panel
        header[TITLE_H:, x0 : x0 + panel] = (60, 60, 60)
        _text_into(header, painter, x0 + 6, TITLE_H + 2, panel - 8, LABEL_H - 2, col.label, 16)
    return header


def compose_frame(
    columns: Sequence[Column],
    t: int,
    title: str,
    panel: int = DEFAULT_PANEL,
    painter: _Painter | None = None,
    header: np.ndarray | None = None,
) -> np.ndarray:
    painter = painter or _Painter()
    if header is None:
        header = render_header(columns, title, panel, painter)
    width = panel * len(columns)
    top = TITLE_H + LABEL_H
    canvas = np.zeros((top + panel, width, 3), dtype=np.uint8)
    canvas[:top] = header
    _text_into(canvas, painter, 8, 8, width - 16, TITLE_H - 10, f"{title}  t={t}", 20)
    for i, col in enumerate(columns):
        x0 = i * panel
        state, index = column_state(col, t)
        if state == "blank":
            canvas[top:, x0 : x0 + panel] = (90, 90, 90)
            key = col.status if col.status != OK else ABSENT
            _text_into(canvas, painter, x0 + 10, top + max(4, panel // 2 - 14), panel - 12, 32, painter.tag(key), 24, (255, 220, 0))
        else:
            canvas[top:, x0 : x0 + panel] = fit_frame(col.source.frame(index), panel, panel)
            tags = []
            if col.status == FAILED:
                tags.append(painter.tag(FAILED))
            if state == "end":
                tags.append(painter.tag("end"))
            if tags:
                # 标注底下压暗一条，保证在任何画面上都看得清
                band = canvas[top + 4 : top + 32, x0 + 2 : x0 + panel - 2]
                band[:] = (band.astype(np.uint16) * 3 // 10).astype(np.uint8)
                _text_into(canvas, painter, x0 + 6, top + 6, panel - 8, 26, " ".join(tags), 20, (255, 60, 60))
        # 栏间分隔线
        canvas[top:, x0 : x0 + 1] = (0, 0, 0)
    return canvas


def iter_segment_frames(
    columns: Sequence[Column],
    title: str,
    panel: int = DEFAULT_PANEL,
    painter: _Painter | None = None,
) -> Iterator[np.ndarray]:
    painter = painter or _Painter()
    header = render_header(columns, title, panel, painter)
    for t in range(segment_length(columns)):
        yield compose_frame(columns, t, title, panel, painter, header)


# ---------------------------------------------------------------- 段顺序与主流程


def segment_keys(
    artifacts: dict, manifest: dict | None, results: dict | None = None
) -> list[tuple[str, int, int | None]]:
    """返回 [(task, seed, episode)]：有清单按 TASK_ORDER→rank，否则按扫描到的产物与结果记录 TASK_ORDER→seed。"""
    if manifest:
        out = []
        for task in TASK_ORDER:
            entries = sorted(manifest.get("tasks", {}).get(task, []), key=lambda e: e.get("rank", 0))
            out.extend((task, int(e["seed"]), int(e["episode"])) for e in entries)
        return out
    pairs = {}
    for (task, seed, _level), art in artifacts.items():
        pairs.setdefault((task, seed), art.episode)
    for (task, seed, _level), rec in (results or {}).items():
        if pairs.get((task, seed)) is None:
            pairs[(task, seed)] = rec.get("episode")
    return [(t, s, e) for (t, s), e in sorted(pairs.items(), key=lambda kv: (task_rank(kv[0][0]), kv[0][1]))]


def render(root: Path, out: Path, manifest: dict | None = None, fps: int = DEFAULT_FPS, panel: int = DEFAULT_PANEL) -> dict:
    import imageio.v2 as imageio

    artifacts = scan(root)
    results, _source = read_run_results(root)
    painter = _Painter()
    segments = segment_keys(artifacts, manifest, results)
    out.parent.mkdir(parents=True, exist_ok=True)
    stats = {"segments": 0, "frames": 0, "cjk_font": painter.font_path}
    with imageio.get_writer(str(out), fps=fps, codec="libx264", quality=8, macro_block_size=16) as writer:
        for task, seed, episode in segments:
            columns = build_columns(task, seed, artifacts, results)
            n = TASK_ORDER.index(task) + 1 if task in TASK_ORDER else 0
            title = f"{n:02d} {task}  seed={seed}  ep={episode}"
            try:
                for frame in iter_segment_frames(columns, title, panel, painter):
                    writer.append_data(frame)
                    stats["frames"] += 1
            finally:
                for col in columns:
                    if col.source is not None:
                        col.source.close()
            stats["segments"] += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="xhard 六栏同屏对比视频（只读已有产物）")
    parser.add_argument("--root", required=True, help="输出根，含 mother/ 与 xhard12..20/")
    parser.add_argument("--out", required=True, help="输出 MP4")
    parser.add_argument("--seeds", default=None, help="母 seed 清单 JSON（决定段顺序，缺产物也出段）")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--panel", type=int, default=DEFAULT_PANEL, help="每栏边长（像素，宜为 16 的倍数）")
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.seeds).read_text(encoding="utf-8")) if args.seeds else None
    stats = render(Path(args.root), Path(args.out), manifest, args.fps, args.panel)
    print(f"COMPARE_VIDEO=PASS segments={stats['segments']} frames={stats['frames']} out={args.out} cjk_font={stats['cjk_font']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
