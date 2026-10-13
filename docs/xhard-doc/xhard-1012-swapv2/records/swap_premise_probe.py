"""只读探针：对阶段零的 30 个母 seed 逐个 reset，核对交换对象是否同形且等高。

同形：各对象的盒体序列逐盒 half / local_p / local_q 完全相等（np.array_equal）。
等高：各对象初始世界位姿 z 完全相等。
只替换 xhard 规划器为记录器，不改仓库文件。
"""
import json
import sys

import gymnasium as gym
import numpy as np
import robomme.robomme_env  # noqa: F401
import robomme_xhard
from robomme_xhard.collision import bin_collision as bc
import robomme_xhard.envs.video_unmask_swap as vus
import robomme_xhard.envs.button_unmask_swap as bus
import robomme_xhard.envs.video_repick as vr

CAPTURE = {}


def hook(cls, attr):
    """在 xhard 子类 _load_scene 末尾读交换对象（与 v1 规划器调用时点相同）。"""
    orig = cls._load_scene

    def wrapped(self, options):
        orig(self, options)
        CAPTURE["states"] = [bc.object_state_from_actor(a, f"o{i}") for i, a in enumerate(getattr(self, attr))]
    cls._load_scene = wrapped


hook(vus.VideoUnmaskSwapXHard, "spawned_bins")
hook(bus.ButtonUnmaskSwapXHard, "spawned_bins")
hook(vr.VideoRepickXHard, "spawned_cubes")

rows_in = json.load(open(sys.argv[1]))["rows"]
out = []
for item in rows_in:
    task, seed = item["task"], item["seed"]
    env = gym.make(robomme_xhard.env_name(task), seed=seed, difficulty="xhard20",
                   obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                   render_mode="rgb_array", reward_mode="dense")
    try:
        env.reset(seed=seed)
        states = CAPTURE.pop("states")
        ref = states[0].shapes
        same_shape, max_dev = True, 0.0
        for s in states[1:]:
            if len(s.shapes) != len(ref):
                same_shape = False
                continue
            for a, b in zip(ref, s.shapes):
                for f in ("half", "local_p", "local_q"):
                    x, y = np.asarray(getattr(a, f)), np.asarray(getattr(b, f))
                    if not np.array_equal(x, y):
                        same_shape = False
                        max_dev = max(max_dev, float(np.max(np.abs(x - y))))
        zs = [float(s.p[2]) for s in states]
        attr = "spawned_cubes" if task == "VideoRepick" else "spawned_bins"
        zs_after = [float(bc.object_state_from_actor(a).p[2]) for a in getattr(env.unwrapped, attr)]
        same_h = len(set(zs)) == 1
        row = {"task": task, "seed": seed, "n_obj": len(states), "n_boxes": len(ref),
               "same_shape": same_shape, "max_shape_dev": max_dev,
               "same_height": same_h, "z": zs, "z_after_reset": zs_after, "same_height_after_reset": len(set(zs_after)) == 1,
               "halves_obj0": [np.asarray(sp.half).tolist() for sp in ref]}
        out.append(row)
        print("PREMISE", task, seed, "objs", len(states), "boxes", len(ref),
              "same_shape", same_shape, "dev", max_dev, "same_height", same_h, "after_reset", len(set(zs_after)) == 1, flush=True)
    finally:
        env.close()

json.dump(out, open(sys.argv[2], "w"), indent=1)
ns = sum(not r["same_shape"] for r in out)
nh = sum(not r["same_height"] for r in out)
print(f"SWAP_PREMISE=INFO seeds={len(out)} not_same_shape={ns} not_same_height={nh}", flush=True)
