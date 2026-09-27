"""只读：从 h5 统计 BinFill / PickXtimes / SwingXtimes / PickHighlight 的演示总帧数与逐子目标帧数。

口径：RecordWrapper 每次 step() 往 buffer 追加一条记录，h5 的 timestep_* 个数 ≈ env.elapsed_steps
（fail_safe_limit=5000 判的就是 elapsed_steps）。按 info/simple_subgoal 连续段切分，按首词归类。
输入：官方 h5（每环境 100 局，easy/medium/hard 混合）+ V5 v5-01 的 xhard 三局。
输出：<out>/<env>.json（逐局记录 + 逐类段长）。
"""
import glob, json, re, sys
from collections import defaultdict
import h5py
import numpy as np

OUT = "artifacts/newtask-v6/plan-probes/count-tasks/frames"
OFFICIAL = "/data/hongzefu/robomme_data_h5/record_dataset_{env}.h5"
V5 = "artifacts/newtask-v5/v5-01/rollout/run1/episodes/{env}_episode_*/hdf5_files/*.h5"


def cat_of(env, sg):
    s = sg.lower()
    if s.startswith("all tasks completed"):
        return "tail"
    if "press the button" in s:
        return "button"
    if s.startswith("pick up"):
        return "pick"
    if "into the bin" in s or "onto the target" in s:
        return "place"
    if "place the cube onto the table" in s:
        return "putback"
    if "right-side target" in s:
        return "swingR"
    if "left-side target" in s:
        return "swingL"
    if "on the table" in s:
        return "putdown"
    return "other:" + s[:40]


def episode_record(env, ep, src):
    ts = [k for k in ep.keys() if k.startswith("timestep_")]
    idx = sorted(ts, key=lambda k: (int(re.match(r"timestep_(\d+)", k).group(1)), k))
    segs = []
    prev, start = None, 0
    for i, k in enumerate(idx):
        sg = ep[k]["info/simple_subgoal"][()]
        sg = sg.decode() if isinstance(sg, bytes) else str(sg)
        if sg != prev:
            if prev is not None:
                segs.append((prev, i - start))
            prev, start = sg, i
    segs.append((prev, len(idx) - start))
    diff = ep["setup/difficulty"][()]
    diff = diff.decode() if isinstance(diff, bytes) else str(diff)
    goal = ep["setup/task_goal"][()]
    goal = [g.decode() if isinstance(g, bytes) else str(g) for g in np.atleast_1d(goal)]
    counts = defaultdict(int)
    lens = defaultdict(list)
    for sg, n in segs:
        c = cat_of(env, sg)
        counts[c] += 1
        lens[c].append(n)
    return {"src": src, "difficulty": diff, "seed": int(ep["setup/seed"][()]), "T": len(idx),
            "goal": goal[0], "counts": dict(counts), "lens": {k: v for k, v in lens.items()},
            "segs": segs}


def main(env):
    rows = []
    for p in sorted(glob.glob(V5.format(env=env))):
        with h5py.File(p, "r") as f:
            for ek in f.keys():
                rows.append(episode_record(env, f[ek], "v5-01"))
    with h5py.File(OFFICIAL.format(env=env), "r") as f:
        for ek in sorted(f.keys(), key=lambda s: int(s.split("_")[1])):
            rows.append(episode_record(env, f[ek], "official"))
    import os
    os.makedirs(OUT, exist_ok=True)
    json.dump(rows, open(f"{OUT}/{env}.json", "w"), ensure_ascii=False)
    print(env, "episodes", len(rows))


if __name__ == "__main__":
    main(sys.argv[1])
