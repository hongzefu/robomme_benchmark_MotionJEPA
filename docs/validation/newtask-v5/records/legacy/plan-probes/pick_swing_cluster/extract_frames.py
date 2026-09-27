"""从 rollout h5 取首帧 front_rgb（以及 wrist 等其他相机若存在）保存 PNG。"""
import h5py, numpy as np, sys, glob, os
from PIL import Image
OUT=sys.argv[1]
base="/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/v4-01/rollout/run1/episodes"
for env in ["PickXtimes","SwingXtimes"]:
    for ep in [0,3,6]:
        f=glob.glob(f"{base}/{env}_episode_{ep}/hdf5_files/*.h5")[0]
        with h5py.File(f,"r") as h:
            g=h[list(h.keys())[0]]
            ts=sorted([k for k in g.keys() if k.startswith("timestep_")], key=lambda s:int(s.split("_")[1]))
            if env=="PickXtimes" and ep==3:
                print("n timesteps",len(ts)); print("obs keys", list(g[ts[0]]["obs"].keys())); print("info keys", list(g[ts[0]]["info"].keys()))
            img=np.array(g[ts[0]]["obs"]["front_rgb"])
            if img.ndim==4: img=img[0]
            Image.fromarray(img.astype(np.uint8)).resize((768,768), Image.NEAREST).save(f"{OUT}/{env}_ep{ep}_frame0.png")
            print(env,ep,img.shape)
