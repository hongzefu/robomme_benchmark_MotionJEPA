"""V6 规划探针公共库：复刻 VUS/BUS xhard 内环布局（借 V5 探针 replica.py，已 20/20 逐值核对），
内环/外环的可行性判定直接调仓库纯函数（check_swap_sweep_prefiltered、evaluate_outer_candidate 等），不改仓库。"""
from __future__ import annotations

import sys
from pathlib import Path

import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np
import torch
torch.set_num_threads(1)

REPO = Path("/data/hongzefu/robomme_benchmark_MotionJEPANewTask")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "artifacts/newtask-v5/plan-probes/unmask_swap"))

from replica import bus_layout, vus_layout, initiators  # noqa: E402,F401
from robomme.robomme_env.utils import unmask_swap_xhard as ux  # noqa: E402
from robomme.robomme_env.utils.bin_collision import (  # noqa: E402
    ObjectState, bin_actor_pose, bin_shape_specs, check_swap_sweep_prefiltered)
from robomme.robomme_env.utils.unmask_distractor_sampler import (  # noqa: E402
    DistractorPlacementError, bin_obb2d, sample_distractor_layout)

CH = 0.02
SHAPES = bin_shape_specs(CH)
BTN_HALF = 0.025 * 1.5 * 1.5
SWAP_RANGE = {"VideoUnmaskSwap": (8, 12), "ButtonUnmaskSwap": (6, 8)}


def st(name, x, y, yaw, shapes=SHAPES):
    p, q = bin_actor_pose([float(x), float(y)], float(yaw), CH)
    return ObjectState(name=name, p=p, q=q, shapes=tuple(shapes))


def inner_layout(task, seed, swap_range=None):
    fn = vus_layout if task == "VideoUnmaskSwap" else bus_layout
    return fn(seed, swap_range or SWAP_RANGE[task])


def inner_states(bins):
    return [st(f"bin_{i}", x, y, yaw) for i, (x, y, yaw) in enumerate(bins)]


def swap_states(states, a, b):
    s = list(states)
    sa, sb = s[a], s[b]
    s[a] = ObjectState(name=sa.name, p=sb.p.copy(), q=sb.q.copy(), shapes=sa.shapes)
    s[b] = ObjectState(name=sb.name, p=sa.p.copy(), q=sa.q.copy(), shapes=sb.shapes)
    return s


def inner_pair_ok(states, a, b, k=0):
    others = [s for j, s in enumerate(states) if j not in (a, b)]
    _g, rej = check_swap_sweep_prefiltered(states[a], states[b], others, sweep_index=k, stage="probe")
    return rej is None


def nearest(states, a, pool=None):
    pos = [np.asarray(s.p[:2], dtype=np.float32) for s in states]
    best, bd = None, float("inf")
    for j, p in enumerate(pos):
        if j == a or (pool is not None and j not in pool):
            continue
        d = np.linalg.norm(pos[a] - p)
        if d < bd:
            best, bd = j, d
    return best


def obstacles(lay):
    obst = [(np.asarray(b, float), np.eye(2), np.array([BTN_HALF, BTN_HALF])) for b in lay["buttons"]]
    return obst + [bin_obb2d(x, y, yaw, CH, pad=CH * 0.75) for x, y, yaw in lay["bins"]]


def windows_from_pairs(states, pairs):
    """给定内环交换对序列，构造 InnerWindow 列表（每窗起点状态）。"""
    ws = []
    s = list(states)
    for a, b in pairs:
        ws.append(ux.InnerWindow(a=int(a), b=int(b), states=tuple(s)))
        s = swap_states(s, a, b)
    return ws
