"""把仓库 check_swap_sweep 推广到「同一窗口里多对同时交换」（只在 scratch 里，不改仓库）。

依据：内外两对用同一个窗口 [start, end] 与同一 smoothstep ⇒ 同一控制步上 alpha 相同 ⇒ 全体位姿是
同一个参数 s 的函数。仓库 _prove_pair 本来就支持「两个都在动」的对象（交换双方就是这样证的），
所以只需把检查对象对扩成：每对内部 + 跨对的四个 mover×mover + 每个 mover×每个静止对象。
判据、常量、粗筛与二分证明全部复用仓库实现。
"""
from __future__ import annotations

import math

import numpy as np

from robomme.robomme_env.utils import bin_collision as bc


class _MoverOffset(bc._Mover):
    """可调弯道侧移的 mover（仓库 _Mover 把 LANE_OFFSET 写死为模块常量）。"""

    lane_offset: float = bc.LANE_OFFSET

    def pose_at(self, s):
        offset = self.lane_offset * math.sin(math.pi * s)
        xy = self.xy0 + self.sign * (self.delta * s + self.normal * offset)
        return np.array([xy[0], xy[1], self.z], dtype=np.float64), bc._quat_at(self.q0, self.q1, s)

    def bounding_sphere(self):
        mid_xy = self.xy0 + self.sign * (self.delta * 0.5 + self.normal * self.lane_offset)
        center = np.array([mid_xy[0], mid_xy[1], self.z], dtype=np.float64)
        return center, 0.5 * float(np.linalg.norm(self.delta)) + self.lane_offset + max(self.radii)

    def speed_bound(self, lo, hi, shape_index):
        translation = float(np.linalg.norm(self.delta)) + self.lane_offset * math.pi
        dq = self.q1 - self.q0
        m = bc._min_blend_norm(self.q0, dq, lo, hi)
        if not math.isfinite(m) or m <= bc.DEGENERATE_NORM:
            raise ValueError("四元数插值退化")
        return translation + self.radii[shape_index] * 2.0 * float(np.linalg.norm(dq)) / m


def movers_for_pair(sa, sb, lane_offset=bc.LANE_OFFSET):
    delta, normal = bc._lane_endpoints(sa.p[:2], sb.p[:2])
    out = []
    for st, other, sign, xy0 in ((sa, sb, 1.0, sa.p[:2].copy()), (sb, sa, -1.0, sb.p[:2].copy())):
        m = _MoverOffset(name=st.name, shapes=st.shapes, radii=st.radii, xy0=xy0, z=float(st.p[2]),
                         delta=delta, normal=normal, sign=sign, q0=st.q.copy(), q1=other.q.copy())
        m.lane_offset = float(lane_offset)
        out.append(m)
    return out


CIRCLE_R = None  # 由调用方设为容器外接圆半径（0.0424）后启用圆判据预筛；None 表示不预筛（与仓库逐对同路径）
_S = np.linspace(0.0, 1.0, 401)


def _xy_path(obj):
    if isinstance(obj, bc._Static):
        return np.repeat(obj.p[None, :2], len(_S), axis=0), 0.0
    off = obj.lane_offset * np.sin(np.pi * _S)[:, None]
    xy = obj.xy0 + obj.sign * (obj.delta * _S[:, None] + obj.normal * off)
    return xy, float(np.linalg.norm(obj.delta)) + obj.lane_offset * math.pi


def check_multi_swap_sweep(pairs, bystanders=(), *, lane_offsets=None, sweep_index=None, stage="sweep",
                           only_involving=None, circle_r=None):
    """pairs: [(state_a, state_b), ...] 同窗口同时交换；bystanders: 静止对象。

    only_involving: 若给定名字集合，只检查至少一方名字在集合里的对象对（用于「只评外部新增风险」）。
    返回 (最小观察 g, 拒绝证据或 None, 被精算的对象对数)。
    """
    lane_offsets = lane_offsets or [bc.LANE_OFFSET] * len(pairs)
    movers = []
    for (sa, sb), lo in zip(pairs, lane_offsets):
        movers += movers_for_pair(sa, sb, lo)
    statics = [bc._Static(name=s.name, shapes=s.shapes, radii=s.radii, p=s.p.copy(), q=s.q.copy()) for s in bystanders]
    checks = []
    for i in range(len(movers)):
        for j in range(i + 1, len(movers)):
            checks.append((movers[i], movers[j]))
    for m in movers:
        for s in statics:
            checks.append((m, s))
    if only_involving is not None:
        checks = [(l, r) for l, r in checks if l.name in only_involving or r.name in only_involving]
    if circle_r is not None:
        # 外接圆严格预筛：401 个 s 上中心距都大于 2r + 相邻采样最大相对位移/2 ⇒ 该对整段分离，跳过（判定不变）
        paths = {}
        kept = []
        for left, right in checks:
            for obj in (left, right):
                if id(obj) not in paths:
                    paths[id(obj)] = _xy_path(obj)
            (pl, vl), (pr, vr) = paths[id(left)], paths[id(right)]
            dmin = float(np.min(np.linalg.norm(pl - pr, axis=1)))
            if dmin - 2 * circle_r > (vl + vr) * (_S[1] - _S[0]) / 2:
                continue
            kept.append((left, right))
        checks = kept
    worst, coarse_worst, proved = np.inf, np.inf, 0
    for left, right in checks:
        cl, rl = left.bounding_sphere()
        cr, rr = right.bounding_sphere()
        clearance = float(np.linalg.norm(cl - cr)) - rl - rr
        if clearance > bc.EPS_M:
            coarse_worst = min(coarse_worst, clearance)
            continue
        proved += 1
        for ia in range(len(left.shapes)):
            for ib in range(len(right.shapes)):
                gap, rej = bc._prove_pair(left, right, ia, ib, stage=stage, sweep_index=sweep_index)
                if rej is not None:
                    return gap, rej, proved
                if math.isfinite(gap):
                    worst = min(worst, gap)
    if math.isfinite(worst):
        return float(worst), None, proved
    return (float(coarse_worst) if math.isfinite(coarse_worst) else float("nan")), None, proved


def mover_path_xy(sa, sb, s_values, lane_offset=bc.LANE_OFFSET):
    """两个 mover 在一组 s 上的中心 XY（与 swap_flat_two_lane 同式）。"""
    a, b = sa.p[:2], sb.p[:2]
    delta, normal = bc._lane_endpoints(a, b)
    s = np.asarray(s_values)[:, None]
    off = lane_offset * np.sin(np.pi * s)
    pa = a + delta * s + normal * off
    pb = b - delta * s - normal * off
    return pa, pb
