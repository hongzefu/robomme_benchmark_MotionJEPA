"""核对：mc_lib 的向量化 SAT / 圆盘判据与仓库 object_generation 的原函数逐例一致（随机 20000 例）。"""
import numpy as np
from robomme.robomme_env.utils.object_generation import _obb2d_intersect, _build_new_cube_obb2d
from mc_lib import _sat_hit, cube_obb, board_strips, button
rng = np.random.default_rng(5)
bad = 0; tot = 0
for it in range(400):
    obs = [cube_obb(*rng.uniform(-0.2, 0.2, 2), rng.uniform(0, 6.3)) for _ in range(5)] + board_strips(*rng.uniform(-0.1, 0.1, 2)) + [button(rng)]
    x = rng.uniform(-0.3, 0.3, 50); y = rng.uniform(-0.3, 0.3, 50); yaw = rng.uniform(0, 6.3, 50)
    mine = _sat_hit(x, y, yaw, 0.04, obs)
    for i in range(50):
        c, A, h = _build_new_cube_obb2d(x[i], y[i], 0.02, yaw[i], pad_xy=0.02)
        ref = any(_obb2d_intersect(oc, oA, oh, c, A, h) for (oc, oA, oh) in obs)
        bad += ref != mine[i]; tot += 1
print(f"SAT_MATCH mismatch={bad}/{tot}")
