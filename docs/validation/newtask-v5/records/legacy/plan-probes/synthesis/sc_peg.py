# 抽查：InsertPeg V4 第 4 根杆（距目标杆根 0.075~0.085、方位均匀、两杆 yaw ±180°）与目标杆足迹重叠率
import numpy as np
rng = np.random.default_rng(7); N = 200000
L, R = 0.05, 0.01
def rect(root, yaw):
    u = np.stack([np.cos(yaw), np.sin(yaw)], -1); n = np.stack([-u[:, 1], u[:, 0]], -1)
    c = root - 0.5 * L * u            # 足迹中心 = root - length/2·u，半长 length=0.05，半宽 0.01
    return c, u, n
def overlap(c1, u1, n1, c2, u2, n2):
    ok = np.ones(len(c1), bool)
    for ax in (u1, n1, u2, n2):
        p1 = np.abs(np.sum(u1 * ax, 1)) * L + np.abs(np.sum(n1 * ax, 1)) * R
        p2 = np.abs(np.sum(u2 * ax, 1)) * L + np.abs(np.sum(n2 * ax, 1)) * R
        d = np.abs(np.sum((c2 - c1) * ax, 1))
        ok &= d <= p1 + p2
    return ok
r = rng.uniform(0.075, 0.085, N); th = rng.uniform(0, 2 * np.pi, N)
root0 = np.zeros((N, 2)); root3 = np.stack([r * np.cos(th), r * np.sin(th)], -1)
y0 = rng.uniform(-np.pi, np.pi, N); y3 = rng.uniform(-np.pi, np.pi, N)
print("P(overlap peg0,peg3 | V4 band) =", overlap(*rect(root0, y0), *rect(root3, y3)).mean().round(4))
# 对照：根距恰 0.075 ⇒ 仍可能重叠；根距 >0.1513 才能保证不重叠
for d in (0.10, 0.15, 0.152):
    root3 = np.stack([np.full(N, d), np.zeros(N)], -1)
    print(f"root dist {d}: P(overlap) =", overlap(*rect(root0, y0), *rect(root3, y3)).mean().round(4))
