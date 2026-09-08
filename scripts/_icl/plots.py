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
from matplotlib.patches import Polygon, Rectangle, Circle
import numpy as np

from robomme_icl.validation.geometry import quaternion_matrix
from robomme_icl.io.scene_metadata import read_scene_metadata
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
TOPOLOGY_LABELS = {
    "field": "区域散布",
    "route": "整排旋转",
    "triangle": "三角形",
    "line": "直线",
    "rectangle": "矩形",
}
KIND_LABELS = {
    "cube": "方块",
    "container": "容器",
    "board": "投放口",
    "button": "按钮",
    "target": "目标点",
    "obstacle": "障碍",
}
MARKERS = {
    "cube": "o",
    "container": "s",
    "board": "D",
    "button": "P",
    "target": "o",
    "obstacle": "s",
}
STEMS = {
    "BinFill": "binfill",
    "RouteStick": "routestick",
    "VideoUnmaskSwap": "videounmaskswap",
    "VideoRepick": "videorepick",
}


def setup_font():
    """明确使用现有中文字体，不下载依赖或字体。"""
    path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if not path.is_file():
        raise FileNotFoundError("缺少 Noto CJK 中文字体，停止出图而不输出乱码")
    font_manager.fontManager.addfont(str(path))
    family = font_manager.FontProperties(fname=str(path)).get_name()
    plt.rcParams.update(
        {
            "font.family": family,
            "font.size": 11,
            "axes.unicode_minus": False,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "figure.facecolor": "#f6f8fb",
            "axes.facecolor": "white",
            "axes.edgecolor": "#b5c0ce",
            "grid.color": "#dfe6ed",
        }
    )


