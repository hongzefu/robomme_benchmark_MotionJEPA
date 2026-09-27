"""V5 候选摆放方法（与 V4 同一 torch 随机流协议：button→颜色→逐块；只在 xhard 生效）。

U0 v4        : 现状，整片矩形均匀拒绝采样（OBB+min_gap 0.02，障碍 OBB 常退化）
U1 hc<d>     : U0 + 中心距硬下限 d（Poisson-disk 式飞镖投掷）
U2 bc<K>     : 最佳候选（Mitchell）：每块先用 U0 判据接受 K 个候选，取「到已放方块中心最近距离」最大者
U3 grid6of8  : 抖动网格：区域 2(x)×4(y) 共 8 格，去掉按钮所在的近端中间 2 格，剩 6 格；randperm 分配格子，格内均匀+U0 判据
CSR          : 对照——6 个 iid 均匀点（无硬核、无按钮）
"""
import numpy as np, torch
from robomme.robomme_env.utils.object_generation import _build_new_cube_obb2d, _obb2d_intersect, create_button_obb
from robomme.robomme_env.utils.xhard import hsv_floor_rgb, HSV_FLOOR_COLOR
from v4rep import cube_obb2d_like_actor, HS, REGION_CENTER, REGION_HALF, BTN_CENTER, BTN_RANGE, BTN_OBB_HALF

XL = REGION_CENTER[0] - REGION_HALF[0] + HS; XH = REGION_CENTER[0] + REGION_HALF[0] - HS
YL = REGION_CENTER[1] - REGION_HALF[1] + HS; YH = REGION_CENTER[1] + REGION_HALF[1] - HS


def _head(seed):
    g = torch.Generator(); g.manual_seed(seed)
    num_repeats = torch.randint(4, 7, (1,), generator=g).item()
    n_swaps = torch.randint(8, 13, (1,), generator=g).item()
    off = torch.rand(2, generator=g) - 0.5
    bx = BTN_CENTER[0] + float(off[0]) * BTN_RANGE[0]; by = BTN_CENTER[1] + float(off[1]) * BTN_RANGE[1]
    torch.rand(3, generator=g)  # 颜色
    return g, num_repeats, n_swaps, (bx, by)


def _trial(g, box, obb_list, placed, dmin):
    """一次尝试：抽 x,y,yaw（与 spawn_random_cube 同三次 rand），返回 (x,y,yaw) 或 None。"""
    xl, xh, yl, yh = box
    u1 = torch.rand(1, generator=g).item(); u2 = torch.rand(1, generator=g).item()
    x = float(xl + u1 * (xh - xl)); y = float(yl + u2 * (yh - yl))
    yaw = float(torch.rand(1, generator=g).item() * 2 * np.pi)
    c_new, A_new, h_new = _build_new_cube_obb2d(x, y, HS, yaw, pad_xy=HS)
    if any(_obb2d_intersect(c, A, h, c_new, A_new, h_new) for (c, A, h) in obb_list):
        return None
    if dmin and placed and min(np.hypot(x - p[0], y - p[1]) for p in placed) < dmin:
        return None
    return (x, y, yaw)


def place(seed, method, n=6, max_trials=256):
    g, num_repeats, n_swaps, btn = _head(seed)
    obb_list = [create_button_obb(center_xy=btn, half_size=BTN_OBB_HALF)]
    placed, trials_total = [], 0
    full = (XL, XH, YL, YH)
    if method == "CSR":
        rng = np.random.default_rng(seed)
        pts = [(float(rng.uniform(XL, XH)), float(rng.uniform(YL, YH)), float(rng.uniform(0, 2 * np.pi))) for _ in range(n)]
        return dict(ok=True, cubes=pts, button=btn, n_swaps=n_swaps, trials=0, g=g)
    cells = None
    if method == "grid6of8":
        xs = np.linspace(XL, XH, 3); ys = np.linspace(YL, YH, 5)
        allc = [(xs[i], xs[i + 1], ys[j], ys[j + 1]) for i in range(2) for j in range(4)]
        cells = [c for k, c in enumerate(allc) if k not in (1, 2)]  # 近端（x 小）中间两格含按钮
        perm = torch.randperm(6, generator=g).tolist()
    for i in range(n):
        if method == "v4" or method.startswith("hc"):
            dmin = float(method[2:]) if method.startswith("hc") else 0.0
            got = None
            for t in range(max_trials):
                trials_total += 1
                got = _trial(g, full, obb_list, placed, dmin)
                if got:
                    break
        elif method.startswith("bc"):
            K = int(method[2:])
            cands = []
            for _k in range(K if placed else 1):
                c = None
                for t in range(max_trials):
                    trials_total += 1
                    c = _trial(g, full, obb_list, placed, 0.0)
                    if c:
                        break
                if c:
                    cands.append(c)
            got = None
            if cands:
                if placed:
                    score = [min(np.hypot(c[0] - p[0], c[1] - p[1]) for p in placed) for c in cands]
                    got = cands[int(np.argmax(score))]
                else:
                    got = cands[0]
        elif method == "grid6of8":
            box = cells[perm[i]]
            got = None
            for t in range(max_trials):
                trials_total += 1
                got = _trial(g, box, obb_list, placed, 0.0)
                if got:
                    break
        else:
            raise ValueError(method)
        if not got:
            return dict(ok=False, fail_at=i, trials=trials_total)
        placed.append(got)
        obb_list.append(cube_obb2d_like_actor(*got))
    return dict(ok=True, cubes=placed, button=btn, n_swaps=n_swaps, trials=trials_total, g=g)


def draw_selection(g, n=6):
    """目标 + 发起者排列：与 V4 _load_cubes_xhard 同两次抽样（randint、randperm(n-1)）。"""
    target = int(torch.randint(0, n, (1,), generator=g).item())
    remaining = [i for i in range(n) if i != target]
    perm = torch.randperm(len(remaining), generator=g).tolist()
    return target, [target] + [remaining[i] for i in perm[:2]], [target] + [remaining[i] for i in perm]
