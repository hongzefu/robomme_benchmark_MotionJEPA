# -*- coding: utf-8 -*-
"""MoveCube 可达区域探针：在桌面网格 × 8 个手腕 yaw 上测三类末端位姿能否到达。

三类位姿（与 subgoal_planner_func.py 中求解器的姿态构造逐项对齐）：
  grasp  ：solve_pickup 的顶抓。approaching=(0,0,-1)，closing=(cos yaw, sin yaw, 0)，
           先到 z=0.15 的 reach 位姿，再从那里下到 z=0.02（两步 screw）。
  push   ：solve_push_to_target 的 push_quat。x 轴=推方向(cos yaw, sin yaw, 0)，z 轴向下，
           推方向 x 分量 < 0（target_x < obj_x）时再右乘 Rz(180°)。位置 (x,y,0.02)。
  peg    ：solve_push_to_target_with_peg 的起点位姿。base_quat 同上（不做 180° 翻转），
           右乘 Rz(90°·s)，s = direction·obj_flag ∈ {+1,-1}。xhard 的抓杆翻转再右乘 Rz(π)
           等价于把 s 取反，因此 s=±1 两种已覆盖翻转情形。位置直接取 (x,y,0.02) 作为 start_pos。

判据（两种执行口径）：
  dry  ：planner.move_to_pose_with_screw(dry_run=True) 返回 dict（非 -1），
         再把机器人 qpos 设为规划轨迹末点、读 tcp 位置，误差 < 1 cm 记成功。
  exec ：真正调用 move_to_pose_with_screw（FailAware 包装，-1 抛 ScrewPlanFailure），
         在物理仿真里跟踪轨迹，到位后读实际 tcp 位置，误差 < 1 cm 记成功。
screw 失败时另用 mplib 的 IK 检查目标位姿是否存在逆解（ik_ok 列），
代表正式生成里 screw 失败后回退 RRT* 的理论上限。
"""
import argparse, csv, math, os, sys, time
import numpy as np
import gymnasium as gym
import sapien
import torch

import robomme.robomme_env  # noqa: F401  注册环境
from robomme.robomme_env.utils.planner_fail_safe import (
    FailAwarePandaArmMotionPlanningSolver, ScrewPlanFailure)
from mani_skill.utils.geometry.rotation_conversions import (
    matrix_to_quaternion, euler_angles_to_matrix, quaternion_multiply)

QPOS0 = np.array([0, 0, 0, -np.pi / 2, 0, np.pi / 2, np.pi / 4, 0.04, 0.04], dtype=np.float32)
Z_OBJ = 0.02
Z_REACH = 0.15
TOL = 0.01


def rz_quat(deg):
    m = euler_angles_to_matrix(torch.deg2rad(torch.tensor([0.0, 0.0, deg], dtype=torch.float32)),
                               convention="XYZ")
    return matrix_to_quaternion(m.unsqueeze(0))[0]


def base_push_quat(yaw):
    """x 轴=推方向、z 轴向下、y 轴右手定则（照抄两个推求解器）。"""
    d = np.array([math.cos(yaw), math.sin(yaw)])
    x_axis = np.array([d[0], d[1], 0.0])
    z_axis = np.array([0.0, 0.0, -1.0])
    y_axis = np.cross(z_axis, x_axis)
    y_axis /= np.linalg.norm(y_axis)
    R = np.column_stack([x_axis, y_axis, z_axis])
    return matrix_to_quaternion(torch.from_numpy(R).float().unsqueeze(0))[0]


def push_quat(yaw):
    q = base_push_quat(yaw)
    if math.cos(yaw) < -1e-6:  # 对应 target_pos[0] < obj_pos[0]
        q = quaternion_multiply(q.unsqueeze(0), rz_quat(180.0).unsqueeze(0))[0]
    return q.cpu().numpy()


