# 仿真实录 vs 离线复刻：逐段搭档、D5 结果、交换开始时各块相对生成槽位的位移
import sys, os, json, math
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from v4rep import v4_reset
from sim_lib import SweepCache, nn_order
log = json.load(open(sys.argv[1]))
recs = [r for r in log if "sweep_index" in r]
by = {}
for r in recs:
    by.setdefault(r["seed"], []).append(r)
agree_pair = agree_rej = total = 0; disp_t, disp_o, dyaw_t = [], [], []
for seed, rs in by.items():
    lay = v4_reset(seed); cache = SweepCache(lay["cubes"]); P = cache.P
    occ = list(range(6)); slot_of = list(range(6)); pred = []
    for k in range(lay["n_swaps"]):
        a = lay["initiators_v4"][k % 3]; sa = slot_of[a]; order, _ = nn_order(P, sa); sb = order[0]; b = occ[sb]
        pred.append((a, b, cache.rejected(sa, sb), sa, sb)); occ[sa], occ[sb] = b, a; slot_of[a], slot_of[b] = sb, sa
    occ = list(range(6)); slot_of = list(range(6))
    for r in sorted(rs, key=lambda x: x["sweep_index"]):
        k = r["sweep_index"]; a, b, rej, sa, sb = pred[k]
        total += 1; agree_pair += (a, b) == (r["a"], r["b"]); agree_rej += rej == r["rejected"]
        # 位移：当前每块应在的槽位 vs 实际位置
        for c in range(6):
            s = slot_of[c]; p = np.array(r["poses"][c][:2]); d = float(np.linalg.norm(p - P[s]))
            (disp_t if c == lay["target"] else disp_o).append(d)
        q = r["poses"][lay["target"]][3:]; yaw_act = 2 * math.atan2(q[3], q[0])
        yaw_slot = lay["cubes"][slot_of[lay["target"]]][2]
        dyaw_t.append(abs((yaw_act - yaw_slot + math.pi / 4) % (math.pi / 2) - math.pi / 4))
        print(f"seed={seed} k={k} actual=({r['a']},{r['b']}) rej={r['rejected']}  offline=({a},{b}) rej={rej}")
        occ[sa], occ[sb] = b, a; slot_of[a], slot_of[b] = sb, sa
print(f"PAIR_AGREE={agree_pair}/{total} D5_AGREE={agree_rej}/{total}")
print(f"target displacement at swap start: max={max(disp_t)*1000:.1f}mm median={np.median(disp_t)*1000:.1f}mm; others max={max(disp_o)*1000:.2f}mm")
print(f"target yaw change (mod 90deg) median={np.degrees(np.median(dyaw_t)):.1f}deg max={np.degrees(max(dyaw_t)):.1f}deg")
