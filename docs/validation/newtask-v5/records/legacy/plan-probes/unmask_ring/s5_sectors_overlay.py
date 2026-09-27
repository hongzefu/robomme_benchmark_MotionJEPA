# 步 5：环带各扇区的可见比例 + 把环带边界投到 V4 rollout 帧上（俯视图 + 相机视角叠加）
import sys, json, math, glob
import numpy as np, h5py
from PIL import Image, ImageDraw
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S)
import ringlib as L
STEP = 0.002
XS = np.arange(-0.9 + STEP / 2, 0.6, STEP); YS = np.arange(-0.9 + STEP / 2, 0.9, STEP)
X, Y = np.meshgrid(XS, YS, indexing="ij")
VIS = L.vis_center_exact(X, Y)
rings = {
    "VU/BU A [0.2425,0.3289]": L.RectRing((-0.2, 0.2, -0.2, 0.2), 0.0425, 0.1289),
    "VU/BU C [0.2675,0.3539]": L.RectRing((-0.2, 0.2, -0.2, 0.2), 0.0675, 0.1539),
    "VUS A (sq 0.2114)": L.RectRing((-0.2114, 0.2114, -0.2114, 0.2114), 0.0425, 0.1289),
    "BUS A +btn rect": L.RectRing((-0.2625, 0.17, -0.17, 0.27), 0.0425, 0.1289),
    "V4 [0.2675,0.45]": L.RectRing((0, 0, 0, 0), 0.2675, 0.45),
}
for name, ring in rings.items():
    m = ring.contains(X, Y)
    x0, x1, y0, y1 = ring.inner
    sec = {
        "far side (-x, image top)": m & (X < x0) & (Y >= y0) & (Y <= y1),
        "near side (+x, image bottom)": m & (X > x1) & (Y >= y0) & (Y <= y1),
        "left side (-y)": m & (Y < y0) & (X >= x0) & (X <= x1),
        "right side (+y)": m & (Y > y1) & (X >= x0) & (X <= x1),
        "far corners": m & (X < x0) & ((Y < y0) | (Y > y1)),
        "near corners": m & (X > x1) & ((Y < y0) | (Y > y1)),
    }
    parts = [f"{k}: {100*(v & VIS).sum()/max(v.sum(),1):.0f}%" for k, v in sec.items()]
    print(f"{name}: 中心带总可见 {100*(m & VIS).sum()/m.sum():.1f}% | " + "; ".join(parts))

# 相机视角叠加：环带中心带内、外边界（z=0）投到 VideoUnmask ep0 t63 帧
def ring_outline(ring, d):
    x0, x1, y0, y1 = ring.inner
    pts = [(x0 - d, y0 - d), (x0 - d, y1 + d), (x1 + d, y1 + d), (x1 + d, y0 - d), (x0 - d, y0 - d)]
    out = []
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        for s in np.linspace(0, 1, 60):
            out.append([ax + (bx - ax) * s, ay + (by - ay) * s, 0.0])
    return np.array(out)
for env, ring_names in [("VideoUnmask", ["VU/BU A [0.2425,0.3289]", "V4 [0.2675,0.45]"]), ("ButtonUnmaskSwap", ["BUS A +btn rect", "V4 [0.2675,0.45]"]),
                        ("VideoUnmaskSwap", ["VUS A (sq 0.2114)", "V4 [0.2675,0.45]"]), ("ButtonUnmask", ["VU/BU A [0.2425,0.3289]", "V4 [0.2675,0.45]"])]:
    fn = glob.glob(f"artifacts/newtask-v4/v4-01/rollout/run1/episodes/{env}_episode_0/hdf5_files/*.h5")[0]
    e = h5py.File(fn, "r")["episode_0"]
    img = Image.fromarray(e["timestep_63/obs/front_rgb"][()]).resize((768, 768), Image.BILINEAR)
    d = ImageDraw.Draw(img)
    colors = [(0, 255, 0), (255, 255, 0)]
    for rn, col in zip(ring_names, colors):
        ring = rings[rn]
        for dd in (ring.d_in, ring.d_out):
            u, v, _ = L.project(ring_outline(ring, dd))
            pts = [(3 * a, 3 * b) for a, b in zip(u, v)]
            d.line(pts, fill=col, width=2)
    img.save(f"{S}/overlay_{env}.png")
print("overlays saved")
