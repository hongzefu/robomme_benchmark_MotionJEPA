#!/usr/bin/env python3
"""V6 三档实测并行 driver：ProcessPool（spawn）N worker，每 worker 一局；结果逐行追加 results.jsonl。"""
import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tiers_worker  # noqa: E402

# 预估长局在前，尾部不拖（VPO/VR/VPB/PL/RS/BinFill 先跑）
ORDER = ["VideoPlaceOrder", "VideoRepick", "VideoPlaceButton", "PatternLock", "RouteStick", "BinFill",
         "PickXtimes", "PickHighlight", "VideoUnmaskSwap", "ButtonUnmaskSwap", "SwingXtimes", "ButtonUnmask",
         "VideoUnmask"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", default="0")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--jobs", default=str(HERE / "jobs.json"))
    ap.add_argument("--out", default=str(HERE / "results.jsonl"))
    ap.add_argument("--tmp-root", default="/tmp/hongzefu-tiers")
    ap.add_argument("--only", default=None, help="逗号分隔的 task_tier 过滤")
    args = ap.parse_args()
    jobs = json.loads(Path(args.jobs).read_text())
    if args.only:
        keep = set(args.only.split(","))
        jobs = [j for j in jobs if f"{j['task']}_{j['tier']}" in keep]
    done = set()
    if Path(args.out).exists():
        for line in open(args.out):
            r = json.loads(line)
            done.add((r["task"], r["tier"], r["seed"]))
    jobs = [j for j in jobs if (j["task"], j["tier"], j["seed"]) not in done]
    # xhard 对照放最后；其余按 ORDER、局序
    jobs.sort(key=lambda j: (j["tier_idx"] == 4, j["i"], ORDER.index(j["task"]), j["tier_idx"]))
    for j in jobs:
        j["dir"] = str(HERE)
        j["tmp_root"] = args.tmp_root
    Path(args.tmp_root).mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    n_ok = 0
    print(f"START jobs={len(jobs)} workers={args.workers}", flush=True)
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=min(args.workers, len(jobs)), mp_context=ctx,
                             initializer=tiers_worker.init, initargs=(args.gpu,)) as ex:  # 去掉 max_tasks_per_child=3：spawn 下 worker 换代挂死（16×3=48、8×3=24 两次都卡在换代点）
        futs = {ex.submit(tiers_worker.run, j): j for j in jobs}
        for n, fut in enumerate(as_completed(futs), 1):
            j = futs[fut]
            try:
                row = fut.result()
            except BaseException as exc:  # noqa: BLE001
                row = {k: j[k] for k in ("task", "tier", "tier_idx", "i", "seed", "patches")}
                row.update(ok=False, failure_class="driver", error_type=type(exc).__name__, error=str(exc)[:400])
            n_ok += row["ok"]
            with open(args.out, "a") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{n}/{len(jobs)}] {row['task']}_{row['tier']} seed={row['seed']} ok={row['ok']} "
                  f"{row.get('error_type') or ''} {(row.get('error') or '')[:120]} es={row.get('elapsed_steps')} "
                  f"h5={row.get('h5_steps')} nd={row.get('h5_nondemo')} wall={row.get('wall_s')} t={time.time() - t0:.0f}s",
                  flush=True)
    print(f"DONE jobs={len(jobs)} ok={n_ok} t={time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
