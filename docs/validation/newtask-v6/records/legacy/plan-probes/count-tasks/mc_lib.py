"""V6 规划探针：四个计数类环境 xhard 摆放的离线蒙特卡洛复刻（纯 numpy，向量化，不进仿真器）。

复刻对象（只读源码，逐式对照）：
* ``utils/object_generation.py::spawn_random_cube``：区域按方块半边长内缩；每 trial 抽 (u1,u2,yaw)；
  新方块 OBB 半边 = half + min_gap，与障碍逐个做 SAT（接触算相交）；再判中心距规则；首个可行 trial 被接受。
* ``spawn_random_target``：圆盘中心在「区域 − 半径」内均匀；与 OBB 取最近点距离 < radius + min_gap 即拒；
  与已放圆盘按圆–圆判（R_c + radius + min_gap）。
* ``build_button`` / ``create_button_obb``：中心 (-0.2,0)+(u-0.5)*(0.1,0.4)，障碍是轴对齐正方形，半边 0.025*1.5*1.5=0.05625。
* 已放方块作障碍一律用精确 OBB（V5 ``cube_obb2d_exact``，half=0.02，无外扩）。

与源码的差别：随机数用 numpy（分布相同、不追求与 torch 流逐位一致）；一次抽满 max_trials 个候选、
取第一个可行者（与逐次拒绝在分布上完全等价）。统计口径：reset 成功＝所有物体都在各自预算内放下。
"""
import numpy as np

HS = 0.02
BTN_HALF = 0.025 * 1.5 * 1.5


def button(rng):
    u = rng.random(2) - 0.5
    c = np.array([-0.2 + u[0] * 0.1, 0.0 + u[1] * 0.4])
    return (c, np.eye(2), np.array([BTN_HALF, BTN_HALF]))


def board_strips(bx, by):
    """BinFill 孔板四条边（轴对齐，pad=0；与 _board_strips_obb2d 同式，板本身的 yaw 不进障碍）。"""
    bh, hh = 0.05, 0.04
    th = bh - hh
    c = np.array([bx, by])
    I = np.eye(2)
    return [
        (c + [0, hh + th / 2], I, np.array([bh, th / 2])),
        (c + [0, -(hh + th / 2)], I, np.array([bh, th / 2])),
        (c + [-(hh + th / 2), 0], I, np.array([th / 2, hh])),
        (c + [hh + th / 2, 0], I, np.array([th / 2, hh])),
    ]


def cube_obb(x, y, yaw, half=HS, pad=0.0):
    cs, sn = np.cos(yaw), np.sin(yaw)
    return (np.array([x, y]), np.array([[cs, -sn], [sn, cs]]), np.array([half + pad, half + pad]))


def _sat_hit(cx, cy, yaw, hp, obs):
    """候选（向量 T 个）与障碍列表是否相交，返回 (T,) bool。候选半边 hp（标量）。"""
    T = cx.shape[0]
    hit = np.zeros(T, bool)
    if not obs:
        return hit
    C = np.array([o[0] for o in obs])          # (M,2)
    A = np.array([o[1] for o in obs])          # (M,2,2) 列为轴
    H = np.array([o[2] for o in obs])          # (M,2)
    cs, sn = np.cos(yaw), np.sin(yaw)
    ca = np.stack([np.stack([cs, sn], -1), np.stack([-sn, cs], -1)], 1)  # (T,2 轴,2)
    d = np.stack([cx, cy], -1)[:, None, :] - C[None]                     # (T,M,2)
    oa = np.transpose(A, (0, 2, 1))                                     # (M,2 轴,2)
    sep = np.zeros((T, len(obs)), bool)
    # 候选的两根轴
    for k in range(2):
        a = ca[:, k, :][:, None, :]                                     # (T,1,2)
        r1 = hp  # 候选在自己轴上的投影半径
        r2 = np.abs((oa[None, :, 0, :] * a).sum(-1)) * H[None, :, 0] + np.abs((oa[None, :, 1, :] * a).sum(-1)) * H[None, :, 1]
        dist = np.abs((d * a).sum(-1))
        sep |= dist > (r1 + r2)
    # 障碍的两根轴
    for k in range(2):
        a = oa[None, :, k, :]                                           # (1,M,2)
        r2 = H[None, :, k]
        r1 = (np.abs((ca[:, None, 0, :] * a).sum(-1)) + np.abs((ca[:, None, 1, :] * a).sum(-1))) * hp
        dist = np.abs((d * a).sum(-1))
        sep |= dist > (r1 + r2)
    return (~sep).any(1)


def place_cube(rng, obs, region_center, region_half, min_gap, max_trials,
               centers=None, min_center_dist=None, half=HS):
    """spawn_random_cube 的复刻；成功返回 (x,y,yaw,trial_idx)，失败返回 None。"""
    rc = np.asarray(region_center, float)
    rh = np.asarray(region_half, float) * np.ones(2)
    xl, xh = rc[0] - rh[0] + half, rc[0] + rh[0] - half
    yl, yh = rc[1] - rh[1] + half, rc[1] + rh[1] - half
    u = rng.random((max_trials, 3))
    x = xl + u[:, 0] * (xh - xl)
    y = yl + u[:, 1] * (yh - yl)
    yaw = u[:, 2] * 2 * np.pi
    ok = ~_sat_hit(x, y, yaw, half + min_gap, obs)
    if centers is not None and min_center_dist is not None and len(centers):
        P = np.asarray(centers)
        dd = np.linalg.norm(np.stack([x, y], -1)[:, None, :] - P[None], axis=-1)
        ok &= (dd >= min_center_dist).all(1)
    idx = np.flatnonzero(ok)
    if len(idx) == 0:
        return None
    i = idx[0]
    return float(x[i]), float(y[i]), float(yaw[i]), int(i)


def place_disk(rng, obs, circles, region_center, region_half, radius, min_gap, max_trials=256):
    """spawn_random_target 的复刻（random_yaw 恒 False，每 trial 两个数）。"""
    rc = np.asarray(region_center, float)
    xl, xh = rc[0] - region_half + radius, rc[0] + region_half - radius
    yl, yh = rc[1] - region_half + radius, rc[1] + region_half - radius
    u = rng.random((max_trials, 2))
    P = np.stack([xl + u[:, 0] * (xh - xl), yl + u[:, 1] * (yh - yl)], -1)
    R = radius + min_gap
    ok = np.ones(max_trials, bool)
    for (c, A, h) in obs:
        loc = (P - c) @ A           # A 列为轴 ⇒ 局部坐标 = A^T (p-c)
        cl = np.clip(loc, -h, h)
        w = c + cl @ A.T
        ok &= np.linalg.norm(P - w, axis=1) >= R
    for (xy, rr) in circles:
        ok &= np.linalg.norm(P - xy, axis=1) >= R + rr
    idx = np.flatnonzero(ok)
    if len(idx) == 0:
        return None
    return P[idx[0]]