def counts_text(values, suffix=""):
    counts = Counter(values)
    return (
        "、".join(f"{key}{suffix}：{count}条" for key, count in sorted(counts.items()))
        or "无样本"
    )


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
        values = sorted(
            set(choices["walk_steps"]) | {row["walk_steps"] for row in params}
        )
        counts = Counter(row["walk_steps"] for row in params)
        ax.bar(
            range(len(values)),
            [counts[value] for value in values],
            color=DIFFICULTY_COLORS[difficulty],
            width=0.6,
        )
        ax.set_xticks(range(len(values)), values)
        ax.set_xlabel("游走段数")
        ax.set_ylabel("episode 条数")
        ax.set_ylim(0, count_max * 1.25)
        ax.set_yticks(range(count_max + 1))
        for index, value in enumerate(values):
            ax.text(
                index,
                counts[value] + 0.03,
                str(counts[value]),
                ha="center",
                va="bottom",
                fontsize=12,
            )
        ax.grid(axis="y", alpha=0.6)
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
            ax.text(
                x_index,
                y_index,
                str(count),
                ha="center",
                va="center",
                fontsize=15,
                color="white" if count > count_max * 0.55 and count else "#1e354b",
                fontweight="bold",
            )
        ax.set_xticks(np.arange(-0.5, len(xs), 1), minor=True)
        ax.set_yticks(np.arange(-0.5, len(ys), 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=2)
        ax.tick_params(which="minor", bottom=False, left=False)
        if task == "BinFill":
            detail = f"场景颜色数：{counts_text((row['scene_color_count'] for row in params), '色')}\n目标颜色池：{counts_text((row['target_color_count'] for row in params), '色')}\n逐色实际目标数见认证统计\n动态 {sum(row['dynamic'] for row in params)} 条 / 静态 {sum(not row['dynamic'] for row in params)} 条"
        elif task == "VideoUnmaskSwap":
            detail = (
                "容器数量："
                + counts_text((row["container_count"] for row in params), "个")
                + "\n藏块：每条红、绿、蓝各一个；仅四容器有空容器。"
            )
        else:
            detail = (
                "方块数量："
                + counts_text((row["spawn_count"] for row in params), "个")
                + "\n"
                + (
                    "三种颜色各五块，交换次数为零。"
                    if difficulty == "hard"
                    else "每条环境里的三个方块同色。"
                )
            )
    if not episodes:
        ax.text(
            0.5,
            0.55,
            "该难度无样本",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=15,
            color="#5e6975",
            bbox={
                "boxstyle": "round,pad=.4",
                "fc": "white",
                "ec": "#c8d1db",
                "alpha": 0.94,
            },
        )
        detail = "套件未包含该难度，不补造样本或配额。"
    ax.text(
        0,
        -0.32,
        detail,
        transform=ax.transAxes,
        fontsize=9,
        color="#47596d",
        va="top",
        linespacing=1.7,
    )


def _scene(suite, episode):
    """小型初态有独立摘要，避免为了画位置图读取全部RGB帧。"""
    cache = suite.setdefault("_plot_scenes", {})
    key = episode["spec_hash"]
    if key not in cache:
        cache[key] = read_scene_metadata(suite["certification"][key])
    return cache[key]


def convex_hull(points):
    """把真实 box 的八个角点投影到 xy 后求凸包，仅用于绘制该 box。"""
    points = sorted(set(points))
    if len(points) <= 2:
        return points

    def cross(origin, first, second):
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (
            first[1] - origin[1]
        ) * (second[0] - origin[0])

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


def _actors(scene):
    state = scene["initial_state"]
    result = {}
    hidden = {
        f"target_cube_{color}"
        for color in scene["native_parameters"].get("color_names", [])
    }
    for name, item in state["actors"].items():
        if name not in {"table-workspace", "ground"} and name not in hidden:
            result[name] = (item["pose"], scene["initial_assets"].get(name, []))
    for name, item in state["articulations"].items():
        if name.startswith("button"):
            parts = []
            for key, asset in scene["initial_assets"].items():
                if key.startswith(name + "/"):
                    parts.extend(asset)
            result[name] = (item["pose"], parts)
    return result


def _color(shape):
    materials = [part.get("material", {}) for part in shape.get("mesh_parts", [])]
    materials.append(shape.get("material", {}))
    for material in materials:
        if "base_color" in material:
            return np.clip(np.asarray(material["base_color"]).reshape(-1), 0, 1)
    return [0.7, 0.7, 0.7, 1.0]


def _draw_actor(ax, pose, asset):
    position = np.asarray(pose["position"]).reshape(-1, 3)[0]
    orientation = np.asarray(pose["quaternion"]).reshape(-1, 4)[0]
    rotation = np.asarray(quaternion_matrix(orientation))
    shapes = []
    for entity in asset:
        for component in entity:
            for shape in component.get("render_shapes", []):
                local = shape["pose"]
                center = position + rotation @ np.asarray(local["position"]).reshape(3)
                local_rotation = np.asarray(
                    quaternion_matrix(np.asarray(local["quaternion"]).reshape(4))
                )
                world_rotation = rotation @ local_rotation
                if "half_size" in shape:
                    half = np.asarray(shape["half_size"]).reshape(3)
                    corners = np.array(
                        [
                            center + world_rotation @ (half * signs)
                            for signs in itertools.product((-1, 1), repeat=3)
                        ]
                    )
                    if corners[:, 2].max() < 0:
                        continue
                    polygon = convex_hull([tuple(point[:2]) for point in corners])
                    shapes.append(
                        (
                            float(corners[:, 2].max()),
                            Polygon(
                                polygon,
                                facecolor=_color(shape),
                                edgecolor="#52616f",
                                linewidth=0.6,
                            ),
                        )
                    )
                elif "radius" in shape and center[2] >= 0:
                    shapes.append(
                        (
                            float(center[2]),
                            Circle(
                                center[:2],
                                float(shape["radius"]),
                                facecolor=_color(shape),
                                edgecolor="#52616f",
                                linewidth=0.3,
                            ),
                        )
                    )
    for _, patch in sorted(shapes, key=lambda item: item[0]):
        ax.add_patch(patch)


def _spatial_axes(ax, points):
    if points:
        values = np.asarray(points)
        ax.set_xlim(values[:, 0].min() - 0.08, values[:, 0].max() + 0.08)
        ax.set_ylim(values[:, 1].min() - 0.08, values[:, 1].max() + 0.08)
    else:
        ax.set_xlim(-0.35, 0.25)
        ax.set_ylim(-0.35, 0.35)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("世界坐标 x / 米")
    ax.set_ylabel("世界坐标 y / 米")
    ax.grid(alpha=0.4)


def _draw_task(suite, task, path):
    episodes = [
        episode for episode in suite["episodes"] if episode["task_kind"] == task
    ]
    figure = plt.figure(figsize=(16, 10), constrained_layout=True)
    grid = figure.add_gridspec(2, 6, height_ratios=[1, 1.3])
    count_max = max(1, len(episodes))
    for index, difficulty in enumerate(DIFFICULTIES):
        axis = figure.add_subplot(grid[0, index * 2 : index * 2 + 2])
        rows = [row for row in episodes if row["difficulty"] == difficulty]
        plot_quotas(
            axis,
            task,
            difficulty,
            rows,
            suite["configs"]["task"]["tasks"][task][difficulty],
            count_max,
        )
    example_axis = figure.add_subplot(grid[1, :3])
    scatter_axis = figure.add_subplot(grid[1, 3:])
    points = []
    for episode in episodes:
        actors = _actors(_scene(suite, episode))
        xy = [
            np.asarray(pose["position"]).reshape(-1, 3)[0][:2]
            for pose, _ in actors.values()
        ]
        points.extend(xy)
        if xy:
            values = np.asarray(xy)
            scatter_axis.scatter(
                values[:, 0],
                values[:, 1],
                s=15,
                alpha=0.6,
                color=DIFFICULTY_COLORS[episode["difficulty"]],
            )
    if episodes:
        sample = episodes[0]
        for pose, asset in _actors(_scene(suite, sample)).values():
            _draw_actor(example_axis, pose, asset)
        example_axis.set_title(f"原版实际初态几何 · seed {sample['seed']}")
    else:
        example_axis.set_title("该任务无样本")
    scatter_axis.set_title("认证初态物体中心分布")
    _spatial_axes(example_axis, points)
    _spatial_axes(scatter_axis, points)
    figure.suptitle(f"{task} · {TASK_LABELS[task]} · {len(episodes)} 条", fontsize=18)
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return {
        "episode_spec_hashes": [row["spec_hash"] for row in episodes],
        "episodes": len(episodes),
        "source": "certified_native_initial_state",
        "position_count": len(points),
    }


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
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _publish_json(path, value):
    """先写同目录临时文件，再排他发布，不覆盖已有结果。"""
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{path.stem}-",
        suffix=".json",
        dir=path.parent,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        json.dump(
            value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
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
            rows = [
                row
                for row in suite["episodes"]
                if row["task_kind"] == task and row["difficulty"] == difficulty
            ]
            parameters = [row["task_parameters"] for row in rows]
            keys = sorted({key for row in parameters for key in row})
            margins = {}
            totals = {}
            for key in keys:
                margins[key] = [
                    {"value": json.loads(encoded), "episodes": count}
                    for encoded, count in sorted(
                        Counter(
                            _json(row[key]) for row in parameters if key in row
                        ).items()
                    )
                ]
                if key.endswith("_count") or key == "walk_steps":
                    values = [row[key] for row in parameters if key in row]
                    if all(type(value) is int for value in values):
                        totals[key] = sum(values)
            groups = defaultdict(list)
            for row in rows:
                count = row["task_parameters"].get(
                    "spawn_count", row["task_parameters"].get("container_count", 0)
                )
                groups[(row["layout"]["topology"], count)].append(row)
            coverage = []
            for (topology, object_count), grouped in sorted(groups.items()):
                dimensions = {}
                for name in sorted(
                    {name for row in grouped for name in row["layout"]["strata"]}
                ):
                    layers = [
                        row["layout"]["strata"][name]
                        for row in grouped
                        if name in row["layout"]["strata"]
                    ]
                    first = layers[0]
                    if any(
                        layer["count"] != first["count"]
                        or layer["support"] != first["support"]
                        for layer in layers
                    ):
                        raise ValueError(
                            f"同一位置分组的分层定义不一致：{task}/{difficulty}/{name}"
                        )
                    indices = Counter(layer["index"] for layer in layers)
                    dimensions[name] = {
                        "support": first["support"],
                        "strata_count": first["count"],
                        "index_counts": {
                            str(index): indices[index]
                            for index in range(first["count"])
                        },
                        "covered_strata": len(indices),
                        "coverage_fraction": len(indices) / first["count"],
                        "missing_indices": [
                            index
                            for index in range(first["count"])
                            if not indices[index]
                        ],
                    }
                coverage.append(
                    {
                        "topology": topology,
                        "object_count": object_count,
                        "episodes": len(grouped),
                        "episode_spec_hashes": [row["spec_hash"] for row in grouped],
                        "dimensions": dimensions,
                    }
                )
            difficulties[difficulty] = {
                "episodes": len(rows),
                "parameter_counts": margins,
                "parameter_totals": totals,
                "target_color_totals": {
                    name: sum(
                        _scene(suite, row)["native_parameters"].get(
                            f"{name}_cubes_target_number", 0
                        )
                        for row in rows
                    )
                    for name in ("red", "green", "blue")
                },
                "topology_counts": dict(
                    Counter(row["layout"]["topology"] for row in rows)
                ),
                "position_groups": coverage,
            }
        tasks[task] = {
            "episodes": sum(row["episodes"] for row in difficulties.values()),
            "difficulties": difficulties,
        }
    return tasks


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
    identity = {
        "schema_version": 1,
        "suite_hash": suite["suite_hash"],
        "plot_code_sha256": _sha256(__file__),
        "episode_spec_hashes": [row["spec_hash"] for row in suite["episodes"]],
    }
    # 在出图前检查整个输出集合，不能先覆盖一部分后才发现其他来源冲突。
    previous = {}
    for task in TASKS:
        png = destination / f"{STEMS[task]}.png"
        sidecar = destination / f"{STEMS[task]}.json"
        if sidecar.exists():
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            if (
                any(metadata.get(key) != value for key, value in identity.items())
                or metadata.get("task_kind") != task
            ):
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
            with tempfile.NamedTemporaryFile(
                prefix=f".{STEMS[task]}-", suffix=".png", dir=destination, delete=False
            ) as stream:
                temporary = Path(stream.name)
            try:
                details = _draw_task(suite, task, temporary)
                result = {
                    **identity,
                    "source_suite": str(source),
                    "task_kind": task,
                    "figure": details,
                    "image_sha256": _sha256(temporary),
                }
                if metadata is not None and result["image_sha256"] != metadata.get(
                    "image_sha256"
                ):
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
        figures.append(
            {
                **metadata["figure"],
                "path": str(path),
                "sidecar": str(sidecar),
                "image_sha256": metadata["image_sha256"],
            }
        )
    result = {
        **identity,
        "source_suite": str(source),
        "source_status": suite["status"],
        "episodes_total": len(suite["episodes"]),
        "tasks": _actual_distribution(suite),
        "figures": figures,
    }
    if existing_summary is not None:
        comparable = {
            key: value
            for key, value in existing_summary.items()
            if key != "source_suite"
        }
        expected = {
            key: value for key, value in result.items() if key != "source_suite"
        }
        if comparable != expected:
            raise ValueError(
                f"已有分布统计与实际清单或图片不符，禁止覆盖：{summary_path}"
            )
    else:
        _publish_json(summary_path, result)
    return {**result, "summary_path": str(summary_path), "resumed": resumed}
