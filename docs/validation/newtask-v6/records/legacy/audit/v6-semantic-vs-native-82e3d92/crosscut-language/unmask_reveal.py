"""只读：Unmask 四环境执行段，每次「pick up the container ... hides the X cube」之后，
在容器被抬起时（下一边界或末帧）于原抓取像素附近统计纯红/绿/蓝像素，判断露出的方块颜色是否与子目标一致。"""
import json, re, os, h5py, numpy as np, cv2
HERE = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/crosscut-language"
R = json.load(open(os.path.join(HERE, "records.json")))
os.makedirs(os.path.join(HERE, "unmask_png"), exist_ok=True)
def classify(img, r, c, h=22):
    r0, r1, c0, c1 = max(0, r - h), min(256, r + h), max(0, c - h), min(256, c + h)
    p = img[r0:r1, c0:c1].astype(int)
    R_, G, B = p[..., 0], p[..., 1], p[..., 2]
    cnt = {"red": int(((R_ > 140) & (G < 70) & (B < 70)).sum()),
           "green": int(((G > 120) & (R_ < 90) & (B < 90)).sum()),
           "blue": int(((B > 120) & (R_ < 70) & (G < 90)).sum())}
    return cnt, (r0, r1, c0, c1)
out = []
for rec in R:
    if rec["task"] not in ("VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap"):
        continue
    f = h5py.File(rec["h5"], "r"); g = f[[k for k in f if k.startswith("episode_")][0]]
    ex = [b for b in rec["boundaries"] if not b["demo"]]
    for i, b in enumerate(ex):
        m = re.match(r"pick up the container at <(\d+), (\d+)> that hides the (\w+) cube", b["grounded"])
        if not m and "hides the" in b["grounded"]:
            # 无坐标时用 choice point
            ch = json.loads(b.get("choice") or "{}"); pt = ch.get("point") or []
            if len(pt) == 2:
                m = (None, pt[0], pt[1], re.search(r"hides the (\w+) cube", b["grounded"]).group(1))
        if not m:
            continue
        r_, c_, col = int(m[1]), int(m[2]), m[3]
        if b["simple"] == "All tasks completed" or (i > 0 and ex[i - 1]["simple"] == b["simple"]):
            continue  # 终止帧重复
        nxt = [x["t"] for x in ex[i + 1:] if x["simple"] != b["simple"]]
        t_obs = (nxt[0] - 1) if nxt else rec["n_steps"] - 1
        img = g[f"timestep_{t_obs}"]["obs"]["front_rgb"][()]
        cnt, box = classify(img, r_, c_)
        seen = max(cnt, key=cnt.get) if max(cnt.values()) >= 8 else None
        ok = seen == col
        tag = f"{rec['task']}_{rec['difficulty']}_ep{rec['episode']}_t{t_obs}_{col}"
        if not ok:
            big = cv2.resize(img, (512, 512), interpolation=cv2.INTER_NEAREST)
            cv2.rectangle(big, (box[2] * 2, box[0] * 2), (box[3] * 2, box[1] * 2), (255, 255, 255), 1)
            cv2.imwrite(os.path.join(HERE, "unmask_png", tag + ".png"), cv2.cvtColor(big, cv2.COLOR_RGB2BGR))
        out.append(dict(task=rec["task"], difficulty=rec["difficulty"], episode=rec["episode"], kind=rec["kind"], t_pick=b["t"], t_obs=t_obs,
                        rc=[r_, c_], subgoal_color=col, pixel_counts=cnt, seen=seen, ok=ok))
json.dump(out, open(os.path.join(HERE, "unmask_reveal.json"), "w"), indent=1)
import collections
print(collections.Counter((o["kind"], o["ok"]) for o in out))
for o in out:
    if not o["ok"]: print(o)
