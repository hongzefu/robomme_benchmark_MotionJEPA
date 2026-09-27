#!/usr/bin/env python3
"""汇总 reset_part_*.jsonl：按统一区域 U 独立复核（规格值 + 实际 actor 位姿两份），出 MC_REGION 行与散点图。"""
import glob, json, math, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

D = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.lightweight.test_v6_xhard_movecube_region import (  # 独立判据（不从被测代码取）
    BASE, C0, R_IN, R_OUT, B_LO, B_HI, segment_violations, _root, _seg_dist, _in_u)

rows = [json.loads(l) for f in sorted(glob.glob(str(D / "reset_part_*.jsonl"))) for l in open(f)]
fails = [r for r in rows if not r["ok"]]
viol, pts = [], {"cube": [], "goal": [], "grasp": [], "push": [], "seg": []}
actual_mismatch = 0
ways = {}
for r in rows:
    if not r["ok"]:
        continue
    ways[r["actual"]["way"]] = ways.get(r["actual"]["way"], 0) + 1
    for seg in ("demo", "execution"):
        lay = r["layout"][seg]
        for v in segment_violations(lay):
            viol.append((r["seed"], seg, v))
        root, yaw = _root(lay), float(lay["peg_yaw"])
        u = np.array([math.cos(yaw), math.sin(yaw)])
        g = np.asarray(lay["goal_xy"]); c = np.asarray(lay["cube_pose"][:2])
        pts["cube"].append(c); pts["goal"].append(g); pts["grasp"].append(root - 0.1 * u)
        pts["seg"].append((root - 0.15 * u, root + 0.05 * u))
        d = (g - c) / np.linalg.norm(g - c); lat = np.array([-d[1], d[0]])
        for s in (0, 1, -1):
            pts["push"].append(c - 0.1 * d - 0.1 * s * lat)
    # 实际 actor 位姿复核（与规格值一致，且同样满足 U）
    A = r["actual"]; L = r["layout"]
    pairs = [(A["cube"], L["demo"]["cube_pose"][:2]), (A["cube_2"], L["execution"]["cube_pose"][:2]),
             (A["goal"], L["demo"]["goal_xy"]), (A["goal_2"], L["execution"]["goal_xy"]),
             (A["peg_p"], _root(L["demo"])), (A["peg2_p"], _root(L["execution"]))]
    for x, y in pairs:
        if np.max(np.abs(np.asarray(x, float) - np.asarray(y, float))) > 1e-5:
            actual_mismatch += 1
    # 实测杆尾（tail link 中心）= 抓取点
    if not _in_u(np.asarray(A["peg_tail"])):
        viol.append((r["seed"], "demo", "actual_peg_tail"))

n = len(rows)
print(f"MC_REGION={'PASS' if not viol and not fails and not actual_mismatch else 'FAIL'} resets={n} "
      f"violations={len(viol)} layout_fail={len(fails)} actual_mismatch={actual_mismatch} ways={ways}")
if fails:
    from collections import Counter
    print(Counter(r["error_type"] for r in fails), fails[0]["error"])
for k in ("cube", "goal", "grasp", "push"):
    P = np.array(pts[k]); rc = np.linalg.norm(P - C0, axis=1); rb = np.linalg.norm(P - BASE, axis=1)
    print(f"  {k}: n={len(P)} 离圆心 [{rc.min():.4f}, {rc.max():.4f}] 离基座 [{rb.min():.4f}, {rb.max():.4f}]")
cg = np.linalg.norm(np.array(pts["goal"]) - np.array(pts["cube"]), axis=1)
print(f"  推距 [{cg.min():.4f}, {cg.max():.4f}] 均值 {cg.mean():.4f}")

# ── 散点图 ──
cjk = [f for f in font_manager.findSystemFonts() if "NotoSansCJK" in f.replace(" ", "") or "Noto Sans CJK" in f]
if cjk:
    font_manager.fontManager.addfont(cjk[0])
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=cjk[0]).get_name()
fig, axes = plt.subplots(1, 2, figsize=(15, 9))
th = np.linspace(0, 2 * np.pi, 400)
for ax, title in zip(axes, ("方块中心 / goal 中心 / 杆抓取点", "推起点（3 个/段）与杆身线段（前 300 段）")):
    for r_, st in ((R_IN, "k--"), (R_OUT, "k-")):
        ax.plot(C0[0] + r_ * np.cos(th), C0[1] + r_ * np.sin(th), st, lw=1.2)
    for r_ in (B_LO, B_HI):
        ax.plot(BASE[0] + r_ * np.cos(th), BASE[1] + r_ * np.sin(th), color="tab:blue", ls=":", lw=1)
    ax.plot(*C0, "k+", ms=10)
    ax.set_aspect("equal"); ax.set_xlim(-0.40, 0.25); ax.set_ylim(-0.38, 0.38); ax.grid(alpha=0.3)
    ax.set_xlabel("x（m，桌面，+x 远离机械臂）"); ax.set_ylabel("y（m）"); ax.set_title(title)
ax = axes[0]
for k, col in (("grasp", "tab:orange"), ("goal", "tab:green"), ("cube", "tab:red")):
    P = np.array(pts[k]); ax.scatter(P[:, 0], P[:, 1], s=2, alpha=0.35, c=col, label=f"{k}（{len(P)}）")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2, markerscale=5, fontsize=9, frameon=False)
ax = axes[1]
P = np.array(pts["push"]); ax.scatter(P[:, 0], P[:, 1], s=1.5, alpha=0.25, c="tab:purple", label=f"推起点（{len(P)}）")
for a, b in pts["seg"][:300]:
    ax.plot([a[0], b[0]], [a[1], b[1]], color="tab:brown", lw=0.6, alpha=0.5)
ax.plot([], [], color="tab:brown", lw=1, label="杆身线段")
ax.plot([], [], color="tab:blue", ls=":", label=f"离基座 {B_LO}/{B_HI}")
ax.plot([], [], "k-", label=f"圆环 r_in={R_IN} / r_out={R_OUT}，圆心 (−0.06, 0)")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2, markerscale=5, fontsize=9, frameon=False)
fig.suptitle(f"V6 MoveCube xhard 统一区域 U：真实 reset {n} 局 × 2 段；违规 {len(viol)}，生成失败 {len(fails)}", y=0.97)
fig.subplots_adjust(top=0.90, bottom=0.18, left=0.06, right=0.98, wspace=0.15)
fig.savefig(D / "region_check.png", dpi=110, bbox_inches="tight")
print("saved", D / "region_check.png")
