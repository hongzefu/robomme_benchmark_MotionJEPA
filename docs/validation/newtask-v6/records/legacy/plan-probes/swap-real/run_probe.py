#!/usr/bin/env python3
"""swap-real 运行器：三环境 × 两组（s5 = S5 补丁；v5 = 原 V5 对照），动态补种子直到每组「通过 reset 的局」达标。
用法：python run_probe.py --workers 16 --out results.jsonl --tmp /tmp/hongzefu-swapreal [--s5 48 --v5 24]
"""
import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("PROBE_REPO", "/data/hongzefu/robomme_benchmark_MotionJEPANewTask"))
OFFICIAL = REPO / "artifacts/train-parity/local-smoke-01/official-src/scripts/data-generation"
ENV_CODE = {"VideoUnmaskSwap": 1, "ButtonUnmaskSwap": 2, "VideoRepick": 3}
CAP = {("s5", "VideoUnmaskSwap"): 110, ("s5", "ButtonUnmaskSwap"): 170, ("s5", "VideoRepick"): 170,
       ("v5", "VideoUnmaskSwap"): 60, ("v5", "ButtonUnmaskSwap"): 70, ("v5", "VideoRepick"): 90}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--gpu", default="0")
    ap.add_argument("--out", default=str(HERE / "results.jsonl"))
    ap.add_argument("--tmp", default="/tmp/hongzefu-swapreal")
    ap.add_argument("--s5", type=int, default=48)
    ap.add_argument("--v5", type=int, default=24)
    ap.add_argument("--tasks", default="VideoUnmaskSwap,ButtonUnmaskSwap,VideoRepick")
    args = ap.parse_args()
    for p in (str(OFFICIAL), str(REPO / "scripts" / "parity"), str(HERE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    import generate_dataset as official
    import probe_worker
    header = json.loads(open(REPO / "scripts/configs/newtask-v5/v5-01/specs.jsonl").readline())
    sampling = header["sampling_config"]
    tasks = args.tasks.split(",")
    groups = [(arm, t) for t in tasks for arm in ("s5", "v5") if (args.s5 if arm == "s5" else args.v5) > 0]
    target = {g: (args.s5 if g[0] == "s5" else args.v5) for g in groups}
    st = {g: {"next": 0, "pending": 0, "accepted": 0, "attempts": 0} for g in groups}
    out = Path(args.out)
    started = time.time()
    ctx = mp.get_context("spawn")
    # 每组一个进程池会浪费席位；这里用一个池，但 s5/v5 的补丁互斥 ⇒ 每个子进程只跑一组（max_tasks_per_child=1）
    ex = ProcessPoolExecutor(max_workers=args.workers, mp_context=ctx, max_tasks_per_child=1)
    futs = {}

    def submit_one(g):
        arm, task = g
        s = st[g]
        i = s["next"]; s["next"] += 1; s["pending"] += 1; s["attempts"] += 1
        seed = 8_000_000 + ENV_CODE[task] * 100_000 + i
        job = official.EpisodeJob(task=task, episode=i, seed=seed, difficulty="xhard",
                                  worker_dir=f"{args.tmp}/episodes/{arm}_{task}_{seed}", gpu=args.gpu, repo_root=str(REPO))
        futs[ex.submit(probe_worker.run, (job, sampling[task], arm))] = (g, job)

    def fill():
        while len(futs) < args.workers:
            cands = [g for g in groups if st[g]["accepted"] + st[g]["pending"] < target[g] and st[g]["attempts"] < CAP[g]]
            if not cands:
                return
            g = min(cands, key=lambda g: (st[g]["accepted"] + st[g]["pending"]) / target[g])
            submit_one(g)

    fill()
    n = 0
    while futs:
        done, _ = wait(list(futs), return_when=FIRST_COMPLETED)
        for fut in done:
            g, job = futs.pop(fut)
            s = st[g]; s["pending"] -= 1; n += 1
            try:
                res = fut.result()
            except BaseException as exc:  # noqa: BLE001
                res = {"task": job.task, "episode": job.episode, "seed": job.seed, "ok": False, "arm": g[0],
                       "error_type": type(exc).__name__, "error": str(exc)}
            reset_ok = bool(res.get("trace"))
            res["reset_ok"] = reset_ok
            if reset_ok:
                s["accepted"] += 1
            with out.open("a") as fh:
                fh.write(json.dumps(res, ensure_ascii=False, default=str) + "\n")
            cap = res.get("capture") or {}
            print(f"[{n}] {g[0]} {job.task} seed={job.seed} reset_ok={reset_ok} ok={res.get('ok')} "
                  f"{res.get('error_type') or ''} {(res.get('error') or '')[:120]} steps={cap.get('elapsed_steps')} "
                  f"wall={res.get('wall_s')} acc={s['accepted']}/{target[g]} att={s['attempts']} t={time.time() - started:.0f}s",
                  flush=True)
        fill()
    ex.shutdown()
    print("SUMMARY " + json.dumps({f"{a}/{t}": st[(a, t)] for a, t in groups}), flush=True)
    print(f"DONE jobs={n} t={time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
