#!/usr/bin/env python3
"""变体 2D 简图：每个源 episode 一张、每条 clip 一个子图。

一眼要看清的三件事：
1. 四个槽位的实际布局（bin 的初始 xy，即「允许的变化维度 1」）；
2. 这条 clip 的唯一事件 —— 第一次 swap 换了哪两个槽位（箭头 + 拓扑类别）；
3. 哪一条是 is_original（与官方 episode 逐位一致的那条）；
4. 这条 clip 里物理引擎**检测到了什么接触**（红框 = 容器互撞；机械臂 ↔ 容器实测 0/48）。

另出两张全局接触图：

* `contact_overview.png` —— 48 条 clip 的接触矩阵（谁撞了、多重、撞了几帧）；
* `contact_timeline.png` —— 每条 clip 的接触时间轴（接触落在 clip 的哪些帧）。

输出目录：{gen_dir}/diagrams/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import h5py  # noqa: E402
import numpy as np  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from clip_plan import CLIP_LEN, CLIP_MARGIN, EVAL_TASKS, SLOT_ROLE, swap_windows_clip  # noqa: E402

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

    # 接触检测：容器互撞用红色粗边框圈出（机械臂 ↔ 容器实测 0/48，若非 0 则另加标注）
    bb = record.get("contact_bin_bin_forceful_frames", 0)
    rb = record.get("contact_robot_bin_forceful_frames", 0)
    if bb:
        for spine in ax.spines.values():
            spine.set_color("#c00000")
            spine.set_linewidth(2.2)
        pairs = record.get("contact_bin_bin_forceful_pairs") or []
        ax.annotate(
            f"⚡容器互撞 {bb}帧  {'·'.join(f'{a}-{b}' for a, b in pairs)}\n"
            f"冲量max {record.get('contact_bin_bin_impulse_max', 0):.1f}"
            f"  起于 clip{record.get('contact_bin_bin_onset_clip_frame', -1)}",
            xy=(0.5, 0.015), xycoords="axes fraction", ha="center", va="bottom",
            fontsize=5.6, color="#c00000",
        )
    if rb:
        ax.annotate(f"机械臂↔容器 {rb}帧", xy=(0.5, 0.13), xycoords="axes fraction",
                    ha="center", fontsize=6.5, color="#000000", weight="bold")

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
    ] + [Patch(facecolor="none", edgecolor="#c00000", lw=2.2, label="红框=检测到容器互撞")]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.035, 1, 0.94))

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{task}_ep{src_episode}_clips.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


# ── 全局接触图：直接回答「哪些 clip 检测到了接触、是哪一类」 ─────────────────


def draw_contact_overview(records: list[dict], out_dir: Path) -> Path:
    """48 条 clip 的接触矩阵：行 = (task, 源 ep)，列 = var0..5。

    格子填色按容器互撞的最大冲量（对数刻度），格内写事件槽位、撞了几帧、涉及哪些容器对。
    机械臂 ↔ 容器接触若存在会用黑色粗边框圈出 —— 2026-08-18 实测 0/48，所以图上不会出现。
    """
    groups: dict[tuple[str, int], dict[int, dict]] = {}
    for record in records:
        groups.setdefault((record["task"], record["src_episode"]), {})[
            record["variant_idx"]
        ] = record
    keys = sorted(groups, key=lambda k: (k[0], k[1]))
    n_rows, n_cols = len(keys), 6

    impulses = [r.get("contact_bin_bin_impulse_max", 0.0) for r in records]
    vmax = max(impulses) or 1.0

    fig, ax = plt.subplots(figsize=(13.0, 1.05 * n_rows + 2.4))
    n_rb = sum(1 for r in records if r.get("contact_robot_bin_forceful_frames", 0))
    n_bb = sum(1 for r in records if r.get("contact_bin_bin_forceful_frames", 0))

    for row, key in enumerate(keys):
        for col in range(n_cols):
            record = groups[key].get(col)
            if record is None:
                continue
            bb = record.get("contact_bin_bin_forceful_frames", 0)
            rb = record.get("contact_robot_bin_forceful_frames", 0)
            imp = record.get("contact_bin_bin_impulse_max", 0.0)
            shade = 0.0 if not bb else 0.25 + 0.75 * (np.log10(imp + 1) / np.log10(vmax + 1))
            face = (1.0, 1.0 - 0.72 * shade, 1.0 - 0.72 * shade) if bb else "#f2f2f2"
            ax.add_patch(plt.Rectangle(
                (col, n_rows - row - 1), 1, 1, facecolor=face,
                edgecolor="#000000" if rb else "#bbbbbb",
                linewidth=2.6 if rb else 0.7, zorder=1,
            ))
            slots = tuple(record["event_slots"])
            label = f"var{col}  {slots[0]}↔{slots[1]}\n{TOPO_LABEL[record['topo_class']]}"
            if bb:
                pairs = record.get("contact_bin_bin_forceful_pairs") or []
                label += (f"\n⚡{bb}帧 J={imp:.1f}\n"
                          + "·".join(f"{a}-{b}" for a, b in pairs))
            else:
                label += "\n无接触"
            ax.annotate(label, (col + 0.5, n_rows - row - 0.5), ha="center", va="center",
                        fontsize=6.0, zorder=3,
                        color="#7a0000" if bb else "#666666")
        ax.annotate(f"{key[0].replace('UnmaskSwap','')}\nep{key[1]}",
                    (-0.06, n_rows - row - 0.5), ha="right", va="center", fontsize=8)

    ax.set_xlim(-0.9, n_cols); ax.set_ylim(0, n_rows)
    ax.set_xticks([]); ax.set_yticks([]); ax.axis("off")
    ax.set_title(
        "clip 接触检测总览（物理引擎 sapien get_contacts 实测，冲量 > 1e-9 才算「真的撞上」）\n"
        f"机械臂 ↔ 容器：{n_rb}/{len(records)} 条  ——  "
        f"容器 ↔ 容器互撞：{n_bb}/{len(records)} 条（全部落在第一次 swap 窗口内）",
        fontsize=11, pad=14,
    )
    handles = [
        Patch(facecolor="#f2f2f2", edgecolor="#bbbbbb", label="未检测到接触"),
        Patch(facecolor="#f5b0b0", edgecolor="#bbbbbb", label="容器互撞（色深=冲量大）"),
        Patch(facecolor="white", edgecolor="#000000", lw=2.6, label="机械臂↔容器接触（实测 0 条）"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8.5, frameon=False)
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "contact_overview.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def draw_contact_timeline(gen_dir: Path, records: list[dict], out_dir: Path) -> Path:
    """接触时间轴：每条 clip 一行，标出接触落在 clip 的哪些帧。

    需要逐帧数据，所以直接读 merged h5 的 `timestep_t/swap_gt/contact_*_impulse`。
    """
    by_task: dict[str, list[dict]] = {}
    for record in records:
        by_task.setdefault(record["task"], []).append(record)

    series: list[tuple[str, np.ndarray, np.ndarray, dict]] = []
    for task in sorted(by_task):
        entries = sorted(by_task[task], key=lambda r: (r["src_episode"], r["variant_idx"]))
        with h5py.File(gen_dir / f"record_dataset_{task}.h5", "r") as handle:
            for record in entries:
                group = handle[record["episode"].replace("ep", "episode_")]
                bb = np.array([
                    float(np.asarray(group[f"timestep_{t}"]["swap_gt"]["contact_bin_bin_impulse"]))
                    for t in range(CLIP_LEN)
                ])
                btn = np.array([
                    float(np.asarray(
                        group[f"timestep_{t}"]["swap_gt"]["contact_robot_button_impulse"]))
                    for t in range(CLIP_LEN)
                ])
                series.append((task, bb, btn, record))

    fig, ax = plt.subplots(figsize=(13.5, 0.30 * len(series) + 2.6))
    w0, w1 = swap_windows_clip(2)[0]
    ax.axvspan(w0, w1, color="#fff2cc", zorder=0)
    ax.axvspan(w1, CLIP_LEN, color="#f0f6ff", zorder=0)
    ax.axvspan(0, w0, color="#f6f6f6", zorder=0)

    for row, (task, bb, btn, record) in enumerate(series):
        y = len(series) - row - 1
        hit_btn = np.flatnonzero(btn > 1e-9)
        if hit_btn.size:
            ax.scatter(hit_btn, np.full(hit_btn.size, y), s=5, marker="s",
                       color="#4a90d9", zorder=2)
        hit_bb = np.flatnonzero(bb > 1e-9)
        if hit_bb.size:
            ax.scatter(hit_bb, np.full(hit_bb.size, y), s=26, marker="|",
                       color="#c00000", linewidths=1.9, zorder=3)
        slots = tuple(record["event_slots"])
        mark = "⚡" if hit_bb.size else "  "
        ax.annotate(
            f"{mark}{task.replace('UnmaskSwap','')[:3]} ep{record['src_episode']} "
            f"var{record['variant_idx']} {slots[0]}↔{slots[1]} {TOPO_LABEL[record['topo_class']]}",
            (-1.5, y), ha="right", va="center", fontsize=5.6,
            color="#c00000" if hit_bb.size else "#555555",
        )

    ax.set_xlim(-38, CLIP_LEN)
    ax.set_ylim(-1, len(series))
    ax.set_yticks([])
    ax.set_xticks([0, w0, 55, w1, CLIP_LEN])
    ax.set_xticklabels([
        "clip0\n(env34)", f"clip{w0}\n第一次swap起", "clip55\n事件中",
        f"clip{w1}\n第一次swap止", f"clip{CLIP_LEN}\n(env144)"], fontsize=7.5)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.set_title(
        "clip 接触时间轴 —— 接触发生在哪些帧\n"
        "黄底 = 第一次 swap 窗口（唯一事件）；蓝底 = 第二次 swap 露出的后 30 帧",
        fontsize=11, pad=12,
    )
    handles = [
        Line2D([0], [0], marker="|", color="#c00000", lw=0, markersize=9,
               markeredgewidth=2, label="容器 ↔ 容器互撞（有力）"),
        Line2D([0], [0], marker="s", color="#4a90d9", lw=0, markersize=5,
               label="机械臂 ↔ 按钮接触（任务本身，仅 Button）"),
        Line2D([0], [0], marker="x", color="#000000", lw=0, markersize=7,
               label="机械臂 ↔ 容器接触：全 48 条实测 0 帧，故图上无此标记"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "contact_timeline.png"
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
    written.append(draw_contact_overview(labels, out_dir))
    written.append(draw_contact_timeline(gen_dir, labels, out_dir))
    for path in written:
        print(f"已写出 {path}")
    print(f"共 {len(written)} 张图")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
