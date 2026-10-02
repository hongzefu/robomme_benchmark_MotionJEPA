"""V9 MoveCube xhard4 区域示意图（1002 V9 计划第一部分 §2）：按 MoveCube.py 的拒绝规则离线模拟，纯 numpy、不 reset 环境。

用法：uv run --no-sync python scripts/injection-dev/v9_movecube_region_fig.py docs/validation/newtask-v9/figures/movecube_v9_region.png
"""
import json, sys
import h5py, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
plt.rcParams["font.family"] = "Noto Sans CJK JP"
OUT = sys.argv[1]
BASE = np.array([-0.615, 0.0]); L = 0.10; EXT = (-0.15, 0.05)
CUR = dict(name="现行 V8", center=(-0.06, 0.0), r_in=0.12, r_out=0.20, base=(0.35, 0.76))
V9 = dict(name="V9", center=(-0.06, 0.0), r_in=0.24, r_out=0.42, base=(0.31, 0.80))
COMMON = dict(push_max=0.30, min_cg=0.10, peg_gap=0.04, goal_peg_gap=0.02, backoff=0.10, lateral=0.10,
              peg_max=128, goal_max=256, cube_max=4096)

def segd(p, a, b):
    ab = b - a; t = np.clip(np.dot(p - a, ab) / np.dot(ab, ab), 0, 1); return np.linalg.norm(p - (a + t * ab))

def in_u(p, R):
    rc = np.linalg.norm(p - R["center"]); rb = np.linalg.norm(p - BASE)
    return R["r_in"] <= rc <= R["r_out"] and R["base"][0] <= rb <= R["base"][1]

def draw_sq(rng, R):
    c = np.asarray(R["center"]); return c + (rng.random(2) * 2 - 1) * R["r_out"]

def episode(rng, R):
    C = COMMON; c = np.asarray(R["center"])
    for tp in range(1, C["peg_max"] + 1):  # 杆：抓取点 + yaw
        g = draw_sq(rng, R); yaw = rng.random() * 2 * np.pi - np.pi
        u = np.array([np.cos(yaw), np.sin(yaw)]); root = g + L * u
        a, b = root + EXT[0] * u, root + EXT[1] * u
        if in_u(g, R) and segd(c, a, b) >= R["r_in"]:
            break
    else:
        return None, "peg"
    for tg in range(1, C["goal_max"] + 1):
        q = draw_sq(rng, R)
        if in_u(q, R) and segd(q, a, b) >= C["goal_peg_gap"]:
            break
    else:
        return None, "goal"
    for tc in range(1, C["cube_max"] + 1):
        p = draw_sq(rng, R)
        if not (in_u(p, R) and segd(p, a, b) >= C["peg_gap"]):
            continue
        d = q - p; n = np.linalg.norm(d)
        if not (C["min_cg"] <= n <= C["push_max"]):
            continue
        d = d / n; lat = np.array([-d[1], d[0]])
        if all(R["base"][0] <= np.linalg.norm(p - C["backoff"] * d - s * C["lateral"] * lat - BASE) <= R["base"][1]
               for s in (0, 1, -1)):
            break
    else:
        return None, "cube"
    return dict(g=g, root=root, yaw=yaw, goal=q, cube=p, push=n, tp=tp, tg=tg, tc=tc), None

def run(R, n=2000, seed=0):
    rng = np.random.default_rng(seed); eps, fails = [], {"peg": 0, "goal": 0, "cube": 0}
    for _ in range(n):
        e, f = episode(rng, R)
        (eps.append(e) if e else fails.__setitem__(f, fails[f] + 1))
    return eps, fails

def area(R):
    xs, ys = np.meshgrid(np.linspace(-0.6, 0.5, 1100), np.linspace(-0.55, 0.55, 1100))
    rc = np.hypot(xs - R["center"][0], ys - R["center"][1]); rb = np.hypot(xs - BASE[0], ys - BASE[1])
    m = (rc >= R["r_in"]) & (rc <= R["r_out"]) & (rb >= R["base"][0]) & (rb <= R["base"][1])
    return m.sum() * (1.1 / 1099) ** 2

