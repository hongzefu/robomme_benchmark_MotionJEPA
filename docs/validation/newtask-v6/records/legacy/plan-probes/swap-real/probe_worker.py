"""swap-real 探针 worker：在 spawn 子进程内安装 s5_patch（arm=s5）或只装只读记录钩子（arm=v5 对照），
再调用 scripts/parity/train_split_worker.run_one（V5 正式生成用的同一镜像 worker；无规格、导出模式、关 recovery）。
另两处只读补丁：RobommeRecordWrapper.close 之前抓取交换相关状态；_execute_tasks 逐句同逻辑、多记逐子任务轨迹。"""
import json
import os
import shutil
import sys
import time
from pathlib import Path


def _i(v):
    try:
        return int(v[0]) if hasattr(v, "__len__") else int(v)
    except Exception:  # noqa: BLE001
        return None


def _capture(env):
    info = {"elapsed_steps": _i(env.elapsed_steps)}
    objs = list(getattr(env, "spawned_bins", None) or getattr(env, "spawned_cubes", None) or [])
    sched = list(getattr(env, "swap_schedule", []) or [])
    ex = []
    for a, b, s, e in sched:
        ex.append([objs.index(a) if a in objs else None, objs.index(b) if b in objs else None, int(s), int(e)])
    info["executed_pairs"] = ex
    info["n_swaps"] = int(getattr(env, "swap_times", len(sched)))
    info["n_objs"] = len(objs)
    info["s5"] = {k: v for k, v in (getattr(env, "_s5_info", None) or {}).items()}
    rc = list(getattr(env, "_runtime_checks", []) or [])
    sw = [c for c in rc if c.get("kind") == "swap_sweep"]
    info["sweep_checks"] = [{"k": c.get("sweep_index"), "ok": c.get("rejection") is None, "min_g_m": c.get("min_g_m"),
                             "inner_pair": c.get("inner_pair"), "outer_pair": c.get("outer_pair"),
                             "mismatch": c.get("inner_partner_mismatch")} for c in sw]
    info["sweep_rejections"] = [c.get("rejection") for c in sw if c.get("rejection") is not None]
    info["probe_ctrl"] = getattr(env, "_probe_ctrl", None)
    info["probe_ctrl_err"] = getattr(env, "_probe_ctrl_err", None)
    op = getattr(env, "distractor_swap_pairs", None)
    info["outer_pairs"] = [[int(o), int(p)] for o, p in op] if op else None
    db = getattr(env, "distractor_bins", None)
    info["n_outer"] = len(db) if db else 0
    info["predicted_inner"] = [list(map(int, p)) for p in (getattr(env, "predicted_inner_swap_pairs", None) or [])]
    return info


def run(payload):
    job, config, arm = payload
    os.environ["CUDA_VISIBLE_DEVICES"] = job.gpu
    src = str(Path(job.repo_root) / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import s5_patch
    if not getattr(s5_patch, "_installed", False):
        s5_patch.install(arm)
        s5_patch._installed = True
    from robomme.env_record_wrapper import RobommeRecordWrapper
    if not getattr(RobommeRecordWrapper, "_swapreal_patched", False):
        orig_close = RobommeRecordWrapper.close

        def close(self):
            try:
                info = _capture(self.unwrapped)
            except Exception as exc:  # noqa: BLE001
                info = {"capture_error": repr(exc)}
            try:
                Path(self._probe_dir).mkdir(parents=True, exist_ok=True)
                (Path(self._probe_dir) / "probe_capture.json").write_text(json.dumps(info, default=str))
            except Exception:  # noqa: BLE001
                pass
            return orig_close(self)
        RobommeRecordWrapper.close = close
        RobommeRecordWrapper._swapreal_patched = True
    RobommeRecordWrapper._probe_dir = job.worker_dir
    import generate_dataset as official
    if not getattr(official, "_swapreal_patched", False):
        def traced_execute(record_env, planner, torch_module, jb):
            """与官方 _execute_tasks 逐句同逻辑，只多记逐子任务轨迹（worker_dir/probe_trace.json）。"""
            trace = []
            env = record_env.unwrapped

            def snap(tag, name):
                ev = env.evaluate(solve_complete_eval=True)
                trace.append({"tag": tag, "task": name, "steps": _i(env.elapsed_steps),
                              "success": official._runtime_bool(ev.get("success", False), torch_module),
                              "fail": official._runtime_bool(ev.get("fail", False), torch_module)})
                return ev

            def dump():
                Path(jb.worker_dir).mkdir(parents=True, exist_ok=True)
                (Path(jb.worker_dir) / "probe_trace.json").write_text(json.dumps(trace))
            try:
                task_list = list(getattr(env, "task_list", []) or [])
                if not task_list:
                    raise official.DatasetGenerationError(f"{jb.task}/episode_{jb.episode}: task_list is empty")
                for entry in task_list:
                    solve = entry.get("solve"); name = entry.get("name")
                    snap("before", name)
                    try:
                        result = solve(record_env, planner)
                    except BaseException as exc:
                        trace.append({"tag": "raise", "task": name, "error_type": type(exc).__name__,
                                      "error": str(exc)[:300], "steps": _i(env.elapsed_steps)})
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
        official._swapreal_patched = True
    import train_split_worker
    t0 = time.time()
    res = train_split_worker.run_one((job, config, None, True))
    res["wall_s"] = round(time.time() - t0, 1)
    res["arm"] = arm
    for name, key in (("probe_capture.json", "capture"), ("probe_trace.json", "trace")):
        p = Path(job.worker_dir) / name
        if p.exists():
            res[key] = json.loads(p.read_text())
    if not res.get("ok"):
        res["traceback_tail"] = (res.get("traceback") or "")[-1500:]
    res.pop("traceback", None)
    if os.environ.get("SWAPREAL_KEEP") != "1":
        shutil.rmtree(job.worker_dir, ignore_errors=True)   # 逐局产物即刻删除，不留大文件
    return res
