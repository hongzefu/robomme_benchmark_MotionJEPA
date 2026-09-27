"""P3 演示层：进程内补丁 PatternLock xhard length=[24,25]、max_attempts=20000，耗尽抛错；
用官方 generate_dataset 的 _planner_classes/_execute_tasks + RobommeRecordWrapper 录 h5（与 V4 实跑同口径，不开 recover、不注入 spec），
随后从 h5 数 is_video_demo 帧、逐段帧数。用法：demo_probe.py <seed> <episode>"""
import sys, os, json, time, logging, types, traceback
from pathlib import Path
OUT = Path("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v5/plan-probes-r2/patternlock_2425")
OFFICIAL = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/train-parity/local-smoke-01/official-src/scripts/data-generation"
sys.path.insert(0, OFFICIAL)
import generate_dataset as official
import numpy as np, h5py, torch, gymnasium as gym
import robomme.robomme_env  # 注册
import importlib; PLm = importlib.import_module("robomme.robomme_env.PatternLock")
assert "/robomme_v5_probe_wt/" in PLm.__file__, PLm.__file__
from robomme.env_record_wrapper import RobommeRecordWrapper
from robomme.robomme_env.utils.planner_fail_safe import (FailAwarePandaArmMotionPlanningSolver,
    FailAwarePandaStickMotionPlanningSolver, ScrewPlanFailure)

# ── 进程内补丁（不落盘） ──
PLm.PatternLock.configs = {**PLm.PatternLock.configs, "xhard": {"grid": 5, "length": [24, 25]}}
PLm.PatternLock.config_xhard = PLm.PatternLock.configs["xhard"]
PLm.NATIVE_SAMPLING["parameters"]["path_selection"]["max_attempts"] = 20000

seed, episode = int(sys.argv[1]), int(sys.argv[2])
wdir = OUT / "episodes" / f"PatternLock_episode_{episode}"
arm_cls, stick_cls = official._planner_classes(FailAwarePandaArmMotionPlanningSolver,
                                               FailAwarePandaStickMotionPlanningSolver, ScrewPlanFailure)
job = types.SimpleNamespace(task="PatternLock", episode=episode, seed=seed)
res = dict(seed=seed, episode=episode)
t0 = time.time(); err = None; rec = None
try:
    wdir.mkdir(parents=True, exist_ok=False)
    base = gym.make("PatternLock", obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                    render_mode="rgb_array", reward_mode="dense", seed=seed, difficulty="xhard")
    rec = RobommeRecordWrapper(base, dataset=str(wdir), env_id="PatternLock", episode=episode, seed=seed, save_video=True)
    t1 = time.time(); rec.reset(); res["reset_wall_s"] = round(time.time() - t1, 1)
    u = rec.unwrapped
    n_nodes = len(u.selected_buttons)
    res["nodes"] = n_nodes
    res["path_attempts"] = u._spec.trace and next((it.get("value", it.get("drawn")) for it in u._spec.trace
                                                    if it.get("path") == "actions.path_attempts"), None)
    res["path_nodes"] = [int(b.name.split("_")[-1]) for b in u.selected_buttons]
    if not (24 <= n_nodes <= 25):
        raise RuntimeError(f"搜索耗尽：节点数 {n_nodes} 不在 [24,25]（模拟 V5 抛错）")
    planner = stick_cls(rec, debug=False, vis=False, base_pose=u.agent.robot.pose,
                        visualize_target_grasp_pose=False, print_env_info=False, joint_vel_limits=0.3)
    official._execute_tasks(rec, planner, torch, job)
    res["ok"] = True
except Exception as exc:
    res["ok"] = False; err = f"{type(exc).__name__}: {exc}"; traceback.print_exc()
finally:
    if rec is not None:
        try: rec.close()
        except Exception as exc: err = (err or "") + f" | close: {exc}"
res["error"] = err; res["total_wall_s"] = round(time.time() - t0, 1)
h5s = list((wdir / "hdf5_files").glob("*.h5")) if wdir.exists() else []
if h5s:
    with h5py.File(h5s[0], "r") as f:
        g = f[f"episode_{episode}"]
        n = len([k for k in g.keys() if k.startswith("timestep_")])
        demo = np.array([bool(g[f"timestep_{i}"]["info/is_video_demo"][()]) for i in range(n)])
        bound = np.array([bool(g[f"timestep_{i}"]["info/is_subgoal_boundary"][()]) for i in range(n)])
        comp_last = bool(g[f"timestep_{n-1}"]["info/is_completed"][()])
    nd = int(demo.sum()); first_nd = int(np.argmin(demo)) if not demo.all() else n
    cuts = np.where(bound)[0].tolist(); segs = []; s0 = 0
    for c in cuts:
        segs.append((bool(demo[s0]), c - s0 + 1)); s0 = c + 1
    dl = [l for d, l in segs if d]; el = [l for d, l in segs if not d]
    res.update(h5=str(h5s[0]), total_frames=n, demo_frames=nd, demo_s=round(nd / 30, 2), exec_frames=n - nd,
               demo_prefix=bool(demo[:first_nd].all() and not demo[first_nd:].any()), completed_last=comp_last,
               demo_seg_lens=dl, exec_seg_lens=el,
               demo_seg_mean=round(float(np.mean(dl)), 2) if dl else None)
print("RESULT " + json.dumps(res, ensure_ascii=False), flush=True)
with open(OUT / "demo_results.jsonl", "a") as f:
    f.write(json.dumps(res, ensure_ascii=False) + "\n")
