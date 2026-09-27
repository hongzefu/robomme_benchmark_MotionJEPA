"""补丁后真实模拟器 reset：与离线副本 mc_v5（R=0.05）逐值对拍；重点确认 seed 1000442、1000446 执行段方块生成不再失败。"""
import sys, time, math, json
D = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v5/plan-probes-r2/movecube_circle"
sys.path.insert(0, D)
import numpy as np
from patch_r2 import apply_patch
apply_patch(R=0.05)
import gymnasium as gym
from mc_v5 import simulate, seg_dist
seeds = [int(s) for s in sys.argv[1].split(",")]
agree = 0; spawn_ok = 0; rows = []
for seed in seeds:
    t = time.time()
    m = simulate(seed, bias=0.0, R=0.05)
    env = gym.make("MoveCube", obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                   render_mode="rgb_array", reward_mode="dense", seed=seed, difficulty="xhard")
    try:
        env.reset(); u = env.unwrapped
        sp = u._spec.to_dict()["layout"]
        errs = []; dists = {}
        for seg, key in (("demo", "demo"), ("exec", "execution")):
            lay = sp[key]; e = m.seg[seg]
            errs += [abs(e["peg_root"][0] - lay["peg_offsets"][1]), abs(e["peg_root"][1] - lay["peg_offsets"][0] - lay["peg_offsets"][2]),
                     abs(e["peg_yaw"] - lay["peg_yaw"]), *np.abs(e["goal"] - np.array(lay["goal_xy"])),
                     *np.abs(e["cube"] - np.array(lay["cube_pose"][:2])), abs(e["cube_yaw"] - lay["cube_pose"][2])]
            root = np.array([lay["peg_offsets"][1], lay["peg_offsets"][0] + lay["peg_offsets"][2]])
            dists[seg] = dict(goal=round(float(np.linalg.norm(lay["goal_xy"])), 4), cube=round(float(np.linalg.norm(lay["cube_pose"][:2])), 4),
                              peg_plan=round(seg_dist(root, lay["peg_yaw"]), 4), peg_phys=round(seg_dist(root, lay["peg_yaw"], -0.15, 0.05), 4))
        # 实测杆几何：head 中心 = root，tail 中心 = root − L·u
        ph = u.peg_head.pose.p[0, :2].cpu().numpy(); pt = u.peg_tail.pose.p[0, :2].cpu().numpy()
        way = u._spec.to_dict()["initializations"]["0"]["way_idx"]
        ok = max(errs) < 1e-6 and way == m.way_idx and u._v5_stats == {k: v for k, v in m.rej.items()}
        agree += ok; spawn_ok += 1
        row = dict(seed=seed, reset="OK", maxerr=float(max(errs)), way=way, model_way=m.way_idx, agree=bool(ok),
                   stats_sim=u._v5_stats, stats_model=m.rej, dists=dists, head_tail_sep=round(float(np.linalg.norm(ph - pt)), 4),
                   wall_s=round(time.time() - t, 1))
    except Exception as exc:
        row = dict(seed=seed, reset=f"EXC {type(exc).__name__}: {str(exc)[:200]}", model_ok=m.ok, model_fail=m.fail)
    finally:
        env.close()
    rows.append(row)
    print("V5RESET", json.dumps(row, ensure_ascii=False, default=str), flush=True)
print(f"V5RESET_SUMMARY agree={agree}/{len(seeds)} reset_ok={spawn_ok}/{len(seeds)}")
