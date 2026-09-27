"""仿真核验（1 次 reset）：评估侧 DemonstrationWrapper 返回给策略的演示帧数、reset 后已计入预算的步数。

用 V4 冻结快照 RouteStick/3（L=12）或命令行指定的 task/episode，走 BenchmarkEnvBuilder.from_v4_specs（与 v4_eval 同路径）。
"""
import sys, time
from pathlib import Path
REPO = Path("/data/hongzefu/robomme_benchmark_MotionJEPANewTask")
for p in (REPO, REPO / "scripts", REPO / "src"):
    sys.path.insert(0, str(p))
from scripts.parity.v4_specs import load_specs
from robomme.env_record_wrapper import BenchmarkEnvBuilder
task = sys.argv[1] if len(sys.argv) > 1 else "RouteStick"
episode = int(sys.argv[2]) if len(sys.argv) > 2 else 3
header, _, specs = load_specs(REPO / "scripts/configs/newtask-v4/v4-01/specs.jsonl")
b = BenchmarkEnvBuilder.from_v4_specs(task, header, specs, action_space="joint_angle", max_steps=1300)
env = b.make_env_for_episode(episode)
t0 = time.time()
obs, info = env.reset()
u = env.unwrapped
# 找 DemonstrationWrapper 实例
w = env
while w is not None and type(w).__name__ != "DemonstrationWrapper":
    w = getattr(w, "env", None)
print(f"RESULT task={task} ep={episode} reset_wall_s={time.time()-t0:.1f} front_rgb_list={len(obs['front_rgb_list'])} "
      f"elapsed_steps={int(u.elapsed_steps[0])} steps_without_demo={getattr(w,'steps_without_demonstration',None)} "
      f"max_steps_without_demo={getattr(w,'max_steps_without_demonstration',None)} n_tasks={len(u.task_list)} "
      f"n_demo_tasks={sum(1 for t in u.task_list if t.get('demonstration'))} cur_task_demo={getattr(u,'current_task_demonstration',None)}", flush=True)
env.close()
