# V4 Swap 两环境的线性可见近似 vs 精确 8 角点针孔：哪些已冻结干扰容器其实出画/贴边
import sys, json, math
import numpy as np
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S)
import ringlib as L
pos = json.load(open(f"{S}/specs_positions.json"))
for t in ["VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap"]:
    D = np.array(pos[t]["distractors"])
    ex = L.vis_center_exact(D[:, 0], D[:, 1])
    # 各点 8 角点投影的最大越界像素
    worst = []
    for x, y in D:
        us, vs = [], []
        for sx in (-1, 1):
            for sy in (-1, 1):
                for z in (0, L.HEIGHT):
                    u, v, _ = L.project([x + sx * L.REACH, y + sy * L.REACH, z]); us.append(u); vs.append(v)
        worst.append(max(-min(us), max(us) - 256, -min(vs), max(vs) - 256))
    worst = np.array(worst)
    print(t, "exact-visible", int(ex.sum()), "/", len(D), " max overshoot px (any-yaw square)", np.round(worst.max(), 1),
          " points with overshoot>0:", [(round(a, 3), round(b, 3), round(w, 1)) for (a, b), w in zip(D, worst) if w > 0])
# 线性近似在哪里比精确判据宽：在 x 取不同值处，两判据的可见 |y| 上限
for x in [-0.7, -0.6, -0.45, -0.3, -0.2, 0.0, 0.2, 0.3, 0.35, 0.38]:
    ys = np.linspace(0, 1, 10001)
    e = ys[L.vis_center_exact(np.full_like(ys, x), ys)]
    s = ys[L.vis_center_swap(np.full_like(ys, x), ys)]
    print(f"x={x:+.2f}: center |y| max exact={e.max() if e.size else float('nan'):.3f}  swap-approx={s.max() if s.size else float('nan'):.3f}")
