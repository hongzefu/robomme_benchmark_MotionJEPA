"""把 policy 侧的 eval 结果按本目录复算出的动作参数分组，画成功率分布图。

数据来源（跨仓库，只读）：
  /data/hongzefu/robomme_policy_learning_MotionJEPA/docs/training-doc/
    eval-{hard,medium}-patternlock-routestick/records/{context,modul}/per_episode.json
两个变体是 framesample 的官方两档：perceptual-framesamp-context / perceptual-framesamp-modul。
join 键是 (task, split, episode)，并断言 seed 与本目录 derived_params.json 逐条相同。

成功率一律带 Wilson 95% 置信区间——每格样本只有个位数到十几条，不给区间会把噪声当趋势看。
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

HERE = Path(__file__).resolve().parent
EVAL_ROOT = Path("/data/hongzefu/robomme_policy_learning_MotionJEPA/docs/training-doc")
DIFFICULTIES = ["medium", "hard"]
# 表格里按 medium → hard 展示（由易到难），与 DIFFICULTIES 的用途区分开
DIFFICULTIES_DISPLAY = ["medium", "hard"]
VARIANTS = ["modul", "context"]
VARIANT_LABEL = {
    "modul": "framesamp-modul",
    "context": "framesamp-context",
}
COLOR = {"modul": "#2f6f9f", "context": "#c2703d"}
IMITATION_TASKS = ["PatternLock", "RouteStick"]
COUNTING_TASKS = ["BinFill", "PickXtimes"]
TASKS = IMITATION_TASKS + COUNTING_TASKS
# BinFill / PickXtimes 的 eval 目录层级与前两轮不同：难度档在 records 下面一层
COUNTING_EVAL_DIR = "eval-binfill-pickxtimes"
WORD_TO_INT = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def setup_font() -> None:
    """让图里的中文能正常渲染。

    系统里的 CJK 字体是 .ttc，matplotlib 默认不索引，必须显式 addfont 注册；
    注册后拿到的 face 名是 "Noto Sans CJK JP"（ttc 的首个 face），但它用的是 CJK 统一字库，
    简体汉字照常显示。
    """
    for path in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    ):
        if Path(path).exists():
            try:
                font_manager.fontManager.addfont(path)
            except Exception:  # 字体损坏或版本不支持时退回默认，图仍能出，只是中文变方块
                continue
    for name in ("Noto Sans CJK JP", "Noto Sans CJK SC", "Noto Serif CJK JP"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float, float]:
    """Wilson score 区间：小样本下比正态近似稳，成功数为 0 时也给得出上界。"""
    if total == 0:
        return (0.0, 0.0, 0.0)
    phat = successes / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    half = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denom
    return (phat, max(0.0, center - half), min(1.0, center + half))


def load_counting_rows() -> list[dict[str, Any]]:
    """装载 BinFill / PickXtimes 的 eval 结果。

    参数不走 h5：eval 记录的 `video` 字段里带着完整 task_goal，动作次数与颜色组成直接从中解析。
    这个解析已用 val 侧 h5 的 setup/task_goal 逐条校验过（48/48 相同），且 test 侧本来就没有官方 h5，
    所以统一从 eval 记录取，图可以独立于 h5 重新生成。
    """
    out: list[dict[str, Any]] = []
    for difficulty in DIFFICULTIES:
        for variant in VARIANTS:
            path = EVAL_ROOT / COUNTING_EVAL_DIR / "records" / difficulty / variant / "per_episode.json"
            for item in json.loads(path.read_text(encoding="utf-8")):
                goal = item["video"].split("_", 3)[3].rsplit("_", 1)[0].lower()
                if item["task"] == "BinFill":
                    counts = {c: 0 for c in ("red", "blue", "green")}
                    for word, color in re.findall(
                        r"(one|two|three|four|five|six) (red|blue|green) cubes?", goal
                    ):
                        counts[color] += WORD_TO_INT[word]
                    params = {
                        "actions": sum(counts.values()),
                        "color_kinds": sum(1 for v in counts.values() if v),
                        "cube_color": None,
                    }
                else:
                    match = re.search(r"repeating this action (one|two|three|four|five|six) times", goal)
                    color = re.search(r"pick up the (red|blue|green) cube", goal)
                    params = {
                        "actions": WORD_TO_INT[match.group(1)] if match else 1,
                        "color_kinds": 1,
                        "cube_color": color.group(1) if color else "unknown",
                    }
                params["task_goal"] = goal
                out.append(
                    {
                        "difficulty": difficulty,
                        "variant": variant,
                        "task": item["task"],
                        "split": item["split"],
                        "episode": item["episode"],
                        "success": bool(item["success"]),
                        "params": params,
                    }
                )
    return out


def load_rows(derived_path: Path) -> list[dict[str, Any]]:
    derived = json.loads(derived_path.read_text(encoding="utf-8"))
    index = {
        (row["task"], row["split"], row["episode"]): row
        for rows in derived.values()
        for row in rows
    }
    out: list[dict[str, Any]] = []
    for difficulty in DIFFICULTIES:
        for variant in VARIANTS:
            path = (
                EVAL_ROOT
                / f"eval-{difficulty}-patternlock-routestick"
                / "records"
                / variant
                / "per_episode.json"
            )
            for item in json.loads(path.read_text(encoding="utf-8")):
                key = (item["task"], item["split"], item["episode"])
                params = index.get(key)
                if params is None:
                    raise KeyError(f"eval 里的 {key} 在 derived_params.json 中找不到")
                if int(params["seed"]) != int(item["seed"]):
                    raise ValueError(f"{key} seed 不一致：{params['seed']} vs {item['seed']}")
                out.append(
                    {
                        "difficulty": difficulty,
                        "variant": variant,
                        "task": item["task"],
                        "split": item["split"],
                        "episode": item["episode"],
                        "success": bool(item["success"]),
                        "params": params,
                    }
                )
    return out


# ---- 分组维度 ----------------------------------------------------------------

def dim_moves(params: dict) -> Any:
    return params["moves"]


def dim_direction_kinds(params: dict) -> Any:
    """PatternLock 路径用到几种不同方向——形状复杂度，与 move 次数不完全重合。"""
    return len(set(params["move_directions"]))


def dim_start_position(params: dict) -> Any:
    grid = params["grid"]
    row, col = divmod(params["path_nodes"][0], grid)
    on_edge = int(row in (0, grid - 1)) + int(col in (0, grid - 1))
    return {2: "角", 1: "边", 0: "内部"}[on_edge]


def dim_span(params: dict) -> Any:
    """起点到终点的曼哈顿格距——路径跨了多远。"""
    grid = params["grid"]
    start, end = params["path_nodes"][0], params["path_nodes"][-1]
    return abs(start // grid - end // grid) + abs(start % grid - end % grid)


def dim_swing_switch(params: dict) -> Any:
    """RouteStick 顺/逆时针切换了几次。"""
    swings = params["swing_directions"]
    return sum(1 for a, b in zip(swings, swings[1:]) if a != b)


def dim_theta(params: dict) -> Any:
    value = abs(params["theta_deg"])
    if value < 10:
        return "|θ| < 10°"
    if value < 20:
        return "10° ≤ |θ| < 20°"
    return "|θ| ≥ 20°"


def dim_backtrack(params: dict) -> Any:
    nodes = params["path_nodes"]
    return "有折返" if any(nodes[i] == nodes[i + 2] for i in range(len(nodes) - 2)) else "无折返"


def dim_turns(params: dict) -> Any:
    """PatternLock 专用：相邻两步的 8 方位不同即算一次转向。

    这个定义只对 PatternLock 成立——它的 move 是格点上的八方位移动，方向变了就是拐了个弯。
    RouteStick 是在 1×9 一字排开的格点上左右走，没有「转角」这回事，不要把它套过去。
    """
    directions = params["move_directions"]
    return sum(1 for a, b in zip(directions, directions[1:]) if a != b)


def dim_backtracks(params: dict) -> Any:
    """路径原地折返的次数（走到 j 又退回 i）。PatternLock 的 DFS 路径不重复节点，恒为 0。"""
    nodes = params["path_nodes"]
    return sum(1 for i in range(len(nodes) - 2) if nodes[i] == nodes[i + 2])


def dim_actions(params: dict) -> Any:
    """BinFill：要放进 bin 的 cube 总数；PickXtimes：同一个动作重复几次。"""
    return params["actions"]


def dim_color_kinds(params: dict) -> Any:
    """BinFill 的目标里涉及几种颜色（1/2/3）——难度配置直接控制这一项。"""
    return params["color_kinds"]


def dim_cube_color(params: dict) -> Any:
    return params["cube_color"]


def aggregate(
    rows: list[dict], keyfn: Callable[[dict], Any], task: str | None = None
) -> dict[str, dict[Any, tuple[int, int]]]:
    table: dict[str, dict[Any, list[int]]] = {v: defaultdict(lambda: [0, 0]) for v in VARIANTS}
    for row in rows:
        if task is not None and row["task"] != task:
            continue
        cell = table[row["variant"]][keyfn(row["params"])]
        cell[1] += 1
        cell[0] += int(row["success"])
    return {v: {k: tuple(c) for k, c in sorted(d.items(), key=lambda x: str(x[0]))} for v, d in table.items()}


def draw_panel(
    ax,
    agg: dict[str, dict[Any, tuple[int, int]]],
    title: str,
    xlabel: str,
    order: list[Any] | None = None,
) -> None:
    present = {k for d in agg.values() for k in d}
    if order is not None:
        keys = [k for k in order if k in present]
    else:
        keys = sorted(present, key=lambda x: (isinstance(x, str), x))
    width = 0.38
    positions = range(len(keys))
    for offset, variant in zip((-width / 2, width / 2), VARIANTS):
        values, lows, highs, counts = [], [], [], []
        for key in keys:
            succ, total = agg[variant].get(key, (0, 0))
            rate, low, high = wilson(succ, total)
            values.append(rate * 100)
            # Wilson 区间的中心不等于 phat，条形用 phat 时误差臂可能算出负值，钳到 0
            lows.append(max(0.0, rate - low) * 100)
            highs.append(max(0.0, high - rate) * 100)
            counts.append((succ, total))
        xs = [p + offset for p in positions]
        ax.bar(
            xs,
            values,
            width,
            label=VARIANT_LABEL[variant],
            color=COLOR[variant],
            edgecolor="white",
            linewidth=0.6,
        )
        ax.errorbar(
            xs, values, yerr=[lows, highs], fmt="none", ecolor="#444444", elinewidth=0.9, capsize=2.5
        )
        for x, value, (succ, total) in zip(xs, values, counts):
            if not total:
                continue
            if succ:
                ax.text(
                    x, value + 8.5, f"{succ / total:.0%}", ha="center", va="bottom",
                    fontsize=7, fontweight="bold",
                )
            # succ 为 0 时不再标 "0%"：0/9 本身就是 0%，两个变体的标注挨在一起会糊成一团
            ax.text(
                x, value + 2.0, f"{succ}/{total}", ha="center", va="bottom",
                fontsize=5.6, color="#5A6266",
            )
    ax.set_xticks(list(positions))
    ax.set_xticklabels([str(k) for k in keys], fontsize=7.5)
    ax.set_xlabel(xlabel, fontsize=8)
    ax.set_ylabel("成功率 (%)", fontsize=8)
    ax.set_title(title, fontsize=9)
    ax.set_ylim(0, 128)
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)


def figure(specs: list[tuple], out_path: Path, suptitle: str, figsize: tuple) -> None:
    fig, axes = plt.subplots(1, len(specs), figsize=figsize)
    if len(specs) == 1:
        axes = [axes]
    for ax, spec in zip(axes, specs):
        agg, title, xlabel = spec[0], spec[1], spec[2]
        order = spec[3] if len(spec) > 3 else None
        draw_panel(ax, agg, title, xlabel, order)
    for ax in axes:
        ax.tick_params(axis="y", labelsize=7.5)
    axes[0].legend(fontsize=7, loc="upper right", framealpha=0.9)
    fig.suptitle(suptitle, fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"已写出 {out_path}")


def rate(rows: list[dict], **filters: Any) -> tuple[int, int, str]:
    hit = [
        r
        for r in rows
        if all(
            (r[k] in v if isinstance(v, (list, tuple, set)) else r[k] == v) for k, v in filters.items()
        )
    ]
    succ = sum(1 for r in hit for _ in [0] if r["success"])
    total = len(hit)
    pct = f"{succ / total:.1%}" if total else "—"
    return succ, total, pct


def write_section(rows: list[dict], out_path: Path, fig_dir_name: str) -> None:
    """出一段可直接拼进 reports/README.md 的 Markdown：口径 + 表 + 图，不写解读。"""

    def cell(**filters: Any) -> str:
        succ, total, pct = rate(rows, **filters)
        return f"{succ}/{total}（{pct}）"

    lines = [
        "## eval 成功率",
        "",
        "- **数据来源**（只读）：`/data/hongzefu/robomme_policy_learning_MotionJEPA/docs/training-doc/` 下的",
        "  `eval-{medium,hard}-patternlock-routestick/records/{context,modul}/` 与",
        "  `eval-binfill-pickxtimes/records/{hard,medium}/{context,modul}/`（后者难度档在 records 下面一层）。",
        "- **两个变体**：`perceptual-framesamp-modul` 与 `perceptual-framesamp-context`，"
        "同一批 ckpt 79999、同 seed 42。",
        "- **覆盖范围**：每个 `(task, split)` 的 50 条 metadata 是 easy 26 / medium 12 / hard 12，"
        "eval 跑 medium 全 12 条 + hard 全 12 条，**easy 未跑**。每任务 test 24 + val 24 = 48 集，"
        "四任务合计 384 条。",
        "- **分组参数**：PatternLock / RouteStick 由 seed 离线复算；BinFill / PickXtimes 解析 task_goal。",
        "- **误差棒**：Wilson 95% 置信区间。0 成功的格子画成一根从 0 起的竖线（点估计 0，上界不为 0）。",
        "",
        "### 分难度",
        "",
        "每格 24 集（test 12 + val 12），suite 合计每格 48 集。",
        "",
        "| suite | 任务 | 难度 | framesamp-modul | framesamp-context |",
        "| --- | --- | --- | --- | --- |",
    ]
    for suite, tasks in (("Imitation", IMITATION_TASKS), ("Counting", COUNTING_TASKS)):
        for task in tasks:
            for level in DIFFICULTIES_DISPLAY:
                lines.append(
                    f"| {suite} | {task} | {level} | "
                    f"{cell(variant='modul', task=task, difficulty=level)} | "
                    f"{cell(variant='context', task=task, difficulty=level)} |"
                )
        for level in DIFFICULTIES_DISPLAY:
            lines.append(
                f"| **{suite} 合计** | | **{level}** | "
                f"**{cell(variant='modul', task=tasks, difficulty=level)}** | "
                f"**{cell(variant='context', task=tasks, difficulty=level)}** |"
            )

    lines += [
        "",
        "### 成功率 vs 动作次数",
        "",
        f"![Imitation 成功率 vs move 次数]({fig_dir_name}/success_by_moves_imitation.png)",
        "",
        f"![Counting 成功率 vs 动作次数]({fig_dir_name}/success_by_actions_counting.png)",
        "",
        "Imitation 的 x 轴是 move 次数；Counting 的 x 轴是 BinFill 要放进 bin 的 cube 总数 / "
        "PickXtimes 同一动作的重复次数。medium 与 hard 合并。",
        "",
        "### 成功率 vs 路径形状（Imitation）",
        "",
        f"![Imitation 路径形状]({fig_dir_name}/success_by_imitation_turns.png)",
        "",
        "两个任务各用一个语义成立的维度：",
        "",
        "- **PatternLock 转角次数** = 相邻两步的 8 方位不同的次数。它的 move 是格点上的八方位移动，"
        "方向变了就是拐了个弯。",
        "- **RouteStick 折返次数** = 路径里走到 j 又退回 i 的次数。它是在 1×9 一字排开的格点上左右走，"
        "**没有「转角」这回事**；另外「左右切换次数」与折返次数在 100 条上逐条相等（同一件事），故不重复列。",
        "",
        "PatternLock 的路径由 DFS 生成、不重复节点，折返恒为 0，所以它没有折返这一档。",
        "",
        "### 成功率 vs 目标颜色种类数（BinFill）",
        "",
        f"![BinFill 颜色种类数]({fig_dir_name}/success_by_binfill_color.png)",
        "",
        "颜色种类数 = 该 episode 的目标里涉及几种颜色的 cube（1 / 2 / 3）。",
        "",
        "> 图与数字由 `plot_eval_success.py` 生成，改动 eval 结果后重跑即可。",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"已写出 {out_path}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="按动作参数分组画 eval 成功率分布图")
    parser.add_argument("--derived", default=str(HERE / "outputs" / "derived_params.json"))
    parser.add_argument("--out-dir", default=str(HERE / "reports" / "figures"))
    args = parser.parse_args(argv)

    setup_font()
    imitation = load_rows(Path(args.derived))
    counting = load_counting_rows()
    rows = imitation + counting
    print(
        f"Imitation join 成功：{len(imitation)} 条（seed 逐条一致）；"
        f"Counting 装载 {len(counting)} 条；合计 {len(rows)} 条"
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    figure(
        [
            (aggregate(rows, dim_moves, task), f"{task}", "move 次数")
            for task in IMITATION_TASKS
        ],
        out_dir / "success_by_moves_imitation.png",
        "Imitation suite：成功率 vs move 次数（medium + hard 合并，误差棒为 Wilson 95% CI）",
        (6.6, 2.9),
    )

    figure(
        [
            (aggregate(rows, dim_actions, "BinFill"), "BinFill", "要放进 bin 的 cube 总数"),
            (aggregate(rows, dim_actions, "PickXtimes"), "PickXtimes", "同一动作重复次数"),
        ],
        out_dir / "success_by_actions_counting.png",
        "Counting suite：成功率 vs 动作次数（medium + hard 合并，误差棒为 Wilson 95% CI）",
        (6.6, 2.9),
    )

    figure(
        [
            (aggregate(rows, dim_turns, "PatternLock"), "PatternLock：转角次数", "相邻两步方位不同的次数"),
            (aggregate(rows, dim_backtracks, "RouteStick"), "RouteStick：折返次数", "走到 j 又退回 i 的次数"),
        ],
        out_dir / "success_by_imitation_turns.png",
        "Imitation suite：成功率 vs 路径形状",
        (6.6, 2.9),
    )

    figure(
        [
            (
                aggregate(rows, dim_color_kinds, "BinFill"),
                "BinFill：目标涉及几种颜色",
                "颜色种类数",
            ),
        ],
        out_dir / "success_by_binfill_color.png",
        "BinFill：成功率 vs 目标的颜色种类数",
        (3.6, 2.9),
    )

    write_section(rows, Path(args.out_dir).parent / "eval_section.md", Path(args.out_dir).name)

    # 同一份聚合结果导出成 JSON，供交互版 artifact 内联（保证两处数字同源）
    export = {
        "difficulty_table": [
            {
                "suite": suite,
                "task": task,
                "difficulty": level,
                "modul": rate(rows, variant="modul", task=task, difficulty=level)[:2],
                "context": rate(rows, variant="context", task=task, difficulty=level)[:2],
            }
            for suite, tasks in (("Imitation", IMITATION_TASKS), ("Counting", COUNTING_TASKS))
            for task in tasks
            for level in DIFFICULTIES_DISPLAY
        ],
        "suite_totals": [
            {
                "suite": suite,
                "difficulty": level,
                "modul": rate(rows, variant="modul", task=tasks, difficulty=level)[:2],
                "context": rate(rows, variant="context", task=tasks, difficulty=level)[:2],
            }
            for suite, tasks in (("Imitation", IMITATION_TASKS), ("Counting", COUNTING_TASKS))
            for level in DIFFICULTIES_DISPLAY
        ],
        "charts": [
            {
                "id": "moves",
                "title": "成功率 vs move 次数",
                "panels": [
                    {"task": t, "xlabel": "move 次数", "data": aggregate(rows, dim_moves, t)}
                    for t in IMITATION_TASKS
                ],
            },
            {
                "id": "actions",
                "title": "成功率 vs 动作次数",
                "panels": [
                    {"task": "BinFill", "xlabel": "要放进 bin 的 cube 总数",
                     "data": aggregate(rows, dim_actions, "BinFill")},
                    {"task": "PickXtimes", "xlabel": "同一动作重复次数",
                     "data": aggregate(rows, dim_actions, "PickXtimes")},
                ],
            },
            {
                "id": "turns",
                "title": "成功率 vs 路径形状",
                "panels": [
                    {"task": "PatternLock", "xlabel": "转角次数（相邻两步方位不同）",
                     "data": aggregate(rows, dim_turns, "PatternLock")},
                    {"task": "RouteStick", "xlabel": "折返次数（走到 j 又退回 i）",
                     "data": aggregate(rows, dim_backtracks, "RouteStick")},
                ],
            },
            {
                "id": "color",
                "title": "成功率 vs 目标颜色种类数",
                "panels": [
                    {"task": "BinFill", "xlabel": "颜色种类数",
                     "data": aggregate(rows, dim_color_kinds, "BinFill")},
                ],
            },
        ],
    }
    export_path = Path(args.out_dir).parents[1] / "outputs" / "eval_aggregate.json"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(
        json.dumps(export, ensure_ascii=False, default=lambda o: list(o) if isinstance(o, tuple) else o),
        encoding="utf-8",
    )
    print(f"已写出 {export_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
