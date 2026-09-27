"""M3（仿真，1 次 gym.make+reset，单进程）：VideoUnmaskSwap xhard seed 4500300（V4 正式局 ep3，运行期 BinCollisionError）。

目的：
1. 实测 reset 墙钟（含 sample_distractors 的逐候选扫掠检查）与每控制步墙钟；
2. 在进程内 monkeypatch 环境模块的 check_swap_sweep（先调真函数），记录每段交换开始时送进检查的真实
   起态（p、q）与控制步，对照名义预演：验证「搭档解析与扫掠检查读的是上一段 smoothstep(32/33) 处、
   尚未落终态的位置」这一判断，并看真实四元数是否与名义一致（排除翻转/倾斜）；
3. 复现 sweep#1 的碰撞拒绝。动作 = 保持当前关节角（pd_joint_pos），不调规划器。
"""
import sys
import time

import numpy as np

sys.path.insert(0, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/src")
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap")
import gymnasium as gym  # noqa: E402
import robomme.robomme_env  # noqa: E402,F401
import importlib  # noqa: E402

from replica import inner_sequence, layout_from_spec, load_spec_rows  # noqa: E402

vus_mod = importlib.import_module("robomme.robomme_env.VideoUnmaskSwap")
real_check = vus_mod.check_swap_sweep
calls = []


def spy(a, b, bystanders, **kw):
    t0 = time.perf_counter()
    out = real_check(a, b, bystanders, **kw)
    calls.append({"sweep": kw.get("sweep_index"), "a": a.name, "b": b.name, "pa": a.p.copy(), "pb": b.p.copy(),
                  "qa": a.q.copy(), "qb": b.q.copy(), "n_by": len(bystanders), "dt": time.perf_counter() - t0,
                  "rej": None if out[1] is None else out[1].summary()})
    return out


vus_mod.check_swap_sweep = spy
row = next(r for r in load_spec_rows("VideoUnmaskSwap") if r["seed"] == 4500300)
lay = layout_from_spec(row)
seq = inner_sequence(lay)

t0 = time.perf_counter()
env = gym.make("VideoUnmaskSwap", obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
               render_mode="rgb_array", reward_mode="dense", seed=4500300, difficulty="xhard",
               native_episode_spec=row["spec"])
t_make = time.perf_counter() - t0
t0 = time.perf_counter()
env.reset()
t_reset = time.perf_counter() - t0
base = env.unwrapped
print(f"make={t_make:.1f}s reset={t_reset:.1f}s n_swaps={base.swap_times} window_steps={base.swap_window_steps} "
      f"schedule_end={base.swap_schedule[-1][3]} distractors={len(base.distractor_bins)}", flush=True)
print("runtime_checks after reset:", [(c['kind'], c.get('rejection') is None) for c in base._runtime_checks], flush=True)
qpos = base.agent.robot.get_qpos()[0].cpu().numpy()
action = np.concatenate([qpos[:7], [qpos[7]]]).astype(np.float32)
step_times = []
err = None
for t in range(140):
    t1 = time.perf_counter()
    try:
        env.step(action)
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        print(f"step {int(base.elapsed_steps)} raised {err}", flush=True)
        break
    step_times.append(time.perf_counter() - t1)
print(f"steps_done={len(step_times)} mean_step={np.mean(step_times)*1000:.0f}ms "
      f"max_step={np.max(step_times)*1000:.0f}ms", flush=True)
for c in calls:
    k = c["sweep"]
    a_nom = seq[k][3]
    ia, ib = int(c["a"].split("_")[1]), int(c["b"].split("_")[1])
    da = float(np.linalg.norm(c["pa"][:2] - a_nom[ia]))
    db = float(np.linalg.norm(c["pb"][:2] - a_nom[ib]))
    print(f"sweep#{k} pair=({c['a']},{c['b']}) nominal_pair={seq[k][:2]} |p_actual-p_nominal| a={da*1000:.3f}mm b={db*1000:.3f}mm "
          f"z=({c['pa'][2]:.5f},{c['pb'][2]:.5f}) qa={np.round(c['qa'],4)} qb={np.round(c['qb'],4)} "
          f"bystanders={c['n_by']} check={c['dt']*1000:.0f}ms rej={c['rej']}", flush=True)
env.close()
