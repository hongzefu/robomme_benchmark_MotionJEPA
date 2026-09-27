"""离线 mplib 螺旋规划模型：复现 PatternLock 每段 solve_swingonto 的帧数（不起仿真器）。

口径（与 PandaStickMotionPlanningSolver 一致）：
- mplib.Planner(urdf=panda_stick.urdf, srdf=panda_stick.srdf, move_group="panda_hand_tcp")
- base pose = [-0.615,0,0]；joint_vel_limits ×0.3（数据生成与 DemonstrationWrapper 都传 0.3），acc ×0.9
- plan_screw(target=[x,y,0.07,q_tcp], qpos, time_step=0.05)（control_timestep = 1/20）
- 每段两次 screw：第二次从第一次终点出发（离线近似：假设 PD 跟踪到位）
"""
import numpy as np, mplib, os
from pathlib import Path
import mani_skill
ASSET = Path(mani_skill.__file__).parent / "assets" / "robots" / "panda"
URDF = str(ASSET / "panda_stick.urdf"); SRDF = str(ASSET / "panda_stick.srdf")
DT = 0.05
Q0 = np.array([0, 0, 0, -np.pi / 2, 0, np.pi / 2, np.pi / 4])

def make_planner(vel_scale=0.3, acc_scale=0.9):
    p = mplib.Planner(urdf=URDF, srdf=SRDF, move_group="panda_hand_tcp")
    p.set_base_pose(np.array([-0.615, 0, 0, 1, 0, 0, 0]))
    p.joint_vel_limits = np.asarray(p.joint_vel_limits) * vel_scale
    p.joint_acc_limits = np.asarray(p.joint_acc_limits) * acc_scale
    return p

def tcp_pose_world(p, q):
    p.pinocchio_model.compute_forward_kinematics(p.pad_qpos(np.asarray(q, float).copy()))
    idx = p.link_name_2_idx[p.move_group]
    pose = np.asarray(p.pinocchio_model.get_link_pose(idx), float)  # 相对 base
    pose = pose.copy(); pose[0] += -0.615
    return pose

def node_xy_grid(idx, R, C, center=(-0.1, 0.0), spacing=0.1):
    r, c = divmod(idx, C)
    return center[0] + (r - (R - 1) / 2) * spacing, center[1] + (c - (C - 1) / 2) * spacing

FALLBACKS = []  # 记录 screw 失败后走兜底的次数（真实系统此时改走 RRT*）

def screw_len(p, q, xy, quat, robust=True):
    goal = np.concatenate([[xy[0], xy[1], 0.07], quat])
    res = p.plan_screw(goal, np.asarray(q, float), time_step=DT)
    if res["status"] != "Success":
        res = p.plan_screw(goal, np.asarray(q, float), time_step=DT)
        if res["status"] != "Success":
            if not robust:
                return None, q
            # 兜底近似 RRT*：IK 到目标，关节空间直线 + 同一 TOPP 时间参数化
            gb = p.transform_goal_to_wrt_base(goal)
            st, sols = p.IK(gb, p.pad_qpos(np.asarray(q, float).copy()))
            if st != "Success" or len(sols) == 0:
                FALLBACKS.append(("ik_fail", tuple(np.round(xy, 3))))
                return None, q
            qg = np.asarray(sols[0])[:7]
            d = np.linalg.norm(qg - np.asarray(q)[:7])
            if d < 1e-3:
                FALLBACKS.append(("at_goal", tuple(np.round(xy, 3))))
                return 1, qg
            n = max(2, int(np.ceil(d / 0.1)) + 1)
            path = np.linspace(np.asarray(q)[:7], qg, n)
            _, pos, _, _, _ = p.TOPP(path, DT)
            FALLBACKS.append(("rrt_proxy", tuple(np.round(xy, 3))))
            return len(pos), qg
    pos = res["position"]
    return len(pos), pos[-1][:7]

def path_frames(p, nodes, R, C, q_start=None, quat=None, spacing=0.1, center=(-0.1, 0.0)):
    """返回 (首段 NO RECORD 帧数, 各段帧数列表)。每段 = screw1 + screw2。"""
    q = Q0.copy() if q_start is None else np.asarray(q_start, float)
    if quat is None:
        quat = tcp_pose_world(p, q)[3:]
    out = []
    for k, n in enumerate(nodes):
        xy = node_xy_grid(n, R, C, center, spacing)
        a, q = screw_len(p, q, xy, quat)
        b, q = screw_len(p, q, xy, quat)
        out.append(None if a is None or b is None else a + b)
    return out[0], out[1:]

if __name__ == "__main__":
    p = make_planner()
    print("tcp pose at Q0:", tcp_pose_world(p, Q0))
    first, segs = path_frames(p, [1, 0, 6, 12, 16, 10, 15, 20, 21, 17, 18, 22, 23, 24, 19, 14, 13, 9, 8, 3, 4], 5, 5)
    print(first, segs, sum(segs))
