"""按 V5 xhard 规则真实抽一局（内环复刻 + 仓库外环采样器 + 仓库外环候选判定），供图 1 / 图 5 使用。"""
from __future__ import annotations

import numpy as np
import vizlib  # noqa: F401  (设置路径)
from mclib import (CH, DistractorPlacementError, inner_layout, inner_states, obstacles, sample_distractor_layout, ux)
from p3_outer_mc import v5_inner_windows


def build_episode(task, seed, count=10, inner_windows=None):
    lay = inner_layout(task, seed)
    if lay.get("spawn_fail"):
        return None
    wins = inner_windows(lay) if inner_windows else v5_inner_windows(lay)
    if ux.prejudge_inner_windows(wins) is not None:
        return None
    dcfg = dict(ux.v5_distractor_cfg(task)); dcfg["count"] = count
    lo = count // 2; dcfg["cube_count_range"] = [lo, lo]
    scfg = ux.parse_distractor_swap_cfg(ux.v5_distractor_swap_cfg(task))
    guard = ux.InnerSweepGuard(wins)
    pad = ux.padded_bin_shapes(CH, scfg.plan_pad_m)
    try:
        layout = sample_distractor_layout(dcfg, obstacles=obstacles(lay), generator=ux.distractor_generator(seed),
                                          cube_half_size=CH, extra_reject=lambda i, x, y, yaw, _p: guard.first_rejection(
                                              ux.distractor_bin_state(i, x, y, yaw, CH, pad)) is not None)
    except DistractorPlacementError:
        return None
    outer = [ux.distractor_bin_state(i, x, y, yaw, CH, pad) for i, (x, y, yaw) in enumerate(layout.bins)]
    return dict(task=task, seed=seed, count=count, lay=lay, wins=wins, layout=layout, outer=outer, scfg=scfg)


def outer_window_graph(ep, k, with_reason=False):
    """第 k 窗（以外环「槽」为单位）全部 C(count,2) 个槽对的可行性；与 p3_outer_mc 同口径（外环槽 = 初始位姿）。"""
    count = ep["count"]; lay = ep["lay"]; w = ep["wins"][k]
    g = {}
    for a in range(count):
        for b in range(a + 1, count):
            ok, r, _ = ux.evaluate_outer_candidate(k, w, a, b, ep["outer"], cfg=ep["scfg"], cube_half_size=CH,
                                                   buttons_xy=[np.asarray(bb) for bb in lay["buttons"]])
            g[(a, b)] = (bool(ok), r) if with_reason else bool(ok)
    return g
