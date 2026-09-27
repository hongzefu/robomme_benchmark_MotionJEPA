#!/usr/bin/env python3
"""MoveCube xhard 布局的逐调用 torch 离线副本（不起 sapien），参数化以评估 V6「继续往外推」的候选。

复刻 src/robomme/robomme_env/MoveCube.py::_load_scene（V5 xhard 分支）的全部随机调用顺序与判据：
  length/radius 两次 rand → 演示段 base_y、杆循环(x,y,yaw) → 执行段 base_y、杆循环 → obj_sample、dir_sample
  → 演示段 goal（spawn_random_target，256 次）→ 执行段 goal → 演示段方块候选（128 次，|c−g|>min_cg 且不进禁区）
  → 演示段方块最终（spawn_random_cube，256 次，每次 u1,u2,yaw）→ 执行段候选 → 执行段方块最终 → way_idx×2。
V5 默认参数下对 scripts/configs/newtask-v5/v5-01/specs.jsonl 的 MoveCube 行逐值核验（见 validate_v5）。

V6 扩展参数（默认值 = V5 xhard）：
  R        禁区内半径（杆按轴线段最近点、goal/候选/方块最终按中心）
  R_out    可选外半径：中心离原点 > R_out 也拒（环带采样；杆不受外半径约束）
  gd_half  演示段 goal 中心采样半宽（= region_half_size − 0.04；V5 0.11）
  ge_half  执行段 goal 中心采样半宽（V5 0.06）
  cand_half 方块候选中心采样半宽（center_span/2；V5 0.10，offset=−cand_half）
  local    方块最终相对候选的半宽（region_half_size 0.05 − half 0.02 = 0.03）
  min_cg   候选与 goal 最小中心距（V5 = 5×0.02 = 0.10）
  x_cap    可选：goal/候选/方块最终中心 x 超过该值也拒（只扩 −x 与 ±y、不往远离机器人的 +x 扩）
  peg_gap  可选：方块候选中心与最终中心到杆身（可视外形线段）距离下限（None=不查，与 V5 相同）；
           候选处再加 peg_gap_cand_extra 的余量（让 ±local 的最终位置仍有解）
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import torch

HS = 0.02
PEG_SEG = (-0.15, 0.05)
V5 = dict(R=0.05, R_out=None, gd_half=0.11, ge_half=0.06, cand_half=0.10, local=0.03, min_cg=0.10,
          peg_gap=None, peg_gap_cand_extra=0.0, x_cap=None, peg_budget=128, goal_budget=256, cand_budget=128, cube_budget=256,
          base_y_abs=0.2, jitter=0.1)


class Exhaust(Exception):
    pass


def f32(v):
    return float(np.float32(v))


def peg_root(base_y, xj, yj):
    t = np.array([0.0, base_y, 0.0], dtype=np.float32)
    t[1] = base_y
    t[:2] += np.array([xj, yj], dtype=np.float32)
    return t[:2].astype(np.float64)


def seg_dist(root, yaw, p=(0.0, 0.0)):
    u = np.array([math.cos(yaw), math.sin(yaw)])
    rel = root - np.asarray(p)
    t = float(np.clip(-(rel @ u), *PEG_SEG))
    return float(np.linalg.norm(rel + t * u))


@dataclass
class Out:
    ok: bool = True
    fail: str = ""
    seg: dict = field(default_factory=dict)
    trials: dict = field(default_factory=dict)
    way: tuple = (-1, -1)
    obj_sample: int = -1


def simulate(seed, **kw):
    P = dict(V5); P.update(kw)
    R, Ro = P["R"], P["R_out"]
    g = torch.Generator(); g.manual_seed(int(seed))
    rand = lambda: torch.rand(1, generator=g).item()
    randint = lambda k: int(torch.randint(0, k, (1,), generator=g).item())

    def bad(xy):
        r = math.hypot(xy[0], xy[1])
        if P["x_cap"] is not None and xy[0] > P["x_cap"]:
            return True
        return r < R or (Ro is not None and r > Ro)

    o = Out()
    try:
        rand(); rand()                                   # length / radius
        pegs = {}
        for s in ("demo", "exec"):
            base_y = -P["base_y_abs"] if rand() < 0.5 else P["base_y_abs"]
            for trial in range(1, P["peg_budget"] + 1):
                xj = (rand() - 0.5) * P["jitter"]
                yj = (rand() - 0.5) * P["jitter"]
                yaw = rand() * 2 * math.pi - math.pi
                root = peg_root(base_y, xj, yj)
                if seg_dist(root, yaw) >= R:
                    break
            else:
                raise Exhaust(f"peg_{s}")
            pegs[s] = (root, yaw, base_y, xj, yj)
            o.trials[f"peg_{s}"] = trial
        o.obj_sample = randint(2); randint(2)
        goals = {}
        for s, h in (("demo", P["gd_half"]), ("exec", P["ge_half"])):
            lo, hi = -h, h
            for trial in range(1, P["goal_budget"] + 1):
                x = float(rand() * (hi - lo) + lo); y = float(rand() * (hi - lo) + lo)
                if not bad((x, y)):
                    break
            else:
                raise Exhaust(f"goal_{s}")
            goals[s] = np.array([f32(x), f32(y)])
            o.trials[f"goal_{s}"] = trial
        cubes = {}
        for s in ("demo", "exec"):
            gxy = goals[s]; cand = None; rej = 0
            span, off = 2 * P["cand_half"], -P["cand_half"]
            for trial in range(1, P["cand_budget"] + 1):
                cx = rand() * span + off
                cy = rand() * span + off
                c = np.array([cx, cy])
                if np.linalg.norm(c - gxy) > P["min_cg"]:
                    if bad(c) or (P["peg_gap"] is not None and seg_dist(pegs[s][0], pegs[s][1], c) < P["peg_gap"] + P["peg_gap_cand_extra"]):
                        rej += 1; continue
                    cand = c; break
            if cand is None:
                raise Exhaust(f"cand_{s}")
            o.trials[f"cand_{s}"] = trial
            xl, xh = cand[0] - P["local"], cand[0] + P["local"]
            yl, yh = cand[1] - P["local"], cand[1] + P["local"]
            placed = None
            for trial in range(1, P["cube_budget"] + 1):
                u1 = rand(); u2 = rand()
                x = float(xl + u1 * (xh - xl)); y = float(yl + u2 * (yh - yl))
                yaw = float(rand() * 2 * np.pi)
                if bad((x, y)):
                    continue
                if P["peg_gap"] is not None and seg_dist(pegs[s][0], pegs[s][1], (x, y)) < P["peg_gap"]:
                    continue
                placed = (x, y, yaw); break
            if placed is None:
                raise Exhaust(f"cube_{s}")
            o.trials[f"cube_{s}"] = trial
            cubes[s] = placed
        o.way = (randint(3), randint(3))
    except Exhaust as e:
        o.ok, o.fail = False, str(e)
        return o
    for s in ("demo", "exec"):
        root, yaw, base_y, xj, yj = pegs[s]
        o.seg[s] = dict(peg_root=root, peg_yaw=yaw, peg_offsets=(base_y, xj, yj), goal=goals[s],
                        cube=np.array(cubes[s][:2]), cube_yaw=cubes[s][2])
    return o


def validate_v5(path="scripts/configs/newtask-v5/v5-01/specs.jsonl"):
    """V5 默认参数下与 v5-01 冻结规格逐值对拍。"""
    import json
    n = ok = 0
    for line in open(path):
        d = json.loads(line)
        if d.get("record") != "spec" or d.get("task") != "MoveCube":
            continue
        n += 1
        sp = d["spec"]; o = simulate(d["seed"])
        good = o.ok
        for s, k in (("demo", "demo"), ("exec", "execution")):
            L = sp["layout"][k]
            good &= np.allclose(o.seg[s]["goal"], L["goal_xy"], atol=1e-6)
            good &= np.allclose(o.seg[s]["cube"], L["cube_pose"][:2], atol=1e-6)
            good &= abs(o.seg[s]["cube_yaw"] - L["cube_pose"][2]) < 1e-5
            good &= np.allclose(o.seg[s]["peg_offsets"], L["peg_offsets"], atol=1e-6)
            good &= abs(o.seg[s]["peg_yaw"] - L["peg_yaw"]) < 1e-5
            good &= o.trials[f"peg_{s}"] == L["center_exclusion_trials"]["peg_trials"]
        good &= o.way == (sp["initializations"]["0"]["way_idx"], sp["initializations"]["1"]["way_idx"])
        ok += bool(good)
        if not good:
            print("MISMATCH seed", d["seed"])
    print(f"VALIDATE_V5 {ok}/{n}")
    return ok, n


if __name__ == "__main__":
    validate_v5()
