# 只读：v5-01 三局 VideoRepick h5 的逐子目标帧数统计（is_video_demo 段 / 非演示段 / 每子目标段）
import h5py, numpy as np, glob, json, itertools
out = {}
for p in sorted(glob.glob("artifacts/newtask-v5/v5-01/rollout/run1/episodes/VideoRepick_episode_*/hdf5_files/*.h5")):
    epdir = p.split("/hdf5_files")[0]
    spec = json.load(open(epdir + "/spec_replay.json"))
    with h5py.File(p, "r") as f:
        ep = f[list(f.keys())[0]]
        tks = sorted([k for k in ep.keys() if k.startswith("timestep_")], key=lambda k: int(k.split("_")[1]))
        demo = np.array([bool(ep[k]["info"]["is_video_demo"][()]) for k in tks])
        sub = [ep[k]["info"]["simple_subgoal"][()] for k in tks]
        sub = [s.decode() if isinstance(s, bytes) else str(s) for s in sub]
    segs = [(k, len(list(g))) for k, g in itertools.groupby(sub)]
    out[p] = dict(total=len(tks), demo=int(demo.sum()), nondemo=int((~demo).sum()), segs=segs)
    print(p.split("/")[-1], "总帧", len(tks), "演示帧", int(demo.sum()), "非演示帧", int((~demo).sum()))
    print("  spec keys:", list(spec.keys())[:10])
    for s in segs: print("   ", s)
json.dump(out, open("artifacts/newtask-v6/plan-probes/videorepick/h5_frames.json", "w"), ensure_ascii=False, indent=1)
