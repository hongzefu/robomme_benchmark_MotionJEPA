#!/usr/bin/env python3
"""条件耗尽概率：对每局已接受的 goal/杆，数值估计方块候选（128 次）与方块最终（256 次）的单次接受率 p，
再求 E[(1−p)^budget] 与最坏局。对拒绝采样「均值小但个别布局几乎无解」的尾部风险给出量化。"""
import sys
import numpy as np
from mc_v6 import V5, simulate, seg_dist
import sweep_v6 as S

rng = np.random.default_rng(0)


def cond_accept(P, e, s, M=4000):
    h = P["cand_half"]
    c = rng.uniform(-h, h, size=(M, 2))
    r = np.hypot(c[:, 0], c[:, 1])
    ok = np.linalg.norm(c - e["goal"], axis=1) > P["min_cg"]
    ok &= r >= P["R"]
    if P["R_out"] is not None:
        ok &= r <= P["R_out"]
    if P["x_cap"] is not None:
        ok &= c[:, 0] <= P["x_cap"]
    if P["peg_gap"] is not None:
        u = np.array([np.cos(e["peg_yaw"]), np.sin(e["peg_yaw"])])
        rel = e["peg_root"][None, :] - c
        t = np.clip(-(rel @ u), -0.15, 0.05)
        d = np.linalg.norm(rel + t[:, None] * u[None, :], axis=1)   # 与 mc_v6.seg_dist 同式（向量化）
        ok &= d >= P["peg_gap"] + P["peg_gap_cand_extra"]
    return ok.mean()


def run(name, kw, N):
    P = dict(V5); P.update(kw)
    ps = []
    for i in range(N):
        o = simulate(8_000_000 + i, **kw)
        if not o.ok:
            continue
        for s in ("demo", "exec"):
            ps.append(cond_accept(P, o.seg[s], s))
    ps = np.array(ps)
    ex = (1 - ps) ** 128
    print(f"{name}: 段数={len(ps)} 候选单次接受率 均值={ps.mean():.3f} p1={np.percentile(ps, 1):.3f} min={ps.min():.4f} "
          f"E[耗尽]={ex.mean():.2e} 最坏段耗尽={ex.max():.2e}", flush=True)


if __name__ == "__main__":
    N = int(sys.argv[1])
    todo = {"V5 xhard": {}}
    todo.update(S.FINAL); todo.update(S.GROUPS["ring"])
    todo.pop("V5 xhard（基线）", None)
    for k, v in todo.items():
        run(k, v, N)