def peg_quat(yaw, s):
    q = base_push_quat(yaw)
    q = quaternion_multiply(q.unsqueeze(0), rz_quat(90.0 * s).unsqueeze(0))[0]
    return q.cpu().numpy()


def grasp_quat(agent, yaw):
    approaching = np.array([0.0, 0.0, -1.0])
    closing = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    return np.asarray(agent.build_grasp_pose(approaching, closing, np.zeros(3)).q)


class Prober:
    def __init__(self, obs_mode, exec_mode, seed=0):
        self.env = gym.make("MoveCube", obs_mode=obs_mode, control_mode="pd_joint_pos",
                            render_mode="rgb_array", reward_mode="dense", seed=seed,
                            difficulty="xhard")
        self.env.reset()
        u = self.env.unwrapped
        self.u = u
        self.agent = u.agent
        # 把方块、goal、杆全部挪到远处，避免碰撞干扰
        far = sapien.Pose(p=[10.0, 10.0, 1.0])
        for name, a in u.scene.actors.items():
            if name in ("table-workspace", "ground"):
                continue
            a.set_pose(far)
        for name, art in u.scene.articulations.items():
            if name.startswith("panda"):
                continue
            art.set_root_pose(far)
        self.planner = FailAwarePandaArmMotionPlanningSolver(
            self.env, debug=False, vis=False, base_pose=self.agent.robot.pose,
            visualize_target_grasp_pose=False, print_env_info=False)
        self.exec_mode = exec_mode
        self.mp = self.planner.planner  # mplib.Planner

    def reset_robot(self):
        self.agent.reset(QPOS0)
        self.agent.robot.set_qvel(np.zeros(9, dtype=np.float32))

    def tcp_p(self):
        return self.agent.tcp.pose.p[0].cpu().numpy().astype(np.float64)

    def ik_ok(self, p, q):
        """mplib 0.1.1 的 IK 只收基座系位姿，先转到基座系；含 20 个随机初值与自碰撞检查。"""
        goal = self.mp.transform_goal_to_wrt_base(np.concatenate([p, q]))
        st, _ = self.mp.IK(goal, self.agent.robot.get_qpos().cpu().numpy()[0], n_init_qpos=20)
        return st == "Success"

    def tcp_q(self):
        return self.agent.tcp.pose.q[0].cpu().numpy().astype(np.float64)

    @staticmethod
    def rot_err_deg(q1, q2):
        d = abs(float(np.dot(q1 / np.linalg.norm(q1), q2 / np.linalg.norm(q2))))
        return math.degrees(2 * math.acos(min(1.0, d)))

    def move(self, p, q):
        """一次 screw 移动；返回 (plan_ok, err_cm, rot_err_deg)。

        注意：mplib 0.1.1 的 plan_screw 是雅可比伪逆开环积分，返回 Success 时末点也可能偏离目标
        （线性化漂移），因此除了看是否规划失败，还要量到位误差。"""
        pose = sapien.Pose(p=list(map(float, p)), q=list(map(float, q)))
        try:
            if self.exec_mode == "exec":
                self.planner.move_to_pose_with_screw(pose)
            else:
                res = self.planner.move_to_pose_with_screw(pose, dry_run=True)
                qf = res["position"][-1]
                full = self.agent.robot.get_qpos().cpu().numpy()[0].copy()
                full[: len(qf)] = qf
                self.agent.robot.set_qpos(full)
        except ScrewPlanFailure:
            return False, float("nan"), float("nan")
        err = float(np.linalg.norm(self.tcp_p() - np.asarray(p))) * 100
        return True, err, self.rot_err_deg(self.tcp_q(), np.asarray(q, dtype=np.float64))

    def test(self, x, y, yaw_deg, ptype, s):
        """返回 dict：plan_ok（所有 screw 段都没失败）、err_cm/rot_deg（最终位姿误差）、
        ok（plan_ok 且 err<1cm）、note、ik_ok（仅失败时测：目标位姿是否存在逆解）。"""
        yaw = math.radians(yaw_deg)
        self.reset_robot()
        target = np.array([x, y, Z_OBJ])
        r = {"reach_err_cm": ""}
        if ptype == "grasp":
            q = grasp_quat(self.agent, yaw)
        elif ptype.startswith("push"):
            q = push_quat(yaw)
        else:
            q = peg_quat(yaw, s)
        if ptype in ("grasp", "push2", "peg2"):
            # 两段式：先到同姿态 z=0.15 的悬停点，再竖直下到 z=0.02（grasp 即 solve_pickup 原样）
            pok, err, rot = self.move(np.array([x, y, Z_REACH]), q)
            if not pok:
                note = "reach_screw_fail"
            else:
                r["reach_err_cm"] = f"{err:.3f}"
                pok, err, rot = self.move(target, q)
                note = "down_screw_fail" if not pok else ""
        else:
            pok, err, rot = self.move(target, q)
            note = "screw_fail" if not pok else ""
        ok = bool(pok and err < TOL * 100)
        if pok:
            note = "ok" if ok else "drift_far"
        ik = ""
        if not ok:
            self.reset_robot()
            ik = int(self.ik_ok(target, q))
        r.update(plan_ok=int(pok), ok=int(ok), err_cm=f"{err:.3f}", rot_deg=f"{rot:.2f}", note=note, ik_ok=ik)
        return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--obs-mode", default="state")
    ap.add_argument("--exec-mode", default="dry", choices=["dry", "exec"])
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--xmin", type=float, default=-0.40)
    ap.add_argument("--xmax", type=float, default=0.35)
    ap.add_argument("--ymin", type=float, default=-0.40)
    ap.add_argument("--ymax", type=float, default=0.40)
    ap.add_argument("--types", default="grasp,push,peg")
    ap.add_argument("--points", default=None, help="可选：只测此 csv 里的 (x,y) 点")
    ap.add_argument("--limit", type=int, default=0, help="每类位姿最多测多少条（计时用）")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    pr = Prober(a.obs_mode, a.exec_mode)
    if a.points:
        pts = sorted({(round(float(r["x"]), 4), round(float(r["y"]), 4))
                      for r in csv.DictReader(open(a.points))})
    else:
        xs = np.round(np.arange(a.xmin, a.xmax + 1e-9, a.step), 4)
        ys = np.round(np.arange(a.ymin, a.ymax + 1e-9, a.step), 4)
        pts = [(float(x), float(y)) for x in xs for y in ys]
    yaws = list(range(0, 360, 45))
    f = open(a.out, "w", newline="")
    w = csv.writer(f)
    cols = ["x", "y", "yaw_deg", "pose_type", "direction", "ok", "err_cm", "note",
            "plan_ok", "rot_deg", "reach_err_cm", "ik_ok", "exec_mode"]
    w.writerow(cols)
    for ptype in a.types.split(","):
        dirs = [1, -1] if ptype.startswith("peg") else [0]
        t0 = time.time()
        n = nok = 0
        for (x, y) in pts:
            for yd in yaws:
                for s in dirs:
                    r = pr.test(x, y, yd, ptype, s)
                    r.update(x=x, y=y, yaw_deg=yd, pose_type=ptype, direction=s, exec_mode=a.exec_mode)
                    w.writerow([r[c] for c in cols])
                    n += 1
                    nok += r["ok"]
                    if a.limit and n >= a.limit:
                        break
                if a.limit and n >= a.limit:
                    break
            if a.limit and n >= a.limit:
                break
            if n % 400 < len(yaws) * len(dirs):
                f.flush()
                print(f"[{ptype}] 进度 {n} 条，成功 {nok}，已用 {time.time()-t0:.1f}s", flush=True)
        dt = time.time() - t0
        print(f"TYPE_DONE {ptype} n={n} ok={nok} 耗时={dt:.1f}s 每条={dt/max(n,1)*1000:.1f}ms", flush=True)
    f.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