stats = {}
res = {}
for R in (CUR, V9):
    eps, fails = run(R)
    res[R["name"]] = eps
    tc = np.array([e["tc"] for e in eps]); tp = np.array([e["tp"] for e in eps]); tg = np.array([e["tg"] for e in eps])
    cy = np.abs(np.array([e["cube"][1] for e in eps])); push = np.array([e["push"] for e in eps])
    same = np.mean([np.sign(e["cube"][1]) == np.sign(e["goal"][1]) for e in eps])
    stats[R["name"]] = dict(area_m2=round(area(R), 4), ok=len(eps), fails=fails,
                            peg_trials_mean=round(tp.mean(), 2), goal_trials_mean=round(tg.mean(), 2),
                            cube_trials_mean=round(tc.mean(), 1), cube_trials_p99=int(np.percentile(tc, 99)),
                            cube_trials_max=int(tc.max()), cube_absy_max=round(cy.max(), 3),
                            push_mean=round(push.mean(), 3), cube_goal_same_side=round(same, 3),
                            grasp_base_max=round(max(np.linalg.norm(e["g"] - BASE) for e in eps), 3),
                            grasp_base_min=round(min(np.linalg.norm(e["g"] - BASE) for e in eps), 3))
print(json.dumps(stats, ensure_ascii=False, indent=1))

# ── 图 ──
xs, ys = np.meshgrid(np.linspace(-0.8, 0.5, 1300), np.linspace(-0.85, 0.85, 1700))
dB = np.hypot(xs - BASE[0], ys - BASE[1])
reach = (dB >= .31) & (dB <= .80) & (xs >= BASE[0])
def ring(R):
    dc = np.hypot(xs - R["center"][0], ys - R["center"][1]); return (dc >= R["r_in"]) & (dc <= R["r_out"])
cur = ring(CUR) & (dB >= .35) & (dB <= .76)
v9ring = ring(V9); v9 = v9ring & reach; v9out = v9ring & ~reach

h = h5py.File("artifacts/newtask-v8/gen1/shard1/episodes/xhard4/MoveCube_episode_21/hdf5_files/MoveCube_ep21_seed23402100.h5")
e = h[list(h.keys())[0]]
K = e["setup/front_camera_intrinsic"][()]; E = e["timestep_0/obs/front_camera_extrinsic"][()]; img = e["timestep_0/obs/front_rgb"][()]
K = K.reshape(3, 3); E = E.reshape(-1, 4)[:3]
def proj(pts):
    P = np.c_[pts, np.zeros(len(pts)), np.ones(len(pts))] @ E.T; uv = P @ K.T; return uv[:, 0] / uv[:, 2], uv[:, 1] / uv[:, 2]
H, W = img.shape[:2]

fig = plt.figure(figsize=(18, 13), dpi=120)
gs = fig.add_gridspec(2, 3, height_ratios=[1, 0.9])
COL = dict(reach="#9ecae1", cur="#fd8d3c", v9="#fdd0a2", out="#d94801")
def regions(a):
    for m, c, al in ((reach, COL["reach"], .45), (v9out, COL["out"], .55), (v9, COL["v9"], .9)):
        a.contourf(xs, ys, m.astype(float), levels=[.5, 1.5], colors=[c], alpha=al)
    a.contour(xs, ys, cur.astype(float), levels=[.5], colors=COL["cur"], linewidths=2)
    a.plot(*BASE, "ks", ms=9); a.text(BASE[0] + .01, -.07, "基座", fontsize=10); a.plot(-.06, 0, "k+", ms=12)
    a.set_aspect("equal"); a.set_xlim(-.72, .45); a.set_ylim(-.6, .6); a.grid(alpha=.3); a.set_xlabel("x (m)"); a.set_ylabel("y (m)")

a = fig.add_subplot(gs[0, 0]); regions(a); a.set_title("① 区域俯视：可达环带 / 现行 U / V9")
a.legend(handles=[Patch(color=COL["reach"], label="Panda 可达环带 0.31–0.80 m（V6 实测）"),
                  Line2D([], [], color=COL["cur"], lw=2, label="现行 V8 区域 U：r 0.12–0.20 ∩ 0.35–0.76"),
                  Patch(color=COL["v9"], label="V9：r 0.24–0.42 ∩ 可达环带"),
                  Patch(color=COL["out"], label="V9 圆环中够不到、被切掉的部分")], loc="lower left", fontsize=8.5)

