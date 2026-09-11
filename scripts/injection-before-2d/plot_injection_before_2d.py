"""跑前分布 2D 可视化（独立脚本，只读冻结规格 JSON，不 import ``tests._shared``）。

输出到 ``artifacts/injection/<run-id>/plots-2d/before/``，每组四类图：

* ``A_positions.png``  —— 100 条全部对象的初始位姿叠在桌面坐标系里，按对象角色分面，
  画合法区域框与真实尺寸的带朝向矩形；右侧附「连续量 × 粗箱」计数热图。
* ``B_events.png``     —— 把非位置的随机事件（抓取、路线、交换对……）画到同一 2D 空间，
  旁边一列面板给全部离散事件的计数。
* ``C_episodes_p1..p4.png`` —— 逐条记录卡，每页 5×5 共 25 条，每格俯视布局 + 文字列出该条
  episode 的全部随机事件。
* ``_mechanism.png``（全局一张）—— 用真实数据演示分层、配额铺设与合法候选平衡。

⚠ 本脚本不改任何既有代码、不写 ``plots/`` 与 ``plot_manifest_before.json``，
与在跑的 ``injection_campaign run`` 完全隔离。
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import textwrap
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLING_CONFIG = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json"

GROUPS: list[tuple[str, str]] = [
    ("BinFill", "easy"), ("BinFill", "medium"), ("BinFill", "hard"),
    ("RouteStick", "easy"), ("RouteStick", "medium"), ("RouteStick", "hard"),
    ("VideoUnmaskSwap", "easy"), ("VideoUnmaskSwap", "medium"), ("VideoUnmaskSwap", "hard"),
    ("VideoRepick", "easy"), ("VideoRepick", "medium"),
]
FEASIBILITY_EPISODES = 30  # 实跑范围 ep0～29
COARSE_BINS = 10
DPI = 150

# 几何常量（与 tests/_shared/injection_specs.py 一致，这里照抄数值不 import）
CUBE_HALF = 0.02
BIN_HALF = (CUBE_HALF * 2.5 + 0.005) * 0.5  # 0.0275
BOARD_SIDE, HOLE_SIDE = 0.1, 0.08
BUTTON_BASE_R = 0.025 * 1.5          # 底座半径（scale=1.5）
BUTTON_OBB_HALF = BUTTON_BASE_R * 1.5  # 避让盒半边 0.05625

COLOR_HEX = {"red": "#d32f2f", "green": "#388e3c", "blue": "#1976d2"}
SWAP_COLORS = ["#6a1b9a", "#ef6c00", "#00838f"]
BATCH_CMAP = plt.get_cmap("tab10")
REQUIRED_FIELDS = {
    # 与 tests/_shared/injection_categories.observed_values 覆盖的字段一致，记录卡必须全部写出
    "BinFill": {"dynamic", "colors_present", "initialize_color_order", "spawn_total", "put_in_total", "target_pool"},
    "RouteStick": {"L", "start_node", "direction", "edge"},
    "VideoUnmaskSwap": {"n_swaps", "n_picks", "layout_type", "selected", "color_order", "swap_pair"},
    "VideoRepick": {"n_swaps", "num_repeats", "layout_type", "color", "target", "swap_pair"},
}


# ── 通用 ────────────────────────────────────────────────────────────────────
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


def rotate(points: list[list[float]], theta: float) -> list[tuple[float, float]]:
    c, s = math.cos(theta), math.sin(theta)
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def square(ax, xy, side: float, angle_deg: float, **kw) -> None:
    ax.add_patch(Rectangle((xy[0] - side / 2, xy[1] - side / 2), side, side, angle=angle_deg,
                           rotation_point="center", **kw))


def region_box(ax, x_lo, x_hi, y_lo, y_hi, label: str, color="#455a64") -> None:
    ax.add_patch(Rectangle((x_lo, y_lo), x_hi - x_lo, y_hi - y_lo, fill=False, linestyle="--",
                           linewidth=1.2, edgecolor=color, zorder=1))
    ax.text(x_lo, y_hi, label, fontsize=8, color=color, va="bottom", ha="left")


def alpha_of(episode: int) -> float:
    return 0.85 if episode < FEASIBILITY_EPISODES else 0.22


def style_axes(ax, title: str, xlim, ylim) -> None:
    ax.set_title(title, fontsize=11)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.grid(alpha=0.2)
    ax.tick_params(labelsize=8)
    ax.set_xlabel("x / 米", fontsize=9)
    ax.set_ylabel("y / 米", fontsize=9)


def count_bars(ax, title: str, counter: Counter, legal: list[str] | None = None) -> None:
    """横向计数条：合法类别补零，条末标数字。"""
    keys = list(legal) if legal else []
    keys += [k for k in sorted(counter) if k not in keys]
    values = [counter.get(k, 0) for k in keys]
    y = range(len(keys))
    ax.barh(list(y), values, color="#5c9ccc")
    ax.set_yticks(list(y))
    ax.set_yticklabels([k if len(k) <= 30 else k[:27] + "…" for k in keys], fontsize=8)
    ax.invert_yaxis()
    for i, v in enumerate(values):
        ax.text(v + max(values + [1]) * 0.01, i, str(v), va="center", fontsize=8)
    spread = (max(values) - min(values)) if values else 0
    ax.set_title(f"{title}（{len(keys)} 类，计数差 {spread}）", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.set_xlim(0, max(values + [1]) * 1.18)


def stratum_heatmap(ax, records: list[dict[str, Any]], title="连续量 × 粗箱计数（目标每箱 10）") -> None:
    names = sorted(records[0].get("sampling_cells", {}))
    matrix = [[0] * COARSE_BINS for _ in names]
    for record in records:
        for r, name in enumerate(names):
            matrix[r][record["sampling_cells"][name][0]] += 1
    image = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=14, aspect="auto")
    for r in range(len(names)):
        for c in range(COARSE_BINS):
            ax.text(c, r, str(matrix[r][c]), ha="center", va="center", fontsize=8,
                    color="white" if matrix[r][c] > 9 else "black")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xticks(range(COARSE_BINS))
    ax.set_xlabel("粗箱编号", fontsize=9)
    ax.set_title(title, fontsize=10)
    plt.colorbar(image, ax=ax, fraction=0.03)


def fmt(v: float, nd=2) -> str:
    return f"{v:.{nd}f}"


def short_color(c: str) -> str:
    return {"red": "r", "green": "g", "blue": "b"}.get(c, c)


# ── 各任务的单条俯视图（A 面板与 C 记录卡共用）──────────────────────────────
def draw_binfill(ax, record, alpha=0.85, labels=True):
    layout = record["layout"]
    bx, by = layout["button_xy"]
    ax.add_patch(Circle((bx, by), BUTTON_BASE_R, color="#455a64", alpha=alpha, zorder=3))
    board = layout["board"]
    square(ax, board["xy"], BOARD_SIDE, board["yaw_deg"], fill=False, edgecolor="#795548", linewidth=1.4, alpha=alpha, zorder=2)
    square(ax, board["xy"], HOLE_SIDE, board["yaw_deg"], fill=False, edgecolor="#795548", linewidth=0.7, linestyle=":", alpha=alpha, zorder=2)
    picked = [a["pick"] for a in record["actions"]]
    for cube in layout["cubes"]:
        is_pick = cube["object_id"] in picked
        square(ax, cube["xy"], 2 * CUBE_HALF, math.degrees(cube["yaw_rad"]),
               facecolor=COLOR_HEX[cube["color"]], edgecolor="black" if is_pick else "none",
               linewidth=1.6, alpha=alpha, zorder=4)
        if labels and is_pick:
            ax.text(cube["xy"][0], cube["xy"][1], str(picked.index(cube["object_id"]) + 1),
                    fontsize=8, ha="center", va="center", color="white", zorder=6, fontweight="bold")


def routestick_points(rotation_deg: float) -> list[tuple[float, float]]:
    return rotate([[-0.1, (col - 4) * 0.07] for col in range(9)], math.radians(rotation_deg))


def draw_routestick(ax, record, alpha=0.85, labels=True):
    points = routestick_points(record["layout"]["rotation_deg"])
    for index, (x, y) in enumerate(points):
        if index % 2 == 0:
            ax.add_patch(Circle((x, y), 0.014, facecolor="#90a4ae", edgecolor="#37474f", alpha=alpha, zorder=3))
            if labels:
                ax.text(x, y, str(index), fontsize=8, ha="center", va="center", zorder=6)
        else:
            rgb = record["layout"]["obstacle_rgb"][index // 2]
            ax.add_patch(Circle((x, y), 0.015, facecolor=rgb, edgecolor="#212121", alpha=alpha, zorder=3))
    slots = record["actions"]["node_slots"]
    directions = record["actions"]["directions"]
    path = [points[s] for s in slots]
    for k in range(len(path) - 1):
        (x0, y0), (x1, y1) = path[k], path[k + 1]
        # 顺时针实线、逆时针虚线；同一条边来回走时用弧线错开
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="-|>", color="#e65100", lw=1.6, alpha=alpha,
                                    linestyle="-" if directions[k] == "clockwise" else "--",
                                    connectionstyle=f"arc3,rad={0.35 if directions[k] == 'clockwise' else -0.35}"),
                    zorder=5)
    ax.plot([path[0][0]], [path[0][1]], "*", color="#1b5e20", markersize=13, alpha=alpha, zorder=6)


def draw_video(ax, record, task: str, alpha=0.85, labels=True):
    layout, objects = record["layout"], record["objects"]
    is_unmask = task == "VideoUnmaskSwap"
    items = layout["bins"] if is_unmask else layout["cubes"]
    hidden_by_bin = {b: c for c, b in objects["hidden"].items()} if is_unmask else {}
    for index, item in enumerate(items):
        if is_unmask:
            color = hidden_by_bin.get(item["object_id"])
            face = COLOR_HEX.get(color, "#cfd8dc")
            square(ax, item["xy"], 2 * BIN_HALF, item["yaw_deg"], facecolor=face, edgecolor="#263238",
                   linewidth=1.0, alpha=alpha, zorder=3)
        else:
            is_target = item["object_id"] == objects["target"]
            square(ax, item["xy"], 2 * CUBE_HALF, math.degrees(item["yaw_rad"]), facecolor=COLOR_HEX[objects["color"]],
                   edgecolor="black" if is_target else "none", linewidth=2.0, alpha=alpha, zorder=3)
        if labels:
            ax.text(item["xy"][0], item["xy"][1], str(index), fontsize=9, ha="center", va="center",
                    color="white", fontweight="bold", zorder=6)
    positions = {item["object_id"]: item["xy"] for item in items}
    for order, pair in enumerate(record["actions"]["swap_pairs"]):
        a, b = positions[pair["initiator"]], positions[pair["partner"]]
        ax.annotate("", xy=b, xytext=a,
                    arrowprops=dict(arrowstyle="-|>", color=SWAP_COLORS[order], lw=1.8, alpha=alpha,
                                    connectionstyle=f"arc3,rad={0.15 * (order + 1)}"), zorder=5)
    if is_unmask:
        for pick in objects["pick_order"]:
            x, y = positions[pick]
            ax.add_patch(Circle((x, y), BIN_HALF * 1.45, fill=False, edgecolor="#000", linewidth=1.4, alpha=alpha, zorder=5))
    else:
        ax.add_patch(Circle(layout["button_xy"], BUTTON_BASE_R, color="#455a64", alpha=alpha, zorder=3))


def draw_episode(ax, task, record, alpha=0.85, labels=True):
    if task == "BinFill":
        draw_binfill(ax, record, alpha, labels)
    elif task == "RouteStick":
        draw_routestick(ax, record, alpha, labels)
    else:
        draw_video(ax, record, task, alpha, labels)


def episode_limits(task: str) -> tuple[tuple[float, float], tuple[float, float]]:
    if task == "BinFill":
        return (-0.36, 0.26), (-0.31, 0.31)
    if task == "RouteStick":
        return (-0.34, 0.16), (-0.36, 0.36)
    if task == "VideoRepick":
        return (-0.34, 0.26), (-0.3, 0.3)
    return (-0.26, 0.26), (-0.26, 0.26)


# ── 图 A：初始位置叠加 ──────────────────────────────────────────────────────
def plot_positions(task, difficulty, records, positions_cfg, out: Path) -> None:
    n = len(records)
    if task == "BinFill":
        fig = plt.figure(figsize=(26, 14))
        grid = fig.add_gridspec(2, 4, height_ratios=[1.6, 1])
        axes = [fig.add_subplot(grid[0, i]) for i in range(3)]
        for episode, r in enumerate(records):
            a = alpha_of(episode)
            bx, by = r["layout"]["button_xy"]
            axes[0].add_patch(Circle((bx, by), BUTTON_BASE_R, color="#455a64", alpha=a * 0.5, zorder=3))
            b = r["layout"]["board"]
            square(axes[1], b["xy"], BOARD_SIDE, b["yaw_deg"], fill=False, edgecolor="#795548", linewidth=1.0, alpha=a, zorder=3)
            for cube in r["layout"]["cubes"]:
                square(axes[2], cube["xy"], 2 * CUBE_HALF, math.degrees(cube["yaw_rad"]),
                       facecolor=COLOR_HEX[cube["color"]], edgecolor="none", alpha=a * 0.6, zorder=3)
        region_box(axes[0], -0.25, -0.15, -0.2, 0.2, "按钮中心合法区 x∈[-0.25,-0.15] y∈[-0.2,0.2]")
        region_box(axes[1], -0.05, 0.15, -0.2, 0.2, "孔板中心合法区 x∈[-0.05,0.15] y∈[-0.2,0.2]，yaw∈[-20°,20°]")
        region_box(axes[2], -0.28, 0.08, -0.23, 0.23, "方块中心合法区 x∈[-0.28,0.08] y∈[-0.23,0.23]（已扣半边 0.02）")
        xl, yl = episode_limits(task)
        style_axes(axes[0], f"按钮位置 ×{n}（底座半径 {BUTTON_BASE_R:.4f} m）", xl, yl)
        style_axes(axes[1], f"孔板位置与朝向 ×{n}（边长 {BOARD_SIDE} m，yaw 已画出）", xl, yl)
        total_cubes = sum(len(r["layout"]["cubes"]) for r in records)
        style_axes(axes[2], f"方块位置与朝向 ×{total_cubes} 块（边长 0.04 m，颜色=方块色）", xl, yl)
        ax_yaw = fig.add_subplot(grid[0, 3])
        ax_yaw.hist([r["layout"]["board"]["yaw_deg"] for r in records], bins=10, range=(-20, 20), color="#795548", alpha=0.8)
        ax_yaw.set_title("孔板 yaw 分箱（-20°～20°，目标每箱 10）", fontsize=10)
        ax_yaw.axhline(10, color="#c62828", linestyle="--")
        ax_yaw.tick_params(labelsize=8)
        ax_heat = fig.add_subplot(grid[1, 0:3])
        stratum_heatmap(ax_heat, records, "每 episode 的采样输入落在哪个粗箱（cube_* 只计第 0 块的首次尝试）")
        ax_note = fig.add_subplot(grid[1, 3])
        ax_note.axis("off")
        ax_note.text(0, 1, "读法\n· 实心 = 实跑范围 ep0～29，半透明 = ep30～99\n· 虚线框 = native_sampling.json 推出的合法区\n"
                     "· 方块面板画的是全部对象实际位置：第 0 块用分层采样点，\n  其余块粗箱轮转散开，被按钮/孔板压住时整域重抽，\n  所以只承诺「采样输入」每箱 10，不承诺实际位置均匀\n"
                     "· 热图每行一个连续量，10 个粗箱各 10 条即通过 COVERAGE_QUOTA",
                     fontsize=10, va="top")
    elif task == "RouteStick":
        fig = plt.figure(figsize=(26, 12))
        grid = fig.add_gridspec(1, 3, width_ratios=[1.6, 1, 1])
        ax = fig.add_subplot(grid[0, 0])
        for episode, r in enumerate(records):
            a = alpha_of(episode)
            for index, (x, y) in enumerate(routestick_points(r["layout"]["rotation_deg"])):
                if index % 2 == 0:
                    ax.plot(x, y, "o", color=BATCH_CMAP(index), markersize=7, alpha=a, zorder=3)
                else:
                    ax.plot(x, y, "^", color=BATCH_CMAP(index), markersize=7, alpha=a, zorder=3)
        for deg in (-30, 30):
            pts = routestick_points(deg)
            ax.plot([p[0] for p in pts], [p[1] for p in pts], "--", color="#455a64", linewidth=1)
        for index, (x, y) in enumerate(routestick_points(0.0)):
            ax.text(x + 0.02, y, f"索引 {index}", fontsize=8, color=BATCH_CMAP(index))
        style_axes(ax, f"9 个格点旋转后的实际位置 ×{n} 条（整排绕原点转 -30°～30°，虚线=两端极限；圆=按钮 三角=障碍柱）",
                   *episode_limits(task))
        ax_h = fig.add_subplot(grid[0, 1])
        ax_h.hist([r["layout"]["rotation_deg"] for r in records], bins=10, range=(-30, 30), color="#5c9ccc")
        ax_h.axhline(10, color="#c62828", linestyle="--")
        ax_h.set_title("rotation_deg 分箱（目标每箱 10）", fontsize=10)
        ax_h.set_xlabel("整排旋转角 / 度", fontsize=9)
        ax_heat = fig.add_subplot(grid[0, 2])
        stratum_heatmap(ax_heat, records)
    else:
        is_unmask = task == "VideoUnmaskSwap"
        items_key = "bins" if is_unmask else "cubes"
        n_obj = len(records[0]["layout"][items_key])
        cols = n_obj + (1 if not is_unmask else 0)
        fig = plt.figure(figsize=(6.5 * max(cols, 4) + 1, 15))
        grid = fig.add_gridspec(2, max(cols, 4), height_ratios=[1.5, 1])
        cfg = positions_cfg["containers"] if is_unmask else positions_cfg["easy_medium_cubes"]
        offset_limit = 0.07 - (BIN_HALF if is_unmask else CUBE_HALF)
        layout_types = sorted({r["layout"]["type"] for r in records})
        col = 0
        if not is_unmask:
            axb = fig.add_subplot(grid[0, 0])
            for episode, r in enumerate(records):
                bx, by = r["layout"]["button_xy"]
                axb.add_patch(Circle((bx, by), BUTTON_BASE_R, color="#455a64", alpha=alpha_of(episode) * 0.5, zorder=3))
            region_box(axb, -0.25, -0.15, -0.05, 0.05, "按钮中心合法区 x∈[-0.25,-0.15] y∈[-0.05,0.05]")
            style_axes(axb, f"按钮位置 ×{n}", *episode_limits(task))
            col = 1
        for i in range(n_obj):
            ax = fig.add_subplot(grid[0, col + i])
            for lt in layout_types:
                anchor = cfg[lt][i]
                radius = math.hypot(*anchor)
                ax.add_patch(Circle((0, 0), radius, fill=False, linestyle="--", edgecolor="#455a64", linewidth=1))
                ax.add_patch(Circle((0, 0), max(radius - offset_limit, 0), fill=False, linestyle=":", edgecolor="#90a4ae", linewidth=0.8))
                ax.add_patch(Circle((0, 0), radius + offset_limit, fill=False, linestyle=":", edgecolor="#90a4ae", linewidth=0.8))
                ax.plot(anchor[0], anchor[1], "k+", markersize=12)
                ax.text(anchor[0], anchor[1] + 0.012, f"{lt} 锚点 r={radius:.3f}", fontsize=8, ha="center")
            for episode, r in enumerate(records):
                item = r["layout"][items_key][i]
                a = alpha_of(episode)
                if is_unmask:
                    color = {b: c for c, b in r["objects"]["hidden"].items()}.get(item["object_id"])
                    square(ax, item["xy"], 2 * BIN_HALF, item["yaw_deg"], facecolor=COLOR_HEX.get(color, "#cfd8dc"),
                           edgecolor="#263238", linewidth=0.5, alpha=a * 0.6, zorder=3)
                else:
                    is_target = item["object_id"] == r["objects"]["target"]
                    square(ax, item["xy"], 2 * CUBE_HALF, math.degrees(item["yaw_rad"]), facecolor=COLOR_HEX[r["objects"]["color"]],
                           edgecolor="black" if is_target else "none", linewidth=1.2, alpha=a * 0.6, zorder=3)
            name = f"bin_{i}"
            style_axes(ax, f"{name} 初始位姿 ×{n}（锚点绕原点转 θ 后再偏移 ≤{offset_limit:.4f}；"
                           + ("填色=藏物颜色，灰=空" if is_unmask else "黑边=目标方块") + "）", *episode_limits(task))
        thetas = [r["layout"]["theta_rad"] for r in records]
        ax_t = fig.add_subplot(grid[1, 0])
        ax_t.hist(thetas, bins=10, range=(0, 180), color="#5c9ccc")
        ax_t.axhline(10, color="#c62828", linestyle="--")
        ax_t.set_title("theta_rad 原始值分箱（0～180 弧度，目标每箱 10）", fontsize=10)
        ax_t.set_xlabel("θ / 弧度（原单位就是弧度，不是度）", fontsize=9)
        ax_p = fig.add_subplot(grid[1, 1], projection="polar")
        mods = [t % (2 * math.pi) for t in thetas]
        counts, edges = [], [k * 2 * math.pi / 24 for k in range(25)]
        for k in range(24):
            counts.append(sum(1 for m in mods if edges[k] <= m < edges[k + 1]))
        ax_p.bar([(edges[k] + edges[k + 1]) / 2 for k in range(24)], counts, width=2 * math.pi / 24, color="#5c9ccc", edgecolor="white")
        ax_p.set_title("θ mod 2π 实际朝向玫瑰图（24 扇区）", fontsize=10)
        ax_heat = fig.add_subplot(grid[1, 2:])
        stratum_heatmap(ax_heat, records)
    fig.suptitle(f"图 A · {task} / {difficulty} 初始位置叠加（跑前，{n} 条冻结规格）", fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out, dpi=DPI)
    plt.close(fig)


# ── 图 B：随机事件 2D 图 ────────────────────────────────────────────────────
def js(v) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def plot_events(task, difficulty, records, sampling, out: Path) -> None:
    n = len(records)
    config = sampling["parameters"][task]["configs"][difficulty]
    if task == "BinFill":
        fig = plt.figure(figsize=(28, 16))
        grid = fig.add_gridspec(3, 4, width_ratios=[2.2, 1, 1, 1])
        ax = fig.add_subplot(grid[:, 0])
        for episode, r in enumerate(records):
            a = alpha_of(episode)
            board_xy = r["layout"]["board"]["xy"]
            cube_by_id = {c["object_id"]: c for c in r["layout"]["cubes"]}
            for action in r["actions"]:
                c = cube_by_id[action["pick"]]
                ax.annotate("", xy=board_xy, xytext=c["xy"],
                            arrowprops=dict(arrowstyle="-|>", color=COLOR_HEX[c["color"]], lw=1.0, alpha=a * 0.7,
                                            linestyle="-" if r["layout"]["dynamic"] else "--"), zorder=3)
            ax.plot(board_xy[0], board_xy[1], "s", color="#795548", markersize=5, alpha=a)
        total_actions = sum(len(r["actions"]) for r in records)
        style_axes(ax, f"抓取动作 ×{total_actions}：被抓方块位置 → 孔板中心（颜色=方块色；实线 dynamic=True，虚线 False；实心=ep0～29）",
                   *episode_limits(task))
        ax.legend(handles=[Line2D([], [], color="k", linestyle="-", label="dynamic=True 分批出现"),
                           Line2D([], [], color="k", linestyle="--", label="dynamic=False 开局全在")], fontsize=9, loc="lower right")
        panels = [
            ("dynamic", Counter(js(r["layout"]["dynamic"]) for r in records), ["true", "false"]),
            ("colors_present", Counter(js(r["objects"]["colors_present"]) for r in records), None),
            ("initialize_color_order（实际创建顺序）", Counter(js(r["objects"]["initialize_color_order"]) for r in records), None),
            ("spawn_total", Counter(str(r["objects"]["spawn_total"]) for r in records), [str(v) for v in range(config["spawn_cubes"][0], config["spawn_cubes"][1] + 1)]),
            ("put_in_total", Counter(str(r["objects"]["put_in_total"]) for r in records), [str(v) for v in range(config["put_in_numbers"][0], config["put_in_numbers"][1] + 1)]),
            ("target_pool（耦合，合法候选内平衡）", Counter(js(r["objects"]["target_pool"]) for r in records), None),
            ("spawn_count 每色块数（耦合）", Counter(f"{c}={k}" for r in records for c, k in r["objects"]["spawn_count"].items()), None),
            ("target_count 每色投入数（耦合，含 0）", Counter(f"{c}={k}" for r in records for c, k in r["objects"]["target_count"].items()), None),
            ("被抓方块的色内序号（约定 B7：取该色最前几块）", Counter(a["pick"].rsplit("_", 1)[0].split("_", 1)[1] + "_" + a["pick"].rsplit("_", 1)[1] for r in records for a in r["actions"]), None),
        ]
        for k, (title, counter, legal) in enumerate(panels):
            count_bars(fig.add_subplot(grid[k // 3, 1 + k % 3]), title, counter, legal)
    elif task == "RouteStick":
        lengths = sorted({r["objects"]["L"] for r in records})
        fig = plt.figure(figsize=(7 * max(len(lengths), 3) + 8, 15))
        grid = fig.add_gridspec(2, max(len(lengths), 3) + 1, width_ratios=[1.2] * max(len(lengths), 3) + [1.1])
        for k, L in enumerate(lengths):
            ax = fig.add_subplot(grid[0, k])
            subset = [(e, r) for e, r in enumerate(records) if r["objects"]["L"] == L]
            for episode, r in subset:
                draw_routestick(ax, r, alpha=alpha_of(episode) * 0.6, labels=False)
            style_axes(ax, f"L={L} 段的 {len(subset)} 条路线（实际坐标；★起点；实线=顺时针绕行，虚线=逆时针）", *episode_limits(task))
        nodes = [0, 2, 4, 6, 8]
        edges_legal = [f"{nodes[i]}→{nodes[j]}" for i in range(5) for j in (i - 1, i + 1) if 0 <= j < 5]
        panels = [
            ("起点 nodes[0]", Counter(str(r["actions"]["nodes"][0]) for r in records), [str(v) for v in nodes]),
            ("L 段数", Counter(str(r["objects"]["L"]) for r in records), [str(v) for v in range(config["length"][0], config["length"][1] + 1)]),
            ("绕行方向（每段一票）", Counter(d for r in records for d in r["actions"]["directions"]), ["clockwise", "counterclockwise"]),
            ("有向边使用频数（耦合，合法邻接内平衡）", Counter(f"{r['actions']['nodes'][i]}→{r['actions']['nodes'][i + 1]}" for r in records for i in range(len(r["actions"]["nodes"]) - 1)), edges_legal),
        ]
        for k, (title, counter, legal) in enumerate(panels[:3]):
            count_bars(fig.add_subplot(grid[1, k]), title, counter, legal)
        count_bars(fig.add_subplot(grid[0, -1]), *panels[3])
        ax_rgb = fig.add_subplot(grid[1, -1])
        ax_rgb.imshow([[tuple(c) for c in r["layout"]["obstacle_rgb"]] for r in records], aspect="auto", interpolation="nearest")
        ax_rgb.set_title("obstacle_rgb：100 条 × 4 根障碍柱的随机颜色（只影响观感）", fontsize=9)
        ax_rgb.set_xlabel("障碍柱索引 1/3/5/7", fontsize=9)
        ax_rgb.set_ylabel("episode", fontsize=9)
        ax_rgb.set_xticks(range(4))
        ax_rgb.set_xticklabels(["1", "3", "5", "7"])
    else:
        is_unmask = task == "VideoUnmaskSwap"
        items_key = "bins" if is_unmask else "cubes"
        fig = plt.figure(figsize=(30, 16))
        grid = fig.add_gridspec(3, 4, width_ratios=[2.4, 1, 1, 1])
        ax = fig.add_subplot(grid[:, 0])
        n_pairs = 0
        for episode, r in enumerate(records):
            a = alpha_of(episode)
            pos = {it["object_id"]: it["xy"] for it in r["layout"][items_key]}
            for order, pair in enumerate(r["actions"]["swap_pairs"]):
                n_pairs += 1
                ax.annotate("", xy=pos[pair["partner"]], xytext=pos[pair["initiator"]],
                            arrowprops=dict(arrowstyle="-|>", color=SWAP_COLORS[order], lw=1.2, alpha=a * 0.7,
                                            connectionstyle="arc3,rad=0.12"), zorder=3)
            if is_unmask:
                for pick in r["objects"]["pick_order"]:
                    ax.plot(pos[pick][0], pos[pick][1], "o", markerfacecolor="none", markeredgecolor="black", markersize=9, alpha=a)
            else:
                t = pos[r["objects"]["target"]]
                ax.plot(t[0], t[1], "s", markerfacecolor="none", markeredgecolor="black", markersize=9, alpha=a)
                ax.plot(r["layout"]["button_xy"][0], r["layout"]["button_xy"][1], ".", color="#455a64", alpha=a)
        style_axes(ax, f"交换动作 ×{n_pairs}：发起者 → 搭档（紫=第 1 次，橙=第 2 次，青=第 3 次；"
                       + ("◯=视频后抓取的容器" if is_unmask else "□=目标方块，·=按钮") + "；实心=ep0～29）", *episode_limits(task))
        ax.legend(handles=[Line2D([], [], color=SWAP_COLORS[i], lw=2, label=f"第 {i + 1} 次交换") for i in range(3)], fontsize=9, loc="lower right")
        names = [it["object_id"] for it in records[0]["layout"][items_key]]
        pair_legal = [f"{a}→{b}" for a in names for b in names if a != b]
        common = [
            ("n_swaps", Counter(str(r["objects"]["n_swaps"]) for r in records), [str(v) for v in range(config["swap_min"], config["swap_max"] + 1)]),
            ("layout_type", Counter(r["layout"]["type"] for r in records), ["region3_tri", "region3_line"] if len(names) == 3 else ["region4"]),
            ("交换对象对 initiator→partner（耦合：搭档=最近邻）", Counter(f"{p['initiator']}→{p['partner']}" for r in records for p in r["actions"]["swap_pairs"]), pair_legal),
            ("swap_initiators 完整 3 个发起者（含未执行段）", Counter(js(r["objects"]["swap_initiators"]) for r in records), None),
        ]
        if is_unmask:
            panels = common + [
                ("n_picks", Counter(str(r["objects"]["n_picks"]) for r in records), [str(v) for v in range(config["pick_min"], config["pick_max"] + 1)]),
                ("selected 藏物容器排序", Counter(js(r["objects"]["selected"]) for r in records), None),
                ("color_order 藏物颜色顺序", Counter(js(r["objects"]["color_order"]) for r in records), None),
                ("hidden 颜色→容器（耦合）", Counter(f"{c}→{b}" for r in records for c, b in r["objects"]["hidden"].items()), None),
                ("pick_order 抓取顺序（耦合）", Counter(js(r["objects"]["pick_order"]) for r in records), None),
            ]
        else:
            panels = common + [
                ("num_repeats 重复抓放次数", Counter(str(r["objects"]["num_repeats"]) for r in records), ["1", "2", "3"]),
                ("color 三块统一颜色", Counter(r["objects"]["color"] for r in records), ["red", "blue", "green"]),
                ("target 目标方块", Counter(r["objects"]["target"] for r in records), names),
                ("后续发起者顺序 tail（去掉目标后的排列）", Counter(js(r["objects"]["swap_initiators"][1:]) for r in records), None),
                ("collision.candidates_used 冻结用了第几个候选", Counter(str(r["collision"]["candidates_used"]) for r in records), None),
            ]
        for k, (title, counter, legal) in enumerate(panels[:9]):
            count_bars(fig.add_subplot(grid[k // 3, 1 + k % 3]), title, counter, legal)
    fig.suptitle(f"图 B · {task} / {difficulty} 随机事件 2D 图（跑前，{n} 条）", fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out, dpi=DPI)
    plt.close(fig)


# ── 图 C：逐条记录卡 ────────────────────────────────────────────────────────
def card_lines(task: str, r: dict[str, Any]) -> tuple[list[str], set[str]]:
    """返回记录卡文字行与其覆盖的随机事件字段集合（供断言不遗漏）。"""
    lay, obj, act = r["layout"], r["objects"], r["actions"]
    if task == "BinFill":
        lines = [
            f"dynamic={'T' if lay['dynamic'] else 'F'}  colors={js(obj['colors_present'])}  init_order={js(obj['initialize_color_order'])}",
            f"spawn_total={obj['spawn_total']} {js(obj['spawn_count'])}  put_in_total={obj['put_in_total']} pool={js(obj['target_pool'])} {js(obj['target_count'])}",
            "pick: " + ", ".join(a["pick"].replace("cube_", "") for a in act),
            f"button=({fmt(lay['button_xy'][0])},{fmt(lay['button_xy'][1])})  board=({fmt(lay['board']['xy'][0])},{fmt(lay['board']['xy'][1])},{lay['board']['yaw_deg']:.1f}°)",
            "cubes(生成序): " + " ".join(f"{c['object_id'].replace('cube_', '')}@({fmt(c['xy'][0])},{fmt(c['xy'][1])},{math.degrees(c['yaw_rad']):.0f}°)" for c in lay["cubes"]),
        ]
        return lines, {"dynamic", "colors_present", "initialize_color_order", "spawn_total", "put_in_total", "target_pool", "spawn_count", "target_count", "actions", "button_xy", "board", "cubes"}
    if task == "RouteStick":
        nodes = act["nodes"]
        lines = [
            f"L={obj['L']}  backtrack={'T' if obj['allow_backtracking'] else 'F'}  rotation={lay['rotation_deg']:.2f}°  start={nodes[0]}",
            "route: " + "→".join(str(v) for v in nodes),
            "dir: " + ", ".join("CW" if d == "clockwise" else "CCW" for d in act["directions"]),
            "obstacle_rgb: " + " ".join("#%02x%02x%02x" % tuple(int(v * 255) for v in c) for c in lay["obstacle_rgb"]),
        ]
        return lines, {"L", "start_node", "direction", "edge", "rotation_deg", "obstacle_rgb"}
    theta = lay["theta_rad"]
    swaps = ", ".join(f"{p['initiator'].replace('bin_', '')}→{p['partner'].replace('bin_', '')}({p['distance_m'] * 100:.1f}cm)" for p in act["swap_pairs"])
    if task == "VideoUnmaskSwap":
        lines = [
            f"layout={lay['type']}  θ={theta:.2f} rad (mod 2π={theta % (2 * math.pi):.2f})  n_swaps={obj['n_swaps']} n_picks={obj['n_picks']}",
            f"selected={js(obj['selected'])} color_order={js(obj['color_order'])}  hidden: " + " ".join(f"{short_color(c)}→{b.replace('bin_', '')}" for c, b in obj["hidden"].items()) + f"  empty={js(obj['empty'])}",
            f"swaps: {swaps}  initiators_full={js([s.replace('bin_', '') for s in obj['swap_initiators']])}",
            f"pick: {js(obj['pick_order'])}  g_min={r['collision']['min_g_m'] * 1000:+.1f}mm cand={r['collision']['candidates_used']}",
            "bins: " + " ".join(f"{b['object_id'].replace('bin_', '')}@({fmt(b['xy'][0])},{fmt(b['xy'][1])},{b['yaw_deg']:.0f}°)" for b in lay["bins"]),
        ]
        return lines, {"n_swaps", "n_picks", "layout_type", "selected", "color_order", "swap_pair", "hidden", "pick_order", "swap_initiators", "theta_rad", "bins", "collision"}
    lines = [
        f"layout={lay['type']}  θ={theta:.2f} rad (mod 2π={theta % (2 * math.pi):.2f})  button=({fmt(lay['button_xy'][0])},{fmt(lay['button_xy'][1])})",
        f"color={obj['color']} target={obj['target']} num_repeats={obj['num_repeats']} n_swaps={obj['n_swaps']}  initiators_full={js([s.replace('bin_', '') for s in obj['swap_initiators']])}",
        f"swaps: {swaps}  g_min={r['collision']['min_g_m'] * 1000:+.1f}mm cand={r['collision']['candidates_used']}",
        "cubes: " + " ".join(f"{c['object_id'].replace('bin_', '')}@({fmt(c['xy'][0])},{fmt(c['xy'][1])},{math.degrees(c['yaw_rad']):.0f}°)" for c in lay["cubes"]),
    ]
    return lines, {"n_swaps", "num_repeats", "layout_type", "color", "target", "swap_pair", "swap_initiators", "theta_rad", "button_xy", "cubes", "collision"}


def plot_cards(task, difficulty, records, out_dir: Path) -> list[Path]:
    outs = []
    xl, yl = episode_limits(task)
    for page in range(4):
        fig, axes = plt.subplots(5, 5, figsize=(27, 38))
        fig.subplots_adjust(hspace=0.9, wspace=0.12, top=0.955, bottom=0.015, left=0.02, right=0.98)
        for k in range(25):
            episode = page * 25 + k
            ax = axes[k // 5][k % 5]
            r = records[episode]
            draw_episode(ax, task, r, alpha=0.9, labels=True)
            ax.set_xlim(*xl)
            ax.set_ylim(*yl)
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            in_run = episode < FEASIBILITY_EPISODES
            ax.set_title(f"ep{episode}" + ("  [实跑]" if in_run else ""), fontsize=12,
                         fontweight="bold" if in_run else "normal", color="#1b5e20" if in_run else "#424242")
            for side in ax.spines.values():
                side.set_linewidth(2.0 if in_run else 0.8)
                side.set_color("#1b5e20" if in_run else "#9e9e9e")
            lines, used = card_lines(task, r)
            missing = REQUIRED_FIELDS[task] - used
            if missing:
                raise AssertionError(f"{task} 记录卡漏掉随机事件字段 {sorted(missing)}")
            # 按格宽手工折行（约 58 个等宽字符），续行缩进两格，避免溢出到相邻格
            wrapped = []
            for line in lines:
                wrapped.extend(textwrap.wrap(line, width=58, subsequent_indent="  ", break_long_words=True) or [""])
            ax.text(0.0, -0.03, "\n".join(wrapped), transform=ax.transAxes, va="top", ha="left", fontsize=8.2,
                    family="monospace")
        fig.suptitle(f"图 C · {task} / {difficulty} 逐条记录卡 第 {page + 1}/4 页（ep{page * 25}～ep{page * 25 + 24}；"
                     "绿框=实跑范围 ep0～29；每格下方列出该条全部随机事件）", fontsize=16)
        out = out_dir / f"C_episodes_p{page + 1}.png"
        fig.savefig(out, dpi=DPI)
        plt.close(fig)
        outs.append(out)
    return outs


# ── 图 D：采样机制图 ────────────────────────────────────────────────────────
def plot_mechanism(documents: dict[tuple[str, str], list[dict[str, Any]]], out: Path) -> None:
    easy = documents[("BinFill", "easy")]
    hard_route = documents[("RouteStick", "hard")]
    fig, axes = plt.subplots(2, 2, figsize=(24, 15))
    lo, hi = -0.25, -0.15
    ax = axes[0][0]
    for e, r in enumerate(easy):
        ax.plot(e, r["layout"]["button_xy"][0], "o", color=BATCH_CMAP(e // 10), markersize=7)
    for k in range(COARSE_BINS + 1):
        ax.axhline(lo + k * (hi - lo) / COARSE_BINS, color="#9e9e9e", linewidth=0.7)
    for b in range(1, COARSE_BINS):
        ax.axvline(b * 10 - 0.5, color="#bdbdbd", linewidth=0.7, linestyle="--")
    ax.set_title("① 连续量 10×10 分层：BinFill/easy 的 button_x（横=episode，颜色=批次；横线=10 个粗箱边界，竖虚线=批次边界）\n"
                 "每批 10 条落在 10 个不同粗箱 → 前 3 批 ep0～29 也均匀；全部 100 条每箱恰 10", fontsize=11)
    ax.set_xlabel("episode", fontsize=10)
    ax.set_ylabel("button_x / 米", fontsize=10)
    ax = axes[0][1]
    for e, r in enumerate(easy):
        ax.plot(r["layout"]["button_xy"][0], r["layout"]["button_xy"][1], "o", color=BATCH_CMAP(e // 10), markersize=7)
    for k in range(COARSE_BINS + 1):
        ax.axvline(lo + k * (hi - lo) / COARSE_BINS, color="#9e9e9e", linewidth=0.7)
        ax.axhline(-0.2 + k * 0.4 / COARSE_BINS, color="#9e9e9e", linewidth=0.7)
    ax.set_title("② 两个连续量各用独立排列：button_x × button_y 联合散点（格线=粗箱）\n不落在对角线上，每行每列都有 10 个点", fontsize=11)
    ax.set_xlabel("button_x / 米", fontsize=10)
    ax.set_ylabel("button_y / 米", fontsize=10)
    ax.set_aspect("equal")
    ax = axes[1][0]
    values = sorted({r["objects"]["spawn_total"] for r in easy})
    cmap = {v: BATCH_CMAP(i) for i, v in enumerate(values)}
    for e, r in enumerate(easy):
        v = r["objects"]["spawn_total"]
        ax.add_patch(Rectangle((e % 10, e // 10), 1, 1, facecolor=cmap[v], edgecolor="white"))
        ax.text(e % 10 + 0.5, e // 10 + 0.5, str(v), ha="center", va="center", fontsize=10, color="white", fontweight="bold")
    ax.set_xlim(0, 10)
    ax.set_ylim(10, 0)
    ax.set_xlabel("批内序号", fontsize=10)
    ax.set_ylabel("批次（每行 10 条）", fontsize=10)
    counts = Counter(r["objects"]["spawn_total"] for r in easy)
    per_batch = [Counter(r["objects"]["spawn_total"] for r in easy[b * 10:(b + 1) * 10]) for b in range(10)]
    ax.set_title("③ 独立离散量配额铺设：BinFill/easy 的 spawn_total（合法值 4/5/6）\n"
                 f"全局 {dict(sorted(counts.items()))}（计数差 ≤ 1 成立）；每批 4/5/6 实际计数：" + " ".join("[" + "/".join(str(pb.get(v, 0)) for v in values) + "]" for pb in per_batch)
                 + "\n⚠ quota_series 的各类别分批桶大小为 9～11 条不等，串接后批边界与 episode 错位，三类时每批只近似按比例（两类 50/50 才恰好每批 5/5）", fontsize=11)
    ax.set_aspect("equal")
    ax = axes[1][1]
    nodes = [0, 2, 4, 6, 8]
    edges_legal = [f"{nodes[i]}→{nodes[j]}" for i in range(5) for j in (i - 1, i + 1) if 0 <= j < 5]
    counter = Counter(f"{r['actions']['nodes'][i]}→{r['actions']['nodes'][i + 1]}" for r in hard_route for i in range(len(r["actions"]["nodes"]) - 1))
    count_bars(ax, "④ 耦合量合法候选平衡：RouteStick/hard 的有向边（每步只在当前合法邻接里挑用得最少的）", counter, edges_legal)
    fig.suptitle("图 D · 分布是怎么生成的（真实数据演示；随机流由 seed 20260909 + 任务/难度/字段标识经 SHA-256 派生，与进程无关）", fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out, dpi=DPI)
    plt.close(fig)


# ── 入口 ────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="跑前分布 2D 可视化（只读规格 JSON）")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifacts-root", default=str(REPO_ROOT / "artifacts" / "injection"))
    parser.add_argument("--out-dir", default=None, help="默认 <artifacts-root>/<run-id>/plots-2d/before")
    args = parser.parse_args()

    root = Path(args.artifacts_root) / args.run_id
    out_root = Path(args.out_dir) if args.out_dir else root / "plots-2d" / "before"
    out_root.mkdir(parents=True, exist_ok=True)
    font = use_cjk_font()
    sampling = json.loads(SAMPLING_CONFIG.read_text(encoding="utf-8"))

    documents: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for task, difficulty in GROUPS:
        path = root / "specs" / task / f"{difficulty}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        documents[(task, difficulty)] = sorted(doc["episodes"], key=lambda item: item["episode"])

    entries: list[dict[str, Any]] = []
    files: list[Path] = []
    for (task, difficulty), records in documents.items():
        target = out_root / task / difficulty
        target.mkdir(parents=True, exist_ok=True)
        a = target / "A_positions.png"
        b = target / "B_events.png"
        plot_positions(task, difficulty, records, sampling["positions"][task], a)
        plot_events(task, difficulty, records, sampling, b)
        cards = plot_cards(task, difficulty, records, target)
        group_files = [a, b, *cards]
        files.extend(group_files)
        entries.append({
            "task": task, "difficulty": difficulty, "directory": str(target.relative_to(root)),
            "files": [f.name for f in group_files],
            "spec_sha256_head": [r["spec_sha256"] for r in records[:3]],
        })
        print(f"  出图 {task}/{difficulty}：{len(group_files)} 张", flush=True)
    mech = out_root / "_mechanism.png"
    plot_mechanism(documents, mech)
    files.append(mech)

    sizes = {}
    try:
        from PIL import Image
        for f in files:
            with Image.open(f) as im:
                sizes[str(f.relative_to(root))] = list(im.size)
    except ImportError:
        pass
    payload = {"run_id": args.run_id, "phase": "before", "font": font, "dpi": DPI, "groups": entries,
               "mechanism": str(mech.relative_to(root)), "sizes": sizes}
    (out_root / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    min_edge = min((max(s) for s in sizes.values()), default=0)
    ok = len(entries) == len(GROUPS) and len(files) == len(GROUPS) * 6 + 1 and (not sizes or min_edge >= 3000)
    print(f"PLOT2D_BEFORE={'PASS' if ok else 'FAIL'} groups={len(entries)} files={len(files)} min_long_edge_px={min_edge} font={font}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
