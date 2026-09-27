"""仿真核验：在评估同款 DemonstrationWrapper（max_steps_without_demonstration=1302）下，
进程内 monkeypatch xhard 配置（不落盘），reset 后用 oracle（环境自带 solve）跑执行段，记录：
- 演示帧数（front_rgb_list，含 1 帧 init）
- 执行段成功时计入预算的步数、是否在 1302 前成功、是否被截断
- 演示期是否有 screw 失败（DemonstrationWrapper 的 _current_demo_task_screw_failed 不会抛）

用法：
  sim_oracle_eval.py RouteStick <seed> <L>
  sim_oracle_eval.py PatternLock <seed> <grid> <lo> <hi> <spacing> [png_out]
"""
import sys, time, json, logging
from pathlib import Path
REPO = Path("/data/hongzefu/robomme_benchmark_MotionJEPANewTask")
sys.path.insert(0, str(REPO / "src"))
logging.disable(logging.CRITICAL)
import numpy as np, gymnasium as gym, torch
import robomme.robomme_env  # 注册
from robomme.env_record_wrapper.DemonstrationWrapper import DemonstrationWrapper
from robomme.robomme_env.utils.planner_fail_safe import FailAwarePandaStickMotionPlanningSolver
task = sys.argv[1]; seed = int(sys.argv[2])
if task == "RouteStick":
    from robomme.robomme_env import RouteStick as RSmod
    import importlib; RS = importlib.import_module("robomme.robomme_env.RouteStick").RouteStick
    L = int(sys.argv[3])
    RS.configs = {**RS.configs, "xhard": {"length": [L, L], "backtrack": True}}
    tag = f"L={L}"
else:
    import os, inspect, textwrap
    PLm = __import__("robomme.robomme_env.PatternLock", fromlist=["x"])
    gs, lo, hi, sp = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), float(sys.argv[6])
    if "x" in gs:
        # 非方形网格：进程内改写 _load_scene 的行列取值（不落盘）
        R_, C_ = [int(v) for v in gs.split("x")]
        grid = R_
        s = textwrap.dedent(inspect.getsource(PLm.PatternLock._load_scene))
        old_line = 'num_rows, num_cols = decision_cfg["grid"][self.difficulty],decision_cfg["grid"][self.difficulty]'
        assert old_line in s
        s = s.replace(old_line, f"num_rows, num_cols = {R_}, {C_}")
        ns = dict(PLm.__dict__); exec(s, ns)
        PLm.PatternLock._load_scene = ns["_load_scene"]
    else:
        grid = int(gs)
    PLm.PatternLock.configs = {**PLm.PatternLock.configs, "xhard": {"grid": grid, "length": [lo, hi]}}
    PLm.NATIVE_SAMPLING["positions"]["grid_spacing"] = sp
    TS = float(os.environ.get("V5_TS", "1.0"))
    if TS != 1.0:
        # 放慢演示方案：只在演示录制期（demonstration_record_traj=True）把 screw 轨迹按 TS 线性重采样
        _orig_sw = PLm.solve_swingonto
        import sapien as _sp
        def _slow_swingonto(env, planner, target=None, record_swing_qpos=False):
            base = env.unwrapped
            if not getattr(base, "demonstration_record_traj", False):
                return _orig_sw(env, planner, target=target, record_swing_qpos=record_swing_qpos)
            q = base.agent.tcp.pose.q.reshape(-1, 4)[0]
            gp = target.pose.p.tolist()[0]; gp[2] = 0.07
            res = None
            for _ in range(2):
                r = planner.move_to_pose_with_screw(_sp.Pose(gp, q), dry_run=True)
                if isinstance(r, dict) and r.get("status") == "Success":
                    pos = r["position"]; n = len(pos); m = int(np.ceil(n * TS))
                    t_old = np.linspace(0, 1, n); t_new = np.linspace(0, 1, m)
                    newpos = np.stack([np.interp(t_new, t_old, pos[:, j]) for j in range(pos.shape[1])], 1)
                    res = planner.follow_path({"status": "Success", "position": newpos})
            if record_swing_qpos:
                base.swing_qpos = base.agent.robot.qpos
            return res
        PLm.solve_swingonto = _slow_swingonto
    tag = f"grid={gs} len=[{lo},{hi}] sp={sp} ts={TS}"
