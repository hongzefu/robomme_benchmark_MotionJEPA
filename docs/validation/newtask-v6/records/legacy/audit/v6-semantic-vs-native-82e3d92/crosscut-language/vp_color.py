"""只读：VPB/VPO 执行段首个 pick 起始帧，在抓取点附近判方块颜色，核对与语言目标里的 {color} cube 一致；并记录演示段首个 pick 的颜色。"""
import json, re, os, h5py, numpy as np, cv2, collections
HERE = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/crosscut-language"
R = json.load(open(os.path.join(HERE, "records.json")))
HUE = {"red": [(0, 8), (172, 180)], "green": [(50, 70)], "blue": [(110, 130)]}
def dominant(img, r, c, h=6):
    p = img[max(0, r - h):r + h + 1, max(0, c - h):c + h + 1]
    hsv = cv2.cvtColor(p.astype(np.uint8), cv2.COLOR_RGB2HSV).reshape(-1, 3)
    sat = hsv[(hsv[:, 1] > 120) & (hsv[:, 2] > 60)]
    return {k: int(sum(((sat[:, 0] >= lo) & (sat[:, 0] <= hi)).sum() for lo, hi in rng)) for k, rng in HUE.items()}
out = []
for rec in R:
    if rec["task"] not in ("VideoPlaceButton", "VideoPlaceOrder"):
        continue
    goal_col = re.search(r"place the (\w+) cube", rec["setup"]["task_goal"][0]).group(1)
    f = h5py.File(rec["h5"], "r"); g = f[[k for k in f if k.startswith("episode_")][0]]
    picks = []
    for b in rec["boundaries"]:
        m = re.match(r"pick up the cube at <(\d+), (\d+)>", b["grounded"])
        if m and b["simple"] != "All tasks completed":
            img = g[f"timestep_{b['t']}"]["obs"]["front_rgb"][()]
            cnt = dominant(img, int(m.group(1)), int(m.group(2)))
            picks.append(dict(t=b["t"], demo=b["demo"], rc=[int(m.group(1)), int(m.group(2))], seen=max(cnt, key=cnt.get) if max(cnt.values()) >= 5 else None, counts=cnt))
    ex = [p for p in picks if not p["demo"]]
    out.append(dict(task=rec["task"], difficulty=rec["difficulty"], episode=rec["episode"], kind=rec["kind"], goal_color=goal_col,
                    exec_pick_color=ex[0]["seen"] if ex else None, demo_pick_colors=[p["seen"] for p in picks if p["demo"]],
                    ok=bool(ex) and ex[0]["seen"] == goal_col))
json.dump(out, open(os.path.join(HERE, "vp_color.json"), "w"), indent=1)
print(collections.Counter((o["task"], o["kind"], o["ok"]) for o in out))
for o in out: print(o["task"], o["difficulty"], o["episode"], o["goal_color"], o["exec_pick_color"], o["demo_pick_colors"])
