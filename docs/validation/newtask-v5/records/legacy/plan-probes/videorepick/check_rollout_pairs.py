# 用复刻布局 + 运行时同一规则（V4：3 发起者循环、XY 最近邻）离线推演 3 条正式局的交换搭档，与 rng_trace 实录比对
import sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from v4rep import v4_reset
from sim_lib import SweepCache, nn_order
for e, seed in [(0, 4900000), (3, 4900300), (6, 4900600)]:
    lay = v4_reset(seed)
    d = json.load(open(f"artifacts/newtask-v4/v4-01/rollout/run1/episodes/VideoRepick_episode_{e}/rng_trace.json"))
    real = [(int(c['drawn']['initiator'][4:]), int(c['drawn']['partner'][4:])) for c in d['calls'] if c['path'].startswith('actions.swap_pairs')]
    cache = SweepCache(lay["cubes"]); P = cache.P
    occ = list(range(6)); slot_of = list(range(6)); sim = []; rej = []
    t0 = time.time()
    for k in range(lay["n_swaps"]):
        a = lay["initiators_v4"][k % 3]; sa = slot_of[a]
        order, dist = nn_order(P, sa); sb = order[0]; b = occ[sb]
        sim.append((a, b)); rej.append(cache.rejected(sa, sb))
        occ[sa], occ[sb] = b, a; slot_of[a], slot_of[b] = sb, sa
    print(f"ep{e} seed{seed} match={sim == real} sim={sim}")
    print(f"   offline D5 sweep rejected per swap={['R' if r else '.' for r in rej]}  init_ok={cache.initial_ok()}  t={time.time()-t0:.2f}s")
    # 按槽位列出位置与最近邻
    for s in range(6):
        order, dist = nn_order(P, s)
        print(f"   slot{s} xy=({P[s,0]:+.3f},{P[s,1]:+.3f}) NN=slot{order[0]} d={dist[order[0]]:.3f}")
