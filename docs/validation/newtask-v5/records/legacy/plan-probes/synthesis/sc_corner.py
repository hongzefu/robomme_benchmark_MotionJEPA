# 抽查：corner_push(b=0.5) 在无障碍、无拒绝时 3 块共享角格的概率（对照：均匀）
import numpy as np
from robomme.robomme_env.utils.xhard import corner_push
rng = np.random.default_rng(1)
N = 200000
def cells(u):
    return np.minimum((u * 3).astype(int), 2)
for b in (0.0, 0.5):
    u = rng.random((N, 3, 2))
    if b:
        f = np.vectorize(lambda v: corner_push(v, b)); u = f(u)
    cx, cy = cells(u[..., 0]), cells(u[..., 1])
    corner = (cx != 1) & (cy != 1)
    cid = cx * 3 + cy
    share = np.zeros(N, bool)
    for i in range(3):
        for j in range(i + 1, 3):
            share |= corner[:, i] & corner[:, j] & (cid[:, i] == cid[:, j])
    print(f"b={b}: in-corner={corner.mean():.3f}  share_corner_cell>=2={share.mean():.3f}")
