"""补丁后的真仿真 reset 与 numpy/torch 模型逐值对拍（V5-b + 执行段不避让）；另测 1 条原三档 hard 不受影响。"""
import sys, time, math
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import numpy as np
from patch_v5 import apply_patch, V5_DEFAULT
apply_patch()
import gymnasium as gym
from mc_layout import simulate, CenterCfg
V5 = CenterCfg("square", V5_DEFAULT["peg_w"], V5_DEFAULT["goal_w_demo"], V5_DEFAULT["goal_w_exec"], V5_DEFAULT["cube_w"], "both")
cases = [(1000442, "xhard"), (1000446, "xhard"), (910404, "xhard"), (910606, "xhard"), (1000003, "hard")]
agree = 0
for seed, diff in cases:
    t = time.time()
    if diff == "xhard":
        m = simulate(seed, bias=0.0, center=V5, exec_avoid_demo=False)
    else:
        m = simulate(seed, bias=0.0, yaw_xhard=False)
    env = gym.make("MoveCube", obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                   render_mode="rgb_array", reward_mode="dense", seed=seed, difficulty=diff)
    try:
        env.reset()
        sp = env.unwrapped._spec.to_dict()["layout"]
        errs = []
        for seg, key in (("demo", "demo"), ("exec", "execution")):
            lay = sp[key]; e = m.seg[seg]
            errs += [abs(e["peg_root"][0] - lay["peg_offsets"][1]), abs(e["peg_root"][1] - lay["peg_offsets"][0] - lay["peg_offsets"][2]),
                     abs(e["peg_yaw"] - lay["peg_yaw"]), *np.abs(e["goal"] - np.array(lay["goal_xy"])),
                     *np.abs(e["cube"] - np.array(lay["cube_pose"][:2])), abs(e["cube_yaw"] - lay["cube_pose"][2])]
        way = env.unwrapped._spec.to_dict()["initializations"]["0"]["way_idx"]
        ok = max(errs) < 1e-6 and way == m.way_idx
        agree += ok
        cz = [max(abs(v) for v in sp[k]["cube_pose"][:2]) for k in ("demo", "execution")]
        gz = [max(abs(v) for v in sp[k]["goal_xy"]) for k in ("demo", "execution")]
        print(f"V5RESET seed={seed} {diff} maxerr={max(errs):.1e} way={way}/{m.way_idx} {'AGREE' if ok else 'DISAGREE'} "
              f"cube_inf={np.round(cz,4).tolist()} goal_inf={np.round(gz,4).tolist()} corner_bias_rec={sp['demo'].get('corner_bias')} draws_model={m.draws} {time.time()-t:.1f}s", flush=True)
    except Exception as exc:
        print(f"V5RESET seed={seed} {diff} EXC {type(exc).__name__}: {str(exc)[:200]} model_ok={m.ok}", flush=True)
    finally:
        env.close()
print(f"V5RESET agree={agree}/{len(cases)}")
