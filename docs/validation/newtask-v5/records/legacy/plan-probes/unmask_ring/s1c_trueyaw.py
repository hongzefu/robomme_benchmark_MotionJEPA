# 用真实 yaw 与真实外廓（半边 0.03、高 0.054）算 V4 Swap 干扰容器在 256×256 画面里的越界像素，并在 rollout 帧上核对
import sys, json, math, glob
import numpy as np, h5py
from PIL import Image, ImageDraw
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, S)
import ringlib as L
rows = [json.loads(l) for l in open("scripts/configs/newtask-v4/v4-01/specs.jsonl")][1:]
def corners(x, y, yaw_deg, h=0.03, H=L.HEIGHT):
    R = L.rot(math.radians(yaw_deg))
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            off = R @ np.array([sx * h, sy * h])
            for z in (0, H):
                pts.append([x + off[0], y + off[1], z])
    return np.array(pts)
for t in ["VideoUnmaskSwap", "ButtonUnmaskSwap"]:
    for r in [r for r in rows if r["task"] == t]:
        ep = r["episode"]; sel = r["selected"]
        for k, v in r["spec"]["layout"]["distractors"].items():
            u, vv, _ = L.project(corners(*v))
            over = max(-u.min(), u.max() - 255, -vv.min(), vv.max() - 255)
            if over > 0:
                frac_out = None
                print(f"{t} ep{ep} sel={sel} distractor {k} xy=({v[0]:.3f},{v[1]:.3f}) yaw={v[2]:.1f} true overshoot={over:.1f}px  u=[{u.min():.1f},{u.max():.1f}] v=[{vv.min():.1f},{vv.max():.1f}]")
                fn = glob.glob(f"artifacts/newtask-v4/v4-01/rollout/run1/episodes/{t}_episode_{ep}/hdf5_files/*.h5")
                if fn:
                    f = h5py.File(fn[0], "r"); e = f["episode_0"]
                    img = Image.fromarray(e["timestep_63/obs/front_rgb"][()]).resize((512, 512), Image.NEAREST)
                    d = ImageDraw.Draw(img)
                    d.rectangle([2 * max(u.min(), 0), 2 * max(vv.min(), 0), 2 * min(u.max(), 255), 2 * min(vv.max(), 255)], outline=(0, 255, 0))
                    img.save(f"{S}/{t}_ep{ep}_d{k}_t63.png"); print("   saved frame", f"{S}/{t}_ep{ep}_d{k}_t63.png")
