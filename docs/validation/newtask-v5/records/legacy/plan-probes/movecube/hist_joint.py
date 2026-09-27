"""联合模拟下方块最终 xy 与 goal 的 Chebyshev 半径直方图（V4 b=0 / V4 b=0.5 / V5-b r=0.3 修复版）。"""
import sys, math
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import numpy as np
from mc_layout import simulate, CenterCfg
s = math.sqrt(0.3)
V5 = CenterCfg("square", s*0.05, s*0.11, s*0.06, s*0.1, "both")
N = 3000
bins_c = np.arange(0, 0.14, 0.01)
for lab, bias, cfg, avoid in (("V4 b=0", 0.0, None, True), ("V4 b=0.5", 0.5, None, True), ("V5-b r=0.3", 0.0, V5, False)):
    cube, gd, ge, peg = [], [], [], []
    for sd in range(4_000_000, 4_000_000 + N):
        L = simulate(sd, bias=bias, center=cfg, exec_avoid_demo=avoid)
        if not L.ok: continue
        for seg in ("demo", "exec"):
            cube.append(np.max(np.abs(L.seg[seg]["cube"])))
            peg.append(np.max(np.abs(L.seg[seg]["peg_root"] - np.array([0, np.sign(L.seg[seg]["peg_root"][1]) * 0.2]))))
        gd.append(np.max(np.abs(L.seg["demo"]["goal"]))); ge.append(np.max(np.abs(L.seg["exec"]["goal"])))
    h, _ = np.histogram(cube, bins=bins_c); h = h / len(cube) * 100
    print(f"HIST 方块最终 |xy|∞ ({lab}) 格宽1cm 0..13cm: " + " ".join(f"{v:4.1f}" for v in h) + f" | <5.48cm 占 {np.mean(np.array(cube)<s*0.1):.3f}")
    h, _ = np.histogram(gd, bins=np.arange(0, 0.12, 0.01)); h = h / len(gd) * 100
    print(f"HIST 演示 goal |xy|∞ ({lab}) 格宽1cm 0..11cm: " + " ".join(f"{v:4.1f}" for v in h) + f" | <6.02cm 占 {np.mean(np.array(gd)<s*0.11):.3f}")
    h, _ = np.histogram(ge, bins=np.arange(0, 0.07, 0.01)); h = h / len(ge) * 100
    print(f"HIST 执行 goal |xy|∞ ({lab}) 格宽1cm 0..6cm: " + " ".join(f"{v:4.1f}" for v in h) + f" | <3.29cm 占 {np.mean(np.array(ge)<s*0.06):.3f}")
    h, _ = np.histogram(peg, bins=np.arange(0, 0.06, 0.01)); h = h / len(peg) * 100
    print(f"HIST 杆根点相对车道中心 |dxy|∞ ({lab}) 格宽1cm 0..5cm: " + " ".join(f"{v:4.1f}" for v in h) + f" | <2.74cm 占 {np.mean(np.array(peg)<s*0.05):.3f}")
