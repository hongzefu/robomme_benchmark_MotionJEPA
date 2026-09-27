"""vp_layout_mc 的按配置并行入口：vp_layout_mc_cfg.py <env> <n_seeds> <goal_avoid 0/1> <half> <cubes> <targets,...>
每个配置输出一行 RESULT json，便于并行跑后汇总。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vp_layout_mc import layout
env, N, ga, half, n = sys.argv[1], int(sys.argv[2]), bool(int(sys.argv[3])), float(sys.argv[4]), int(sys.argv[5])
for T in map(int, sys.argv[6].split(",")):
    fails = {}; ok = 0
    for k in range(N):
        r = layout(env, 5000000 + k, n, T, ga, half)
        ok += r == "ok"
        if r != "ok": fails[r] = fails.get(r, 0) + 1
    print("RESULT " + json.dumps(dict(env=env, goal_avoid=ga, half=half, cubes=n, targets=T, n=N, ok_rate=ok / N, fails=fails)), flush=True)
