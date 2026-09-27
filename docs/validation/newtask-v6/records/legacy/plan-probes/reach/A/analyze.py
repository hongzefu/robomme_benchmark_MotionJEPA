# -*- coding: utf-8 -*-
"""汇总分片 csv → reach_grid.csv、reach_maps.png、reach_envelope.png、metrics.json。"""
import glob, json, math, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch, Rectangle, Circle

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

D = sys.argv[1] if len(sys.argv) > 1 else "."
BASE = np.array([-0.615, 0.0])
STEP = 0.025
BOX = 0.14
YAWS = list(range(0, 360, 45))
TYPES = ["grasp", "push", "push2", "peg", "peg2"]
TNAME = {"grasp": "顶抓（先到 z=0.15 再下到 0.02）",
         "push": "推方块（初始位姿直达 z=0.02）",
         "push2": "推方块（两段式：悬停 0.15 再下）",
         "peg": "带杆推起点（直达，正负两方向取较好者）",
         "peg2": "带杆推起点（两段式，正负两方向取较好者）"}

df = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"{D}/shards/*.csv"))], ignore_index=True)
df = df.sort_values(["pose_type", "x", "y", "yaw_deg", "direction"]).reset_index(drop=True)
df.to_csv(f"{D}/reach_grid.csv", index=False)
# 状态码：3=成功；2=规划成功但到位误差≥1cm；1=screw 失败但存在逆解；0=screw 失败且无逆解
df["code"] = np.where(df.ok == 1, 3, np.where(df.plan_ok == 1, 2, np.where(df.ik_ok == 1, 1, 0)))
# 规划成功但偏离很大（>5cm）说明 screw 积分停在别处，按「无逆解」对待更贴切，仅在 ik_ok=0 时降级
df.loc[(df.code == 2) & (df.ik_ok == 0) & (df.err_cm > 5), "code"] = 0

xs = np.round(np.sort(df.x.unique()), 4)
ys = np.round(np.sort(df.y.unique()), 4)
XI = {v: i for i, v in enumerate(xs)}
YI = {v: i for i, v in enumerate(ys)}
GX, GY = np.meshgrid(xs, ys, indexing="ij")


def grid(sub, col="code", agg="min"):
    g = sub.groupby(["x", "y"])[col].agg(agg)
    a = np.full((len(xs), len(ys)), -1, dtype=float)
    for (x, y), v in g.items():
        a[XI[round(x, 4)], YI[round(y, 4)]] = v
    return a


codes = {}  # codes[type][yaw] -> 网格状态（peg 类取 ±方向中较好者，即 xhard 抓杆翻转可选时的口径）
codes_lit = {}  # peg 类取 ±方向较差者（两方向都必须成功）
for t in TYPES:
    agg = "max" if t.startswith("peg") else "min"
    codes[t] = {yd: grid(df[(df.pose_type == t) & (df.yaw_deg == yd)], agg=agg) for yd in YAWS}
    codes_lit[t] = {yd: grid(df[(df.pose_type == t) & (df.yaw_deg == yd)], agg="min") for yd in YAWS}
# 等价归约：顶抓 closing 方向 yaw 与 yaw+180° 是同一个物理抓取（solve_pickup 按 OBB 取离当前闭合方向最近的边，
# 因而实际只会用到离当前手腕最近的那一个），故 grasp 的「某 yaw 可抓」= 两者任一成功
def eff(t, yd):
    if t == "grasp":
        return np.maximum(codes[t][yd], codes[t][(yd + 180) % 360])
    return codes[t][yd]
ok_all = {t: np.all([eff(t, yd) == 3 for yd in YAWS], axis=0) for t in TYPES}
ok_all_lit = {t: np.all([codes_lit[t][yd] == 3 for yd in YAWS], axis=0) for t in TYPES}
ik_all = {t: np.all([codes_lit[t][yd] >= 1 for yd in YAWS], axis=0) for t in TYPES}


def fill_holes(M):
    """把不与扫描域边界连通的「不可达」格点（内部孤立洞）填为可达，返回新网格与填掉的格数。"""
    bad = ~M
    seen = np.zeros_like(bad)
    stack = [(i, j) for i in range(bad.shape[0]) for j in range(bad.shape[1])
             if bad[i, j] and (i in (0, bad.shape[0] - 1) or j in (0, bad.shape[1] - 1))]
    for p in stack:
        seen[p] = True
    while stack:
        i, j = stack.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = i + di, j + dj
            if 0 <= a < bad.shape[0] and 0 <= b < bad.shape[1] and bad[a, b] and not seen[a, b]:
                seen[a, b] = True
                stack.append((a, b))
    return ~seen, int((bad & ~seen).sum())


