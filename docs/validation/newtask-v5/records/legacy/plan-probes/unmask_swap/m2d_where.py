"""M2d：各环带里干扰容器中心落在哪（机器人侧 -x 边 / ±y 两侧 / 远端 +x 边）与可放容量（放置成功率）。"""
import sys, collections, numpy as np
SP = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap"
sys.path.insert(0, SP)
from replica import vus_layout, bus_layout, inner_sequence
from ring_sampler import V4_RING, V4PAD_RING, sample_ring, state, RADIUS
from robomme.robomme_env.utils import unmask_swap_xhard as ux
BTN = float(np.linalg.norm([0.05625, 0.05625]))
for task, fn, base in (("VUS", vus_layout, 9_100_000), ("BUS", bus_layout, 9_300_000)):
    for rname, ring, vr in (("v4", V4_RING, None), ("v4pad", V4PAD_RING, RADIUS + 0.07)):
        for count in (3, 6, 10):
            side = collections.Counter(); pf = 0; n = 0; xs = []
            for i in range(150):
                lay = fn(base + i)
                if lay.get("spawn_fail"): continue
                seq = inner_sequence(lay)
                sweeps = [(state(f"bin_{a}", *pos[a], yaw[a]), state(f"bin_{b}", *pos[b], yaw[b])) for a, b, _d, pos, yaw in seq]
                obst = [((b[0], b[1]), RADIUS) for b in lay["bins"]] + [((bx, by), BTN) for bx, by in lay["buttons"]]
                pl = sample_ring(ux.distractor_generator(lay["seed"]), ring=ring, count=count, obstacles=obst, sweeps=sweeps, vis_radius=vr)
                n += 1
                if pl is None: pf += 1; continue
                for x, y, _ in pl:
                    xs.append(x)
                    side["-x(robot side)" if x <= -abs(y) else ("+x(far)" if x >= abs(y) else "±y")] += 1
            tot = sum(side.values())
            print(f"{task} {rname:5s} n={count:2d} placement_fail={pf}/{n} sides={ {k: round(v/tot,3) for k,v in side.items()} } x_mean={np.mean(xs):.3f}", flush=True)
