# 抽查：V4 PatternLock / RouteStick 六局 h5 的 demo 帧数（is_video_demo 计数）
import glob, h5py, numpy as np
base = "artifacts/newtask-v4/v4-01/rollout/run1/episodes"
for env in ("PatternLock", "RouteStick"):
    for ep in (0, 3, 6):
        fs = glob.glob(f"{base}/{env}_episode_{ep}/hdf5_files/*.h5")
        with h5py.File(fs[0], "r") as f:
            root = f[list(f.keys())[0]]
            steps = [k for k in root.keys() if k.startswith("timestep_")]
            demo = 0
            for k in steps:
                g = root[k]
                if "info" in g and "is_video_demo" in g["info"]:
                    demo += int(np.asarray(g["info"]["is_video_demo"][()]).reshape(-1)[0])
            print(env, ep, "total", len(steps), "demo", demo, f"{demo/30:.2f}s")
