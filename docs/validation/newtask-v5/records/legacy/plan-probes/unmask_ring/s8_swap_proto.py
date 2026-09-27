# 步 8：Swap 两环境 V5 原型（进程内替换 sample_distractors，不改仓库）：矩形环带 + 精确 8 角点可见 + 与区域内同密度间距 + 预演扫掠精确判据
# 用法：s8_swap_proto.py <Task> <reset_seeds> <demo_seeds> ；环境变量 V5CFG={"count":16,"inner":[x0,x1,y0,y1],"d":[a,b],"cubes":8,"max_trials":1024}
import os, sys, json, time, math
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
REPO = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask"
S = "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_ring"
sys.path.insert(0, REPO + "/scripts"); sys.path.insert(0, REPO + "/src"); sys.path.insert(0, S)
import numpy as np
import generate_dataset_newseed as gen
gen._pool_init(os.environ["CUDA_VISIBLE_DEVICES"], None, REPO + "/src")
import gymnasium as gym, torch
from PIL import Image
import robomme.robomme_env  # noqa
import importlib
from robomme.robomme_env.utils import unmask_swap_xhard as ux
from robomme.robomme_env.utils import unmask_distractors as ud
from robomme.robomme_env.utils.bin_collision import ObjectState, bin_actor_pose, bin_shape_specs, check_swap_sweep
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError
import ringlib as L
task = sys.argv[1]
seeds = [int(s) for s in sys.argv[2].split(",") if s]
demo_seeds = [int(s) for s in sys.argv[3].split(",") if s]
V5 = json.loads(os.environ["V5CFG"])
ring = L.RectRing(tuple(V5["inner"]), V5["d"][0], V5["d"][1])
STATS = {"sweep_calls": 0, "sweep_s": 0.0}


def proto_sample(*, generator, cfg, obstacles, sweeps, recorder, cube_half_size):
    count = int(V5["count"]); n_cube = int(V5["cubes"]); mt = int(V5.get("max_trials", 1024))
    x0, x1, y0, y1 = ring.bbox()
    half = (cube_half_size * 2.5 + 0.005) * 0.5; gap = cube_half_size * 0.75
    occ = [(np.asarray(xy, float)[:2], float(r)) for xy, r in obstacles]
    shapes = bin_shape_specs(cube_half_size)
    recorder.record("layout.distractors_requested", count)
    placements = []
    for i in range(count):
        chosen = None
        for _ in range(mt):
            x = x0 + torch.rand(1, generator=generator).item() * (x1 - x0)
            y = y0 + torch.rand(1, generator=generator).item() * (y1 - y0)
            if not ring.contains(x, y) or not L.vis_center_exact(x, y):
                continue
            here = np.array([x, y])
            if any(np.linalg.norm(here - c) < r + half + gap for c, r in occ):
                continue
            yaw = torch.rand(1, generator=generator).item() * 90.0
            p, q = bin_actor_pose([x, y], yaw, cube_half_size)
            cand = ObjectState(name=f"distractor_bin_{i}", p=p, q=q, shapes=shapes)
            t0 = time.time(); bad = False
            for k, (a, b) in enumerate(sweeps):
                STATS["sweep_calls"] += 1
                if check_swap_sweep(a, b, [cand], sweep_index=k, stage="distractor")[1] is not None:
                    bad = True; break
            STATS["sweep_s"] += time.time() - t0
            if bad:
                continue
            chosen = (x, y, yaw); break
        if chosen is None:
            raise SceneGenerationError(f"proto: 干扰容器 {i} 放不下")
        x, y, yaw = recorder.value(f"layout.distractors.{i}", list(chosen))
        placements.append({"xy": [float(x), float(y)], "yaw_deg": float(yaw)})
        occ.append((np.array([x, y]), ux.bin_footprint_radius(cube_half_size)))
    recorder.record("layout.distractors_placed", len(placements))
    order = torch.randperm(3, generator=generator).tolist()
    colors = [["yellow", "cyan", "magenta"][order[j % 3]] for j in range(n_cube)]   # 均衡循环（有放回的一种）
    colors = recorder.value("objects.distractors.cube_colors", colors, decision_key="xhard.distractor.colors")
    return {"placements": placements, "cube_colors": colors}


