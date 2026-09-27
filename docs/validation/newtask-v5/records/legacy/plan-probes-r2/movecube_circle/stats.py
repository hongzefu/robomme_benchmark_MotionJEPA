"""V5 规则离线统计：seed 2_000_000 起 N 局（每局含演示段 + 执行段各一套布局）。
口径 A（主）：计划 2.9 的杆段 root−0.075u…root+0.025u；口径 B（对照）：模拟器实测杆段 root−0.15u…root+0.05u。
R ∈ {0.04, 0.05, 0.06}。"""
import sys, math, json, time
sys.path.insert(0, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v5/plan-probes-r2/movecube_circle")
import numpy as np
from mc_v5 import simulate, POINTS, seg_dist
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
S0 = 2_000_000
OUT = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v5/plan-probes-r2/movecube_circle/stats.json"
SEGS = {"A_plan": (-0.075, 0.025), "B_phys": (-0.15, 0.05)}
ANALYTIC = {"goal_demo": lambda r: math.pi * r * r / 0.22 ** 2, "goal_exec": lambda r: math.pi * r * r / 0.12 ** 2,
            "cand_demo": lambda r: math.pi * r * r / 0.2 ** 2, "cand_exec": lambda r: math.pi * r * r / 0.2 ** 2}
summary = {}

# 基线：无禁区、bias 0、执行段不避让（= V5 去掉 corner_bias 与禁区）：最终布局里各物体中心落进圆的比例
for R in (0.04, 0.05, 0.06):
    cnt = {"goal_demo": 0, "goal_exec": 0, "cube_demo": 0, "cube_exec": 0, "pegA_demo": 0, "pegA_exec": 0,
           "pegB_demo": 0, "pegB_exec": 0, "any_A": 0}
    draws = []
    for s in range(S0, S0 + N):
        L = simulate(s, bias=0.0, R=None, exec_avoid_demo=False)
        draws.append(L.draws)
        anyin = False
        for sg in ("demo", "exec"):
            e = L.seg[sg]
            for k, v in (("goal", np.linalg.norm(e["goal"])), ("cube", np.linalg.norm(e["cube"])),
                         ("pegA", seg_dist(e["peg_root"], e["peg_yaw"], *SEGS["A_plan"])),
                         ("pegB", seg_dist(e["peg_root"], e["peg_yaw"], *SEGS["B_phys"]))):
                cnt[f"{k}_{sg}"] += v < R
                if k != "pegB" and v < R:
                    anyin = True
        cnt["any_A"] += anyin
    summary[f"base_R{R}"] = {k: v / N for k, v in cnt.items()}
    print(f"BASE 无禁区 bias0 R={R}: 最终中心落圆比例 " + " ".join(f"{k}={v/N:.3f}" for k, v in cnt.items()), flush=True)
bd = np.array(draws)
summary["base_draws"] = dict(mean=float(bd.mean()), p99=float(np.percentile(bd, 99)), max=int(bd.max()))
print(f"BASE 随机调用 均值={bd.mean():.2f} p99={np.percentile(bd,99):.0f} max={bd.max()}", flush=True)

for segname, pseg in SEGS.items():
    for R in (0.04, 0.05, 0.06):
        t = time.time()
        fails = {}; redraw = []; draws = []; rej = {p: 0 for p in POINTS}; att = {p: 0 for p in POINTS}
        raw_in = {p: 0 for p in POINTS}; raw_n = {p: 0 for p in POINTS}; ppmax = {p: 0 for p in POINTS}
        viol = 0; pegd = []
        for s in range(S0, S0 + N):
            L = simulate(s, bias=0.0, R=R, peg_seg=pseg)
            for p in POINTS:
                rej[p] += L.rej[p]; att[p] += L.att[p]; raw_in[p] += L.raw_in[(p, R)]; raw_n[p] += L.raw_n[p]
                ppmax[p] = max(ppmax[p], L.rej[p])
            if not L.ok:
                fails[L.fail] = fails.get(L.fail, 0) + 1; continue
            redraw.append(sum(L.rej.values())); draws.append(L.draws)
            for sg in ("demo", "exec"):
                e = L.seg[sg]
                pd = seg_dist(e["peg_root"], e["peg_yaw"], *pseg); pegd.append(pd)
                viol += (np.linalg.norm(e["goal"]) < R) + (np.linalg.norm(e["cube"]) < R) + (pd < R)
        rd = np.array(redraw); dr = np.array(draws)
        rate = {p: (rej[p] / att[p] if att[p] else 0.0) for p in POINTS}
        rawrate = {p: raw_in[p] / raw_n[p] for p in POINTS}
        exh = {p: rate[p] ** 128 for p in POINTS}
        key = f"{segname}_R{R}"
        summary[key] = dict(N=N, layout_fail=sum(fails.values()), fails=fails, mean_redraw=float(rd.mean()),
                            p50_redraw=float(np.percentile(rd, 50)), p99_redraw=float(np.percentile(rd, 99)), max_redraw=int(rd.max()),
                            hist_redraw={int(k): int(v) for k, v in zip(*np.unique(rd, return_counts=True))},
                            draws_mean=float(dr.mean()), draws_p99=float(np.percentile(dr, 99)), draws_max=int(dr.max()),
                            rate=rate, rawrate=rawrate, per_point_max=ppmax, exhaust_est=exh, exhaust_sum=float(sum(exh.values())),
                            zone_violations=int(viol), peg_min_dist=float(min(pegd)))
        print(f"[{key}] 局数={N} layout_fail={sum(fails.values())} {fails} 每局重抽 均值={rd.mean():.3f} p50={np.percentile(rd,50):.0f} "
              f"p99={np.percentile(rd,99):.0f} max={rd.max()} 随机调用 均值={dr.mean():.2f} p99={np.percentile(dr,99):.0f} max={dr.max()} "
              f"禁区违规={viol} 杆段最近={min(pegd):.4f} 耗尽估计合计={sum(exh.values()):.1e} ({time.time()-t:.0f}s)", flush=True)
        for p in POINTS:
            an = ANALYTIC.get(p)
            print(f"   {p:<10} 拒绝率(检查口径)={rate[p]:.4f} 原始抽样落圆={rawrate[p]:.4f} 解析={an(R) if an else float('nan'):.4f} "
                  f"单局最多重抽={ppmax[p]} rate^128={exh[p]:.1e}", flush=True)
json.dump(summary, open(OUT, "w"), ensure_ascii=False, indent=1, default=float)
print("STATS_DONE")
