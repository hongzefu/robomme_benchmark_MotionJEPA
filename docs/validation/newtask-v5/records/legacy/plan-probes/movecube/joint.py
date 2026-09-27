#!/usr/bin/env python3
"""第 3/4 问：完整 demo+execution 布局的联合模拟（逐调用 torch 复刻，已对 v4-01 specs 10/10 逐位核验）。

每方案 N 个 seed（1_000_000+i）；报：布局成功率、随机调用次数（= 随机流位置平移）、各对象拒绝次数、
最终位置落入中心禁区的比例、方块-goal 距离、推杆/夹爪推起点到机器人基座的水平距离（可达性代理）、
杆与方块初始几何重叠、杆身侵入中心禁区、way 分布。

    cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <本文件> [N]
"""
from __future__ import annotations

import math
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
from mc_layout import CenterCfg, HS, _obb, _sat, simulate  # noqa: E402

BASE = np.array([-0.615, 0.0])
SQ = math.sqrt(0.3)
DK = math.sqrt(0.3 * 4 / math.pi)

SCHEMES = {
    "V4 b=0（均匀）": (0.0, None),
    "V4 b=0.5（现行）": (0.5, None),
    "V4 b=1.0": (1.0, None),
    "V5-a 逐轴30%方(面积9%)": (0.0, CenterCfg("square", 0.3 * 0.05, 0.3 * 0.11, 0.3 * 0.06, 0.3 * 0.1, "both")),
    "V5-b 面积30%方【推荐】": (0.0, CenterCfg("square", SQ * 0.05, SQ * 0.11, SQ * 0.06, SQ * 0.1, "both")),
    "V5-b 仅候选(方块会漏进中心)": (0.0, CenterCfg("square", SQ * 0.05, SQ * 0.11, SQ * 0.06, SQ * 0.1, "cand")),
    "V5-b' 面积30%圆": (0.0, CenterCfg("disk", DK * 0.05, DK * 0.11, DK * 0.06, DK * 0.1, "both")),
    "V5-b 方块按最终支撑盒(0.0712)": (0.0, CenterCfg("square", SQ * 0.05, SQ * 0.11, SQ * 0.06, SQ * 0.13, "both")),
    "V5-a' 十字(只留四角)": (0.0, CenterCfg("cross", 0.3 * 0.05, 0.3 * 0.11, 0.3 * 0.06, 0.3 * 0.1, "both")),
    "V5-c 公共中心方0.045": (0.0, CenterCfg("square", None, 0.045, 0.045, 0.045, "both")),
}
W_REF = SQ * 0.1  # 用来统一度量「方块/goal 是否在中心」的参考禁区（推荐方案的方块禁区 0.0548）


def peg_boxes(root, yaw):
    """build_peg：head 碰撞盒中心=根点、半长 0.045、半宽 0.01；tail 中心=根点-0.1·轴向。"""
    ax = np.array([math.cos(yaw), math.sin(yaw)])
    A = np.array([[ax[0], -ax[1]], [ax[1], ax[0]]])
    h = np.array([0.045, 0.01])
    return [(root.copy(), A, h), (root - 0.1 * ax, A, h)]


def peg_intrudes_zone(root, yaw, w):
    """杆身（视觉全长：根点+0.05 到 根点-0.15、半宽 0.01）是否进入 (0,0) 中心方禁区 max(|x|,|y|)<w。"""
    ax = np.array([math.cos(yaw), math.sin(yaw)])
    A = np.array([[ax[0], -ax[1]], [ax[1], ax[0]]])
    body = (root - 0.05 * ax, A, np.array([0.1, 0.01]))
    zone = (np.zeros(2), np.eye(2), np.array([w, w]))
    return _sat(*zone, *body)


def disk_hits_box(center, r, box):
    c, A, h = box
    local = A.T @ (center - c)
    closest = np.clip(local, -h, h)
    return np.linalg.norm(local - closest) < r


def push_starts(cube, goal):
    d = goal - cube
    d = d / np.linalg.norm(d)
    direction = 1 if cube[1] - goal[1] > 0 else -1
    lat = np.array([-d[1], d[0]])
    peg_start = cube - 0.1 * d - lat * 0.1 * direction
    grip_start = cube - 0.05 * d
    return np.linalg.norm(peg_start - BASE), np.linalg.norm(grip_start - BASE), np.linalg.norm(goal - BASE)


