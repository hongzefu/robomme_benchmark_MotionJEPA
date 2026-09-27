"""面积比 r 扫描（推荐结构：bias 0、中心方、方块候选+最终都判、执行段不避让演示方块），外加「只判最终」反例。"""
import sys, math
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import numpy as np
from mc_layout import simulate, CenterCfg, HS, _obb, _sat
from joint import push_starts, peg_boxes
N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
def run(label, bias, cfg, avoid):
    fails = {}; draws = []; rp = []; cinf = []; ov = 0; segs = 0; rej = {}
    for s in range(3_000_000, 3_000_000 + N):
        L = simulate(s, bias=bias, center=cfg, exec_avoid_demo=avoid)
        if not L.ok:
            fails[L.fail] = fails.get(L.fail, 0) + 1; continue
        draws.append(L.draws)
        for k, v in L.rejects.items(): rej[k] = rej.get(k, 0) + v
        for seg in ("demo", "exec"):
            e = L.seg[seg]; segs += 1
            rp.append(push_starts(e["cube"], e["goal"])[0]); cinf.append(np.max(np.abs(e["cube"])))
            cb = _obb(e["cube"][0], e["cube"][1], HS, e["cube_yaw"])
            ov += any(_sat(*cb, *p) for p in peg_boxes(e["peg_root"], e["peg_yaw"]))
    d = np.array(draws); rp = np.array(rp); ok = len(draws)
    print(f"SWEEP {label:<40} 布局成功={ok}/{N} 失败={fails} 随机调用 均值={d.mean():.2f} p99={np.percentile(d,99):.0f} max={d.max()} "
          f"中心重抽/局={sum(rej.values())/ok:.2f} 方块E[|xy|∞]={np.mean(cinf):.4f} 推杆起点>0.80={np.mean(rp>0.80):.3f} 杆-方块重叠/段={ov/segs:.4f}", flush=True)
run("V4 b=0.5 现行（执行段避让）", 0.5, None, True)
run("V4 b=0.5 + 仅修执行段不避让", 0.5, None, False)
run("V4 b=0（均匀）+ 不避让", 0.0, None, False)
for r in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
    s = math.sqrt(r)
    run(f"V5 面积比 r={r}（w=√r·半边）", 0.0, CenterCfg("square", s*0.05, s*0.11, s*0.06, s*0.1, "both"), False)
s = math.sqrt(0.3)
run("反例：r=0.3 只判最终 xy（候选不判）", 0.0, CenterCfg("square", s*0.05, s*0.11, s*0.06, s*0.1, "final"), False)
run("反例：r=0.3 只判候选（最终会漏）", 0.0, CenterCfg("square", s*0.05, s*0.11, s*0.06, s*0.1, "cand"), False)
