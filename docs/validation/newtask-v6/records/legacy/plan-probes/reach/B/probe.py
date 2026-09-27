#!/usr/bin/env python3
"""MoveCube xhard 抓杆可达性探针（真实模拟器 + 正式规划器）。

每个 worker 建一个 MoveCube(xhard) 环境、reset 一次、建与 DemonstrationWrapper 相同的
FailAwarePandaArmMotionPlanningSolver（并包上同样的 screw 1 次 → RRT* 3 次重试），
把方块 / goal 挪到 (10,10,1) 等远处，然后对分到的 (root_x, root_y, yaw) 逐个：
  机器人 agent.reset(初始 qpos) → 杆 set_pose(root, yaw) → grasp_and_lift_peg_side(env, planner, env.grasp_target)
判据：不抛异常、无规划失败（-1），且结束时 grasp_target 的 z > 0.1 并 agent.is_grasping(grasp_target)。
不修改仓库任何被跟踪的文件，只 import。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
import traceback

import numpy as np

REPO = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask"
sys.path.insert(0, os.path.join(REPO, "src"))

import gymnasium as gym  # noqa: E402
import sapien  # noqa: E402
import torch  # noqa: E402

import robomme  # noqa: E402,F401  注册环境
from robomme.robomme_env.utils import subgoal_planner_func as spf  # noqa: E402
from robomme.robomme_env.utils.planner_fail_safe import (  # noqa: E402
    FailAwarePandaArmMotionPlanningSolver,
    ScrewPlanFailure,
)
from mani_skill.utils.geometry.rotation_conversions import (  # noqa: E402
    euler_angles_to_matrix,
    matrix_to_quaternion,
)

INIT_QPOS = np.array([0.0, 0, 0, -np.pi * 4 / 8, 0, np.pi * 2 / 4, np.pi / 4, 0.04, 0.04], dtype=np.float32)
FAR = [10.0, 10.0, 1.0]


class PlanExhausted(RuntimeError):
    """screw→RRT* 全部失败（与 DemonstrationWrapper 返回 -1 的情形对应）。"""


def to_np(x):
    if isinstance(x, torch.Tensor):
        x = x.detach().cpu().numpy()
    return np.asarray(x, dtype=np.float64).reshape(-1)


def yaw_quat(yaw):
    """与 _load_scene 相同的算法：euler XYZ (0,0,yaw) → wxyz。"""
    m = euler_angles_to_matrix(torch.tensor([[0.0, 0.0, float(yaw)]], dtype=torch.float32), convention="XYZ")
    return matrix_to_quaternion(m)[0].detach().cpu().numpy().tolist()


def build(seed, obs_mode):
    env = gym.make("MoveCube", obs_mode=obs_mode, control_mode="pd_joint_pos", render_mode="rgb_array",
                   reward_mode="dense", seed=seed, difficulty="xhard")
    env.reset()
    base = env.unwrapped
    assert getattr(base, "_xhard_peg_yaw_reduction", False), "xhard 翻转归约开关未打开"
    planner = FailAwarePandaArmMotionPlanningSolver(
        env, debug=False, vis=False, base_pose=base.agent.robot.pose,
        visualize_target_grasp_pose=False, print_env_info=False)
    stats = {"rrt_used": 0}
    orig_screw = planner.move_to_pose_with_screw
    orig_rrt = planner.move_to_pose_with_RRTStar

    def screw_then_rrt(*a, **k):
        # 复刻 DemonstrationWrapper：screw 1 次，失败再 RRT* 最多 3 次；全失败返回 -1（这里改为抛异常方便记录）
        try:
            r = orig_screw(*a, **k)
            if not (isinstance(r, int) and r == -1):
                return r
        except ScrewPlanFailure:
            pass
        stats["rrt_used"] += 1
        for _ in range(3):
            try:
                r = orig_rrt(*a, **k)
            except Exception:
                continue
            if isinstance(r, int) and r == -1:
                continue
            return r
        raise PlanExhausted("screw→RRT* 全部失败")

    planner.move_to_pose_with_screw = screw_then_rrt
    return env, planner, stats


def park_distractors(base):
    for name in ("cube", "cube_2"):
        obj = getattr(base, name, None)
        if obj is not None:
            obj.set_pose(sapien.Pose(p=FAR))
    for i, name in enumerate(("goal_site", "goal_site_2")):
        obj = getattr(base, name, None)
        if obj is not None:
            obj.set_pose(sapien.Pose(p=[10.0, 10.0 + 2 * (i + 1), 1.0]))


def place_peg(base, x, y, z, yaw):
    base.peg.set_pose(sapien.Pose(p=[float(x), float(y), float(z)], q=yaw_quat(yaw)))
    try:
        base.peg.set_root_linear_velocity(torch.zeros(3))
        base.peg.set_root_angular_velocity(torch.zeros(3))
    except Exception:
        pass
    if base.peg.dof > 0:
        zero = np.zeros(base.peg.dof)
        base.peg.set_qpos(zero)
        base.peg.set_qvel(zero)


def peg_geometry(base):
    """杆各子 link 的世界 pose → 沿杆朝向 u 相对根的端点参数 t（可视外形并集）。"""
    root = to_np(base.peg.pose.p)
    q = to_np(base.peg.pose.q)
    w, qx, qy, qz = q
    u = np.array([1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy + w * qz), 2 * (qx * qz - w * qy)])
    out = {"root": root.tolist(), "u": u.tolist(), "links": {}}
    lo, hi = np.inf, -np.inf
    for link in (base.peg_head, base.peg_tail):
        lp = to_np(link.pose.p)
        t_center = float((lp - root) @ u)
        comp = link._objs[0]
        halves = []
        for c in comp.get_entity().get_components():
            for rs in getattr(c, "render_shapes", []) or []:
                if hasattr(rs, "half_size"):
                    halves.append((float(rs.half_size[0]), float(rs.local_pose.p[0])))
        for sh in comp.get_collision_shapes():
            halves.append((float(sh.half_size[0]), float(sh.local_pose.p[0])))
        seg = [min(t_center + lx - h for h, lx in halves), max(t_center + lx + h for h, lx in halves)]
        lo, hi = min(lo, seg[0]), max(hi, seg[1])
        out["links"][link.name] = {"world_p": lp.tolist(), "t_center": t_center, "t_extent": seg}
    out["t_extent_union"] = [lo, hi]
    out["world_endpoints"] = [(root + lo * u).tolist(), (root + hi * u).tolist()]
    return out


def run_trial(env, planner, stats, x, y, z, yaw):
    base = env.unwrapped
    base.reset_in_proecess = False
    base.agent.reset(INIT_QPOS)
    park_distractors(base)
    place_peg(base, x, y, z, yaw)
    base._peg_grasp_flipped = False
    base._peg_grasp_flip_log = []
    planner.gripper_state = planner.OPEN
    rrt0 = stats["rrt_used"]
    err, msg = "", ""
    t0 = time.time()
    try:
        spf.grasp_and_lift_peg_side(env, planner, base.grasp_target)
    except PlanExhausted as e:
        err, msg = "PlanExhausted", str(e)
    except ScrewPlanFailure as e:
        err, msg = "ScrewPlanFailure", str(e)
    except Exception as e:  # noqa: BLE001
        err, msg = type(e).__name__, str(e).splitlines()[0][:120] if str(e) else ""
    dt = time.time() - t0
    tgt = base.grasp_target
    tz = float(to_np(tgt.pose.p)[2])
    try:
        grasping = bool(to_np(base.agent.is_grasping(tgt))[0])
    except Exception:
        grasping = False
    ok = (err == "") and tz > 0.1 and grasping
    if err == "" and not ok:
        err = "NotLifted" if tz <= 0.1 else "NotGrasping"
    flipped = bool(getattr(base, "_peg_grasp_flipped", False))
    return dict(ok=int(ok), err=err, msg=msg, flipped=int(flipped), tgt_z=round(tz, 4), grasping=int(grasping),
                rrt=stats["rrt_used"] - rrt0, sec=round(dt, 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True, help="json 列表 [[x,y,yaw_deg],...] 的文件")
    ap.add_argument("--worker", type=int, default=0)
    ap.add_argument("--nworkers", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--obs-mode", default="state")
    ap.add_argument("--geom-out", default="")
    a = ap.parse_args()
    tasks = json.load(open(a.tasks))[a.worker::a.nworkers]
    t0 = time.time()
    env, planner, stats = build(a.seed, a.obs_mode)
    base = env.unwrapped
    z0 = float(to_np(base.peg.pose.p)[2])
    print(f"[w{a.worker}] 环境就绪 {time.time()-t0:.1f}s，原生成杆根 z={z0:.4f}，grasp_target={base.grasp_target.name}，任务 {len(tasks)}", flush=True)
    if a.geom_out:
        geoms = []
        for (x, y, yd) in [(0.0, 0.2, 0.0), (0.1, -0.2, 90.0), (-0.05, 0.1, 210.0)]:
            base.agent.reset(INIT_QPOS)
            place_peg(base, x, y, z0, math.radians(yd))
            g = peg_geometry(base)
            g["set"] = [x, y, yd]
            geoms.append(g)
        json.dump({"z0": z0, "samples": geoms}, open(a.geom_out, "w"), ensure_ascii=False, indent=1)
        print(f"[w{a.worker}] 几何已写 {a.geom_out}", flush=True)
    fields = ["x", "y", "yaw_deg", "ok", "err", "flipped", "tgt_z", "grasping", "rrt", "sec", "msg"]
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, (x, y, yd) in enumerate(tasks):
            r = run_trial(env, planner, stats, x, y, z0, math.radians(yd))
            w.writerow(dict(x=x, y=y, yaw_deg=yd, **r))
            f.flush()
            if (i + 1) % 20 == 0 or i + 1 == len(tasks):
                print(f"[w{a.worker}] 进度 {i+1}/{len(tasks)} 用时 {time.time()-t0:.0f}s", flush=True)
    print(f"[w{a.worker}] DONE {time.time()-t0:.0f}s", flush=True)
    env.close()


if __name__ == "__main__":
    main()