def run(N):
    seeds = [1_000_000 + i for i in range(N)]
    print(f"N={N} seeds=1_000_000..{1_000_000 + N - 1}；V4 基准随机调用数=27（不含拒绝重抽）")
    summary = {}
    for name, (bias, cfg) in SCHEMES.items():
        ok = 0
        fails = Counter()
        draws, rej_tot = [], Counter()
        rej_max = Counter()
        cube_in, goal_in, cg_dist = [], [], []
        rpeg, rgrip = [], []
        overlap, intrude, peg_goal = 0, 0, 0
        segs = 0
        ways = Counter()
        cube_inf = []
        for sd in seeds:
            L = simulate(sd, bias=bias, center=cfg)
            if not L.ok:
                fails[L.fail] += 1
                continue
            ok += 1
            draws.append(L.draws)
            ways[L.way_idx] += 1
            for k, v in L.rejects.items():
                rej_tot[k] += v
                rej_max[k] = max(rej_max[k], v)
            for sname in ("demo", "exec"):
                e = L.seg[sname]
                segs += 1
                cube, goal = e["cube"], e["goal"]
                cube_inf.append(np.max(np.abs(cube)))
                cube_in.append(np.max(np.abs(cube)) < W_REF)
                gw = SQ * (0.11 if sname == "demo" else 0.06)
                goal_in.append(np.max(np.abs(goal)) < gw)
                cg_dist.append(np.linalg.norm(cube - goal))
                a, b, _ = push_starts(cube, goal)
                rpeg.append(a); rgrip.append(b)
                cb = _obb(cube[0], cube[1], HS, e["cube_yaw"])
                pb = peg_boxes(e["peg_root"], e["peg_yaw"])
                overlap += any(_sat(*cb, *p) for p in pb)
                intrude += peg_intrudes_zone(e["peg_root"], e["peg_yaw"], W_REF)
                vis = [(e["peg_root"], pb[0][1], np.array([0.05, 0.01])),
                       (e["peg_root"] - 0.1 * np.array([math.cos(e["peg_yaw"]), math.sin(e["peg_yaw"])]), pb[0][1], np.array([0.05, 0.01]))]
                peg_goal += any(disk_hits_box(goal, 0.04, v) for v in vis)
        draws = np.array(draws); rpeg = np.array(rpeg); rgrip = np.array(rgrip); cg = np.array(cg_dist)
        cube_inf = np.array(cube_inf)
        s = {
            "ok": ok, "N": N, "fails": dict(fails),
            "draws_mean": draws.mean(), "draws_p99": np.percentile(draws, 99), "draws_max": draws.max(),
            "extra_draws_mean": draws.mean() - 27,
            "rej_mean": {k: rej_tot[k] / ok for k in rej_tot}, "rej_max": dict(rej_max),
            "cube_in_W": float(np.mean(cube_in)), "goal_in_own": float(np.mean(goal_in)),
            "cube_inf_mean": float(cube_inf.mean()),
            "cg_mean": cg.mean(), "cg_p10": np.percentile(cg, 10), "cg_p90": np.percentile(cg, 90),
            "rpeg_mean": rpeg.mean(), "rpeg_p90": np.percentile(rpeg, 90), "rpeg_p99": np.percentile(rpeg, 99),
            "rpeg_max": rpeg.max(), "rpeg_gt078": float(np.mean(rpeg > 0.78)), "rpeg_gt080": float(np.mean(rpeg > 0.80)),
            "rgrip_p99": np.percentile(rgrip, 99),
            "overlap": overlap / segs, "intrude": intrude / segs, "peg_goal": peg_goal / segs,
            "ways": {k: ways[k] / ok for k in sorted(ways)},
        }
        summary[name] = s
        print(f"\n### {name}  (bias={bias})")
        print(f"  布局成功 {ok}/{N}  失败={dict(fails)}")
        print(f"  随机调用数 均值={s['draws_mean']:.2f}（比 V4 基准 27 多 {s['extra_draws_mean']:.2f}）p99={s['draws_p99']:.0f} max={s['draws_max']}")
        print("  每局平均中心拒绝次数: " + ", ".join(f"{k}={v:.3f}(max {rej_max[k]})" for k, v in s['rej_mean'].items()))
        print(f"  方块最终 xy 落在 max(|x|,|y|)<{W_REF:.4f} 的比例={s['cube_in_W']:.3f}；E[max(|x|,|y|)]={s['cube_inf_mean']:.4f}；goal 落在自身 30% 面积中心方={s['goal_in_own']:.3f}")
        print(f"  方块-goal 距离 均值={s['cg_mean']:.3f} p10={s['cg_p10']:.3f} p90={s['cg_p90']:.3f}")
        print(f"  推杆起点距基座 均值={s['rpeg_mean']:.3f} p90={s['rpeg_p90']:.3f} p99={s['rpeg_p99']:.3f} max={s['rpeg_max']:.3f}；>0.78 占 {s['rpeg_gt078']:.3f}，>0.80 占 {s['rpeg_gt080']:.3f}；夹爪推起点 p99={s['rgrip_p99']:.3f}")
        print(f"  杆-方块初始重叠(每段)={s['overlap']:.4f}；杆身侵入中心方({W_REF:.4f})={s['intrude']:.3f}；杆压在 goal 圆盘上(视觉)={s['peg_goal']:.3f}")
        print(f"  way 分布={ {k: round(v, 3) for k, v in s['ways'].items()} }")
    return summary


if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    run(N)
