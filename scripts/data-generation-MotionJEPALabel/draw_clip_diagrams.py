#!/usr/bin/env python3
"""变体 2D 简图：每个源 episode 一张、每条 clip 一个子图。

一眼要看清的三件事：
1. 四个槽位的实际布局（bin 的初始 xy，即「允许的变化维度 1」）；
2. 这条 clip 的唯一事件 —— 第一次 swap 换了哪两个槽位（箭头 + 拓扑类别）；
3. 哪一条是 is_original（与官方 episode 逐位一致的那条）。

输出：{gen_dir}/diagrams/{Task}_ep{N}_clips.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from clip_plan import EVAL_TASKS, SLOT_ROLE  # noqa: E402

TOPO_COLOR = {
    "same_column": "#1f77b4",
    "cross_aligned": "#2ca02c",
    "cross_diagonal": "#d62728",
}
TOPO_LABEL = {
    "same_column": "同列",
    "cross_aligned": "跨列同侧",
    "cross_diagonal": "跨列对角",
}


def draw_clip(ax, record: dict) -> None:
    slot_xy = record["slot_xy"]
    event = tuple(record["event_slots"])
    topo = record["topo_class"]
    color = TOPO_COLOR[topo]

    xs = [p[0] for p in slot_xy]
    ys = [p[1] for p in slot_xy]
    # 桌面坐标：x 向前、y 向左；画成 y 横轴、x 纵轴更接近俯视观感
    for slot, (x, y) in enumerate(slot_xy):
        column, side = SLOT_ROLE[slot]
        on_event = slot in event
        ax.scatter(
            y, x,
            s=210 if on_event else 150,
            facecolor=color if on_event else "#dddddd",
            edgecolor="#333333",
            linewidth=1.4 if on_event else 0.8,
            zorder=3,
        )
        ax.annotate(
            str(slot), (y, x), ha="center", va="center", fontsize=8, zorder=4,
            color="white" if on_event else "#333333", weight="bold",
        )
        ax.annotate(
            f"列{column}/{'上' if side == 'high' else '下'}",
            (y, x), textcoords="offset points", xytext=(0, -15),
            ha="center", fontsize=5.5, color="#777777", zorder=4,
        )

    a, b = slot_xy[event[0]], slot_xy[event[1]]
    ax.annotate(
        "", xy=(b[1], b[0]), xytext=(a[1], a[0]),
        arrowprops=dict(arrowstyle="<->", color=color, lw=2.0,
                        connectionstyle="arc3,rad=0.18"),
        zorder=2,
    )

    pad = 0.06
    ax.set_xlim(max(ys) + pad, min(ys) - pad)  # y 轴反向，贴合俯视图
    ax.set_ylim(min(xs) - pad, max(xs) + pad)
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#cccccc")

    flag = "  ★原始" if record["is_original"] else ""
    dev = record.get("action_dev_max")
    dev_text = "" if not dev else f"\n动作偏差 {dev:.1e} rad(组{record.get('action_group')})"
    ax.set_title(
        f"var{record['variant_idx']}  槽位{event[0]}↔{event[1]}{flag}\n"
        f"{TOPO_LABEL[topo]}  d={record['pair_distance']:.3f}m{dev_text}",
        fontsize=6.5, color=color, pad=3,
    )


def draw_episode(task: str, src_episode: int, records: Sequence[dict], out_dir: Path) -> Path:
    records = sorted(records, key=lambda item: item["variant_idx"])
    fig, axes = plt.subplots(2, 3, figsize=(9.6, 7.0))
    for ax, record in zip(axes.flat, records):
        draw_clip(ax, record)
    for ax in axes.flat[len(records):]:
        ax.axis("off")

    first = records[0]
    fig.suptitle(
        f"{task} / 源 ep{src_episode}（env_seed={first['env_seed']}，{first['difficulty']}，"
        f"swap_times={first['swap_times']}）\n"
        f"每子图 = 一条 110 帧 clip；唯一事件 = 第一次 swap 换了哪两个槽位"
        f"（后续窗口按槽位固定，跨变体一致）",
        fontsize=10, y=0.98,
    )
    handles = [
        Line2D([0], [0], color=TOPO_COLOR[name], lw=2.4, label=TOPO_LABEL[name])
        for name in ("same_column", "cross_aligned", "cross_diagonal")
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.035, 1, 0.94))

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{task}_ep{src_episode}_clips.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="画 clip 变体 2D 简图")
    parser.add_argument("--gen-dir", required=True)
    parser.add_argument("--tasks", default=",".join(EVAL_TASKS))
    args = parser.parse_args(argv)

    gen_dir = Path(args.gen_dir).resolve()
    labels = json.loads((gen_dir / "clip_events.json").read_text(encoding="utf-8"))["records"]
    out_dir = gen_dir / "diagrams"

    written = []
    for task in (item.strip() for item in args.tasks.split(",") if item.strip()):
        by_source: dict[int, list[dict]] = {}
        for record in labels:
            if record["task"] == task:
                by_source.setdefault(record["src_episode"], []).append(record)
        for src_episode, records in sorted(by_source.items()):
            written.append(draw_episode(task, src_episode, records, out_dir))
    for path in written:
        print(f"已写出 {path}")
    print(f"共 {len(written)} 张简图")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
