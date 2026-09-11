"""采样窗口数轴出图（只读同目录 ``windows_timeline.json``，公式从 ``window_timeline`` 复用）。

把上一会话 artifact「采样窗口与 eval 成功率」的 ``track()`` 画法搬成静态 PNG，产物放本目录 ``figures/``（已 gitignore）：

* ``figures/<任务>/<难度>/4_windows.png`` —— 该组全部可用 episode 各一行（按 T 升序），同任务各档共用一根横轴；
* ``figures/windows_overview.png`` —— 14 组 × 最短／中位／最长 = 42 行，全局横轴，对应 artifact 默认「全部」视图。

每一行从下到上：subgoal 分段（交替灰块，块够宽写中文短标）→ 窗口细条（demo 蓝、exec 绿，按 ``i % 3`` 堆三行防粘连，
段 < 33 帧画虚线空框）→ N=8 帧路红点 → N=32 帧路紫细线；行底色淡蓝 = demo 段、淡绿 = exec 段；
右侧文字 ``T · 窗口 d+e=n · Δ32 · Δ8``。BinFill 的 demo 是「同一条重复两遍」模拟出来的，行标签标明。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from plot_injection_before_2d import SWAP_COLORS, use_cjk_font  # noqa: E402
from window_timeline import (  # noqa: E402
    BANDS, BUDGETS, GROUPS, TIMELINE_JSON, WIN, deltas, frame_path, phase_segments, representatives, short_label,
    window_counts, window_starts,
)

FIGURES_DIR = HERE / "figures"
DPI = 110
FIG_W_IN = 26.0           # 整图宽
ROW_IN = 0.62             # 每行高
AX_LEFT, AX_RIGHT = 0.085, 0.80   # 轴在图里的横向占比（左右各留文字栏）
MIN_LONG_EDGE = 2000
WIN_ROWS = -(-WIN // 16)  # ceil(33/16) = 3：同一行内窗口互不接触所需的行数

COLOR = {"demo": "#3E7FA8", "exec": "#4E9B7C", "f32": "#7B6FC9", "f8": "#C2593E", "empty": "#C9713D",
         "sg_a": "#DDE3E0", "sg_b": "#EEF2F0", "sg_line": "#A3AFAA", "ink": "#14181A", "ink2": "#48534F", "ink3": "#7B8783"}


def _label_for(row: dict[str, Any], task: str, difficulty: str, band: str | None = None) -> str:
    parts = [f"{task}/{difficulty}", f"ep{row['episode']} · seed {row['seed']}"]
    if band:
        parts.insert(1, band)
    if row.get("simulated_demo"):
        parts.append("模拟 demo（重复两遍）")
    return "\n".join(parts)


def _right_text(row: dict[str, Any]) -> str:
    d, e = window_counts(row)
    d32, d8 = deltas(row["total"])
    t = f"T={row['total']}" + (f"（2×{row['original_total']}）" if row.get("simulated_demo") else "")
    tokens = f"窗口 {d}+{e}={d + e}" + ("（无 motion token）" if d + e == 0 else "")
    return f"{t}\n{tokens}\nΔ32={d32:.1f} · Δ8={d8:.1f}"


def draw_track(ax, row: dict[str, Any], y: float, xmax: float, axis_px: float) -> None:
    """在 y∈[y, y+1) 这条带里画一条 episode（y 轴向下为正，行 0 在最上）。"""
    top, bottom = y + 0.06, y + 0.94
    sg_top, sg_bottom = y + 0.72, y + 0.94        # subgoal 块
    win_base = y + 0.66                            # 窗口细条最底一行
    f8_y, f32_top, f32_bottom = y + 0.33, y + 0.15, y + 0.27
    for start, length, kind in phase_segments(row):
        ax.add_patch(Rectangle((start, top), length, bottom - top, facecolor=COLOR[kind], alpha=0.09, edgecolor="none", zorder=1))
        ax.plot([start, start], [top, bottom], color=COLOR[kind], linewidth=0.8, alpha=0.7, zorder=2)
    char_px = 7 * DPI / 72
    # swap 事件：贯穿整行的半透明竖带（第 1～5 次紫/橙/青/玫红/棕，与跑前图 2 同色；xhard 最多 5 次），顶部小字「换k a↔b」；校验不过画虚线空框
    swap_ok = row.get("swap_check") == "PASS"
    for k, (s, e, label) in enumerate(row.get("swaps", [])):
        color = SWAP_COLORS[k % len(SWAP_COLORS)]
        ax.add_patch(Rectangle((s, top), e - s, bottom - top, facecolor=color if swap_ok else "none", edgecolor=color,
                               linewidth=0.7, linestyle="-" if swap_ok else "--", alpha=0.18 if swap_ok else 0.9, zorder=2))
        text = f"换{k + 1} {label.replace('bin_', '')}"
        width_px = (e - s) / xmax * axis_px
        shown = text if width_px >= len(text) * char_px * 0.75 + 4 else str(k + 1)
        ax.text(s + (e - s) / 2, y + 0.02, shown, fontsize=6.5, ha="center", va="top", color=color, fontweight="bold", zorder=7)
    for i, (start, length, text) in enumerate(row["segs"]):
        ax.add_patch(Rectangle((start, sg_top), length, sg_bottom - sg_top, facecolor=COLOR["sg_a"] if i % 2 == 0 else COLOR["sg_b"],
                               edgecolor=COLOR["sg_line"], linewidth=0.4, zorder=3))
        label, _ = short_label(text)
        width_px = length / xmax * axis_px
        shown = label if width_px >= len(label) * char_px + 4 else (label[:1] if width_px >= char_px + 3 else "")
        if shown:
            ax.text(start + length / 2, (sg_top + sg_bottom) / 2, shown, fontsize=7, ha="center", va="center", color=COLOR["ink2"], zorder=4)
    for start, length, kind in phase_segments(row):
        starts = window_starts(length)
        if not starts:
            ax.add_patch(Rectangle((start, win_base - 0.26), max(length, 1), 0.28, fill=False, linestyle="--", linewidth=0.9,
                                   edgecolor=COLOR["empty"], zorder=4))
            continue
        for i, f in enumerate(starts):
            level = win_base - (i % WIN_ROWS) * 0.10
            ax.add_patch(Rectangle((start + f, level - 0.07), WIN - 1, 0.07, facecolor=COLOR[kind], edgecolor="white", linewidth=0.3, alpha=0.9, zorder=5))
    xs = frame_path(row["total"], BUDGETS[0])
    ax.vlines(xs, f32_top, f32_bottom, color=COLOR["f32"], linewidth=0.7, alpha=0.85, zorder=5)
    xs8 = frame_path(row["total"], BUDGETS[1])
    ax.plot(xs8, [f8_y] * len(xs8), "o", color=COLOR["f8"], markersize=3.2, zorder=6)


def _draw_board(items: list[tuple[str, Any]], xmax: float, title: str, out: Path) -> None:
    """items 里每项是 ("header", 文本) 或 ("row", 左栏标签, row)。"""
    n = len(items)
    fig_h = ROW_IN * n + 2.9
    fig = plt.figure(figsize=(FIG_W_IN, fig_h))
    ax = fig.add_axes([AX_LEFT, 1.9 / fig_h, AX_RIGHT - AX_LEFT, 1 - (1.9 + 0.9) / fig_h])
    axis_px = FIG_W_IN * DPI * (AX_RIGHT - AX_LEFT)
    for y, item in enumerate(items):
        if item[0] == "header":
            ax.add_patch(Rectangle((0, y + 0.1), xmax, 0.8, facecolor="#F0F3F1", edgecolor="none", zorder=1))
            ax.text(xmax * 0.004, y + 0.5, item[1], fontsize=11, fontweight="bold", va="center", ha="left", color=COLOR["ink"], zorder=4)
            continue
        _, label, row = item
        draw_track(ax, row, y, xmax, axis_px)
        ax.text(-0.006, 1 - (y + 0.5) / n, label, transform=ax.transAxes, fontsize=8.5, ha="right", va="center", color=COLOR["ink"], linespacing=1.3)
        ax.text(1.006, 1 - (y + 0.5) / n, _right_text(row), transform=ax.transAxes, fontsize=8.5, ha="left", va="center",
                color=COLOR["ink2"], linespacing=1.3)  # 不用 monospace：等宽字体没有中文字形会显示成方框
        ax.axhline(y + 1, color="#EBF0EE", linewidth=0.6, zorder=0)
    ax.set_xlim(0, xmax)
    ax.set_ylim(n, 0)
    ax.set_yticks([])
    step = 100 if xmax <= 1200 else 200
    ax.set_xticks(range(0, int(xmax) + 1, step))
    ax.tick_params(axis="x", labelsize=9, colors=COLOR["ink3"])
    ax.set_xlabel("帧（timestep）", fontsize=10, color=COLOR["ink2"])
    ax.xaxis.grid(True, color="#EBF0EE", linewidth=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    handles = [Patch(facecolor=COLOR["demo"], label="demo 段窗口 [f, f+32]"),
               Patch(facecolor=COLOR["exec"], label="exec 段窗口（相邻错 16 帧，堆 3 行防粘连）"),
               Patch(facecolor=COLOR["sg_a"], edgecolor=COLOR["sg_line"], label="subgoal 分段（块内为中文短标，全文见 md 表）"),
               Line2D([], [], color=COLOR["f32"], linewidth=1.2, label=f"帧路 N={BUDGETS[0]}"),
               Line2D([], [], marker="o", linestyle="", color=COLOR["f8"], markersize=5, label=f"帧路 N={BUDGETS[1]}"),
               Patch(facecolor="none", edgecolor=COLOR["empty"], linestyle="--", label=f"段 < {WIN} 帧，铺不出窗口"),
               Patch(facecolor=COLOR["demo"], alpha=0.15, label="淡蓝底 = demo 段（BinFill 为同一条重复两遍的模拟 demo）"),
               Patch(facecolor=COLOR["exec"], alpha=0.15, label="淡绿底 = exec 段"),
               *[Patch(facecolor=SWAP_COLORS[k], alpha=0.35, edgecolor=SWAP_COLORS[k], label=f"第 {k + 1} 次 swap（换k 发起者↔搭档；Unmask 按调度常量、Repick 按关节静止反解）") for k in range(len(SWAP_COLORS))]]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=9, framealpha=0.95, bbox_to_anchor=(0.5, 0.01))
    fig.suptitle(title, fontsize=14, y=1 - 0.35 / fig_h)
    fig.text(0.5, 1 - 0.72 / fig_h, f"窗口 [f, f+{WIN - 1}]（{WIN} 帧）、stride 16、不跨 demo／exec 段，每段窗口数 len(range(0, max(0, L-{WIN - 1}), 16))；"
             f"帧路 round(linspace(0, T-1, N))，Δ = (T-1)/(N-1)；N={BUDGETS[0]} 与 N={BUDGETS[1]} 是帧预算不是切分步长",
             ha="center", fontsize=9, color=COLOR["ink3"])
    fig.savefig(out, dpi=DPI)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="采样窗口数轴出图（只读 windows_timeline.json，产物放 figures/）")
    parser.add_argument("--json", default=str(TIMELINE_JSON))
    parser.add_argument("--out-dir", default=str(FIGURES_DIR))
    args = parser.parse_args()
    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    font = use_cjk_font()
    run_id = data["rollout_run_id"]

    files: list[Path] = []
    task_xmax = {task: max(r["total"] for t, d in GROUPS if t == task for r in data["groups"].get(f"{t}/{d}", []) or [{"total": 1}])
                 for task, _ in GROUPS}
    for task, difficulty in GROUPS:
        rows = sorted(data["groups"].get(f"{task}/{difficulty}", []), key=lambda r: (r["total"], r["episode"]))
        target = out_root / task / difficulty
        target.mkdir(parents=True, exist_ok=True)
        items = [("row", _label_for(r, task, difficulty), r) for r in rows]
        title = (f"图 4 · {task} / {difficulty} 采样窗口数轴（实跑 {run_id}，{len(rows)} 条按 T 升序；横轴 0–{task_xmax[task]} 在 {task} 各档间固定）"
                 + ("；BinFill 的 demo 为同一条重复两遍模拟" if task == "BinFill" else ""))
        out = target / "4_windows.png"
        _draw_board(items, task_xmax[task], title, out)
        files.append(out)
        print(f"  出图 {task}/{difficulty}：{len(rows)} 行", flush=True)

    global_xmax = max(task_xmax.values())
    items = []
    for task, difficulty in GROUPS:
        rows = data["groups"].get(f"{task}/{difficulty}", [])
        if not rows:
            continue
        reps = representatives(rows)
        items.append(("header", f"{task} / {difficulty}（{len(rows)} 条）" + ("　模拟 demo：同一条重复两遍" if rows[0].get("simulated_demo") else "")))
        for band in BANDS:
            items.append(("row", _label_for(reps[band], task, difficulty, band), reps[band]))
    overview = out_root / "windows_overview.png"
    _draw_board(items, global_xmax, f"采样窗口数轴总览 · {len(GROUPS)} 组各取最短／中位／最长三条（实跑 {run_id}；横轴 0–{global_xmax} 全局固定，可跨任务横比）", overview)
    files.append(overview)

    sizes = {}
    try:
        from PIL import Image
        for f in files:
            with Image.open(f) as im:
                sizes[str(f.relative_to(out_root))] = list(im.size)
    except ImportError:
        pass
    min_edge = min((max(s) for s in sizes.values()), default=0)
    (out_root / "windows_manifest.json").write_text(json.dumps(
        {"rollout_run_id": run_id, "episodes": data["episodes"], "font": font, "dpi": DPI,
         "files": [str(f.relative_to(out_root)) for f in files], "sizes": sizes}, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = len(files) == len(GROUPS) + 1 and (not sizes or min_edge >= MIN_LONG_EDGE)
    print(f"WINDOWS_PLOT={'PASS' if ok else 'FAIL'} groups={len(GROUPS)} files={len(files)} min_long_edge_px={min_edge} font={font}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
