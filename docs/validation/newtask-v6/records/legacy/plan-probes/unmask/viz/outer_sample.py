"""图 5 的补充采样：每局逐窗重算外环 G_k（与 p3_outer_mc 同口径：V5 内环序列 + 仓库 evaluate_outer_candidate），
记录每窗可行槽对数、每窗每槽的可行搭档数、槽坐标。用法：outer_sample.py <task> <N> [procs]"""
import json, multiprocessing as mp, sys, time
import numpy as np
import vizlib as V
from episode import build_episode, outer_window_graph


def one(args):
    task, seed = args
    ep = build_episode(task, seed, 10)
    if ep is None:
        return None
    cache = {}; wins = []
    for k, w in enumerate(ep["wins"]):
        key = tuple(sorted((tuple(np.round(w.states[w.a].p[:2], 6)), tuple(np.round(w.states[w.b].p[:2], 6)))))
        if key not in cache:
            cache[key] = outer_window_graph(ep, k)
        g = cache[key]
        deg = [0] * 10
        for (a, b), f in g.items():
            if f: deg[a] += 1; deg[b] += 1
        wins.append(dict(nfeas=int(sum(g.values())), deg=deg))
    return dict(seed=seed, xy=[st.p[:2].round(4).tolist() for st in ep["outer"]], wins=wins)


if __name__ == "__main__":
    task = sys.argv[1]; N = int(sys.argv[2]); procs = int(sys.argv[3]) if len(sys.argv) > 3 else 28
    base = 9_700_000 if task == "VideoUnmaskSwap" else 9_800_000
    t0 = time.time()
    with mp.Pool(procs) as pool:
        res = [r for r in pool.imap_unordered(one, [(task, base + i) for i in range(N)], chunksize=2) if r]
    json.dump(res, open(V.HERE / f"outer_sample_{task}.json", "w"))
    print(f"OUTER_SAMPLE_DONE task={task} N={len(res)} wall={time.time()-t0:.1f}s")