def region_metrics(M):
    """M：布尔网格（True=可达）。返回 r(θ)、x/y 范围、内切圆等。"""
    pts = np.stack([GX[M], GY[M]], 1)
    out = {"area_m2": float(M.sum() * STEP ** 2), "n": int(M.sum())}
    if len(pts) == 0:
        return out
    rel = pts - BASE
    r = np.hypot(rel[:, 0], rel[:, 1])
    th = np.degrees(np.arctan2(rel[:, 1], rel[:, 0]))
    bins = np.arange(-70, 71, 10)
    on_edge = (np.isclose(pts[:, 0], xs[0]) | np.isclose(pts[:, 0], xs[-1]) |
               np.isclose(pts[:, 1], ys[0]) | np.isclose(pts[:, 1], ys[-1]))
    rt = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        s = (th >= lo) & (th < hi)
        e = {"theta": f"[{lo},{hi})", "r_min": float(r[s].min()) if s.any() else None,
             "r_max": float(r[s].max()) if s.any() else None}
        if s.any():
            # 取到 r_max / r_min 的格点若落在扫描域边界上，说明真实值可能更大/更小（被扫描域截断）
            e["r_max_edge"] = bool(on_edge[s][np.argmax(r[s])])
            e["r_min_edge"] = bool(on_edge[s][np.argmin(r[s])])
        rt.append(e)
    out["r_theta"] = rt
    out["r_max"] = float(r.max()); out["r_min"] = float(r.min())
    out["x_range"] = [float(pts[:, 0].min()), float(pts[:, 0].max())]
    out["y_range"] = [float(pts[:, 1].min()), float(pts[:, 1].max())]
    y0 = np.isclose(GY, 0) & M
    out["x_range_at_y0"] = [float(GX[y0].min()), float(GX[y0].max())] if y0.any() else None
    x0 = np.isclose(GX, 0) & M
    out["y_range_at_x0"] = [float(GY[x0].min()), float(GY[x0].max())] if x0.any() else None
    # 内切圆：圆心到最近「不可达格点」的距离 − 半步长；同时受扫描边界限制（边界外未测，按未知处理）
    bad = np.stack([GX[~M], GY[~M]], 1)
    xlo, xhi, ylo, yhi = xs[0] - STEP / 2, xs[-1] + STEP / 2, ys[0] - STEP / 2, ys[-1] + STEP / 2

    def R_at(c):
        rb = np.hypot(*(bad - c).T).min() - STEP / 2 if len(bad) else 9.0
        re = min(c[0] - xlo, xhi - c[0], c[1] - ylo, yhi - c[1])
        return max(0.0, float(min(rb, re))), bool(re < rb)

    R0, lim0 = R_at(np.array([0.0, 0.0]))
    out["R_center00"] = R0; out["R_center00_domain_limited"] = lim0
    best = (-1, None, None)
    best_y0 = (-1, None, None)
    for cx in np.arange(-0.30, 0.20 + 1e-9, 0.0125):
        for cy in np.arange(-0.10, 0.10 + 1e-9, 0.0125):
            R, lim = R_at(np.array([cx, cy]))
            if R > best[0]:
                best = (R, (round(cx, 4), round(cy, 4)), lim)
            if abs(cy) < 1e-9 and R > best_y0[0]:
                best_y0 = (R, (round(cx, 4), 0.0), lim)
    out["R_best"] = best[0]; out["R_best_center"] = best[1]; out["R_best_domain_limited"] = best[2]
    out["R_best_y0"] = best_y0[0]; out["R_best_y0_center"] = best_y0[1]
    return out


metrics = {"per_type_yaw": {}, "per_type_all_yaw": {}, "per_type_all_yaw_ik": {}, "combos": {}}
for t in TYPES:
    for yd in YAWS:
        m = region_metrics(codes[t][yd] == 3)
        m["ik_area_m2"] = float((codes_lit[t][yd] >= 1).sum() * STEP ** 2)
        m.pop("r_theta", None)
        metrics["per_type_yaw"][f"{t}|{yd}"] = m
    metrics["per_type_all_yaw"][t] = region_metrics(ok_all[t])
    metrics["per_type_all_yaw_literal"] = metrics.get("per_type_all_yaw_literal", {})
    metrics["per_type_all_yaw_literal"][t] = region_metrics(ok_all_lit[t])
    metrics["per_type_all_yaw_ik"][t] = region_metrics(ik_all[t])
