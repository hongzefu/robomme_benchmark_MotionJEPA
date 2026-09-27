# 俯视散点（V4 vs hc0.12，同 seed）与 2400 局位置密度热图
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from placements import place
HERE = os.path.dirname(__file__)
seeds = [4900000 + 100 * e for e in range(10)]
fig, axes = plt.subplots(2, 5, figsize=(16, 7))
for j, s in enumerate(seeds[:5]):
    for i, m in enumerate(["v4", "hc0.12"]):
        ax = axes[i, j]; r = place(s, m); P = np.array([c[:2] for c in r["cubes"]])
        ax.add_patch(plt.Rectangle((-0.25, -0.3), 0.5, 0.4, fill=False, ls="--", color="g"))
        bx, by = r["button"]; ax.add_patch(plt.Rectangle((by - 0.056, bx - 0.056), 0.1125, 0.1125, color="m", alpha=0.3))
        ax.scatter(P[:, 1], P[:, 0], s=120, marker="s", c="goldenrod", edgecolors="k")
        for k, (x, y) in enumerate(P):
            ax.text(y + 0.012, x + 0.012, str(k), fontsize=8)
        ax.set_xlim(0.28, -0.28); ax.set_ylim(0.13, -0.33); ax.set_aspect("equal")
        ax.set_title(f"{m} seed {s}", fontsize=9)
fig.suptitle("top-down (y horizontal, x vertical; robot side up = image top); magenta=button, green=region")
fig.tight_layout(); fig.savefig(os.path.join(HERE, "layouts_v4_vs_hc012.png"), dpi=80)
R = json.load(open(os.path.join(HERE, "big_sim_2400.json")))
fig, axes = plt.subplots(1, 4, figsize=(16, 4.5))
for ax, m in zip(axes, ["v4", "hc0.12", "bc8", "CSR"]):
    P = np.concatenate([np.array(R[s][m]["P"]) for s in R if R[s][m]["ok"]])
    h = ax.hist2d(P[:, 1], P[:, 0], bins=[23, 18], range=[[-0.23, 0.23], [-0.28, 0.08]], cmap="viridis")
    ax.set_title(f"{m}: density of cube centers"); ax.invert_xaxis(); ax.invert_yaxis(); plt.colorbar(h[3], ax=ax)
fig.tight_layout(); fig.savefig(os.path.join(HERE, "density_2400.png"), dpi=80)
print("saved")
