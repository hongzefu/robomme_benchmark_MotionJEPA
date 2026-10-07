"""合成 xhard1 参考数轴：用官方 hard 数据按 subgoal 段「复制粘贴」拼出 xhard1 的参考时间轴并出图。

不跑仿真、不改源码，只读 /data/hongzefu/data_0226/ 里 16 任务的 hard episode（每任务 25 条，
Unmask 系 h5 只有 ep0–99 所以也是 25 条）。每个任务的「重复单元」按 1006-xhard12-env-plan.md
第一部分四节的 xhard1 取值复制若干份（复制的是同一条 episode 自己的段，循环取），其余段原样保留，
拼成一条合成时间轴。合成结果与真实 xhard 的差别只在段长的随机波动与 planner 路径差异，作为参考。

出图用 V2 画法（同目录 v2_plot.py，逐字搬自 origin/newtask-v2 的 injection-before-2d 数轴脚本）：
demo / exec 底色、subgoal 分段、stride-16 不跨段的 33 帧窗口（3 行堆叠）、32 帧与 8 帧帧路、
每次 swap 一条半透明竖带。每任务一张 <Task>.png：按合成 T 取最短 / 中位 / 最长三条，
每条画两行——上行官方 hard 原样、下行 xhard1 合成；另出 overview.png：14 任务各三条 xhard1，共用全局横轴。

漏段口径（2026-10-07 用户「v2有一个swap的标注 也作为subgoal 你也要考虑这个问题 swap采不到也不行」，
追问后定「每次 swap 算一段」）：skip8_total = 执行段（不含尾段）漏采数 + 每次 swap 事件（50 帧）漏采数。

用法：
  uv run --no-sync python vis/synthesize_reference_timeline.py \
      --h5-dir /data/hongzefu/data_0226 --metadata-dir src/robomme/env_metadata/train --out vis/output
判定行：XHARD_REF=INFO tasks=<n> episodes=<n> synthetic=1；XHARD_REF_SWAP=INFO tasks=4 ...
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any

import h5py

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import v2_plot  # noqa: E402

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
    "ButtonUnmaskSwap": {"kind": "unchanged", "swap_hard": [2, 3], "swap_xhard1": [4, 5],
                         "note": "swap [2,3] → [4,5]，交换与按钮并行、时长基本不变（swap 次数 h5 里读不到，按序号轮流估）"},
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


SWAP_START, SWAP_LEN = 64, 50  # VideoUnmaskSwap / ButtonUnmaskSwap._refresh_swap_schedule：第 k 次 = [64+50(k−1), 64+50k]


def swap_events(task: str, tier: str, item: dict[str, Any], how: dict[str, Any], episode: int) -> list[list[Any]]:
    """每次 swap 一个事件 [起, 止, 标注]（V2 draw_track 的 row["swaps"] 格式）。

    * VideoUnmaskSwap：demo 内调度常量，次数 hard 取 demo 长反推的 how["from"]、xhard1 取 how["to"]；
    * ButtonUnmaskSwap：同一组调度常量（从 episode 第 0 步起算，与按钮并行），h5 读不到次数，按 episode 序号轮流估；
    * VideoPlaceButton / VideoPlaceOrder：最后一个 demo static 段起点 s0 起每 50 帧一次（hard 1 次、xhard1 3 次）；
      真实 h5 里 swap 闩锁步与段边界可能差十几帧，合成参考接受这个近似。
    其余任务没有 swap。
    """
    rule = RULES[task]
    if task == "VideoUnmaskSwap":
        n, base, note = how["from"] if tier == "hard" else how["to"], SWAP_START, ""
    elif task == "ButtonUnmaskSwap":
        n, base, note = pick_variant(rule["swap_hard" if tier == "hard" else "swap_xhard1"], episode), SWAP_START, "估"
    elif task in ("VideoPlaceButton", "VideoPlaceOrder"):
        statics = [x for x in item["segments"] if x["demo"] and x["text"] == "static"]
        if not statics:
            return []
        n = 1 if tier == "hard" or how.get("to") is None else rule["swaps"]
        base, note = statics[-1]["start"], ""
    else:
        return []
    return [[base + SWAP_LEN * k, base + SWAP_LEN * (k + 1), note] for k in range(n)]


def _missed(spans: list[tuple[int, int]], frames: list[int]) -> int:
    return sum(1 for a, b in spans if not any(a <= f < b for f in frames))


def stats(item: dict[str, Any], swaps: list[list[Any]]) -> dict[str, Any]:
    total, demo = item["total"], item["demo"]
    windows_demo = len(v2_plot.window_starts(demo)) if demo else 0
    windows_exec = len(v2_plot.window_starts(total - demo))
    frames8 = v2_plot.frame_path(total, 8)
    exec_segs = [s for s in item["segments"] if not s["demo"] and s["text"] != TAIL]
    exec_skip8 = _missed([(s["start"], s["start"] + s["len"]) for s in exec_segs], frames8)
    swap_skip8 = _missed([(a, b) for a, b, _ in swaps], frames8)
    shortest = min((s["len"] for s in exec_segs), default=0)
    return {
        "T": total, "demo": demo, "windows": windows_demo + windows_exec,
        "windows_demo": windows_demo, "windows_exec": windows_exec,
        "delta8": round((total - 1) / 7, 1), "delta32": round((total - 1) / 31, 1),
        "exec_segments": len(exec_segs), "shortest_exec_seg": shortest,
        "exec_skip8": exec_skip8, "swap_events": len(swaps), "swap_skip8": swap_skip8,
        "skip8_total": exec_skip8 + swap_skip8,
    }


def v2_row(rec: dict[str, Any]) -> dict[str, Any]:
    """转成 V2 draw_track 的 row：segs = [起点, 长度, 文本]，swap_check 固定 PASS（合成值无需校验）。"""
    item = rec["item"]
    return {"episode": rec["episode"], "seed": rec["seed"], "total": item["total"], "demo": item["demo"],
            "segs": [[x["start"], x["len"], x["text"]] for x in item["segments"]],
            "swaps": rec["swaps"], "swap_check": "PASS"}


def plot_pair_rows(task: str, rows: list[tuple[str, dict[str, Any], dict[str, Any]]], out_path: Path) -> None:
    xmax = max(max(h["item"]["total"], x["item"]["total"]) for _, h, x in rows)
    items: list[tuple[Any, ...]] = []
    for band, hard, synth in rows:
        items.append(("header", f"{band}（按合成 T）· ep{hard['episode']} · seed {hard['seed']} · "
                                f"漏段8 hard {hard['stats']['exec_skip8']}+swap {hard['stats']['swap_skip8']} → "
                                f"xhard1 {synth['stats']['exec_skip8']}+swap {synth['stats']['swap_skip8']}"))
        items.append(("row", v2_plot._label_for(v2_row(hard), task, "官方 hard"), v2_row(hard), False))
        items.append(("row", v2_plot._label_for(v2_row(synth), task, "xhard1 合成"), v2_row(synth), False))
    title = f"{task}：官方 hard vs xhard1 合成参考（{RULES[task]['note']}；按 subgoal 段复制粘贴，非实跑）"
    v2_plot._draw_board(items, xmax, title, out_path)


def plot_overview(per_task: list[tuple[str, list[dict[str, Any]]]], out_path: Path) -> None:
    xmax = max(r["xhard1"]["item"]["total"] for _, records in per_task for r in records)
    items: list[tuple[Any, ...]] = []
    for task, records in per_task:
        rows = [{**v2_row({**r["xhard1"], "episode": r["episode"], "seed": r["seed"]})} for r in records]
        reps = v2_plot.representatives(rows)
        items.append(("header", f"{task} / xhard1 合成（{len(rows)} 条）　{RULES[task]['note']}"))
        for band in v2_plot.BANDS:
            items.append(("row", v2_plot._label_for(reps[band], task, "xhard1", band), reps[band], False))
    v2_plot._draw_board(items, xmax, f"xhard1 合成参考数轴总览 · {len(per_task)} 任务各取最短／中位／最长三条（横轴 0–{xmax} 全局固定，可跨任务横比；非实跑）", out_path)


def median_int(values: list[int]) -> int:
    return int(statistics.median(values)) if values else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--h5-dir", default="/data/hongzefu/data_0226")
    parser.add_argument("--metadata-dir", default=str(REPO_ROOT / "src" / "robomme" / "env_metadata" / "train"))
    parser.add_argument("--out", default=str(REPO_ROOT / "vis" / "output"))
    parser.add_argument("--tasks", default=",".join(RULES))
    args = parser.parse_args(argv)

    v2_plot.use_cjk_font()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = [t for t in args.tasks.split(",") if t]
    summary_rows = []
    swap_rows = []
    swap_min: dict[str, int] = {}
    per_task: list[tuple[str, list[dict[str, Any]]]] = []
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
                hard_swaps = swap_events(task, "hard", hard_item, how, episode)
                synth_swaps = swap_events(task, "xhard1", synth_item, how, episode)
                records.append({
                    "episode": episode, "seed": hard[episode], "synthesis": how,
                    "hard": {"item": hard_item, "swaps": hard_swaps, "stats": stats(hard_item, hard_swaps)},
                    "xhard1": {"item": synth_item, "swaps": synth_swaps, "stats": stats(synth_item, synth_swaps)},
                })
        total_episodes += len(records)
        (out_dir / f"reference_{task}.json").write_text(
            json.dumps({"task": task, "rule": RULES[task]["note"], "synthetic": True, "records": records},
                       ensure_ascii=False, indent=1), encoding="utf-8")

        by_t = sorted(records, key=lambda r: r["xhard1"]["stats"]["T"])
        picks = [("最短", by_t[0]), ("中位", by_t[len(by_t) // 2]), ("最长", by_t[-1])]
        rows = [(label, {**r["hard"], "episode": r["episode"], "seed": r["seed"]},
                 {**r["xhard1"], "episode": r["episode"], "seed": r["seed"]}) for label, r in picks]
        plot_pair_rows(task, rows, out_dir / f"{task}.png")
        per_task.append((task, records))

        def agg(side: str, key: str):
            vals = [r[side]["stats"][key] for r in records]
            return min(vals), median_int(vals), max(vals), round(statistics.mean(vals), 2)

        plan_t, plan_w = PLAN_EXTRAPOLATION[task]
        h_t, x_t = agg("hard", "T"), agg("xhard1", "T")
        h_w, x_w = agg("hard", "windows"), agg("xhard1", "windows")
        h_s, x_s = agg("hard", "skip8_total"), agg("xhard1", "skip8_total")
        x_e, x_w8 = agg("xhard1", "exec_skip8"), agg("xhard1", "swap_skip8")
        x_short = agg("xhard1", "shortest_exec_seg")
        x_d8 = agg("xhard1", "delta8")
        zero_hard = sum(1 for r in records if r["hard"]["stats"]["skip8_total"] == 0)
        zero_x = sum(1 for r in records if r["xhard1"]["stats"]["skip8_total"] == 0)
        summary_rows.append(
            f"| {task} | {len(records)} | {h_t[0]}/{h_t[1]}/{h_t[2]} | {x_t[0]}/{x_t[1]}/{x_t[2]} | {plan_t} | "
            f"{h_w[1]} | {x_w[0]}/{x_w[1]}/{x_w[2]} | {plan_w} | {x_d8[1]} | {x_short[1]} | "
            f"{x_e[3]}（最少 {x_e[0]}） | {x_w8[3]}（最少 {x_w8[0]}） | {h_s[3]}（最少 {h_s[0]}） | {x_s[3]}（最少 {x_s[0]}） | "
            f"{zero_hard}/{len(records)} → {zero_x}/{len(records)} |"
        )
        if any(r["xhard1"]["swaps"] for r in records):
            sw_h, sw_x = agg("hard", "swap_events"), agg("xhard1", "swap_events")
            swap_rows.append(f"| {task} | {sw_h[0]}–{sw_h[2]} → {sw_x[0]}–{sw_x[2]} | {agg('hard', 'swap_skip8')[3]} → {x_w8[3]}（最少 {x_w8[0]}） | "
                             f"{h_s[0]} → {x_s[0]} | {zero_hard}/{len(records)} → {zero_x}/{len(records)} |")
            swap_min[task] = x_s[0]
        print(f"XHARD_REF_TASK=INFO task={task} episodes={len(records)} T_hard_med={h_t[1]} T_synth_med={x_t[1]} "
              f"plan_T={plan_t} windows_synth_med={x_w[1]} plan_windows={plan_w} "
              f"exec_skip8_min={x_e[0]} swap_skip8_min={x_w8[0]} skip8_total_min={x_s[0]}")

    summary = [
        "# xhard1 合成参考数轴：汇总",
        "",
        "合成方法：官方 hard 每条 episode 按 subgoal 段切开，把「重复单元」按 xhard1 取值复制粘贴（复制同一条 episode 自己的段，循环取），其余段原样；**非实跑**。"
        "T 单位 timestep；窗 = demo 窗 + exec 窗（33 帧、stride 16、不跨段）；Δ8 = (T−1)/7；最短段 = 执行段里最短一段；"
        "8 帧帧路 = V2 的 `floor(i·(T−1)/7 + 0.5)`；执行段漏 = 帧路没有点落入的执行段数（不含 demo 与尾段）；swap 漏 = 帧路没有点落入的 swap 事件数（每次 swap 50 帧算一段，2026-10-07 用户定）；合计漏 = 两者之和。"
        "「外推」列是 `1006-xhard12-env-plan.md` 第一部分四节的线性外推中位值。",
        "",
        "| 任务 | n | hard T（最短/中位/最长） | 合成 T（最短/中位/最长） | 外推 T | hard 窗（中位） | 合成窗（最短/中位/最长） | 外推窗 | 合成 Δ8（中位） | 合成最短段（中位） | 合成执行段漏（均值） | 合成 swap 漏（均值） | hard 合计漏（均值） | 合成合计漏（均值） | 0 漏条数 hard → 合成 |",
        "|---|---:|---|---|---:|---:|---|---:|---:|---:|---|---|---|---|---|",
        *summary_rows,
        "",
        "## 有 swap 的四个任务",
        "",
        "swap 事件时刻：VideoUnmaskSwap / ButtonUnmaskSwap 按调度常量 `[64+50(k−1), 64+50k]`（ButtonUnmaskSwap 从第 0 步起算、与按钮并行，次数 h5 读不到，按 episode 序号轮流估）；"
        "VideoPlaceButton / VideoPlaceOrder 从最后一个 demo static 段起点每 50 帧一次（真实 h5 里闩锁步可能晚十几帧）。",
        "",
        "| 任务 | swap 次数 hard → xhard1 | swap 漏均值 hard → xhard1 | 合计漏最少 hard → xhard1 | 0 漏条数 hard → xhard1 |",
        "|---|---|---|---|---|",
        *swap_rows,
        "",
        "各任务复制规则见 `vis/synthesize_reference_timeline.py` 的 `RULES`；逐条数据见同目录 `reference_<Task>.json`；图见 `<Task>.png`（每任务按合成 T 取最短 / 中位 / 最长三条，每条上行官方 hard、下行 xhard1 合成，竖带为 swap）与 `overview.png`（V2 画法总览）；V2 实测原图见 `../v2/windows_overview.png`。",
    ]
    (out_dir / "reference_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    plot_overview(per_task, out_dir / "overview.png")
    print("XHARD_REF_SWAP=INFO tasks=" + str(len(swap_min)) + "".join(f" min_total_skip8_{t}={v}" for t, v in swap_min.items()))
    print(f"XHARD_REF=INFO tasks={len(tasks)} episodes={total_episodes} synthetic=1 out={out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
