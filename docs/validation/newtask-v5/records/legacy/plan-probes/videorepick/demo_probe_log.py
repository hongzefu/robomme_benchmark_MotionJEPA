# 仿真校准（只读、单进程、GPU1）：走正式入口 generate_dataset_newseed._worker 跑 xhard 演示，
# 进程内 monkeypatch VideoRepick._check_swap_sweep_from_actual，在每段交换开始时记下全部方块实际位姿
# 与 D5 结果，用来和离线复刻（v4rep + sim_lib）逐段比对：搭档身份、扫掠拒绝与否、演示抓放后目标的位移。
import sys, os, json, time
from pathlib import Path
REPO = Path("/data/hongzefu/robomme_benchmark_MotionJEPANewTask")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, str(REPO / "src")); sys.path.insert(0, str(HERE))
import generate_dataset_newseed as gen
gen._pool_init("1", None, str(REPO / "src"))
import numpy as np
from robomme.robomme_env.VideoRepick import VideoRepick
LOG = []
_orig = VideoRepick._check_swap_sweep_from_actual
def patched(self, sweep_index, initiator, partner):
    poses = []
    for a in self.spawned_cubes:
        p = self._get_actor_position(a); q = a.pose.q
        q = q.detach().cpu().numpy().reshape(-1) if hasattr(q, "detach") else np.asarray(q).reshape(-1)
        poses.append([float(p[0]), float(p[1]), float(p[2])] + [float(v) for v in q])
    rec = {"seed": int(self.seed), "sweep_index": int(sweep_index), "a": self.spawned_cubes.index(initiator),
           "b": self.spawned_cubes.index(partner), "poses": poses, "target": self.spawned_cubes.index(self.target_cube_1)}
    try:
        _orig(self, sweep_index, initiator, partner)
        rec["rejected"] = False
    except Exception as exc:
        rec["rejected"] = True; rec["reason"] = str(exc)[:200]
        LOG.append(rec); raise
    LOG.append(rec)
VideoRepick._check_swap_sweep_from_actual = patched
out = HERE / "demo_out"; out.mkdir(exist_ok=True)
seeds = [int(s) for s in sys.argv[1].split(",")]
tag = sys.argv[2]
for seed in seeds:
    job = gen.EpisodeJob(task="VideoRepick", episode=9, attempt=0, seed=seed, difficulty="xhard",
                         output_root=str(out), repo_root=str(REPO), sampling_config=None)
    t0 = time.time(); res = gen._worker(job)
    print(f"seed={seed} ok={res.get('ok')} err={res.get('error_type')} {str(res.get('error'))[:120]} wall={time.time()-t0:.0f}s", flush=True)
    for f in (out / "hdf5_files").glob(f"*seed{seed}*"):
        f.unlink()  # 省盘：h5 不需要
    LOG.append({"seed": seed, "episode_result": {"ok": bool(res.get("ok")), "error_type": res.get("error_type"), "error": str(res.get("error"))[:200]}})
    json.dump(LOG, open(HERE / f"demo_log_{tag}.json", "w"))
print("全部完成", len(LOG), "swap records")
