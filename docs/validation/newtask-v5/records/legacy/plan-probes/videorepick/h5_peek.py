# 只读：列 h5 结构并导出若干帧 front_rgb 为 PNG
import h5py, sys, numpy as np
from PIL import Image
p, out_prefix = sys.argv[1], sys.argv[2]
with h5py.File(p, "r") as f:
    epk = list(f.keys())[0]
    ep = f[epk]
    tks = sorted([k for k in ep.keys() if k.startswith("timestep_")], key=lambda k: int(k.split("_")[1]))
    print("episode", epk, "n timesteps", len(tks))
    def walk(g, pre=""):
        for k in g.keys():
            o = g[k]
            if isinstance(o, h5py.Group):
                walk(o, pre + k + "/")
            else:
                print("  ", pre + k, o.shape, o.dtype)
    print("setup:"); walk(ep["setup"])
    print("timestep_0:"); walk(ep[tks[0]])
    demo = [int(np.asarray(ep[k]["info"]["is_video_demo"]).reshape(-1)[0]) if "is_video_demo" in ep[k]["info"] else -1 for k in tks]
    demo = np.array(demo)
    print("demo frames", int((demo == 1).sum()), "non-demo", int((demo == 0).sum()))
    idxs = [0] + [int(x) for x in sys.argv[3:]]
    for i in idxs:
        img = np.asarray(ep[tks[i]]["obs"]["front_rgb"])
        img = img.reshape(img.shape[-3:]) if img.ndim > 3 else img
        Image.fromarray(img.astype(np.uint8)).resize((512, 512), Image.NEAREST).save(f"{out_prefix}_t{i}.png")
        print("saved", f"{out_prefix}_t{i}.png", img.shape)
