"""BinFill / medium 单条 episode 的精简数轴图（只读同目录 ``windows_timeline.json``）。

从 ``plot_sampling_windows.py`` 的整版数轴里裁出两条轴线，供单独放大看：

* 上轴 ``subgoal 分段``：交替灰块 + 块内中文短标（全文见 SAMPLING_WINDOWS.md 的段表）；
* 下轴 ``帧路 N=32``：``round(linspace(0, T-1, 32))`` 的 32 根竖线，步长 Δ32 = (T-1)/31。

不画 demo/exec 窗口细条、N=8 帧路与 swap 竖带；demo/exec 只留淡底色与分界虚线做背景参照
（BinFill 的 demo 为同一条重复两遍，不画分界会让前后两轮 subgoal 看着像 16 段独立段）。
产物 ``figures/BinFill/medium/single_subgoal_delta32.png``（figures/ 已 gitignore）。
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
from plot_injection_before_2d import use_cjk_font  # noqa: E402
from plot_sampling_windows import COLOR, FIGURES_DIR  # noqa: E402
from window_timeline import BANDS, BUDGETS, TIMELINE_JSON, deltas, frame_path, phase_segments, representatives, short_label  # noqa: E402

TASK, DIFFICULTY = "BinFill", "medium"
DPI = 200
FIG_W_IN, FIG_H_IN = 16.0, 3.2
AX_LEFT, AX_RIGHT = 0.085, 0.985
SG_TOP, SG_BOTTOM = 0.62, 0.90      # subgoal 块的上下沿（数据坐标，y 向上）
F32_TOP, F32_BOTTOM = 0.20, 0.42    # Δ32 竖线的上下沿


def pick_row(rows: list[dict[str, Any]], band: str, episode: int | None) -> dict[str, Any]:
    """按 ``--episode`` 精确取，否则取 ``--band`` 对应的最短／中位／最长代表条。"""
    if episode is not None:
        matched = [r for r in rows if r["episode"] == episode]
        if not matched:
            raise SystemExit(f"{TASK}/{DIFFICULTY} 里没有 ep{episode}；可选 {sorted(r['episode'] for r in rows)}")
        return matched[0]
    return representatives(rows)[band]


def draw(row: dict[str, Any], run_id: str, out: Path) -> None:
    total = row["total"]
    d32 = deltas(total)[0]
    fig = plt.figure(figsize=(FIG_W_IN, FIG_H_IN))
    ax = fig.add_axes([AX_LEFT, 0.30, AX_RIGHT - AX_LEFT, 0.50])
    axis_px = FIG_W_IN * DPI * (AX_RIGHT - AX_LEFT)
    char_px = 9 * DPI / 72

    for start, length, kind in phase_segments(row):          # demo/exec 淡底色 + 分界竖线，只作背景参照
        ax.add_patch(Rectangle((start, 0.08), length, 0.88, facecolor=COLOR[kind], alpha=0.08, edgecolor="none", zorder=1))
        ax.plot([start, start], [0.08, 0.96], color=COLOR[kind], linewidth=0.9, alpha=0.7, zorder=2)
        ax.text(start + length / 2, 0.985, "demo 段（同一条重复两遍）" if kind == "demo" else "exec 段",
                fontsize=9, ha="center", va="bottom", color=COLOR[kind], zorder=4)

    for i, (start, length, text) in enumerate(row["segs"]):   # 轴线一：subgoal 分段
        ax.add_patch(Rectangle((start, SG_BOTTOM), length, SG_TOP - SG_BOTTOM,
                               facecolor=COLOR["sg_a"] if i % 2 == 0 else COLOR["sg_b"],
                               edgecolor=COLOR["sg_line"], linewidth=0.5, zorder=3))
        label, _ = short_label(text)
        width_px = length / total * axis_px
        shown = label if width_px >= len(label) * char_px + 4 else (label[:1] if width_px >= char_px + 3 else "")
        if shown:
            ax.text(start + length / 2, (SG_TOP + SG_BOTTOM) / 2, shown, fontsize=9, ha="center", va="center", color=COLOR["ink2"], zorder=4)

    xs = frame_path(total, BUDGETS[0])                       # 轴线二：Δ32 帧路
    ax.vlines(xs, F32_BOTTOM, F32_TOP, color=COLOR["f32"], linewidth=1.1, alpha=0.9, zorder=5)

    ax.set_xlim(0, total)
    ax.set_ylim(0, 1)
    ax.set_yticks([(SG_TOP + SG_BOTTOM) / 2, (F32_TOP + F32_BOTTOM) / 2])
    ax.set_yticklabels(["subgoal 分段", f"帧路 N={BUDGETS[0]}"], fontsize=10, color=COLOR["ink"])
    ax.tick_params(axis="y", length=0)
    ax.set_xticks(range(0, total + 1, 100))
    ax.tick_params(axis="x", labelsize=9, colors=COLOR["ink3"])
    ax.set_xlabel("帧（timestep）", fontsize=10, color=COLOR["ink2"])
    ax.xaxis.grid(True, color="#EBF0EE", linewidth=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)

    handles = [Patch(facecolor=COLOR["sg_a"], edgecolor=COLOR["sg_line"], label="subgoal 分段（块内为中文短标，全文见 md 段表）"),
               Line2D([], [], color=COLOR["f32"], linewidth=1.4, label=f"帧路 N={BUDGETS[0]}：round(linspace(0, T-1, 32))，Δ32=(T-1)/31"),
               Patch(facecolor=COLOR["demo"], alpha=0.15, label="淡蓝底 = demo 段"),
               Patch(facecolor=COLOR["exec"], alpha=0.15, label="淡绿底 = exec 段")]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=9, framealpha=0.95, bbox_to_anchor=(0.5, 0.01))
    fig.suptitle(f"{TASK} / {DIFFICULTY} · ep{row['episode']} · seed {row['seed']}　"
                 f"T={total}（2×{row['original_total']}） · {len(row['segs'])} 个 subgoal 段 · Δ32={d32:.1f} 帧　（实跑 {run_id}）",
                 fontsize=12, y=0.965)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{TASK}/{DIFFICULTY} 单条 episode 的 subgoal + Δ32 两轴图")
    parser.add_argument("--json", default=str(TIMELINE_JSON))
    parser.add_argument("--out-dir", default=str(FIGURES_DIR))
    parser.add_argument("--band", default="中位", choices=list(BANDS), help="不指定 --episode 时取哪一档代表条")
    parser.add_argument("--episode", type=int, default=None, help="精确指定 episode 号，优先于 --band")
    args = parser.parse_args()
    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    rows = data["groups"][f"{TASK}/{DIFFICULTY}"]
    font = use_cjk_font()
    row = pick_row(rows, args.band, args.episode)
    out = Path(args.out_dir) / TASK / DIFFICULTY / "single_subgoal_delta32.png"
    draw(row, data["rollout_run_id"], out)
    ok = out.exists() and out.stat().st_size > 0
    print(f"SINGLE_PLOT={'PASS' if ok else 'FAIL'} ep={row['episode']} T={row['total']} segs={len(row['segs'])} font={font} out={out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
