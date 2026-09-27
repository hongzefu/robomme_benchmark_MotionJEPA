"""只读：逐步读 VideoRepick 演示段 front_rgb 与子目标，统计交换运动窗口数。"""
import h5py, numpy as np, json, sys
out = {}
for h5 in sys.argv[1:]:
    f = h5py.File(h5, "r"); g = f[[k for k in f if k.startswith("episode_")][0]]
    n = len([k for k in g if k.startswith("timestep_")])
    prev = None; diffs = []; subs = []; bnd = []
    for t in range(n):
        s = g[f"timestep_{t}"]
        if not bool(s["info/is_video_demo"][()]):
            break
        img = s["obs/front_rgb"][()].astype(np.int16)
        diffs.append(0.0 if prev is None else float(np.abs(img - prev).mean()))
        prev = img
        subs.append(s["info/simple_subgoal"][()].decode())
        bnd.append(bool(s["info/is_subgoal_boundary"][()]))
    d = np.array(diffs)
    # 从第一个 static 起统计运动窗口
    first_static = subs.index("static")
    moving = d > 0.05
    wins = []; cur = None
    for t in range(first_static, len(d)):
        if moving[t] and cur is None: cur = t
        if not moving[t] and cur is not None:
            if t - cur >= 5: wins.append((cur, t))
            cur = None
    if cur is not None: wins.append((cur, len(d)))
    out[h5.split("/")[-1]] = dict(demo_len=len(d), first_static=first_static, static_boundaries=[t for t in range(len(d)) if bnd[t] and subs[t] == "static"],
                                  motion_windows=wins, n_windows=len(wins), last_diff_tail=[round(x, 3) for x in d[-12:]])
    print(json.dumps(out[h5.split("/")[-1]]))
import os; json.dump(out, open(os.environ.get("OUT", "/dev/null"), "w"), indent=1)
