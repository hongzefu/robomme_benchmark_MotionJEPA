"""画采样窗口时序数轴：每任务每难度的最短 / 中位 / 最长三条 episode。

一行 = 一条 episode 的完整时间轴，从上到下叠四层信息：

1. **段底色**：demo 段与 exec 段（Counting 无 demo 段，整条都是 exec）；
2. **subgoal 分段**：交替深浅块 + 边界线，块内写压缩后的中文短标签；
3. **motion 窗口**：窗口 `[f, f+32]`、stride 16、**不跨段**，每段各自从段起点铺。
   画法上每个窗口只占它 stride 宽（16 帧）的一格、格间留白，所以**格子数就是窗口数、可以直接数**；
   窗口的真实跨度（33 帧、相邻重叠一半）另用一条细线示意。段短于 33 帧铺不出窗口，画成虚线空槽；
4. **帧路**：上排 32 帧预算的采样点（细竖线），下排 8 帧预算（圆点），Δ = (T-1)/(N-1)。

口径与 policy 侧 motion_store / even_sampling_indices 对齐，已用其 16 任务中位集逐条验证。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
TASKS = ["PatternLock", "RouteStick", "BinFill", "PickXtimes"]
DIFFICULTIES = ["easy", "medium", "hard"]
WINDOW_FRAMES = 33
WINDOW_STRIDE = 16
FRAME_BUDGETS = [32, 8]

COLOR = {
    "demo": "#3E8FAE",
    "exec": "#5FA98D",
    "frame32": "#8B85D9",
    "frame8": "#C4553D",
    "sg_a": "#D8DEE2",
    "sg_b": "#EDF1F3",
    "sg_line": "#9AA6AC",
    "empty": "#C9713D",
}

# subgoal 原文 → 中文短标签。顺序敏感：先匹配更具体的句式。
LABEL_RULES: list[tuple[str, str]] = [
    (r"^move to the nearest (left|right) target.*(counterclockwise)$", "绕{0}逆"),
    (r"^move to the nearest (left|right) target.*(clockwise)$", "绕{0}顺"),
    (r"^move (backward-left|backward-right|forward-left|forward-right|backward|forward|left|right)$", "移{0}"),
    (r"^pick up the (\w+) (red|blue|green) cube$", "抓{1}{0}"),
    (r"^pick up the (red|blue|green) cube for the (\w+) time$", "抓{0}{1}"),
    (r"^put it into the bin$", "投箱"),
    (r"^place the (red|blue|green) cube onto the target$", "置{0}标"),
    (r"^press the button to stop$", "按钮停"),
    (r"^press the button$", "按钮"),
    (r"^All tasks completed$", "完成"),
]
ORDINAL = {
    "first": "1", "second": "2", "third": "3", "fourth": "4",
    "fifth": "5", "sixth": "6", "seventh": "7",
}
DIRECTION = {
    "backward-left": "后左", "backward-right": "后右", "forward-left": "前左",
    "forward-right": "前右", "backward": "后", "forward": "前", "left": "左", "right": "右",
}
COLOR_CN = {"red": "红", "blue": "蓝", "green": "绿"}


def short_label(text: str) -> str:
    """把 subgoal 原文压成 2~4 个字，画在窗口带里。匹配不到就退回截断的原文。"""
    for pattern, template in LABEL_RULES:
        match = re.match(pattern, text, re.I)
        if not match:
            continue
        parts = [
            DIRECTION.get(g, ORDINAL.get(g, COLOR_CN.get(g, g))) if g else ""
            for g in match.groups()
        ]
        return template.format(*parts) if parts else template
    return text[:6]


def setup_font() -> None:
    """系统 CJK 字体是 .ttc，matplotlib 默认不索引，必须显式 addfont 注册。"""
    for path in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    ):
        if Path(path).exists():
            try:
                font_manager.fontManager.addfont(path)
            except Exception:  # noqa: BLE001
                continue
    for name in ("Noto Sans CJK JP", "Noto Sans CJK SC", "Noto Serif CJK JP"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def seg_windows(seg_len: int) -> list[int]:
    """一段内窗口的起点（段内相对坐标）。"""
    return list(range(0, max(0, seg_len - (WINDOW_FRAMES - 1)), WINDOW_STRIDE))


def frame_indices(total: int, budget: int) -> list[int]:
    """linspace(0, t, N) 取整，t = T-1。"""
    t = total - 1
    if budget <= 1:
        return [0]
    return [round(i * t / (budget - 1)) for i in range(budget)]


def load_episodes(paths: dict[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for kind, files in paths.items():
        for file in files:
            payload = json.loads(Path(file).read_text(encoding="utf-8"))
            for key, rows in payload.items():
                task, _, split = key.partition("-")
                for episode, row in rows.items():
                    segments = row["segments"]
                    demo = (
                        sum(row["demo_durations"]) if kind == "imitation" else 0
                    )
                    out.setdefault(task, []).append(
                        {
                            "task": task,
                            "split": split,
                            "episode": int(episode),
                            "seed": row["seed"],
                            "difficulty": row["difficulty"],
                            "total": row["n_timesteps_total"],
                            "demo": demo,
                            "segments": [
                                {
                                    "start": s["start_timestep"],
                                    "len": s["n_timesteps"],
                                    "text": s["subgoal"],
                                }
                                for s in segments
                            ],
                        }
                    )
    return out


def pick_rows(episodes: list[dict[str, Any]]) -> list[tuple[str, str, dict[str, Any]]]:
    """每难度按整条长度取最短 / 中位 / 最长。"""
    picked: list[tuple[str, str, dict[str, Any]]] = []
    for level in DIFFICULTIES:
        group = sorted(
            [e for e in episodes if e["difficulty"] == level], key=lambda e: e["total"]
        )
        if not group:
            continue
        for label, item in (
            ("最短", group[0]),
            ("中位", group[len(group) // 2]),
            ("最长", group[-1]),
        ):
            picked.append((level, label, item))
    return picked


def draw_row(ax, y: float, item: dict[str, Any], xmax: int) -> None:
    total, demo = item["total"], item["demo"]
    segments = [(0, demo, "demo"), (demo, total - demo, "exec")] if demo else [(0, total, "exec")]

    # 1) 段底色
    for start, length, kind in segments:
        if length <= 0:
            continue
        ax.add_patch(
            Rectangle((start, y - 0.30), length, 0.63, facecolor=COLOR[kind], alpha=0.10, lw=0)
        )
        ax.plot([start, start], [y - 0.30, y + 0.33], color=COLOR[kind], lw=1.0)

    # 2) subgoal 分段
    for index, seg in enumerate(item["segments"]):
        ax.add_patch(
            Rectangle(
                (seg["start"], y - 0.30),
                seg["len"],
                0.20,
                facecolor=COLOR["sg_a"] if index % 2 == 0 else COLOR["sg_b"],
                edgecolor=COLOR["sg_line"],
                lw=0.35,
            )
        )
        if seg["len"] / xmax > 0.045:
            ax.text(
                seg["start"] + seg["len"] / 2,
                y - 0.20,
                short_label(seg["text"]),
                ha="center",
                va="center",
                fontsize=5.2,
                color="#3A4247",
            )

    # 3) motion 窗口：每段各自铺。窗口长 33、stride 16，相邻重叠一半——
    #    若按 33 帧全宽画，相邻窗口首尾相接会糊成一条实线、数不出个数。
    #    所以每个窗口只画它 stride 宽（16 帧）的那一格，格间留白：格子数 == 窗口数，可以直接数。
    #    窗口的真实跨度另用一条细线示意（见图例）。
    for start, length, kind in segments:
        starts = seg_windows(length)
        if not starts:
            ax.add_patch(
                Rectangle(
                    (start, y + 0.10),
                    max(length, 1),
                    0.10,
                    facecolor="none",
                    edgecolor=COLOR["empty"],
                    lw=0.6,
                    ls=(0, (2, 1.6)),
                )
            )
            continue
        gap = max(xmax * 0.0012, 0.6)
        for offset in starts:
            ax.add_patch(
                Rectangle(
                    (start + offset + gap / 2, y + 0.105),
                    WINDOW_STRIDE - gap,
                    0.075,
                    facecolor=COLOR[kind],
                    alpha=0.85,
                    lw=0,
                )
            )
        # 首个窗口的真实跨度（33 帧）示意线，说明格子之间是重叠的
        ax.plot(
            [start + starts[0], start + starts[0] + WINDOW_FRAMES - 1],
            [y + 0.196, y + 0.196],
            color=COLOR[kind],
            lw=0.7,
            solid_capstyle="butt",
        )

    # 4) 帧路：32 帧竖线（上）、8 帧圆点（下）
    for index in frame_indices(total, 32):
        ax.plot([index, index], [y + 0.245, y + 0.325], color=COLOR["frame32"], lw=0.5, alpha=0.85)
    ax.plot(
        frame_indices(total, 8),
        [y + 0.052] * 8,
        "o",
        ms=1.9,
        color=COLOR["frame8"],
        zorder=3,
    )


def plot_task(task: str, episodes: list[dict[str, Any]], out_path: Path) -> None:
    picked = pick_rows(episodes)
    xmax = max(item["total"] for _, _, item in picked)
    fig, ax = plt.subplots(figsize=(11, 0.62 * len(picked) + 1.5))

    for row_index, (level, label, item) in enumerate(picked):
        y = len(picked) - row_index
        draw_row(ax, y, item, xmax)
        demo_w = len(seg_windows(item["demo"]))
        exec_w = len(seg_windows(item["total"] - item["demo"]))
        ax.text(
            -xmax * 0.012,
            y,
            f"{level}·{label}",
            ha="right",
            va="center",
            fontsize=6.8,
        )
        ax.text(
            xmax * 1.012,
            y,
            f"{item['split']}-ep{item['episode']}  T={item['total']}  "
            f"窗口 {demo_w}+{exec_w}={demo_w + exec_w}  "
            f"Δ32={(item['total'] - 1) / 31:.1f}  Δ8={(item['total'] - 1) / 7:.1f}",
            ha="left",
            va="center",
            fontsize=6.0,
            color="#4A5257",
        )

    ax.set_xlim(0, xmax)
    ax.set_ylim(0.4, len(picked) + 0.75)
    ax.set_yticks([])
    ax.set_xlabel("timestep（1 ts = 1 个 env step = 0.05 s）", fontsize=8)
    ax.tick_params(axis="x", labelsize=7.5)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.set_title(
        f"{task}：采样窗口时序数轴（窗口 [f, f+{WINDOW_FRAMES - 1}]、stride {WINDOW_STRIDE}、不跨段）",
        fontsize=10,
    )

    handles = [
        Rectangle((0, 0), 1, 1, facecolor=COLOR["demo"], alpha=0.85, label="demo 段：每格 = 1 个窗口"),
        Rectangle((0, 0), 1, 1, facecolor=COLOR["exec"], alpha=0.85, label="exec 段：每格 = 1 个窗口"),
        plt.Line2D([], [], color="#666B6E", lw=1.0, label=f"首窗真实跨度 {WINDOW_FRAMES} 帧（相邻重叠 {WINDOW_STRIDE}）"),
        Rectangle((0, 0), 1, 1, facecolor=COLOR["sg_a"], edgecolor=COLOR["sg_line"], label="subgoal 分段"),
        Rectangle((0, 0), 1, 1, facecolor="none", edgecolor=COLOR["empty"], ls=(0, (2, 1.6)),
                  label=f"段 < {WINDOW_FRAMES} 帧，无窗口"),
        plt.Line2D([], [], color=COLOR["frame32"], lw=1.0, label="帧路 N=32"),
        plt.Line2D([], [], color=COLOR["frame8"], marker="o", ms=3, lw=0, label="帧路 N=8"),
    ]
    ax.legend(
        handles=handles,
        fontsize=6.4,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.30 / (0.62 * len(picked) + 1.5) * 4),
        ncol=4,
        frameon=False,
    )
    fig.subplots_adjust(left=0.085, right=0.735, top=0.90, bottom=0.16)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"已写出 {out_path}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="画采样窗口时序数轴")
    parser.add_argument("--imitation", action="append", required=True, help="durations_*.json")
    parser.add_argument("--counting", action="append", required=True, help="counting_params_*.json")
    parser.add_argument("--out-dir", default=str(HERE / "reports" / "figures"))
    args = parser.parse_args(argv)

    setup_font()
    episodes = load_episodes({"imitation": args.imitation, "counting": args.counting})
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for task in TASKS:
        if task in episodes:
            plot_task(task, episodes[task], out_dir / f"sampling_{task}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
