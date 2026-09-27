"""探针 C 的 worker：直接调用 scripts/parity/train_split_worker.run_one（V5 正式生成用的同一镜像 worker），
只在子进程内做两处只读/提速补丁（不改任何仓库文件）：
  （首版曾强制 save_video=False 提速，实测 h5 逐帧记录也挂在 save_video 上，关掉后 h5 为空、全部被判失败，已撤回）
  1. RobommeRecordWrapper.close 之前把 elapsed_steps、当前子任务序号/名称写进 worker_dir/probe_steps.json。
"""
import json
import os
import sys
import time
from pathlib import Path


def run(payload):
    job, config, spec = payload
    os.environ["CUDA_VISIBLE_DEVICES"] = job.gpu
    src = str(Path(job.repo_root) / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from robomme.env_record_wrapper import RobommeRecordWrapper
    if not getattr(RobommeRecordWrapper, "_probe_c_patched", False):
        orig_init, orig_close = RobommeRecordWrapper.__init__, RobommeRecordWrapper.close

        def close(self):
            info = {}
            try:
                env = self.unwrapped
                info["elapsed_steps"] = int(env.elapsed_steps[0]) if hasattr(env.elapsed_steps, "__len__") else int(env.elapsed_steps)
                info["current_task_index"] = getattr(env, "current_task_index", None)
                names = [t.get("name") for t in getattr(env, "task_list", [])]
                info["task_names"] = names
                info["way"] = getattr(env, "way", None)
                info["reset_in_process"] = bool(getattr(env, "reset_in_proecess", False))
                cube = env.cube.pose.p[0].detach().cpu().numpy().tolist()
                goal = env.goal_site.pose.p[0].detach().cpu().numpy().tolist()
                info["final_cube_xyz"] = cube
                info["final_goal_xyz"] = goal
            except Exception as exc:  # noqa: BLE001
                info["probe_error"] = repr(exc)
            try:
                Path(self._probe_dir).mkdir(parents=True, exist_ok=True)
                (Path(self._probe_dir) / "probe_steps.json").write_text(json.dumps(info))
            except Exception:  # noqa: BLE001
                pass
            return orig_close(self)

        RobommeRecordWrapper.close = close
        RobommeRecordWrapper._probe_c_patched = True
    RobommeRecordWrapper._probe_dir = job.worker_dir
    import generate_dataset as official
    if not getattr(official, "_probe_c_patched", False):
        orig_exec = official._execute_tasks

        def traced_execute(record_env, planner, torch_module, jb):
            """与官方 _execute_tasks 逐句同逻辑，只多记一份逐子任务轨迹（写到 worker_dir/probe_trace.json）。"""
            trace = []
            env = record_env.unwrapped

            def snap(tag, name, extra=None):
                ev = env.evaluate(solve_complete_eval=True)
                item = {"tag": tag, "task": name, "steps": int(env.elapsed_steps[0]) if hasattr(env.elapsed_steps, "__len__") else int(env.elapsed_steps),
                        "idx": getattr(env, "current_task_index", None),
                        "success": official._runtime_bool(ev.get("success", False), torch_module),
                        "fail": official._runtime_bool(ev.get("fail", False), torch_module)}
                if extra:
                    item.update(extra)
                trace.append(item)
                return ev

            def dump():
                Path(jb.worker_dir).mkdir(parents=True, exist_ok=True)
                (Path(jb.worker_dir) / "probe_trace.json").write_text(json.dumps(trace))

            try:
                task_list = list(getattr(env, "task_list", []) or [])
                if not task_list:
                    raise official.DatasetGenerationError(f"{jb.task}/episode_{jb.episode}: task_list is empty")
                for entry in task_list:
                    solve = entry.get("solve")
                    name = entry.get("name")
                    snap("before", name)
                    try:
                        result = solve(record_env, planner)
                    except BaseException as exc:
                        trace.append({"tag": "raise", "task": name, "error_type": type(exc).__name__, "error": str(exc)[:200],
                                      "steps": int(env.elapsed_steps[0]) if hasattr(env.elapsed_steps, "__len__") else int(env.elapsed_steps)})
                        raise
                    if official._is_failure(result):
                        trace.append({"tag": "solve_-1", "task": name})
                        raise official.PlannerExhausted(f"{jb.task}/episode_{jb.episode}: solve returned -1")
                    evaluation = snap("after", name)
                    if official._runtime_bool(evaluation.get("fail", False), torch_module):
                        raise official.DatasetGenerationError(f"{jb.task}/episode_{jb.episode}: environment reported failure")
                    if official._runtime_bool(evaluation.get("success", False), torch_module):
                        return
                evaluation = snap("final", None)
                if not official._runtime_bool(evaluation.get("success", False), torch_module):
                    raise official.DatasetGenerationError(f"{jb.task}/episode_{jb.episode}: did not succeed after the complete task_list")
            finally:
                dump()

        official._execute_tasks = traced_execute
        official._probe_c_patched = True
    import train_split_worker
    t0 = time.time()
    res = train_split_worker.run_one((job, config, spec, True))
    res["wall_s"] = round(time.time() - t0, 1)
    p = Path(job.worker_dir) / "probe_steps.json"
    if p.exists():
        res["probe"] = json.loads(p.read_text())
    tp = Path(job.worker_dir) / "probe_trace.json"
    if tp.exists():
        res["trace"] = json.loads(tp.read_text())
    rp = Path(job.worker_dir) / "spec_replay.json"
    if rp.exists():
        r = json.loads(rp.read_text())
        res["spec_binding"] = {"mismatch_paths": sorted({m["path"] for m in r.get("mismatches", [])}),
                               "unused": r.get("unused")}
    import shutil
    shutil.rmtree(job.worker_dir, ignore_errors=True)   # GL 版：逐局产物即刻删除，不留大文件
    return res
