"""P5 共用库：Swap 两环境「V4 环带 10 个干扰容器 + 外环随内环同步交换」的最终规则（离线与进程内原型共用同一份代码）。

最终规则（用户已定，V5 计划 L16～L23）：
* 干扰容器：V4 环带 max(|x|,|y|) ∈ [0.2675, 0.45]，count 10，含 cube [5,5]；
  统一采样器（与 unmask_distractors.spawn_ring_distractor_bins 同一判据）：方框均匀抽 (x,y) → 环带 → 精确 8 角点可见
  → OBB 避让（障碍 OBB 外扩 min_gap=0.015，中心到 OBB 点距 ≥ 0.0275+0.015）→ 通过后抽 yaw；
  Swap 专有：对预演的内环扫掠做 H1 静态候选检查（候选与任一段扫掠相交即拒绝）；1024 次/个。
  cube：randint(5,5) → cube_bins=randperm(10)[:5] → order=randperm(3)，第 j 个 cube 用 COLORS[order[j%3]]，名字带序号。
* 外环交换：perm = randperm(10)（追加在全部放置与 cube 抽样之后）；第 k 窗从 perm[k%10] 起按排列顺延试发起者 o，
  搭档 p = 干扰容器中 XY 最近邻（float32，严格 <，平局取序号小）；可行 = 两对联合连续证明通过 ∧ 两条外环中心路径
  全程精确可见 ∧ 离每个内环容器（静止与移动）圆距（中心距 − 2r）≥ 0.04 ∧（BUS）离两按钮中心 ≥ 0.122；lane 0.07。
  某窗 10 个发起者都不可行 ⇒ 整段重抽干扰布局（同一专用流继续抽），最多 16 次，再失败候选级拒绝。
* 内环对内环：reset 时按预演逐窗 check_swap_sweep(内环对, 其余内环)；有拒绝 ⇒ 候选级拒绝。
* 认证预筛（PREFILTER）：外接圆严格判据只跳过已证明分离的对，判定不变。

本文件只在探针产物目录，不改任何被 git 跟踪的文件。
"""
from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from multi_sweep import check_multi_swap_sweep  # noqa: E402

from robomme.robomme_env.utils import bin_collision as bc  # noqa: E402
from robomme.robomme_env.utils.bin_collision import (  # noqa: E402
    ObjectState, bin_actor_pose, bin_shape_specs, check_swap_sweep, quat_to_matrix)
from robomme.robomme_env.utils.unmask_distractors import bin_corners, bin_geometry, visible_in_camera  # noqa: E402
from robomme.robomme_env.utils.unmask_distractors import (  # noqa: E402
    BASE_CAMERA_EYE, BASE_CAMERA_TARGET, BASE_CAMERA_FOV, _camera_axes)
from robomme.robomme_env.utils.unmask_swap_xhard import bin_footprint_radius  # noqa: E402

CUBE_HALF = 0.02
CFG = dict(count=10, ring=(0.2675, 0.45), cube_count=(5, 5), min_gap=CUBE_HALF * 0.75, max_trials=1024,
           lane=0.07, inner_clear=0.04, btn_dist=0.122, layout_max_attempts=16)
COLORS = ["yellow", "cyan", "magenta"]
HALF, REACH_ANY_YAW, HEIGHT = bin_geometry(CUBE_HALF)          # 0.0275, 0.042426, 0.054
RADIUS = bin_footprint_radius(CUBE_HALF)                        # 0.042426
OUTER_HALF = CUBE_HALF * 2.5 * 0.5 + 0.005                       # 0.03
SHAPES = bin_shape_specs(CUBE_HALF)
S = np.linspace(0.0, 1.0, 401)
DS = S[1] - S[0]
PREFILTER = os.environ.get("SWAP10_PREFILTER", "1") != "0"
STATS = {"h1_calls": 0, "h1_s": 0.0, "joint_calls": 0, "joint_s": 0.0}


class SceneReject(Exception):
    """候选级拒绝（进程内原型里转成 SceneGenerationError）。"""

    def __init__(self, kind, msg):
        super().__init__(msg)
        self.kind = kind


