"""独立复现 VideoPlaceButton-01：直接读原始 H5 subgoal 边界，不复用上一轮审查的 records.json。"""
import h5py, json

EPISODES = {
    "xhard3_ep0": "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01/xhard3/rollout/run1/episodes/VideoPlaceButton_episode_0/hdf5_files/VideoPlaceButton_ep0_seed13000001.h5",
    "xhard4_ep0": "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/VideoPlaceButton_episode_0/hdf5_files/VideoPlaceButton_ep0_seed7000000.h5",
    "xhard4_ep3": "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/VideoPlaceButton_episode_3/hdf5_files/VideoPlaceButton_ep3_seed7000302.h5",
}

out = {}
for tag, path in EPISODES.items():
    f = h5py.File(path, "r")
    epkey = [k for k in f.keys() if k.startswith("episode_")][0]
    g = f[epkey]
    n = sum(1 for k in g.keys() if k.startswith("timestep_"))
    boundaries = []
    for i in range(n):
        ts = g[f"timestep_{i}"]
        if bool(ts["info/is_subgoal_boundary"][()]):
            grounded = ts["info/grounded_subgoal"][()]
            if isinstance(grounded, bytes):
                grounded = grounded.decode()
            simple = ts["info/simple_subgoal"][()]
            if isinstance(simple, bytes):
                simple = simple.decode()
            boundaries.append({"step": i, "simple": simple, "grounded": grounded})
    out[tag] = {"h5": path, "n_steps": n, "boundaries": boundaries}
    f.close()

with open("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/verify/VideoPlaceButton-01/h5_traces.json", "w") as fh:
    json.dump(out, fh, indent=2, ensure_ascii=False)
print("独立复现完成，写入 h5_traces.json")

# 抽取所有 "drop the cube onto target" 的坐标序列，独立核对无重复复用同一模块的记录
for tag, data in out.items():
    drops = [b["grounded"] for b in data["boundaries"] if "drop the cube onto target" in b["grounded"]]
    print(tag, "target-drops:", drops)
