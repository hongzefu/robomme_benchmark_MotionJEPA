#!/usr/bin/env python3
"""颜色分布出图入口：把 v4.1 颜色表的判决结果画成图，veto / noveto 各一版。

`fit_color_model.py` 产出的颜色表是一张 `颜色 → 三列计数` 的表（列 0 = 纯背景、
列 1 = 背景∪物体混合、列 2 = 机械臂）。推理时每种颜色被判成哪一类，完全由这张表
决定——**与画面内容无关**，所以判决分布可以脱离图片单独画出来，这正是本入口做的事。

两个版本对应 `ColorModel.classify` 的 `veto_shared` 开关：

- **noveto（对照口径）**：纯归一化似然 argmax；
- **veto（默认口径）**：argmax 判臂后，凡混合列计数 > 0 的颜色一律改判混合。

两版差别只可能出现在「argmax 判臂 **且** 混合列见过」的那批颜色上，本入口把它们
单独拎出来画成第三张差异图，并给出它们带走了多少臂像素。

### 三个口径必须分清（report 里逐个标注）

1. **色数口径**：一种颜色算一票，不管它出现过几次；
2. **像素量口径**：按该颜色在标定集里真实出现的像素数加权。单色像素数取
   `counts[:, MIX] + counts[:, ARM]`——混合列把每个背景/物体像素恰记一次、臂列把每个
   臂像素恰记一次，两者相加就是该颜色的真实出现次数（纯背景列与混合列是重叠计数，
   直接三列求和会把背景像素数重复计一遍）；
3. **判臂颜色的成分**：判成臂的那批颜色上，`counts[:, ARM]` 是标定集里真正的臂像素、
   `counts[:, MIX]` 是标定集里真正的非臂（背景∪物体）像素——后者就是「颜色阶段就已
   注定的误标上界」。veto 口径下这个数恰好为 0，这是「零物体误标」的根源。

产物（`--out` 目录，默认 `outputs/color_distribution/`）：

- `color_distribution_noveto.png` / `color_distribution_veto.png`：同版式两版分布大图；
- `veto_diff.png`：被否决翻转的那批颜色的色板、像素量条与似然平面位置；
- `stats.json`：上面全部数字，供 report 引用。

用法：

    uv run --no-sync python scripts/data-generation-v4.1/color_distribution.py \\
      --model scripts/data-generation-v4.1/outputs/color_model.npz \\
      --out scripts/data-generation-v4.1/outputs/color_distribution
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

# 与 compare_veto.py 同一套深色版式，出图风格保持一致
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


def decide(counts: np.ndarray, veto_shared: bool) -> np.ndarray:
    """颜色表 → 每种颜色的判决类别，与 `ColorModel.classify` 同一套算式。

    刻意不复用 `classify`（它吃的是图像、还要处理未见颜色），而是在表上直接算：
    每列除以本列像素总量得 `P(颜色|类)`，`argmax` 取胜者，列序使平手偏向非臂；
    `veto_shared` 打开时再把「判臂但混合列见过」的一律改判混合。
    `tests/lightweight/test_color_distribution.py` 用合成表逐位对拍两条路径。
    """
    totals = counts.sum(axis=0).astype(np.float64)
    if not np.all(totals > 0):
        raise ValueError(f"颜色表存在空列，无法归一化：各列总量 = {totals.tolist()}")
    winner = np.argmax(counts.astype(np.float64) / totals, axis=1)
    if veto_shared:
        winner[(winner == CLASS_ARM) & (counts[:, CLASS_MIX] > 0)] = CLASS_MIX
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


def _swatch_image(
    rgb: np.ndarray, order: np.ndarray, columns: int, rows: int
) -> np.ndarray:
    """把一批颜色铺成 `rows × columns` 的等面积马赛克，空位填背景色。"""
    canvas = np.full((rows, columns, 3), 0x18, dtype=np.uint8)
    canvas[:, :, 1] = 0x18
    canvas[:, :, 2] = 0x1C
    picked = rgb[order]
    take = min(picked.shape[0], rows * columns)
    flat = canvas.reshape(-1, 3)
    flat[:take] = picked[:take]
    return flat.reshape(rows, columns, 3)


def _weighted_bar(rgb: np.ndarray, weights: np.ndarray, width: int = 1400) -> np.ndarray:
    """按像素量加权的一维色带：每种颜色占的横向宽度 ∝ 它的像素数。"""
    bar = np.full((1, width, 3), 0x18, dtype=np.uint8)
    total = float(weights.sum())
    if total <= 0:
        return bar
    order = np.argsort(-weights)
    edges = np.concatenate([[0.0], np.cumsum(weights[order]) / total]) * width
    starts = np.floor(edges[:-1]).astype(int)
    ends = np.ceil(edges[1:]).astype(int)
    for index in range(order.size):
        low, high = starts[index], min(ends[index], width)
        if high > low:
            bar[0, low:high] = rgb[order[index]]
    return bar


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


def _likelihood_plane(
    axis: plt.Axes,
    counts: np.ndarray,
    rgb: np.ndarray,
    winner: np.ndarray,
    highlight: np.ndarray | None = None,
) -> None:
    """判决似然平面：x = log10 P(色|混合)，y = log10 P(色|臂)。

    混合列没见过的颜色 `P = 0`，log 取不到，统一放进左侧那条「从未在无臂场景出现」
    的专列（画在最小有限值再往左一格）。veto 口径的几何含义在这张图上一目了然——
    它把整个右半平面（专列以外）的臂色一次性清空。
    """
    totals = counts.sum(axis=0).astype(np.float64)
    p_mix = counts[:, CLASS_MIX] / totals[CLASS_MIX]
    p_arm = counts[:, CLASS_ARM] / totals[CLASS_ARM]
    seen_mix = p_mix > 0
    x = np.full(p_mix.shape, np.nan)
    x[seen_mix] = np.log10(p_mix[seen_mix])
    floor = float(np.nanmin(x)) - 1.2
    x[~seen_mix] = floor
    y = np.full(p_arm.shape, floor - 1.0)
    positive_arm = p_arm > 0
    y[positive_arm] = np.log10(p_arm[positive_arm])

    visible = positive_arm  # 臂列没见过的颜色不可能判臂，画出来只会糊成一片
    axis.scatter(
        x[visible],
        y[visible],
        c=rgb[visible] / 255.0,
        s=np.where(winner[visible] == CLASS_ARM, 22, 8),
        marker="o",
        linewidths=0.25,
        edgecolors="#9a9aa2",
        zorder=2,
    )
    if highlight is not None and highlight.any():
        axis.scatter(
            x[highlight],
            y[highlight],
            s=90,
            facecolors="none",
            edgecolors="#ff4d4d",
            linewidths=1.1,
            zorder=3,
            label=f"被否决翻转（{int(highlight.sum())} 色）",
        )
        axis.legend(
            facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=9, loc="lower right"
        )
    axis.axvline(floor + 0.6, color="#ff4d4d", linestyle="--", linewidth=1.0, zorder=1)
    axis.text(
        floor,
        axis.get_ylim()[1],
        "混合列\n从未见过",
        color="#ff8f8f",
        fontsize=8,
        ha="center",
        va="top",
    )
    limits = [min(floor, float(np.nanmin(y[visible]))), 0.0]
    axis.plot(limits, limits, color=GRID, linestyle=":", linewidth=1.0, zorder=1)
    axis.grid(color=GRID, linewidth=0.4, alpha=0.5)


def render_distribution(
    model: ColorModel,
    veto_shared: bool,
    stats: dict[str, Any],
    out_path: Path,
) -> Path:
    """出一版（veto 或 noveto）判决分布大图：3 行 × 3 列九个面板。"""
    rgb = unpack_rgb(model.colors)
    counts = model.counts
    winner = decide(counts, veto_shared)
    features = color_features(rgb)
    # 单色真实像素数 = 混合列 + 臂列（纯背景列与混合列重叠计数，不能三列直接相加）
    pixels = (counts[:, CLASS_MIX] + counts[:, CLASS_ARM]).astype(np.float64)

    figure = plt.figure(figsize=(19.5, 16.0), facecolor=BG)
    grid = figure.add_gridspec(
        3, 3, hspace=0.30, wspace=0.20, left=0.05, right=0.98, top=0.90, bottom=0.05
    )
    mode = "默认口径：混合支撑否决（veto）" if veto_shared else "对照口径：纯似然 argmax（noveto）"
    figure.suptitle(
        f"v4.1 颜色表判决分布 · {mode}\n"
        f"标定集 val ep0-9 · 唯一颜色 {model.colors.size} 种 · 判决只由颜色表决定，与画面内容无关",
        color=FG,
        fontsize=17,
        y=0.965,
    )

    # 行 1：三类各一张「饱和度 × 亮度」散点。这个平面对本链路最有分辨力——
    # 机械臂是低饱和的灰白壳体，任务物体大多带彩色，veto 的全部矛盾就在左上角
    # 那团「灰白」里（灰白臂壳 vs 灰白物体高光在 24 位 RGB 上完全同色）。
    for class_index in range(3):
        axis = figure.add_subplot(grid[0, class_index])
        selected = winner == class_index
        share = pixels[selected].sum() / max(pixels.sum(), 1.0)
        axis.scatter(
            features["sat"][selected],
            features["luma"][selected],
            c=rgb[selected] / 255.0,
            s=9,
            linewidths=0.2,
            edgecolors="#8a8a92",
        )
        _style(
            axis,
            f"{CLASS_LABELS[class_index]}：{int(selected.sum())} 色 · 像素占比 {share:.2%}",
            "饱和度 S",
            "亮度 luma" if class_index == 0 else "",
        )
        axis.set_xlim(-0.03, 1.03)
        axis.set_ylim(-0.03, 1.03)
        axis.grid(color=GRID, linewidth=0.4, alpha=0.5)

    # 行 2：三类的等面积色板——一种颜色一个小方块，按亮度排序。看的是「色数口径」的
    # 分布：哪一类占了颜色空间的哪一片。
    for class_index in range(3):
        axis = figure.add_subplot(grid[1, class_index])
        selected = np.flatnonzero(winner == class_index)
        order = selected[np.argsort(features["luma"][selected])]
        columns = int(np.ceil(np.sqrt(max(order.size, 1) * 1.6)))
        rows = int(np.ceil(max(order.size, 1) / columns))
        axis.imshow(
            _swatch_image(rgb, order, columns, rows), interpolation="nearest", aspect="auto"
        )
        axis.set_xticks([])
        axis.set_yticks([])
        _style(axis, f"{CLASS_LABELS[class_index]} 色板（等面积，按亮度排序）")

    # 行 3 左：像素量加权色带。与行 2 对照着看——色数口径与像素量口径能差出量级。
    axis = figure.add_subplot(grid[2, 0])
    bars = []
    for class_index in range(3):
        selected = winner == class_index
        bars.append(np.repeat(_weighted_bar(rgb[selected], pixels[selected]), 40, axis=0))
        bars.append(np.full((10, bars[-1].shape[1], 3), 0x18, dtype=np.uint8))
    axis.imshow(np.concatenate(bars[:-1], axis=0), interpolation="nearest", aspect="auto")
    axis.set_xticks([])
    axis.set_yticks([20, 70, 120])
    axis.set_yticklabels(CLASS_LABELS, fontsize=9)
    _style(axis, "像素量加权色带（每类内部宽度 ∝ 该色像素数）")

    # 行 3 中：亮度分布，实线 = 像素量口径、虚线 = 色数口径。两条线分岔的地方就是
    # 「颜色种类很多但像素很少」的长尾（抗锯齿边缘、阴影过渡色）。
    axis = figure.add_subplot(grid[2, 1])
    edges = np.linspace(0.0, 1.0, 61)
    centers = (edges[:-1] + edges[1:]) / 2
    for class_index in range(3):
        selected = winner == class_index
        by_pixel, _ = np.histogram(
            features["luma"][selected], bins=edges, weights=pixels[selected]
        )
        by_color, _ = np.histogram(features["luma"][selected], bins=edges)
        axis.plot(
            centers,
            by_pixel / max(by_pixel.sum(), 1.0),
            color=CLASS_ACCENT[class_index],
            linewidth=1.8,
            label=f"{CLASS_LABELS[class_index]}（像素量）",
        )
        axis.plot(
            centers,
            by_color / max(by_color.sum(), 1.0),
            color=CLASS_ACCENT[class_index],
            linewidth=1.1,
            linestyle="--",
            alpha=0.75,
            label=f"{CLASS_LABELS[class_index]}（色数）",
        )
    axis.legend(facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=8, ncol=1)
    axis.grid(color=GRID, linewidth=0.4, alpha=0.5)
    _style(axis, "亮度分布（各自归一化）", "亮度 luma", "占比")

    # 行 3 右：判决似然平面，veto 的几何含义全在这张图里
    axis = figure.add_subplot(grid[2, 2])
    highlight = None
    if veto_shared:
        highlight = np.asarray(stats["翻转掩码"])
    _likelihood_plane(axis, counts, rgb, winner, highlight)
    _style(
        axis,
        "判决似然平面（只画臂列见过的颜色）",
        "log10 P(色 | 混合)",
        "log10 P(色 | 臂)",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, dpi=110, facecolor=BG)
    plt.close(figure)
    return out_path


def render_diff(model: ColorModel, stats: dict[str, Any], out_path: Path) -> Path:
    """差异图：只画被混合支撑否决翻转的那批颜色（noveto 判臂 → veto 判混合）。"""
    rgb = unpack_rgb(model.colors)
    counts = model.counts
    flipped = np.asarray(stats["翻转掩码"])
    noveto = decide(counts, False)

    figure = plt.figure(figsize=(19.5, 6.4), facecolor=BG)
    grid = figure.add_gridspec(
        1, 3, wspace=0.18, left=0.04, right=0.98, top=0.80, bottom=0.10
    )
    figure.suptitle(
        f"混合支撑否决翻转的颜色：{int(flipped.sum())} 种 · 带走臂像素 "
        f"{stats['veto']['翻转带走的臂像素']:,} 个（占臂像素 "
        f"{stats['veto']['翻转带走的臂像素占比']:.4%}）\n"
        "它们是 argmax 判臂、但在「无臂场景（背景∪物体）」里出现过的颜色——无法排除属于物体，一律倒向保守",
        color=FG,
        fontsize=15,
        y=0.955,
    )

    order = np.flatnonzero(flipped)[np.argsort(-counts[flipped, CLASS_ARM])]
    axis = figure.add_subplot(grid[0, 0])
    columns = int(np.ceil(np.sqrt(max(order.size, 1) * 1.6)))
    rows = int(np.ceil(max(order.size, 1) / columns))
    axis.imshow(
        _swatch_image(rgb, order, columns, rows), interpolation="nearest", aspect="auto"
    )
    axis.set_xticks([])
    axis.set_yticks([])
    _style(axis, "翻转色色板（等面积，按臂像素量降序）")

    axis = figure.add_subplot(grid[0, 1])
    stacked = [
        np.repeat(_weighted_bar(rgb[flipped], counts[flipped, CLASS_ARM].astype(float)), 46, axis=0),
        np.full((12, 1400, 3), 0x18, dtype=np.uint8),
        np.repeat(_weighted_bar(rgb[flipped], counts[flipped, CLASS_MIX].astype(float)), 46, axis=0),
    ]
    axis.imshow(np.concatenate(stacked, axis=0), interpolation="nearest", aspect="auto")
    axis.set_xticks([])
    axis.set_yticks([23, 81])
    axis.set_yticklabels(["按臂像素量", "按混合像素量"], fontsize=9)
    _style(axis, "翻转色的像素量构成（宽度 ∝ 像素数）")

    axis = figure.add_subplot(grid[0, 2])
    _likelihood_plane(axis, counts, rgb, noveto, flipped)
    _style(
        axis,
        "翻转色在似然平面上的位置（底图 = noveto 判决）",
        "log10 P(色 | 混合)",
        "log10 P(色 | 臂)",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, dpi=110, facecolor=BG)
    plt.close(figure)
    return out_path


def compute_stats(model: ColorModel) -> dict[str, Any]:
    """两版判决的全部可引用数字，口径逐个写清楚。"""
    counts = model.counts
    pixels = (counts[:, CLASS_MIX] + counts[:, CLASS_ARM]).astype(np.int64)
    total_pixels = int(pixels.sum())
    noveto = decide(counts, False)
    veto = decide(counts, True)
    flipped = (noveto == CLASS_ARM) & (veto == CLASS_MIX)

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
        "noveto": side(noveto),
        "veto": side(veto),
        "翻转掩码": flipped,
    }
    stats["veto"]["翻转色数"] = int(flipped.sum())
    stats["veto"]["翻转带走的臂像素"] = int(counts[flipped, CLASS_ARM].sum())
    stats["veto"]["翻转带走的臂像素占比"] = round(
        float(counts[flipped, CLASS_ARM].sum()) / max(int(counts[:, CLASS_ARM].sum()), 1),
        6,
    )
    stats["veto"]["翻转带走的非臂像素"] = int(counts[flipped, CLASS_MIX].sum())

    # 翻转色明细：按带走的臂像素降序，供 report 直接列表。它们全是灰白系——
    # 灰白臂壳与灰白任务物体在 24 位 RGB 上完全同色，这是否决代价的全部来源。
    rgb = unpack_rgb(model.colors)
    order = np.flatnonzero(flipped)[np.argsort(-counts[flipped, CLASS_ARM])]
    stats["翻转色明细"] = [
        {
            "hex": "#{:02X}{:02X}{:02X}".format(*rgb[index]),
            "rgb": [int(value) for value in rgb[index]],
            "臂像素": int(counts[index, CLASS_ARM]),
            "混合像素": int(counts[index, CLASS_MIX]),
            "占全部臂像素": round(
                float(counts[index, CLASS_ARM]) / max(int(counts[:, CLASS_ARM].sum()), 1),
                6,
            ),
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
        default=str(SCRIPT_DIR / "outputs" / "color_distribution"),
        help="产物目录",
    )
    args = parser.parse_args(argv)

    setup_font()
    model = ColorModel.load(args.model)
    out_dir = Path(args.out)
    stats = compute_stats(model)

    written = [
        render_distribution(model, False, stats, out_dir / "color_distribution_noveto.png"),
        render_distribution(model, True, stats, out_dir / "color_distribution_veto.png"),
        render_diff(model, stats, out_dir / "veto_diff.png"),
    ]

    payload = {key: value for key, value in stats.items() if key != "翻转掩码"}
    payload["颜色表"] = args.model
    (out_dir / "stats.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for path in written:
        print(f"已写出 {path}")
    print(json.dumps(payload["veto"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
