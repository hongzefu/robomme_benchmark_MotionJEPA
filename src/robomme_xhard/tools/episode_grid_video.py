"""逐 episode 拼接视频：每个“任务＋母 episode/seed”一支 MP4，2 列 × 3 行同屏放原版录像。

口径（用户 2026-10-12 确认）：
- 帧源只读录像器 ``RecordWrapper`` 写出的原版 mp4（含 goal 文本、PLANNER/ONLINE 两行、每行 5 个画面
  含分割图、演示段红框）；分割图没有存进 H5，所以绝不从 H5 重画，只做拼接。
- 文件名规则见 ``RecordWrapper._video_build_filename_parts`` / ``_video_flush_episode_files``：
  ``<Task>_ep<E>_seed<S>_<difficulty>_<goal...>.mp4``；``success_NO_OBJECT_`` 与 ``FAILED_NO_OBJECT_``
  一律排除；``FAILED_`` 只在该档没有成功视频时作为“失败”格的帧源。同一档匹配到多个候选即报错，不猜。
- 布局固定：第 1 行 母档 | xhard12；第 2 行 xhard14 | xhard16；第 3 行 xhard18 | xhard20。
  配置表 ``TIER_CONFIGS`` 里没有该档 → 灰底 ``MISSING TIER``；有档但没有产物 → 灰底 ``NO OUTPUT``。
- 每格放原版帧原样，不缩放、不裁剪；不足全视频统一格子尺寸（所有格最大高宽）的部分在下方 / 右侧补黑边。
- 每格上方标签栏直接调用原版 ``RecordWrapper._add_text_to_frame``（未绑定调用，self=None）。
  cv2.putText 不支持中文与“·”，标签一律 ASCII，用 `` | `` 分隔。
- 时间轴：各格从第 0 帧同步原速播放，不拉伸；短的放完停在末帧并在标签追加 ``ENDED``；
  总长 = 最长一格的帧数。
- 写出调用原版 ``RecordWrapper._video_write_mp4``（fps=30、libx264、quality=8），传帧生成器，逐帧流式。
  整幅画面在右侧 / 下方补黑边到 16 的倍数，避免 imageio-ffmpeg 的 macro_block_size 自动缩放。

只读产物，不重放仿真，不改 ``src/robomme/``。

用法::

    python -m robomme_xhard.tools.episode_grid_video --root <输出根> --out-dir <目录> \
        [--seeds <母 seed 清单.json>] [--task <Task>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import numpy as np

from ..configs import SOURCE_DIFFICULTY, TASK_ORDER, TIER_CONFIGS

MOTHER = "mother"
# 2 列 × 3 行，按行优先排列的固定位置
GRID_LEVELS: tuple[str, ...] = (MOTHER, "xhard12", "xhard14", "xhard16", "xhard18", "xhard20")
GRID_COLS = 2
GRID_ROWS = 3

# 官网编号（AGENTS.md P6）
TASK_NUMBERS: dict[str, str] = {
    "BinFill": "1.1",
    "PickXtimes": "1.2",
    "SwingXtimes": "1.3",
    "StopCube": "1.4",
    "VideoUnmask": "2.1",
    "ButtonUnmask": "2.2",
    "VideoUnmaskSwap": "2.3",
    "ButtonUnmaskSwap": "2.4",
    "PickHighlight": "3.1",
    "VideoRepick": "3.2",
    "VideoPlaceButton": "3.3",
    "VideoPlaceOrder": "3.4",
    "MoveCube": "4.1",
    "InsertPeg": "4.2",
    "PatternLock": "4.3",
    "RouteStick": "4.4",
}
assert tuple(TASK_NUMBERS) == TASK_ORDER, "编号表顺序必须与 configs.TASK_ORDER 一致"

# 格子状态
OK = "ok"
FAILED = "failed"
MISSING = "missing"  # 配置表里没有该档
ABSENT = "absent"  # 有效档但没有任何产物

STATUS_TEXT = {FAILED: "FAILED", MISSING: "MISSING TIER", ABSENT: "NO OUTPUT"}
ENDED_TEXT = "ENDED"
GRAY = 96
MACRO_BLOCK = 16

VIDEO_NAME_RE = re.compile(
    r"^(?P<failed>FAILED_)?(?P<task>[A-Za-z]+?)(?:XHard)?_ep(?P<episode>\d+)_seed(?P<seed>\d+)"
    r"(?P<recover>_FailRecover(?:XY|Z)?)?_(?P<suffix>.+)\.mp4$"
)


# ---------------------------------------------------------------- 原版函数


def _record_wrapper():
    from robomme.env_record_wrapper.RecordWrapper import RobommeRecordWrapper as RecordWrapper

    return RecordWrapper


def add_label(frame: np.ndarray, text) -> np.ndarray:
    """原版标签栏：未绑定调用 RecordWrapper._add_text_to_frame（不依赖实例状态）。"""
    return _record_wrapper()._add_text_to_frame(None, frame, text)


def write_mp4(frames, output_path: Path) -> None:
    """原版写出：未绑定调用 RecordWrapper._video_write_mp4（fps=30、libx264、quality=8）。"""
    _record_wrapper()._video_write_mp4(None, frames, Path(output_path))


# ---------------------------------------------------------------- 产物发现


def expected_difficulty(task: str, level: str) -> str:
    return SOURCE_DIFFICULTY.get(task, "hard") if level == MOTHER else level


def tier_exists(task: str, level: str) -> bool:
    if level == MOTHER:
        return task in TASK_ORDER
    return level in TIER_CONFIGS.get(task, {})


def _ignored(name: str) -> bool:
    return name.startswith("success_NO_OBJECT_") or name.startswith("FAILED_NO_OBJECT_")


@dataclass
class Unit:
    """一支输出视频：任务 + 母 episode + seed。"""

    task: str
    episode: int
    seed: int
    cards: dict[str, dict] = field(default_factory=dict)  # level -> run_summary card
    videos: dict[str, list[Path]] = field(default_factory=dict)  # level -> 成功视频候选
    failed_videos: dict[str, list[Path]] = field(default_factory=dict)  # level -> FAILED_ 候选


def _level_of_card(card: dict) -> str | None:
    if card.get("role") == MOTHER:
        return MOTHER
    diff = card.get("difficulty")
    return diff if diff in GRID_LEVELS else None


def discover(root: Path) -> dict[tuple[str, int, int], Unit]:
    """扫描输出根的视频与 run_summary.json，按 (task, episode, seed) 归组。"""
    root = Path(root)
    units: dict[tuple[str, int, int], Unit] = {}

    def unit(task: str, episode: int, seed: int) -> Unit:
        key = (task, episode, seed)
        if key not in units:
            units[key] = Unit(task=task, episode=episode, seed=seed)
        return units[key]

    summary = root / "run_summary.json"
    if summary.is_file():
        payload = json.loads(summary.read_text(encoding="utf-8"))
        for card in payload.get("cards", []):
            level = _level_of_card(card)
            if level is None or card.get("task") not in TASK_ORDER:
                continue
            u = unit(card["task"], int(card["mother_episode"]), int(card["seed"]))
            if level in u.cards:
                raise ValueError(f"run_summary 中 {card['task']} ep{u.episode} seed{u.seed} {level} 出现多张卡片")
            u.cards[level] = card

    for level in GRID_LEVELS:
        vdir = root / level / "videos"
        if not vdir.is_dir():
            continue
        for path in sorted(vdir.glob("*.mp4")):
            if _ignored(path.name):
                continue
            m = VIDEO_NAME_RE.match(path.name)
            if not m or m["task"] not in TASK_ORDER:
                continue
            diff = expected_difficulty(m["task"], level)
            if not m["suffix"].startswith(diff + "_") and m["suffix"] != diff:
                raise ValueError(f"{path} 的难度标签与目录 {level}（应为 {diff}）不符")
            u = unit(m["task"], int(m["episode"]), int(m["seed"]))
            bucket = u.failed_videos if m["failed"] else u.videos
            bucket.setdefault(level, []).append(path)
    return units


# ---------------------------------------------------------------- 格子


class FrameStream:
    """逐帧流式读取一支 mp4（预读一帧以便判断是否已到末尾）；读完后停在末帧。"""

    def __init__(self, path: Path):
        import imageio

        self.path = Path(path)
        self._reader = imageio.get_reader(self.path.as_posix())
        self._iter = iter(self._reader)
        self.count = 0  # 已交出的真实帧数
        self._next = self._read()
        if self._next is None:
            self.close()
            raise ValueError(f"{path} 没有任何帧")
        self.last = self._next

    def _read(self):
        if self._reader is None:
            return None
        frame = next(self._iter, None)
        if frame is None:
            self.close()
            return None
        return np.asarray(frame)

    @property
    def shape(self) -> tuple[int, int]:
        return int(self.last.shape[0]), int(self.last.shape[1])

    @property
    def has_more(self) -> bool:
        return self._next is not None

    def next(self) -> tuple[np.ndarray, bool]:
        """返回 (帧, 是否已结束)；结束后反复返回末帧。"""
        if self._next is None:
            return self.last, True
        self.last = self._next
        self.count += 1
        self._next = self._read()
        return self.last, False

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None


@dataclass
class Cell:
    level: str
    status: str
    label: str
    stream: FrameStream | None = None


def _fmt_ratio(value: float) -> str:
    return f"x{value:.2f}"


def build_cells(u: Unit) -> list[Cell]:
    mother_card = u.cards.get(MOTHER)
    mother_ts = mother_card.get("timesteps") if mother_card and mother_card.get("ok") else None
    cells: list[Cell] = []
    for level in GRID_LEVELS:
        name = f"{MOTHER} ({expected_difficulty(u.task, MOTHER)})" if level == MOTHER else level
        if not tier_exists(u.task, level):
            cells.append(Cell(level, MISSING, f"{name} | {STATUS_TEXT[MISSING]}"))
            continue
        ok_cands = u.videos.get(level, [])
        fail_cands = u.failed_videos.get(level, [])
        if len(ok_cands) > 1:
            raise ValueError(f"{u.task} ep{u.episode} seed{u.seed} {level} 匹配到多个成功视频：{ok_cands}")
        if len(fail_cands) > 1 and not ok_cands:
            raise ValueError(f"{u.task} ep{u.episode} seed{u.seed} {level} 匹配到多个 FAILED_ 视频：{fail_cands}")
        card = u.cards.get(level)
        parts = [name]
        if ok_cands:
            status, path = OK, ok_cands[0]
        elif fail_cands:
            status, path = FAILED, fail_cands[0]
        elif card is not None and not card.get("ok"):
            status, path = FAILED, None
        else:
            status, path = ABSENT, None
        ts = card.get("timesteps") if card else None
        if status == OK and ts:
            parts.append(f"{ts} timestep")
            if level != MOTHER and mother_ts:
                parts.append(_fmt_ratio(ts / mother_ts))
        if status != OK:
            parts.append(STATUS_TEXT[status])
        stream = FrameStream(path) if path is not None else None
        cells.append(Cell(level, status, " | ".join(parts), stream))
    return cells


# ---------------------------------------------------------------- 拼接


def _pad(frame: np.ndarray, h: int, w: int, value: int = 0) -> np.ndarray:
    fh, fw = frame.shape[:2]
    if fh > h or fw > w:
        raise ValueError(f"帧尺寸 {fh}x{fw} 超过格子尺寸 {h}x{w}")
    if (fh, fw) == (h, w):
        return frame
    out = np.full((h, w, 3), value, dtype=np.uint8)
    out[:fh, :fw] = frame[..., :3]
    return out


def _round_up(x: int, m: int = MACRO_BLOCK) -> int:
    return (x + m - 1) // m * m


def _gray_body(h: int, w: int, text: str) -> np.ndarray:
    import cv2

    body = np.full((h, w, 3), GRAY, dtype=np.uint8)
    font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 1.2, 2
    (tw, th), _ = cv2.getTextSize(text, font, scale, thick)
    cv2.putText(body, text, (max(0, (w - tw) // 2), (h + th) // 2), font, scale, (255, 255, 255), thick)
    return body


def grid_geometry(cells: list[Cell]) -> tuple[int, int, int]:
    """返回 (格子高, 格子宽, 标签栏高)：格子取所有视频首帧的最大高宽；标签栏高度对所有格
    （含追加 ENDED 的情形）用原版函数渲染一次取最大，保证格子尺寸全程不变。"""
    shapes = [c.stream.shape for c in cells if c.stream is not None]
    if shapes:
        cell_h = max(s[0] for s in shapes)
        cell_w = max(s[1] for s in shapes)
    else:
        cell_h, cell_w = 256, 256
    probe = np.zeros((1, cell_w, 3), dtype=np.uint8)
    label_h = 0
    for c in cells:
        for text in (c.label, f"{c.label} | {ENDED_TEXT}"):
            label_h = max(label_h, add_label(probe, text).shape[0] - 1)
    return cell_h, cell_w, label_h


def labeled_box(body: np.ndarray, label: str, label_h: int) -> np.ndarray:
    """原版函数在 body 上方叠标签栏；标签栏下方补黑到统一的 label_h，使各格画面顶边对齐。"""
    stacked = add_label(body, label)
    text_h = stacked.shape[0] - body.shape[0]
    if text_h > label_h:
        raise ValueError(f"标签栏高 {text_h} 超过统一高度 {label_h}")
    box = np.zeros((label_h + body.shape[0], body.shape[1], 3), dtype=np.uint8)
    box[:text_h] = stacked[:text_h]
    box[label_h:] = body
    return box


def compose_frames(cells: list[Cell]) -> Iterator[np.ndarray]:
    """逐帧生成拼接画面；总长 = 最长一格的帧数。"""
    cell_h, cell_w, label_h = grid_geometry(cells)
    box_h = cell_h + label_h
    out_h = _round_up(box_h * GRID_ROWS)
    out_w = _round_up(cell_w * GRID_COLS)

    static: dict[int, np.ndarray] = {}
    for i, c in enumerate(cells):
        if c.stream is None:
            body = _gray_body(cell_h, cell_w, STATUS_TEXT.get(c.status, c.status))
            static[i] = labeled_box(body, c.label, label_h)

    yielded = 0
    try:
        while True:
            # 全部格都没有视频时仍出 1 帧，避免写出空文件
            if yielded and not any(c.stream is not None and c.stream.has_more for c in cells):
                break
            boxes = []
            for i, c in enumerate(cells):
                if c.stream is None:
                    boxes.append(static[i])
                    continue
                frame, ended = c.stream.next()
                label = f"{c.label} | {ENDED_TEXT}" if ended else c.label
                body = _pad(np.asarray(frame)[..., :3], cell_h, cell_w)
                boxes.append(labeled_box(body, label, label_h))
            canvas = np.zeros((out_h, out_w, 3), dtype=np.uint8)
            for i, box in enumerate(boxes):
                r, col = divmod(i, GRID_COLS)
                canvas[r * box_h : (r + 1) * box_h, col * cell_w : (col + 1) * cell_w] = box
            yielded += 1
            yield canvas
    finally:
        for c in cells:
            if c.stream is not None:
                c.stream.close()


def output_name(u: Unit) -> str:
    return f"{TASK_NUMBERS[u.task]}_{u.task}_ep{u.episode}_seed{u.seed}.mp4"


def _manifest_keys(manifest: dict) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for task, entries in manifest.get("tasks", {}).items():
        for e in entries:
            keys.add((task, int(e["seed"])))
    return keys


def render_all(root: Path, out_dir: Path, manifest: dict | None = None, task: str | None = None) -> dict:
    units = discover(root)
    selected = []
    allowed = _manifest_keys(manifest) if manifest is not None else None
    for key in sorted(units, key=lambda k: (TASK_ORDER.index(k[0]), k[1], k[2])):
        u = units[key]
        if task is not None and u.task != task:
            continue
        if allowed is not None and (u.task, u.seed) not in allowed:
            continue
        selected.append(u)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = {"videos": 0, "cells": 0, "missing": 0, "frames": 0, "outputs": []}
    for u in selected:
        cells = build_cells(u)
        out = out_dir / output_name(u)
        counter = {"n": 0}

        def counted(gen):
            for frame in gen:
                counter["n"] += 1
                yield frame

        write_mp4(counted(compose_frames(cells)), out)
        stats["videos"] += 1
        stats["cells"] += len(cells)
        stats["missing"] += sum(1 for c in cells if c.status in (MISSING, ABSENT))
        stats["frames"] += counter["n"]
        stats["outputs"].append(str(out))
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="逐 episode 2x3 拼接原版录像（只读已有产物）")
    parser.add_argument("--root", required=True, help="输出根，含 mother/ 与 xhard12..20/ 及 run_summary.json")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    parser.add_argument("--seeds", default=None, help="母 seed 清单 JSON（只出清单内的 seed）")
    parser.add_argument("--task", default=None, choices=TASK_ORDER, help="只出某一个任务")
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.seeds).read_text(encoding="utf-8")) if args.seeds else None
    stats = render_all(Path(args.root), Path(args.out_dir), manifest, args.task)
    for path in stats["outputs"]:
        print(path)
    print(
        f"EPISODE_GRID_VIDEO=PASS videos={stats['videos']} cells={stats['cells']} missing={stats['missing']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
