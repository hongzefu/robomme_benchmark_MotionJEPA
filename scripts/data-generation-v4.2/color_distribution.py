#!/usr/bin/env python3
"""颜色分布出图入口：把颜色表的判决结果画成图（v4.2 单口径）。

`fit_color_model.py` 产出的颜色表是一张 `颜色 → 三列计数` 的表（列 0 = 纯背景、
列 1 = 背景∪物体混合、列 2 = 机械臂）。推理时每种颜色被判成哪一类，完全由这张表
决定——**与画面内容无关**，所以判决分布可以脱离图片单独画出来，这正是本入口做的事。

判决口径只有一条，与 `ColorModel.classify` 逐位同源：**纯支撑三段式判据**——
`N₀ > 0` 判背景、`N₁ = 0 且 N₂ > 0` 判臂、其余判混合。计数的数值大小不参与判决，
只参与本入口的加权统计与出图。

### 三个口径必须分清（report 里逐个标注）

1. **色数口径**：一种颜色算一票，不管它出现过几次；
2. **像素量口径**：按该颜色在标定集里真实出现的像素数加权。单色像素数取
   `counts[:, MIX] + counts[:, ARM]`——混合列把每个背景/物体像素恰记一次、臂列把每个
   臂像素恰记一次，两者相加就是该颜色的真实出现次数（纯背景列与混合列是重叠计数，
   直接三列求和会把背景像素数重复计一遍）；
3. **判臂颜色的成分**：判成臂的那批颜色上，`counts[:, ARM]` 是标定集里真正的臂像素、
   `counts[:, MIX]` 是标定集里真正的非臂（背景∪物体）像素——后者就是「颜色阶段就已
   注定的误标上界」。⚠ 由判臂的定义（`N₁ = 0`）这个数**恒等于 0**，所以「颜色阶段
   精确率上界 = 1.000」是恒等式而不是经验数字；本入口照样把它算出来打印，是把恒等式
   当自校验用——不为 0 就说明表或算式坏了。

产物（`--out` 目录，默认 `outputs/color_distribution_val_ep0-9/`）：

- `color_distribution.png`：四面板大图（主图 / 亮度剖面 / 支撑集分解 / 共享色 TOP20）；
- `outputs/json/<out 目录名>.json`：上面全部数字的机读版（JSON 产物集中在 outputs/json/）。

用法：

    uv run --no-sync python scripts/data-generation-v4.2/color_distribution.py \\
      --model scripts/data-generation-v4.2/outputs/color_model.npz \\
      --out scripts/data-generation-v4.2/outputs/color_distribution_val_ep0-9
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import rgb_to_hsv  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from color_model import (  # noqa: E402
    CLASS_ARM,
    CLASS_BACKGROUND,
    CLASS_MIX,
    ColorModel,
)

# 与走查视频同一套深色版式，出图风格保持一致
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
BG = "#18181c"
FG = "#f0f0f0"
GRID = "#4a4a52"

# 三类的显示名与强调色（强调色只用于标题与图例，散点本身一律画颜色自己的 RGB）
CLASS_LABELS = ("纯背景", "背景∪物体混合", "机械臂")
CLASS_ACCENT = ("#8fb8ff", "#fab05a", "#78eb8c")


def setup_font() -> None:
    """注册思源宋体，让中文标题不掉成豆腐块。"""
    font_manager.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = "Noto Serif CJK JP"
    plt.rcParams["axes.unicode_minus"] = False


def unpack_rgb(colors: np.ndarray) -> np.ndarray:
    """(N,) uint32 打包色 → (N, 3) uint8，`color_model.pack_rgb` 的逆运算。"""
    packed = np.asarray(colors, dtype=np.uint32)
    return np.stack(
        [(packed >> 16) & 0xFF, (packed >> 8) & 0xFF, packed & 0xFF], axis=1
    ).astype(np.uint8)


def decide(counts: np.ndarray) -> np.ndarray:
    """颜色表 → 每种颜色的判决类别，与 `ColorModel.classify` 同一套三段支撑判据。

    刻意不复用 `classify`（它吃的是图像、还要处理未见颜色），而是在表上直接算：
    `N₀ > 0` 判背景、`N₁ = 0 且 N₂ > 0` 判臂、其余判混合。计数的数值大小不参与。
    `tests/lightweight/test_color_distribution_v4_2.py` 用合成表逐位对拍两条路径。
    """
    counts = np.asarray(counts)
    if counts.size and not np.all(counts.sum(axis=1) > 0):
        bad = int(np.flatnonzero(counts.sum(axis=1) <= 0)[0])
        raise ValueError(
            f"颜色表存在三列全零行（第 {bad} 行）：这种行会被静默判成混合，"
            "表里只该收录真实出现过的颜色"
        )
    winner = np.full(counts.shape[0], CLASS_MIX, dtype=np.int64)
    winner[counts[:, CLASS_BACKGROUND] > 0] = CLASS_BACKGROUND
    winner[(counts[:, CLASS_MIX] == 0) & (counts[:, CLASS_ARM] > 0)] = CLASS_ARM
    return winner


def color_features(rgb: np.ndarray) -> dict[str, np.ndarray]:
    """(N, 3) uint8 → 亮度 / 饱和度 / 色相，全部归一化到 [0, 1]。"""
    unit = rgb.astype(np.float64) / 255.0
    hsv = rgb_to_hsv(unit)
    return {
        "luma": unit @ np.array([0.299, 0.587, 0.114]),
        "sat": hsv[:, 1],
        "hue": hsv[:, 0],
    }


def shared_colors(counts: np.ndarray) -> np.ndarray:
    """臂∩混合共享色的布尔掩码：两列都见过 = 判臂条件差一步、被规则挡下的那批。

    它就是颜色阶段漏标代价的**全部**来源（判臂要求 `N₁ = 0`，而这些色 `N₁ > 0`），
    实测 126 色、带走 9.0789% 的臂像素，且全是 `R=G=B` 的中性灰白。
    """
    counts = np.asarray(counts)
    return (counts[:, CLASS_ARM] > 0) & (counts[:, CLASS_MIX] > 0)


def _style(axis: plt.Axes, title: str, xlabel: str = "", ylabel: str = "") -> None:
    axis.set_facecolor(BG)
    axis.set_title(title, color=FG, fontsize=12, pad=8)
    axis.tick_params(colors=FG, labelsize=9)
    for spine in axis.spines.values():
        spine.set_color(GRID)
    if xlabel:
        axis.set_xlabel(xlabel, color=FG, fontsize=10)
    if ylabel:
        axis.set_ylabel(ylabel, color=FG, fontsize=10)


def _panel_plane(
    axis: plt.Axes,
    rgb: np.ndarray,
    features: dict[str, np.ndarray],
    winner: np.ndarray,
    shared: np.ndarray,
) -> None:
    """面板 A：亮度 × 饱和度，三类画在**同一张图**上，每个点用它自己的 RGB 上色。

    这个平面对本链路最有分辨力——机械臂是低饱和的灰白壳体（挤在 S≈0 那条竖线上），
    任务物体大多带彩色（散在右侧），桌面背景是一大团橙木色。整条规则的全部矛盾就在
    S≈0 那条线上：灰白臂壳与灰白物体高光在 24 位 RGB 上完全同色。126 个共享色用红圈
    标出来，一眼看到它们确实全落在那条线上。
    """
    for class_index, marker, size, edge in (
        (CLASS_BACKGROUND, "o", 7, "#5a5a62"),
        (CLASS_MIX, "s", 13, "#8a8a92"),
        (CLASS_ARM, "o", 30, "#f0f0f0"),
    ):
        selected = winner == class_index
        axis.scatter(
            features["sat"][selected],
            features["luma"][selected],
            c=rgb[selected] / 255.0,
            s=size,
            marker=marker,
            linewidths=0.35 if class_index == CLASS_ARM else 0.15,
            edgecolors=edge,
            zorder=2 + class_index,
        )
    # ⚠ 共享色几乎全落在 S≈0 那一条竖线上，圈画大了会叠成一根实心红条（实测），
    # 反而看不出「一个个颜色」。所以用小而细的空心圈，再拉一条标注线点名那条竖线。
    axis.scatter(
        features["sat"][shared],
        features["luma"][shared],
        s=26,
        marker="o",
        facecolors="none",
        edgecolors="#ff4d4d",
        linewidths=0.7,
        zorder=6,
    )
    axis.annotate(
        f"{int(shared.sum())} 个共享色全部落在\nS≈0 这条灰白竖线上",
        xy=(0.012, 0.30),
        xytext=(0.20, 0.16),
        color="#ff8f8f",
        fontsize=10,
        arrowprops=dict(arrowstyle="->", color="#ff4d4d", linewidth=1.0),
        zorder=7,
    )
    # 图例里的色块只是各类的代表色（真实点一律画颜色本身），形状才是类别标识
    legend_specs = (
        ("o", 5, "#d9a06a", "#5a5a62", f"判背景 {int((winner == CLASS_BACKGROUND).sum())} 色"),
        ("s", 6, "#b47ad0", "#8a8a92", f"判混合 {int((winner == CLASS_MIX).sum())} 色"),
        ("o", 7, "#c8c8c8", "#f0f0f0", f"判机械臂 {int((winner == CLASS_ARM).sum())} 色"),
        ("o", 9, "none", "#ff4d4d", f"臂∩混合共享色 {int(shared.sum())} 色（被规则挡下）"),
    )
    axis.legend(
        handles=[
            plt.Line2D(
                [], [], marker=marker, linestyle="", markersize=size,
                markerfacecolor=face, markeredgecolor=edge, label=label,
            )
            for marker, size, face, edge, label in legend_specs
        ],
        facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=9, loc="upper right",
    )
    axis.set_xlim(-0.04, 1.04)
    axis.set_ylim(-0.04, 1.04)
    axis.grid(color=GRID, linewidth=0.4, alpha=0.5)


def _panel_luma(
    axis: plt.Axes,
    counts: np.ndarray,
    features: dict[str, np.ndarray],
    shared: np.ndarray,
) -> None:
    """面板 B：亮度轴上的臂 vs 非臂剖面（像素量口径），红色填充 = 共享色带走的部分。

    两条曲线各自按自己的总量归一化，所以看的是**形状**不是高度。两条同时抬起来的
    亮度段就是灰白重叠区；红色填充是这段重叠里真正付出的代价——它与臂曲线同分母，
    是臂曲线的一部分，面积恰等于共享色带走的臂像素占比。
    """
    edges = np.linspace(0.0, 1.0, 61)
    centers = (edges[:-1] + edges[1:]) / 2
    arm_pixels = counts[:, CLASS_ARM].astype(np.float64)
    non_arm_pixels = counts[:, CLASS_MIX].astype(np.float64)
    arm_total = max(float(arm_pixels.sum()), 1.0)
    non_arm_total = max(float(non_arm_pixels.sum()), 1.0)

    hist_arm, _ = np.histogram(features["luma"], bins=edges, weights=arm_pixels)
    hist_non_arm, _ = np.histogram(features["luma"], bins=edges, weights=non_arm_pixels)
    hist_shared, _ = np.histogram(
        features["luma"][shared], bins=edges, weights=arm_pixels[shared]
    )

    axis.fill_between(
        centers,
        hist_shared / arm_total,
        color="#ff4d4d",
        alpha=0.55,
        zorder=2,
        label=f"其中被共享色带走 {float(arm_pixels[shared].sum()) / arm_total:.2%}",
    )
    axis.plot(
        centers, hist_arm / arm_total, color=CLASS_ACCENT[CLASS_ARM],
        linewidth=2.0, zorder=3, label="机械臂像素",
    )
    axis.plot(
        centers, hist_non_arm / non_arm_total, color=CLASS_ACCENT[CLASS_MIX],
        linewidth=1.5, linestyle="--", alpha=0.85, zorder=3,
        label="非臂像素（背景∪物体）",
    )
    axis.legend(facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=9)
    axis.grid(color=GRID, linewidth=0.4, alpha=0.5)
    axis.set_xlim(0.0, 1.0)


def _panel_support(axis: plt.Axes, counts: np.ndarray, shared: np.ndarray) -> None:
    """面板 C：臂列见过的那批色怎么被拆成「判臂」与「被挡下」两块。

    上下两行是同一个域（臂列见过的色 / 全部臂像素），只是口径不同。两个百分比不一样
    正说明共享色单个更「重」——它们是大面积的中性灰白，色数上占少数、像素上占多数。
    """
    seen_arm = counts[:, CLASS_ARM] > 0
    kept = seen_arm & ~shared
    rows = (
        ("色数口径", int(kept.sum()), int(shared.sum()), "色"),
        (
            "像素量口径",
            int(counts[kept, CLASS_ARM].sum()),
            int(counts[shared, CLASS_ARM].sum()),
            "px",
        ),
    )
    for position, (_, keep_value, drop_value, unit) in enumerate(rows):
        total = max(keep_value + drop_value, 1)
        axis.barh(
            position, keep_value / total, color=CLASS_ACCENT[CLASS_ARM],
            edgecolor=GRID, height=0.78,
        )
        axis.barh(
            position, drop_value / total, left=keep_value / total,
            color="#ff4d4d", edgecolor=GRID, height=0.5,
        )
        axis.text(
            0.015, position, f"判臂 {keep_value:,} {unit}（{keep_value / total:.2%}）",
            color="#18181c", fontsize=11, va="center",
        )
        axis.text(
            0.985, position, f"挡下 {drop_value:,} {unit}（{drop_value / total:.2%}）",
            color=FG, fontsize=11, va="center", ha="right",
        )
    axis.set_yticks(range(len(rows)))
    axis.set_yticklabels([row[0] for row in rows])
    axis.set_xticks([])
    axis.set_xlim(0.0, 1.0)
    axis.invert_yaxis()


def _panel_shared_top(
    axis: plt.Axes,
    rgb: np.ndarray,
    counts: np.ndarray,
    shared: np.ndarray,
    limit: int = 20,
) -> None:
    """面板 D：共享色里带走臂像素最多的前 N 个，条形本身就涂成那个颜色。

    实测全是 `R=G=B` 的中性灰白，`#6C6C6C` 一个色就吃掉约 3% 的臂像素。这张图就是
    「灰白臂壳与灰白物体在 24 位 RGB 上完全同色」这句话的具体清单。
    """
    arm_total = max(int(counts[:, CLASS_ARM].sum()), 1)
    order = np.flatnonzero(shared)[np.argsort(-counts[shared, CLASS_ARM])][:limit]
    values = counts[order, CLASS_ARM] / arm_total * 100.0
    axis.barh(
        np.arange(order.size),
        values,
        color=[tuple(float(value) / 255.0 for value in rgb[index]) for index in order],
        edgecolor="#8a8a92",
        linewidth=0.6,
        height=0.72,
    )
    axis.set_yticks(np.arange(order.size))
    axis.set_yticklabels(
        ["#{:02X}{:02X}{:02X}".format(*rgb[index]) for index in order], fontsize=8
    )
    axis.invert_yaxis()
    axis.grid(color=GRID, linewidth=0.4, alpha=0.5, axis="x")
    axis.set_xlim(0.0, float(values.max()) * 1.18 if values.size else 1.0)


def render_distribution(model: ColorModel, out_path: Path) -> Path:
    """出判决分布大图：四个面板，每个回答一个问题。"""
    rgb = unpack_rgb(model.colors)
    counts = model.counts
    winner = decide(counts)
    features = color_features(rgb)
    shared = shared_colors(counts)
    arm_total = max(int(counts[:, CLASS_ARM].sum()), 1)
    shared_share = float(counts[shared, CLASS_ARM].sum()) / arm_total

    figure = plt.figure(figsize=(19.0, 13.0), facecolor=BG)
    grid = figure.add_gridspec(
        2,
        2,
        hspace=0.26,
        wspace=0.16,
        width_ratios=[1.3, 1.0],
        height_ratios=[1.0, 0.82],
        left=0.05,
        right=0.98,
        top=0.88,
        bottom=0.06,
    )
    figure.suptitle(
        "v4.2 颜色表判决分布 · 纯支撑三段式判据（唯一口径）\n"
        f"标定集 val ep0-9 · 唯一颜色 {model.colors.size} 种 · "
        "判决只看每列见过没见过，计数的数值大小不参与，也与画面内容无关",
        color=FG,
        fontsize=17,
        y=0.965,
    )

    axis = figure.add_subplot(grid[0, 0])
    _panel_plane(axis, rgb, features, winner, shared)
    _style(axis, "A · 三类在颜色空间怎么切的（点色 = 颜色本身）", "饱和度 S", "亮度 luma")

    axis = figure.add_subplot(grid[0, 1])
    _panel_luma(axis, counts, features, shared)
    _style(axis, "B · 亮度轴剖面（像素量口径，两条各自归一化）", "亮度 luma", "占本类像素比例")

    axis = figure.add_subplot(grid[1, 0])
    _panel_support(axis, counts, shared)
    _style(
        axis,
        f"C · 全表 {model.colors.size} 色 → 臂列见过 "
        f"{int((counts[:, CLASS_ARM] > 0).sum())} 色 → 判臂 "
        f"{int((winner == CLASS_ARM).sum())} 色",
    )

    axis = figure.add_subplot(grid[1, 1])
    _panel_shared_top(axis, rgb, counts, shared)
    _style(
        axis,
        f"D · 共享色 TOP20（{int(shared.sum())} 色共带走 {shared_share:.2%} 臂像素）",
        "带走的臂像素占全部臂像素 %",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, dpi=110, facecolor=BG)
    plt.close(figure)
    return out_path


def compute_stats(model: ColorModel) -> dict[str, Any]:
    """判决的全部可引用数字，口径逐个写清楚。"""
    counts = model.counts
    pixels = (counts[:, CLASS_MIX] + counts[:, CLASS_ARM]).astype(np.int64)
    total_pixels = int(pixels.sum())
    winner_all = decide(counts)

    def side(winner: np.ndarray) -> dict[str, Any]:
        arm_colors = winner == CLASS_ARM
        return {
            "各类色数": {
                CLASS_LABELS[index]: int((winner == index).sum()) for index in range(3)
            },
            "各类像素数": {
                CLASS_LABELS[index]: int(pixels[winner == index].sum())
                for index in range(3)
            },
            "各类像素占比": {
                CLASS_LABELS[index]: round(
                    float(pixels[winner == index].sum()) / total_pixels, 6
                )
                for index in range(3)
            },
            "判臂颜色上的真实臂像素": int(counts[arm_colors, CLASS_ARM].sum()),
            "判臂颜色上的真实非臂像素": int(counts[arm_colors, CLASS_MIX].sum()),
            "颜色阶段召回上界": round(
                float(counts[arm_colors, CLASS_ARM].sum())
                / max(int(counts[:, CLASS_ARM].sum()), 1),
                6,
            ),
            "颜色阶段精确率上界": round(
                float(counts[arm_colors, CLASS_ARM].sum())
                / max(
                    int(
                        counts[arm_colors, CLASS_ARM].sum()
                        + counts[arm_colors, CLASS_MIX].sum()
                    ),
                    1,
                ),
                6,
            ),
        }

    stats: dict[str, Any] = {
        "口径说明": {
            "色数口径": "一种颜色算一票，不看出现次数",
            "像素量口径": "按 counts[:, 混合] + counts[:, 臂] 加权，即该色在标定集里真实出现的像素数",
            "颜色阶段召回上界": "判臂颜色上的真实臂像素 / 全部臂像素；形态学只会再往下砍，故是上界",
            "颜色阶段精确率上界": "判臂颜色上的真实臂像素 / 判臂颜色上的全部像素",
        },
        "唯一颜色数": int(model.colors.size),
        "总像素数": total_pixels,
        "各列像素数": {
            "纯背景": int(counts[:, CLASS_BACKGROUND].sum()),
            "背景∪物体混合": int(counts[:, CLASS_MIX].sum()),
            "机械臂": int(counts[:, CLASS_ARM].sum()),
        },
        "各列支撑色数": {
            "纯背景": int((counts[:, CLASS_BACKGROUND] > 0).sum()),
            "背景∪物体混合": int((counts[:, CLASS_MIX] > 0).sum()),
            "机械臂": int((counts[:, CLASS_ARM] > 0).sum()),
        },
        "判决": side(winner_all),
    }

    # 规则的代价：臂∩混合共享色。判臂要求「混合列没见过」，而这些色混合列见过，
    # 所以它们就是颜色阶段漏标的**全部**来源——一分不多、一分不少。
    shared = shared_colors(counts)
    arm_total = max(int(counts[:, CLASS_ARM].sum()), 1)
    stats["否决代价"] = {
        "口径": "臂∩混合共享色（两列都见过），纯支撑集定义",
        "共享色数": int(shared.sum()),
        "共享色带走的臂像素": int(counts[shared, CLASS_ARM].sum()),
        "共享色带走的臂像素占比": round(
            float(counts[shared, CLASS_ARM].sum()) / arm_total, 6
        ),
        "共享色上的非臂像素": int(counts[shared, CLASS_MIX].sum()),
    }

    # 共享色明细：按带走的臂像素降序，供 report 直接列表。它们全是灰白系——
    # 灰白臂壳与灰白任务物体在 24 位 RGB 上完全同色，这是否决代价的全部来源。
    rgb = unpack_rgb(model.colors)
    order = np.flatnonzero(shared)[np.argsort(-counts[shared, CLASS_ARM])]
    stats["共享色明细"] = [
        {
            "hex": "#{:02X}{:02X}{:02X}".format(*rgb[index]),
            "rgb": [int(value) for value in rgb[index]],
            "臂像素": int(counts[index, CLASS_ARM]),
            "混合像素": int(counts[index, CLASS_MIX]),
            "占全部臂像素": round(float(counts[index, CLASS_ARM]) / arm_total, 6),
        }
        for index in order[:20]
    ]
    return stats


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=str(SCRIPT_DIR / "outputs" / "color_model.npz"),
        help="fit_color_model.py 产出的颜色表",
    )
    parser.add_argument(
        "--out",
        default=str(SCRIPT_DIR / "outputs" / "color_distribution_val_ep0-9"),
        help="产物目录",
    )
    args = parser.parse_args(argv)

    setup_font()
    model = ColorModel.load(args.model)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = compute_stats(model)

    written = [render_distribution(model, out_dir / "color_distribution.png")]

    payload = dict(stats)
    payload["颜色表"] = args.model
    json_dir = out_dir.parent / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    (json_dir / f"{out_dir.name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for path in written:
        print(f"已写出 {path}")

    # 恒等式自校验：判臂色上的非臂像素必须为 0（判臂条件 N₁ = 0 的直接推论）
    false_upper = payload["判决"]["判臂颜色上的真实非臂像素"]
    if false_upper != 0:
        raise SystemExit(
            f"⚠ 恒等式被破坏：判臂颜色上的真实非臂像素 = {false_upper}，应恒为 0；"
            "说明颜色表或判别算式出了问题，产物不可信"
        )
    print(json.dumps(payload["判决"], ensure_ascii=False, indent=2))
    print(json.dumps(payload["否决代价"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
