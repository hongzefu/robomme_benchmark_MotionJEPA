"""replica_v5 的扩展版：可调区域半边长、max_trials、有色方块两两最小中心距（分散判据）。
默认参数下与 replica.pick_layout（即 V4 实际过程）逐位一致（见 __main__ 自检）。"""
import math, torch, sys
import numpy as np
import replica as R


def pick_layout_ext(seed, corner_bias=0.5, obb_mode="trimesh", min_center_dist=None, target_slot0=False,
                    distinct_quadrant=False, cube_half=0.2, disk_half=0.2, max_trials=256,
                    colored_min_dist=None, distractor_corner_bias=0.0):
    g = torch.Generator(); g.manual_seed(seed)
    bxy, bobb = R.build_button(g)
    order = torch.randperm(3, generator=g).tolist()
    torch.randint(0, 3, (1,), generator=g).item()
    obbs = [bobb]
    d = R.spawn_disk(g, obbs, [], (-0.1, 0), disk_half, radius=2 * R.HS, min_gap=2 * R.HS, max_trials=max_trials)
    if d is None:
        return {"fail": "disk"}
    gx, gy, _ = d
    obbs.append(R.disk_obb((gx, gy), 2 * R.HS + 2 * R.HS - R.HS))
    names = ["red", "blue", "green"]
    colored, placed, cplaced, quads = [], [], [], set()

    def rej(is_colored):
        def f(x, y):
            if min_center_dist is not None and any(math.hypot(x - px, y - py) < min_center_dist for (px, py) in placed):
                return True
            if is_colored and colored_min_dist is not None and any(math.hypot(x - px, y - py) < colored_min_dist for (px, py) in cplaced):
                return True
            if is_colored and distinct_quadrant and (int(x >= -0.1), int(y >= 0.0)) in quads:
                return True
            return False
        return f

    for k, ci in enumerate(order):
        cb = corner_bias if (not target_slot0 or k == 0) else 0.0
        r = R.spawn_cube(g, obbs, [], (-0.1, 0), cube_half, corner_bias=cb, obb_mode=obb_mode,
                         extra_reject=rej(True), max_trials=max_trials)
        if r is None:
            return {"fail": f"cube{k}"}
        x, y, yaw, _ = r
        colored.append((names[ci], x, y, yaw)); placed.append((x, y)); cplaced.append((x, y))
        quads.add((int(x >= -0.1), int(y >= 0.0)))
        obbs.append(R.cube_obb2d(x, y, yaw, obb_mode))
    tidx = torch.randint(0, 3, (1,), generator=g).item()
    if target_slot0:
        tidx = 0
    dis = []
    for name in ["yellow", "cyan", "magenta"]:
        r = R.spawn_cube(g, obbs, [], (-0.1, 0), cube_half, corner_bias=distractor_corner_bias, obb_mode=obb_mode,
                         extra_reject=rej(False), max_trials=max_trials)
        if r is None:
            return {"fail": f"distractor_{name}"}
        x, y, yaw, _ = r
        dis.append((name, x, y, yaw)); placed.append((x, y))
        obbs.append(R.cube_obb2d(x, y, yaw, obb_mode))
    return {"button": bxy, "goal": (gx, gy), "colored": colored, "target_idx": tidx, "distractors": dis, "order": order}


if __name__ == "__main__":
    ok = 0
    for s in range(50):
        a = R.pick_layout(3_000_000 + s); b = pick_layout_ext(3_000_000 + s)
        ok += a["colored"] == b["colored"] and a["distractors"] == b["distractors"]
    print("ext default == replica:", ok, "/50")