# peg 分方向（不合并）的全 yaw 成功面积
for t in ("peg", "peg2"):
    for s in (1, -1):
        g = np.all([grid(df[(df.pose_type == t) & (df.yaw_deg == yd) & (df.direction == s)]) == 3 for yd in YAWS], 0)
        metrics["per_type_all_yaw"][f"{t}|s={s}"] = region_metrics(g)
COMBOS = {
    "严格（grasp∧push∧peg，初始位姿直达）": ok_all["grasp"] & ok_all["push"] & ok_all["peg"],
    "推荐（grasp∧push2∧peg2，两段式）": ok_all["grasp"] & ok_all["push2"] & ok_all["peg2"],
    "抓+两段式推（grasp∧push2，不含带杆推）": ok_all["grasp"] & ok_all["push2"],
    "仅顶抓（grasp，yaw≡yaw+180°）": ok_all["grasp"],
    "IK 上限（五类全 yaw 存在无碰逆解）": np.all([ik_all[t] for t in TYPES], 0),
}
FILLED = {}
for k, M in COMBOS.items():
    metrics["combos"][k] = region_metrics(M)
    Mf, nh = fill_holes(M)
    FILLED[k] = Mf
    mf = region_metrics(Mf)
    mf["holes_filled"] = nh
    metrics["combos_filled"] = metrics.get("combos_filled", {})
    metrics["combos_filled"][k] = mf
for t in TYPES:
    Mf, nh = fill_holes(ok_all[t])
    mf = region_metrics(Mf); mf["holes_filled"] = nh
    metrics["per_type_all_yaw_filled"] = metrics.get("per_type_all_yaw_filled", {})
    metrics["per_type_all_yaw_filled"][t] = mf
json.dump(metrics, open(f"{D}/metrics.json", "w"), ensure_ascii=False, indent=1)

# ---------------- 图 1：reach_maps.png ----------------
cmap = ListedColormap(["#d9d9d9", "#f4a261", "#e9c46a", "#2a9d8f"])
norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], 4)
ext = [xs[0] - STEP / 2, xs[-1] + STEP / 2, ys[0] - STEP / 2, ys[-1] + STEP / 2]


def deco(ax):
    ax.plot(*BASE, marker="s", color="k", ms=5)
    ax.plot(0, 0, marker="+", color="k", ms=8, mew=1.5)
    ax.add_patch(Rectangle((-BOX, -BOX), 2 * BOX, 2 * BOX, fill=False, ls="--", lw=1.0, ec="#c1121f"))
    ax.set_xlim(-0.66, 0.37); ax.set_ylim(-0.42, 0.42); ax.set_aspect("equal")
    ax.tick_params(labelsize=7)


nr, nc = len(TYPES), 9
fig, axs = plt.subplots(nr, nc, figsize=(nc * 2.35, nr * 2.25 + 1.3))
for i, t in enumerate(TYPES):
    for j in range(nc):
        ax = axs[i, j]
        if j < 8:
            yd = YAWS[j]
            ax.imshow(codes[t][yd].T, origin="lower", extent=ext, cmap=cmap, norm=norm, interpolation="nearest")
            a = metrics["per_type_yaw"][f"{t}|{yd}"]["area_m2"]
            ax.set_title(f"yaw={yd}°  面积 {a:.3f} m²", fontsize=8)
        else:
            ax.imshow(np.where(ok_all[t], 3, np.where(ik_all[t], 1, 0)).T, origin="lower", extent=ext, cmap=cmap, norm=norm, interpolation="nearest")
            ax.set_title(("8 yaw 全成功（yaw≡yaw+180°）" if t == "grasp" else "8 个 yaw 全成功") + f"\n{metrics['per_type_all_yaw'][t]['area_m2']:.3f} m²", fontsize=8)
        deco(ax)
        if j == 0:
            ax.set_ylabel(TNAME[t].replace("（", "\n（"), fontsize=8)
handles = [Patch(color="#2a9d8f", label="成功（规划成功且误差<1cm）"),
           Patch(color="#e9c46a", label="规划成功但到位误差≥1cm（screw 开环漂移）"),
           Patch(color="#f4a261", label="screw 失败，但目标存在无碰逆解（正式生成可回退 RRT*）"),
           Patch(color="#d9d9d9", label="screw 失败且无逆解（不可达）"),
           plt.Line2D([], [], marker="s", color="k", ls="", label="机器人基座 (-0.615, 0)"),
           plt.Line2D([], [], marker="+", color="k", ls="", ms=8, label="桌面中心 (0, 0)"),
           Patch(fill=False, ec="#c1121f", ls="--", label="当前 xhard 采样框 ±0.14")]
fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=9, frameon=False)
fig.suptitle("MoveCube：Panda 末端桌面可达性（按手腕 yaw 分列，网格步长 0.025 m，初始 qpos 出发）", fontsize=13)
fig.tight_layout(rect=[0, 0.06, 1, 0.965])
fig.savefig(f"{D}/reach_maps.png", dpi=110)
plt.close(fig)

# ---------------- 图 2：reach_envelope.png ----------------
fig = plt.figure(figsize=(16, 7.2))
ax = fig.add_subplot(1, 2, 1)
ax2 = fig.add_subplot(1, 2, 2)
layers = [("IK 上限（五类全 yaw 存在无碰逆解）", "#e0e0e0"),
          ("仅顶抓（grasp，yaw≡yaw+180°）", "#bde0fe"),
          ("推荐（grasp∧push2∧peg2，两段式）", "#2a9d8f"),
          ("严格（grasp∧push∧peg，初始位姿直达）", "#e76f51")]
for k, col in layers:
    M = FILLED[k]
    rgba = np.zeros((len(ys), len(xs), 4))
    c = matplotlib.colors.to_rgba(col)
    rgba[M.T] = c
    ax.imshow(rgba, origin="lower", extent=ext, interpolation="nearest")
deco(ax)
ax.set_xlim(-0.66, 0.37)
rec = metrics["combos_filled"]["推荐（grasp∧push2∧peg2，两段式）"]
holes = COMBOS["推荐（grasp∧push2∧peg2，两段式）"] != FILLED["推荐（grasp∧push2∧peg2，两段式）"]
ax.scatter(GX[holes], GY[holes], s=10, marker="x", color="#9d0208", zorder=5, label="_")
ax.add_patch(Circle((0, 0), rec["R_center00"], fill=False, ec="k", lw=1.5))
cx, cy = rec["R_best_y0_center"]
ax.add_patch(Circle((cx, cy), rec["R_best_y0"], fill=False, ec="#6a4c93", lw=1.5, ls="-."))
ax.plot(cx, cy, "x", color="#6a4c93")
ax.set_xlabel("x（m）"); ax.set_ylabel("y（m）")
ax.set_title("三类位姿「8 个 yaw 全成功」交集（俯视，内部孤立失败点已填洞）", fontsize=11)
hl = [Patch(color=c, label=k + ("（空集）" if metrics["combos"][k]["n"] == 0 else "")) for k, c in layers]
hl += [plt.Line2D([], [], color="k", lw=1.5, label=f"推荐区以 (0,0) 为心内切圆 R={rec['R_center00']:.3f}"),
       plt.Line2D([], [], color="#6a4c93", lw=1.5, ls="-.", label=f"推荐区最优圆心 ({cx:+.3f},0) R={rec['R_best_y0']:.3f}"),
       Patch(fill=False, ec="#c1121f", ls="--", label="当前 xhard 采样框 ±0.14"),
       plt.Line2D([], [], marker="x", color="#9d0208", ls="", label="推荐区内部孤立失败点（已填洞，见报告）")]
ax.legend(handles=hl, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False)
for k, col in layers:
    rt = metrics["combos_filled"][k].get("r_theta", [])
    th = [int(e["theta"].strip("[)").split(",")[0]) + 5 for e in rt]
    ax2.plot(th, [e["r_max"] if e["r_max"] is not None else np.nan for e in rt], "-o", color=col if col != "#e0e0e0" else "#888", label=f"{k} r_max")
    ax2.plot(th, [e["r_min"] if e["r_min"] is not None else np.nan for e in rt], "--", color=col if col != "#e0e0e0" else "#888", alpha=0.7)
ax2.set_xlabel("以基座为原点的方位角 θ（度，0°=+x 朝桌面中心）")
ax2.set_ylabel("离基座距离 r（m）；实线 r_max，虚线 r_min")
ax2.set_title("交集区域的 r_max(θ) / r_min(θ)（10° 分箱；|θ|>40° 处受扫描域 y=±0.4 截断）", fontsize=10)
ax2.axhline(0.615, color="k", lw=0.8, ls=":")
ax2.text(-68, 0.622, "桌面中心 (0,0) 与基座的距离 0.615", fontsize=8)
ax2.grid(alpha=0.3)
ax2.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=1, frameon=False)
fig.suptitle("MoveCube：全 yaw 可达包络（网格步长 0.025 m，扫描域 x∈[-0.40,0.35]，y∈[-0.40,0.40]）", fontsize=13)
fig.tight_layout(rect=[0, 0, 1, 0.95])
fig.savefig(f"{D}/reach_envelope.png", dpi=110)
print("ANALYZE_DONE")
