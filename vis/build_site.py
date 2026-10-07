"""把数轴做成可交互网页：按「对比的 V2 参照」分组，每组先画 V2 参照，再按官网顺序画各任务的原版（官方 hard）与新版（xhard1）。

2026-10-07 用户原话：「重新画数轴 根据最新的内容 并且host成aspen的网站给我 原版新版都要画 默认显示中位数长度
可以选择显示min max」「并且按照对比v2的来分组显示」。

数据来源（全部只读）：
  * 原版 / 新版：同目录 output/reference_<Task>.json（synthesize_reference_timeline.py 产出；新版是合成参考，非实跑；
    VideoPlaceButton / VideoPlaceOrder 不加档，新版 = 原版）；
  * V2 参照：v2/windows_timeline.json（origin/newtask-v2 的 scripts/injection-before-2d/windows_timeline.json 原样拷贝，
    20260911-contract-v3-07 一次实跑、每组 ep0–29 的成功条，已去掉 excluded_slow 慢条）。
分组与倍数口径同 1006-xhard12-env-plan.md 第一部分四节长度对比表；倍数 = 新版中位 ÷ V2 交付集中位（表中数），
网页里 V2 那一行画的是 07 实跑的代表条，与交付集中位相差在几十 timestep 以内。

每条轨迹独立按 timestep 数排序取最短 / 中位（下标 n//2）/ 最长，与 v2_plot.representatives 同规则。
用法：uv run --no-sync python vis/build_site.py --out artifacts/vis-site
判定行：XHARD_SITE=INFO groups=<n> tracks=<n> out=<路径>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import v2_plot  # noqa: E402

# 分组 = 计划四节长度对比表的「对比的 V2 参照」；组内任务按官网编号（AGENTS.md P6），组按首个任务的官网编号排。
# v2_median / v2_win_median 取计划表里的 V2 交付集中位 timestep 数（倍数分母）与中位 motion 窗口数。
GROUPS: list[dict[str, Any]] = [
    {"key": "BinFill/hard", "title": "参照 V2 BinFill hard（demo 为同一条重复两遍）", "v2_median": 1630, "v2_win_median": 98,
     "tasks": [("1.1", "BinFill"), ("1.2", "PickXtimes"), ("1.3", "SwingXtimes"), ("3.1", "PickHighlight")],
     "note": "BinFill 另对 V2 纯执行段（去掉假 demo，中位 815）：新版中位 1109，倍数 1.36。"},
    {"key": "RouteStick/xhard", "title": "参照 V2 RouteStick xhard", "v2_median": 900, "v2_win_median": 54,
     "tasks": [("1.4", "StopCube"), ("4.3", "PatternLock"), ("4.4", "RouteStick")], "note": ""},
    {"key": "VideoUnmaskSwap/xhard", "title": "参照 V2 VideoUnmaskSwap xhard", "v2_median": 558, "v2_win_median": 32,
     "tasks": [("2.1", "VideoUnmask"), ("2.2", "ButtonUnmask"), ("2.3", "VideoUnmaskSwap"), ("2.4", "ButtonUnmaskSwap")], "note": ""},
    {"key": "VideoRepick/xhard", "title": "参照 V2 VideoRepick xhard", "v2_median": 863, "v2_win_median": 51,
     "tasks": [("3.1", "PickHighlight"), ("3.2", "VideoRepick"), ("3.3", "VideoPlaceButton"), ("3.4", "VideoPlaceOrder")],
     "note": "VideoPlaceButton、VideoPlaceOrder 不加档（2026-10-07 用户定），新版与原版相同。"},
]
BAND_KEYS = {"最短": "min", "中位": "med", "最长": "max"}


def track_row(seg_items: list[dict[str, Any]], total: int, demo: int, swaps: list[list[Any]],
              episode: int, seed: int, swap_ok: bool = True, extra: str = "") -> dict[str, Any]:
    segs = []
    for x in seg_items:
        label, _ = v2_plot.short_label(x["text"])
        segs.append([x["start"], x["len"], label, x["text"]])
    d, e = v2_plot.window_counts({"demo": demo, "total": total})
    return {"episode": episode, "seed": seed, "total": total, "demo": demo, "segs": segs,
            "swaps": [[a, b, str(c).replace("bin_", "")] for a, b, c in swaps], "swap_ok": swap_ok,
            "windows": [d, e], "extra": extra}


def bands(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    reps = v2_plot.representatives(rows)
    return {BAND_KEYS[k]: v for k, v in reps.items()}


def load_task(out_dir: Path, task: str) -> dict[str, Any]:
    data = json.loads((out_dir / f"reference_{task}.json").read_text(encoding="utf-8"))
    sides = {}
    for side in ("hard", "xhard1"):
        rows = [track_row(r[side]["item"]["segments"], r[side]["item"]["total"], r[side]["item"]["demo"], r[side]["swaps"],
                          r["episode"], r["seed"]) for r in data["records"]]
        totals = sorted(x["total"] for x in rows)
        wins = sorted(sum(x["windows"]) for x in rows)
        sides[side] = {"bands": bands(rows), "n": len(rows), "median": totals[len(totals) // 2], "win_median": wins[len(wins) // 2]}
    return {"rule": data["rule"], **sides}


def load_v2(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    excluded = {(r["task"], r["difficulty"], r["episode"]) for r in data.get("excluded_slow", [])}
    out = {}
    for group in GROUPS:
        task, diff = group["key"].split("/")
        rows = []
        for r in data["groups"][group["key"]]:
            if (task, diff, r["episode"]) in excluded:
                continue
            segs = [{"start": s, "len": n, "text": t} for s, n, t in r["segs"]]
            extra = f"demo 重复两遍（原 {r['original_total']}）" if r.get("simulated_demo") else ""
            rows.append(track_row(segs, r["total"], r["demo"], r.get("swaps", []), r["episode"], r["seed"],
                                  r.get("swap_check", "PASS") == "PASS", extra))
        totals = sorted(x["total"] for x in rows)
        out[group["key"]] = {"bands": bands(rows), "n": len(rows), "median": totals[len(totals) // 2],
                             "run": data.get("rollout_run_id", "")}
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ref-dir", default=str(HERE / "output"))
    parser.add_argument("--v2", default=str(HERE / "v2" / "windows_timeline.json"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    ref_dir, out = Path(args.ref_dir), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    v2 = load_v2(Path(args.v2))
    tasks: dict[str, Any] = {}
    payload_groups = []
    n_tracks = 0
    for group in GROUPS:
        items = []
        for no, task in group["tasks"]:
            if task not in tasks:
                tasks[task] = load_task(ref_dir, task)
            t = tasks[task]
            items.append({"no": no, "task": task, "rule": t["rule"], "hard": t["hard"], "xhard1": t["xhard1"],
                          "ratio": round(t["xhard1"]["median"] / group["v2_median"], 2)})
            n_tracks += 2
        payload_groups.append({"key": group["key"], "title": group["title"], "note": group["note"],
                               "v2_median": group["v2_median"], "v2_win_median": group["v2_win_median"], "v2": v2[group["key"]], "items": items})
        n_tracks += 1
    payload = {"groups": payload_groups, "win": v2_plot.WIN, "stride": v2_plot.STRIDE, "budgets": list(v2_plot.BUDGETS),
               "swap_colors": v2_plot.SWAP_COLORS, "color": v2_plot.COLOR}
    html = (HERE / "site_template.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"XHARD_SITE=INFO groups={len(payload_groups)} tracks={n_tracks} out={out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