# ── 几何小件 ───────────────────────────────────────────────────────────────────
def state(name, x, y, yaw):
    p, q = bin_actor_pose([x, y], yaw, CUBE_HALF)
    return ObjectState(name=name, p=p, q=q, shapes=SHAPES)


def yaw_axes(q):
    rot = quat_to_matrix(q)
    u = rot[:2, 0] / np.linalg.norm(rot[:2, 0])
    v = rot[:2, 1] / np.linalg.norm(rot[:2, 1])
    return np.stack([u, v], axis=1)


def bin_obb(x, y, q, pad):
    """容器的 2D OBB（与 _trimesh_box_to_obb2d(get_actor_obb) 同口径：外廓半边 0.03 + pad）。"""
    return (np.array([x, y], dtype=np.float64), yaw_axes(q), np.array([OUTER_HALF + pad, OUTER_HALF + pad]))


def hits(pos, obbs, reach):
    for c, A, h in obbs:
        local = A.T @ (pos - c)
        closest = c + A @ np.clip(local, -h, h)
        if np.linalg.norm(pos - closest) < reach:
            return True
    return False


_EYE, _FWD, _RIGHT, _UP = _camera_axes(BASE_CAMERA_EYE, BASE_CAMERA_TARGET)
_TAN = math.tan(BASE_CAMERA_FOV / 2)
_CORNER = np.array([(sx * REACH_ANY_YAW, sy * REACH_ANY_YAW, z) for sx in (-1, 1) for sy in (-1, 1) for z in (0.0, HEIGHT)])


def visible_xy_many(xy):
    """向量化的精确 8 角点可见判据（与 visible_in_camera(bin_corners(...)) 逐点等价）。xy: (N,2) → (N,) bool。"""
    xy = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
    pts = np.concatenate([xy, np.zeros((len(xy), 1))], axis=1)[:, None, :] + _CORNER[None]
    d = pts - _EYE
    depth = d @ _FWD
    ok = depth > 1e-6
    safe = np.where(ok, depth, 1.0)
    ok &= np.abs((d @ _RIGHT) / safe) / _TAN <= 1.0
    ok &= np.abs((d @ _UP) / safe) / _TAN <= 1.0
    return ok.all(axis=1)


def visible_xy(x, y):
    return visible_in_camera(bin_corners(float(x), float(y), REACH_ANY_YAW, HEIGHT))


def lane_paths(xy_a, xy_b, lane):
    a, b = np.asarray(xy_a, float)[:2], np.asarray(xy_b, float)[:2]
    delta, normal = bc._lane_endpoints(a, b)
    s = S[:, None]
    off = lane * np.sin(np.pi * s)
    return a + delta * s + normal * off, b - delta * s - normal * off, float(np.linalg.norm(delta)) + lane * np.pi


def mind(A, B):
    return float(np.min(np.linalg.norm(A - B, axis=1)))


# ── 内环预演 ───────────────────────────────────────────────────────────────────
def predict_inner(states, positions, initiators):
    """与 unmask_swap_xhard.predict_swap_sweeps 同语义，但返回每窗 (a, b, 起态全表)。positions 为 float32 XY。"""
    states = list(states)
    pos = [np.asarray(p, dtype=np.float32)[:2] for p in positions]
    seq = []
    for a in initiators:
        b, best = None, float("inf")
        for j, p in enumerate(pos):
            if j == a:
                continue
            d = np.linalg.norm(pos[a] - p)
            if d < best:
                b, best = j, d
        seq.append((a, b, list(states)))
        sa, sb = states[a], states[b]
        states[a] = ObjectState(name=sa.name, p=sb.p.copy(), q=sb.q.copy(), shapes=sa.shapes)
        states[b] = ObjectState(name=sb.name, p=sa.p.copy(), q=sa.q.copy(), shapes=sb.shapes)
        pos[a], pos[b] = pos[b].copy(), pos[a].copy()
    return seq


def inner_prejudge(seq):
    """L20：内环对内环扫掠 reset 预判；返回第一处拒绝 (k, rejection) 或 None。"""
    for k, (a, b, st) in enumerate(seq):
        by = [s for j, s in enumerate(st) if j not in (a, b)]
        # 单对时 check_multi_swap_sweep 与仓库 check_swap_sweep 逐值相同（m0c 15/15）；PREFILTER 只跳过已证明分离的对
        _g, rej, _n = check_multi_swap_sweep([(st[a], st[b])], by, sweep_index=k, stage="inner_prejudge",
                                             circle_r=RADIUS if PREFILTER else None)
        if rej is not None:
            return k, rej
    return None


