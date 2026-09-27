# 步 6：真仿真小样本（进程内 monkeypatch，不落盘改仓库）：V5 外环配置下 reset 成败/耗时、前 64 步揭示、放回精度、画面
# 用法：s6_sim_v5.py <Task> <v4|v5> <seed,seed,...> [demo_seeds]
import os, sys, json, time, math
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
REPO = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask"
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, REPO + "/scripts"); sys.path.insert(0, REPO + "/src")
import numpy as np
import generate_dataset_newseed as gen
gen._pool_init(os.environ["CUDA_VISIBLE_DEVICES"], None, REPO + "/src")
import gymnasium as gym, torch
from PIL import Image
import robomme.robomme_env  # noqa
from robomme.robomme_env.utils import unmask_distractors as ud
from robomme.robomme_env.utils import unmask_swap_xhard as ux
import importlib
task, mode = sys.argv[1], sys.argv[2]
seeds = [int(s) for s in sys.argv[3].split(",") if s]
demo_seeds = [int(s) for s in sys.argv[4].split(",")] if len(sys.argv) > 4 and sys.argv[4] else []
mod = importlib.import_module(f"robomme.robomme_env.{task}")
V5 = json.loads(os.environ.get("V5CFG", "{}"))
if mode == "v5":
    if task in ("VideoUnmask", "ButtonUnmask"):
        n_col = int(V5.get("n_colors", 9))
        base = [dict(c) for c in ud.DISTRACTOR_COLORS]
        ud.DISTRACTOR_COLORS = tuple(base[i % 3] for i in range(n_col))   # 模拟「有放回」：色池按 3 色循环扩长
        cfg = dict(mod.XHARD_DISTRACTOR)
        cfg.update(count=V5["count"], ring_max_abs_xy=V5["ring"], cube_count_range=V5["cubes"],
                   color_pool=[c["name"] for c in ud.DISTRACTOR_COLORS], max_trials=V5.get("max_trials", 1024))
        mod.XHARD_DISTRACTOR = cfg
    else:
        cfg = dict(mod.XHARD_DISTRACTOR)
        cfg.update(count=V5["count"], ring_half_extent=V5["ring"], with_cube_range=V5["cubes"])
        if "min_gap" in V5:
            cfg["min_gap"] = V5["min_gap"]
        mod.XHARD_DISTRACTOR = cfg
        if "max_trials" in V5:
            ux.DISTRACTOR_MAX_TRIALS = V5["max_trials"]
print("CFG", task, mode, json.dumps(mod.XHARD_DISTRACTOR), flush=True)

kw = dict(obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos", render_mode="rgb_array",
          reward_mode="dense", difficulty="xhard")
out = []
for seed in seeds:
    row = {"task": task, "mode": mode, "seed": seed}
    t0 = time.time()
    env = None
    try:
        env = gym.make(task, seed=seed, **kw)
        obs, _ = env.reset()
        row["reset_s"] = round(time.time() - t0, 1)
        b = env.unwrapped
        dbs = list(getattr(b, "distractor_bins", []))
        row["n_distractors"] = len(dbs); row["n_dcubes"] = len(getattr(b, "distractor_cubes", []))
        p0 = {a.name: a.pose.p[0].cpu().numpy().copy() for a in dbs + list(b.spawned_bins)}
        qpos = b.agent.robot.get_qpos()[0].cpu().numpy()
        act = np.concatenate([qpos[:7], [qpos[7]]]).astype(np.float32)
        tt = []
        for k in range(72):
            s = time.time(); obs, *_ = env.step(act); tt.append(time.time() - s)
            if k in (10, 45):
                rgb = obs["sensor_data"]["base_camera"]["rgb"][0].cpu().numpy()
                Image.fromarray(rgb).save(f"{S}/sim_{task}_{mode}_{seed}_t{k}.png")
        row["step_ms_reveal_0_31"] = round(1000 * float(np.mean(tt[:32])), 1)
        row["step_ms_after_33_71"] = round(1000 * float(np.mean(tt[33:])), 1)
        errs, zs = [], []
        for a in dbs + list(b.spawned_bins):
            p = a.pose.p[0].cpu().numpy()
            errs.append(float(np.linalg.norm(p[:2] - p0[a.name][:2]))); zs.append(float(p[2]))
        row["max_xy_err_after_reveal_mm"] = round(1000 * max(errs), 2)
        row["z_range"] = [round(min(zs), 4), round(max(zs), 4)]
        row["ok"] = True
        spec = b._spec.to_dict()
        row["distractor_spec"] = spec.get("objects", {}).get("distractors") or spec.get("layout", {}).get("distractors")
    except Exception as exc:
        row["ok"] = False; row["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"; row["reset_s"] = round(time.time() - t0, 1)
    finally:
        if env is not None:
            env.close()
    print("ROW", json.dumps(row), flush=True)
    out.append(row)
for seed in demo_seeds:
    job = gen.EpisodeJob(task=task, episode=9, attempt=0, seed=seed, difficulty="xhard",
                         output_root=f"{S}/demo_{task}_{mode}", repo_root=REPO, sampling_config=None)
    t0 = time.time(); r = gen._worker(job)
    print("DEMO", json.dumps({"task": task, "mode": mode, "seed": seed, "ok": bool(r.get("ok")), "class": r.get("failure_class"),
                              "etype": r.get("error_type"), "err": (r.get("error") or "")[:300], "wall_s": round(time.time() - t0, 1),
                              "timesteps": r.get("timesteps") or r.get("timestep_count")}), flush=True)
print("SIM_DONE", task, mode)
