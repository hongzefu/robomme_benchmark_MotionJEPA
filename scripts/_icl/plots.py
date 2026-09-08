"""从已认证清单绘制实际次数配额、单局布局与跨局位置分布。"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import itertools
import json
import os
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib-icl-certified"))

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon, Rectangle
import numpy as np

from robomme_icl.geometry.collision import actor_boxes
from robomme_icl.io.paths import output_path, repository_root
from robomme_icl.suite import DIFFICULTIES, TASKS, load_suite


DIFFICULTY_LABELS = {"easy": "简单", "medium": "中等", "hard": "困难"}
DIFFICULTY_COLORS = {"easy": "#187aa6", "medium": "#d88613", "hard": "#9560a0"}
TASK_LABELS = {
    "BinFill": "按颜色数量投放",
    "RouteStick": "记忆游走顺序与绕行方向",
    "VideoUnmaskSwap": "观看演示后追踪交换容器",
    "VideoRepick": "记忆目标并重复抓放",
}
TOPOLOGY_LABELS = {"field": "区域散布", "route": "整排旋转", "triangle": "三角形", "line": "直线", "rectangle": "矩形"}
KIND_LABELS = {"cube": "方块", "container": "容器", "board": "投放口", "button": "按钮", "target": "目标点", "obstacle": "障碍"}
MARKERS = {"cube": "o", "container": "s", "board": "D", "button": "P", "target": "o", "obstacle": "s"}
STEMS = {"BinFill": "binfill", "RouteStick": "routestick", "VideoUnmaskSwap": "videounmaskswap", "VideoRepick": "videorepick"}


def setup_font():
    """明确使用现有中文字体，不下载依赖或字体。"""
    path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if not path.is_file():
        raise FileNotFoundError("缺少 Noto CJK 中文字体，停止出图而不输出乱码")
    font_manager.fontManager.addfont(str(path))
    family = font_manager.FontProperties(fname=str(path)).get_name()
    plt.rcParams.update({"font.family": family, "font.size": 11, "axes.unicode_minus": False,
                         "axes.titlesize": 13, "axes.labelsize": 11, "figure.facecolor": "#f6f8fb",
                         "axes.facecolor": "white", "axes.edgecolor": "#b5c0ce", "grid.color": "#dfe6ed"})


def counts_text(values, suffix=""):
    counts = Counter(values)
    return "、".join(f"{key}{suffix}：{count}条" for key, count in sorted(counts.items())) or "无样本"


def task_dimensions(task):
    if task == "BinFill":
        return "spawn_count", "pick_count", "场上方块总数", "放入次数"
    if task == "VideoUnmaskSwap":
        return "swap_count", "pick_count", "交换次数", "抓起容器次数"
    return "swap_count", "repeat_count", "交换次数", "评测阶段重复抓放次数"


def plot_quotas(ax, task, difficulty, episodes, choices, count_max):
    """联合图对其余维度求和，数值完全由套件里的场景记录计数。"""
    title = f"{DIFFICULTY_LABELS[difficulty]} · {len(episodes)} 条"
    ax.set_title(title, loc="left", fontweight="bold", pad=12)
    params = [episode["task_parameters"] for episode in episodes]
    if task == "RouteStick":
        values = sorted(set(choices["walk_steps"]) | {row["walk_steps"] for row in params})
        counts = Counter(row["walk_steps"] for row in params)
        ax.bar(range(len(values)), [counts[value] for value in values], color=DIFFICULTY_COLORS[difficulty], width=.6)
        ax.set_xticks(range(len(values)), values)
        ax.set_xlabel("游走段数")
        ax.set_ylabel("episode 条数")
        ax.set_ylim(0, count_max * 1.25)
        ax.set_yticks(range(count_max + 1))
        for index, value in enumerate(values):
            ax.text(index, counts[value] + .03, str(counts[value]), ha="center", va="bottom", fontsize=12)
        ax.grid(axis="y", alpha=.6)
        ax.set_axisbelow(True)
        detail = "每段都连接相邻目标；整排位置只改变旋转角。"
    else:
        x_key, y_key, x_label, y_label = task_dimensions(task)
        xs = sorted(set(choices[x_key]) | {row[x_key] for row in params})
        ys = sorted(set(choices[y_key]) | {row[y_key] for row in params})
        counts = Counter((row[x_key], row[y_key]) for row in params)
        matrix = np.array([[counts[x, y] for x in xs] for y in ys], dtype=int)
        ax.imshow(matrix, cmap="Blues", vmin=0, vmax=count_max, aspect="auto")
        ax.set_xticks(range(len(xs)), xs)
        ax.set_yticks(range(len(ys)), ys)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        for y_index, x_index in itertools.product(range(len(ys)), range(len(xs))):
            count = int(matrix[y_index, x_index])
            ax.text(x_index, y_index, str(count), ha="center", va="center", fontsize=15,
                    color="white" if count > count_max * .55 and count else "#1e354b", fontweight="bold")
        ax.set_xticks(np.arange(-.5, len(xs), 1), minor=True)
        ax.set_yticks(np.arange(-.5, len(ys), 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=2)
        ax.tick_params(which="minor", bottom=False, left=False)
        if task == "BinFill":
            target_totals = {name: sum(row["target_counts"][name] for row in params) for name in ("red", "green", "blue")}
            detail = f"场景颜色数：{counts_text((row['scene_color_count'] for row in params), '色')}\n目标颜色数：{counts_text((row['target_color_count'] for row in params), '色')}\n目标投放合计：红 {target_totals['red']}、绿 {target_totals['green']}、蓝 {target_totals['blue']} 个\n动态 {sum(row['dynamic'] for row in params)} 条 / 静态 {sum(not row['dynamic'] for row in params)} 条"
        elif task == "VideoUnmaskSwap":
            detail = "容器数量：" + counts_text((row["container_count"] for row in params), "个") + "\n藏块：每条红、绿、蓝各一个；仅四容器有空容器。"
        else:
            detail = "方块数量：" + counts_text((row["spawn_count"] for row in params), "个") + "\n" + ("三种颜色各五块，交换次数为零。" if difficulty == "hard" else "每条环境里的三个方块同色。")
    if not episodes:
        ax.text(.5, .55, "该难度无样本", transform=ax.transAxes, ha="center", va="center", fontsize=15,
                color="#5e6975", bbox={"boxstyle": "round,pad=.4", "fc": "white", "ec": "#c8d1db", "alpha": .94})
        detail = "套件未包含该难度，不补造样本或配额。"
    ax.text(0, -.32, detail, transform=ax.transAxes, fontsize=9, color="#47596d", va="top", linespacing=1.7)


def selected_actors(episode):
    """藏块与容器共用 xy，位置覆盖图只计一次容器中心。"""
    return [actor for actor in episode["actors"] if "parent_id" not in actor]


def convex_hull(points):
    """把真实 box 的八个角点投影到 xy 后求凸包，仅用于绘制该 box。"""
    points = sorted(set(points))
    if len(points) <= 2:
        return points
    def cross(origin, first, second):
        return (first[0]-origin[0])*(second[1]-origin[1])-(first[1]-origin[1])*(second[0]-origin[0])
    lower, upper = [], []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def box_polygon(box):
    return convex_hull([tuple(box.center[coordinate] + sum(signs[index] * box.half_size[index] * box.axes[index][coordinate] for index in range(3)) for coordinate in range(2))
                        for signs in itertools.product((-1, 1), repeat=3)])


def spatial_limits(episodes):
    points = []
    for episode in episodes:
        for actor in selected_actors(episode):
            points.extend(box_polygon(box) for box in actor_boxes(actor, episode["geometry"]))
            if "initial_xy_bounds" in actor:
                bounds = actor["initial_xy_bounds"]
                points.append(list(itertools.product(bounds["x"], bounds["y"])))
    flat = [point for polygon in points for point in polygon]
    if not flat:
        return -.4, .4, -.4, .4
    xs, ys = zip(*flat)
    center_x, center_y = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
    half = max(max(xs)-min(xs), max(ys)-min(ys), .3)/2 + .045
    return center_x-half, center_x+half, center_y-half, center_y+half


def format_spatial(ax, limits):
    ax.set_xlim(limits[:2])
    ax.set_ylim(limits[2:])
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("世界坐标 x（米）")
    ax.set_ylabel("世界坐标 y（米）")
    ax.grid(alpha=.65, linewidth=.7)
    ax.set_axisbelow(True)


def plot_single(ax, task, episode, limits):
    difficulty = episode["difficulty"]
    ax.set_title(f"单条环境：{DIFFICULTY_LABELS[difficulty]} · seed={episode['seed']}", loc="left", fontweight="bold", pad=12)
    seen_bounds = set()
    actors = selected_actors(episode)
    for actor in actors:
        if "initial_xy_bounds" in actor:
            bounds = actor["initial_xy_bounds"]
            key = tuple(bounds["x"]+bounds["y"])
            if key not in seen_bounds:
                seen_bounds.add(key)
                ax.add_patch(Rectangle((bounds["x"][0], bounds["y"][0]), bounds["x"][1]-bounds["x"][0], bounds["y"][1]-bounds["y"][0],
                                       fill=False, edgecolor="#a2b0bd", linestyle="--", linewidth=.85, zorder=1))
        color = actor["color"]
        if actor["kind"] == "board":
            color = "#bd8a4a"
        elif actor["kind"] == "button":
            color = "#646f7d"
        for box in actor_boxes(actor, episode["geometry"]):
            ax.add_patch(Polygon(box_polygon(box), facecolor=color, edgecolor="#2d3d4c", alpha=.48, linewidth=.8, zorder=3))
        x, y = actor["position"][:2]
        if actor["role"] in ("target", "hidden_target"):
            ax.scatter([x], [y], s=90, marker="*", color="#111a27", zorder=5)
        short = actor["id"].replace("container_", "b").replace("cube_", "c").replace("target_", "T").replace("obstacle_", "o").replace("button", "按钮").replace("board", "投放口")
        ax.annotate(short, (x, y), xytext=(2, 5), textcoords="offset points", fontsize=8, color="#192b3a", zorder=6)
    topology = TOPOLOGY_LABELS[episode["layout"]["topology"]]
    notes = [f"实际布局：{topology}；图中物体均属于这一条环境。", "虚线框＝完整物体的初始支持外框；★＝任务目标。"]
    if task == "RouteStick":
        yaw = episode["layout"]["yaw_degrees"]
        targets = sorted([actor for actor in actors if actor["kind"] == "target"], key=lambda actor: actor["id"])
        ax.plot([actor["position"][0] for actor in targets], [actor["position"][1] for actor in targets], linestyle="--", linewidth=1, color="#748da4", zorder=2)
        sequence = " → ".join(f"T{index}" for index in episode["task_parameters"]["path_indices"])
        notes = [f"整排旋转角：{yaw:.2f}°；访问顺序：{sequence}", "虚线仅表示目标的排列，不代表机械臂运动轨迹。"]
    elif task == "VideoUnmaskSwap":
        children = [actor for actor in episode["actors"] if "parent_id" in actor]
        for actor in children:
            x, y = actor["position"][:2]
            ax.scatter([x], [y], color=[actor["color"]], s=26, edgecolor="white", linewidth=.7, zorder=7)
        notes.append("容器中心的小色点仅标注实际藏块颜色，未改变其真实位置。")
    elif task == "VideoRepick":
        notes.append(f"评测重复抓放 {episode['task_parameters']['repeat_count']} 次；演示另有一次抓放。")
    ax.text(0, -.18, "\n".join(notes), transform=ax.transAxes, fontsize=9, color="#47596d", va="top", linespacing=1.7)
    format_spatial(ax, limits)


def plot_scatter(ax, task, episodes, limits):
    ax.set_title(f"跨 episode 初始位置叠加：{len(episodes)} 条独立环境", loc="left", fontweight="bold", pad=12)
    point_counts = Counter()
    kinds = set()
    for difficulty in DIFFICULTIES:
        rows = [episode for episode in episodes if episode["difficulty"] == difficulty]
        for kind in KIND_LABELS:
            points = [actor["position"][:2] for episode in rows for actor in selected_actors(episode) if actor["kind"] == kind]
            if not points:
                continue
            point_counts[kind] += len(points)
            kinds.add(kind)
            xs, ys = zip(*points)
            ax.scatter(xs, ys, marker=MARKERS[kind], s=26 if kind == "cube" else 42, c=DIFFICULTY_COLORS[difficulty], alpha=.68,
                       linewidths=.45, edgecolors="#304355", zorder=3)
    handles = [Line2D([0], [0], linestyle="", marker="o", markersize=6, color=DIFFICULTY_COLORS[difficulty], label=f"{DIFFICULTY_LABELS[difficulty]} {sum(e['difficulty']==difficulty for e in episodes)}条") for difficulty in DIFFICULTIES]
    handles += [Line2D([0], [0], linestyle="", marker=MARKERS[kind], markersize=6, color="#6a7785", label=f"{KIND_LABELS[kind]} {point_counts[kind]}点") for kind in KIND_LABELS if kind in kinds]
    ax.legend(handles=handles, fontsize=8, loc="upper right", ncol=2, framealpha=.94, title="颜色＝难度；形状＝物体类型", title_fontsize=8)
    topologies = Counter(episode["layout"]["topology"] for episode in episodes)
    topology_text = "、".join(f"{TOPOLOGY_LABELS[name]} {count}条" for name, count in sorted(topologies.items()))
    notes = [f"总计 {sum(point_counts.values())} 个中心点；{topology_text}。", "叠加点来自不同环境，点重叠不表示同一环境发生碰撞。"]
    if task == "VideoUnmaskSwap":
        notes.append("藏块与容器共用 xy；此图仅计容器中心，不重复绘制藏块。")
    if task == "RouteStick":
        notes.append("弧带来自整排共同旋转，目标与障碍之间的相对布局保持。")
    ax.text(0, -.18, "\n".join(notes), transform=ax.transAxes, fontsize=9, color="#47596d", va="top", linespacing=1.7)
    format_spatial(ax, limits)
    return dict(point_counts)


def _safe_output(path):
    """绘图输出不能越出仓库或进入官方参考集。"""
    target = output_path(path)
    reference = repository_root() / "data" / "robomme_data_h5"
    if target == reference or target.is_relative_to(reference):
        raise ValueError(f"禁止向官方参考数据写入图表：{target}")
    return target


def _sha256(path):
    """分块读取文件摘要，验证已存在的图片与来源记录。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(value):
    """来源与计数使用稳定 JSON 编码，避免字典顺序影响比较。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _publish_json(path, value):
    """先写同目录临时文件，再排他发布，不覆盖已有结果。"""
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=f".{path.stem}-",
                                     suffix=".json", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            actual = json.loads(path.read_text(encoding="utf-8"))
            if actual != value:
                raise ValueError(f"已有图表来源记录不同，拒绝覆盖：{path}")
    finally:
        temporary.unlink(missing_ok=True)


def _actual_distribution(suite):
    """从冻结记录统计实际计数和每个位置分组的分层覆盖。"""
    tasks = {}
    for task in TASKS:
        difficulties = {}
        for difficulty in DIFFICULTIES:
            rows = [row for row in suite["episodes"] if row["task_kind"] == task and row["difficulty"] == difficulty]
            parameters = [row["task_parameters"] for row in rows]
            keys = sorted({key for row in parameters for key in row})
            margins = {}
            totals = {}
            for key in keys:
                margins[key] = [
                    {"value": json.loads(encoded), "episodes": count}
                    for encoded, count in sorted(Counter(_json(row[key]) for row in parameters if key in row).items())
                ]
                if key.endswith("_count") or key == "walk_steps":
                    values = [row[key] for row in parameters if key in row]
                    if all(type(value) is int for value in values):
                        totals[key] = sum(values)
            groups = defaultdict(list)
            for row in rows:
                count = row["task_parameters"].get("spawn_count", row["task_parameters"].get("container_count", 0))
                groups[(row["layout"]["topology"], count)].append(row)
            coverage = []
            for (topology, object_count), grouped in sorted(groups.items()):
                dimensions = {}
                for name in sorted({name for row in grouped for name in row["layout"]["strata"]}):
                    layers = [row["layout"]["strata"][name] for row in grouped if name in row["layout"]["strata"]]
                    first = layers[0]
                    if any(layer["count"] != first["count"] or layer["support"] != first["support"] for layer in layers):
                        raise ValueError(f"同一位置分组的分层定义不一致：{task}/{difficulty}/{name}")
                    indices = Counter(layer["index"] for layer in layers)
                    dimensions[name] = {
                        "support": first["support"], "strata_count": first["count"],
                        "index_counts": {str(index): indices[index] for index in range(first["count"])},
                        "covered_strata": len(indices), "coverage_fraction": len(indices) / first["count"],
                        "missing_indices": [index for index in range(first["count"]) if not indices[index]],
                    }
                coverage.append({"topology": topology, "object_count": object_count, "episodes": len(grouped),
                                 "episode_spec_hashes": [row["spec_hash"] for row in grouped], "dimensions": dimensions})
            difficulties[difficulty] = {
                "episodes": len(rows), "parameter_counts": margins, "parameter_totals": totals,
                "target_color_totals": {name: sum(row.get("target_counts", {}).get(name, 0) for row in parameters)
                                        for name in ("red", "green", "blue")},
                "topology_counts": dict(Counter(row["layout"]["topology"] for row in rows)),
                "position_groups": coverage,
            }
        tasks[task] = {"episodes": sum(row["episodes"] for row in difficulties.values()), "difficulties": difficulties}
    return tasks


def _draw_task(suite, task, path):
    """保持既有五面板组合图，所有标记点均来自实际场景。"""
    episodes = [episode for episode in suite["episodes"] if episode["task_kind"] == task]
    if task == "RouteStick":
        quota_counts = Counter((episode["difficulty"], episode["task_parameters"]["walk_steps"]) for episode in episodes)
    else:
        x_key, y_key, _, _ = task_dimensions(task)
        quota_counts = Counter((episode["difficulty"], episode["task_parameters"][x_key], episode["task_parameters"][y_key]) for episode in episodes)
    count_max = max(list(quota_counts.values()) + [1])
    fig = plt.figure(figsize=(15, 12.5))
    try:
        grid = fig.add_gridspec(2, 6, left=.065, right=.975, bottom=.18, top=.84, wspace=.8, hspace=.72, height_ratios=(.9, 1.6))
        fig.suptitle(f"{task}：{TASK_LABELS[task]}", x=.065, y=.975, ha="left", fontsize=23, fontweight="bold", color="#142f48")
        fig.text(.065, .931, f"已认证套件的实际数据 · 本任务 {len(episodes)} 条 · 上方数字均为 episode 条数", fontsize=12, color="#355268")
        fig.text(.065, .898, "次数配额：按难度分别统计；联合图已对颜色、动态机制等其他维度求和。" if task != "RouteStick" else "次数配额：游走段数直接读取每条场景记录；没有重新随机采样。", fontsize=11, color="#53687b")
        for index, difficulty in enumerate(DIFFICULTIES):
            plot_quotas(fig.add_subplot(grid[0, index*2:index*2+2]), task, difficulty,
                        [episode for episode in episodes if episode["difficulty"] == difficulty], suite["configs"]["task"]["tasks"][task][difficulty], count_max)
        single_axis = fig.add_subplot(grid[1, :3])
        scatter_axis = fig.add_subplot(grid[1, 3:])
        limits = spatial_limits(episodes)
        point_counts = {}
        selected = None
        if episodes:
            selected = next((episode for episode in episodes if episode["difficulty"] == "hard"), episodes[0])
            plot_single(single_axis, task, selected, limits)
            point_counts = plot_scatter(scatter_axis, task, episodes, limits)
        else:
            for axis in (single_axis, scatter_axis):
                axis.text(.5, .5, "该任务无认证样本", transform=axis.transAxes, ha="center", va="center")
                format_spatial(axis, limits)
        fig.text(.065, .043, "所有位置和数量均来自传入的已认证 EpisodeSpec；未补造点、未对缺失难度推算配额。", fontsize=10, color="#3c566e")
        fig.text(.065, .02, f"套件哈希：{suite['suite_hash']}    |    坐标单位：米；位置图采用等比例坐标轴", fontsize=8, color="#6b7c8c")
        fig.savefig(path, dpi=170, facecolor=fig.get_facecolor())
    finally:
        plt.close(fig)
    return {"task_kind": task, "episodes": len(episodes),
            "single_example_seed": selected["seed"] if selected else None,
            "single_example_spec_hash": selected["spec_hash"] if selected else None,
            "scatter_point_counts": point_counts,
            "episode_spec_hashes": [episode["spec_hash"] for episode in episodes]}


def plot_distributions(suite_path, output_dir) -> dict:
    """校验清单后出四张组合图；复用完整同源产物，只补缺失图片。"""
    source = Path(suite_path).expanduser().resolve()
    if source.is_dir():
        source /= "suite.json"
    suite = load_suite(source)
    destination = _safe_output(output_dir)
    for task in TASKS:
        for suffix in ("png", "json"):
            _safe_output(destination / f"{STEMS[task]}.{suffix}")
    summary_path = _safe_output(destination / "distribution_summary.json")
    identity = {"schema_version": 1, "suite_hash": suite["suite_hash"], "plot_code_sha256": _sha256(__file__),
                "episode_spec_hashes": [row["spec_hash"] for row in suite["episodes"]]}
    # 在出图前检查整个输出集合，不能先覆盖一部分后才发现其他来源冲突。
    previous = {}
    for task in TASKS:
        png = destination / f"{STEMS[task]}.png"
        sidecar = destination / f"{STEMS[task]}.json"
        if sidecar.exists():
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            if any(metadata.get(key) != value for key, value in identity.items()) or metadata.get("task_kind") != task:
                raise ValueError(f"已有分布图来源不匹配，禁止覆盖：{sidecar}")
            previous[task] = metadata
            if png.exists() and _sha256(png) != metadata.get("image_sha256"):
                raise ValueError(f"已有分布图摘要不匹配，禁止覆盖：{png}")
        elif png.exists():
            raise FileExistsError(f"已有分布图缺少来源记录，禁止覆盖：{png}")
    existing_summary = None
    if summary_path.exists():
        existing_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if any(existing_summary.get(key) != value for key, value in identity.items()):
            raise ValueError(f"已有分布统计来源不匹配，禁止覆盖：{summary_path}")
    destination.mkdir(parents=True, exist_ok=True)
    setup_font()
    figures = []
    resumed = True
    for task in TASKS:
        path = destination / f"{STEMS[task]}.png"
        sidecar = destination / f"{STEMS[task]}.json"
        metadata = previous.get(task)
        if not path.exists():
            resumed = False
            with tempfile.NamedTemporaryFile(prefix=f".{STEMS[task]}-", suffix=".png", dir=destination, delete=False) as stream:
                temporary = Path(stream.name)
            try:
                details = _draw_task(suite, task, temporary)
                result = {**identity, "source_suite": str(source), "task_kind": task,
                          "figure": details, "image_sha256": _sha256(temporary)}
                if metadata is not None and result["image_sha256"] != metadata.get("image_sha256"):
                    raise ValueError("补图与既有来源记录的图像摘要不同，禁止覆盖")
                if metadata is None:
                    _publish_json(sidecar, result)
                    metadata = result
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    if _sha256(path) != result["image_sha256"]:
                        raise ValueError("并发发布的分布图不同，禁止覆盖")
            finally:
                temporary.unlink(missing_ok=True)
        figures.append({**metadata["figure"], "path": str(path), "sidecar": str(sidecar),
                        "image_sha256": metadata["image_sha256"]})
    result = {**identity, "source_suite": str(source), "source_status": suite["status"],
              "episodes_total": len(suite["episodes"]), "tasks": _actual_distribution(suite), "figures": figures}
    if existing_summary is not None:
        comparable = {key: value for key, value in existing_summary.items() if key != "source_suite"}
        expected = {key: value for key, value in result.items() if key != "source_suite"}
        if comparable != expected:
            raise ValueError(f"已有分布统计与实际清单或图片不符，禁止覆盖：{summary_path}")
    else:
        _publish_json(summary_path, result)
    return {**result, "summary_path": str(summary_path), "resumed": resumed}