# 进程内计数 RRT* 兜底调用（演示期 DemonstrationWrapper 与执行期兜底都会走到基类这个方法）
from mani_skill.examples.motionplanning.base_motionplanner.motionplanner import BaseMotionPlanningSolver as _B
RRT_CALLS = []
_orig_rrt = _B.move_to_pose_with_RRTStar
def _rrt(self, *a, **k):
    RRT_CALLS.append(1)
    return _orig_rrt(self, *a, **k)
_B.move_to_pose_with_RRTStar = _rrt
from robomme.robomme_env.utils.planner_fail_safe import ScrewPlanFailure
class ScrewThenRRTStick(FailAwarePandaStickMotionPlanningSolver):
    """与数据生成 _planner_classes 同口径：screw 3 次失败后 RRT* 3 次。"""
    def move_to_pose_with_screw(self, *a, **k):
        for _ in range(3):
            try:
                r = super().move_to_pose_with_screw(*a, **k)
            except ScrewPlanFailure:
                continue
            if not (isinstance(r, int) and r == -1):
                return r
        for _ in range(3):
            try:
                r = self.move_to_pose_with_RRTStar(*a, **k)
            except Exception:
                continue
            if not (isinstance(r, int) and r == -1):
                return r
        raise RuntimeError("screw and RRT* exhausted")
env = gym.make(task, obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos", render_mode="rgb_array",
               reward_mode="dense", seed=seed, difficulty="xhard")
w = DemonstrationWrapper(env, max_steps_without_demonstration=1302, gui_render=False)
t0 = time.time()
obs, info = w.reset()
u = w.unwrapped
demo_frames = len(obs["front_rgb_list"])
nodes = None
if task == "PatternLock":
    nodes = [b.name for b in u.selected_buttons]
if len(sys.argv) > 7 and task == "PatternLock":
    import imageio
    imageio.imwrite(sys.argv[7], np.asarray(obs["front_rgb_list"][len(obs["front_rgb_list"]) // 2]))
reset_s = time.time() - t0
rrt_demo = len(RRT_CALLS)
demo_task_idx = int(getattr(u, "timestep", -1))
n_demo_tasks = sum(1 for t in u.task_list if t.get("demonstration"))
count_after_reset = w.steps_without_demonstration
log = []
orig = w.step
def step(a):
    out = orig(a)
    log.append((w.steps_without_demonstration, out[4].get("status")))
    return out
w.step = step
planner = ScrewThenRRTStick(w, debug=False, vis=False, base_pose=u.agent.robot.pose,
                                                  visualize_target_grasp_pose=False, print_env_info=False, joint_vel_limits=0.3)
exec_tasks = [t for t in u.task_list if not t.get("demonstration")]
err = None
try:
    for t in exec_tasks:
        t["solve"](w, planner)
        st = log[-1][1] if log else None
        if st in ("success", "fail"):
            break
except Exception as exc:
    err = f"{type(exc).__name__}: {exc}"
first_success = next((c for c, s in log if s == "success"), None)
first_timeout = next((c for c, s in log if s == "timeout"), None)
first_fail = next((c for c, s in log if s == "fail"), None)
print("RESULT " + json.dumps(dict(task=task, seed=seed, cfg=tag, n_selected=len(u.selected_buttons),
      demo_frames_incl_init=demo_frames, demo_s=round((demo_frames - 1) / 30, 2), reset_wall_s=round(reset_s, 1),
      budget_count_after_reset=count_after_reset, exec_steps_logged=len(log), success_at_count=first_success,
      timeout_at_count=first_timeout, rrt_calls_demo=rrt_demo, rrt_calls_exec=len(RRT_CALLS) - rrt_demo,
      task_index_after_reset=demo_task_idx, n_demo_tasks=n_demo_tasks, fail_at_count=first_fail, error=err, nodes=nodes)), flush=True)
w.close()
