# 议题 3：演示帧数模型拟合。数据 = v5-01 三局 h5（录像帧，不含 NO RECORD）+ s3g 本机演示 7 局的环境控制步（含 NO RECORD）
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, torch
S3G = {4900300: 1732, 4900100: 1837, 4900400: 1644, 4900700: 1729, 4900200: 1533, 7000000: 1630, 7000001: 2112}
rows = []
for seed, steps in S3G.items():
    g = torch.Generator(); g.manual_seed(seed)
    r = torch.randint(4, 7, (1,), generator=g).item(); n = torch.randint(8, 13, (1,), generator=g).item()
    rows.append((seed, n, r, steps))
X = np.array([[1, n, r] for _, n, r, _ in rows], float); y = np.array([s for *_, s in rows], float)
# 交换段每次恰 50 控制步（_refresh_swap_schedule），固定该系数，只拟合截距与每次 repick 的步数
coef, *_ = np.linalg.lstsq(X[:, [0, 2]], y - 50 * X[:, 1], rcond=None)
pred = X[:, 0] * coef[0] + 50 * X[:, 1] + X[:, 2] * coef[1]
for (seed, n, r, s), p in zip(rows, pred):
    print(f"seed {seed}: n_swaps={n} repeats={r} 控制步={s} 拟合={p:.0f} 残差={s-p:+.0f}")
print(f"环境控制步 ≈ {coef[0]:.0f} + 50·n_swaps + {coef[1]:.0f}·repeats；残差最大 {np.abs(y-pred).max():.0f}")
H = json.load(open("h5_frames.json"))
for p, d in H.items():
    print(p.split("/")[-1], "h5 总帧", d["total"], "演示帧", d["demo"], "非演示帧", d["nondemo"])
