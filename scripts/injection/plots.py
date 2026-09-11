"""跑前／跑后三类图（NEW_VALUE_INJECTION_TEST_PLAN 第 4.4 节）。

每组三张，版式跑前跑后相同：

* **图 1 布局总览**：10×10 小图，每条 episode 一个俯视布局；跑后按七类结果给小图着色，
  实跑范围外的 70 格保留细边框并标「范围外」。
* **图 2 空间覆盖**：XY 散点 + 10×10 占用格 + 每维分箱计数；跑后同版式叠失败标记。
* **图 3 对象与动作分布**：横向条形 + 频数；跑后同一条形按结果分色堆叠。

⚠ 出图只用于目视复核，**验收看计数表**（``check`` 打的判定行）。图与计数表引用同一份
规格散列，``plot_manifest.json`` 里逐张登记。
"""

from __future__ import annotations

import glob
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402

from .categories import legal_categories, observed_values  # noqa: E402
from .contract import Contract  # noqa: E402
from .sampling import COARSE_BINS, GROUP_SIZE  # noqa: E402

#: 实跑范围：每组 episode 0～29。范围外的格子在跑后图里标「范围外」，不进分母。
FEASIBILITY_EPISODES = 30

#: 七类最终状态的着色，与第 4.4 节草图的图例一致。
RESULT_COLORS = {
    "通过": "#2e7d32",
    "规格拒绝": "#6a1b9a",
    "碰撞拒绝": "#c62828",
    "实际对象/动作不符": "#ef6c00",
    "规划失败": "#1565c0",
    "超时": "#00838f",
    "未运行": "#9e9e9e",
}
CUBE_COLORS = {"red": "#d32f2f", "green": "#388e3c", "blue": "#1976d2"}


