#!/usr/bin/env python3
"""原三档逐位对比：对 easy/medium/hard 各 1 个 seed 做真实 reset，导出规格与物体位姿（float.hex）。"""
import json, os, sys
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")
import gymnasium as gym
import numpy as np
import torch
import robomme
import robomme.robomme_env  # noqa: F401

out = {"robomme_file": robomme.__file__}
for tier, seed in (("easy", 3000), ("medium", 3001), ("hard", 3002)):
    env = gym.make("MoveCube", obs_mode="state", control_mode="pd_joint_pos", render_mode=None,
                   reward_mode="dense", seed=seed, difficulty=tier)
    env.reset()
    u = env.unwrapped
    rec = {"spec": u._spec.to_dict()}
    for name in ("peg", "peg_head", "peg_tail", "goal_site", "cube"):
        a = getattr(u, name)
        rec[name] = [float(v).hex() for v in torch.cat([a.pose.p.reshape(-1), a.pose.q.reshape(-1)]).tolist()]
    for name in ("cube_init_pose", "cube_init_pose_2"):
        a = getattr(u, name)
        rec[name] = [float(v).hex() for v in torch.cat([a.p.reshape(-1), a.q.reshape(-1)]).tolist()]
    rec["goal_site_2_pose_p"] = [float(v).hex() for v in np.asarray(u.goal_site_2_pose_p).reshape(-1)]
    rec["peg_init_poses_2"] = [float(v).hex() for v in list(u.peg_init_poses_2[0].p) + list(u.peg_init_poses_2[0].q)]
    rec["way"] = u.way
    rec["sentinel"] = float(torch.rand(1, generator=u._hb_generator).item()).hex()
    out[tier] = rec
    env.close()
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True, default=str)
print("DUMPED", out["robomme_file"])
