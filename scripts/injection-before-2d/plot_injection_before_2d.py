"""跑前分布 2D 可视化（独立脚本，只读冻结规格 JSON，不 import ``tests._shared``）。

只画实跑范围 **前 30 条**（ep0～29）：100 条全叠在一起目视不可读，用户要求降到 30 条并拆面板。
产物放在本目录 ``figures/<任务>/<难度>/``（已 gitignore 不入库，文档链接指向本地文件），每组 7 张：

* ``1_positions.png`` —— 初始位置。第一面板把该组全部物体叠在同一个桌面坐标轴里，其余面板按物体种类拆开
  （按钮＋孔板／方块；格点；每个容器；按钮／每块方块），矩形是真实尺寸与朝向，虚线框／虚线环是合法区。
* ``2_events.png``   —— 随机事件画进桌面坐标。第一面板全部叠加，其余面板拆开：BinFill 按 dynamic 分两面，
  RouteStick 按起点分五面，视频任务按第 1／2／3 次交换分三面。
* ``3_episodes_p1..p5.png`` —— 单个 episode 的情况，每页 6 条（2 行 × 3 列），每格是该条的俯视布局
  （编号、朝向、箭头、目标标记），格下文字逐项列出这条 episode 的全部随机事件与位姿数值。

不画任何直方图、热图、玫瑰图或计数条——所有计数一律落到
``NEW_VALUE_DISTRIBUTION_BEFORE.md`` 第二节的「结果分布」列（由同目录 ``event_tables.py`` 生成）。

⚠ 本脚本不改任何既有代码、不写 ``plots/`` 与 ``plot_manifest_before.json``，
与在跑的 ``injection_campaign run`` 完全隔离。
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import textwrap
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Patch, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SAMPLING_CONFIG = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json"
FIGURES_DIR = HERE / "figures"

GROUPS: list[tuple[str, str]] = [
    ("BinFill", "easy"), ("BinFill", "medium"), ("BinFill", "hard"),
    ("RouteStick", "easy"), ("RouteStick", "medium"), ("RouteStick", "hard"),
    ("VideoUnmaskSwap", "easy"), ("VideoUnmaskSwap", "medium"), ("VideoUnmaskSwap", "hard"),
    ("VideoRepick", "easy"), ("VideoRepick", "medium"),
]
PLOT_EPISODES = 30       # 只画实跑范围 ep0～29
EPISODES_PER_PAGE = 6    # 单 episode 图每页 2 行 × 3 列
EPISODE_PAGES = PLOT_EPISODES // EPISODES_PER_PAGE
FILES_PER_GROUP = 2 + EPISODE_PAGES
DPI = 110
PANEL_IN = 11.0          # 每个面板的边长（英寸）
MIN_LONG_EDGE = 2000     # 每张图长边像素下限

# 几何常量（与 tests/_shared/injection_specs.py 一致，这里照抄数值不 import）
CUBE_HALF = 0.02
BIN_HALF = (CUBE_HALF * 2.5 + 0.005) * 0.5  # 0.0275
BOARD_SIDE, HOLE_SIDE = 0.1, 0.08
BUTTON_BASE_R = 0.025 * 1.5  # 底座半径（scale=1.5）

COLOR_HEX = {"red": "#d32f2f", "green": "#388e3c", "blue": "#1976d2"}
COLOR_CN = {"red": "红", "green": "绿", "blue": "蓝"}
SWAP_COLORS = ["#6a1b9a", "#ef6c00", "#00838f"]
BUTTON_COLOR, BOARD_COLOR, EMPTY_BIN_COLOR, ROUTE_COLOR = "#455a64", "#795548", "#cfd8dc", "#e65100"
ALPHA = 0.75


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
                           linewidth=1.4, edgecolor=color, zorder=1))
    ax.text(x_lo, y_hi, label, fontsize=10, color=color, va="bottom", ha="left", zorder=9,
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1.5))


def style_axes(ax, title: str, xlim, ylim) -> None:
    ax.set_title(title, fontsize=13)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.grid(alpha=0.2)
    ax.tick_params(labelsize=10)
    ax.set_xlabel("x / 米", fontsize=11)
    ax.set_ylabel("y / 米", fontsize=11)


def episode_limits(task: str) -> tuple[tuple[float, float], tuple[float, float]]:
    if task == "BinFill":
        return (-0.36, 0.26), (-0.31, 0.31)
    if task == "RouteStick":
        return (-0.34, 0.16), (-0.36, 0.36)
    if task == "VideoRepick":
        return (-0.34, 0.26), (-0.3, 0.3)
    return (-0.26, 0.26), (-0.26, 0.26)


def routestick_points(rotation_deg: float) -> list[tuple[float, float]]:
    return rotate([[-0.1, (col - 4) * 0.07] for col in range(9)], math.radians(rotation_deg))


def ep_text(ax, xy, episode: int, color="white", size=7) -> None:
    ax.text(xy[0], xy[1], str(episode), fontsize=size, ha="center", va="center", color=color, fontweight="bold", zorder=8)


def make_panels(n_panels: int, cols: int) -> tuple[Any, list]:
    rows = math.ceil(n_panels / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(PANEL_IN * cols, PANEL_IN * rows + 1.5 * rows), squeeze=False)
    flat = [ax for row in axes for ax in row]
    for ax in flat[n_panels:]:
        ax.axis("off")
    return fig, flat[:n_panels]


def finish(fig, title: str, handles: list, out: Path) -> None:
    fig.legend(handles=handles, loc="lower center", ncol=min(len(handles), 6), fontsize=11, framealpha=0.9)
    fig.suptitle(title, fontsize=17)
    fig.tight_layout(rect=[0, 0.05, 1, 0.965], h_pad=4.0, w_pad=2.0)
    fig.savefig(out, dpi=DPI)
    plt.close(fig)


def draw_anchor_rings(ax, anchors_cfg: dict[str, Any], layout_types: list[str], n_obj: int, offset_limit: float, label=True) -> None:
    """视频任务：每种布局的每个锚点画十字、锚半径虚线圆、±偏移上限的点线圆。"""
    for lt in layout_types:
        for i in range(n_obj):
            anchor = anchors_cfg[lt][i]
            radius = math.hypot(*anchor)
            ax.add_patch(Circle((0, 0), radius, fill=False, linestyle="--", edgecolor="#455a64", linewidth=1.0, zorder=1))
            ax.add_patch(Circle((0, 0), max(radius - offset_limit, 0), fill=False, linestyle=":", edgecolor="#90a4ae", linewidth=0.9, zorder=1))
            ax.add_patch(Circle((0, 0), radius + offset_limit, fill=False, linestyle=":", edgecolor="#90a4ae", linewidth=0.9, zorder=1))
            ax.plot(anchor[0], anchor[1], "k+", markersize=14, markeredgewidth=2, zorder=7)
            if label:
                ax.text(anchor[0], anchor[1] + 0.012, f"{lt} 锚点 {i}", fontsize=9, ha="center", zorder=7)


# ── 单条 episode 的俯视图（图 3 每格、图 1／图 2 的叠加共用）───────────────────
def draw_binfill(ax, r, labels=True, alpha=ALPHA):
    layout = r["layout"]
    ax.add_patch(Circle(layout["button_xy"], BUTTON_BASE_R, color=BUTTON_COLOR, alpha=alpha, zorder=3))
    board = layout["board"]
    square(ax, board["xy"], BOARD_SIDE, board["yaw_deg"], fill=False, edgecolor=BOARD_COLOR, linewidth=1.6, alpha=alpha, zorder=2)
    square(ax, board["xy"], HOLE_SIDE, board["yaw_deg"], fill=False, edgecolor=BOARD_COLOR, linewidth=0.8, linestyle=":", alpha=alpha, zorder=2)
    picked = [a["pick"] for a in r["actions"]]
    for cube in layout["cubes"]:
        is_pick = cube["object_id"] in picked
        square(ax, cube["xy"], 2 * CUBE_HALF, math.degrees(cube["yaw_rad"]), facecolor=COLOR_HEX[cube["color"]],
               edgecolor="black" if is_pick else "none", linewidth=1.8, alpha=alpha, zorder=4)
        if labels and is_pick:
            ep_text(ax, cube["xy"], picked.index(cube["object_id"]) + 1, size=9)


def draw_routestick(ax, r, labels=True, alpha=ALPHA):
    points = routestick_points(r["layout"]["rotation_deg"])
    for index, (x, y) in enumerate(points):
        if index % 2 == 0:
            ax.add_patch(Circle((x, y), 0.014, facecolor="#cfd8dc", edgecolor="#37474f", alpha=alpha, zorder=3))
            if labels:
                ax.text(x, y, str(index), fontsize=8, ha="center", va="center", zorder=6)
        else:
            ax.add_patch(Circle((x, y), 0.015, facecolor=r["layout"]["obstacle_rgb"][index // 2], edgecolor="#212121", alpha=alpha, zorder=3))
    # actions.nodes 存的是 9 格点里的索引（0/2/4/6/8），node_slots 是局部槽位（0～4），画图必须用前者
    path = [points[k] for k in r["actions"]["nodes"]]
    for k, direction in enumerate(r["actions"]["directions"]):
        clockwise = direction == "clockwise"
        # 顺时针实线、逆时针虚线；同一条边来回走时用相反弧度错开
        ax.annotate("", xy=path[k + 1], xytext=path[k],
                    arrowprops=dict(arrowstyle="-|>", color=ROUTE_COLOR, lw=1.6, alpha=alpha, linestyle="-" if clockwise else "--",
                                    connectionstyle=f"arc3,rad={0.35 if clockwise else -0.35}"), zorder=5)
    ax.plot(path[0][0], path[0][1], "*", color="#1b5e20", markersize=14, alpha=alpha, zorder=6)


def draw_video(ax, r, task: str, labels=True, alpha=ALPHA):
    layout, objects = r["layout"], r["objects"]
    is_unmask = task == "VideoUnmaskSwap"
    items = layout["bins"] if is_unmask else layout["cubes"]
    hidden_by_bin = {b: c for c, b in objects["hidden"].items()} if is_unmask else {}
    for index, item in enumerate(items):
        if is_unmask:
            face = COLOR_HEX.get(hidden_by_bin.get(item["object_id"]), EMPTY_BIN_COLOR)
            square(ax, item["xy"], 2 * BIN_HALF, item["yaw_deg"], facecolor=face, edgecolor="#263238", linewidth=1.0, alpha=alpha, zorder=3)
        else:
            is_target = item["object_id"] == objects["target"]
            square(ax, item["xy"], 2 * CUBE_HALF, math.degrees(item["yaw_rad"]), facecolor=COLOR_HEX[objects["color"]],
                   edgecolor="black" if is_target else "none", linewidth=2.0, alpha=alpha, zorder=3)
        if labels:
            ep_text(ax, item["xy"], index, size=9)
    positions = {item["object_id"]: item["xy"] for item in items}
    for order, pair in enumerate(r["actions"]["swap_pairs"]):
        ax.annotate("", xy=positions[pair["partner"]], xytext=positions[pair["initiator"]],
                    arrowprops=dict(arrowstyle="-|>", color=SWAP_COLORS[order], lw=1.8, alpha=alpha,
                                    connectionstyle=f"arc3,rad={0.15 * (order + 1)}"), zorder=5)
    if is_unmask:
        for pick in objects["pick_order"]:
            ax.add_patch(Circle(positions[pick], BIN_HALF * 1.45, fill=False, edgecolor="#000", linewidth=1.4, alpha=alpha, zorder=5))
    else:
        ax.add_patch(Circle(layout["button_xy"], BUTTON_BASE_R, color=BUTTON_COLOR, alpha=alpha, zorder=3))


def draw_episode(ax, task, r, labels=True, alpha=ALPHA):
    if task == "BinFill":
        draw_binfill(ax, r, labels, alpha)
    elif task == "RouteStick":
        draw_routestick(ax, r, labels, alpha)
    else:
        draw_video(ax, r, task, labels, alpha)


# ── 图 1：初始位置（全部叠加 + 按物体种类拆开）────────────────────────────────
def plot_positions(task, difficulty, records, positions_cfg, out: Path) -> None:
    n = len(records)
    xl, yl = episode_limits(task)
    base = f"图 1 · {task} / {difficulty} 初始位置（前 {n} 条 ep0～{n - 1}）"
    if task == "BinFill":
        fig, axes = make_panels(3, 3)
        total_cubes = sum(len(r["layout"]["cubes"]) for r in records)
        for episode, r in enumerate(records):
            layout, board = r["layout"], r["layout"]["board"]
            # 面板 0：全部叠加（按钮只画轮廓，免得被方块盖住）
            axes[0].add_patch(Circle(layout["button_xy"], BUTTON_BASE_R, fill=False, edgecolor=BUTTON_COLOR, linewidth=1.6, zorder=6))
            square(axes[0], board["xy"], BOARD_SIDE, board["yaw_deg"], fill=False, edgecolor=BOARD_COLOR, linewidth=1.2, alpha=ALPHA, zorder=2)
            for cube in layout["cubes"]:
                square(axes[0], cube["xy"], 2 * CUBE_HALF, math.degrees(cube["yaw_rad"]), facecolor=COLOR_HEX[cube["color"]], edgecolor="none", alpha=0.55, zorder=4)
            # 面板 1：按钮 + 孔板，标 ep 号
            axes[1].add_patch(Circle(layout["button_xy"], BUTTON_BASE_R, color=BUTTON_COLOR, alpha=0.45, zorder=3))
            ep_text(axes[1], layout["button_xy"], episode, size=9)
            square(axes[1], board["xy"], BOARD_SIDE, board["yaw_deg"], fill=False, edgecolor=BOARD_COLOR, linewidth=1.4, alpha=0.9, zorder=2)
            square(axes[1], board["xy"], HOLE_SIDE, board["yaw_deg"], fill=False, edgecolor=BOARD_COLOR, linewidth=0.7, linestyle=":", alpha=0.9, zorder=2)
            ep_text(axes[1], board["xy"], episode, color=BOARD_COLOR, size=9)
            # 面板 2：全部方块，黑细边
            for cube in layout["cubes"]:
                square(axes[2], cube["xy"], 2 * CUBE_HALF, math.degrees(cube["yaw_rad"]), facecolor=COLOR_HEX[cube["color"]], edgecolor="#212121", linewidth=0.4, alpha=0.6, zorder=4)
        for ax in axes:
            region_box(ax, -0.25, -0.15, -0.2, 0.2, "按钮中心合法区 x∈[-0.25,-0.15] y∈[-0.2,0.2]", BUTTON_COLOR)
            region_box(ax, -0.05, 0.15, -0.2, 0.2, "孔板中心合法区 x∈[-0.05,0.15] y∈[-0.2,0.2]，yaw∈[-20°,20°]", BOARD_COLOR)
            region_box(ax, -0.28, 0.08, -0.23, 0.23, "方块中心合法区 x∈[-0.28,0.08] y∈[-0.23,0.23]", "#1b5e20")
        style_axes(axes[0], f"① 全部物体叠加：按钮 ×{n} + 孔板 ×{n} + 方块 ×{total_cubes}", xl, yl)
        style_axes(axes[1], f"② 按钮 ×{n}（底座半径 {BUTTON_BASE_R:.4f} m）+ 孔板 ×{n}（边长 {BOARD_SIDE} m，内孔 {HOLE_SIDE} m），数字 = ep 号", xl, yl)
        style_axes(axes[2], f"③ 方块 ×{total_cubes}（边长 0.04 m，颜色 = 方块色，带朝向）", xl, yl)
        handles = [Patch(facecolor=BUTTON_COLOR, label="按钮"), Patch(facecolor="none", edgecolor=BOARD_COLOR, label="孔板（实线外框 + 点线内孔）"),
                   *[Patch(facecolor=COLOR_HEX[c], label=f"{COLOR_CN[c]}方块") for c in ("red", "blue", "green")],
                   Line2D([], [], linestyle="--", color="#455a64", label="虚线框 = 合法区")]
    elif task == "RouteStick":
        fig, axes = make_panels(2, 2)
        for episode, r in enumerate(records):
            points = routestick_points(r["layout"]["rotation_deg"])
            for index, (x, y) in enumerate(points):
                if index % 2 == 0:
                    axes[0].plot(x, y, "o", color="#607d8b", markeredgecolor="#263238", markersize=9, alpha=ALPHA, zorder=3)
                else:
                    axes[0].plot(x, y, "^", color=r["layout"]["obstacle_rgb"][index // 2], markeredgecolor="#212121", markersize=10, alpha=ALPHA, zorder=3)
            axes[1].plot([p[0] for p in points], [p[1] for p in points], "-", color="#607d8b", linewidth=1.0, alpha=0.7, zorder=2)
            axes[1].plot([p[0] for p in points[::2]], [p[1] for p in points[::2]], "o", color="#607d8b", markersize=4, zorder=3)
        # 30 根排的端点挤在一起，ep 号与转角改成面板内的分栏文字清单（按 ep 号排）
        listing = [f"ep{e:>2d}  {r['layout']['rotation_deg']:+6.1f}°" for e, r in enumerate(records)]
        for col, chunk in enumerate([listing[k:k + 15] for k in range(0, len(listing), 15)]):
            axes[1].text(0.66 + 0.17 * col, 0.98, "\n".join(chunk), transform=axes[1].transAxes, va="top", ha="left",
                         fontsize=10, family="monospace", bbox=dict(facecolor="white", alpha=0.9, edgecolor="#b0bec5"))
        for ax in axes:
            for deg in (-30, 30):
                pts = routestick_points(deg)
                ax.plot([p[0] for p in pts], [p[1] for p in pts], "--", color="#455a64", linewidth=1.4, zorder=1)
        for index, (x, y) in enumerate(routestick_points(0.0)):
            axes[0].text(x + 0.03, y, f"格点 {index}（{'节点' if index % 2 == 0 else '障碍柱'}）", fontsize=10, color="#37474f", va="center")
        style_axes(axes[0], f"① 9 个格点 × {n} 条 = {9 * n} 个（整排绕世界原点转 -30°～30°，虚线 = 两端极限）", xl, yl)
        style_axes(axes[1], f"② 每条 episode 一根排（节点小圆点），右侧清单 = 每条的 rotation_deg", xl, yl)
        handles = [Line2D([], [], marker="o", linestyle="", color="#607d8b", markeredgecolor="#263238", markersize=10, label="节点（偶数索引，可踩）"),
                   Line2D([], [], marker="^", linestyle="", color="#9e9e9e", markeredgecolor="#212121", markersize=10, label="障碍柱（奇数索引，颜色 = 该条 obstacle_rgb）"),
                   Line2D([], [], linestyle="--", color="#455a64", label="rotation_deg = ±30° 的极限排")]
    else:
        is_unmask = task == "VideoUnmaskSwap"
        items_key = "bins" if is_unmask else "cubes"
        n_obj = len(records[0]["layout"][items_key])
        anchors_cfg = positions_cfg["containers"] if is_unmask else positions_cfg["easy_medium_cubes"]
        offset_limit = 0.07 - (BIN_HALF if is_unmask else CUBE_HALF)
        layout_types = sorted({r["layout"]["type"] for r in records})
        n_panels = 1 + (0 if is_unmask else 1) + n_obj
        fig, axes = make_panels(n_panels, 3 if n_panels <= 6 else 4)
        obj_axes = axes[1 + (0 if is_unmask else 1):]
        for ax in [axes[0], *obj_axes]:
            draw_anchor_rings(ax, anchors_cfg, layout_types, n_obj, offset_limit, label=(ax is axes[0]))
        for episode, r in enumerate(records):
            hidden_by_bin = {b: c for c, b in r["objects"]["hidden"].items()} if is_unmask else {}
            for i, item in enumerate(r["layout"][items_key]):
                if is_unmask:
                    face, edge, lw = COLOR_HEX.get(hidden_by_bin.get(item["object_id"]), EMPTY_BIN_COLOR), "#263238", 0.6
                    side, ang = 2 * BIN_HALF, item["yaw_deg"]
                else:
                    is_target = item["object_id"] == r["objects"]["target"]
                    face, edge, lw = COLOR_HEX[r["objects"]["color"]], ("black" if is_target else "none"), 1.6
                    side, ang = 2 * CUBE_HALF, math.degrees(item["yaw_rad"])
                square(axes[0], item["xy"], side, ang, facecolor=face, edgecolor=edge, linewidth=lw, alpha=0.5, zorder=3)
                square(obj_axes[i], item["xy"], side, ang, facecolor=face, edgecolor=edge if edge != "none" else "#212121", linewidth=max(lw, 0.5), alpha=0.6, zorder=3)
                ep_text(obj_axes[i], item["xy"], episode, size=8)
            if not is_unmask:
                axes[0].add_patch(Circle(r["layout"]["button_xy"], BUTTON_BASE_R, fill=False, edgecolor=BUTTON_COLOR, linewidth=1.4, zorder=6))
                axes[1].add_patch(Circle(r["layout"]["button_xy"], BUTTON_BASE_R, color=BUTTON_COLOR, alpha=0.45, zorder=3))
                ep_text(axes[1], r["layout"]["button_xy"], episode, size=9)
        obj_name = "容器" if is_unmask else "方块"
        style_axes(axes[0], f"① 全部物体叠加：{obj_name} ×{n_obj} × {n} 条" + ("" if is_unmask else f" + 按钮 ×{n}"), xl, yl)
        if not is_unmask:
            region_box(axes[1], -0.25, -0.15, -0.05, 0.05, "按钮中心合法区 x∈[-0.25,-0.15] y∈[-0.05,0.05]", BUTTON_COLOR)
            style_axes(axes[1], f"② 按钮 ×{n}，数字 = ep 号", xl, yl)
        for i, ax in enumerate(obj_axes):
            k = i + (2 if is_unmask else 3)
            style_axes(ax, f"{'①②③④⑤⑥'[k - 1]} bin_{i} ×{n}（锚点绕原点转 θ 后再偏移 ≤{offset_limit:.4f}），数字 = ep 号", xl, yl)
        if is_unmask:
            handles = [*[Patch(facecolor=COLOR_HEX[c], edgecolor="#263238", label=f"藏了{COLOR_CN[c]}方块的容器") for c in ("red", "green", "blue")],
                       Patch(facecolor=EMPTY_BIN_COLOR, edgecolor="#263238", label="空容器")]
        else:
            handles = [Patch(facecolor=BUTTON_COLOR, label="按钮"),
                       *[Patch(facecolor=COLOR_HEX[c], label=f"{COLOR_CN[c]}方块（该条三块同色）") for c in ("red", "blue", "green")],
                       Patch(facecolor="white", edgecolor="black", linewidth=1.6, label="黑边 = 目标方块")]
        handles += [Line2D([], [], marker="+", linestyle="--", color="#455a64", markersize=12, label="锚点十字 + 锚半径虚线圆"),
                    Line2D([], [], linestyle=":", color="#90a4ae", label=f"点线圆 = 锚半径 ±{offset_limit:.4f} 偏移上限")]
    finish(fig, base, handles, out)


# ── 图 2：随机事件画进桌面坐标（全部叠加 + 拆开）──────────────────────────────
def plot_events(task, difficulty, records, sampling, out: Path) -> None:
    n = len(records)
    xl, yl = episode_limits(task)
    base = f"图 2 · {task} / {difficulty} 随机事件画进桌面坐标（前 {n} 条 ep0～{n - 1}）"
    if task == "BinFill":
        fig, axes = make_panels(3, 3)
        counts = [0, 0, 0]
        for episode, r in enumerate(records):
            board_xy = r["layout"]["board"]["xy"]
            cube_by_id = {c["object_id"]: c for c in r["layout"]["cubes"]}
            dyn = r["layout"]["dynamic"]
            targets = [axes[0], axes[1] if dyn else axes[2]]
            for action in r["actions"]:
                cube = cube_by_id[action["pick"]]
                for ax in targets:
                    ax.annotate("", xy=board_xy, xytext=cube["xy"],
                                arrowprops=dict(arrowstyle="-|>", color=COLOR_HEX[cube["color"]], lw=1.3, linestyle="-" if dyn else "--", alpha=ALPHA), zorder=4)
                counts[0] += 1
                counts[1 if dyn else 2] += 1
            for ax in targets:
                ax.plot(board_xy[0], board_xy[1], "s", color=BOARD_COLOR, markersize=6, zorder=5)
                ep_text(ax, (board_xy[0] + 0.012, board_xy[1] + 0.012), episode, color=BOARD_COLOR, size=8)
        style_axes(axes[0], f"① 全部抓取动作 ×{counts[0]}：被抓方块 → 该条的孔板中心（数字 = ep 号）", xl, yl)
        style_axes(axes[1], f"② 只看 dynamic=True（方块分批出现）的 episode：{counts[1]} 个动作", xl, yl)
        style_axes(axes[2], f"③ 只看 dynamic=False（开局全在）的 episode：{counts[2]} 个动作", xl, yl)
        handles = [*[Line2D([], [], color=COLOR_HEX[c], label=f"抓{COLOR_CN[c]}方块") for c in ("red", "blue", "green")],
                   Line2D([], [], color="#37474f", linestyle="-", label="实线 = dynamic=True"),
                   Line2D([], [], color="#37474f", linestyle="--", label="虚线 = dynamic=False"),
                   Line2D([], [], marker="s", linestyle="", color=BOARD_COLOR, label="孔板中心")]
    elif task == "RouteStick":
        starts = [0, 2, 4, 6, 8]
        fig, axes = make_panels(6, 3)
        seg_all, seg_by_start = 0, {s: 0 for s in starts}
        for episode, r in enumerate(records):
            start = r["actions"]["nodes"][0]
            segs = len(r["actions"]["directions"])
            seg_all += segs
            seg_by_start[start] += segs
            for ax in (axes[0], axes[1 + starts.index(start)]):
                draw_routestick(ax, r, labels=False, alpha=0.6)
                x0, y0 = routestick_points(r["layout"]["rotation_deg"])[start]
                ep_text(ax, (x0 - 0.02, y0), episode, color="#1b5e20", size=8)
        style_axes(axes[0], f"① 全部路线 ×{n} 条 = {seg_all} 段（绿星 = 起点，数字 = ep 号）", xl, yl)
        for k, s in enumerate(starts):
            style_axes(axes[1 + k], f"{'②③④⑤⑥'[k]} 只看起点 = 格点 {s} 的 episode：{seg_by_start[s]} 段", xl, yl)
        handles = [Line2D([], [], marker="*", linestyle="", color="#1b5e20", markersize=14, label="起点 nodes[0]"),
                   Line2D([], [], color=ROUTE_COLOR, linestyle="-", label="实线弧 = clockwise 绕行"),
                   Line2D([], [], color=ROUTE_COLOR, linestyle="--", label="虚线弧 = counterclockwise 绕行"),
                   Line2D([], [], marker="o", linestyle="", color="#cfd8dc", markeredgecolor="#37474f", markersize=10, label="节点"),
                   Line2D([], [], marker="o", linestyle="", color="#9e9e9e", markeredgecolor="#212121", markersize=10, label="障碍柱（颜色 = obstacle_rgb）")]
    else:
        is_unmask = task == "VideoUnmaskSwap"
        items_key = "bins" if is_unmask else "cubes"
        fig, axes = make_panels(4, 4)
        counts = [0, 0, 0, 0]
        for episode, r in enumerate(records):
            positions = {item["object_id"]: item["xy"] for item in r["layout"][items_key]}
            for order, pair in enumerate(r["actions"]["swap_pairs"]):
                counts[0] += 1
                counts[1 + order] += 1
                for ax in (axes[0], axes[1 + order]):
                    ax.annotate("", xy=positions[pair["partner"]], xytext=positions[pair["initiator"]],
                                arrowprops=dict(arrowstyle="-|>", color=SWAP_COLORS[order], lw=1.5, alpha=ALPHA, connectionstyle="arc3,rad=0.12"), zorder=4)
                    ix, iy = positions[pair["initiator"]]
                    ep_text(ax, (ix, iy), episode, color=SWAP_COLORS[order], size=8)
            for ax in axes:
                if is_unmask:
                    for pick in r["objects"]["pick_order"]:
                        ax.plot(positions[pick][0], positions[pick][1], "o", markerfacecolor="none", markeredgecolor="black", markersize=11, alpha=0.8, zorder=5)
                else:
                    tx, ty = positions[r["objects"]["target"]]
                    ax.plot(tx, ty, "s", markerfacecolor="none", markeredgecolor="black", markersize=11, alpha=0.8, zorder=5)
                    ax.plot(r["layout"]["button_xy"][0], r["layout"]["button_xy"][1], ".", color=BUTTON_COLOR, markersize=8, alpha=0.8, zorder=5)
        marker_note = "空心圆 = 视频后抓取的容器" if is_unmask else "空心方 = 目标方块，灰点 = 按钮"
        style_axes(axes[0], f"① 全部交换 ×{counts[0]}：发起者 → 搭档（数字 = ep 号，标在发起者处；{marker_note}）", xl, yl)
        for k in range(3):
            style_axes(axes[1 + k], f"{'②③④'[k]} 只看第 {k + 1} 次交换：{counts[1 + k]} 次" + ("（本组无第 3 次交换）" if k == 2 and counts[3] == 0 else ""), xl, yl)
        handles = [Line2D([], [], color=SWAP_COLORS[k], label=f"第 {k + 1} 次交换 initiator → partner") for k in range(3)]
        if is_unmask:
            handles.append(Line2D([], [], marker="o", linestyle="", markerfacecolor="none", markeredgecolor="black", markersize=10, label="视频后抓取的容器（pick_order）"))
        else:
            handles += [Line2D([], [], marker="s", linestyle="", markerfacecolor="none", markeredgecolor="black", markersize=10, label="目标方块（target）"),
                        Line2D([], [], marker=".", linestyle="", color=BUTTON_COLOR, markersize=10, label="按钮中心")]
    finish(fig, base, handles, out)


# ── 图 3：单个 episode 的情况 ────────────────────────────────────────────────
def fmt(v: float, nd=3) -> str:
    return f"{v:.{nd}f}"


def card_lines(task: str, r: dict[str, Any]) -> list[str]:
    """每格下方的文字：逐项列出这条 episode 的全部随机事件与位姿数值。"""
    lay, obj, act = r["layout"], r["objects"], r["actions"]
    if task == "BinFill":
        return [
            f"dynamic={lay['dynamic']}  场上颜色={'+'.join(obj['colors_present'])}  创建顺序={'-'.join(obj['initialize_color_order'])}",
            f"生成 {obj['spawn_total']} 块 {obj['spawn_count']}  投入 {obj['put_in_total']} 块 目标色={'+'.join(obj['target_pool'])} {obj['target_count']}",
            "抓取顺序: " + ", ".join(a["pick"].replace("cube_", "") for a in act),
            f"按钮=({fmt(lay['button_xy'][0])}, {fmt(lay['button_xy'][1])})  孔板=({fmt(lay['board']['xy'][0])}, {fmt(lay['board']['xy'][1])}, yaw {lay['board']['yaw_deg']:.1f}°)",
            "方块(生成序): " + " ".join(f"{c['object_id'].replace('cube_', '')}@({fmt(c['xy'][0])},{fmt(c['xy'][1])},{math.degrees(c['yaw_rad']):.0f}°)" for c in lay["cubes"]),
        ]
    if task == "RouteStick":
        nodes = act["nodes"]
        return [
            f"L={obj['L']} 段  允许回退={obj['allow_backtracking']}  rotation_deg={lay['rotation_deg']:.2f}°  起点=格点 {nodes[0]}",
            "路线: " + " → ".join(str(v) for v in nodes),
            "每段绕行: " + ", ".join("顺时针" if d == "clockwise" else "逆时针" for d in act["directions"]),
            "障碍柱 RGB: " + " ".join("#%02x%02x%02x" % tuple(int(v * 255) for v in c) for c in lay["obstacle_rgb"]),
        ]
    theta = lay["theta_rad"]
    swaps = ", ".join(f"{p['initiator'].replace('bin_', '')}→{p['partner'].replace('bin_', '')} ({p['distance_m'] * 100:.1f} cm)" for p in act["swap_pairs"])
    col = r["collision"]
    if task == "VideoUnmaskSwap":
        return [
            f"布局={lay['type']}  θ={theta:.2f} rad（mod 2π = {theta % (2 * math.pi):.2f}）  n_swaps={obj['n_swaps']}  n_picks={obj['n_picks']}",
            f"selected={obj['selected']}  color_order={'-'.join(obj['color_order'])}  藏物: " + " ".join(f"{COLOR_CN[c]}→{b.replace('bin_', '')}" for c, b in obj["hidden"].items()) + f"  空={obj['empty'] or '无'}",
            f"交换: {swaps}  完整发起者={[s.replace('bin_', '') for s in obj['swap_initiators']]}",
            f"视频后抓取={obj['pick_order']}  最小间隙={col['min_g_m'] * 1000:+.1f} mm  用到候选 #{col['candidates_used']}",
            "容器: " + " ".join(f"{b['object_id'].replace('bin_', '')}@({fmt(b['xy'][0])},{fmt(b['xy'][1])},{b['yaw_deg']:.0f}°)" for b in lay["bins"]),
        ]
    return [
        f"布局={lay['type']}  θ={theta:.2f} rad（mod 2π = {theta % (2 * math.pi):.2f}）  按钮=({fmt(lay['button_xy'][0])}, {fmt(lay['button_xy'][1])})",
        f"颜色={obj['color']}  目标={obj['target']}  num_repeats={obj['num_repeats']}  n_swaps={obj['n_swaps']}  完整发起者={[s.replace('bin_', '') for s in obj['swap_initiators']]}",
        f"交换: {swaps}  最小间隙={col['min_g_m'] * 1000:+.1f} mm  用到候选 #{col['candidates_used']}",
        "方块: " + " ".join(f"{c['object_id'].replace('bin_', '')}@({fmt(c['xy'][0])},{fmt(c['xy'][1])},{math.degrees(c['yaw_rad']):.0f}°)" for c in lay["cubes"]),
    ]


def plot_episode_pages(task, difficulty, records, out_dir: Path) -> list[Path]:
    outs = []
    xl, yl = episode_limits(task)
    for page in range(EPISODE_PAGES):
        fig, axes = plt.subplots(2, 3, figsize=(3 * PANEL_IN, 2 * PANEL_IN + 7))
        fig.subplots_adjust(hspace=0.5, wspace=0.12, top=0.95, bottom=0.14, left=0.03, right=0.98)
        for k in range(EPISODES_PER_PAGE):
            episode = page * EPISODES_PER_PAGE + k
            ax = axes[k // 3][k % 3]
            r = records[episode]
            draw_episode(ax, task, r, labels=True, alpha=0.9)
            ax.set_xlim(*xl)
            ax.set_ylim(*yl)
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(f"ep{episode}", fontsize=15, fontweight="bold", color="#1b5e20")
            # 按格宽手工折行（约 70 个等宽字符），续行缩进两格，避免溢出到相邻格
            wrapped = []
            for line in card_lines(task, r):
                wrapped.extend(textwrap.wrap(line, width=70, subsequent_indent="  ", break_long_words=True) or [""])
            # 不用 monospace：等宽字体没有中文字形会显示成方框，走 rcParams 里的 CJK sans
            ax.text(0.0, -0.02, "\n".join(wrapped), transform=ax.transAxes, va="top", ha="left", fontsize=11, linespacing=1.4)
        first, last = page * EPISODES_PER_PAGE, page * EPISODES_PER_PAGE + EPISODES_PER_PAGE - 1
        fig.suptitle(f"图 3 · {task} / {difficulty} 单个 episode 的情况 第 {page + 1}/{EPISODE_PAGES} 页（ep{first}～ep{last}；"
                     "格下文字 = 该条全部随机事件与位姿；黑边方块 = 被抓／目标，箭头 = 动作）", fontsize=16)
        out = out_dir / f"3_episodes_p{page + 1}.png"
        fig.savefig(out, dpi=DPI)
        plt.close(fig)
        outs.append(out)
    return outs


# ── 入口 ────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="跑前分布 2D 可视化（只读规格 JSON，只画前 30 条，产物放本目录 figures/）")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifacts-root", default=str(REPO_ROOT / "artifacts" / "injection"))
    parser.add_argument("--out-dir", default=str(FIGURES_DIR))
    args = parser.parse_args()

    root = Path(args.artifacts_root) / args.run_id
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    font = use_cjk_font()
    sampling = json.loads(SAMPLING_CONFIG.read_text(encoding="utf-8"))

    entries: list[dict[str, Any]] = []
    files: list[Path] = []
    for task, difficulty in GROUPS:
        path = root / "specs" / task / f"{difficulty}.json"
        records = sorted(json.loads(path.read_text(encoding="utf-8"))["episodes"], key=lambda item: item["episode"])[:PLOT_EPISODES]
        target = out_root / task / difficulty
        target.mkdir(parents=True, exist_ok=True)
        group_files = [target / "1_positions.png", target / "2_events.png"]
        plot_positions(task, difficulty, records, sampling["positions"][task], group_files[0])
        plot_events(task, difficulty, records, sampling, group_files[1])
        group_files += plot_episode_pages(task, difficulty, records, target)
        files.extend(group_files)
        entries.append({
            "task": task, "difficulty": difficulty, "directory": str(target.relative_to(out_root)),
            "files": [f.name for f in group_files],
            "spec_sha256_head": [r["spec_sha256"] for r in records[:3]],
        })
        print(f"  出图 {task}/{difficulty}：{len(group_files)} 张", flush=True)

    sizes = {}
    try:
        from PIL import Image
        for f in files:
            with Image.open(f) as im:
                sizes[str(f.relative_to(out_root))] = list(im.size)
    except ImportError:
        pass
    payload = {"run_id": args.run_id, "phase": "before", "episodes": PLOT_EPISODES, "font": font, "dpi": DPI,
               "groups": entries, "sizes": sizes}
    (out_root / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    min_edge = min((max(s) for s in sizes.values()), default=0)
    ok = len(entries) == len(GROUPS) and len(files) == len(GROUPS) * FILES_PER_GROUP and (not sizes or min_edge >= MIN_LONG_EDGE)
    print(f"PLOT2D_BEFORE={'PASS' if ok else 'FAIL'} groups={len(entries)} files={len(files)} episodes={PLOT_EPISODES} min_long_edge_px={min_edge} font={font}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
