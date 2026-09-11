"""跑前分布 2D 可视化（独立脚本，只读冻结规格 JSON，不 import ``tests._shared``）。

输出到 ``artifacts/injection/<run-id>/plots-2d/before/<任务>/<难度>/``，每组只有两张绝对坐标 xy 图：

* ``1_positions.png`` —— 该组 100 条规格的**全部物体**初始位置叠在同一个桌面坐标轴里（按钮、孔板、方块、
  格点、容器……全画在一起），矩形是真实尺寸与朝向，虚线框／虚线环是合法区；实心 = 实跑范围 ep0～29，
  半透明 = ep30～99。
* ``2_events.png``   —— 同一坐标范围，把该组**全部随机事件**画进桌面坐标：BinFill 的抓取箭头、RouteStick 的
  100 条路线、视频任务的三次交换箭头与抓取／目标标记。

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
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Patch, Rectangle  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLING_CONFIG = REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json"

GROUPS: list[tuple[str, str]] = [
    ("BinFill", "easy"), ("BinFill", "medium"), ("BinFill", "hard"),
    ("RouteStick", "easy"), ("RouteStick", "medium"), ("RouteStick", "hard"),
    ("VideoUnmaskSwap", "easy"), ("VideoUnmaskSwap", "medium"), ("VideoUnmaskSwap", "hard"),
    ("VideoRepick", "easy"), ("VideoRepick", "medium"),
]
FILES_PER_GROUP = 2
FEASIBILITY_EPISODES = 30  # 实跑范围 ep0～29
DPI = 150
FIGSIZE = (22, 22)  # 单轴大图，150 dpi → 3300 px，满足 min_long_edge_px ≥ 3000

# 几何常量（与 tests/_shared/injection_specs.py 一致，这里照抄数值不 import）
CUBE_HALF = 0.02
BIN_HALF = (CUBE_HALF * 2.5 + 0.005) * 0.5  # 0.0275
BOARD_SIDE, HOLE_SIDE = 0.1, 0.08
BUTTON_BASE_R = 0.025 * 1.5  # 底座半径（scale=1.5）

COLOR_HEX = {"red": "#d32f2f", "green": "#388e3c", "blue": "#1976d2"}
COLOR_CN = {"red": "红", "green": "绿", "blue": "蓝"}
SWAP_COLORS = ["#6a1b9a", "#ef6c00", "#00838f"]
BUTTON_COLOR, BOARD_COLOR, EMPTY_BIN_COLOR = "#455a64", "#795548", "#cfd8dc"


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
    ax.text(x_lo, y_hi, label, fontsize=11, color=color, va="bottom", ha="left", zorder=9,
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1.5))


def alpha_of(episode: int) -> float:
    return 0.85 if episode < FEASIBILITY_EPISODES else 0.22


def style_axes(ax, title: str, xlim, ylim) -> None:
    ax.set_title(title, fontsize=15)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.grid(alpha=0.2)
    ax.tick_params(labelsize=11)
    ax.set_xlabel("x / 米", fontsize=13)
    ax.set_ylabel("y / 米", fontsize=13)


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


def alpha_legend() -> list[Line2D]:
    return [Line2D([], [], marker="s", linestyle="", color="#37474f", alpha=0.85, markersize=12, label="实心 = 实跑范围 ep0～29"),
            Line2D([], [], marker="s", linestyle="", color="#37474f", alpha=0.22, markersize=12, label="半透明 = ep30～99")]


def draw_anchor_rings(ax, anchors_cfg: dict[str, Any], layout_types: list[str], n_obj: int, offset_limit: float) -> None:
    """视频任务：每种布局的每个锚点画十字、锚半径虚线圆、±偏移上限的点线圆。"""
    for lt in layout_types:
        for i in range(n_obj):
            anchor = anchors_cfg[lt][i]
            radius = math.hypot(*anchor)
            ax.add_patch(Circle((0, 0), radius, fill=False, linestyle="--", edgecolor="#455a64", linewidth=1.2, zorder=1))
            ax.add_patch(Circle((0, 0), max(radius - offset_limit, 0), fill=False, linestyle=":", edgecolor="#90a4ae", linewidth=1.0, zorder=1))
            ax.add_patch(Circle((0, 0), radius + offset_limit, fill=False, linestyle=":", edgecolor="#90a4ae", linewidth=1.0, zorder=1))
            ax.plot(anchor[0], anchor[1], "k+", markersize=16, markeredgewidth=2, zorder=7)
            ax.text(anchor[0], anchor[1] + 0.012, f"{lt} 锚点 {i}（r={radius:.3f}）", fontsize=10, ha="center", zorder=7)


def finish(fig, ax, title: str, handles: list, out: Path) -> None:
    ax.legend(handles=handles, loc="lower right", fontsize=12, framealpha=0.9)
    fig.suptitle(title, fontsize=18)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out, dpi=DPI)
    plt.close(fig)


# ── 图 1：全部物体的初始位置 ──────────────────────────────────────────────────
def plot_positions(task, difficulty, records, positions_cfg, out: Path) -> None:
    n = len(records)
    fig, ax = plt.subplots(figsize=FIGSIZE)
    xl, yl = episode_limits(task)
    if task == "BinFill":
        total_cubes = 0
        for episode, r in enumerate(records):
            a = alpha_of(episode)
            layout = r["layout"]
            # 按钮画在方块之上且只画轮廓，否则会被上千块方块整个盖住
            ax.add_patch(Circle(layout["button_xy"], BUTTON_BASE_R, fill=False, edgecolor=BUTTON_COLOR, linewidth=1.6, alpha=a, zorder=6))
            board = layout["board"]
            square(ax, board["xy"], BOARD_SIDE, board["yaw_deg"], fill=False, edgecolor=BOARD_COLOR, linewidth=1.2, alpha=a, zorder=2)
            square(ax, board["xy"], HOLE_SIDE, board["yaw_deg"], fill=False, edgecolor=BOARD_COLOR, linewidth=0.6, linestyle=":", alpha=a, zorder=2)
            for cube in layout["cubes"]:
                total_cubes += 1
                square(ax, cube["xy"], 2 * CUBE_HALF, math.degrees(cube["yaw_rad"]),
                       facecolor=COLOR_HEX[cube["color"]], edgecolor="none", alpha=a * 0.6, zorder=4)
        region_box(ax, -0.25, -0.15, -0.2, 0.2, "按钮中心合法区 x∈[-0.25,-0.15] y∈[-0.2,0.2]", BUTTON_COLOR)
        region_box(ax, -0.05, 0.15, -0.2, 0.2, "孔板中心合法区 x∈[-0.05,0.15] y∈[-0.2,0.2]，yaw∈[-20°,20°]", BOARD_COLOR)
        region_box(ax, -0.28, 0.08, -0.23, 0.23, "方块中心合法区 x∈[-0.28,0.08] y∈[-0.23,0.23]（已扣半边 0.02）", "#1b5e20")
        style_axes(ax, f"按钮 ×{n}（底座半径 {BUTTON_BASE_R:.4f} m）+ 孔板 ×{n}（边长 {BOARD_SIDE} m，内孔 {HOLE_SIDE} m）+ 方块 ×{total_cubes}（边长 0.04 m）", xl, yl)
        handles = [Patch(facecolor="none", edgecolor=BUTTON_COLOR, linewidth=1.6, label="按钮（圆轮廓 = 底座）"),
                   Patch(facecolor="none", edgecolor=BOARD_COLOR, label="孔板（实线外框 + 点线内孔）"),
                   *[Patch(facecolor=COLOR_HEX[c], label=f"{COLOR_CN[c]}方块") for c in ("red", "blue", "green")],
                   Line2D([], [], linestyle="--", color="#455a64", label="虚线框 = 合法区"), *alpha_legend()]
        title = f"图 1 · {task} / {difficulty} 全部物体的初始位置（跑前 {n} 条叠加，共 {2 * n + total_cubes} 个物体）"
    elif task == "RouteStick":
        for episode, r in enumerate(records):
            a = alpha_of(episode)
            for index, (x, y) in enumerate(routestick_points(r["layout"]["rotation_deg"])):
                if index % 2 == 0:
                    ax.plot(x, y, "o", color="#607d8b", markeredgecolor="#263238", markersize=9, alpha=a, zorder=3)
                else:
                    ax.plot(x, y, "^", color=r["layout"]["obstacle_rgb"][index // 2], markeredgecolor="#212121", markersize=10, alpha=a, zorder=3)
        for deg in (-30, 30):
            pts = routestick_points(deg)
            ax.plot([p[0] for p in pts], [p[1] for p in pts], "--", color="#455a64", linewidth=1.4, zorder=1)
        for index, (x, y) in enumerate(routestick_points(0.0)):
            ax.text(x + 0.03, y, f"格点 {index}（{'节点' if index % 2 == 0 else '障碍柱'}）", fontsize=11, color="#37474f", va="center")
        style_axes(ax, f"9 个格点 ×{n} 条 = {9 * n} 个格点（整排绕世界原点转 -30°～30°，两条虚线 = 旋转两端极限）", xl, yl)
        handles = [Line2D([], [], marker="o", linestyle="", color="#607d8b", markeredgecolor="#263238", markersize=10, label="节点（偶数索引，可踩）"),
                   Line2D([], [], marker="^", linestyle="", color="#9e9e9e", markeredgecolor="#212121", markersize=10, label="障碍柱（奇数索引，颜色 = 该条 obstacle_rgb）"),
                   Line2D([], [], linestyle="--", color="#455a64", label="rotation_deg = ±30° 的极限排"), *alpha_legend()]
        title = f"图 1 · {task} / {difficulty} 全部物体的初始位置（跑前 {n} 条叠加，共 {9 * n} 个格点）"
    else:
        is_unmask = task == "VideoUnmaskSwap"
        items_key = "bins" if is_unmask else "cubes"
        n_obj = len(records[0]["layout"][items_key])
        anchors_cfg = positions_cfg["containers"] if is_unmask else positions_cfg["easy_medium_cubes"]
        offset_limit = 0.07 - (BIN_HALF if is_unmask else CUBE_HALF)
        layout_types = sorted({r["layout"]["type"] for r in records})
        draw_anchor_rings(ax, anchors_cfg, layout_types, n_obj, offset_limit)
        for episode, r in enumerate(records):
            a = alpha_of(episode)
            if is_unmask:
                hidden_by_bin = {b: c for c, b in r["objects"]["hidden"].items()}
                for item in r["layout"]["bins"]:
                    face = COLOR_HEX.get(hidden_by_bin.get(item["object_id"]), EMPTY_BIN_COLOR)
                    square(ax, item["xy"], 2 * BIN_HALF, item["yaw_deg"], facecolor=face, edgecolor="#263238", linewidth=0.6, alpha=a * 0.6, zorder=3)
            else:
                ax.add_patch(Circle(r["layout"]["button_xy"], BUTTON_BASE_R, color=BUTTON_COLOR, alpha=a * 0.6, zorder=3))
                for item in r["layout"]["cubes"]:
                    is_target = item["object_id"] == r["objects"]["target"]
                    square(ax, item["xy"], 2 * CUBE_HALF, math.degrees(item["yaw_rad"]), facecolor=COLOR_HEX[r["objects"]["color"]],
                           edgecolor="black" if is_target else "none", linewidth=1.4, alpha=a * 0.6, zorder=4 if is_target else 3)
        if is_unmask:
            style_axes(ax, f"容器 ×{n_obj} × {n} 条 = {n_obj * n} 个（边长 {2 * BIN_HALF:.3f} m；锚点绕原点转 θ 后再偏移 ≤{offset_limit:.4f}，yaw 0～90°）", xl, yl)
            handles = [*[Patch(facecolor=COLOR_HEX[c], edgecolor="#263238", label=f"藏了{COLOR_CN[c]}方块的容器") for c in ("red", "green", "blue")],
                       Patch(facecolor=EMPTY_BIN_COLOR, edgecolor="#263238", label="空容器")]
            total = n_obj * n
        else:
            region_box(ax, -0.25, -0.15, -0.05, 0.05, "按钮中心合法区 x∈[-0.25,-0.15] y∈[-0.05,0.05]", BUTTON_COLOR)
            style_axes(ax, f"按钮 ×{n} + 方块 ×{n_obj} × {n} 条 = {n_obj * n} 块（边长 0.04 m；锚点绕原点转 θ 后再偏移 ≤{offset_limit:.4f}，yaw 0～2π）", xl, yl)
            handles = [Patch(facecolor=BUTTON_COLOR, label="按钮（圆 = 底座）"),
                       *[Patch(facecolor=COLOR_HEX[c], label=f"{COLOR_CN[c]}方块（该条三块同色）") for c in ("red", "blue", "green")],
                       Patch(facecolor="white", edgecolor="black", linewidth=1.4, label="黑边 = 目标方块")]
            total = n + n_obj * n
        handles += [Line2D([], [], marker="+", linestyle="--", color="#455a64", markersize=12, label="锚点十字 + 锚半径虚线圆"),
                    Line2D([], [], linestyle=":", color="#90a4ae", label=f"点线圆 = 锚半径 ±{offset_limit:.4f} 偏移上限"), *alpha_legend()]
        title = f"图 1 · {task} / {difficulty} 全部物体的初始位置（跑前 {n} 条叠加，共 {total} 个物体）"
    finish(fig, ax, title, handles, out)


# ── 图 2：全部随机事件画进桌面坐标 ─────────────────────────────────────────────
def plot_events(task, difficulty, records, sampling, out: Path) -> None:
    n = len(records)
    fig, ax = plt.subplots(figsize=FIGSIZE)
    xl, yl = episode_limits(task)
    if task == "BinFill":
        total_actions = 0
        for episode, r in enumerate(records):
            a = alpha_of(episode)
            board_xy = r["layout"]["board"]["xy"]
            cube_by_id = {c["object_id"]: c for c in r["layout"]["cubes"]}
            style = "-" if r["layout"]["dynamic"] else "--"
            for action in r["actions"]:
                total_actions += 1
                cube = cube_by_id[action["pick"]]
                ax.annotate("", xy=board_xy, xytext=cube["xy"],
                            arrowprops=dict(arrowstyle="-|>", color=COLOR_HEX[cube["color"]], lw=1.2, linestyle=style, alpha=a * 0.7), zorder=4)
            ax.plot(board_xy[0], board_xy[1], "s", color=BOARD_COLOR, markersize=6, alpha=a, zorder=5)
        style_axes(ax, f"抓取动作 ×{total_actions}：被抓方块 → 该条的孔板中心（箭头颜色 = 方块色；实线 = dynamic 分批出现，虚线 = 开局全在）", xl, yl)
        handles = [*[Line2D([], [], color=COLOR_HEX[c], label=f"抓{COLOR_CN[c]}方块") for c in ("red", "blue", "green")],
                   Line2D([], [], color="#37474f", linestyle="-", label="实线 = dynamic=True（方块分批出现）"),
                   Line2D([], [], color="#37474f", linestyle="--", label="虚线 = dynamic=False（开局全在）"),
                   Line2D([], [], marker="s", linestyle="", color=BOARD_COLOR, label="孔板中心"), *alpha_legend()]
        title = f"图 2 · {task} / {difficulty} 全部随机事件画进桌面坐标（跑前 {n} 条叠加，共 {total_actions} 个抓取动作）"
    elif task == "RouteStick":
        total_segments = 0
        for episode, r in enumerate(records):
            a = alpha_of(episode) * 0.7
            points = routestick_points(r["layout"]["rotation_deg"])
            # actions.nodes 存的是 9 格点里的索引（0/2/4/6/8），node_slots 是局部槽位（0～4），画图必须用前者
            nodes, directions = r["actions"]["nodes"], r["actions"]["directions"]
            path = [points[k] for k in nodes]
            total_segments += len(path) - 1
            for k in range(len(path) - 1):
                clockwise = directions[k] == "clockwise"
                # 顺时针实线、逆时针虚线；同一条边来回走时用相反弧度错开
                ax.annotate("", xy=path[k + 1], xytext=path[k],
                            arrowprops=dict(arrowstyle="-|>", color="#e65100", lw=1.4, alpha=a, linestyle="-" if clockwise else "--",
                                            connectionstyle=f"arc3,rad={0.35 if clockwise else -0.35}"), zorder=4)
            ax.plot(path[0][0], path[0][1], "*", color="#1b5e20", markersize=15, alpha=a, zorder=6)
            for index, (x, y) in enumerate(points):
                if index % 2 == 0:
                    ax.add_patch(Circle((x, y), 0.012, facecolor="#cfd8dc", edgecolor="#546e7a", alpha=a * 0.5, zorder=2))
                else:
                    ax.add_patch(Circle((x, y), 0.013, facecolor=r["layout"]["obstacle_rgb"][index // 2], edgecolor="#212121", alpha=a * 0.5, zorder=2))
        style_axes(ax, f"路线 ×{n} 条 = {total_segments} 段（不按 L 分面全部叠加；绿星 = 起点；实线弧 = 顺时针绕行，虚线弧 = 逆时针绕行）", xl, yl)
        handles = [Line2D([], [], marker="*", linestyle="", color="#1b5e20", markersize=15, label="起点 nodes[0]"),
                   Line2D([], [], color="#e65100", linestyle="-", label="实线弧 = clockwise 绕行"),
                   Line2D([], [], color="#e65100", linestyle="--", label="虚线弧 = counterclockwise 绕行"),
                   Line2D([], [], marker="o", linestyle="", color="#cfd8dc", markeredgecolor="#546e7a", markersize=10, label="节点"),
                   Line2D([], [], marker="o", linestyle="", color="#9e9e9e", markeredgecolor="#212121", markersize=10, label="障碍柱（颜色 = obstacle_rgb）"), *alpha_legend()]
        title = f"图 2 · {task} / {difficulty} 全部随机事件画进桌面坐标（跑前 {n} 条叠加，共 {total_segments} 段路线）"
    else:
        is_unmask = task == "VideoUnmaskSwap"
        items_key = "bins" if is_unmask else "cubes"
        total_swaps = 0
        for episode, r in enumerate(records):
            a = alpha_of(episode)
            positions = {item["object_id"]: item["xy"] for item in r["layout"][items_key]}
            for order, pair in enumerate(r["actions"]["swap_pairs"]):
                total_swaps += 1
                ax.annotate("", xy=positions[pair["partner"]], xytext=positions[pair["initiator"]],
                            arrowprops=dict(arrowstyle="-|>", color=SWAP_COLORS[order], lw=1.4, alpha=a * 0.7,
                                            connectionstyle="arc3,rad=0.12"), zorder=4)
            if is_unmask:
                for pick in r["objects"]["pick_order"]:
                    ax.plot(positions[pick][0], positions[pick][1], "o", markerfacecolor="none", markeredgecolor="black", markersize=10, alpha=a, zorder=5)
            else:
                tx, ty = positions[r["objects"]["target"]]
                ax.plot(tx, ty, "s", markerfacecolor="none", markeredgecolor="black", markersize=10, alpha=a, zorder=5)
                ax.plot(r["layout"]["button_xy"][0], r["layout"]["button_xy"][1], ".", color=BUTTON_COLOR, markersize=8, alpha=a, zorder=5)
        marker_note = "空心圆 = 视频后抓取的容器 pick_order" if is_unmask else "空心方 = 目标方块 target；灰点 = 按钮"
        style_axes(ax, f"交换动作 ×{total_swaps}：发起者 → 搭档（紫 = 第 1 次，橙 = 第 2 次，青 = 第 3 次；{marker_note}）", xl, yl)
        handles = [*[Line2D([], [], color=SWAP_COLORS[k], label=f"第 {k + 1} 次交换 initiator → partner") for k in range(3)]]
        if is_unmask:
            handles.append(Line2D([], [], marker="o", linestyle="", markerfacecolor="none", markeredgecolor="black", markersize=10, label="视频后抓取的容器（pick_order）"))
        else:
            handles += [Line2D([], [], marker="s", linestyle="", markerfacecolor="none", markeredgecolor="black", markersize=10, label="目标方块（target）"),
                        Line2D([], [], marker=".", linestyle="", color=BUTTON_COLOR, markersize=10, label="按钮中心")]
        handles += alpha_legend()
        title = f"图 2 · {task} / {difficulty} 全部随机事件画进桌面坐标（跑前 {n} 条叠加，共 {total_swaps} 次交换）"
    finish(fig, ax, title, handles, out)


# ── 入口 ────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="跑前分布 2D 可视化（只读规格 JSON，每组两张绝对坐标图）")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifacts-root", default=str(REPO_ROOT / "artifacts" / "injection"))
    parser.add_argument("--out-dir", default=None, help="默认 <artifacts-root>/<run-id>/plots-2d/before")
    args = parser.parse_args()

    root = Path(args.artifacts_root) / args.run_id
    out_root = Path(args.out_dir) if args.out_dir else root / "plots-2d" / "before"
    out_root.mkdir(parents=True, exist_ok=True)
    font = use_cjk_font()
    sampling = json.loads(SAMPLING_CONFIG.read_text(encoding="utf-8"))

    entries: list[dict[str, Any]] = []
    files: list[Path] = []
    for task, difficulty in GROUPS:
        path = root / "specs" / task / f"{difficulty}.json"
        records = sorted(json.loads(path.read_text(encoding="utf-8"))["episodes"], key=lambda item: item["episode"])
        target = out_root / task / difficulty
        target.mkdir(parents=True, exist_ok=True)
        group_files = [target / "1_positions.png", target / "2_events.png"]
        plot_positions(task, difficulty, records, sampling["positions"][task], group_files[0])
        plot_events(task, difficulty, records, sampling, group_files[1])
        files.extend(group_files)
        entries.append({
            "task": task, "difficulty": difficulty, "directory": str(target.relative_to(root)),
            "files": [f.name for f in group_files],
            "spec_sha256_head": [r["spec_sha256"] for r in records[:3]],
        })
        print(f"  出图 {task}/{difficulty}：{len(group_files)} 张", flush=True)

    sizes = {}
    try:
        from PIL import Image
        for f in files:
            with Image.open(f) as im:
                sizes[str(f.relative_to(root))] = list(im.size)
    except ImportError:
        pass
    payload = {"run_id": args.run_id, "phase": "before", "font": font, "dpi": DPI, "groups": entries, "sizes": sizes}
    (out_root / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    min_edge = min((max(s) for s in sizes.values()), default=0)
    ok = len(entries) == len(GROUPS) and len(files) == len(GROUPS) * FILES_PER_GROUP and (not sizes or min_edge >= 3000)
    print(f"PLOT2D_BEFORE={'PASS' if ok else 'FAIL'} groups={len(entries)} files={len(files)} min_long_edge_px={min_edge} font={font}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
