"""逐 episode 一字横排视频：每个“任务＋母 episode/seed”一支 MP4，六列横排只放前视相机画面。

口径（用户 2026-10-12：「最左边第一张图片然后上方放上goal在goal上方再放上当的难度梯度表和对应的
难度梯度旋钮 然后一字排开 横向放置」；追加「难度旋钮用中文表示」）：
- 六列顺序固定：母档、xhard12、xhard14、xhard16、xhard18、xhard20。配置表 ``TIER_CONFIGS`` 里没有该档
  → 灰底“缺档”；有档没有产物 → 灰底“无产物”；run_summary 里 ok=false → 灰底“失败”。
- 画面只用前视相机：逐帧流式读 H5 ``episode_<E>/timestep_<i>/obs/front_rgb``（timestep 按整数序），
  ``<root>/<mother|xhardNN>/hdf5_files/<Task>_ep<E>_seed<S>.h5``；每列放大到 512×512（INTER_LINEAR，
  真实相机照片，不受 patch 特征图最近邻约束）。演示段（``info/is_video_demo`` 为真）调用原版
  ``RobommeRecordWrapper._add_red_border`` 加红框（未绑定调用，self=None，函数体不访问 self）。
- 每列画面上方自上而下两块文字：
  (a) 难度与旋钮行，中文，PIL + NotoSansCJK 渲染（cv2.putText 不支持中文），白字黑底；格式
      ``<档名> ｜ <旋钮中文> ｜ <timestep> 步 ｜ 母档的 <倍数> 倍``，母档为 ``母档（hard） ｜ <旋钮> ｜ <timestep> 步``；
      放完后追加 `` ｜ 结束``。行宽超出列宽时按“｜”分段折行。
  (b) 该档 goal 全文（英文，不翻译）：读 H5 ``episode_<E>/setup/task_goal`` 全部备选，交给原版
      ``RobommeRecordWrapper._add_text_to_frame`` 渲染（每条一行、超宽自动折行）。
  两块的高度都取六列最大值（含追加“结束”后的情形），不足补黑，保证各列画面顶边对齐且全程尺寸不变。
- 时间轴：各列从第 0 帧同步原速，不拉伸；短的停在末帧并追加“结束”；总长 = 最长一列。
- 写出调用原版 ``RobommeRecordWrapper._video_write_mp4``（30 fps、libx264、quality 8），传帧生成器流式写；
  画布宽高补黑到 16 的倍数，避免 imageio-ffmpeg 自动缩放。

只读产物，不重放仿真，不改 ``src/robomme/``。

用法::

    python -m robomme_xhard.tools.episode_strip_video --root <输出根> --out-dir <目录> \
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

from ..configs import MOTHER_KNOBS, SOURCE_DIFFICULTY, TASK_ORDER, TIER_CONFIGS
from .episode_grid_video import TASK_NUMBERS, _manifest_keys
from .layout import read_run_results

MOTHER = "mother"
LEVELS: tuple[str, ...] = (MOTHER, "xhard12", "xhard14", "xhard16", "xhard18", "xhard20")

OK = "ok"
FAILED = "failed"
MISSING = "missing"  # 配置表里没有该档
ABSENT = "absent"  # 有效档但没有产物
STATUS_TEXT = {FAILED: "失败", MISSING: "缺档", ABSENT: "无产物"}
ENDED_TEXT = "结束"
SEP = " ｜ "

BODY = 512  # 每列画面边长
MACRO_BLOCK = 16
GRAY = 96

FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
HEADER_FONT_SIZE = 19
HEADER_LINE_H = 26
HEADER_PAD = 8  # 文字块上下留白
STATUS_FONT_SIZE = 40

H5_NAME_RE = re.compile(r"^(?P<task>[A-Za-z]+?)(?:XHard)?_ep(?P<episode>\d+)_seed(?P<seed>\d+)\.h5$")

# knobs 键 → 中文名；按任务区分的键写成 {任务: 中文}
KNOB_NAMES: dict[str, str | dict[str, str]] = {
    "target_total": "投入方块数",
    "repeats": {"PickXtimes": "抓放次数", "SwingXtimes": "往返次数"},
    "stop_k": "第几次经过时停",
    "move_interval": "单程间隔步数",
    "pick_count": "抓容器个数",
    "swap_count": "交换次数",
    "press_count": "按按钮次数",
    "pickup": "高亮方块数",
    "spawn": "生成方块数",
    "repick_count": "重抓次数",
    "extra_groups": "额外抓放组数",
    "num_targets": "不同目标数",
    "length": {"PatternLock": "路径节点数", "RouteStick": "移动边数"},
    "grid": "网格边长",
}
EXTRA_GROUPS_NOTE = {1: "（前或后随机）", 2: "（前后各一）"}
NO_KNOB_TEXT = "无旋钮"


# ---------------------------------------------------------------- 原版函数


def _record_wrapper():
    from robomme.env_record_wrapper.RecordWrapper import RobommeRecordWrapper

    return RobommeRecordWrapper


def add_goal_text(frame: np.ndarray, lines: list[str]) -> np.ndarray:
    """原版文字区：未绑定调用 _add_text_to_frame（每条一行，超宽折行，叠在 frame 上方）。"""
    return _record_wrapper()._add_text_to_frame(None, frame, lines)


def add_red_border(frame: np.ndarray) -> np.ndarray:
    """原版演示段红框：未绑定调用 _add_red_border（只用参数 frame，不访问 self）。"""
    return _record_wrapper()._add_red_border(None, frame)


def write_mp4(frames, output_path: Path) -> None:
    """原版写出：未绑定调用 _video_write_mp4（fps=30、libx264、quality=8）。"""
    _record_wrapper()._video_write_mp4(None, frames, Path(output_path))


# ---------------------------------------------------------------- 中文渲染


class CjkPainter:
    """PIL + NotoSansCJK 渲染中文行；找不到字体直接报错，不退回英文。"""

    def __init__(self, font_path: Path = FONT_PATH):
        font_path = Path(font_path)
        if not font_path.is_file():
            raise FileNotFoundError(f"找不到中文字体 {font_path}，无法渲染中文旋钮行")
        self.font_path = font_path
        self._fonts = {}
        self.font(HEADER_FONT_SIZE)  # 提前加载，字体损坏时尽早报错

    def font(self, size: int):
        from PIL import ImageFont

        if size not in self._fonts:
            self._fonts[size] = ImageFont.truetype(str(self.font_path), size)
        return self._fonts[size]

    def width(self, text: str, size: int = HEADER_FONT_SIZE) -> int:
        return int(self.font(size).getlength(text))

    def wrap(self, segments: list[str], max_width: int) -> list[str]:
        """按“｜”分段贪心折行；单段超宽也整段放一行（不在词中间断开）。"""
        lines: list[str] = []
        cur = ""
        for seg in segments:
            cand = seg if not cur else cur + SEP + seg
            if cur and self.width(cand) > max_width:
                lines.append(cur)
                cur = seg
            else:
                cur = cand
        if cur:
            lines.append(cur)
        return lines

    def header_lines(self, segments: list[str], width: int) -> list[str]:
        return self.wrap(segments, width - 20)

    def render_header(self, lines: list[str], width: int, height: int) -> np.ndarray:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            draw.text((10, HEADER_PAD + i * HEADER_LINE_H), line, font=self.font(HEADER_FONT_SIZE), fill=(255, 255, 255))
        return np.asarray(img).copy()

    def gray_body(self, text: str, size: int = BODY) -> np.ndarray:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (size, size), (GRAY, GRAY, GRAY))
        draw = ImageDraw.Draw(img)
        font = self.font(STATUS_FONT_SIZE)
        # 错误类型可能很长，逐字符折行，避免灰底标签溢出六列版式。
        lines, current = [], ""
        for char in text:
            if current and font.getlength(current + char) > size - 32:
                lines.append(current)
                current = char
            else:
                current += char
        if current:
            lines.append(current)
        if len(lines) == 1:
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            draw.text(((size - (right - left)) // 2 - left, (size - (bottom - top)) // 2 - top), text, font=font, fill=(255, 255, 255))
            return np.asarray(img).copy()
        line_h = STATUS_FONT_SIZE + 12
        for index, line in enumerate(lines):
            left, top, right, bottom = draw.textbbox((0, 0), line, font=font)
            draw.text(((size - (right - left)) // 2 - left, (size - len(lines) * line_h) // 2 + index * line_h - top), line, font=font, fill=(255, 255, 255))
        return np.asarray(img).copy()


def header_height(n_lines: int) -> int:
    return n_lines * HEADER_LINE_H + 2 * HEADER_PAD


# ---------------------------------------------------------------- 旋钮与档名


def knob_text(task: str, knobs: dict) -> str:
    """knobs 字典 → 中文，按字典顺序用“，”连接；未知键直接报错。"""
    if not knobs:
        return NO_KNOB_TEXT
    parts = []
    for key, value in knobs.items():
        if key not in KNOB_NAMES:
            raise KeyError(f"旋钮键 {key!r}（任务 {task}）没有中文名")
        name = KNOB_NAMES[key]
        if isinstance(name, dict):
            if task not in name:
                raise KeyError(f"旋钮键 {key!r} 没有任务 {task} 的中文名")
            name = name[task]
        text = f"{name} {value}"
        if key == "extra_groups" and task == "VideoPlaceButton":
            text += EXTRA_GROUPS_NOTE.get(int(value), "")
        parts.append(text)
    return "，".join(parts)


def level_knobs(task: str, level: str) -> dict | None:
    if level == MOTHER:
        return MOTHER_KNOBS.get(task)
    tier = TIER_CONFIGS.get(task, {}).get(level)
    return None if tier is None else tier["knobs"]


def level_name(task: str, level: str) -> str:
    return f"母档（{SOURCE_DIFFICULTY.get(task, 'hard')}）" if level == MOTHER else level


def tier_exists(task: str, level: str) -> bool:
    if level == MOTHER:
        return task in TASK_ORDER
    return level in TIER_CONFIGS.get(task, {})


# ---------------------------------------------------------------- 产物发现


@dataclass
class Unit:
    task: str
    episode: int
    seed: int
    cards: dict[str, dict] = field(default_factory=dict)  # level -> run_summary card
    h5: dict[str, Path] = field(default_factory=dict)  # level -> H5 路径


def _level_of_card(card: dict) -> str | None:
    if card.get("role") == MOTHER:
        return MOTHER
    diff = card.get("difficulty")
    return diff if diff in LEVELS else None


def discover(root: Path) -> dict[tuple[str, int, int], Unit]:
    root = Path(root)
    units: dict[tuple[str, int, int], Unit] = {}

    def unit(task: str, episode: int, seed: int) -> Unit:
        key = (task, episode, seed)
        if key not in units:
            units[key] = Unit(task, episode, seed)
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
    else:
        # 没有最终汇总时仍沿统一读取链保留逐卡失败，不能误标成无产物。
        results, _ = read_run_results(root)
        for (task, seed, level), record in results.items():
            if task not in TASK_ORDER or record.get("episode") is None:
                continue
            unit(task, record["episode"], seed).cards[level] = record

    for level in LEVELS:
        hdir = root / level / "hdf5_files"
        if not hdir.is_dir():
            continue
        for path in sorted(hdir.glob("*.h5")):
            m = H5_NAME_RE.match(path.name)
            if not m or m["task"] not in TASK_ORDER:
                continue
            u = unit(m["task"], int(m["episode"]), int(m["seed"]))
            if level in u.h5:
                raise ValueError(f"{u.task} ep{u.episode} seed{u.seed} {level} 匹配到多个 H5：{u.h5[level]}、{path}")
            u.h5[level] = path
    return units


# ---------------------------------------------------------------- H5 流


def _decode(x) -> str:
    return x.decode("utf-8") if isinstance(x, (bytes, bytearray)) else str(x)


def read_goals(path: Path, episode: int) -> list[str]:
    import h5py

    with h5py.File(path, "r") as f:
        ds = f.get(f"episode_{episode}/setup/task_goal")
        if ds is None:
            return []
        raw = ds[()]
    if isinstance(raw, np.ndarray):
        return [_decode(x) for x in raw.reshape(-1)]
    return [_decode(raw)]


class H5FrameStream:
    """逐帧流式读 front_rgb；读完后停在末帧。返回已放大到 BODY 且演示段带红框的帧。"""

    def __init__(self, path: Path, episode: int):
        import h5py

        self.path = Path(path)
        self._file = h5py.File(self.path, "r")
        group_name = f"episode_{episode}"
        if group_name not in self._file:
            self.close()
            raise ValueError(f"{path} 没有 {group_name}")
        self._ep = self._file[group_name]
        steps = []
        for name in self._ep.keys():
            if name.startswith("timestep_"):
                steps.append(int(name[len("timestep_"):]))
        if not steps:
            self.close()
            raise ValueError(f"{path} 的 {group_name} 没有任何 timestep")
        self._steps = sorted(steps)
        self.length = len(self._steps)
        self._pos = 0
        self.last: np.ndarray | None = None

    @property
    def has_more(self) -> bool:
        return self._pos < self.length

    def _load(self, step: int) -> np.ndarray:
        import cv2

        g = self._ep[f"timestep_{step}"]
        frame = np.asarray(g["obs/front_rgb"][()])[..., :3].astype(np.uint8)
        frame = cv2.resize(frame, (BODY, BODY), interpolation=cv2.INTER_LINEAR)
        demo = g.get("info/is_video_demo")
        if demo is not None and bool(np.asarray(demo[()]).reshape(-1)[0]):
            frame = add_red_border(frame)
        return np.ascontiguousarray(frame)

    def next(self) -> tuple[np.ndarray, bool]:
        """返回 (帧, 是否已结束)；结束后反复返回末帧。"""
        if self._pos >= self.length:
            return self.last, True
        self.last = self._load(self._steps[self._pos])
        self._pos += 1
        if self._pos >= self.length:
            self.close()
        return self.last, False

    def close(self) -> None:
        if getattr(self, "_file", None) is not None:
            self._file.close()
            self._file = None


# ---------------------------------------------------------------- 列


@dataclass
class Column:
    level: str
    status: str
    segments: list[str]  # 难度与旋钮行的各段（不含“结束”）
    goals: list[str]
    stream: H5FrameStream | None = None
    failure_text: str | None = None


def build_columns(u: Unit) -> list[Column]:
    mother_card = u.cards.get(MOTHER)
    mother_ts = mother_card.get("timesteps") if mother_card and mother_card.get("ok") else None
    cols: list[Column] = []
    for level in LEVELS:
        name = level_name(u.task, level)
        if not tier_exists(u.task, level):
            cols.append(Column(level, MISSING, [name, STATUS_TEXT[MISSING]], []))
            continue
        segments = [name, knob_text(u.task, level_knobs(u.task, level) or {})]
        card = u.cards.get(level)
        path = u.h5.get(level)
        if card is not None and not card.get("ok"):
            error_type = card.get("error_type")
            label = f"失败：{error_type}" if error_type else STATUS_TEXT[FAILED]
            cols.append(Column(level, FAILED, segments + [label], [], failure_text=label))
            continue
        if path is None:
            cols.append(Column(level, ABSENT, segments + [STATUS_TEXT[ABSENT]], []))
            continue
        stream = H5FrameStream(path, u.episode)
        ts = card.get("timesteps") if card else None
        if not ts:
            ts = stream.length
        segments.append(f"{ts} 步")
        if level != MOTHER and mother_ts:
            segments.append(f"母档的 {ts / mother_ts:.2f} 倍")
        cols.append(Column(level, OK, segments, read_goals(path, u.episode), stream))
    return cols


# ---------------------------------------------------------------- 拼接


def _round_up(x: int, m: int = MACRO_BLOCK) -> int:
    return (x + m - 1) // m * m


def _pad_rows(img: np.ndarray, height: int) -> np.ndarray:
    if img.shape[0] > height:
        raise ValueError(f"文字区高 {img.shape[0]} 超过统一高度 {height}")
    if img.shape[0] == height:
        return img
    out = np.zeros((height, img.shape[1], 3), dtype=np.uint8)
    out[: img.shape[0]] = img[..., :3]
    return out


def goal_block(goals: list[str], width: int = BODY) -> np.ndarray:
    """原版函数渲染 goal 文字区（去掉其下方的占位行）；没有 goal 时返回 0 高。"""
    probe = np.zeros((1, width, 3), dtype=np.uint8)
    stacked = add_goal_text(probe, goals)
    return np.ascontiguousarray(stacked[:-1])


@dataclass
class Layout:
    header_h: int
    goal_h: int
    headers: list[tuple[np.ndarray, np.ndarray]]  # 每列 (未结束, 已结束) 的旋钮行图
    goals: list[np.ndarray]  # 每列已补到 goal_h 的 goal 图
    statics: dict[int, np.ndarray]  # 无画面列的灰底

    @property
    def top_h(self) -> int:
        return self.header_h + self.goal_h


def build_layout(cols: list[Column], painter: CjkPainter) -> Layout:
    line_sets = []
    for c in cols:
        normal = painter.header_lines(c.segments, BODY)
        ended = painter.header_lines(c.segments + [ENDED_TEXT], BODY) if c.stream is not None else normal
        line_sets.append((normal, ended))
    n_lines = max(max(len(a), len(b)) for a, b in line_sets)
    header_h = header_height(n_lines)
    headers = [(painter.render_header(a, BODY, header_h), painter.render_header(b, BODY, header_h)) for a, b in line_sets]
    raw_goals = [goal_block(c.goals) for c in cols]
    goal_h = max(g.shape[0] for g in raw_goals)
    goals = [_pad_rows(g, goal_h) if g.shape[0] else np.zeros((goal_h, BODY, 3), np.uint8) for g in raw_goals]
    statics = {i: painter.gray_body(c.failure_text or STATUS_TEXT[c.status]) for i, c in enumerate(cols) if c.stream is None}
    return Layout(header_h, goal_h, headers, goals, statics)


def compose_frames(cols: list[Column], painter: CjkPainter) -> Iterator[np.ndarray]:
    """逐帧生成横排画面；总长 = 最长一列的帧数。"""
    layout = build_layout(cols, painter)
    top = layout.top_h
    out_h = _round_up(top + BODY)
    out_w = _round_up(BODY * len(cols))
    yielded = 0
    try:
        while True:
            # 全部列都没有画面时仍出 1 帧，避免写出空文件
            if yielded and not any(c.stream is not None and c.stream.has_more for c in cols):
                break
            canvas = np.zeros((out_h, out_w, 3), dtype=np.uint8)
            for i, c in enumerate(cols):
                x = i * BODY
                if c.stream is None:
                    header, body = layout.headers[i][0], layout.statics[i]
                else:
                    body, ended = c.stream.next()
                    header = layout.headers[i][1 if ended else 0]
                canvas[: layout.header_h, x : x + BODY] = header
                canvas[layout.header_h : top, x : x + BODY] = layout.goals[i]
                canvas[top : top + BODY, x : x + BODY] = body
            yielded += 1
            yield canvas
    finally:
        for c in cols:
            if c.stream is not None:
                c.stream.close()


def output_name(u: Unit) -> str:
    return f"{TASK_NUMBERS[u.task]}_{u.task}_ep{u.episode}_seed{u.seed}.mp4"


def render_all(root: Path, out_dir: Path, manifest: dict | None = None, task: str | None = None) -> dict:
    painter = CjkPainter()
    units = discover(root)
    allowed = _manifest_keys(manifest) if manifest is not None else None
    selected = []
    for key in sorted(units, key=lambda k: (TASK_ORDER.index(k[0]), k[1], k[2])):
        u = units[key]
        if task is not None and u.task != task:
            continue
        if allowed is not None and (u.task, u.seed) not in allowed:
            continue
        selected.append(u)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = {"videos": 0, "columns": 0, "missing": 0, "frames": 0, "outputs": []}
    for u in selected:
        cols = build_columns(u)
        out = out_dir / output_name(u)
        counter = {"n": 0}

        def counted(gen):
            for frame in gen:
                counter["n"] += 1
                yield frame

        write_mp4(counted(compose_frames(cols, painter)), out)
        stats["videos"] += 1
        stats["columns"] += len(cols)
        stats["missing"] += sum(1 for c in cols if c.status in (MISSING, ABSENT))
        stats["frames"] += counter["n"]
        stats["outputs"].append(str(out))
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="逐 episode 六列横排前视相机视频（只读已有 H5 产物）")
    parser.add_argument("--root", required=True, help="输出根，含 mother/ 与 xhard12..20/ 及 run_summary.json")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    parser.add_argument("--seeds", default=None, help="母 seed 清单 JSON（只出清单内的 task+seed）")
    parser.add_argument("--task", default=None, choices=TASK_ORDER, help="只出某一个任务")
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.seeds).read_text(encoding="utf-8")) if args.seeds else None
    stats = render_all(Path(args.root), Path(args.out_dir), manifest, args.task)
    for path in stats["outputs"]:
        print(path)
    print(f"EPISODE_STRIP_VIDEO=PASS videos={stats['videos']} columns={stats['columns']} missing={stats['missing']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
