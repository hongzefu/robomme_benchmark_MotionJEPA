"""V6 规划探针（VideoPlaceButton / VideoPlaceOrder）：xhard 布局 reset 成功率的离线蒙特卡洛。

复刻 _load_scene 前半段的抽样顺序（goal_site → 按钮 → 颜色 randperm(3) → 方块 × n → 目标台 × T），
直接调真实的 spawn_random_cube / spawn_random_target（actor builder 换替身，按钮替身与真 build_button 同样抽随机数，
方块以 cube_obb2d_exact 精确三元组进 avoid，同 V5 xhard）。
变量：方块数 n、目标台数 T、goal_site 是否进 avoid（xhard 下 goal_site 不被任何任务使用、初始化时沉到桌下）、
区域半宽 half（方块与目标台共用）。
用法：vp_layout_mc.py <env> <n_seeds> [seed0]   输出 json 与表格。
"""
import sys, os, json, math, itertools, logging, time
from types import SimpleNamespace
import torch
sys.path.insert(0, "src")
logging.disable(logging.CRITICAL)
from robomme.robomme_env.utils import object_generation as og
from robomme.robomme_env.utils.xhard import cube_obb2d_exact

CUBE_HALF = 0.02


class _A:
    def __init__(self, name, initial_pose):
        self.name = name; self.initial_pose = initial_pose; self.pose = initial_pose


def _fake_cube(scene, half_size, color, name, initial_pose):
    return _A(name, initial_pose)


def _fake_target(scene, radius, thickness, name, body_type, add_collision, initial_pose):
    return _A(name, initial_pose)


og.actors.build_cube = _fake_cube
for nm in ("build_purple_white_target", "build_gray_white_target", "build_green_white_target", "build_red_white_target"):
    setattr(og, nm, _fake_target)


def fake_button(g, center_xy=(0.1, 0.0), scale=1.5, randomize_range=(0.05, 0.3), base_half=(0.025, 0.025, 0.005)):
    bh = [b * scale for b in base_half]
    off = torch.rand(2, generator=g) - 0.5
    cx = center_xy[0] + float(off[0]) * randomize_range[0]
    cy = center_xy[1] + float(off[1]) * randomize_range[1]
    return og.create_button_obb(center_xy=(cx, cy), half_size=max(bh[0], bh[1]) * 1.5)


GOAL_RADIUS_FACTOR = {"VideoPlaceButton": 3, "VideoPlaceOrder": 5}


def layout(env, seed, n_cubes=3, n_targets=4, goal_avoid=True, half=0.2, target_gap_factor=1.0):
    g = torch.Generator(); g.manual_seed(seed)
    fake = SimpleNamespace(scene=None, cube_half_size=CUBE_HALF, device="cpu")
    try:
        goal = og.spawn_random_target(fake, avoid=None, include_existing=False, include_goal=False,
                                      region_center=[-0.1, 0], region_half_size=0.1,
                                      radius=CUBE_HALF * GOAL_RADIUS_FACTOR[env], thickness=0.005,
                                      min_gap=CUBE_HALF, name_prefix="goal_site", generator=g)
    except RuntimeError:
        return "goal"
    avoid = [goal] if goal_avoid else []
    avoid.append(fake_button(g))
    torch.randperm(3, generator=g)
    for i in range(n_cubes):
        try:
            c = og.spawn_random_cube(fake, color=(1, 0, 0, 1), avoid=avoid, include_existing=False, include_goal=False,
                                     region_center=[0, 0], region_half_size=half, half_size=CUBE_HALF, min_gap=CUBE_HALF,
                                     random_yaw=True, name_prefix=f"cube_{i}", generator=g)
        except RuntimeError:
            return f"cube{i+1}"
        avoid.append(cube_obb2d_exact(c.initial_pose, CUBE_HALF))
    for i in range(n_targets):
        try:
            t = og.spawn_random_target(fake, avoid=avoid, include_existing=False, include_goal=False,
                                       region_center=[0, 0], region_half_size=half, radius=CUBE_HALF * 2,
                                       thickness=0.005, min_gap=CUBE_HALF * target_gap_factor,
                                       name_prefix=f"target_{i}", generator=g)
        except RuntimeError:
            return f"target{i+1}"
        avoid.append(t)
    return "ok"


if __name__ == "__main__":
    env = sys.argv[1]; N = int(sys.argv[2]); s0 = int(sys.argv[3]) if len(sys.argv) > 3 else 5000000
    grid = []
    for goal_avoid in (True, False):
        for half in (0.2, 0.25):
            for n in (3, 4, 5, 6):
                for T in (4, 5, 6, 7, 8):
                    grid.append((goal_avoid, half, n, T))
    out = []
    t0 = time.time()
    for goal_avoid, half, n, T in grid:
        fails = {}
        ok = 0
        for k in range(N):
            r = layout(env, s0 + k, n, T, goal_avoid, half)
            if r == "ok": ok += 1
            else: fails[r] = fails.get(r, 0) + 1
        rec = dict(env=env, goal_avoid=goal_avoid, half=half, cubes=n, targets=T, n=N, ok_rate=ok / N, fails=fails)
        out.append(rec)
        print(f"{env} goal_avoid={goal_avoid!s:5} half={half} cubes={n} targets={T}: ok={ok/N:.3f} fails={fails}", flush=True)
    print(f"wall {time.time()-t0:.0f}s")
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"vp_layout_mc_{env}.json"), "w"), indent=1)
