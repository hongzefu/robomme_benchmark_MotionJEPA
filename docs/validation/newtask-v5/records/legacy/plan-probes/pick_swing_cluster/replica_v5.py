"""给 replica.pick_layout 加 V5 候选开关（只在本 scratch 进程内生效）：
- target_slot0：第一个放的有色方块（颜色由 randperm 决定、对颜色均匀）固定为目标，只它加 corner_bias，
  另两块 corner_bias=0；原 target_cube_idx 的 randint 照抽（占位，不改取值点结构）。
- distinct_quadrant：三块有色方块的候选点若落在已被前面有色方块占用的象限（相对区域中心）则拒绝。
两者都不新增抽样点，只改映射/拒绝条件。
"""
import math, torch
import numpy as np
import replica as R

_orig = R.pick_layout


def pick_layout(seed, corner_bias=0.5, obb_mode="trimesh", distractor_corner_bias=0.0,
                colored_min_gap=R.HS, distractor_min_gap=R.HS, min_center_dist=None,
                target_slot0=False, distinct_quadrant=False, **_):
    g = torch.Generator(); g.manual_seed(seed)
    bxy, bobb = R.build_button(g)
    order = torch.randperm(3, generator=g).tolist()
    torch.randint(0, 3, (1,), generator=g).item()
    obbs = [bobb]
    d = R.spawn_disk(g, obbs, [], (-0.1, 0), 0.2, radius=2 * R.HS, min_gap=2 * R.HS)
    if d is None:
        return {"fail": "disk"}
    gx, gy, _ = d
    obbs.append(R.disk_obb((gx, gy), 2 * R.HS + 2 * R.HS - R.HS))
    names = ["red", "blue", "green"]
    colored, placed, quads = [], [], set()

    def rej_factory(check_quad):
        def rej(x, y):
            if min_center_dist is not None and any(math.hypot(x - px, y - py) < min_center_dist for (px, py) in placed):
                return True
            if check_quad and (int(x >= -0.1), int(y >= 0.0)) in quads:
                return True
            return False
        return rej

    for k, ci in enumerate(order):
        cb = corner_bias if (not target_slot0 or k == 0) else 0.0
        r = R.spawn_cube(g, obbs, [], (-0.1, 0), 0.2, corner_bias=cb, min_gap=colored_min_gap,
                         obb_mode=obb_mode, extra_reject=rej_factory(distinct_quadrant))
        if r is None:
            return {"fail": f"cube{k}"}
        x, y, yaw, _ = r
        colored.append((names[ci], x, y, yaw)); placed.append((x, y)); quads.add((int(x >= -0.1), int(y >= 0.0)))
        obbs.append(R.cube_obb2d(x, y, yaw, obb_mode))
    tidx = torch.randint(0, 3, (1,), generator=g).item()
    if target_slot0:
        tidx = 0
    dis = []
    for name in ["yellow", "cyan", "magenta"]:
        r = R.spawn_cube(g, obbs, [], (-0.1, 0), 0.2, corner_bias=distractor_corner_bias,
                         min_gap=distractor_min_gap, obb_mode=obb_mode, extra_reject=rej_factory(False))
        if r is None:
            return {"fail": f"distractor_{name}"}
        x, y, yaw, _ = r
        dis.append((name, x, y, yaw)); placed.append((x, y))
        obbs.append(R.cube_obb2d(x, y, yaw, obb_mode))
    return {"button": bxy, "goal": (gx, gy), "colored": colored, "target_idx": tidx,
            "distractors": dis, "order": order}


R.pick_layout = pick_layout
