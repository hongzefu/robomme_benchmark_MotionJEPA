"""V2 采样窗口数轴画法（逐字搬运，只改 import）。

来源：origin/newtask-v2 分支 commit ``70bc2ce0``（V2 总览图 ``figures/windows_overview.png`` 由 ``c0e7f046`` 入库，
已拷到 ``vis/v2/``）。搬运清单：
  * ``scripts/injection-before-2d/window_timeline.py``：``WIN, STRIDE, BUDGETS``、``BANDS``、``window_starts``、
    ``frame_path``、``deltas``、``phase_segments``、``window_counts``、``representatives``、短标规则 ``_RULES`` 与 ``short_label``；
  * ``scripts/injection-before-2d/plot_injection_before_2d.py``：``SWAP_COLORS``、``use_cjk_font``；
  * ``scripts/injection-before-2d/plot_sampling_windows.py``：画图常量、``COLOR``、``_label_for``、``_right_text``、
    ``draw_track``、``_draw_board``。
以上函数体与常量逐字不动（例外：2026-10-07 用户「不要用这种你自己定义的 用timestep！全程」，`_right_text` 的 `T=` 改为 `timestep=`、横轴标题改为 `timestep`）；本仓库只在文件末尾追加 ``EXTRA_RULES``（V2 没有的 12 个任务的中文短标），
由 ``short_label`` 之前插入的一行 ``_RULES.extend(EXTRA_RULES)`` 生效（V2 规则优先匹配）。
2026-10-07 用户原话：「然后恢复v2的图片数轴」。
"""

from __future__ import annotations

import glob
import math
import re
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

# ── 来自 window_timeline.py ──
WIN, STRIDE, BUDGETS = 33, 16, (32, 8)
BANDS = ("最短", "中位", "最长")


def window_starts(length: int) -> list[int]:
    """一段 length 帧里能铺的窗口起点：``range(0, max(0, L-32), 16)``，与 artifact 的 ``winStarts`` 同。"""
    return list(range(0, max(0, length - (WIN - 1)), STRIDE))


def frame_path(total: int, n: int) -> list[int]:
    """帧路 ``round(linspace(0, T-1, N))``；用 floor(x+0.5) 而不是 Python 的银行家舍入，与 JS ``Math.round`` 一致。"""
    t = total - 1
    return [math.floor(i * t / (n - 1) + 0.5) for i in range(n)]


def deltas(total: int) -> tuple[float, ...]:
    """两条帧路的步长 Δ = (T-1)/(N-1)。"""
    return tuple((total - 1) / (n - 1) for n in BUDGETS)


def phase_segments(row: dict[str, Any]) -> list[tuple[int, int, str]]:
    """不跨段：demo 与 exec 各自从段起点铺；没有 demo 时整条是一个 exec 段。"""
    if row["demo"]:
        return [(0, row["demo"], "demo"), (row["demo"], row["total"] - row["demo"], "exec")]
    return [(0, row["total"], "exec")]


def window_counts(row: dict[str, Any]) -> tuple[int, int]:
    """(demo 段窗口数, exec 段窗口数)。"""
    counts = {"demo": 0, "exec": 0}
    for _start, length, kind in phase_segments(row):
        counts[kind] = len(window_starts(length))
    return counts["demo"], counts["exec"]


