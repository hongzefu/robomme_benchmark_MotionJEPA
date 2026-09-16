"""BinFill / medium 单条 episode 的精简数轴图，两张，图面文案全英文（只读同目录 ``windows_timeline.json``）。

从 ``plot_sampling_windows.py`` 的整版数轴里裁出单条 episode，出两张：

* ``single_subgoal_delta8.png`` —— 两条轴线：subgoal 分段 + 帧路 N=8；
* ``single_subgoal_delta8_windows.png`` —— 在上图基础上加第三条轴线 motion 窗口
  （每段自段起点铺 [f, f+32]、stride 16、按 ``i % 3`` 堆三行防粘连）。

图面文字（标题／轴标／段标／图例）一律英文，subgoal 短标走本文件的 ``_EN_RULES`` 英文规则表，
与 ``window_timeline.short_label`` 的中文规则表一一对应。不画 N=32 帧路与 swap 竖带；
demo/exec 只留淡底色与分界虚线做背景参照（BinFill 的 demo 为同一条重复两遍，不画分界
会让前后两轮 subgoal 看着像 16 段独立段）。产物放 ``figures/BinFill/medium/``（已 gitignore）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from plot_sampling_windows import COLOR, FIGURES_DIR, WIN_ROWS  # noqa: E402
from window_timeline import (  # noqa: E402
    BANDS, BUDGETS, STRIDE, TIMELINE_JSON, WIN, deltas, frame_path, phase_segments, representatives, window_starts,
)

TASK, DIFFICULTY = "BinFill", "medium"
BUDGET = BUDGETS[1]        # N=8
DPI = 200
FIG_W_IN = 16.0
AX_LEFT, AX_RIGHT = 0.105, 0.985

# 英文短标规则表：与 window_timeline._RULES 的中文表一一对应，兜底取原文前 10 字符
_ORDS = {"first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5", "sixth": "6", "seventh": "7", "eighth": "8"}
_COLS = {"red": "R", "blue": "B", "green": "G"}
_EN_RULES: list[tuple[re.Pattern[str], Callable[[re.Match[str]], str]]] = [
    (re.compile(r"^move to the nearest (left|right) target by circling around the stick counterclockwise$", re.I), lambda m: f"{m[1][0].upper()}-CCW"),
    (re.compile(r"^move to the nearest (left|right) target by circling around the stick clockwise$", re.I), lambda m: f"{m[1][0].upper()}-CW"),
    (re.compile(r"^pick up the (\w+) (red|blue|green) cube$", re.I), lambda m: f"Pick {_COLS[m[2].lower()]}{_ORDS.get(m[1].lower(), m[1])}"),
    (re.compile(r"^pick up the container that hides the (red|blue|green) cube$", re.I), lambda m: f"Pick box {_COLS[m[1].lower()]}"),
    (re.compile(r"^put down the container$", re.I), lambda m: "Drop box"),
    (re.compile(r"^put it into the bin$", re.I), lambda m: "To bin"),
    (re.compile(r"^pick up the correct cube for the (\w+) time$", re.I), lambda m: f"Retry {_ORDS.get(m[1].lower(), m[1])}"),
    (re.compile(r"^pick up the cube$", re.I), lambda m: "Pick cube"),
    (re.compile(r"^drop the cube on the table$", re.I), lambda m: "Drop"),
    (re.compile(r"^put it down$", re.I), lambda m: "Put down"),
    (re.compile(r"^press the button to finish$", re.I), lambda m: "Press end"),
    (re.compile(r"^press the button$", re.I), lambda m: "Press"),
    (re.compile(r"^static$", re.I), lambda m: "Static"),
    (re.compile(r"^All tasks completed$", re.I), lambda m: "Done"),
]


def short_label_en(text: str) -> tuple[str, bool]:
    """返回 (英文短标, 是否命中规则)；没命中时兜底取前 10 个字符，调用方应把这类文本报出来。"""
    for pattern, render in _EN_RULES:
        match = pattern.match(text.strip())
        if match:
            return render(match), True
    return text.strip()[:10], False


def pick_row(rows: list[dict[str, Any]], band: str, episode: int | None) -> dict[str, Any]:
    """按 ``--episode`` 精确取，否则取 ``--band`` 对应的最短／中位／最长代表条。"""
    if episode is not None:
        matched = [r for r in rows if r["episode"] == episode]
        if not matched:
            raise SystemExit(f"{TASK}/{DIFFICULTY} 里没有 ep{episode}；可选 {sorted(r['episode'] for r in rows)}")
        return matched[0]
    return representatives(rows)[band]


def draw(row: dict[str, Any], run_id: str, out: Path, *, with_windows: bool) -> list[str]:
    """画一张图；``with_windows=True`` 时多画一条 motion 窗口轴。返回未命中英文规则表的 subgoal 原文。"""
    total, delta = row["total"], deltas(row["total"])[1]
    fig_h = 4.2 if with_windows else 3.2
    # 轴内 y 自上而下：subgoal 带、（可选）窗口三行、帧路；带窗口时整体压扁给窗口腾地方
    if with_windows:
        sg_top, sg_bottom, win_base, fp_top, fp_bottom = 0.96, 0.78, 0.70, 0.30, 0.14
    else:
        sg_top, sg_bottom, win_base, fp_top, fp_bottom = 0.90, 0.62, 0.0, 0.42, 0.20
    fig = plt.figure(figsize=(FIG_W_IN, fig_h))
    ax = fig.add_axes([AX_LEFT, 1.0 / fig_h, AX_RIGHT - AX_LEFT, 1 - 2.0 / fig_h])
    axis_px = FIG_W_IN * DPI * (AX_RIGHT - AX_LEFT)
    char_px = 9 * DPI / 72 * 0.6            # 英文按 0.6 em 估宽（汉字才是 1 em）

    for start, length, kind in phase_segments(row):          # demo/exec 淡底色 + 分界竖线，只作背景参照
        ax.add_patch(Rectangle((start, 0.06), length, 0.94, facecolor=COLOR[kind], alpha=0.08, edgecolor="none", zorder=1))
        ax.plot([start, start], [0.06, 1.0], color=COLOR[kind], linewidth=0.9, alpha=0.7, zorder=2)
        ax.text(start + length / 2, 1.015, "demo phase (same episode replayed twice)" if kind == "demo" else "exec phase",
                fontsize=9, ha="center", va="bottom", color=COLOR[kind], zorder=4)

    unmatched: list[str] = []
    for i, (start, length, text) in enumerate(row["segs"]):   # 轴线一：subgoal 分段
        ax.add_patch(Rectangle((start, sg_bottom), length, sg_top - sg_bottom,
                               facecolor=COLOR["sg_a"] if i % 2 == 0 else COLOR["sg_b"],
                               edgecolor=COLOR["sg_line"], linewidth=0.5, zorder=3))
        label, matched = short_label_en(text)
        if not matched:
            unmatched.append(text)
        width_px = length / total * axis_px
        shown = label if width_px >= len(label) * char_px + 4 else (label[:1] if width_px >= char_px + 3 else "")
        if shown:
            ax.text(start + length / 2, (sg_top + sg_bottom) / 2, shown, fontsize=9, ha="center", va="center", color=COLOR["ink2"], zorder=4)

    n_windows = 0
    if with_windows:                                         # 轴线二：motion 窗口，不跨段、堆三行防粘连
        for start, length, kind in phase_segments(row):
            starts = window_starts(length)
            if not starts:
                ax.add_patch(Rectangle((start, win_base - 0.24), max(length, 1), 0.24, fill=False, linestyle="--",
                                       linewidth=0.9, edgecolor=COLOR["empty"], zorder=4))
                continue
            n_windows += len(starts)
            for i, f in enumerate(starts):
                level = win_base - (i % WIN_ROWS) * 0.09
                ax.add_patch(Rectangle((start + f, level - 0.065), WIN - 1, 0.065, facecolor=COLOR[kind],
                                       edgecolor="white", linewidth=0.3, alpha=0.9, zorder=5))

    xs = frame_path(total, BUDGET)                           # 轴线三：N=8 帧路，8 个点标出帧号
    ax.vlines(xs, fp_bottom, fp_top, color=COLOR["f8"], linewidth=1.4, zorder=5)
    ax.plot(xs, [fp_top] * len(xs), "o", color=COLOR["f8"], markersize=4.5, zorder=6)
    for x in xs:
        ax.text(x, fp_bottom - 0.02, str(x), fontsize=8, ha="center", va="top", color=COLOR["f8"], zorder=6)

    ticks = [(sg_top + sg_bottom) / 2, (fp_top + fp_bottom) / 2]
    labels = ["Subgoal\nsegments", f"Frame path\nN={BUDGET}"]
    if with_windows:
        ticks.insert(1, win_base - 0.09)
        labels.insert(1, f"Motion windows\n[f, f+{WIN - 1}]")
    ax.set_xlim(0, total)
    ax.set_ylim(0, 1.05)
    ax.set_yticks(ticks)
    ax.set_yticklabels(labels, fontsize=10, color=COLOR["ink"], linespacing=1.4)
    ax.tick_params(axis="y", length=0)
    ax.set_xticks(range(0, total + 1, 100))
    ax.tick_params(axis="x", labelsize=9, colors=COLOR["ink3"])
    ax.set_xlabel("frame (timestep)", fontsize=10, color=COLOR["ink2"])
    ax.xaxis.grid(True, color="#EBF0EE", linewidth=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)

    handles = [Patch(facecolor=COLOR["sg_a"], edgecolor=COLOR["sg_line"], label="subgoal segment (short label; full text in the md tables)")]
    if with_windows:
        handles += [Patch(facecolor=COLOR["demo"], label=f"demo-phase motion window [f, f+{WIN - 1}]"),
                    Patch(facecolor=COLOR["exec"], label=f"exec-phase motion window (stride {STRIDE}, stacked in {WIN_ROWS} rows)")]
    handles += [Line2D([], [], marker="o", color=COLOR["f8"], linewidth=1.4, markersize=6,
                       label=f"frame path N={BUDGET}: round(linspace(0, T-1, {BUDGET})), Δ{BUDGET}=(T-1)/{BUDGET - 1}"),
                Patch(facecolor=COLOR["demo"], alpha=0.15, label="blue tint = demo phase"),
                Patch(facecolor=COLOR["exec"], alpha=0.15, label="green tint = exec phase")]
    fig.legend(handles=handles, loc="lower center", ncol=3 if with_windows else 4, fontsize=9, framealpha=0.95,
               bbox_to_anchor=(0.5, 0.008))
    subtitle = (f"T={total} (2×{row['original_total']})  ·  {len(row['segs'])} subgoal segments"
                + (f"  ·  {n_windows} motion windows" if with_windows else "")
                + f"  ·  Δ{BUDGET}={delta:.1f} frames  ·  rollout {run_id}")
    fig.suptitle(f"{TASK} / {DIFFICULTY}  ·  ep{row['episode']}  ·  seed {row['seed']}\n{subtitle}",
                 fontsize=12, y=1 - 0.12 / fig_h, linespacing=1.6)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    return unmatched


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{TASK}/{DIFFICULTY} 单条 episode 的 subgoal + N=8 两张图（图面英文）")
    parser.add_argument("--json", default=str(TIMELINE_JSON))
    parser.add_argument("--out-dir", default=str(FIGURES_DIR))
    parser.add_argument("--band", default="中位", choices=list(BANDS), help="不指定 --episode 时取哪一档代表条")
    parser.add_argument("--episode", type=int, default=None, help="精确指定 episode 号，优先于 --band")
    args = parser.parse_args()
    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    rows = data["groups"][f"{TASK}/{DIFFICULTY}"]
    row = pick_row(rows, args.band, args.episode)
    target = Path(args.out_dir) / TASK / DIFFICULTY
    outs = {False: target / f"single_subgoal_delta{BUDGET}.png", True: target / f"single_subgoal_delta{BUDGET}_windows.png"}
    unmatched: list[str] = []
    for with_windows, out in outs.items():
        unmatched += draw(row, data["rollout_run_id"], out, with_windows=with_windows)
    ok = all(o.exists() and o.stat().st_size > 0 for o in outs.values()) and not unmatched
    print(f"SINGLE_PLOT={'PASS' if ok else 'FAIL'} ep={row['episode']} T={row['total']} segs={len(row['segs'])} "
          f"files={len(outs)} unmatched={sorted(set(unmatched))}")
    for out in outs.values():
        print(f"  {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
