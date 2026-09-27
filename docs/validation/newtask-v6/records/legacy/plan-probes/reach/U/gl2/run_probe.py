#!/usr/bin/env python3
"""探针 C 运行器：仿 scripts/parity/train_split_runner.py（官方编排 + 工作副本 src + 镜像 worker 回注规格）。
用法：python run_probe.py --gpu 0 --workers 3
"""
import argparse
import json
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
import os
REPO = Path(os.environ.get("PROBE_REPO", HERE.parents[4]))
OFFICIAL = REPO / "artifacts/train-parity/local-smoke-01/official-src/scripts/data-generation"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dir", default=str(HERE))
    args = ap.parse_args()
    for p in (str(OFFICIAL), str(REPO / "scripts" / "parity"), str(HERE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    import generate_dataset as official
    import probe_worker
    D = Path(args.dir)
    sampling = json.loads((D / "sampling.json").read_text())["tasks"]["MoveCube"]
    specs = json.loads((D / "specs.json").read_text())["specs"]
    items = json.loads((D / f"jobs_gpu{args.gpu}.json").read_text())[: args.limit]
    jobs = [official.EpisodeJob(task=i["task"], episode=i["episode"], seed=i["seed"], difficulty=i["difficulty"],
                                worker_dir=i["worker_dir"], gpu=str(args.gpu), repo_root=str(REPO)) for i in items]
    out = D / f"results_gpu{args.gpu}.jsonl"
    started = time.time()
    with ProcessPoolExecutor(max_workers=min(args.workers, len(jobs)), mp_context=mp.get_context("spawn")) as ex:
        futs = {ex.submit(probe_worker.run, (j, sampling, specs[f"MoveCube/{j.episode}"])): j for j in jobs}
        for n, fut in enumerate(as_completed(futs), 1):
            j = futs[fut]
            try:
                res = fut.result()
            except BaseException as exc:  # noqa: BLE001
                res = {"task": j.task, "episode": j.episode, "seed": j.seed, "ok": False,
                       "error_type": type(exc).__name__, "error": str(exc)}
            res.pop("traceback", None) if res.get("ok") else None
            with out.open("a") as fh:
                fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            print(f"[{n}/{len(jobs)}] ep={j.episode} ok={res.get('ok')} {res.get('error_type') or ''} "
                  f"{(res.get('error') or '')[:150]} steps={res.get('probe', {}).get('elapsed_steps')} "
                  f"wall={res.get('wall_s')} t={time.time() - started:.0f}s", flush=True)
    print(f"DONE gpu={args.gpu} jobs={len(jobs)} t={time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
