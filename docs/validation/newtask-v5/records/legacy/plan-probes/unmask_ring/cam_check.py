import h5py, numpy as np, json, glob
from PIL import Image
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
import sys
sys.path.insert(0, "src")
from robomme.robomme_env.utils.unmask_distractors import visible_in_camera, _camera_axes
base = "artifacts/newtask-v4/v4-01/rollout/run1/episodes"
for env in ["VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap"]:
    fn = glob.glob(f"{base}/{env}_episode_0/hdf5_files/*.h5")[0]
    f = h5py.File(fn, "r")
    ep = f["episode_0"]
    K = ep["setup/front_camera_intrinsic"][()]
    E = ep["timestep_0/obs/front_camera_extrinsic"][()]
    print(env, "K=", np.round(K, 3).tolist())
    print("  E=", np.round(E, 4).tolist())
    ts = sorted([k for k in ep.keys() if k.startswith("timestep_")], key=lambda s: int(s.split("_")[1]))
    demo = [bool(ep[t]["info/is_video_demo"][()]) for t in ts]
    print("  n_ts", len(ts), "n_demo", sum(demo))
    for i in [0, 20, 40, 63]:
        if i < len(ts):
            Image.fromarray(ep[ts[i]]["obs/front_rgb"][()]).save(f"{S}/{env}_ep0_t{i}.png")
    # project a few points with K,E
    def proj(p):
        pc = E[:, :3] @ np.asarray(p) + E[:, 3]
        uv = K @ pc
        return uv[:2] / uv[2], pc[2]
    for p in [(0, 0, 0), (0.43, 0, 0), (-0.45, 0.45, 0), (-0.72, 0, 0), (0.3, 0.3, 0)]:
        print("  proj", p, [np.round(x, 2).tolist() for x in proj(p)])
