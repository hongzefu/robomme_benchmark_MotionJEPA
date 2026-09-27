# 步 1：复刻判据核对 + 区域内实际范围（源码公式 vs specs.jsonl 10 条候选）
import sys, json, math
import numpy as np
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S); sys.path.insert(0, "src")
import ringlib as L
from robomme.robomme_env.utils import unmask_distractors as ud
from robomme.robomme_env.utils import unmask_swap_xhard as ux

# (a) 可见性复刻核对
half, reach, height = ud.bin_geometry(0.02)
print("bin_geometry:", half, reach, height, "swap radius", ux.bin_footprint_radius(0.02))
rng = np.random.default_rng(0)
pts = rng.uniform([-0.8, -0.9], [0.5, 0.9], (20000, 2))
ref = np.array([ud.visible_in_camera(ud.bin_corners(x, y, reach, height)) for x, y in pts])
mine = L.vis_center_exact(pts[:, 0], pts[:, 1])
print("vis exact mismatch:", int((ref != mine).sum()), "/", len(pts))
ref2 = np.array([ux.visible_on_camera(x, y, ux.bin_footprint_radius(0.02)) for x, y in pts])
mine2 = L.vis_center_swap(pts[:, 0], pts[:, 1])
print("vis swap mismatch:", int((ref2 != mine2).sum()))
# 两个可见判据之间的差异（在中心坐标上）
both = ref & ref2; only_exact = ref & ~ref2; only_swap = ~ref & ref2
print("exact-visible", int(ref.sum()), "swap-visible", int(ref2.sum()), "only_exact", int(only_exact.sum()), "only_swap", int(only_swap.sum()))

# (b) specs.jsonl 统计
rows = [json.loads(l) for l in open("scripts/configs/newtask-v4/v4-01/specs.jsonl")][1:]
out = {}
for t in ["VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap"]:
    rr = [r for r in rows if r["task"] == t]
    B, D, btn = [], [], []
    ncube = []
    for r in rr:
        s = r["spec"]
        bins = s["layout"]["bins"]
        B += [v[:2] for v in bins.values()]
        if t in ("VideoUnmask", "ButtonUnmask"):
            D += [v[:2] for v in s["objects"]["distractors"]["bins"].values()]
            ncube.append(s["objects"]["distractors"]["cube_count"])
        else:
            D += [v[:2] for v in s["layout"]["distractors"].values()]
            ncube.append(s["objects"]["distractors"]["n_with_cube"])
        if "button_xy" in s["layout"]:
            btn.append(s["layout"]["button_xy"])
    B = np.array(B); D = np.array(D)
    print(f"\n{t}: {len(rr)} rows; inner bins {len(B)}; distractors {len(D)}; cube counts {ncube}")
    print("  inner centers x[min,max]=", np.round([B[:,0].min(), B[:,0].max()], 4), " y=", np.round([B[:,1].min(), B[:,1].max()], 4),
          " max|.|∞=", round(float(np.max(np.abs(B))), 4), " max r=", round(float(np.max(np.linalg.norm(B, axis=1))), 4))
    print("  distractor max(|x|,|y|) range:", np.round([np.max(np.abs(D), 1).min(), np.max(np.abs(D), 1).max()], 4),
          " x range", np.round([D[:,0].min(), D[:,0].max()], 3), " y range", np.round([D[:,1].min(), D[:,1].max()], 3))
    # 距离最近的内容器中心距离
    dmin = [float(np.min(np.linalg.norm(B - d, axis=1))) for d in D]
    print("  distractor→nearest inner-bin center dist: min", round(min(dmin), 4), "median", round(float(np.median(dmin)), 4), "max", round(max(dmin), 4))
    if btn:
        btn = np.array(btn); print("  button_xy x", np.round([btn[:,0].min(), btn[:,0].max()], 3), "y", np.round([btn[:,1].min(), btn[:,1].max()], 3))
    out[t] = dict(inner=B.tolist(), distractors=D.tolist())
json.dump(out, open(f"{S}/specs_positions.json", "w"))

# (c) 源码公式给出的包络（Monte Carlo 10 万次抽内层参数）
rng = np.random.default_rng(1)
# VideoUnmaskSwap：center = R(θ)a + u, u∈[-0.0425,0.0425]^2
ang = rng.random(200000) * 180.0
a = L.VUS_REGION4[rng.integers(0, 4, 200000)]
c, s_ = np.cos(ang), np.sin(ang)
rx = a[:, 0] * c - a[:, 1] * s_; ry = a[:, 0] * s_ + a[:, 1] * c
u = rng.uniform(-0.0425, 0.0425, (200000, 2))
cx, cy = rx + u[:, 0], ry + u[:, 1]
print("\nVUS formula envelope: max|x|", round(float(np.abs(cx).max()), 4), " max r", round(float(np.hypot(cx, cy).max()), 4),
      " anchor radii", np.round(np.linalg.norm(L.VUS_REGION4, axis=1), 4))
# ButtonUnmaskSwap：four_point + y 偏移
print("BUS formula: centers x∈[-0.0425,0.1425], y∈[-0.1425,0.2425]; buttons x∈[-0.225,-0.175]±0.0375, y∈±[0.075,0.125]±0.0375")
