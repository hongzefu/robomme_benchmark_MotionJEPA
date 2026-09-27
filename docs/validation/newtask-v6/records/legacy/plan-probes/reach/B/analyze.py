#!/usr/bin/env python3
"""汇总 parts/w*.csv → peg_grid.csv，出 peg_reach_maps.png / peg_envelope.png，并打印报告用数字（stats.json）。"""
import csv
import glob
import json
import math
import os
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.patches import Circle, Rectangle

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

D = os.path.dirname(os.path.abspath(__file__))
BASE = np.array([-0.615, 0.0])
STEP = 0.025
XS = np.round(np.arange(-0.40, 0.35 + 1e-9, STEP), 3)
YS = np.round(np.arange(-0.40, 0.40 + 1e-9, STEP), 3)
YAWS = list(range(0, 360, 30))
T_GRASP, T_MID = -0.10, -0.05   # 抓取点（peg_tail 中心）与杆身中点沿 u 相对根的位置

rows = []
for p in sorted(glob.glob(os.path.join(D, "parts", "w*.csv"))):
    rows += list(csv.DictReader(open(p)))
for r in rows:
    r["x"], r["y"], r["yaw_deg"] = float(r["x"]), float(r["y"]), int(float(r["yaw_deg"]))
rows.sort(key=lambda r: (r["yaw_deg"], r["x"], r["y"]))
fields = ["x", "y", "yaw_deg", "ok", "err", "flipped", "tgt_z", "grasping", "rrt", "sec", "msg"]
with open(os.path.join(D, "peg_grid.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in fields})

ix = {v: i for i, v in enumerate(XS)}
iy = {v: j for j, v in enumerate(YS)}
OK = np.full((len(YAWS), len(XS), len(YS)), -1, dtype=int)
FL = np.zeros_like(OK)
for r in rows:
    k = YAWS.index(r["yaw_deg"])
    OK[k, ix[round(r["x"], 3)], iy[round(r["y"], 3)]] = int(r["ok"])
    FL[k, ix[round(r["x"], 3)], iy[round(r["y"], 3)]] = int(r["flipped"])
missing = int((OK < 0).sum())
ALL = (OK == 1).all(axis=0)
GX, GY = np.meshgrid(XS, YS, indexing="ij")


def region_stats(mask, cx, cy, valid=None):
    """mask 为真的格点集合的统计：离基座最远/最近、x/y 范围、以 (0,0) 为圆心的最大内切圆半径。
    valid 为可评估格（参考点换算回杆根后仍在网格内）；内切圆只按可评估的失败格算。"""
    if not mask.any():
        return None
    if valid is None:
        valid = np.ones_like(mask)
    px, py = cx[mask], cy[mask]
    d = np.hypot(px - BASE[0], py - BASE[1])
    bad = (~mask) & valid
    dom = min(abs(XS[0]), XS[-1], abs(YS[0]), YS[-1])   # 网格边界离原点的最近距离（内切圆上限）
    r_in = float(np.hypot(cx[bad], cy[bad]).min()) if bad.any() else dom
    return dict(n=int(mask.sum()), area_m2=round(float(mask.sum()) * STEP ** 2, 4),
                d_base_max=round(float(d.max()), 4), d_base_min=round(float(d.min()), 4),
                x_range=[float(px.min()), float(px.max())], y_range=[float(py.min()), float(py.max())],
                r_inscribed=round(min(r_in, dom), 4), r_inscribed_capped=bool(r_in >= dom))


def shifted_all(t):
    """以「根 + t·u」为参考点重排：参考点格 m 在各 yaw 下对应根 m − t·u，取最近根格（误差 ≤ 半格）。"""
    out = np.ones((len(XS), len(YS)), dtype=bool)
    valid = np.ones_like(out)
    per = []
    for k, yd in enumerate(YAWS):
        u = np.array([math.cos(math.radians(yd)), math.sin(math.radians(yd))])
        rx, ry = GX - t * u[0], GY - t * u[1]
        ii = np.rint((rx - XS[0]) / STEP).astype(int)
        jj = np.rint((ry - YS[0]) / STEP).astype(int)
        inside = (ii >= 0) & (ii < len(XS)) & (jj >= 0) & (jj < len(YS))
        m = np.zeros_like(out)
        m[inside] = OK[k, ii[inside], jj[inside]] == 1
        per.append(m)
        out &= m
        valid &= inside
    return out, valid


def draw_context(ax, boxes=True):
    ax.plot(*BASE, marker="s", ms=9, color="#333333", zorder=5)
    ax.annotate("基座", BASE, xytext=(4, 8), textcoords="offset points", fontsize=8, color="#333333")
    ax.plot(0, 0, marker="+", ms=10, mew=2, color="#1f4e9c", zorder=5)
    if boxes:
        for yc in (0.2, -0.2):
            ax.add_patch(Rectangle((-0.05, yc - 0.05), 0.10, 0.10, fill=False, ec="#1f4e9c", lw=1.4, ls="--", zorder=4))
    ax.set_xlim(-0.66, 0.39)
    ax.set_ylim(-0.44, 0.44)
    ax.set_aspect("equal")


cmap = ListedColormap(["#d9534f", "#5cb85c"])
ext = [XS[0] - STEP / 2, XS[-1] + STEP / 2, YS[0] - STEP / 2, YS[-1] + STEP / 2]

# ── 图 1：12 个 yaw + 交集 ──
fig, axes = plt.subplots(4, 4, figsize=(17, 15.5))
for k, yd in enumerate(YAWS):
    ax = axes.flat[k]
    ax.imshow(OK[k].T == 1, origin="lower", extent=ext, cmap=cmap, vmin=0, vmax=1, interpolation="nearest", alpha=0.85)
    fl = FL[k] == 1
    if fl.any():
        ax.scatter(GX[fl], GY[fl], s=2.5, c="k", marker=".", linewidths=0, zorder=3)
    draw_context(ax)
    u = np.array([math.cos(math.radians(yd)), math.sin(math.radians(yd))])
    ax.annotate("", xy=(-0.52 + 0.08 * u[0], 0.33 + 0.08 * u[1]), xytext=(-0.52, 0.33),
                arrowprops=dict(arrowstyle="-|>", color="k", lw=1.5))
    n = int((OK[k] == 1).sum())
    ax.set_title(f"yaw={yd}°  成功 {n}/{OK[k].size} 格", fontsize=11)
    ax.tick_params(labelsize=7)
ax = axes.flat[12]
ax.imshow(ALL.T, origin="lower", extent=ext, cmap=cmap, vmin=0, vmax=1, interpolation="nearest", alpha=0.85)
draw_context(ax)
ax.set_title(f"全部 12 个 yaw 都成功（交集） {int(ALL.sum())} 格", fontsize=11)
ax.tick_params(labelsize=7)
cnt = (OK == 1).sum(axis=0)
ax = axes.flat[13]
im = ax.imshow(cnt.T, origin="lower", extent=ext, cmap="viridis", vmin=0, vmax=12, interpolation="nearest")
draw_context(ax)
ax.set_title("成功的 yaw 个数（0～12）", fontsize=11)
ax.tick_params(labelsize=7)
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
for a in axes.flat[14:]:
    a.axis("off")
axes.flat[14].text(0.02, 0.95,
                   "图例\n绿：抓起成功   红：失败\n黑点：该格触发 xhard 翻转归约\n灰方块：机器人基座 (-0.615, 0)\n"
                   "蓝十字：桌心 (0, 0)\n蓝虚线框：当前杆根范围\n  x∈[-0.05,0.05]，y∈±0.2±0.05\n左上黑箭头：杆朝向 u（根→head）\n\n"
                   "格点 = 杆根 root，步长 0.025 m\n抓取点 = root − 0.10·u（peg_tail 中心）\n横轴 x（米，远离基座为正），纵轴 y（米）",
                   va="top", fontsize=10.5, transform=axes.flat[14].transAxes)
fig.suptitle("MoveCube xhard：杆根位置 × yaw 的抓杆可达图（真实模拟器 + 正式规划器）", fontsize=15, y=0.995)
fig.tight_layout(rect=[0, 0, 1, 0.98])
fig.savefig(os.path.join(D, "peg_reach_maps.png"), dpi=110)
plt.close(fig)

# ── 图 2：交集包络（按根 / 按杆身中点 / 按抓取点）──
MID, MID_valid = shifted_all(T_MID)
GRP, GRP_valid = shifted_all(T_GRASP)
stats = {"missing": missing, "n_rows": len(rows)}
fig, axes = plt.subplots(1, 3, figsize=(20, 9.6))
for ax, (name, mask, valid) in zip(axes, [("按杆根 root", ALL, np.ones_like(ALL)), ("按杆身中点 root−0.05·u", MID, MID_valid),
                                           ("按抓取点 root−0.10·u", GRP, GRP_valid)]):
    img = np.where(valid, mask.astype(int) + 1, 0)
    ax.imshow(img.T, origin="lower", extent=ext, cmap=ListedColormap(["#dddddd", "#f2b8b5", "#5cb85c"]), vmin=0, vmax=2,
              interpolation="nearest")
    draw_context(ax, boxes=(name.startswith("按杆根")))
    s = region_stats(mask, GX, GY, valid)
    if s:
        vx, vy = GX[valid], GY[valid]
        s["x_hits_grid_edge"] = [bool(s["x_range"][0] <= vx.min() + 1e-9), bool(s["x_range"][1] >= vx.max() - 1e-9)]
        s["y_hits_grid_edge"] = [bool(s["y_range"][0] <= vy.min() + 1e-9), bool(s["y_range"][1] >= vy.max() - 1e-9)]
    stats[name] = s
    if s:
        d = np.hypot(GX - BASE[0], GY - BASE[1])
        for dist, col, lab in ((s["d_base_max"], "#8a2be2", "最远"), (s["d_base_min"], "#e67e22", "最近")):
            ax.add_patch(Circle(BASE, dist, fill=False, ec=col, lw=1.2, ls=":"))
        ax.add_patch(Circle((0, 0), s["r_inscribed"], fill=False, ec="#1f4e9c", lw=1.8))
        ax.add_patch(Rectangle((s["x_range"][0] - STEP / 2, s["y_range"][0] - STEP / 2),
                               s["x_range"][1] - s["x_range"][0] + STEP, s["y_range"][1] - s["y_range"][0] + STEP,
                               fill=False, ec="k", lw=0.8, ls="-."))
        edge = lambda f: "（顶到可评估边界）" if any(f) else ""
        txt = (f"格数 {s['n']}（{s['area_m2']} m²）\n离基座最远 {s['d_base_max']:.3f} m（紫点线）\n"
               f"离基座最近 {s['d_base_min']:.3f} m（橙点线）\n"
               f"x ∈ [{s['x_range'][0]:.3f}, {s['x_range'][1]:.3f}]{edge(s['x_hits_grid_edge'])}\n"
               f"y ∈ [{s['y_range'][0]:.3f}, {s['y_range'][1]:.3f}]{edge(s['y_hits_grid_edge'])}（点划框）\n"
               f"以 (0,0) 为心内切圆 r = {s['r_inscribed']:.3f} m（蓝实线）"
               + ("\n（已顶到网格边界）" if s["r_inscribed_capped"] else ""))
        txt += "\n绿：12 个 yaw 全成功  粉：至少一个失败\n灰：换算回杆根后出了探测网格，无法评估"
        ax.text(0.0, -0.13, txt, transform=ax.transAxes, fontsize=10, va="top",
                bbox=dict(boxstyle="round", fc="white", ec="#999999", alpha=0.92))
    ax.set_title(f"全 yaw 可抓区域（{name}）", fontsize=12.5)
    ax.set_xlabel("x（米）")
    ax.set_ylabel("y（米）")
fig.suptitle("MoveCube xhard 抓杆：12 个 yaw 全部成功的区域包络", fontsize=15)
fig.subplots_adjust(left=0.04, right=0.99, top=0.92, bottom=0.30, wspace=0.18)
fig.savefig(os.path.join(D, "peg_envelope.png"), dpi=110)
plt.close(fig)

# ── 报告数字 ──
per_yaw = []
for k, yd in enumerate(YAWS):
    m = OK[k] == 1
    s = region_stats(m, GX, GY)
    u = np.array([math.cos(math.radians(yd)), math.sin(math.radians(yd))])
    gx, gy = GX + T_GRASP * u[0], GY + T_GRASP * u[1]
    dg = np.hypot(gx - BASE[0], gy - BASE[1])
    fails = OK[k] == 0
    inbox = ((np.abs(GX) <= 0.05 + 1e-9) & (np.abs(np.abs(GY) - 0.2) <= 0.05 + 1e-9))
    per_yaw.append(dict(
        yaw=yd, n_ok=int(m.sum()), area=s["area_m2"] if s else 0,
        flip_frac_all=round(float((FL[k] == 1).mean()), 3),
        flip_frac_ok=round(float((FL[k][m] == 1).mean()), 3) if m.any() else 0,
        grasp_d_ok_max=round(float(dg[m].max()), 3) if m.any() else None,
        grasp_d_fail_min=round(float(dg[fails].min()), 3) if fails.any() else None,
        root_r_inscribed=s["r_inscribed"] if s else 0,
        box_ok=f"{int((m & inbox).sum())}/{int(inbox.sum())}",
        x_max_ok=s["x_range"][1] if s else None))
stats["per_yaw"] = per_yaw
stats["err_counts"] = Counter(r["err"] or "OK" for r in rows)
stats["err_by_yaw"] = {yd: dict(Counter(r["err"] for r in rows if r["yaw_deg"] == yd and r["ok"] != "1")) for yd in YAWS}
stats["msg_top"] = Counter(r["msg"] for r in rows if r["ok"] != "1").most_common(8)
stats["rrt_rescued"] = sum(1 for r in rows if r["ok"] == "1" and int(r["rrt"]) > 0)
stats["sec_total"] = round(sum(float(r["sec"]) for r in rows), 1)
# 抓取点离基座距离分桶的成功率（全部 yaw 混合）
dgs, oks = [], []
for r in rows:
    u = np.array([math.cos(math.radians(r["yaw_deg"])), math.sin(math.radians(r["yaw_deg"]))])
    g = np.array([r["x"], r["y"]]) + T_GRASP * u
    dgs.append(float(np.hypot(*(g - BASE)))); oks.append(r["ok"] == "1")
dgs, oks = np.array(dgs), np.array(oks)
bins = np.arange(0.15, 1.10, 0.05)
stats["grasp_dist_rate"] = [(round(b, 2), round(b + 0.05, 2), int(((dgs >= b) & (dgs < b + 0.05)).sum()),
                             round(float(oks[(dgs >= b) & (dgs < b + 0.05)].mean()), 3) if ((dgs >= b) & (dgs < b + 0.05)).any() else None)
                            for b in bins]
# 当前杆根框里全 yaw 成功比例
inbox = ((np.abs(GX) <= 0.05 + 1e-9) & (np.abs(np.abs(GY) - 0.2) <= 0.05 + 1e-9))
stats["box_all_yaw"] = f"{int((ALL & inbox).sum())}/{int(inbox.sum())}"
json.dump(stats, open(os.path.join(D, "stats.json"), "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(stats, ensure_ascii=False, indent=1, default=str))
