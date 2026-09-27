"""真仿真核验：模型预测「执行段方块 256 次全被演示段方块挡住」的 seed，reset 是否真失败。"""
import sys, time, json
sys.path.insert(0, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/src")
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import gymnasium as gym
import robomme.robomme_env  # noqa
from mc_layout import simulate
cases = [(1000177, "xhard"), (1000442, "xhard"), (1000446, "xhard"), (1000000, "xhard"),
         (1000002, "hard"), (1000042, "hard")]
for seed, diff in cases:
    t = time.time()
    model = simulate(seed, bias=0.5 if diff == "xhard" else 0.0, yaw_xhard=(diff == "xhard"))
    env = None
    try:
        env = gym.make("MoveCube", obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
                       render_mode="rgb_array", reward_mode="dense", seed=seed, difficulty=diff)
        env.reset()
        spec = env.unwrapped._spec.to_dict()
        ex = spec["layout"]["execution"]["cube_pose"]
        res = f"OK exec_cube={[round(v,5) for v in ex]}"
        if model.ok:
            m = model.seg["exec"]["cube"]
            res += f" model_exec_cube={[round(float(v),5) for v in m]} way(real/model)={spec['initializations']['0']['way_idx']}/{model.way_idx}"
    except Exception as exc:
        res = f"EXC {type(exc).__name__}: {str(exc)[:150]}"
    finally:
        if env is not None:
            env.close()
    print(f"SIMVERIFY seed={seed} diff={diff} model_ok={model.ok} model_fail={model.fail} real={res} {time.time()-t:.1f}s", flush=True)
