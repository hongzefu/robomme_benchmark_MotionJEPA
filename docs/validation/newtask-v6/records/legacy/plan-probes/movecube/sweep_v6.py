#!/usr/bin/env python3
"""V6 MoveCube「往外推」候选方案的离线蒙特卡洛扫描。

用法：uv run --no-sync python sweep_v6.py <N> <方案组> > xxx.out
方案组：frozen（V5 框不动、只加大 R）/ grid（框 × R 网格）/ final（推荐三档，含热图）
每方案 seed = 7_000_000 + i（与 V5 探针、v5-01 的 seed 区间不重叠）。
"""
from __future__ import annotations

import math
import sys
from collections import Counter

import numpy as np

import geom
from mc_v6 import V5, simulate

GLYPH = " .:-=+*#%@"


def box(ge, cand, gd=0.11):
    return dict(ge_half=ge, cand_half=cand, gd_half=gd)


GROUPS = {
    "frozen": {f"V5框 R={R:.3f}": dict(R=R) for R in (0.05, 0.06, 0.07, 0.08, 0.084, 0.10, 0.12, 0.15)},
    "grid": {},
    "final": {},
    "variants": {},
}
BOXES = {
    "B0 V5框(ge.06 c.10 gd.11)": box(0.06, 0.10),
    "B1(ge.09 c.12 gd.12)": box(0.09, 0.12, 0.12),
    "B2(ge.11 c.13 gd.13)": box(0.11, 0.13, 0.13),
    "B3(ge.13 c.15 gd.15)": box(0.13, 0.15, 0.15),
}
for bn, b in BOXES.items():
    for R in (0.05, 0.08, 0.10, 0.12, 0.15):
        GROUPS["grid"][f"{bn} R={R:.2f}"] = dict(b, R=R)

# 推荐三档（按 grid 结果选定；见 report.md）
FINAL = {
    "V5 xhard（基线）": dict(),
    "T1: R=0.08 B1框 x_cap0.11 peg_gap0.04": dict(box(0.09, 0.12, 0.12), R=0.08, x_cap=0.11, peg_gap=0.04, peg_gap_cand_extra=0.02),
    "T2: R=0.10 B2框 x_cap0.11 peg_gap0.04": dict(box(0.11, 0.13, 0.13), R=0.10, x_cap=0.11, peg_gap=0.04, peg_gap_cand_extra=0.02),
    "T3: R=0.12 B3框 x_cap0.11 peg_gap0.04": dict(box(0.13, 0.15, 0.15), R=0.12, x_cap=0.11, peg_gap=0.04, peg_gap_cand_extra=0.02),
}
GROUPS["final"] = FINAL
GROUPS["ring"] = {
    "环带 T1: [0.08,0.12] 框0.12 x_cap0.11 peg_gap0.04": dict(box(0.12, 0.12, 0.12), R=0.08, R_out=0.12, x_cap=0.11, peg_gap=0.04, peg_gap_cand_extra=0.02),
    "环带 T2: [0.10,0.14] 框0.14 x_cap0.11 peg_gap0.04": dict(box(0.14, 0.14, 0.14), R=0.10, R_out=0.14, x_cap=0.11, peg_gap=0.04, peg_gap_cand_extra=0.02),
    "环带 T3: [0.12,0.16] 框0.16 x_cap0.11 peg_gap0.04": dict(box(0.16, 0.16, 0.16), R=0.12, R_out=0.16, x_cap=0.11, peg_gap=0.04, peg_gap_cand_extra=0.02),
}
GROUPS["variants"] = {
    "V5框 R=0.07（不扩框的上限档）": dict(R=0.07),
    "T1 x_cap=0.11": dict(box(0.09, 0.12, 0.12), R=0.08, x_cap=0.11),
    "T2 x_cap=0.11": dict(box(0.11, 0.13, 0.13), R=0.10, x_cap=0.11),
    "T3 x_cap=0.11": dict(box(0.13, 0.15, 0.15), R=0.12, x_cap=0.11),
    "T1 + peg_gap 0.04": dict(box(0.09, 0.12, 0.12), R=0.08, peg_gap=0.04),
    "T3 + peg_gap 0.04": dict(box(0.13, 0.15, 0.15), R=0.12, peg_gap=0.04),
    "T3 环带 R_out=0.17": dict(box(0.13, 0.15, 0.15), R=0.12, R_out=0.17),
    "T1 min_cg=0.12": dict(box(0.09, 0.12, 0.12), R=0.08, min_cg=0.12),
    "T2 min_cg=0.14": dict(box(0.11, 0.13, 0.13), R=0.10, min_cg=0.14),
    "T3 min_cg=0.16": dict(box(0.13, 0.15, 0.15), R=0.12, min_cg=0.16),
}
_OLD_VARIANTS = {
    "T2 + peg_gap 0.04": dict(box(0.09, 0.12, 0.12), R=0.10, peg_gap=0.04),
    "T3 + peg_gap 0.04": dict(box(0.11, 0.13, 0.13), R=0.12, peg_gap=0.04),
    "T3 环带 R_out=0.16": dict(box(0.11, 0.13, 0.13), R=0.12, R_out=0.16),
    "T2 min_cg=0.14": dict(box(0.09, 0.12, 0.12), R=0.10, min_cg=0.14),
    "T3 min_cg=0.16": dict(box(0.11, 0.13, 0.13), R=0.12, min_cg=0.16),
    "V5框 R=0.08 min_cg=0.12": dict(R=0.08, min_cg=0.12),
}


