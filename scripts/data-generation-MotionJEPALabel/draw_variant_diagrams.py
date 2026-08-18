#!/usr/bin/env python3
"""swap 变体 2D 简图：每个源 episode 一张 PNG，每个派生变体一个子图。

子图内容（俯视）：bin 按真实坐标/尺寸画方块，方块内的小色块 = 该 bin 底下藏的
cube 颜色（灰斜线 = 空诱饵）；金色粗框 = 第一抓取目标（藏 color_names[0] cube），
银色虚线框 = 第二抓取目标（pick_times=2 时）；双向弧线箭头 = 交换，圈号 ①②③ =
交换次序（同一对重复交换用不同弧度错开）；★橙底 = 原始组合（is_original）；
⚠ = min_clearance < 0.055 m（对角交换穿越旁观 bin，验收同口径）。

数据源：phase0 的布局指纹（同源变体布局逐位相同）+ episode_map（交换序列）。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Patch, Rectangle  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent

plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

BIN_SIDE = 0.055  # bin 物理边长（米），与仿真同尺
CUBE_COLORS = {"red": "#d62728", "green": "#2ca02c", "blue": "#1f77b4"}
BIN_FACE = "#f3ead8"
ARROW_COLORS = ["#222222", "#8e24aa", "#e07b00"]  # 第 1/2/3 次交换
CLEARANCE_DEGENERATE = 0.055


def _load_fingerprints(phase0_dir: Path) -> dict[tuple[str, int], dict]:
    payload = json.loads((phase0_dir / "original_index.json").read_text(encoding="utf-8"))
    return {(r["task"], int(r["episode"])): r["fingerprint"] for r in payload["records"]}


def _grid(n: int) -> tuple[int, int]:
    """变体数 → (行, 列)。方案钉死的几档 + 兜底。"""
    fixed = {3: (1, 3), 6: (2, 3), 9: (3, 3), 36: (6, 6), 216: (18, 12)}
    if n in fixed:
        return fixed[n]
    cols = math.ceil(math.sqrt(n))
    return math.ceil(n / cols), cols


def _arc_offsets(pairs: list[tuple[int, int]]) -> list[float]:
    """每次交换的弧度：按次序取不同基准，同一对重复出现时再错开，避免弧线重叠。"""
    base = [0.22, -0.30, 0.42]
    seen: dict[tuple[int, int], int] = {}
    offsets = []
    for k, pair in enumerate(pairs):
        occurrence = seen.get(pair, 0)
        seen[pair] = occurrence + 1
        offsets.append(base[k % 3] + 0.10 * occurrence * (1 if base[k % 3] > 0 else -1))
    return offsets


def draw_variant(ax, fingerprint: dict, entry: dict, compact: bool) -> None:
    bins_xy = np.array([b["p"][:2] for b in fingerprint["bins"]])
    bin_to_color = fingerprint["bin_to_color"]
    color_names = fingerprint["color_names"]
    pick_times = fingerprint["pick_times"]
    # 目标 bin：selected_bin_indices[i] 藏 color_names[i]
    selected = fingerprint["selected_bin_indices"]
    target1 = selected[0]
    target2 = selected[1] if pick_times == 2 and len(selected) > 1 else None

    label_fs = 4.5 if compact else 7
    num_fs = 5.5 if compact else 8

    for idx, (x, y) in enumerate(bins_xy):
        half = BIN_SIDE / 2
        ax.add_patch(
            Rectangle((x - half, y - half), BIN_SIDE, BIN_SIDE, facecolor=BIN_FACE,
                      edgecolor="#6b5b3e", linewidth=0.8, zorder=2)
        )
        color = bin_to_color.get(str(idx))
        if color in CUBE_COLORS:
            inner = BIN_SIDE * 0.52
            ax.add_patch(
                Rectangle((x - inner / 2, y - inner / 2), inner, inner,
                          facecolor=CUBE_COLORS[color], edgecolor="none", zorder=3)
            )
        else:
            inner = BIN_SIDE * 0.52
            ax.add_patch(
                Rectangle((x - inner / 2, y - inner / 2), inner, inner,
                          facecolor="#d8d8d8", edgecolor="#999999", linewidth=0.4,
                          hatch="////", zorder=3)
            )
        if idx == target1:
            ax.add_patch(
                Rectangle((x - half * 1.28, y - half * 1.28), BIN_SIDE * 1.28, BIN_SIDE * 1.28,
                          facecolor="none", edgecolor="#DAA520", linewidth=1.8, zorder=4)
            )
        elif target2 is not None and idx == target2:
            ax.add_patch(
                Rectangle((x - half * 1.28, y - half * 1.28), BIN_SIDE * 1.28, BIN_SIDE * 1.28,
                          facecolor="none", edgecolor="#9e9e9e", linewidth=1.2,
                          linestyle=(0, (3, 2)), zorder=4)
            )
        ax.annotate(str(idx), (x - half, y + half), ha="right", va="bottom",
                    fontsize=label_fs, color="#444444", zorder=5)

    pairs = [tuple(p) for p in entry["pairs"]]
    for k, ((i, j), rad) in enumerate(zip(pairs, _arc_offsets(pairs))):
        a, b = bins_xy[i], bins_xy[j]
        ax.add_patch(
            FancyArrowPatch(a, b, connectionstyle=f"arc3,rad={rad}",
                            arrowstyle="<|-|>", mutation_scale=7 if compact else 10,
                            color=ARROW_COLORS[k % 3], linewidth=1.0 if compact else 1.5,
                            shrinkA=4, shrinkB=4, zorder=6)
        )
        mid = (a + b) / 2
        delta = b - a
        norm = np.linalg.norm(delta)
        perp = np.array([-delta[1], delta[0]]) / (norm + 1e-9)
        pos = mid + perp * rad * norm * 0.5
        ax.annotate(chr(0x2460 + k), pos, ha="center", va="center", fontsize=num_fs,
                    color=ARROW_COLORS[k % 3], zorder=7,
                    bbox=dict(boxstyle="circle,pad=0.08", fc="white",
                              ec=ARROW_COLORS[k % 3], lw=0.6))

    title = f"var{entry['variant_idx']}  {entry['signature']}"
    color = "#222222"
    if entry["is_original"] == 1:
        title = "★ " + title + "（原始）"
        color = "#c85a00"
        ax.set_facecolor("#fff3e0")
    if entry["min_clearance"] < CLEARANCE_DEGENERATE:
        title += " ⚠"
    ax.set_title(title, fontsize=5.5 if compact else 8.5, color=color, pad=2)

    pad = 0.055
    ax.set_xlim(bins_xy[:, 0].min() - pad, bins_xy[:, 0].max() + pad)
    ax.set_ylim(bins_xy[:, 1].min() - pad, bins_xy[:, 1].max() + pad)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#cccccc")
        spine.set_linewidth(0.5)


def _figure_legend(fig, fingerprint: dict) -> None:
    pick_times = fingerprint["pick_times"]
    handles = [
        Patch(facecolor=CUBE_COLORS["red"], label="藏红 cube"),
        Patch(facecolor=CUBE_COLORS["green"], label="藏绿 cube"),
        Patch(facecolor=CUBE_COLORS["blue"], label="藏蓝 cube"),
        Patch(facecolor="#d8d8d8", hatch="////", label="空诱饵 bin"),
        Patch(facecolor="none", edgecolor="#DAA520", linewidth=1.8, label="第一抓取目标"),
    ]
    if pick_times == 2:
        handles.append(
            Patch(facecolor="none", edgecolor="#9e9e9e", linewidth=1.2,
                  linestyle=(0, (3, 2)), label="第二抓取目标")
        )
    handles += [
        Line2D([], [], color=ARROW_COLORS[0], marker="$①$", markersize=9,
               linewidth=1.5, label="第 n 次交换（圈号=次序）"),
        Patch(facecolor="#fff3e0", edgecolor="#c85a00", label="★ 原始组合"),
        Patch(facecolor="white", edgecolor="#888888", label="⚠ 低间隙（<0.055m，穿越旁观 bin）"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8, frameon=False,
               columnspacing=1.2, handletextpad=0.6)


def draw_episode(task: str, episode: int, fingerprint: dict, entries: list[dict],
                 out_dir: Path) -> Path:
    entries = sorted(entries, key=lambda item: item["variant_idx"])
    n = len(entries)
    rows, cols = _grid(n)
    compact = n > 40
    cell = 1.55 if compact else 2.3
    extra = 2.3  # 顶部两行标题 + 底部三列图例的预留高度（英寸）
    height = rows * cell + extra
    fig, axes = plt.subplots(rows, cols, figsize=(max(cols * cell, 7.2), height))
    axes = np.atleast_1d(axes).ravel()

    for ax, entry in zip(axes, entries):
        draw_variant(ax, fingerprint, entry, compact)
    for ax in axes[n:]:
        ax.axis("off")

    k = len(entries[0]["pairs"])
    fig.suptitle(
        f"{task} 源 ep{episode}（env_seed {entries[0]['env_seed']}，"
        f"{entries[0]['difficulty']}，{k} 次交换，共 {n} 个变体）俯视布局\n"
        f"目标语言：pick up the container that hides the "
        f"{fingerprint['color_names'][0]} cube",
        fontsize=11, y=1 - 0.12 / height,
    )
    _figure_legend(fig, fingerprint)
    fig.tight_layout(rect=(0, 1.35 / height, 1, 1 - 1.0 / height))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{task}_ep{episode}_variants.png"
    fig.savefig(out_path, dpi=110 if compact else 140)
    plt.close(fig)
    return out_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="画 swap 变体 2D 简图（每源 episode 一张）")
    parser.add_argument("--phase0-dir", default=str(SCRIPT_DIR / "outputs" / "phase0"))
    parser.add_argument("--gen-dir", default=str(SCRIPT_DIR / "outputs" / "full"))
    parser.add_argument("--out-dir", default=None, help="默认 <gen-dir>/diagrams")
    parser.add_argument("--tasks", default="VideoUnmaskSwap,ButtonUnmaskSwap")
    parser.add_argument("--episodes", default="90,91,92,93")
    args = parser.parse_args(argv)

    gen_dir = Path(args.gen_dir).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else gen_dir / "diagrams"
    fingerprints = _load_fingerprints(Path(args.phase0_dir))

    for task in (t.strip() for t in args.tasks.split(",") if t.strip()):
        episode_map = json.loads(
            (gen_dir / f"episode_map_{task}.json").read_text(encoding="utf-8")
        )["records"]
        for episode in (int(e) for e in args.episodes.split(",") if e.strip()):
            entries = [r for r in episode_map if r["src_episode"] == episode]
            if not entries:
                print(f"跳过 {task}/ep{episode}：episode_map 无记录", file=sys.stderr)
                continue
            path = draw_episode(task, episode, fingerprints[(task, episode)], entries, out_dir)
            print(f"{task}/ep{episode}: {len(entries)} 个变体 → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