# ── 干扰容器放置（统一采样器 + H1）────────────────────────────────────────────────
def _h1_reject(cand, cand_xy, seq_paths, seq):
    for k, (a, b, st) in enumerate(seq):
        if PREFILTER:
            pa, pb, v = seq_paths[k]
            if min(mind(pa, cand_xy[None]), mind(pb, cand_xy[None])) - 2 * RADIUS > v * DS / 2:
                continue
        STATS["h1_calls"] += 1
        t = time.perf_counter()
        if PREFILTER:
            # 内环对自身已在 inner_prejudge 证过，这里只证「候选 × 两个 mover」，且只精算圆判有风险的对（判定不变）
            rej = check_multi_swap_sweep([(st[a], st[b])], [cand], sweep_index=k, stage="distractor",
                                         only_involving={cand.name}, circle_r=RADIUS)[1]
        else:  # V4 原样：仓库 check_swap_sweep（含内环对自身）
            rej = check_swap_sweep(st[a], st[b], [cand], sweep_index=k, stage="distractor")[1]
        STATS["h1_s"] += time.perf_counter() - t
        if rej is not None:
            return True
    return False


def sample_layout(gen, base_obbs, seq, cfg=CFG):
    """一次完整的干扰布局尝试；放不满返回 None（对应 SceneGenerationError）。"""
    count, (r_in, r_out) = cfg["count"], cfg["ring"]
    gap = cfg["min_gap"]
    reach = HALF + gap
    seq_paths = [lane_paths(st[a].p[:2], st[b].p[:2], bc.LANE_OFFSET) for a, b, st in seq]
    obbs = list(base_obbs)
    placements = []
    for i in range(count):
        chosen = None
        for _ in range(cfg["max_trials"]):
            x = float(torch.rand(1, generator=gen).item() * 2.0 * r_out - r_out)
            y = float(torch.rand(1, generator=gen).item() * 2.0 * r_out - r_out)
            if not (r_in <= max(abs(x), abs(y)) <= r_out):
                continue
            if not visible_xy(x, y):
                continue
            here = np.array([x, y])
            if hits(here, obbs, reach):
                continue
            yaw = float(torch.rand(1, generator=gen).item() * 90.0)
            cand = state(f"distractor_bin_{i}", x, y, yaw)
            if seq and _h1_reject(cand, here, seq_paths, seq):
                continue
            chosen = (x, y, yaw, cand)
            break
        if chosen is None:
            return None
        placements.append(chosen)
        obbs.append(bin_obb(chosen[0], chosen[1], chosen[3].q, gap))
    lo, hi = cfg["cube_count"]
    n_cube = int(torch.randint(lo, hi + 1, (1,), generator=gen).item())
    cube_bins = torch.randperm(count, generator=gen)[:n_cube].tolist()
    order = torch.randperm(3, generator=gen).tolist()
    colors = [COLORS[order[j % 3]] for j in range(n_cube)]
    return dict(placements=[(x, y, yaw) for x, y, yaw, _ in placements], states=[c for *_, c in placements],
                cube_bins=cube_bins, cube_colors=colors)


