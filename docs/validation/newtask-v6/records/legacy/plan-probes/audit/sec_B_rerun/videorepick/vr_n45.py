"""审计：VR 2.5 表 xhard1(4 块)/xhard2(5 块) reset 成功率在原报告 sweep_geom 中无 N=4/5 行，这里用同一复刻库补测。
口径与 sweep_geom.py 相同：规划成功上界 = 摆放成功 × 无孤立槽位；dmin=0.12、余量 5 mm、按钮作障碍、区域不变。种子固定 7_200_000+s。"""
import sys, os
sys.path.insert(0, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/plan-probes/videorepick")
import numpy as np, torch
torch.set_num_threads(1)
from multiprocessing import Pool
import vr6_lib as L

def work(job):
    N, seed, sw = job
    r = L.reset_sample(seed, n_cubes=N, dmin=0.12, swaps=sw)
    if not r["ok"]:
        return N, None
    M = L.feasibility_matrix(r["cubes"], r["button"])
    deg = M.sum(1)
    return N, (bool((deg == 0).any()), float(deg.mean()))

if __name__ == "__main__":
    K = int(sys.argv[1])
    SW = {4: (3, 5), 5: (5, 7), 6: (8, 12)}
    jobs = [(N, 7_200_000 + s, SW[N]) for N in (4, 5, 6) for s in range(K)]
    with Pool(10) as p:
        R = p.map(work, jobs, chunksize=8)
    for N in (4, 5, 6):
        rs = [o for n, o in R if n == N]
        pl = [o for o in rs if o is not None]
        place = len(pl) / len(rs); iso = np.mean([o[0] for o in pl]); deg = np.mean([o[1] for o in pl])
        print(f"VR_N{N} 局数={len(rs)} 摆放成功={place:.3f} 孤立槽位局={iso:.3f} 规划成功上界={place*(1-iso):.3f} 平均可行度={deg:.2f}")
