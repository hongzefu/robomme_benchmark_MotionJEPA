"""候选网格的几何可行性：可达性（离线螺旋规划含关节限位与自碰撞检查）、逐边帧数、前视相机投影。

相机：从 V4 实跑 h5 读 front_camera_intrinsic 与 front_camera_extrinsic（world→cam 3x4），投影 z=0.01 的节点中心，
判断是否落在 256x256 图内，并给出按钮半径 0.02 m 的像素边距。
"""
import sys, os, json, time, itertools, logging
import numpy as np, h5py, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screw_model import make_planner, screw_len, tcp_pose_world, Q0
logging.disable(logging.CRITICAL)
p = make_planner()
quat = tcp_pose_world(p, Q0)[3:]
f = h5py.File(glob.glob("artifacts/newtask-v4/v4-01/rollout/run1/episodes/PatternLock_episode_0/hdf5_files/*.h5")[0], "r")
K = f["episode_0/setup/front_camera_intrinsic"][()]
E = f["episode_0/timestep_0/obs/front_camera_extrinsic"][()]
print("K=", K.tolist()); print("E=", E.tolist())
def proj(xyz):
    pc = E[:, :3] @ np.asarray(xyz) + E[:, 3]
    # OpenCV 约定：z 前向
    uv = K @ pc
    return uv[:2] / uv[2], pc[2]
# 自检：5x5 四角
def grid(R, C, sp, center=(-0.1, 0.0)):
    return {r * C + c: (center[0] + (r - (R - 1) / 2) * sp, center[1] + (c - (C - 1) / 2) * sp) for r in range(R) for c in range(C)}
CONFIGS = [(5, 5, 0.10), (5, 6, 0.10), (6, 5, 0.10), (6, 6, 0.10), (6, 6, 0.09), (6, 6, 0.08), (7, 7, 0.07), (7, 7, 0.08)]
summary = {}
for R, C, sp in CONFIGS:
    nodes = grid(R, C, sp)
    t0 = time.time()
    # 可达性：从 Q0 直达每个节点；再从该节点构型到每个 8 邻居
    qn, reach_fail = {}, []
    for n, xy in nodes.items():
        a, q = screw_len(p, Q0, xy, quat)
        if a is None: reach_fail.append(n)
        else: qn[n] = q
    edge_frames, edge_fail = {}, []
    for n, (x, y) in nodes.items():
        if n not in qn: continue
        r, c = divmod(n, C)
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
            rr, cc = r + dr, c + dc
            if 0 <= rr < R and 0 <= cc < C:
                m = rr * C + cc
                a, q2 = screw_len(p, qn[n], nodes[m], quat)
                b, _ = (None, None) if a is None else screw_len(p, q2, nodes[m], quat)
                if a is None or b is None: edge_fail.append((n, m))
                else: edge_frames[(n, m)] = a + b
    ef = np.array(list(edge_frames.values()))
    # 相机
    uvs = [proj((x, y, 0.01))[0] for (x, y) in nodes.values()]
    uvs = np.array(uvs)
    # 按钮半径 0.02 在像素上的近似：取节点 ±0.02 的投影
    margin = min(min(u, v, 255 - u, 255 - v) for u, v in uvs)
    straight_y = [v for (a, b), v in edge_frames.items() if divmod(a, C)[0] == divmod(b, C)[0]]
    straight_x = [v for (a, b), v in edge_frames.items() if divmod(a, C)[1] == divmod(b, C)[1]]
    diag = [v for (a, b), v in edge_frames.items() if divmod(a, C)[0] != divmod(b, C)[0] and divmod(a, C)[1] != divmod(b, C)[1]]
    # 按行统计（x 越大越远离机器人）
    by_row = {}
    for (a, b), v in edge_frames.items():
        by_row.setdefault(max(divmod(a, C)[0], divmod(b, C)[0]), []).append(v)
    xs = sorted({x for x, _ in nodes.values()}); ys = sorted({y for _, y in nodes.values()})
    rec = dict(x_range=[round(xs[0], 3), round(xs[-1], 3)], y_range=[round(ys[0], 3), round(ys[-1], 3)],
               reach_fail=reach_fail, edge_fail=len(edge_fail), n_edges=len(edge_frames),
               edge_mean=round(float(ef.mean()), 1), edge_min=int(ef.min()), edge_max=int(ef.max()),
               straight_y_mean=round(float(np.mean(straight_y)), 1), straight_x_mean=round(float(np.mean(straight_x)), 1),
               diag_mean=round(float(np.mean(diag)), 1),
               row_mean={int(k): round(float(np.mean(v)), 1) for k, v in sorted(by_row.items())},
               img_u=[round(float(uvs[:, 0].min()), 1), round(float(uvs[:, 0].max()), 1)],
               img_v=[round(float(uvs[:, 1].min()), 1), round(float(uvs[:, 1].max()), 1)],
               img_min_margin_px=round(float(margin), 1), wall_s=round(time.time() - t0, 1))
    summary[f"{R}x{C}@{sp}"] = rec
    print(f"{R}x{C}@{sp}: {json.dumps(rec)}", flush=True)
json.dump(summary, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "grid_geometry.json"), "w"), indent=1)
