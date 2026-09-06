"""画 Persistent suite 四个任务（ButtonUnmask / VideoUnmask / VideoUnmaskSwap / ButtonUnmaskSwap）
的 episode 长度分布。

长度直接数 h5 里的 `timestep_*` 个数（不解帧），难度读 `env_metadata/{split}/`。
每个任务一格：按难度分色的堆叠直方图 + 用该任务 (mean, sd) 画的正态曲线，
另标出 min / median / max / mean / sd 与 Shapiro-Wilk 正态性检验的 p 值。
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from scipy import stats  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
TASKS = ["ButtonUnmask", "VideoUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap"]
DIFFICULTIES = ["easy", "medium", "hard"]
DIFF_COLOR = {"easy": "#6DAF8F", "medium": "#E0A458", "hard": "#C4553D"}


def setup_font() -> None:
    for path in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    ):
        if Path(path).exists():
            try:
                font_manager.fontManager.addfont(path)
            except Exception:  # noqa: BLE001
                continue
    for name in ("Noto Sans CJK JP", "Noto Sans CJK SC", "Noto Serif CJK JP"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def load_lengths(h5_dir: Path, split: str) -> dict[str, list[tuple[int, str]]]:
    """返回 {task: [(长度, 难度), ...]}。长度只数 timestep_* 的个数，不读帧。"""
    meta_root = REPO_ROOT / "src" / "robomme" / "env_metadata" / split
    out: dict[str, list[tuple[int, str]]] = {}
    for task in TASKS:
        meta_path = meta_root / f"record_dataset_{task}_metadata.json"
        difficulty = {}
        if meta_path.exists():
            difficulty = {
                int(r["episode"]): r["difficulty"]
                for r in json.loads(meta_path.read_text(encoding="utf-8"))["records"]
            }
        with h5py.File(h5_dir / f"record_dataset_{task}.h5", "r") as handle:
            episodes = sorted(
                int(name.split("_")[1]) for name in handle if name.startswith("episode_")
            )
            out[task] = [
                (
                    sum(1 for k in handle[f"episode_{e}"] if k.startswith("timestep_")),
                    difficulty.get(e, "unknown"),
                )
                for e in episodes
            ]
    return out


def draw(ax, task: str, rows: list[tuple[int, str]]) -> None:
    lengths = [n for n, _ in rows]
    mean, sd = statistics.mean(lengths), statistics.stdev(lengths)
    bins = np.histogram_bin_edges(lengths, bins=18)
    per_level = [
        [n for n, d in rows if d == level]
        for level in DIFFICULTIES
        if any(d == level for _, d in rows)
    ]
    labels = [level for level in DIFFICULTIES if any(d == level for _, d in rows)]
    ax.hist(
        per_level,
        bins=bins,
        stacked=True,
        color=[DIFF_COLOR[k] for k in labels],
        label=labels,
        edgecolor="white",
        linewidth=0.4,
    )
    # 用该任务的 (mean, sd) 画正态曲线，缩放到与直方图同一计数尺度，便于对照形状
    xs = np.linspace(min(lengths), max(lengths), 240)
    scale = len(lengths) * (bins[1] - bins[0])
    ax.plot(xs, stats.norm.pdf(xs, mean, sd) * scale, color="#3A4247", lw=1.3, label="正态拟合")
    ax.axvline(mean, color="#3A4247", ls="--", lw=0.9)
    ax.axvline(statistics.median(lengths), color="#7B6FC9", ls=":", lw=1.1)

    shapiro_p = stats.shapiro(lengths).pvalue
    ax.set_title(task, fontsize=10)
    ax.set_xlabel("整条长度（timestep）", fontsize=8)
    ax.set_ylabel("episode 数", fontsize=8)
    ax.tick_params(labelsize=7.5)
    ax.grid(axis="y", alpha=0.22, lw=0.6)
    ax.set_axisbelow(True)
    ax.text(
        0.98,
        0.96,
        f"n={len(lengths)}  min={min(lengths)}  max={max(lengths)}\n"
        f"mean={mean:.1f}  sd={sd:.1f}  中位={statistics.median(lengths):.0f}\n"
        f"Shapiro-Wilk p={shapiro_p:.2g}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=6.8,
        linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#DDE4E1", alpha=0.9),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Persistent suite 四任务的长度分布")
    parser.add_argument("--h5-dir", default="/data/hongzefu/robomme_data_h5")
    parser.add_argument("--split", default="train", choices=("train", "test", "val"))
    parser.add_argument("--out", default=str(HERE / "reports" / "figures" / "length_dist_persistent.png"))
    args = parser.parse_args(argv)

    setup_font()
    data = load_lengths(Path(args.h5_dir), args.split)
    fig, axes = plt.subplots(2, 2, figsize=(9.6, 6.2))
    for ax, task in zip(axes.ravel(), TASKS):
        draw(ax, task, data[task])
        print(
            f"{task:18s} n={len(data[task]):3d} "
            f"mean={statistics.mean([n for n, _ in data[task]]):6.1f} "
            f"sd={statistics.stdev([n for n, _ in data[task]]):5.1f} "
            f"Shapiro p={stats.shapiro([n for n, _ in data[task]]).pvalue:.3g}"
        )
    axes[0][0].legend(fontsize=7, loc="center right", framealpha=0.9)
    fig.suptitle(
        f"Persistent suite 四任务的 episode 长度分布（{args.split} split，虚线 = 均值，点线 = 中位）",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"已写出 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
