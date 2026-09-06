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
            if total:
                ax.text(x, value + 2.5, f"{succ}/{total}", ha="center", va="bottom", fontsize=7.5)
    ax.set_xticks(list(positions))
    ax.set_xticklabels([str(k) for k in keys], fontsize=9)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel("成功率 (%)", fontsize=9)
    ax.set_title(title, fontsize=10.5)
    ax.set_ylim(0, 118)
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
    axes[0].legend(fontsize=8.5, loc="upper right", framealpha=0.9)
    fig.suptitle(suptitle, fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out_path, dpi=160)
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
    """出一段可直接拼进 reports/README.md 的 Markdown（图 + 基于实测数字的解读）。"""

    def cell(**filters: Any) -> str:
        succ, total, pct = rate(rows, **filters)
        return f"{succ}/{total}（{pct}）"

    def bucket(task: str, variant: str, values: list[Any], dim: str = "actions") -> str:
        hit = [
            r
            for r in rows
            if r["task"] == task and r["variant"] == variant and r["params"].get(dim) in values
        ]
        succ = sum(1 for r in hit if r["success"])
        pct = f"{succ / len(hit):.0%}" if hit else "—"
        return f"{succ}/{len(hit)}（{pct}）"

    def moves_cell(task: str, variant: str, moves: list[int]) -> str:
        return bucket(task, variant, moves, dim="moves")

    lines = [
        "## 这些参数怎么影响策略成功率",
        "",
        "把 policy 侧三轮 eval 的逐集结果按动作参数分组，就能看出成功率随哪些参数塌陷。",
        "",
        "- **数据来源**（只读）：`/data/hongzefu/robomme_policy_learning_MotionJEPA/docs/training-doc/` 下的",
        "  `eval-{medium,hard}-patternlock-routestick/records/{context,modul}/` 与",
        "  `eval-binfill-pickxtimes/records/{hard,medium}/{context,modul}/`（后者难度档在 records 下面一层）。",
        "- **两个变体**：framesample 的官方两档 —— `perceptual-framesamp-modul`（上游脚本默认）与",
        "  `perceptual-framesamp-context`（本基准原先锁死的那个）。三轮同一批 ckpt 79999、同 seed 42，",
        "  policy 侧已用 `PARAM_TREE_EXACT=PASS n_model=61 n_ckpt=61` 证明权重同一。",
        "- **覆盖范围**：四个任务完全相同 —— 每个 `(task, split)` 的 50 条 metadata 是 easy 26 / medium 12 / hard 12，",
        "  eval 跑的是 **medium 全 12 条 + hard 全 12 条**（各难度跑满全集，不是抽样），**easy 26 条一条未跑**。",
        "  每任务 test 24 + val 24 = 48 集，四任务合计 384 条（2 变体 × 2 难度 × 96）。",
        "- **参数从哪来**：PatternLock / RouteStick 用 seed 离线复算（见上文）；",
        "  BinFill / PickXtimes 直接解析 eval 记录里的 task_goal（要放几个什么颜色的 cube、重复几次），",
        "  该解析已用 val 侧 h5 的 `setup/task_goal` 逐条校验，48/48 相同。",
        "- **误差棒**：Wilson 95% 置信区间。每格只有个位数到十几条样本，",
        "  0 成功的格子画出来是一根从 0 起的竖线（点估计 0，上界不为 0），不是缺数据。",
        "",
        "### 总体",
        "",
        "| suite | 任务 | framesamp-modul | framesamp-context |",
        "| --- | --- | --- | --- |",
    ]
    for suite, tasks in (("Imitation", IMITATION_TASKS), ("Counting", COUNTING_TASKS)):
        for task in tasks:
            lines.append(
                f"| {suite} | {task} | {cell(variant='modul', task=task)} | {cell(variant='context', task=task)} |"
            )
        lines.append(
            f"| **{suite} 合计** | | **{cell(variant='modul', task=tasks)}** | **{cell(variant='context', task=tasks)}** |"
        )

    lines += [
        "",
        "**最重要的一点：变体差异是逐任务的，不是全局的。** BinFill 上两个变体统计上毫无差异",
        "（policy 侧 result.md 的任务级 Fisher 单尾 p，hard 与 medium 两档**均为 0.50**），",
        "而 PickXtimes 上差距悬殊。把两个任务平均成一个 suite 数字会把这个结构完全抹掉。",
        "",
        "### Imitation suite：成功率 vs move 次数",
        "",
        f"![Imitation 成功率 vs move 次数]({fig_dir_name}/success_by_moves_imitation.png)",
        "",
        "两个任务都随 move 次数上行而塌陷（不是严格单调：PatternLock 的 2 次与 3 次基本持平，",
        "RouteStick 的 6 次那格只有 3 条样本、置信区间几乎覆盖满量程）：",
        "",
        f"- PatternLock（modul）：2~3 次 move {moves_cell('PatternLock', 'modul', [2, 3])}，"
        f"4 次掉到 {moves_cell('PatternLock', 'modul', [4])}，**5 次及以上 "
        f"{moves_cell('PatternLock', 'modul', [5, 6, 7])}**。",
        f"- RouteStick（modul）：4 次 {moves_cell('RouteStick', 'modul', [4])}，"
        f"5 次 {moves_cell('RouteStick', 'modul', [5])}，"
        f"6 次 {moves_cell('RouteStick', 'modul', [6])}（样本仅 3 条，不足以判读），"
        f"7 次 {moves_cell('RouteStick', 'modul', [7])}。",
        "",
        "context 在这两个任务上几乎全零，没有可读的趋势。",
        "",
        "### Counting suite：成功率 vs 动作次数",
        "",
        f"![Counting 成功率 vs 动作次数]({fig_dir_name}/success_by_actions_counting.png)",
        "",
        "**这张图是两个变体最锋利的分界，而且两个任务的形状完全不同：**",
        "",
        f"- **BinFill**：两条曲线几乎重合 —— 放 2 个 cube 时 modul {bucket('BinFill', 'modul', [2])}、"
        f"context {bucket('BinFill', 'context', [2])}（完全相同）；放 3 个就双双跌到 "
        f"{bucket('BinFill', 'modul', [3])} 与 {bucket('BinFill', 'context', [3])}；"
        f"4~5 个时 modul {bucket('BinFill', 'modul', [4, 5])}、context {bucket('BinFill', 'context', [4, 5])}。"
        "**两个变体在这个任务上是同一条曲线**，瓶颈是任务本身而不是 framesample 策略。",
        f"- **PickXtimes**：modul 几乎不随次数下降 —— 1 次 {bucket('PickXtimes', 'modul', [1])}、"
        f"3 次 {bucket('PickXtimes', 'modul', [3])}、4~5 次 {bucket('PickXtimes', 'modul', [4, 5])}；"
        f"而 context 随次数一路塌陷 —— 1 次 {bucket('PickXtimes', 'context', [1])}、"
        f"3 次 {bucket('PickXtimes', 'context', [3])}、4~5 次 {bucket('PickXtimes', 'context', [4, 5])}。"
        "**次数越多，两者差距越大**：这正是「要记住自己已经搬了几次」的能力差异。",
        "",
        "（PickXtimes modul 在 2 次那格反而低于 1 次和 3 次，只有 8 条样本，置信区间与两侧大幅重叠，不构成反例。）",
        "",
        "### Counting suite：场景布局",
        "",
        f"![Counting 场景布局]({fig_dir_name}/success_by_counting_layout.png)",
        "",
        f"- **BinFill 的颜色种类数**比 cube 总数更能说明问题：目标只涉及 1 种颜色时两变体都是 "
        f"{bucket('BinFill', 'modul', [1], dim='color_kinds')}；涉及 2 种时 modul "
        f"{bucket('BinFill', 'modul', [2], dim='color_kinds')}、context "
        f"{bucket('BinFill', 'context', [2], dim='color_kinds')}；3 种时两者都是 "
        f"{bucket('BinFill', 'modul', [3], dim='color_kinds')}。"
        "要同时按颜色分类并计数，两个变体都做不到。",
        "- **PickXtimes 的 cube 颜色**没有信号（三种颜色成功率相当），这正是想要的对照结果 ——"
        "  差异来自次数而不是颜色。",
        "",
        "> 顺带一个 env 配置层面的注意点：PickXtimes 的 medium 与 easy 的重复次数范围相同（都是 1~3 次），",
        "> medium 的难点在于场上同时有 3 种颜色的 cube 作干扰，而不是次数更多；hard 才是 4~5 次。",
        "> 所以 PickXtimes 的难度档之间不能只按「次数」理解。",
        "",
        "### 成功率 vs 难度档",
        "",
        f"![成功率 vs 难度档]({fig_dir_name}/success_by_difficulty.png)",
        "",
        "难度效应（medium 比 hard 好多少）是判断模型是否真在工作的关键量：",
        "",
        f"- Imitation：modul {cell(variant='modul', task=IMITATION_TASKS, difficulty='medium')} vs "
        f"{cell(variant='modul', task=IMITATION_TASKS, difficulty='hard')}；"
        f"context {cell(variant='context', task=IMITATION_TASKS, difficulty='medium')} vs "
        f"{cell(variant='context', task=IMITATION_TASKS, difficulty='hard')}。",
        f"- Counting：modul {cell(variant='modul', task=COUNTING_TASKS, difficulty='medium')} vs "
        f"{cell(variant='modul', task=COUNTING_TASKS, difficulty='hard')}；"
        f"context {cell(variant='context', task=COUNTING_TASKS, difficulty='medium')} vs "
        f"{cell(variant='context', task=COUNTING_TASKS, difficulty='hard')}。",
        "",
        "policy 侧 result.md 对这八组做了 Fisher 检验：**四组里唯有 context-on-Imitation 失去了难度效应**",
        "（p = 0.247，不显著），其余三组降低难度都带来显著提升。所以 context 的问题是",
        "**在 Imitation suite 上失灵**，而不是普遍能力弱 —— 同一份权重在 Counting 的 medium 档达 43.75%，",
        "与 modul 在 Imitation medium 的 47.92% 相当。",
        "",
        "### split 对照",
        "",
        f"![成功率 vs split]({fig_dir_name}/success_by_split.png)",
        "",
        "四个任务的 test 与 val 都接近，没有明显的 split 偏置 —— 两个 split 的参数分布本来就同源",
        "（同一套难度循环、只是 seed 域不同），这张图是用来确认这一点的。",
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
        (11, 4.2),
    )

    figure(
        [
            (aggregate(rows, dim_actions, "BinFill"), "BinFill", "要放进 bin 的 cube 总数"),
            (aggregate(rows, dim_actions, "PickXtimes"), "PickXtimes", "同一动作重复次数"),
        ],
        out_dir / "success_by_actions_counting.png",
        "Counting suite：成功率 vs 动作次数（medium + hard 合并，误差棒为 Wilson 95% CI）",
        (11, 4.2),
    )

    figure(
        [
            (aggregate(rows, dim_color_kinds, "BinFill"), "BinFill：目标涉及几种颜色", "颜色种类数"),
            (
                aggregate(rows, dim_cube_color, "PickXtimes"),
                "PickXtimes：要反复搬的 cube 颜色",
                "cube 颜色",
                ["red", "blue", "green"],
            ),
        ],
        out_dir / "success_by_counting_layout.png",
        "Counting suite：成功率 vs 场景布局",
        (11, 4.2),
    )

    figure(
        [
            (
                {
                    v: {
                        d: (
                            sum(1 for r in rows if r["variant"] == v and r["task"] == task and r["difficulty"] == d and r["success"]),
                            sum(1 for r in rows if r["variant"] == v and r["task"] == task and r["difficulty"] == d),
                        )
                        for d in DIFFICULTIES
                    }
                    for v in VARIANTS
                },
                task,
                "难度档",
            )
            for task in TASKS
        ],
        out_dir / "success_by_difficulty.png",
        "成功率 vs 难度档（四个任务；easy 档未评测）",
        (17, 4.2),
    )

    figure(
        [
            (aggregate(rows, dim_direction_kinds, "PatternLock"), "路径用到几种方向", "方向种类数"),
            (aggregate(rows, dim_span, "PatternLock"), "起终点跨了多远", "曼哈顿格距"),
            (
                aggregate(rows, dim_start_position, "PatternLock"),
                "起点落在格点哪里",
                "起点位置",
                ["角", "边", "内部"],
            ),
        ],
        out_dir / "success_by_patternlock_layout.png",
        "PatternLock：成功率 vs 路径布局",
        (14, 4.2),
    )

    figure(
        [
            (aggregate(rows, dim_swing_switch, "RouteStick"), "绕行方向换了几次", "顺/逆时针切换次数"),
            (
                aggregate(rows, dim_theta, "RouteStick"),
                "整排旋转角",
                "|θ|",
                ["|θ| < 10°", "10° ≤ |θ| < 20°", "|θ| ≥ 20°"],
            ),
            (
                aggregate(rows, dim_backtrack, "RouteStick"),
                "路径是否原地折返",
                "",
                ["无折返", "有折返"],
            ),
        ],
        out_dir / "success_by_routestick_layout.png",
        "RouteStick：成功率 vs 路径布局",
        (14, 4.2),
    )

    figure(
        [
            (
                {
                    v: {
                        s: (
                            sum(1 for r in rows if r["variant"] == v and r["task"] == task and r["split"] == s and r["success"]),
                            sum(1 for r in rows if r["variant"] == v and r["task"] == task and r["split"] == s),
                        )
                        for s in ("test", "val")
                    }
                    for v in VARIANTS
                },
                task,
                "split",
            )
            for task in TASKS
        ],
        out_dir / "success_by_split.png",
        "成功率 vs split（检查是否存在 split 偏置）",
        (17, 4.2),
    )

    write_section(rows, Path(args.out_dir).parent / "eval_section.md", Path(args.out_dir).name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
