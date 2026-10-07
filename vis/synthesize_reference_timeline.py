"""合成 xhard1 参考数轴：用官方 hard 数据按 subgoal 段「复制粘贴」拼出 xhard1 的参考时间轴并出图。

不跑仿真、不改源码，只读 /data/hongzefu/data_0226/ 里 16 任务的 hard episode（每任务 25 条，
Unmask 系 h5 只有 ep0–99 所以也是 25 条）。每个任务的「重复单元」按 1006-xhard12-env-plan.md
第一部分四节的 xhard1 取值复制若干份（复制的是同一条 episode 自己的段，循环取），其余段原样保留，
拼成一条合成时间轴。合成结果与真实 xhard 的差别只在段长的随机波动与 planner 路径差异，作为参考。

出图口径复用 scripts/patternlock-routestick-params/plot_sampling_windows.py：demo / exec 分段、
stride-16 不跨段的 33 帧窗口（3 行堆叠防粘连）、32 帧与 8 帧帧路。每任务一张图：按合成 T 取
最短 / 中位 / 最长三条，每条画两行——上行官方 hard 原样、下行 xhard1 合成。

用法：
  uv run --no-sync python vis/synthesize_reference_timeline.py \
      --h5-dir /data/hongzefu/data_0226 --metadata-dir src/robomme/env_metadata/train --out vis/output
判定行：XHARD_REF=INFO tasks=<n> episodes=<n> synthetic=1
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any

import h5py

REPO_ROOT = Path(__file__).resolve().parents[1]
PLOT_MODULE = REPO_ROOT / "scripts" / "patternlock-routestick-params" / "plot_sampling_windows.py"

TAIL = "All tasks completed"

# 纳入 xhard1 的 11 个任务及其合成规则参数（取值与计划第一部分四节一致）
RULES: dict[str, dict[str, Any]] = {
    "PickXtimes": {"kind": "pairs_exec", "pick": r"^pick up the \w+ cube for the \w+ time$",
                   "place": r"^place the \w+ cube onto the target$", "extra": [2], "note": "次数 [4,5] → [6,7]"},
    "SwingXtimes": {"kind": "pairs_exec", "pick": r"^move to the top of the right-side target",
                    "place": r"^move to the top of the left-side target", "target": [7, 8], "note": "摆动 3 → [7,8]"},
    "BinFill": {"kind": "pairs_exec", "pick": r"^pick up the \w+ \w+ cube$", "place": r"^put it into the bin$",
                "target": [5, 6], "note": "投入 [3,5] → [5,6]"},
    "VideoRepick": {"kind": "pairs_exec", "pick": r"^pick up the correct cube for the \w+ time$",
                    "place": r"^put it down$", "target": [4, 5], "note": "重抓 [1,3] → [4,5]"},
    "PickHighlight": {"kind": "pairs_exec_lastpick", "pick": r"^pick up the \w+ highlighted cube",
                      "place": r"^place the cube onto the table$", "target": [5], "note": "高亮块 3 → 5"},
    "VideoPlaceOrder": {"kind": "pairs_demo", "pick": r"^pick up the cube$", "place": r"^drop the cube onto target$",
                        "target": [4], "note": "演示放台 [2,4] → 4"},
    "PatternLock": {"kind": "moves_both", "move": r"^move ", "target": [10, 11, 12, 13, 14], "note": "节点 [4,8] → [10,14]"},
    "RouteStick": {"kind": "moves_both", "move": r"^move to the nearest ", "target": [8, 9, 10], "note": "段数 [4,7] → [8,10]"},
    "StopCube": {"kind": "stopcube", "target": [8, 9, 10], "interval": 120, "note": "停止序号 [2,5] → [8,10]，间隔钉 120"},
    "VideoUnmaskSwap": {"kind": "demo_static", "target": [4, 5], "note": "swap [2,3] → [4,5]，demo static 每次 +50"},
    "ButtonUnmaskSwap": {"kind": "unchanged", "note": "swap [2,3] → [4,5]，交换与按钮并行、时长基本不变"},
    "VideoUnmask": {"kind": "unmask_pick3", "note": "pick 2 → 3（追加「放下 → 抓第三个容器」）"},
    "ButtonUnmask": {"kind": "unmask_pick3", "note": "pick 2 → 3（追加「放下 → 抓第三个容器」）"},
    "VideoPlaceButton": {"kind": "place_two_cubes", "before": 2, "after": 2, "swaps": 3,
                         "note": "1 块放 2 次 → 2 块各按钮前后放 1 次（共 4 次）+ 各回原位 + swap 3 次"},
    "VideoPlaceOrder": {"kind": "place_two_cubes", "visits": 5, "swaps": 3,
                        "note": "1 块放 [2,4] 次 → 2 块共访问 5 次（2+3）+ 各回原位 + swap 3 次"},
}

# 计划第一部分四节的外推值（中位 T / 窗），用来和合成值对账
PLAN_EXTRAPOLATION = {
    "PickXtimes": (1120, 68), "StopCube": (1020, 62), "SwingXtimes": (840, 50), "BinFill": (1140, 69),
    "VideoUnmaskSwap": (560, 31), "ButtonUnmaskSwap": (520, 31), "VideoRepick": (935, 56),
    "VideoPlaceOrder": (1800, 110), "PickHighlight": (850, 51), "PatternLock": (810, 49), "RouteStick": (900, 53),
    "VideoUnmask": (480, 26), "ButtonUnmask": (525, 30), "VideoPlaceButton": (1550, 92),
}


def load_plot_module():
    spec = importlib.util.spec_from_file_location("plot_sampling_windows", PLOT_MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def read_segments(group: h5py.Group) -> tuple[int, list[dict[str, Any]]]:
    """切段口径同留档 4.1：is_subgoal_boundary 为起点，段名取该步 simple_subgoal，demo 与尾段都算段。"""
    steps = sorted(int(name.split("_")[1]) for name in group if name.startswith("timestep_"))
    bounds: list[tuple[int, str, bool]] = []
    for step in steps:
        info = group[f"timestep_{step}"]["info"]
        if bool(info["is_subgoal_boundary"][()]):
            bounds.append((step, _text(info["simple_subgoal"][()]), bool(info["is_video_demo"][()])))
    total = len(steps)
    segments = []
    for index, (start, text, demo) in enumerate(bounds):
        end = bounds[index + 1][0] if index + 1 < len(bounds) else total
        segments.append({"text": text, "len": end - start, "demo": demo})
    return total, segments


def relayout(segments: list[dict[str, Any]]) -> dict[str, Any]:
    """按顺序重算 start，返回画图用的 item（total / demo / segments）。"""
    start = 0
    out = []
    demo = 0
    for seg in segments:
        out.append({"start": start, "len": seg["len"], "text": seg["text"], "demo": seg["demo"]})
        if seg["demo"]:
            demo += seg["len"]
        start += seg["len"]
    return {"total": start, "demo": demo, "segments": out}


def pick_variant(choices: list[int], episode: int) -> int:
    """按 episode 在 hard 序列里的序号轮流取区间内的值（ep3→第 0 个，ep7→第 1 个…）。"""
    return choices[(episode // 4) % len(choices)]


def synthesize(task: str, episode: int, segments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rule = RULES[task]
    kind = rule["kind"]
    segs = [dict(s) for s in segments]
    meta: dict[str, Any] = {"rule": rule["note"]}

    if kind == "unchanged":
        meta["from"] = meta["to"] = None
        return segs, meta

    if kind in ("pairs_exec", "pairs_exec_lastpick", "pairs_demo"):
        want_demo = kind == "pairs_demo"
        pick_re, place_re = re.compile(rule["pick"]), re.compile(rule["place"])
        pairs: list[tuple[int, int]] = []  # (pick_idx, place_idx)
        for i, s in enumerate(segs):
            if s["demo"] == want_demo and pick_re.search(s["text"]) and i + 1 < len(segs) and place_re.search(segs[i + 1]["text"]):
                pairs.append((i, i + 1))
        picks = [i for i, s in enumerate(segs) if s["demo"] == want_demo and pick_re.search(s["text"])]
        n_from = len(picks)
        if "extra" in rule:
            n_to = n_from + pick_variant(rule["extra"], episode)
        else:
            n_to = pick_variant(rule["target"], episode)
        add = max(0, n_to - n_from)
        if not pairs or add == 0:
            meta.update({"from": n_from, "to": n_to, "added_pairs": 0})
            return segs, meta
        # 插入位置：lastpick 型插在最后一个 pick 之前（它没有配对的 place）；其余插在最后一对之后
        insert_at = picks[-1] if kind == "pairs_exec_lastpick" else pairs[-1][1] + 1
        copies = []
        for k in range(add):
            pi, qi = pairs[k % len(pairs)]
            copies.append(dict(segs[pi]))
            copies.append(dict(segs[qi]))
        segs = segs[:insert_at] + copies + segs[insert_at:]
        meta.update({"from": n_from, "to": n_to, "added_pairs": add})
        return segs, meta

    if kind == "moves_both":
        move_re = re.compile(rule["move"])
        n_demo = sum(1 for s in segs if s["demo"] and move_re.search(s["text"]))
        n_exec = sum(1 for s in segs if not s["demo"] and move_re.search(s["text"]))
        if task == "PatternLock":
            l_from = n_exec + 1  # 节点数 L = move 数 + 1
            l_to = pick_variant(rule["target"], episode)
            add = max(0, (l_to - 1) - n_exec)
        else:
            l_from = n_exec
            l_to = pick_variant(rule["target"], episode)
            add = max(0, l_to - n_exec)
        out = []
        for side in (True, False):
            moves = [s for s in segs if s["demo"] == side and move_re.search(s["text"])]
            others_before = []
            others_after = []
            seen_move = False
            for s in segs:
                if s["demo"] != side:
                    continue
                if move_re.search(s["text"]):
                    seen_move = True
                elif not seen_move:
                    others_before.append(s)
                else:
                    others_after.append(s)
            extra = [dict(moves[k % len(moves)]) for k in range(add)] if moves else []
            out += others_before + moves + extra + others_after
        meta.update({"from": l_from, "to": l_to, "added_moves_per_side": add})
        return out, meta

    if kind == "stopcube":
        k_to = pick_variant(rule["target"], episode)
        mi = rule["interval"]
        final = mi * k_to - mi // 2 - 30  # steps_press − 30
        first = segs[0]
        statics = [s for s in segs if s["text"] == "remain static"]
        rest = [s for s in segs if s["text"] != "remain static"][1:]  # press + tail
        k_from = round((sum(s["len"] for s in statics) + first["len"] + 30 + 60 / 2) / 60) if statics else None
        checkpoints = [c for c in list(range(100, final, 100)) + [final] if c > first["len"]]
        bounds = [first["len"]] + checkpoints
        new_statics = [{"text": "remain static", "len": bounds[i + 1] - bounds[i], "demo": False} for i in range(len(bounds) - 1)]
        meta.update({"from_static_segments": len(statics), "to_static_segments": len(new_statics), "k_to": k_to, "final": final})
        return [first] + new_statics + rest, meta

    if kind == "demo_static":
        demo_len = sum(s["len"] for s in segs if s["demo"])
        s_from = round((demo_len - 64) / 50)
        s_to = pick_variant(rule["target"], episode)
        new_demo = 6 * math.ceil((64 + 50 * s_to) / 6)
        for s in segs:
            if s["demo"]:
                s["len"] = new_demo
                break
        meta.update({"from": s_from, "to": s_to, "demo_from": demo_len, "demo_to": new_demo})
        return segs, meta

    if kind == "unmask_pick3":
        # 官方：[static|press] → pick bin_0 → put down → pick bin_1 → 尾段；合成：在尾段前追加 [put down → pick]（复制已有的那对）
        put = next((i for i, x in enumerate(segs) if x["text"] == "put down the container"), None)
        if put is None or put + 1 >= len(segs):
            meta.update({"from": 2, "to": 2, "added_pairs": 0})
            return segs, meta
        pair = [dict(segs[put]), dict(segs[put + 1])]
        tail_idx = next(i for i, x in enumerate(segs) if x["text"] == TAIL)
        segs = segs[:tail_idx] + pair + segs[tail_idx:]
        meta.update({"from": 2, "to": 3, "added_pairs": 1})
        return segs, meta

    if kind == "place_two_cubes":
        # 官方 demo：若干 [pick up the cube → drop the cube onto target]（按钮插在中间）→ [pick → drop onto table] → static(20) → static(60, 1 次 swap)
        # 合成 demo：按钮前 b 对 → press → 按钮后 a 对 → 2 对回原位（用「drop onto table」那对代替）→ static(20) → static(60 + 50×(swaps−1))
        demo = [x for x in segs if x["demo"]]
        exec_ = [x for x in segs if not x["demo"]]
        pairs = [(demo[i], demo[i + 1]) for i in range(len(demo) - 1)
                 if demo[i]["text"] == "pick up the cube" and demo[i + 1]["text"] == "drop the cube onto target"]
        home = next(((demo[i], demo[i + 1]) for i in range(len(demo) - 1)
                     if demo[i]["text"] == "pick up the cube" and demo[i + 1]["text"] == "drop the cube onto table"), None)
        press = next((x for x in demo if x["text"] == "press the button"), None)
        statics = [x for x in demo if x["text"] == "static"]
        if not pairs or home is None or press is None or len(statics) < 2:
            meta.update({"from": len(pairs), "to": None, "note2": "段结构不符，原样"})
            return segs, meta
        if "visits" in rule:
            n_total = rule["visits"]
            n_before = n_total // 2  # 按钮插在中间附近
            n_after = n_total - n_before
        else:
            n_before, n_after = rule["before"], rule["after"]
        def take(n, offset=0):
            out = []
            for k in range(n):
                a, b = pairs[(k + offset) % len(pairs)]
                out += [dict(a), dict(b)]
            return out
        home_pairs = [dict(home[0]), dict(home[1])] * 2
        for x in home_pairs:
            x["text"] = "put the cube back to its original position" if x["text"] == "drop the cube onto table" else x["text"]
        new_demo = take(n_before) + [dict(press)] + take(n_after, n_before) + home_pairs
        swap_static = dict(statics[-1]); swap_static["len"] = statics[-1]["len"] + 50 * (rule["swaps"] - 1)
        new_demo += [dict(statics[0]), swap_static]
        meta.update({"from": len(pairs), "to": n_before + n_after, "cubes": 2, "swaps": rule["swaps"]})
        return new_demo + exec_, meta

    raise ValueError(kind)


def stats(item: dict[str, Any], plot) -> dict[str, Any]:
    total, demo = item["total"], item["demo"]
    windows_demo = len(plot.seg_windows(demo)) if demo else 0
    windows_exec = len(plot.seg_windows(total - demo))
    frames8 = plot.frame_indices(total, 8)
    exec_segs = [s for s in item["segments"] if not s["demo"] and s["text"] != TAIL]
    skip8 = sum(1 for s in exec_segs if not any(s["start"] <= f < s["start"] + s["len"] for f in frames8))
    shortest = min((s["len"] for s in exec_segs), default=0)
    return {
        "T": total, "demo": demo, "windows": windows_demo + windows_exec,
        "windows_demo": windows_demo, "windows_exec": windows_exec,
        "delta8": round((total - 1) / 7, 1), "delta32": round((total - 1) / 31, 1),
        "exec_segments": len(exec_segs), "shortest_exec_seg": shortest, "skip8": skip8,
    }


def plot_pair_rows(task: str, rows: list[tuple[str, dict[str, Any], dict[str, Any]]], out_path: Path, plot) -> None:
    plt = plot.plt
    Rectangle = plot.Rectangle
    xmax = max(max(h["item"]["total"], x["item"]["total"]) for _, h, x in rows)
    n_rows = len(rows) * 2
    fig, ax = plt.subplots(figsize=(11, 0.68 * n_rows + 1.6))
    y = n_rows
    for label, hard, synth in rows:
        for tag, rec in (("官方 hard", hard), ("xhard1 合成", synth)):
            plot.draw_row(ax, y, rec["item"], xmax)
            st = rec["stats"]
            ax.text(-xmax * 0.012, y, f"{label}(按合成T)·{tag}", ha="right", va="center", fontsize=6.4)
            ax.text(
                xmax * 1.012, y,
                f"ep{rec['episode']} seed{rec['seed']}  T={st['T']}  窗口 {st['windows_demo']}+{st['windows_exec']}={st['windows']}  "
                f"Δ8={st['delta8']}  最短段={st['shortest_exec_seg']}  漏段8={st['skip8']}",
                ha="left", va="center", fontsize=5.8, color="#4A5257",
            )
            y -= 1
    ax.set_xlim(0, xmax)
    ax.set_ylim(0.4, n_rows + 0.75)
    ax.set_yticks([])
    ax.set_xlabel("timestep（1 ts = 1 个 env step = 0.05 s）", fontsize=8)
    ax.tick_params(axis="x", labelsize=7.5)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.set_title(
        f"{task}：官方 hard vs xhard1 合成参考\n{RULES[task]['note']}；按 subgoal 段复制粘贴，非实跑",
        fontsize=8.8, loc="left", x=-0.12,
    )
    handles = [
        Rectangle((0, 0), 1, 1, facecolor=plot.COLOR["demo"], alpha=0.9, label="demo 段窗口 [f, f+32]"),
        Rectangle((0, 0), 1, 1, facecolor=plot.COLOR["exec"], alpha=0.9, label="exec 段窗口（stride 16，堆 3 行）"),
        Rectangle((0, 0), 1, 1, facecolor=plot.COLOR["sg_a"], edgecolor=plot.COLOR["sg_line"], label="subgoal 分段"),
        plt.Line2D([], [], color=plot.COLOR["frame32"], lw=1.0, label="帧路 N=32"),
        plt.Line2D([], [], color=plot.COLOR["frame8"], marker="o", ms=3, lw=0, label="帧路 N=8"),
    ]
    ax.legend(handles=handles, fontsize=6.4, loc="lower center",
              bbox_to_anchor=(0.5, -0.22), ncol=5, frameon=False)
    fig.subplots_adjust(left=0.125, right=0.70, top=0.90, bottom=0.20)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def median_int(values: list[int]) -> int:
    return int(statistics.median(values)) if values else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--h5-dir", default="/data/hongzefu/data_0226")
    parser.add_argument("--metadata-dir", default=str(REPO_ROOT / "src" / "robomme" / "env_metadata" / "train"))
    parser.add_argument("--out", default=str(REPO_ROOT / "vis" / "output"))
    parser.add_argument("--tasks", default=",".join(RULES))
    args = parser.parse_args(argv)

    plot = load_plot_module()
    plot.setup_font()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = [t for t in args.tasks.split(",") if t]
    summary_rows = []
    total_episodes = 0

    for task in tasks:
        meta = json.loads((Path(args.metadata_dir) / f"record_dataset_{task}_metadata.json").read_text(encoding="utf-8"))
        hard = {r["episode"]: r["seed"] for r in meta["records"] if r["difficulty"] == "hard"}
        records = []
        with h5py.File(Path(args.h5_dir) / f"record_dataset_{task}.h5", "r") as handle:
            for episode in sorted(hard):
                key = f"episode_{episode}"
                if key not in handle:
                    continue
                total, segments = read_segments(handle[key])
                hard_item = relayout(segments)
                assert hard_item["total"] == total, (task, episode)
                synth_segments, how = synthesize(task, episode, segments)
                synth_item = relayout(synth_segments)
                records.append({
                    "episode": episode, "seed": hard[episode], "synthesis": how,
                    "hard": {"item": hard_item, "stats": stats(hard_item, plot)},
                    "xhard1": {"item": synth_item, "stats": stats(synth_item, plot)},
                })
        total_episodes += len(records)
        (out_dir / f"reference_{task}.json").write_text(
            json.dumps({"task": task, "rule": RULES[task]["note"], "synthetic": True, "records": records},
                       ensure_ascii=False, indent=1), encoding="utf-8")

        by_t = sorted(records, key=lambda r: r["xhard1"]["stats"]["T"])
        picks = [("最短", by_t[0]), ("中位", by_t[len(by_t) // 2]), ("最长", by_t[-1])]
        rows = [(label, {**r["hard"], "episode": r["episode"], "seed": r["seed"]},
                 {**r["xhard1"], "episode": r["episode"], "seed": r["seed"]}) for label, r in picks]
        plot_pair_rows(task, rows, out_dir / f"{task}.png", plot)

        def agg(side: str, key: str):
            vals = [r[side]["stats"][key] for r in records]
            return min(vals), median_int(vals), max(vals), round(statistics.mean(vals), 2)

        plan_t, plan_w = PLAN_EXTRAPOLATION[task]
        h_t, x_t = agg("hard", "T"), agg("xhard1", "T")
        h_w, x_w = agg("hard", "windows"), agg("xhard1", "windows")
        h_s, x_s = agg("hard", "skip8"), agg("xhard1", "skip8")
        x_short = agg("xhard1", "shortest_exec_seg")
        x_d8 = agg("xhard1", "delta8")
        min_skip = min(r["xhard1"]["stats"]["skip8"] for r in records)
        summary_rows.append(
            f"| {task} | {len(records)} | {h_t[0]}/{h_t[1]}/{h_t[2]} | {x_t[0]}/{x_t[1]}/{x_t[2]} | {plan_t} | "
            f"{h_w[1]} | {x_w[0]}/{x_w[1]}/{x_w[2]} | {plan_w} | {x_d8[1]} | {x_short[1]} | {h_s[3]} | {x_s[3]}（最少 {min_skip}） |"
        )
        print(f"XHARD_REF_TASK=INFO task={task} episodes={len(records)} T_hard_med={h_t[1]} T_synth_med={x_t[1]} "
              f"plan_T={plan_t} windows_synth_med={x_w[1]} plan_windows={plan_w} skip8_synth_min={min_skip}")

    summary = [
        "# xhard1 合成参考数轴：汇总",
        "",
        "合成方法：官方 hard 每条 episode 按 subgoal 段切开，把「重复单元」按 xhard1 取值复制粘贴（复制同一条 episode 自己的段，循环取），其余段原样；**非实跑**。"
        "T 单位 timestep；窗 = demo 窗 + exec 窗（33 帧、stride 16、不跨段）；Δ8 = (T−1)/7；最短段 = 执行段里最短一段；漏段8 = 8 帧帧路没有采样点落入的执行段数。"
        "「外推」列是 `1006-xhard12-env-plan.md` 第一部分四节的线性外推中位值。",
        "",
        "| 任务 | n | hard T（最短/中位/最长） | 合成 T（最短/中位/最长） | 外推 T | hard 窗（中位） | 合成窗（最短/中位/最长） | 外推窗 | 合成 Δ8（中位） | 合成最短段（中位） | hard 漏段8（均值） | 合成漏段8（均值） |",
        "|---|---:|---|---|---:|---:|---|---:|---:|---:|---:|---|",
        *summary_rows,
        "",
        "各任务复制规则见 `vis/synthesize_reference_timeline.py` 的 `RULES`；逐条数据见同目录 `reference_<Task>.json`；图见 `<Task>.png`（每任务按合成 T 取最短 / 中位 / 最长三条，每条上行官方 hard、下行 xhard1 合成）。",
    ]
    (out_dir / "reference_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"XHARD_REF=INFO tasks={len(tasks)} episodes={total_episodes} synthetic=1 out={out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
