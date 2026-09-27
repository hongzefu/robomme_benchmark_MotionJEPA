"""俯视散点：V4 实际 vs V5 候选（各 400 局，有色=红点、干扰=灰点、目标=黑叉）。"""
import sys
sys.path.insert(0, sys.argv[1])
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import replica as R
from replica_v5b import pick_layout_ext
N = 400; S0 = 20_000_000
cfgs = [("PickXtimes V4 actual (cb0.5 all3, trimesh OBB)", lambda s: pick_layout_ext(s), 0.2),
        ("PickXtimes V5B distinct-quadrant + exact OBB + min 8cm", lambda s: pick_layout_ext(s, obb_mode="exact", distinct_quadrant=True, min_center_dist=0.08, max_trials=1024), 0.2),
        ("PickXtimes V5B + region half 0.25", lambda s: pick_layout_ext(s, obb_mode="exact", distinct_quadrant=True, min_center_dist=0.08, cube_half=0.25, max_trials=1024), 0.25),
        ("SwingXtimes V4 actual", lambda s: R.swing_layout(s), 0.25)]
fig, axs = plt.subplots(1, 4, figsize=(22, 6))
for ax, (title, f, h) in zip(axs, cfgs):
    for i in range(N):
        o = f(S0 + i)
        if "fail" in o: continue
        for (_, x, y, _) in o["colored"]: ax.plot(y, x, ".", color="tab:red", ms=2, alpha=0.5)
        for (_, x, y, _) in o["distractors"]: ax.plot(y, x, ".", color="tab:gray", ms=2, alpha=0.5)
    ax.add_patch(plt.Rectangle((-h, -0.1 - h), 2 * h, 2 * h, fill=False, ls="--"))
    ax.axhline(-0.1, lw=0.5); ax.axvline(0, lw=0.5)
    ax.set_title(title, fontsize=9); ax.set_xlabel("y (m)"); ax.set_ylabel("x (m, robot at -0.615 = bottom)")
    ax.set_aspect("equal"); ax.set_xlim(-0.3, 0.3); ax.set_ylim(-0.4, 0.2)
plt.tight_layout(); plt.savefig(f"{sys.argv[1]}/layout_scatter_v4_vs_v5.png", dpi=80)
print("saved")