for j, (key, title) in enumerate((("现行 V8", "② 现行 V8 抽样 2000 段"), ("V9", "③ V9 抽样 2000 段"))):
    a = fig.add_subplot(gs[0, 1 + j]); regions(a); E9 = res[key][:600]
    a.scatter([e["g"][0] for e in E9], [e["g"][1] for e in E9], s=3, c="#6a51a3", label="杆抓取点")
    a.scatter([e["goal"][0] for e in E9], [e["goal"][1] for e in E9], s=3, c="#31a354", label="goal 中心")
    a.scatter([e["cube"][0] for e in E9], [e["cube"][1] for e in E9], s=3, c="#e31a1c", label="方块中心")
    a.set_title(f"{title}（散点画前 600 段）"); a.legend(loc="lower left", fontsize=8.5, markerscale=4)

b = fig.add_subplot(gs[1, 0:2]); b.imshow(img, extent=(0, W, H, 0))
pts = np.c_[xs.ravel(), ys.ravel()]; u, v = proj(pts)
def paint(m, c, al):
    g = np.zeros((H, W)); k = m.ravel() & (u >= 0) & (u < W) & (v >= 0) & (v < H); g[v[k].astype(int), u[k].astype(int)] = 1
    b.contourf(np.arange(W) + .5, np.arange(H) + .5, g, levels=[.5, 1.5], colors=[c], alpha=al)
paint(reach, "#3182bd", .22); paint(v9out, COL["out"], .5); paint(v9, COL["v9"], .7)
g = np.zeros((H, W)); k = cur.ravel() & (u >= 0) & (u < W) & (v >= 0) & (v < H); g[v[k].astype(int), u[k].astype(int)] = 1
b.contour(np.arange(W) + .5, np.arange(H) + .5, g, levels=[.5], colors=COL["cur"], linewidths=2)
E9 = res["V9"][:300]
for key, c in (("g", "#6a51a3"), ("goal", "#31a354"), ("cube", "#e31a1c")):
    uu, vv = proj(np.array([e[key] for e in E9])); b.scatter(uu, vv, s=4, c=c)
b.set_xlim(0, W); b.set_ylim(H, 0); b.axis("off"); b.set_title("④ 前置相机视角（V8 gen1 MoveCube xhard4 ep21 首帧，桌面 z=0 投影；点为 V9 抽样前 300 段）")

a = fig.add_subplot(gs[1, 2]); a.axis("off")
s0, s9 = stats["现行 V8"], stats["V9"]
rows = [("区域面积 m²", s0["area_m2"], s9["area_m2"]),
        ("2000 段生成成功", s0["ok"], s9["ok"]),
        ("方块平均尝试 / p99 / 最大", f'{s0["cube_trials_mean"]} / {s0["cube_trials_p99"]} / {s0["cube_trials_max"]}',
         f'{s9["cube_trials_mean"]} / {s9["cube_trials_p99"]} / {s9["cube_trials_max"]}'),
        ("杆 / goal 平均尝试", f'{s0["peg_trials_mean"]} / {s0["goal_trials_mean"]}', f'{s9["peg_trials_mean"]} / {s9["goal_trials_mean"]}'),
        ("方块 |y| 最大 m", s0["cube_absy_max"], s9["cube_absy_max"]),
        ("推距均值 m（上限 0.30）", s0["push_mean"], s9["push_mean"]),
        ("方块与 goal 同侧比例", s0["cube_goal_same_side"], s9["cube_goal_same_side"]),
        ("抓杆点离基座 最小–最大 m", f'{s0["grasp_base_min"]}–{s0["grasp_base_max"]}', f'{s9["grasp_base_min"]}–{s9["grasp_base_max"]}')]
t = a.table(cellText=[[r[0], r[1], r[2]] for r in rows], colLabels=["指标（离线 2000 段）", "现行 V8", "V9"],
            loc="upper center", cellLoc="left", colWidths=[.5, .25, .25])
t.auto_set_font_size(False); t.set_fontsize(10); t.scale(1, 1.9)
a.set_title("⑤ 离线抽样统计（规则与 MoveCube.py 相同）")
fig.suptitle("MoveCube xhard4 V9 生成区域：同一圆心 (−0.06, 0)，圆环 r 0.24–0.42 ∩ Panda 可达环带 0.31–0.80 m（其余规则不变）", fontsize=14)
fig.tight_layout(rect=(0, 0, 1, .97))
fig.savefig(OUT, bbox_inches="tight")
