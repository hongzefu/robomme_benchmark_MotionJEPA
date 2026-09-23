# 用源码里真实的 spawn_random_bin 函数体（只把 build_bin 与 get_actor_obb 换成 trimesh 桩），核对 g2_mc 的等价性
import sys, numpy as np, torch
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import robomme.robomme_env.utils.object_generation as og
from obb_check import bin_mesh


class Fake:
    def __init__(s, mesh):
        s.mesh = mesh


def fake_build_bin(self, callsign=None, position=None, z_rotation_deg=0.0):
    return Fake(bin_mesh(position[0], position[1], z_rotation_deg))


def fake_obb(actor, to_world_frame=True, vis=False):
    return actor.mesh.bounding_box_oriented


og.build_bin = fake_build_bin
og.get_actor_obb = fake_obb


class Env:
    cube_half_size = 0.02


def count_bins(seed, n, button, region=0.2, gap=0.04):
    env = Env(); g = torch.Generator(); g.manual_seed(seed); avoid = []
    if button:
        off = torch.rand(2, generator=g) - 0.5
        avoid.append(og.create_button_obb(center_xy=(-0.2 + float(off[0]) * 0.1, float(off[1]) * 0.1),
                                          half_size=0.025 * 1.5 * 1.5))
    k = 0
    for i in range(n):
        try:
            b = og.spawn_random_bin(env, avoid=avoid, region_center=[0, 0], region_half_size=region,
                                    min_gap=gap, max_trials=256, generator=g)
        except RuntimeError:
            break
        avoid.append(b); k += 1
    return k


if __name__ == "__main__":
    for button in [False, True]:
        c = [count_bins(s, 15, button) for s in range(60)]
        print("button" if button else "video", "N=15 放下 均值/最小/最大", np.mean(c), min(c), max(c))
