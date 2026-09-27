# 按钮在方块中心采样矩形里挖掉的面积比例（首块单次尝试被按钮拒绝的概率，含按钮位置抖动与随机 yaw）
import numpy as np
from robomme.robomme_env.utils.object_generation import _build_new_cube_obb2d, _obb2d_intersect, create_button_obb
rng = np.random.default_rng(0); hit = 0; M = 40000
for _ in range(M):
    bx, by = -0.2 + (rng.random() - 0.5) * 0.1, (rng.random() - 0.5) * 0.1
    ob = create_button_obb((bx, by), 0.025 * 1.5 * 1.5)
    x = -0.28 + rng.random() * 0.36; y = -0.23 + rng.random() * 0.46; yaw = rng.random() * 2 * np.pi
    hit += _obb2d_intersect(*ob, *_build_new_cube_obb2d(x, y, 0.02, yaw, pad_xy=0.02))
print(f"button exclusion fraction of center-sampling rectangle = {hit/M:.3f} (M={M})")