def _use_cjk_font() -> str | None:
    """把系统里的 CJK 字体注册给 matplotlib，否则中文标签会渲染成豆腐块。

    ⚠ ``.ttc`` 是字体集合，matplotlib 默认不扫描，必须显式 ``addfont``；注册进来的
    face 名字可能是 ``Noto Sans CJK JP``，但 CJK 字体的汉字字形是共用的，简体照常渲染。
    """
    candidates = sorted(set(glob.glob("/usr/share/fonts/**/*CJK*.tt?", recursive=True)))
    candidates += sorted(set(glob.glob("/usr/share/fonts/**/DroidSansFallback*.ttf", recursive=True)))
    for path in candidates:
        try:
            font_manager.fontManager.addfont(path)
        except Exception:  # noqa: BLE001 - 字体损坏时跳过，图仍然出得来
            continue
    for name in ("Noto Sans CJK SC", "Noto Sans CJK JP", "Droid Sans Fallback", "Noto Serif CJK JP"):
        if any(item.name == name for item in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return name
    return None


# ── 图 1：布局总览 ──────────────────────────────────────────────────────────
def _draw_binfill(ax, record: dict[str, Any]) -> None:
    layout = record["layout"]
    ax.add_patch(Circle(layout["button_xy"], 0.02, color="#455a64", zorder=3))
    board = layout["board"]
    ax.add_patch(
        Rectangle(
            (board["xy"][0] - 0.05, board["xy"][1] - 0.05), 0.1, 0.1,
            angle=board["yaw_deg"], rotation_point="center",
            fill=False, edgecolor="#795548", linewidth=1.2, zorder=2,
        )
    )
    picked = {action["pick"] for action in record["actions"]}
    for cube in layout["cubes"]:
        ax.add_patch(
            Rectangle(
                (cube["xy"][0] - 0.02, cube["xy"][1] - 0.02), 0.04, 0.04,
                angle=math.degrees(cube["yaw_rad"]), rotation_point="center",
                facecolor=CUBE_COLORS.get(cube["color"], "#888"),
                edgecolor="black" if cube["object_id"] in picked else "none",
                linewidth=1.0, alpha=0.85, zorder=4,
            )
        )
    ax.set_xlim(-0.32, 0.22)
    ax.set_ylim(-0.28, 0.28)


def _draw_routestick(ax, record: dict[str, Any]) -> None:
    theta = math.radians(record["layout"]["rotation_deg"])
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    points = []
    for col in range(9):
        x, y = -0.1, (col - 4) * 0.07
        points.append((x * cos_t - y * sin_t, x * sin_t + y * cos_t))
    for index, (x, y) in enumerate(points):
        if index % 2 == 0:
            ax.add_patch(Circle((x, y), 0.012, facecolor="#90a4ae", edgecolor="#37474f", zorder=3))
        else:
            rgb = record["layout"]["obstacle_rgb"][index // 2]
            ax.add_patch(Polygon([(x, y + 0.014), (x - 0.012, y - 0.01), (x + 0.012, y - 0.01)], color=rgb, zorder=3))
    slots = record["actions"]["node_slots"]
    path = [points[slot] for slot in slots]
    ax.plot([p[0] for p in path], [p[1] for p in path], "-o", color="#e65100", linewidth=1.4, markersize=3, zorder=5)
    ax.plot([path[0][0]], [path[0][1]], "*", color="#1b5e20", markersize=9, zorder=6)
    ax.set_xlim(-0.3, 0.15)
    ax.set_ylim(-0.36, 0.36)


def _draw_video(ax, record: dict[str, Any], is_unmask: bool) -> None:
    layout = record["layout"]
    objects = record["objects"]
    items = layout["bins"] if is_unmask else layout["cubes"]
    if is_unmask:
        hidden_by_bin = {bin_name: color for color, bin_name in objects["hidden"].items()}
    for index, item in enumerate(items):
        x, y = item["xy"]
        if is_unmask:
            color = hidden_by_bin.get(item["object_id"])
            face = CUBE_COLORS.get(color, "#eceff1")
            ax.add_patch(
                Rectangle((x - 0.03, y - 0.03), 0.06, 0.06, angle=item["yaw_deg"], rotation_point="center",
                          facecolor=face, edgecolor="#263238", linewidth=1.0, alpha=0.75, zorder=3)
            )
        else:
            is_target = item["object_id"] == objects["target"]
            ax.add_patch(
                Rectangle((x - 0.02, y - 0.02), 0.04, 0.04, angle=math.degrees(item["yaw_rad"]),
                          rotation_point="center", facecolor=CUBE_COLORS.get(objects["color"], "#888"),
                          edgecolor="black" if is_target else "none", linewidth=1.4, alpha=0.85, zorder=3)
            )
        ax.text(x, y, str(index), fontsize=5, ha="center", va="center", zorder=6, color="white")
    positions = {item["object_id"]: item["xy"] for item in items}
    for order, pair in enumerate(record["actions"]["swap_pairs"]):
        a, b = positions[pair["initiator"]], positions[pair["partner"]]
        ax.annotate("", xy=b, xytext=a,
                    arrowprops=dict(arrowstyle="<->", color="#6d4c41", lw=0.8, alpha=max(0.2, 0.8 - 0.15 * order)), zorder=2)  # xhard 第 5 次（order=4）仍可见
    if not is_unmask:
        ax.add_patch(Circle(layout["button_xy"], 0.015, color="#455a64", zorder=3))
        ax.set_xlim(-0.3, 0.3)
    else:
        ax.set_xlim(-0.3, 0.3)
    ax.set_ylim(-0.3, 0.3)


def _draw_episode(ax, task: str, record: dict[str, Any]) -> None:
    if task == "BinFill":
        _draw_binfill(ax, record)
    elif task == "RouteStick":
        _draw_routestick(ax, record)
    else:
        _draw_video(ax, record, task == "VideoUnmaskSwap")
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def plot_overview(task: str, difficulty: str, records: list[dict[str, Any]], results: dict[int, str] | None, out: Path) -> None:
    """图 1：100 条布局总览，10×10 小图。"""
    figure, axes = plt.subplots(10, 10, figsize=(22, 22))
    phase = "跑后" if results else "跑前"
    for episode, record in enumerate(records):
        ax = axes[episode // 10][episode % 10]
        _draw_episode(ax, task, record)
        if results is None:
            ax.set_title(f"ep{episode}", fontsize=6, pad=2)
            for side in ax.spines.values():
                side.set_linewidth(0.4)
            continue
        outcome = results.get(episode)
        if outcome is None:
            # 实跑范围外：保留细边框并标「范围外」，不进分母
            ax.set_title(f"ep{episode} 范围外", fontsize=6, pad=2, color="#9e9e9e")
            for side in ax.spines.values():
                side.set_linewidth(0.4)
                side.set_color("#cfcfcf")
            continue
        color = RESULT_COLORS.get(outcome, "#9e9e9e")
        ax.set_title(f"ep{episode} {outcome}", fontsize=6, pad=2, color=color)
        for side in ax.spines.values():
            side.set_linewidth(2.0)
            side.set_color(color)
    figure.suptitle(f"图 1 · {task} / {difficulty} 布局总览（{phase}，100 条）", fontsize=16)
    figure.tight_layout(rect=[0, 0, 1, 0.98])
    figure.savefig(out, dpi=90)
    plt.close(figure)


# ── 图 2：空间覆盖 ──────────────────────────────────────────────────────────
def _object_positions(task: str, record: dict[str, Any]) -> list[tuple[float, float]]:
    layout = record["layout"]
    if task == "BinFill":
        return [tuple(cube["xy"]) for cube in layout["cubes"]]
    if task == "RouteStick":
        theta = math.radians(layout["rotation_deg"])
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        return [((-0.1) * cos_t - ((c - 4) * 0.07) * sin_t, (-0.1) * sin_t + ((c - 4) * 0.07) * cos_t) for c in range(9)]
    items = layout.get("bins") or layout.get("cubes")
    return [tuple(item["xy"]) for item in items]


def plot_coverage(task: str, difficulty: str, records: list[dict[str, Any]], results: dict[int, str] | None, out: Path) -> None:
    """图 2：XY 散点 + 每 episode 采样输入的 10×10 占用格 + 每维分箱计数。"""
    phase = "跑后" if results else "跑前"
    cell_names = sorted(records[0].get("sampling_cells", {}))
    figure = plt.figure(figsize=(18, 5 + 2.6 * max(1, math.ceil(len(cell_names) / 4))))
    grid = figure.add_gridspec(1 + math.ceil(len(cell_names) / 4), 4, height_ratios=[2.2] + [1] * math.ceil(len(cell_names) / 4))

    ax_scatter = figure.add_subplot(grid[0, 0:2])
    for episode, record in enumerate(records):
        outcome = results.get(episode) if results else None
        color = "#9e9e9e" if results and outcome is None else RESULT_COLORS.get(outcome, "#1976d2")
        marker = "o" if (outcome in (None, "通过")) else "x"
        for x, y in _object_positions(task, record):
            ax_scatter.plot(x, y, marker, color=color, markersize=3, alpha=0.55)
    ax_scatter.set_aspect("equal")
    ax_scatter.set_title(f"全部对象的实际位置（{phase}）", fontsize=11)
    ax_scatter.set_xlabel("x / 米")
    ax_scatter.set_ylabel("y / 米")
    ax_scatter.grid(alpha=0.25)

    ax_grid = figure.add_subplot(grid[0, 2])
    if cell_names:
        primary = cell_names[0]
        secondary = cell_names[1] if len(cell_names) > 1 else cell_names[0]
        occupancy = [[0] * COARSE_BINS for _ in range(COARSE_BINS)]
        for record in records:
            row = record["sampling_cells"][primary][0]
            col = record["sampling_cells"][secondary][0]
            occupancy[row][col] += 1
        image = ax_grid.imshow(occupancy, cmap="Blues", vmin=0)
        for row in range(COARSE_BINS):
            for col in range(COARSE_BINS):
                ax_grid.text(col, row, str(occupancy[row][col]), ha="center", va="center", fontsize=6)
        figure.colorbar(image, ax=ax_grid, fraction=0.046)
        ax_grid.set_title(f"占用格 {primary} × {secondary}", fontsize=10)
        ax_grid.set_xlabel(secondary)
        ax_grid.set_ylabel(primary)

    ax_note = figure.add_subplot(grid[0, 3])
    ax_note.axis("off")
    ax_note.text(
        0.0, 0.95,
        "读法\n"
        "· 左：全部对象的实际位置，不承诺严格均匀\n"
        "· 中：每 episode 的采样输入落在哪个粗箱\n"
        "· 下：每个连续量的粗箱计数，目标每箱 10 条\n"
        "· 几何拒绝后在同粗箱内重采样，配额不变\n"
        + ("· 跑后只对 episode 0～29 着色，其余标范围外\n" if results else ""),
        fontsize=9, va="top", family="sans-serif",
    )

    for index, name in enumerate(cell_names):
        ax = figure.add_subplot(grid[1 + index // 4, index % 4])
        counts = Counter(record["sampling_cells"][name][0] for record in records)
        values = [counts.get(b, 0) for b in range(COARSE_BINS)]
        ax.bar(range(COARSE_BINS), values, color="#5c9ccc")
        ax.axhline(GROUP_SIZE / COARSE_BINS, color="#c62828", linestyle="--", linewidth=0.9)
        ax.set_title(name, fontsize=9)
        ax.set_xticks(range(COARSE_BINS))
        ax.tick_params(labelsize=7)
        ax.set_ylim(0, max(12, max(values) + 1))

    figure.suptitle(f"图 2 · {task} / {difficulty} 空间覆盖（{phase}）", fontsize=15)
    figure.tight_layout(rect=[0, 0, 1, 0.96])
    figure.savefig(out, dpi=100)
    plt.close(figure)


# ── 图 3：对象与动作分布 ────────────────────────────────────────────────────
def plot_distribution(
    task: str, difficulty: str, records: list[dict[str, Any]], contract: Contract,
    results: dict[int, str] | None, out: Path,
) -> None:
    """图 3：独立类别与耦合类别的横向条形；跑后同一条形按结果分色堆叠。"""
    phase = "跑后" if results else "跑前"
    categories = legal_categories(task, difficulty, contract)
    fields = [(name, legal, True) for name, legal in categories["independent"].items()]
    fields += [(name, legal, False) for name, legal in categories["coupled"].items() if legal]

    figure, axes = plt.subplots(len(fields), 1, figsize=(13, 2.4 * len(fields)))
    if len(fields) == 1:
        axes = [axes]
    for ax, (name, legal, independent) in zip(axes, fields):
        passed: Counter = Counter()
        failed: Counter = Counter()
        for episode, record in enumerate(records):
            values = observed_values(task, record).get(name, [])
            outcome = results.get(episode) if results else None
            target = failed if (results and outcome not in (None, "通过")) else passed
            for value in values:
                target[json.dumps(value, sort_keys=True, ensure_ascii=False)] += 1
        keys = [json.dumps(value, sort_keys=True, ensure_ascii=False) for value in legal]
        # 合法类别之外真的出现了值就并进来（应当为空，出现即是缺陷）
        keys += [key for key in sorted(set(passed) | set(failed)) if key not in keys]
        good = [passed.get(key, 0) for key in keys]
        bad = [failed.get(key, 0) for key in keys]
        positions = range(len(keys))
        ax.barh(positions, good, color="#2e7d32" if results else "#5c9ccc", label="通过" if results else "计数")
        if results:
            ax.barh(positions, bad, left=good, color="#c62828", label="失败")
        ax.set_yticks(list(positions))
        ax.set_yticklabels([key if len(key) <= 34 else key[:31] + "…" for key in keys], fontsize=8)
        spread = (max(good) - min(good)) if good else 0
        flag = "独立类别，计数差 %d" % spread if independent else "耦合类别，只报实际频数"
        uncovered = sum(1 for key in keys if passed.get(key, 0) + failed.get(key, 0) == 0)
        ax.set_title(f"{name}（{flag}；未覆盖 {uncovered} 类）", fontsize=10)
        ax.tick_params(labelsize=8)
        for index, (g, b) in enumerate(zip(good, bad)):
            ax.text(g + b + 0.4, index, str(g + b), va="center", fontsize=7)
        if results:
            ax.legend(fontsize=8, loc="lower right")
    figure.suptitle(f"图 3 · {task} / {difficulty} 对象与动作分布（{phase}）", fontsize=15)
    figure.tight_layout(rect=[0, 0, 1, 0.98])
    figure.savefig(out, dpi=100)
    plt.close(figure)


# ── 入口 ────────────────────────────────────────────────────────────────────
def cmd_plot(run_id: str, phase: str = "before") -> dict[str, Any]:
    from .campaign import DEFAULT_SAMPLING_CONFIG, CampaignError, load_group_documents, resolve_contract, _write_json

    font = _use_cjk_font()
    root, manifest, documents = load_group_documents(run_id)
    sampling = json.loads(DEFAULT_SAMPLING_CONFIG.read_text(encoding="utf-8"))  # 图 1 的几何合法区
    contract = resolve_contract(manifest)  # 图 3 的合法类别表按冻结时那份契约算

    results_by_group: dict[tuple[str, str], dict[int, str]] = {}
    if phase == "after":
        results_path = root / "feasibility_results.json"
        if not results_path.is_file():
            raise CampaignError(f"跑后出图需要实跑结果：{results_path} 不存在，先跑步骤 5")
        payload = json.loads(results_path.read_text(encoding="utf-8"))
        for item in payload["rows"]:
            results_by_group.setdefault((item["task"], item["difficulty"]), {})[int(item["episode"])] = item["outcome"]

    entries: list[dict[str, Any]] = []
    for (task, difficulty), document in documents.items():
        records = sorted(document["episodes"], key=lambda item: item["episode"])
        results = results_by_group.get((task, difficulty)) if phase == "after" else None
        target = root / "plots" / phase / task / difficulty
        target.mkdir(parents=True, exist_ok=True)
        plot_overview(task, difficulty, records, results, target / "overview.png")
        plot_coverage(task, difficulty, records, results, target / "coverage.png")
        plot_distribution(task, difficulty, records, contract, results, target / "distribution.png")
        entries.append(
            {
                "task": task,
                "difficulty": difficulty,
                "phase": phase,
                "directory": str(target.relative_to(root)),
                "files": ["overview.png", "coverage.png", "distribution.png"],
                "thumbnails": len(records),
                # 图与计数表引用同一份规格散列，事后可比对
                "spec_sha256_head": [item["spec_sha256"] for item in records[:3]],
            }
        )
        print(f"  出图 {task}/{difficulty}（{phase}）", flush=True)

    payload = {"run_id": run_id, "phase": phase, "font": font, "groups": entries}
    _write_json(root / f"plot_manifest_{phase}.json", payload)
    print(
        f"PLOT_EVIDENCE={'PASS' if len(entries) == 11 else 'FAIL'} groups={len(entries)} "
        f"phase={phase} thumbnails={sum(item['thumbnails'] for item in entries)} font={font}"
    )
    return payload
