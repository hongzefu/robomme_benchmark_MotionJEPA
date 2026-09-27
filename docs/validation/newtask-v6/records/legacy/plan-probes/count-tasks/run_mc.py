"""V6 规划探针：四个计数类环境「方块总数 N → reset 成功率」曲线（每点 1024 局）。

用法：uv run --no-sync python run_mc.py <env> [--region ...]
每行输出：env 变体 N 成功率 平均最近邻距 等。结果同时写 mc_<env>.json。
"""
import json, sys, time
import numpy as np
from mc_lib import button, board_strips, cube_obb, place_cube, place_disk, HS

EPISODES = 1024


def binfill(rng, N, region_half=(0.2, 0.25), region_center=(-0.1, 0.0), gap=0.02, trials=256):
    obs = [button(rng)]
    bx = 0.15 + (rng.random() * 0.2 - 0.2)
    by = 0.0 + (rng.random() * 0.4 - 0.2)
    rng.random()  # 板 yaw（不进障碍）
    obs += board_strips(bx, by)
    cs = []
    for k in range(N):
        r = place_cube(rng, obs, region_center, region_half, gap, trials)
        if r is None:
            return False, cs, ("cube", k)
        obs.append(cube_obb(r[0], r[1], r[2]))
        cs.append((r[0], r[1]))
    return True, cs, None


def pickx(rng, N, region_half=0.25, dist=0.08, trials=1024, disk_half=0.2):
    b = button(rng)
    obs = [b]
    d = place_disk(rng, [b], [], (-0.1, 0.0), disk_half, 0.04, 0.04)
    if d is None:
        return False, [], ("disk", 0)
    obs.append((np.asarray(d), np.eye(2), np.array([0.06, 0.06])))
    cs = []
    for k in range(N):  # 前 3 块有色、其余干扰，规则相同（区域、间距、预算、中心距）
        r = place_cube(rng, obs, (-0.1, 0.0), region_half, 0.02, trials, centers=cs, min_center_dist=dist)
        if r is None:
            return False, cs, ("cube", k)
        obs.append(cube_obb(r[0], r[1], r[2]))
        cs.append((r[0], r[1]))
    return True, cs, None


def swingx(rng, N, region_half=0.25, dist=0.08, trials=256, n_colored=3):
    b = button(rng)
    obs = [b]
    cs = []
    for k in range(min(n_colored, N)):
        r = place_cube(rng, obs, (-0.1, 0.0), region_half, 0.02, trials, centers=cs, min_center_dist=dist)
        if r is None:
            return False, cs, ("colored", k)
        obs.append(cube_obb(r[0], r[1], r[2]))
        cs.append((r[0], r[1]))
    d0 = place_disk(rng, obs, [], (-0.1, -0.2), 0.1, 0.04, 0.02)
    if d0 is None:
        return False, cs, ("disk", 0)
    d1 = place_disk(rng, obs, [(np.asarray(d0), 0.04)], (-0.1, 0.2), 0.1, 0.04, 0.02)
    if d1 is None:
        return False, cs, ("disk", 1)
    clearance = HS * (2 + 1) - HS
    obs2 = obs + [(np.asarray(d0), np.eye(2), np.array([clearance] * 2)),
                  (np.asarray(d1), np.eye(2), np.array([clearance] * 2))]
    for k in range(N - n_colored):
        r = place_cube(rng, obs2, (-0.1, 0.0), region_half, 0.02, trials, centers=cs, min_center_dist=dist)
        if r is None:
            return False, cs, ("distractor", k)
        obs2.append(cube_obb(r[0], r[1], r[2]))
        cs.append((r[0], r[1]))
    return True, cs, None


def pickhl(rng, N, region_half=0.2, gap=0.04, trials=256):
    obs = [button(rng)]
    cs = []
    for k in range(N):
        r = place_cube(rng, obs, (-0.1, 0.0), region_half, gap, trials)
        if r is None:
            return False, cs, ("cube", k)
        obs.append(cube_obb(r[0], r[1], r[2]))
        cs.append((r[0], r[1]))
    return True, cs, None


FN = {"BinFill": binfill, "PickXtimes": pickx, "SwingXtimes": swingx, "PickHighlight": pickhl}


def sweep(env, Ns, variant="现值", seed=0, **kw):
    fn = FN[env]
    rows = []
    for N in Ns:
        rng = np.random.default_rng(1_000_003 * seed + 7919 * N + 17)
        ok = 0
        fails = {}
        nn = []
        t0 = time.time()
        for e in range(EPISODES):
            s, cs, why = fn(rng, N, **kw)
            if s:
                ok += 1
                P = np.array(cs)
                D = np.linalg.norm(P[:, None] - P[None], axis=-1) + np.eye(len(P)) * 9
                nn.append(D.min())
            else:
                fails[why[0]] = fails.get(why[0], 0) + 1
        rate = ok / EPISODES
        # Wilson 95% 下界
        z = 1.96; n = EPISODES; p = rate
        lo = (p + z * z / (2 * n) - z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)
        row = dict(env=env, variant=variant, N=N, success=rate, wilson_lo=lo, fails=fails,
                   min_pair_median=float(np.median(nn)) if nn else None, kw={k: v for k, v in kw.items()},
                   sec=round(time.time() - t0, 1))
        print(f"{env:13s} {variant:24s} N={N:2d} 成功 {rate*100:6.2f}% (95%下界 {lo*100:5.1f}%) 失败处 {fails} 最近对中位 {row['min_pair_median']}", flush=True)
        rows.append(row)
    return rows


if __name__ == "__main__":
    env = sys.argv[1]
    allrows = []
    if env == "BinFill":
        allrows += sweep(env, [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 24, 26, 28], "现值框 0.4x0.5")
        allrows += sweep(env, [16, 18, 20, 22, 24, 26, 28, 30], "框 y 半宽 0.30", region_half=(0.2, 0.30))
        allrows += sweep(env, [16, 18, 20, 22, 24, 26, 28, 30], "框 x 0.45 y 0.30", region_half=(0.225, 0.30), region_center=(-0.1, 0.0))
    elif env == "PickXtimes":
        allrows += sweep(env, [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16], "现值 0.25 d=0.08")
        allrows += sweep(env, [10, 12, 14, 16, 18], "半宽 0.30 d=0.08", region_half=0.30)
        allrows += sweep(env, [8, 10, 12, 14], "0.25 d=0.07", dist=0.07)
    elif env == "SwingXtimes":
        allrows += sweep(env, [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16], "现值 0.25 d=0.08")
        allrows += sweep(env, [8, 10, 12, 14], "现值 0.25 d=0.08 预算1024", trials=1024)
        allrows += sweep(env, [10, 12, 14, 16, 18], "半宽 0.30 d=0.08", region_half=0.30)
    elif env == "PickHighlight":
        allrows += sweep(env, [6, 8, 9, 10, 11, 12, 13, 14], "现值 0.2 gap=0.04")
        allrows += sweep(env, [10, 11, 12, 13, 14, 15, 16], "现值 0.2 gap=0.04 预算1024", trials=1024)
        allrows += sweep(env, [10, 12, 14, 16, 18, 20], "半宽 0.25 gap=0.04", region_half=0.25)
        allrows += sweep(env, [10, 12, 14, 16, 18], "半宽 0.25 gap=0.04 预算1024", region_half=0.25, trials=1024)
    json.dump(allrows, open(f"mc_{env}.json", "w"), ensure_ascii=False, indent=1)
