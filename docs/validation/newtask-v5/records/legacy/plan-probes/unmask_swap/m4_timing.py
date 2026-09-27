"""M4：每窗碰撞检查墙钟（单进程）。
A = 现行运行期：仓库 check_swap_sweep(内部对, 旁观=其余内部+干扰容器)；
B = V5 联合检查：check_multi_swap_sweep([内部对, 外部对], 全部静止)（不加圆预筛，逐对照仓库粗筛+二分）；
C = B + 外接圆严格预筛（只精算圆判有风险的对象对）。
布局：VUS/BUS 合成 seed 各 6 个；干扰容器 count=3（V4 外环）与 10（V4 外环），外部发起者 perm。
"""
import sys, time, numpy as np, torch
SP = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap"
sys.path.insert(0, SP)
from replica import vus_layout, bus_layout, inner_sequence
from ring_sampler import V4_RING, sample_ring, state, RADIUS, _sweep_paths
from multi_sweep import check_multi_swap_sweep, movers_for_pair
from robomme.robomme_env.utils.bin_collision import check_swap_sweep
from robomme.robomme_env.utils import bin_collision as bc
from robomme.robomme_env.utils import unmask_swap_xhard as ux
BTN = float(np.linalg.norm([0.05625, 0.05625]))
S = np.linspace(0, 1, 401)

def prefiltered(pairs, statics):
    movers, paths = [], []
    for sa, sb in pairs:
        ma, mb = movers_for_pair(sa, sb); pa, pb, v = _sweep_paths(sa, sb)
        movers += [(ma, pa, v), (mb, pb, v)]
    checks = []
    for i in range(len(movers)):
        for j in range(i + 1, len(movers)):
            (m1, p1, v1), (m2, p2, v2) = movers[i], movers[j]
            if not float(np.min(np.linalg.norm(p1 - p2, axis=1))) - 2 * RADIUS > (v1 + v2) * (S[1] - S[0]) / 2:
                checks.append((m1, m2))
    for m, p, v in movers:
        for st in statics:
            if not float(np.min(np.linalg.norm(p - st.p[:2], axis=1))) - 2 * RADIUS > v * (S[1] - S[0]) / 2:
                checks.append((m, bc._Static(name=st.name, shapes=st.shapes, radii=st.radii, p=st.p.copy(), q=st.q.copy())))
    for l, r in checks:
        for ia in range(len(l.shapes)):
            for ib in range(len(r.shapes)):
                g, rej = bc._prove_pair(l, r, ia, ib, stage="sweep", sweep_index=None)
                if rej is not None:
                    return rej
    return None

res = {}
for count in (3, 10):
    for name, fn, base in (("VUS", vus_layout, 9_100_000), ("BUS", bus_layout, 9_300_000)):
        tA, tB, tC, nw = 0, 0, 0, 0
        for i in range(6):
            lay = fn(base + i)
            seq = inner_sequence(lay)
            sweeps = [(state(f"bin_{a}", *pos[a], yaw[a]), state(f"bin_{b}", *pos[b], yaw[b])) for a, b, _d, pos, yaw in seq]
            obst = [((b[0], b[1]), RADIUS) for b in lay["bins"]] + [((bx, by), BTN) for bx, by in lay["buttons"]]
            gen = ux.distractor_generator(lay["seed"])
            pl = sample_ring(gen, ring=V4_RING, count=count, obstacles=obst, sweeps=sweeps)
            perm = torch.randperm(count, generator=gen).tolist()
            opos = [np.array(p[:2]) for p in pl]; oyaw = [p[2] for p in pl]
            for k, (a, b, _d, ipos, iyaw) in enumerate(seq[:4]):
                o = perm[k % count]
                p = min((j for j in range(count) if j != o), key=lambda j: (float(np.linalg.norm(opos[o] - opos[j])), j))
                sa, sb = state(f"bin_{a}", *ipos[a], iyaw[a]), state(f"bin_{b}", *ipos[b], iyaw[b])
                so, sp = state(f"d{o}", *opos[o], oyaw[o]), state(f"d{p}", *opos[p], oyaw[p])
                inner_by = [state(f"bin_{j}", *ipos[j], iyaw[j]) for j in range(4) if j not in (a, b)]
                outer_all = [state(f"d{j}", *opos[j], oyaw[j]) for j in range(count)]
                outer_by = [s for j, s in enumerate(outer_all) if j not in (o, p)]
                t = time.perf_counter(); check_swap_sweep(sa, sb, inner_by + outer_all); tA += time.perf_counter() - t
                t = time.perf_counter(); check_multi_swap_sweep([(sa, sb), (so, sp)], inner_by + outer_by); tB += time.perf_counter() - t
                t = time.perf_counter(); prefiltered([(sa, sb), (so, sp)], inner_by + outer_by); tC += time.perf_counter() - t
                nw += 1
                opos[o], opos[p] = opos[p].copy(), opos[o].copy(); oyaw[o], oyaw[p] = oyaw[p], oyaw[o]
        print(f"{name} count={count} windows={nw}: A_current={1000*tA/nw:.0f} ms/window  B_joint={1000*tB/nw:.0f} ms/window  C_joint+circle={1000*tC/nw:.1f} ms/window", flush=True)