def analytic(P):
    P2 = dict(V5); P2.update(P)
    R, Ro = P2["R"], P2["R_out"]
    out = {}
    for k, h, B in (("goal_demo", P2["gd_half"], P2["goal_budget"]), ("goal_exec", P2["ge_half"], P2["goal_budget"])):
        p = geom.accept_square_annulus(h, R, Ro)
        out[k] = (1 - p, (1 - p) ** B if p < 1 else 0.0)
    p = geom.accept_square_annulus(P2["cand_half"], R, Ro)
    out["cand(仅禁区)"] = (1 - p, None)
    return out


def heat(points, lim=0.22, cell=0.02):
    n = int(round(2 * lim / cell))
    H = np.zeros((n, n))
    for x, y in points:
        i = int((x + lim) // cell); j = int((y + lim) // cell)
        if 0 <= i < n and 0 <= j < n:
            H[i, j] += 1
    H = H / max(1, len(points))
    mx = H.max()
    lines = []
    # 行 = x（上方 x 大，远离机器人），列 = y（左 −y 右 +y）
    for i in range(n - 1, -1, -1):
        row = "".join(GLYPH[min(9, int(math.ceil(9 * v / mx)))] if v > 0 else " " for v in H[i])
        lines.append(f"  x={-lim + (i + .5) * cell:+.2f} |{row}|")
    lines.append(f"          y: {-lim:+.2f} … {lim:+.2f}，每格 {cell} m，最深字符 = 峰值 {mx * 100:.2f}%")
    return "\n".join(lines)


def run(name, P, N, show_heat=False):
    fails = Counter(); ok = 0
    trials = Counter(); tmax = Counter()
    rad = {k: [] for k in ("goal_demo", "goal_exec", "cube_demo", "cube_exec", "peg_near_demo", "peg_near_exec")}
    cg = {"demo": [], "exec": []}
    pegstart, gripstart, far_obj, pegend = [], [], [], []
    cam_margin = []
    overlap = under = 0; segs = 0
    pts = {k: [] for k in ("goal_demo", "goal_exec", "cube_demo", "cube_exec", "peg_mid")}
    for i in range(N):
        o = simulate(7_000_000 + i, **P)
        if not o.ok:
            fails[o.fail] += 1; continue
        ok += 1
        for k, v in o.trials.items():
            trials[k] += v; tmax[k] = max(tmax[k], v)
        for s in ("demo", "exec"):
            e = o.seg[s]; segs += 1
            cube, goal, root, pyaw = e["cube"], e["goal"], e["peg_root"], e["peg_yaw"]
            rad[f"goal_{s}"].append(np.hypot(*goal)); rad[f"cube_{s}"].append(np.hypot(*cube))
            from mc_v6 import seg_dist
            rad[f"peg_near_{s}"].append(seg_dist(root, pyaw))
            cg[s].append(np.linalg.norm(cube - goal))
            ps, pe, gs = geom.push_starts(cube, goal)
            pegstart.append(max(np.linalg.norm(ps - geom.BASE), np.linalg.norm(pe - geom.BASE)))
            gripstart.append(np.linalg.norm(gs - geom.BASE))
            far_obj.append(max(np.linalg.norm(cube - geom.BASE), np.linalg.norm(goal - geom.BASE)))
            cam_margin.append(min(geom.pixel_margin(geom.cube_points(cube, e["cube_yaw"])),
                                  geom.pixel_margin(geom.disk_points(goal)),
                                  geom.pixel_margin(geom.peg_points(root, pyaw))))
            overlap += geom.peg_cube_overlap(root, pyaw, cube, e["cube_yaw"])
            under += geom.goal_under_peg(root, pyaw, goal)
            pts[f"goal_{s}"].append(goal); pts[f"cube_{s}"].append(cube)
            u = np.array([math.cos(pyaw), math.sin(pyaw)])
            pts["peg_mid"].append(root - 0.05 * u)
    pegstart, gripstart, far_obj = map(np.array, (pegstart, gripstart, far_obj))
    q = lambda a: f"{np.median(a):.3f}/{np.percentile(a, 90):.3f}"
    an = analytic(P)
    print(f"== {name}  P={ {k: v for k, v in P.items()} }")
    print(f"  布局成功 {ok}/{N} 失败={dict(fails)}")
    print("  解析每次抽样拒绝率/预算耗尽概率：" + "；".join(
        f"{k} 拒{v[0] * 100:.1f}%" + (f" 耗尽{v[1]:.2e}" if v[1] is not None else "") for k, v in an.items()))
    if ok:
        print("  平均尝试次数(max)：" + " ".join(f"{k}={trials[k] / ok:.2f}({tmax[k]})" for k in sorted(trials)))
        print("  离圆心距离 中位/p90：" + " ".join(f"{k}={q(v)}" for k, v in rad.items()))
        print(f"  方块-goal 距离 demo 均值={np.mean(cg['demo']):.3f} p10/p50/p90={np.percentile(cg['demo'], 10):.3f}/{np.median(cg['demo']):.3f}/{np.percentile(cg['demo'], 90):.3f}；"
              f"exec 均值={np.mean(cg['exec']):.3f} p10/p50/p90={np.percentile(cg['exec'], 10):.3f}/{np.median(cg['exec']):.3f}/{np.percentile(cg['exec'], 90):.3f}")
        print(f"  可达性代理(距基座)：peg_push 路点 p99={np.percentile(pegstart, 99):.3f} >0.78={np.mean(pegstart > 0.78) * 100:.1f}% >0.80={np.mean(pegstart > 0.80) * 100:.1f}%；"
              f"gripper_push 起点 p99={np.percentile(gripstart, 99):.3f} >0.78={np.mean(gripstart > 0.78) * 100:.1f}%；方块/goal 最远 p99={np.percentile(far_obj, 99):.3f} max={far_obj.max():.3f}")
        cm = np.array(cam_margin)
        print(f"  front 相机最小像素余量 p1={np.percentile(cm, 1):.1f} min={cm.min():.1f} 出画={np.mean(cm < 0) * 100:.2f}%；"
              f"杆-方块初始重叠/段={overlap / segs * 100:.2f}% goal 圆盘压杆/段={under / segs * 100:.1f}%")
        rr = np.concatenate([rad["goal_exec"]])
        print("  执行段 goal 半径分布：" + " ".join(f"[{a:.2f},{b:.2f})={np.mean((rr >= a) & (rr < b)) * 100:.0f}%" for a, b in ((0, .05), (.05, .08), (.08, .10), (.10, .12), (.12, .15), (.15, .3))))
        rr = np.concatenate([rad["cube_demo"], rad["cube_exec"]])
        print("  方块半径分布：" + " ".join(f"[{a:.2f},{b:.2f})={np.mean((rr >= a) & (rr < b)) * 100:.0f}%" for a, b in ((0, .05), (.05, .08), (.08, .10), (.10, .12), (.12, .15), (.15, .3))))
    if show_heat and ok:
        for k in ("goal_exec", "goal_demo", "cube_demo", "peg_mid"):
            print(f"  -- 俯视热图 {k}（上 = +x 远离机器人，下 = −x 靠近机器人）")
            print(heat(pts[k], lim=0.28 if k == "peg_mid" else 0.2))
    sys.stdout.flush()


if __name__ == "__main__":
    N = int(sys.argv[1]); grp = sys.argv[2]
    for name, P in GROUPS[grp].items():
        run(name, P, N, show_heat=(grp in ("final", "ring")))
