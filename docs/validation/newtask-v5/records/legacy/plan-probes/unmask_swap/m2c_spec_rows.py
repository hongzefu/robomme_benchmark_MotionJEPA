"""M2c：V4 冻结规格的 20 行（VUS/BUS 各 10）原样的 3 个干扰容器上，外部交换（perm 发起者 = 追加一次 randperm(3)）
的逐窗结果：不顺延时各窗是否通过，顺延时整局是否可行（ev / evc 两级判据）。"""
import sys, json, collections
import numpy as np, torch
SP = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap"
sys.path.insert(0, SP)
from replica import layout_from_spec, load_spec_rows, inner_sequence
from m2b_fallback import eval_window
from robomme.robomme_env.utils import unmask_swap_xhard as ux
from ring_sampler import sample_ring, V4_RING, state, RADIUS
tot = collections.Counter()
for row in load_spec_rows():
    if row["task"] not in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
        continue
    lay = layout_from_spec(row)
    seq = inner_sequence(lay)
    # 专用流：复现 V4 的放置消耗后再追加 randperm(3)
    gen = ux.distractor_generator(row["seed"])
    sweeps = [(state(f"bin_{a}", *pos[a], yaw[a]), state(f"bin_{b}", *pos[b], yaw[b])) for a, b, _d, pos, yaw in seq]
    obst = [((b[0], b[1]), RADIUS) for b in lay["bins"]] + [((bx, by), float(np.linalg.norm([0.05625, 0.05625]))) for bx, by in lay["buttons"]]
    pl = sample_ring(gen, ring=V4_RING, count=3, obstacles=obst, sweeps=sweeps)
    assert np.allclose(np.array(pl), np.array(lay["distractors"]), atol=0, rtol=0)
    perm = torch.randperm(3, generator=gen).tolist()
    out = {}
    for crit in ("none", "ev", "evc"):
        opos = [np.array(p[:2]) for p in pl]; oyaw = [p[2] for p in pl]
        ok_all, tries, first = True, [], []
        for k, (a, b, _d, ipos, iyaw) in enumerate(seq):
            chosen = None
            for j in range(3 if crit != "none" else 1):
                o = perm[(k + j) % 3]
                p = min((q for q in range(3) if q != o), key=lambda q: (float(np.linalg.norm(np.float32(opos[o]) - np.float32(opos[q]))), q))
                r = eval_window(k, a, b, ipos, iyaw, o, p, opos, oyaw, 0.07, lay["buttons"])
                good = r["exact_ok"] and r["visible"] and r["btn_ok"] and (crit != "evc" or r["c_inner"] >= 0.04)
                if crit == "none":
                    first.append("ok" if r["exact_ok"] else "COL")
                    chosen = (o, p); good_none = r["exact_ok"]
                    if not r["exact_ok"]:
                        ok_all = False
                    break
                if good:
                    chosen = (o, p); tries.append(j + 1); break
            if chosen is None:
                ok_all = False; break
            o, p = chosen
            opos[o], opos[p] = opos[p].copy(), opos[o].copy(); oyaw[o], oyaw[p] = oyaw[p], oyaw[o]
        out[crit] = (ok_all, tries if crit != "none" else "".join("." if f == "ok" else "X" for f in first))
        tot[(row["task"][:3], crit)] += ok_all
    print(row["task"][:3], "ep", row["episode"], "seed", row["seed"], "n_swaps", lay["n_swaps"],
          "no_fallback(exact only) per-window:", out["none"][1], "ok" if out["none"][0] else "FAIL",
          "| fallback ev:", out["ev"], "| fallback evc:", out["evc"], flush=True)
print("SPEC_ROWS_OUTER_FEASIBLE", dict(tot))
