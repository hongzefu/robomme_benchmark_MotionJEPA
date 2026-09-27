"""V6 规划探针：VideoRepick xhard 复位抽样 + 搭档规划的纯 CPU 复刻（只读，不起 sapien 场景）。

随机流顺序与 VideoRepick.__init__ / _load_scene / _load_cubes_xhard 一致（V5 源码 HEAD da77662）：
  num_repeats randint(lo,hi) → n_swaps randint(smin,smax+1) → build_button rand(2) → 颜色 rand(3)
  → N 块 × 每次 trial rand(1)×3（x,y,yaw）；判据：按钮 OBB(半边 0.05625) + 已放方块精确 OBB（新块外扩 min_gap=hs）
     + 最小中心距 d（spawn_random_cube(min_center_dist=...) 在 OBB 判据之后判）
  → 目标 randint(0,N) → randperm(N-1) → 追加 rand(n_swaps)
  → 规划：直接调用源码里的 _xhard_slot_states / _XhardSlotSweepFeasibility / _plan_swap_partners_xhard（不复制逻辑）。
可行性矩阵按槽位对一次算全（N(N-1)/2 次 check_swap_sweep_prefiltered），供各候选方案共用。
"""
import numpy as np, torch
from robomme.robomme_env.utils.object_generation import _build_new_cube_obb2d, _obb2d_intersect, create_button_obb
from robomme.robomme_env.utils.bin_collision import button_base_state
import importlib
VR = importlib.import_module("robomme.robomme_env.VideoRepick")

HS = 0.02
MARGIN = 0.005
BTN_CENTER = (-0.2, 0.0)
BTN_RANGE = (0.1, 0.1)
BTN_OBB_HALF = 0.025 * 1.5 * 1.5


def region_box(center=(-0.1, 0.0), half=(0.2, 0.25)):
    return (center[0] - half[0] + HS, center[0] + half[0] - HS, center[1] - half[1] + HS, center[1] + half[1] - HS)


def exact_obb(x, y, yaw, hs=HS):
    c, s = np.cos(yaw), np.sin(yaw)
    return (np.array([x, y]), np.array([[c, -s], [s, c]]), np.array([hs, hs]))


def f32(v):
    return float(np.float32(v))


def reset_sample(seed, n_cubes=6, dmin=0.12, rep=(4, 7), swaps=(8, 12), box=None, max_trials=256):
    """复刻 V5 xhard 的 reset 抽样。返回 dict(ok, cubes=[(x,y,yaw)], button, n_swaps, num_repeats, target, perm, u, g)。"""
    box = box or region_box()
    XL, XH, YL, YH = box
    g = torch.Generator(); g.manual_seed(seed)
    num_repeats = torch.randint(rep[0], rep[1], (1,), generator=g).item()
    n_swaps = torch.randint(swaps[0], swaps[1] + 1, (1,), generator=g).item()
    off = torch.rand(2, generator=g) - 0.5
    btn = (BTN_CENTER[0] + float(off[0]) * BTN_RANGE[0], BTN_CENTER[1] + float(off[1]) * BTN_RANGE[1])
    torch.rand(3, generator=g)  # 颜色
    obb = [create_button_obb(center_xy=btn, half_size=BTN_OBB_HALF)]
    placed, trials = [], 0
    for i in range(n_cubes):
        got = None
        for t in range(max_trials):
            trials += 1
            u1 = torch.rand(1, generator=g).item(); u2 = torch.rand(1, generator=g).item()
            x = float(XL + u1 * (XH - XL)); y = float(YL + u2 * (YH - YL))
            yaw = float(torch.rand(1, generator=g).item() * 2 * np.pi)
            cn, An, hn = _build_new_cube_obb2d(x, y, HS, yaw, pad_xy=HS)
            if any(_obb2d_intersect(c, A, h, cn, An, hn) for (c, A, h) in obb):
                continue
            if placed and min(np.hypot(x - p[0], y - p[1]) for p in placed) < dmin:
                continue
            got = (x, y, yaw); break
        if got is None:
            return dict(ok=False, fail_at=i, trials=trials, n_swaps=n_swaps, num_repeats=num_repeats)
        # 已放方块的障碍与参考点取自 actor 位姿（float32），这里按 float32 截断复刻
        got = (f32(got[0]), f32(got[1]), got[2])
        placed.append(got)
        obb.append(exact_obb(*got))
    target = int(torch.randint(0, n_cubes, (1,), generator=g).item())
    perm = torch.randperm(n_cubes - 1, generator=g).tolist()
    u = torch.rand(n_swaps, generator=g).tolist()
    return dict(ok=True, cubes=placed, button=btn, n_swaps=n_swaps, num_repeats=num_repeats,
                target=target, perm=perm, u=u, g=g, trials=trials)


def feasibility_matrix(cubes, button, margin=MARGIN, button_obstacle=True):
    """全部槽位对的扫掠可行性（源码 _XhardSlotSweepFeasibility 口径），返回 N×N bool 矩阵。"""
    states = VR._xhard_slot_states(cubes, HS, margin)
    statics = [button_base_state("button_base", button, scale=1.5)] if button_obstacle else []
    fz = VR._XhardSlotSweepFeasibility(states, statics)
    N = len(cubes)
    M = np.zeros((N, N), bool)
    for a in range(N):
        for b in range(a + 1, N):
            M[a, b] = M[b, a] = fz.feasible(a, b)
    return M


def initiator_seq_current(target, perm, n_cubes, n_swaps):
    remaining = [i for i in range(n_cubes) if i != target]
    order = [target] + [remaining[i] for i in perm]
    return [order[k % n_cubes] for k in range(n_swaps)]


def plan_current(cubes, M, seq, u, nearest_k=3):
    """直接调用源码 _plan_swap_partners_xhard；失败返回 (None, k)。"""
    try:
        plan = VR._plan_swap_partners_xhard([c[:2] for c in cubes], seq, u, lambda a, b: bool(M[a, b]), nearest_k)
    except VR._RealSceneGenerationError as e:
        msg = str(e); k = int(msg.split("第 ")[1].split(" 次")[0])
        return None, k
    return plan, None