def representatives(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """按 T 排序取最短／中位（下标 n//2）／最长三条，与 artifact 的三档同规则。"""
    ordered = sorted(rows, key=lambda r: (r["total"], r["episode"]))
    return {"最短": ordered[0], "中位": ordered[len(ordered) // 2], "最长": ordered[-1]}


# ── swap 事件 ─────────────────────────────────────────────────────────────────


_DIRS = {"left": "左", "right": "右"}
_ORDS = {"first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5", "sixth": "6", "seventh": "7", "eighth": "8"}
_COLS = {"red": "红", "blue": "蓝", "green": "绿"}
_RULES: list[tuple[re.Pattern[str], Callable[[re.Match[str]], str]]] = [
    (re.compile(r"^move to the nearest (left|right) target by circling around the stick counterclockwise$", re.I), lambda m: "绕" + _DIRS[m[1].lower()] + "逆"),
    (re.compile(r"^move to the nearest (left|right) target by circling around the stick clockwise$", re.I), lambda m: "绕" + _DIRS[m[1].lower()] + "顺"),
    (re.compile(r"^pick up the (\w+) (red|blue|green) cube$", re.I), lambda m: "抓" + _COLS[m[2].lower()] + _ORDS.get(m[1].lower(), m[1])),
    (re.compile(r"^pick up the container that hides the (red|blue|green) cube$", re.I), lambda m: "抓" + _COLS[m[1].lower()] + "容"),
    (re.compile(r"^put down the container$", re.I), lambda m: "放容"),
    (re.compile(r"^put it into the bin$", re.I), lambda m: "投箱"),
    (re.compile(r"^pick up the correct cube for the (\w+) time$", re.I), lambda m: "抓对" + _ORDS.get(m[1].lower(), m[1])),
    (re.compile(r"^pick up the cube$", re.I), lambda m: "抓块"),
    (re.compile(r"^drop the cube on the table$", re.I), lambda m: "放桌"),
    (re.compile(r"^put it down$", re.I), lambda m: "放下"),
    (re.compile(r"^press the button to finish$", re.I), lambda m: "按钮停"),
    (re.compile(r"^press the button$", re.I), lambda m: "按钮"),
    (re.compile(r"^static$", re.I), lambda m: "静止"),
    (re.compile(r"^All tasks completed$", re.I), lambda m: "完成"),
]


# ── 本仓库追加（不属于 V2 原文）：V2 只覆盖 4 个任务，这里补其余任务的中文短标 ──
# 2026-10-07：xhard1 合成参考涉及 14 个任务，subgoal 文本种类见 vis/output/reference_*.json。
_MOVES = {"forward": "前", "backward": "后", "left": "左", "right": "右",
          "forward-left": "左前", "forward-right": "右前", "backward-left": "左后", "backward-right": "右后"}
EXTRA_RULES: list[tuple[re.Pattern[str], Callable[[re.Match[str]], str]]] = [
    (re.compile(r"^move (forward|backward|left|right|forward-left|forward-right|backward-left|backward-right)$", re.I),
     lambda m: "移" + _MOVES[m[1].lower()]),
    (re.compile(r"^move to the top of the (left|right)-side target for the (\w+) time$", re.I),
     lambda m: "摆" + _DIRS[m[1].lower()] + _ORDS.get(m[2].lower(), m[2])),
    (re.compile(r"^move to the top of the button to prepare$", re.I), lambda m: "备按"),
    (re.compile(r"^pick up the (red|blue|green) cube for the (\w+) time$", re.I),
     lambda m: "抓" + _COLS[m[1].lower()] + _ORDS.get(m[2].lower(), m[2])),
    (re.compile(r"^pick up the (\w+) highlighted cube, which is (red|blue|green)$", re.I),
     lambda m: "抓亮" + _ORDS.get(m[1].lower(), m[1])),
    (re.compile(r"^pick up the (red|blue|green) cube$", re.I), lambda m: "抓" + _COLS[m[1].lower()]),
    (re.compile(r"^place the (red|blue|green) cube onto the target$", re.I), lambda m: "放台"),
    (re.compile(r"^place the cube onto the correct target$", re.I), lambda m: "放对台"),
    (re.compile(r"^place the cube onto the table$", re.I), lambda m: "放桌"),
    (re.compile(r"^put the (red|blue|green) cube on the table$", re.I), lambda m: "放桌"),
    (re.compile(r"^drop the cube onto target$", re.I), lambda m: "放台"),
    (re.compile(r"^drop the cube onto table$", re.I), lambda m: "放桌"),
    (re.compile(r"^put the cube back to its original position$", re.I), lambda m: "回原位"),
    (re.compile(r"^press the (\w+) button$", re.I), lambda m: "按钮" + _ORDS.get(m[1].lower(), m[1])),
    (re.compile(r"^press the button to stop.*$", re.I), lambda m: "按钮停"),
    (re.compile(r"^remain static$", re.I), lambda m: "静止"),
]
_RULES.extend(EXTRA_RULES)  # V2 规则在前、优先匹配；本仓库规则只兜 V2 没命中的文本


def short_label(text: str) -> tuple[str, bool]:
    """返回 (短标, 是否命中规则)；没命中时兜底取前 6 个字符，调用方应把这类文本报出来。"""
    for pattern, render in _RULES:
        match = pattern.match(text.strip())
        if match:
            return render(match), True
    return text.strip()[:6], False


# ── 来自 plot_injection_before_2d.py ──
SWAP_COLORS = ["#6a1b9a", "#ef6c00", "#00838f", "#ad1457", "#5d4037"]


def use_cjk_font() -> str | None:
    candidates = sorted(set(glob.glob("/usr/share/fonts/**/*CJK*.tt?", recursive=True)))
    candidates += sorted(set(glob.glob("/usr/share/fonts/**/DroidSansFallback*.ttf", recursive=True)))
    for path in candidates:
        try:
            font_manager.fontManager.addfont(path)
        except Exception:  # noqa: BLE001
            continue
    for name in ("Noto Sans CJK SC", "Noto Sans CJK JP", "Droid Sans Fallback", "Noto Serif CJK JP"):
        if any(item.name == name for item in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return name
    return None


# ── 来自 plot_sampling_windows.py ──
DPI = 110
FIG_W_IN = 26.0           # 整图宽
ROW_IN = 0.62             # 每行高
AX_LEFT, AX_RIGHT = 0.085, 0.80   # 轴在图里的横向占比（左右各留文字栏）
MIN_LONG_EDGE = 2000
WIN_ROWS = -(-WIN // 16)  # ceil(33/16) = 3：同一行内窗口互不接触所需的行数
DIM_ALPHA = 0.35          # 被慢条剔除的行整体透明度

COLOR = {"demo": "#3E7FA8", "exec": "#4E9B7C", "f32": "#7B6FC9", "f8": "#C2593E", "empty": "#C9713D",
         "sg_a": "#DDE3E0", "sg_b": "#EEF2F0", "sg_line": "#A3AFAA", "ink": "#14181A", "ink2": "#48534F", "ink3": "#7B8783"}


def _label_for(row: dict[str, Any], task: str, difficulty: str, band: str | None = None,
               reasons: list[str] | None = None) -> str:
    """左栏行标签；``reasons`` 非空表示这条被慢条剔除，首行打「✕ 已剔除」、末尾另起一行写命中原因。"""
    parts = [f"{task}/{difficulty}", f"ep{row['episode']} · seed {row['seed']}"]
    if band:
        parts.insert(1, band)
    if row.get("simulated_demo"):
        parts.append("demo 由生成器直出（重复两遍）" if row.get("demo_source") == "recorded" else "模拟 demo（重复两遍）")
    if reasons:
        parts[0] = "✕ 已剔除 " + parts[0]
        parts.append("；".join(reasons))
    return "\n".join(parts)


def _right_text(row: dict[str, Any]) -> str:
    d, e = window_counts(row)
    d32, d8 = deltas(row["total"])
    t = f"timestep={row['total']}" + (f"（2×{row['original_total']}）" if row.get("simulated_demo") else "")
    tokens = f"窗口 {d}+{e}={d + e}" + ("（无 motion token）" if d + e == 0 else "")
    return f"{t}\n{tokens}\nΔ32={d32:.1f} · Δ8={d8:.1f}"


def draw_track(ax, row: dict[str, Any], y: float, xmax: float, axis_px: float, dimmed: bool = False) -> None:
    """在 y∈[y, y+1) 这条带里画一条 episode（y 轴向下为正，行 0 在最上）。

    ``dimmed=True`` 用于被慢条剔除的行：整行透明度乘 0.35、段底色再加斜纹 hatch，一眼区分于在统计里的行。
    """
    dim = DIM_ALPHA if dimmed else 1.0
    top, bottom = y + 0.06, y + 0.94
    sg_top, sg_bottom = y + 0.72, y + 0.94        # subgoal 块
    win_base = y + 0.66                            # 窗口细条最底一行
    f8_y, f32_top, f32_bottom = y + 0.33, y + 0.15, y + 0.27
    for start, length, kind in phase_segments(row):
        ax.add_patch(Rectangle((start, top), length, bottom - top, facecolor=COLOR[kind], alpha=0.09 if not dimmed else 0.14,
                               edgecolor=COLOR[kind] if dimmed else "none", linewidth=0.0 if not dimmed else 0.4,
                               hatch="//" if dimmed else None, zorder=1))
        ax.plot([start, start], [top, bottom], color=COLOR[kind], linewidth=0.8, alpha=0.7 * dim, zorder=2)
    char_px = 7 * DPI / 72
    # swap 事件：贯穿整行的半透明竖带（第 1～5 次紫/橙/青/玫红/棕，与跑前图 2 同色；xhard 最多 5 次），顶部小字「换k a↔b」；校验不过画虚线空框
    swap_ok = row.get("swap_check") == "PASS"
    for k, (s, e, label) in enumerate(row.get("swaps", [])):
        color = SWAP_COLORS[k % len(SWAP_COLORS)]
        ax.add_patch(Rectangle((s, top), e - s, bottom - top, facecolor=color if swap_ok else "none", edgecolor=color,
                               linewidth=0.7, linestyle="-" if swap_ok else "--", alpha=(0.18 if swap_ok else 0.9) * dim, zorder=2))
        text = f"换{k + 1} {label.replace('bin_', '')}"
        width_px = (e - s) / xmax * axis_px
        shown = text if width_px >= len(text) * char_px * 0.75 + 4 else str(k + 1)
        ax.text(s + (e - s) / 2, y + 0.02, shown, fontsize=6.5, ha="center", va="top", color=color, fontweight="bold", alpha=dim, zorder=7)
    for i, (start, length, text) in enumerate(row["segs"]):
        ax.add_patch(Rectangle((start, sg_top), length, sg_bottom - sg_top, facecolor=COLOR["sg_a"] if i % 2 == 0 else COLOR["sg_b"],
                               edgecolor=COLOR["sg_line"], linewidth=0.4, alpha=dim, zorder=3))
        label, _ = short_label(text)
        width_px = length / xmax * axis_px
        shown = label if width_px >= len(label) * char_px + 4 else (label[:1] if width_px >= char_px + 3 else "")
        if shown:
            ax.text(start + length / 2, (sg_top + sg_bottom) / 2, shown, fontsize=7, ha="center", va="center", color=COLOR["ink2"],
                    alpha=dim, zorder=4)
    for start, length, kind in phase_segments(row):
        starts = window_starts(length)
        if not starts:
            ax.add_patch(Rectangle((start, win_base - 0.26), max(length, 1), 0.28, fill=False, linestyle="--", linewidth=0.9,
                                   edgecolor=COLOR["empty"], alpha=dim, zorder=4))
            continue
        for i, f in enumerate(starts):
            level = win_base - (i % WIN_ROWS) * 0.10
            ax.add_patch(Rectangle((start + f, level - 0.07), WIN - 1, 0.07, facecolor=COLOR[kind], edgecolor="white",
                                   linewidth=0.3, alpha=0.9 * dim, zorder=5))
    xs = frame_path(row["total"], BUDGETS[0])
    ax.vlines(xs, f32_top, f32_bottom, color=COLOR["f32"], linewidth=0.7, alpha=0.85 * dim, zorder=5)
    xs8 = frame_path(row["total"], BUDGETS[1])
    ax.plot(xs8, [f8_y] * len(xs8), "o", color=COLOR["f8"], markersize=3.2, alpha=dim, zorder=6)


def _draw_board(items: list[tuple[str, Any]], xmax: float, title: str, out: Path) -> None:
    """items 里每项是 ("header", 文本) 或 ("row", 左栏标签, row, 是否灰化)。"""
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
        _, label, row, dimmed = item
        draw_track(ax, row, y, xmax, axis_px, dimmed=dimmed)
        ax.text(-0.006, 1 - (y + 0.5) / n, label, transform=ax.transAxes, fontsize=8.5, ha="right", va="center",
                color=COLOR["ink3"] if dimmed else COLOR["ink"], linespacing=1.3)
        ax.text(1.006, 1 - (y + 0.5) / n, _right_text(row), transform=ax.transAxes, fontsize=8.5, ha="left", va="center",
                color=COLOR["ink3"] if dimmed else COLOR["ink2"], linespacing=1.3)  # 不用 monospace：等宽字体没有中文字形会显示成方框
        ax.axhline(y + 1, color="#EBF0EE", linewidth=0.6, zorder=0)
    ax.set_xlim(0, xmax)
    ax.set_ylim(n, 0)
    ax.set_yticks([])
    step = 100 if xmax <= 1200 else 200
    ax.set_xticks(range(0, int(xmax) + 1, step))
    ax.tick_params(axis="x", labelsize=9, colors=COLOR["ink3"])
    ax.set_xlabel("timestep", fontsize=10, color=COLOR["ink2"])
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
               Patch(facecolor=COLOR["demo"], alpha=0.15, label="淡蓝底 = demo 段（BinFill 的 demo 为同一条重复两遍（07 起由生成器直出））"),
               Patch(facecolor=COLOR["exec"], alpha=0.15, label="淡绿底 = exec 段"),
               Patch(facecolor=COLOR["exec"], alpha=DIM_ALPHA, hatch="//", edgecolor=COLOR["ink3"], label="灰化+斜纹 = 慢条剔除（不进统计与代表）"),
               *[Patch(facecolor=SWAP_COLORS[k], alpha=0.35, edgecolor=SWAP_COLORS[k], label=f"第 {k + 1} 次 swap（换k 发起者↔搭档；Unmask 按调度常量、Repick 按关节静止反解）") for k in range(len(SWAP_COLORS))]]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=9, framealpha=0.95, bbox_to_anchor=(0.5, 0.01))
    fig.suptitle(title, fontsize=14, y=1 - 0.35 / fig_h)
    fig.text(0.5, 1 - 0.72 / fig_h, f"窗口 [f, f+{WIN - 1}]（{WIN} 帧）、stride 16、不跨 demo／exec 段，每段窗口数 len(range(0, max(0, L-{WIN - 1}), 16))；"
             f"帧路 round(linspace(0, T-1, N))，Δ = (T-1)/(N-1)；N={BUDGETS[0]} 与 N={BUDGETS[1]} 是帧预算不是切分步长",
             ha="center", fontsize=9, color=COLOR["ink3"])
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
