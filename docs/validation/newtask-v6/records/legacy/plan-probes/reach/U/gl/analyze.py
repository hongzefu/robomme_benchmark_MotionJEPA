#!/usr/bin/env python3
"""合并 layouts.csv 与 results_gpu*.jsonl → results.jsonl；给出失败子任务/阶段归因与分组统计。
用法：python analyze.py <目录> [<目录> ...]（多个目录合并统计）
"""
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


def category(r):
    if r.get("ok"):
        return "成功"
    et, err = r.get("error_type"), r.get("error") or ""
    if et == "DatasetGenerationError" and "did not succeed" in err:
        return "任务未完成"
    if et == "DatasetGenerationError" and "reported failure" in err:
        return "环境判失败"
    return et or "未知"


def locate(r):
    """返回 (卡住的子任务序号, 子任务名, 阶段 demo/exec/reset)。"""
    trace = r.get("trace") or []
    names = (r.get("probe") or {}).get("task_names") or []
    no_rec = names.index("NO RECORD") if "NO RECORD" in names else None
    pos = -1
    stuck = None
    for t in trace:
        if t["tag"] == "before":
            pos += 1
        elif t["tag"] == "raise":
            stuck = pos
            break
        elif t["tag"] == "after" and stuck is None and t["idx"] is not None and t["idx"] <= pos \
                and names[pos] not in ("NO RECORD",):
            stuck = pos
    if stuck is None:
        return None, None, None
    phase = "reset" if names[stuck] == "NO RECORD" else ("demo" if no_rec is None or stuck < no_rec else "exec")
    return stuck, names[stuck], phase


def load(d):
    d = Path(d)
    lay = {int(row["episode"]): row for row in csv.DictReader((d / "layouts.csv").open())}
    out = []
    for f in sorted(d.glob("results_gpu*.jsonl")):
        for line in f.open():
            r = json.loads(line)
            ep = int(r["episode"])
            row = {k: (float(v) if k not in ("way", "gpu") else v) for k, v in lay[ep].items()}
            stuck, name, phase = (None, None, None) if r.get("ok") else locate(r)
            rec = {"batch": d.name, "episode": ep, "seed": r["seed"], "way": row["way"], "ok": bool(r.get("ok")),
                   "category": category(r), "error_type": r.get("error_type"), "error": (r.get("error") or "")[:300] or None,
                   "fail_subtask_index": stuck, "fail_subtask": name, "fail_phase": phase,
                   "steps": (r.get("probe") or {}).get("elapsed_steps"), "timestep_count": r.get("timestep_count"),
                   "wall_s": r.get("wall_s"), "trace": r.get("trace"), "layout": row}
            out.append(rec)
    out.sort(key=lambda x: x["episode"])
    return out


def main():
    dirs = sys.argv[1:] or ["."]
    allr = []
    for d in dirs:
        rs = load(d)
        with (Path(d) / "results.jsonl").open("w") as fh:
            for r in rs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        allr += rs
    by_way = defaultdict(list)
    for r in allr:
        by_way[r["way"]].append(r)
    for w, rs in by_way.items():
        c = Counter((r["category"], r["fail_phase"], r["fail_subtask"]) for r in rs if not r["ok"])
        ok = sum(r["ok"] for r in rs)
        print(f"{w}: {ok}/{len(rs)}  失败 {dict(c)}")
    print(f"合计 {sum(r['ok'] for r in allr)}/{len(allr)}")


if __name__ == "__main__":
    main()