# ── 外环规划 ───────────────────────────────────────────────────────────────────
def eval_candidate(k, a, b, ist, o, p, ost, buttons, cfg=CFG):
    """返回 (ok, reason)。reason ∈ vis / btn / inner_clear / exact。"""
    lane = cfg["lane"]
    oa, ob, v_out = lane_paths(ost[o].p[:2], ost[p].p[:2], lane)
    if not visible_xy_many(np.vstack([oa, ob])).all():
        return False, "vis"
    for bt in buttons:
        btn = np.asarray(bt, float)[None, :2]
        if min(mind(oa, btn), mind(ob, btn)) < cfg["btn_dist"]:
            return False, "btn"
    ia, ib, _v = lane_paths(ist[a].p[:2], ist[b].p[:2], bc.LANE_OFFSET)
    c = min(mind(oa, ia), mind(oa, ib), mind(ob, ia), mind(ob, ib))
    for j, s in enumerate(ist):
        if j in (a, b):
            continue
        c = min(c, mind(oa, s.p[None, :2]), mind(ob, s.p[None, :2]))
    if c - 2 * RADIUS < cfg["inner_clear"]:
        return False, "inner_clear"
    by = [s for j, s in enumerate(ist) if j not in (a, b)] + [s for j, s in enumerate(ost) if j not in (o, p)]
    STATS["joint_calls"] += 1
    t = time.perf_counter()
    _g, rej, _n = check_multi_swap_sweep([(ist[a], ist[b]), (ost[o], ost[p])], by, lane_offsets=[bc.LANE_OFFSET, lane],
                                         sweep_index=k, stage="joint", circle_r=RADIUS if PREFILTER else None)
    STATS["joint_s"] += time.perf_counter() - t
    if rej is not None:
        return False, "exact"
    return True, None


def nearest_outer(ost, o):
    pos = [np.asarray(s.p[:2], dtype=np.float32) for s in ost]
    best, bd, second = None, float("inf"), float("inf")
    for j, q in enumerate(pos):
        if j == o:
            continue
        d = float(np.linalg.norm(pos[o] - q))
        if d < bd:
            best, second, bd = j, bd, d
        elif d < second:
            second = d
    return best, bd, second - bd


def plan_windows(gen, layout, seq, buttons, cfg=CFG):
    """返回 dict(ok, pairs, tries, fails, near_tie)；ok=False 时 fail_win 为不可行窗口。"""
    count = cfg["count"]
    perm = torch.randperm(count, generator=gen).tolist()
    ost = list(layout["states"])
    pairs, tries, fails, near_tie = [], [], {}, 0
    for k, (a, b, ist) in enumerate(seq):
        chosen = None
        for j in range(count):
            o = perm[(k + j) % count]
            p, _d, margin = nearest_outer(ost, o)
            ok, why = eval_candidate(k, a, b, ist, o, p, ost, buttons, cfg)
            if ok:
                chosen = (o, p, j + 1, margin)
                break
            fails[why] = fails.get(why, 0) + 1
        if chosen is None:
            return dict(ok=False, perm=perm, fail_win=k, pairs=pairs, tries=tries, fails=fails, near_tie=near_tie)
        o, p, t, margin = chosen
        near_tie += margin < 0.005
        pairs.append((o, p))
        tries.append(t)
        so, sp = ost[o], ost[p]
        ost[o] = ObjectState(name=so.name, p=sp.p.copy(), q=sp.q.copy(), shapes=so.shapes)
        ost[p] = ObjectState(name=sp.name, p=so.p.copy(), q=so.q.copy(), shapes=sp.shapes)
    return dict(ok=True, perm=perm, pairs=pairs, tries=tries, fails=fails, near_tie=near_tie,
                final_xy=[s.p[:2].tolist() for s in ost])


def plan_episode(gen, base_obbs, seq, buttons, cfg=CFG):
    """reset 时的完整规划：内环预判 → 最多 16 次（放置 + 外环规划）。成功返回 dict，失败抛 SceneReject。"""
    t0 = time.perf_counter()
    pre = inner_prejudge(seq)
    t_pre = time.perf_counter() - t0
    if pre is not None:
        raise SceneReject("inner_inner", f"内环对内环扫掠第 {pre[0]} 段拒绝：{pre[1].summary()}")
    attempts = []
    for attempt in range(1, cfg["layout_max_attempts"] + 1):
        layout = sample_layout(gen, base_obbs, seq, cfg)
        if layout is None:
            raise SceneReject("placement", f"第 {attempt} 次干扰布局放不满 {cfg['count']} 个")
        plan = plan_windows(gen, layout, seq, buttons, cfg)
        attempts.append(dict(ok=plan["ok"], fail_win=plan.get("fail_win"), tries=plan["tries"], fails=plan["fails"]))
        if plan["ok"]:
            return dict(layout=layout, plan=plan, attempts=attempts, n_attempts=attempt,
                        t_prejudge=t_pre, t_total=time.perf_counter() - t0)
    raise SceneReject("exhausted", f"{cfg['layout_max_attempts']} 次干扰布局都有窗口不可行")
