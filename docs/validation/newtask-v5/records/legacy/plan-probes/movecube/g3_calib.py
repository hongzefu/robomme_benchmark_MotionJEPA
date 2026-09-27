"""用 V4 G3 扫描的逐 seed 成败（step3b-movecube-insertpeg 报告三、5）校准「推杆起点距基座」代理量。"""
import sys, math
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import numpy as np
import torch
from mc_layout import simulate
from joint import push_starts
seeds = [910000, 910101, 910202, 910303, 910404, 910505, 910606, 910808]
fail = {0.25: {910606}, 0.5: {910202, 910404}, 0.75: {910404, 910606}, 1.0: {910404, 910505, 910606}}
ok_r, bad_r = [], []
for b in (0.0, 0.25, 0.5, 0.75, 1.0):
    for s in seeds:
        L = simulate(s, bias=b)
        if not L.ok:
            print(f"G3CAL b={b} seed={s} 模型布局失败 {L.fail}"); continue
        rs = []
        for seg in ("demo", "exec"):
            e = L.seg[seg]
            rp, rg, _ = push_starts(e["cube"], e["goal"])
            rs.append((rp, rg))
        f = s in fail.get(b, set())
        (bad_r if f else ok_r).append(max(r[0] for r in rs))
        print(f"G3CAL b={b} seed={s} way0={L.way_idx} {'FAIL' if f else 'ok  '} 推杆起点 demo={rs[0][0]:.3f} exec={rs[1][0]:.3f} 夹爪推起点 demo={rs[0][1]:.3f} exec={rs[1][1]:.3f} cube_demo={np.round(L.seg['demo']['cube'],3)} goal_demo={np.round(L.seg['demo']['goal'],3)} cube_exec={np.round(L.seg['exec']['cube'],3)} goal_exec={np.round(L.seg['exec']['goal'],3)}")
print(f"G3CAL 成功条目 max(推杆起点) 均值={np.mean(ok_r):.3f} 中位={np.median(ok_r):.3f}；失败条目 均值={np.mean(bad_r):.3f} 中位={np.median(bad_r):.3f} n_ok={len(ok_r)} n_fail={len(bad_r)}")
