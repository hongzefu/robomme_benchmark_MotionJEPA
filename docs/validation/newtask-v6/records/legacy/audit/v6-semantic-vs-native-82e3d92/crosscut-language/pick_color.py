"""只读：子目标「pick up the ... COL cube at <r, c>」起始帧，在 <r,c> 附近按 HSV 色相判断方块颜色，核对与子目标颜色词一致。"""
import json, re, os, h5py, numpy as np, cv2, collections
HERE = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/crosscut-language"
R = json.load(open(os.path.join(HERE, "records.json")))
os.makedirs(os.path.join(HERE, "pick_color_png"), exist_ok=True)
HUE = {"red": [(0, 8), (172, 180)], "yellow": [(22, 38)], "green": [(50, 70)], "cyan": [(80, 100)], "blue": [(110, 130)], "magenta": [(140, 160)]}
def dominant(img, r, c, h=6):
    p = img[max(0, r - h):r + h + 1, max(0, c - h):c + h + 1]
    hsv = cv2.cvtColor(p.astype(np.uint8), cv2.COLOR_RGB2HSV).reshape(-1, 3)
    sat = hsv[(hsv[:, 1] > 120) & (hsv[:, 2] > 60)]
    cnt = {k: int(sum(((sat[:, 0] >= lo) & (sat[:, 0] <= hi)).sum() for lo, hi in rng)) for k, rng in HUE.items()}
    return cnt
out = []
for rec in R:
    if rec["task"] not in ("BinFill", "PickXtimes", "SwingXtimes"):
        continue
    f = h5py.File(rec["h5"], "r"); g = f[[k for k in f if k.startswith("episode_")][0]]
    for b in rec["boundaries"]:
        if b["simple"] == "All tasks completed":
            continue
        m = re.match(r"pick up the (?:\w+ )?(red|blue|green) cube at <(\d+), (\d+)>", b["grounded"])
        if not m:
            continue
        col, r_, c_ = m.group(1), int(m.group(2)), int(m.group(3))
        img = g[f"timestep_{b['t']}"]["obs"]["front_rgb"][()]
        cnt = dominant(img, r_, c_)
        seen = max(cnt, key=cnt.get) if max(cnt.values()) >= 5 else None
        ok = seen == col
        if not ok:
            big = cv2.resize(img, (512, 512), interpolation=cv2.INTER_NEAREST)
            cv2.circle(big, (c_ * 2, r_ * 2), 14, (255, 255, 255), 1)
            cv2.imwrite(os.path.join(HERE, "pick_color_png", f"{rec['task']}_{rec['difficulty']}_ep{rec['episode']}_t{b['t']}_{col}.png"), cv2.cvtColor(big, cv2.COLOR_RGB2BGR))
        out.append(dict(task=rec["task"], difficulty=rec["difficulty"], episode=rec["episode"], kind=rec["kind"], t=b["t"], rc=[r_, c_], subgoal=b["grounded"], counts=cnt, seen=seen, ok=ok))
json.dump(out, open(os.path.join(HERE, "pick_color.json"), "w"), indent=1)
print(collections.Counter((o["task"], o["kind"], o["ok"]) for o in out))
for o in out:
    if not o["ok"]: print(o["task"], o["difficulty"], o["episode"], o["t"], o["subgoal"], o["counts"])
