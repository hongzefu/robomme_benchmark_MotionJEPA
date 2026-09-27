#!/usr/bin/env python3
"""V6 MoveCube xhard 统一区域 U：真实模拟器 reset 复核（每个 seed 一次 gym.make + reset，state obs）。

用法：python reset_check.py --start 6100000 --n 250 --gpu 0 --out part_0.jsonl
每局记录两段的杆根/yaw/抓取点、goal、方块（从 _spec 与实际 actor 位姿各取一份）与失败信息。
"""
import argparse, json, os, sys, time, traceback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--gpu", default="0")
    ap.add_argument("--out", required=True)
    ap.add_argument("--difficulty", default="xhard")
    a = ap.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = a.gpu
    import gymnasium as gym
    import numpy as np
    import robomme.robomme_env  # noqa: F401
    with open(a.out, "w") as f:
        for seed in range(a.start, a.start + a.n):
            t0 = time.time()
            row = {"seed": seed}
            env = None
            try:
                env = gym.make("MoveCube", obs_mode="state", control_mode="pd_joint_pos", render_mode=None,
                               reward_mode="dense", seed=seed, difficulty=a.difficulty)
                env.reset()
                u = env.unwrapped
                row["layout"] = u._spec.to_dict()["layout"]
                row["actual"] = {
                    "peg_p": u.peg.pose.p[0, :2].tolist(), "peg_q": u.peg.pose.q[0].tolist(),
                    "peg_tail": u.peg_tail.pose.p[0, :2].tolist(),
                    "cube": u.cube_init_pose.p[0, :2].tolist(), "cube_2": u.cube_init_pose_2.p[0, :2].tolist(),
                    "goal": np.asarray(u.goal_site_1_pose_p).reshape(-1)[:2].tolist(),
                    "goal_2": np.asarray(u.goal_site_2_pose_p).reshape(-1)[:2].tolist(),
                    "peg2_p": list(u.peg_init_poses_2[0].p[:2]),
                    "way": u.way,
                }
                row["ok"] = True
            except Exception as exc:  # noqa: BLE001
                row["ok"] = False
                row["error_type"] = type(exc).__name__
                row["error"] = str(exc)[:300]
                row["tb"] = traceback.format_exc()[-800:]
            finally:
                if env is not None:
                    env.close()
            row["wall"] = round(time.time() - t0, 2)
            f.write(json.dumps(row, default=float) + "\n")
            f.flush()


if __name__ == "__main__":
    main()