mod = importlib.import_module(f"robomme.robomme_env.{task}")
mod.sample_distractors = proto_sample


def proto_build(env, layout, build_bin, spawn_fixed_cube, cube_divisor: float = 1.2):
    """与 build_distractors 相同，只把方块名改成带序号（颜色重复时 V4 命名 distractor_cube_<色名> 会撞名）。"""
    from robomme.robomme_env.utils.xhard import DISTRACTOR_COLORS
    rgba = {item["name"]: item["rgba"] for item in DISTRACTOR_COLORS}
    bins, cubes = [], []
    for i, entry in enumerate(layout["placements"]):
        x, y = entry["xy"]
        bins.append(build_bin(env, callsign=f"distractor_bin_{i}", position=[x, y, 0.002], z_rotation_deg=entry["yaw_deg"]))
    for j, color in enumerate(layout["cube_colors"]):
        x, y = layout["placements"][j]["xy"]
        cubes.append(spawn_fixed_cube(env, position=[x, y], half_size=env.cube_half_size / cube_divisor, color=rgba[color],
                                      name_prefix=f"distractor_cube_{j}_{color}", yaw=0.0, dynamic=True))
    return bins, cubes


mod.build_distractors = proto_build
kw = dict(obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos", render_mode="rgb_array", reward_mode="dense", difficulty="xhard")
for seed in seeds:
    STATS.update(sweep_calls=0, sweep_s=0.0)
    t0 = time.time(); env = None
    try:
        env = gym.make(task, seed=seed, **kw); obs, _ = env.reset()
        b = env.unwrapped
        row = dict(task=task, seed=seed, ok=True, reset_s=round(time.time() - t0, 1), n=len(b.distractor_bins),
                   n_cubes=len(b.distractor_cubes), sweep_calls=STATS["sweep_calls"], sweep_s=round(STATS["sweep_s"], 1))
        pos = [a.pose.p[0].cpu().numpy()[:2].tolist() for a in b.distractor_bins]
        row["all_exact_visible"] = bool(all(L.vis_center_exact(x, y) for x, y in pos))
        qpos = b.agent.robot.get_qpos()[0].cpu().numpy(); act = np.concatenate([qpos[:7], [qpos[7]]]).astype(np.float32)
        for k in range(46):
            obs, *_ = env.step(act)
            if k in (10, 45):
                Image.fromarray(obs["sensor_data"]["base_camera"]["rgb"][0].cpu().numpy()).save(f"{S}/proto_{task}_{seed}_t{k}.png")
    except Exception as exc:
        row = dict(task=task, seed=seed, ok=False, err=f"{type(exc).__name__}: {str(exc)[:200]}", reset_s=round(time.time() - t0, 1),
                   sweep_calls=STATS["sweep_calls"], sweep_s=round(STATS["sweep_s"], 1))
    finally:
        if env is not None:
            env.close()
    print("ROW", json.dumps(row), flush=True)
for seed in demo_seeds:
    STATS.update(sweep_calls=0, sweep_s=0.0)
    job = gen.EpisodeJob(task=task, episode=9, attempt=0, seed=seed, difficulty="xhard",
                         output_root=f"{S}/demo_{task}_proto", repo_root=REPO, sampling_config=None)
    t0 = time.time(); r = gen._worker(job)
    print("DEMO", json.dumps({"task": task, "seed": seed, "ok": bool(r.get("ok")), "class": r.get("failure_class"), "etype": r.get("error_type"),
                              "err": (r.get("error") or "")[:300], "wall_s": round(time.time() - t0, 1), "sweep_s_in_sampling": round(STATS["sweep_s"], 1),
                              "timesteps": r.get("timesteps") or r.get("timestep_count")}), flush=True)
print("SIM_DONE")
