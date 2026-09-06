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
TASKS = ["PatternLock", "RouteStick"]


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

    def moves_cell(task: str, variant: str, moves: list[int]) -> str:
        hit = [r for r in rows if r["task"] == task and r["variant"] == variant and r["params"]["moves"] in moves]
        succ = sum(1 for r in hit if r["success"])
        pct = f"{succ / len(hit):.0%}" if hit else "—"
        return f"{succ}/{len(hit)}（{pct}）"

    lines = [
        "## 这些参数怎么影响策略成功率",
        "",
        "把 policy 侧两轮 eval 的逐集结果按上面复算出的动作参数分组，就能看出成功率随哪些参数塌陷。",
        "",
        "- **数据来源**：`/data/hongzefu/robomme_policy_learning_MotionJEPA/docs/training-doc/"
        "eval-{medium,hard}-patternlock-routestick/records/{context,modul}/per_episode.json`（只读）。",
        "- **两个变体**：framesample 的官方两档 —— `perceptual-framesamp-modul`（上游脚本默认）与 "
        "`perceptual-framesamp-context`（本基准原先锁死的那个）。",
        "- **范围**：medium 与 hard 两档 × 两变体 × 48 集 = 192 条，"
        "join 键是 `(task, split, episode)`，并逐条断言 seed 与本目录复算表相同。easy 档尚未评测。",
        "- **误差棒**：Wilson 95% 置信区间。每格只有个位数到十几条样本，"
        "0 成功的格子画出来是一根从 0 起的竖线（点估计 0，上界不为 0），不是缺数据。",
        "",
        "### 总体",
        "",
        "| 变体 | PatternLock | RouteStick | 合计 |",
        "| --- | --- | --- | --- |",
    ]
    for variant in VARIANTS:
        lines.append(
            f"| {VARIANT_LABEL[variant]} | {cell(variant=variant, task='PatternLock')} | "
            f"{cell(variant=variant, task='RouteStick')} | {cell(variant=variant)} |"
        )

    lines += [
        "",
        "### 成功率 vs move 次数",
        "",
        f"![成功率 vs move 次数]({fig_dir_name}/success_by_moves.png)",
        "",
        "这是最陡的一条趋势，两个任务都随 move 次数上行而塌陷（不是严格单调："
        "PatternLock 的 2 次与 3 次基本持平，RouteStick 的 6 次那格只有 3 条样本、置信区间几乎覆盖满量程）：",
        "",
        f"- PatternLock（modul）：2~3 次 move {moves_cell('PatternLock', 'modul', [2, 3])}，"
        f"4 次掉到 {moves_cell('PatternLock', 'modul', [4])}，**5 次及以上 "
        f"{moves_cell('PatternLock', 'modul', [5, 6, 7])}**。",
        f"- RouteStick（modul）：4 次 {moves_cell('RouteStick', 'modul', [4])}，"
        f"5 次 {moves_cell('RouteStick', 'modul', [5])}，"
        f"6 次 {moves_cell('RouteStick', 'modul', [6])}（样本仅 3 条，不足以判读），"
        f"7 次 {moves_cell('RouteStick', 'modul', [7])}。",
        "",
        "换句话说，两个策略的能力边界都卡在「一条轨迹里要连续做对几步」上——"
        "而 move 次数正是 env 按难度直接配出来的（见上面的按难度分组），所以难度档之间的差距"
        "本质上就是这条曲线的不同区段。",
        "",
        "### 成功率 vs 难度档",
        "",
        f"![成功率 vs 难度档]({fig_dir_name}/success_by_difficulty.png)",
        "",
        f"modul 在 medium 上 {cell(variant='modul', difficulty='medium')}，"
        f"到 hard 掉成 {cell(variant='modul', difficulty='hard')}；"
        f"context 两档分别是 {cell(variant='context', difficulty='medium')} 与 "
        f"{cell(variant='context', difficulty='hard')}。",
        "",
        "### PatternLock：路径布局",
        "",
        f"![PatternLock 路径布局]({fig_dir_name}/success_by_patternlock_layout.png)",
        "",
        "- **方向种类数**（这条路径用到几种不同的移动方向）比 move 次数更能区分难易：只用 2 种方向时"
        "成功率最高，用到 4 种以上基本归零。它和 move 次数不完全重合——"
        "同样 4 步，走「一直向右」和「右、前右、左、前左」的难度不一样。",
        "- **起终点跨度**（曼哈顿格距）影响温和，跨 1~3 格差别不大，跨 5 格以上没有成功样本。",
        "- **起点位置**：起点在格边上时成功率明显高于落在格点内部——内部起点四周八向都通，"
        "更容易在第一步就走错方向。注意这一项与格点尺寸耦合（3×3 几乎没有内部点），",
        "  样本上主要反映的是 medium/hard 的差异。",
        "",
        "### RouteStick：路径布局",
        "",
        f"![RouteStick 路径布局]({fig_dir_name}/success_by_routestick_layout.png)",
        "",
        "- **绕行方向切换次数**：切换 0~3 次时成功率相当（30%~50%），切到 4 次以上全灭——"
        "同样是「连续做对几步」的表现。",
        "- **整排旋转角 |θ|**：中间档（10°~20°）反而最高，两端都低，且各档只有 16 条样本、"
        "置信区间大幅重叠，**不足以支持「旋转角影响成功率」的结论**。",
        "- **是否原地折返**：有无折返差别不大（折返只在 hard 档允许）。",
        "",
        "### split 对照",
        "",
        f"![成功率 vs split]({fig_dir_name}/success_by_split.png)",
        "",
        "test 与 val 的成功率接近，没有明显的 split 偏置——两个 split 的参数分布本来就同源"
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
    rows = load_rows(Path(args.derived))
    print(f"join 成功：{len(rows)} 条（2 难度 × 2 变体 × 48 集），seed 逐条一致")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    figure(
        [
            (aggregate(rows, dim_moves, task), f"{task}", "move 次数")
            for task in TASKS
        ],
        out_dir / "success_by_moves.png",
        "成功率 vs move 次数（medium + hard 合并，误差棒为 Wilson 95% CI）",
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
        "成功率 vs 难度档",
        (9, 4.2),
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
        (9, 4.2),
    )

    write_section(rows, Path(args.out_dir).parent / "eval_section.md", Path(args.out_dir).name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
