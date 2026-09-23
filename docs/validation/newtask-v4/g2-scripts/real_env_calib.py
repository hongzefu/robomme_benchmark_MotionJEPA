# 真实环境校准（只读，只 reset 不跑演示）：统计 hard 下实际放下的容器数，并读真实 actor 的 2D OBB
import sys, json, numpy as np
import gymnasium as gym
import robomme.robomme_env  # noqa: F401
from mani_skill.examples.motionplanning.base_motionplanner.utils import get_actor_obb
from robomme.robomme_env.utils.object_generation import _trimesh_box_to_obb2d

KW = dict(obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos", render_mode="rgb_array", reward_mode="dense")
out = {}
for task in ["VideoUnmask", "ButtonUnmask"]:
    counts, mind = [], []
    for seed in range(int(sys.argv[1]) if len(sys.argv) > 1 else 8):
        env = gym.make(task, seed=seed, difficulty="hard", **KW)
        env.reset(seed=seed)
        u = env.unwrapped
        bins = u.spawned_bins
        xy = np.array([np.asarray(b.pose.p.cpu())[0, :2] for b in bins])
        d = np.linalg.norm(xy[:, None] - xy[None], axis=-1) + np.eye(len(xy)) * 9
        counts.append(len(bins)); mind.append(float(d.min()))
        if seed == 0:
            c, A, h = _trimesh_box_to_obb2d(get_actor_obb(bins[0], to_world_frame=True, vis=False))
            out[f"{task}_bin0_obb"] = dict(h=h.tolist(), colnorm=np.linalg.norm(A, axis=0).tolist())
        env.close()
    out[task] = dict(counts=counts, min_center_dist=mind)
    print(task, counts, [round(x, 4) for x in mind], flush=True)

# VideoRepick hard：真实方块 actor 的 2D OBB 退化比例
degen = tot = 0
for seed in range(4):
    env = gym.make("VideoRepick", seed=seed, difficulty="hard", **KW)
    env.reset(seed=seed)
    for cube in env.unwrapped.spawned_cubes:
        c, A, h = _trimesh_box_to_obb2d(get_actor_obb(cube, to_world_frame=True, vis=False))
        tot += 1; degen += int(np.linalg.norm(A, axis=0).min() < 0.5)
    env.close()
out["VideoRepick_cube_obb_degenerate"] = [degen, tot]
print("VideoRepick 方块 OBB 退化", degen, "/", tot)
print(json.dumps(out, ensure_ascii=False))
