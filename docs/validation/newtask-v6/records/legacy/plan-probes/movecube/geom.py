"""几何工具：解析接受率、相机投影（base_camera = front_rgb）、可达性代理、杆-方块重叠。"""
from __future__ import annotations

import math

import numpy as np

BASE = np.array([-0.615, 0.0])          # MoveCube._load_agent 的机器人基座
EYE = np.array([0.3, 0.0, 0.4])         # MoveCube._default_sensor_configs 实际使用的 base_camera
TGT = np.array([0.0, 0.0, -0.2])
TABLE_X = (-0.7402168, 0.4688596)       # TableSceneBuilder.build 的 aabb
TABLE_Y = (-1.2148621, 1.2030163)


def accept_square_annulus(h, R, R_out=None, n=4001):
    """[-h,h]² 均匀抽样落在 R ≤ |c| (≤ R_out) 的概率（格点数值积分）。"""
    xs = np.linspace(-h, h, n)
    X, Y = np.meshgrid(xs, xs)
    r = np.hypot(X, Y)
    ok = r >= R
    if R_out is not None:
        ok &= r <= R_out
    return float(ok.mean())


def _cam_basis():
    f = TGT - EYE; f = f / np.linalg.norm(f)
    left = np.cross([0, 0, 1.0], f); left /= np.linalg.norm(left)
    up = np.cross(f, left)
    return f, left, up


F, L, U = _cam_basis()


def project(p):
    """世界点 → (col,row) 像素（256×256，fov=π/2 ⇒ 焦距 128）；返回 None 表示在相机后方。"""
    v = np.asarray(p, dtype=np.float64) - EYE
    xf, yl, zu = v @ F, v @ L, v @ U
    if xf <= 1e-6:
        return None
    return 128.0 - 128.0 * yl / xf, 128.0 - 128.0 * zu / xf


def pixel_margin(points):
    """一组点离画面边缘的最小像素余量（负数 = 出画）。"""
    m = np.inf
    for p in points:
        q = project(p)
        if q is None:
            return -np.inf
        c, r = q
        m = min(m, c, 255 - c, r, 255 - r)
    return m


def cube_points(xy, yaw, hs=0.02):
    pts = []
    c, s = math.cos(yaw), math.sin(yaw)
    for dx in (-hs, hs):
        for dy in (-hs, hs):
            for z in (0.0, 2 * hs):
                pts.append((xy[0] + c * dx - s * dy, xy[1] + s * dx + c * dy, z))
    return pts


def disk_points(xy, r=0.04):
    return [(xy[0] + r * math.cos(a), xy[1] + r * math.sin(a), 0.005) for a in np.linspace(0, 2 * math.pi, 16, endpoint=False)]


def peg_points(root, yaw):
    u = np.array([math.cos(yaw), math.sin(yaw)]); n = np.array([-u[1], u[0]])
    pts = []
    for t in (-0.15, 0.05):
        for w in (-0.01, 0.01):
            q = root + t * u + w * n
            pts += [(q[0], q[1], 0.0), (q[0], q[1], 0.02)]
    return pts


def footprint():
    """相机在桌面 z=0 上的可见范围：沿 y=0 的 x 区间，以及若干 x 处的 y 半宽。"""
    xs = np.linspace(-1.0, 0.6, 1601)
    vis = [x for x in xs if (lambda q: q is not None and 0 <= q[0] <= 255 and 0 <= q[1] <= 255)(project((x, 0, 0)))]
    rows = {}
    for x in (-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4):
        ys = np.linspace(0, 1.0, 2001)
        ok = [y for y in ys if (lambda q: q is not None and 0 <= q[0] <= 255 and 0 <= q[1] <= 255)(project((x, y, 0)))]
        rows[x] = max(ok) if ok else None
    return (min(vis), max(vis)), rows


def obb_overlap(c1, A1, h1, c2, A2, h2):
    d = c2 - c1
    for A in (A1, A2):
        for k in range(2):
            ax = A[:, k]
            r1 = abs(A1[:, 0] @ ax) * h1[0] + abs(A1[:, 1] @ ax) * h1[1]
            r2 = abs(A2[:, 0] @ ax) * h2[0] + abs(A2[:, 1] @ ax) * h2[1]
            if abs(d @ ax) > r1 + r2:
                return False
    return True


def rot(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]])


def peg_cube_overlap(root, pyaw, cube, cyaw, pad=0.0):
    u = np.array([math.cos(pyaw), math.sin(pyaw)])
    body = (root - 0.05 * u, rot(pyaw), np.array([0.10 + pad, 0.01 + pad]))
    cb = (np.asarray(cube), rot(cyaw), np.array([0.02, 0.02]))
    return obb_overlap(*body, *cb)


def goal_under_peg(root, pyaw, goal, r=0.04):
    u = np.array([math.cos(pyaw), math.sin(pyaw)])
    c = root - 0.05 * u; A = rot(pyaw); h = np.array([0.10, 0.01])
    local = A.T @ (np.asarray(goal) - c)
    return np.linalg.norm(local - np.clip(local, -h, h)) < r


def push_starts(cube, goal):
    """与 subgoal_planner_func 同式：peg_push 起点 cube−0.1d−0.1·lat·direction；gripper_push 起点 cube−0.05d。"""
    d = goal - cube; d = d / np.linalg.norm(d)
    direction = 1 if cube[1] - goal[1] > 0 else -1
    lat = np.array([-d[1], d[0]])
    peg_start = cube - 0.1 * d - lat * 0.1 * direction
    peg_end = goal - 0.03 * d - lat * 0.1 * direction
    grip_start = cube - 0.05 * d
    return peg_start, peg_end, grip_start
