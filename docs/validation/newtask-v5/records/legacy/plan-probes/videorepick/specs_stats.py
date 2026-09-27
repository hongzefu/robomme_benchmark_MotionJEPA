# 10 条 V4 冻结候选的均匀性与交换覆盖（离线复刻，已逐位核对）+ 2400 局参与块数分布
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from v4rep import v4_reset
from sim_lib import SweepCache, run_episode
from big_sim import uni_metrics
rows = [json.loads(l) for l in open("scripts/configs/newtask-v4/v4-01/specs.jsonl") if '"task":"VideoRepick"' in l and '"record":"spec"' in l]
print("ep seed sel n_swaps | nn_mean min_pair CE_R clump3 max_cell side_min far_half | S0: participants never_moved first_rej target_home distinct_pairs | S1(all-cycle NN): participants")
agg = collections.Counter()
for r in rows:
    lay = v4_reset(r["seed"]); P = np.array([[c[0], c[1]] for c in lay["cubes"]]); u = uni_metrics(P)
    cache = SweepCache(lay["cubes"]); rng = np.random.default_rng(0)
    n = lay["n_swaps"]
    e0 = run_episode(lay["cubes"], lay["target"], n, [lay["initiators_v4"][k % 3] for k in range(n)], "nn", rng, cache=cache)
    e1 = run_episode(lay["cubes"], lay["target"], n, [lay["initiators_all"][k % 6] for k in range(n)], "nn", rng, cache=cache)
    agg[e0["participants"]] += 1
    print(f"{r['episode']} {r['seed']} {int(r['selected'])} {n:2d} | {u['nn_mean']:.3f} {u['min_pair']:.3f} {u['ce_R']:.2f} {int(u['clump3'])} {u['max_cell']} {u['side_min']} {u['far_half']} | {e0['participants']} {6-e0['participants']} {e0['first_rej']} {int(e0['target_home'])} {e0['distinct_pairs']} | {e1['participants']} first_rej={e1['first_rej']}")
print("10 条候选 S0 参与块数分布:", dict(sorted(agg.items())))
R = json.load(open(os.path.join(os.path.dirname(__file__), "big_sim_2400.json")))
for sc in ["S0_v4_3init_nn", "S6_iid_init_nn", "S5_random_pair"]:
    c = collections.Counter(R[s]["v4"]["schemes"][sc]["participants"] for s in R)
    print(f"2400 局 v4 布局 {sc} 参与块数分布:", {k: f"{100*v/len(R):.1f}%" for k, v in sorted(c.items())})
c = collections.Counter(R[s]["v4"]["nn_comp"] for s in R)
print("2400 局 v4 布局 最近邻图连通分量数分布:", {k: f"{100*v/len(R):.1f}%" for k, v in sorted(c.items())})
