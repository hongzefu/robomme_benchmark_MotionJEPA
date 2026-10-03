"""旧官方 SimpleMemVLA 评估的包装启动器：同进程执行 ``robomme_sim.eval_success``，外挂只读钩子录制。

用法（cwd = 官方工作树根，REC_ROOT 必设；参数与 ``python -m robomme_sim.eval_success`` 完全相同）：
    python smvla_wrap.py --pretrained_checkpoint ... --episode_manifest M --shard 0/1 --episode_log L --resume
    python smvla_wrap.py --v75-preflight

钩子（方案 §2.5「钩子铁律」：只复制主机端 numpy、不调随机函数、不做 GPU 运算、不改参数与返回值；线程安全，
环境在 InProcSimPool 的线程池里跑，录制只在主线程）：
- ``InProcSimPool.reset``（主线程，fut.result 之后）：reset 返回的全部演示帧 + 初始帧（前视、腕部）、8 维状态、
  instruction；调用期间录制器处于 reset 阶段（只入队、不编码）。
- ``InProcSimPool.step``（主线程，fut.result 之后）：派发的动作块原样、实际执行的各行
  ``np.asarray(row, float64).reshape(-1)[:8]``（按返回的 consumed 截取，与 ``SimEnvService.step``／
  ``RoboMMESimEnv.step_one`` 的换算逐字相同）、返回的帧与状态、consumed/done/status。
  钩子不进环境线程，不占 step_timeout／reset_timeout 的计时。
- ``BatchedEvalPolicy.generate_batch``：输出 actions_unnorm 与子任务文本；输入里 CPU 张量记 sha256，
  GPU 张量（如 state_norm）跳过、不做 ``.cpu()``。
- 局边界：包 ``run_group``（evaluate_manifest 的逐行循环里每行调一次，specs 给出 task 与 episode）。

⚠ 与 ``-m`` 直接运行的唯一差别：为了在 ``main()`` 之前把 ``run_group`` 换成包装，本启动器用
importlib 以模块本名 ``robomme_sim.eval_success`` 执行模块体（此时 ``if __name__ == "__main__"`` 不触发），
替换活模块命名空间里的 ``run_group`` 后再调用同一个 ``main()``（见 ``run_observed``）。模块源码、参数解析、种子设置位置都不变。
"""
from __future__ import annotations

import hashlib
import os
import sys
import threading
import traceback
from pathlib import Path

import numpy as np

_OBS_DIR = str(Path(__file__).resolve().parent)
if _OBS_DIR not in sys.path:
    sys.path.append(_OBS_DIR)
import _v75_obs_common as C  # noqa: E402

R = C.load_recorder()

_lock = threading.RLock()
_state = {"rec": None, "step": 0, "decision": 0, "root": None}


def _hook_error(where: str) -> None:
    print(f"OBSERVER_HOOK_ERROR where={where} {traceback.format_exc(limit=3)!r}", flush=True)


def _tensor_sha(t) -> str | None:
    """CPU 张量的 sha256（字节 + dtype + shape）；GPU 张量返回 None（不做设备拷贝）。"""
    if getattr(t, "is_cuda", False) or getattr(getattr(t, "device", None), "type", "cpu") != "cpu":
        return None
    import torch

    b = t.detach().contiguous().reshape(-1).view(torch.uint8).numpy().tobytes()
    h = hashlib.sha256(b)
    h.update(str(t.dtype).encode())
    h.update(repr(tuple(t.shape)).encode())
    return h.hexdigest()


def _hash_inputs(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "policy":
                continue
            out.update(_hash_inputs(v, f"{prefix}{k}/"))
    elif isinstance(obj, (list, tuple)):
        # Python 列表不逐元素递归（可能很长）：纯标量列表整体取 repr 的 sha256 一次；
        # 含张量等对象时只记类型与长度（张量的 repr 会触发设备拷贝，禁止）
        if all(isinstance(x, (int, float, str, bool, type(None))) for x in obj):
            out[prefix.rstrip("/")] = "repr:" + hashlib.sha256(repr(obj).encode()).hexdigest()
        else:
            out[prefix.rstrip("/")] = f"list:len={len(obj)} types={sorted({type(x).__name__ for x in obj})}"
    elif hasattr(obj, "detach"):
        s = _tensor_sha(obj)
        out[prefix.rstrip("/")] = s if s is not None else "skipped:gpu"
    elif isinstance(obj, np.ndarray):
        out[prefix.rstrip("/")] = R.array_sha256(obj)
    return out


# ------------------------------------------------------------------ 环境钩子（主线程）

def _record_reset(rec, i: int, spec: dict, r) -> None:
    ev = {"kind": "reset", "slot": i, "payload": dict(spec), "ok": bool(isinstance(r, dict) and r.get("ok"))}
    if ev["ok"]:
        fi = rec.add_frames("front", np.stack([np.asarray(f["front"]) for f in r["frames"]]), tag="reset")
        wi = rec.add_frames("wrist", np.stack([np.asarray(f["wrist"]) for f in r["frames"]]), tag="reset")
        st = np.stack([np.asarray(x) for x in r["states"]])
        rec.add_array("reset_state", st)
        ev.update(instruction=r["instruction"], n_frames=len(fi), front_idx=[fi[0], fi[-1]],
                  wrist_idx=[wi[0], wi[-1]], state_sha256=R.array_sha256(st), max_steps=r.get("max_steps"))
    else:
        ev["reason"] = r.get("reason") if isinstance(r, dict) else repr(r)
    rec.add_event(ev)


def _record_step(rec, i: int, chunk, r) -> None:
    with _lock:
        k = _state["step"]
        _state["step"] += 1
    ev = {"kind": "step", "k": k, "slot": i}
    if not isinstance(r, dict) or "error" in r:
        ev["pool_error"] = r.get("error") if isinstance(r, dict) else repr(r)
    else:
        ev.update(consumed=int(r.get("consumed", 0)), done=r.get("done"), success=r.get("success"),
                  status=r.get("status"), error_message=r.get("error_message"), n_frames=len(r.get("frames", [])))
    if chunk is not None:
        c = np.array(chunk, copy=True)
        rec.add_array("action_chunk", c, step=k)
        n = ev.get("consumed", 0)
        # 与 SimEnvService.step / RoboMMESimEnv.step_one 的换算逐字相同：先整体 float64，再逐行 reshape(-1)[:8]
        rows = np.asarray(c, dtype=np.float64)
        execd = (np.stack([np.asarray(a, dtype=np.float64).reshape(-1)[:8] for a in rows[:n]]) if n
                 else np.zeros((0, 8), np.float64))
        rec.add_array("exec_action", execd, step=k)
        ev["exec_sha256"] = R.array_sha256(execd)
    if isinstance(r, dict) and r.get("frames"):
        ev["front_idx"] = rec.add_frames("front", np.stack([np.asarray(f["front"]) for f in r["frames"]]), tag="step")
        ev["wrist_idx"] = rec.add_frames("wrist", np.stack([np.asarray(f["wrist"]) for f in r["frames"]]), tag="step")
    if isinstance(r, dict) and r.get("states"):
        st = np.stack([np.asarray(x) for x in r["states"]])
        rec.add_array("state", st, step=k)
        ev["state_sha256"] = R.array_sha256(st)
    rec.add_event(ev)


def _patch_pool(mod) -> None:
    """包 InProcSimPool.reset/step：在主线程里、fut.result 返回之后，从返回的 dict 录制；
    不进环境线程，不占 step_timeout／reset_timeout 的计时。"""
    cls = mod.InProcSimPool
    orig_reset, orig_step = cls.reset, cls.step

    def reset(self, specs):
        rec = _state["rec"]
        try:
            if rec is not None:
                rec.set_phase("reset")
        except Exception:
            _hook_error("pool.reset.pre")
        out = orig_reset(self, specs)
        try:
            if rec is not None:
                for i in range(min(len(specs), self.num_envs)):
                    _record_reset(rec, i, specs[i], out[i])
                rec.set_phase("run")
        except Exception:
            _hook_error("pool.reset.post")
        return out

    def step(self, action_chunks, active):
        out = orig_step(self, action_chunks, active)
        rec = _state["rec"]
        try:
            if rec is not None:
                for i in active:
                    if out[i] is None:  # alive=False 的槽位未派发
                        continue
                    _record_step(rec, i, action_chunks[i], out[i])
        except Exception:
            _hook_error("pool.step.post")
        return out

    cls.reset, cls.step = reset, step
    cls._v75_hooked = True


# ------------------------------------------------------------------ 策略输出钩子

def _patch_policy(mod) -> None:
    cls = mod.BatchedEvalPolicy
    orig = cls.generate_batch

    def generate_batch(self, processed_list, state_norm_list):
        rec = _state["rec"]
        hashes = None
        try:
            if rec is not None:
                hashes = [_hash_inputs(p) for p in processed_list]
                hashes_state = [_hash_inputs(s) for s in state_norm_list]
        except Exception:
            _hook_error("generate_batch.pre")
            hashes = None
        out = orig(self, processed_list, state_norm_list)
        try:
            if rec is not None:
                with _lock:
                    d = _state["decision"]
                    _state["decision"] += 1
                texts = []
                for i, (acts, sub) in enumerate(out):
                    rec.add_array("model_action", np.asarray(acts), step=d)
                    texts.append(sub)
                rec.add_event({"kind": "decision", "d": d, "subtask": texts, "input_sha256": hashes,
                               "state_sha256": hashes_state if hashes is not None else None,
                               "action_sha256": [R.array_sha256(np.asarray(a)) for a, _ in out]})
        except Exception:
            _hook_error("generate_batch.post")
        return out

    cls.generate_batch = generate_batch
    cls._v75_hooked = True


# ------------------------------------------------------------------ 局边界

def _wrap_run_group(orig, seeds: dict):
    def run_group(args, pool, batched, buffer_factory, normalize_state, task, specs, *a, **kw):
        rec = None
        try:
            ep = int(specs[0]["episode"])
            seed = seeds.get((task, ep), -1)
            d = C.episode_dir(_state["root"], task, ep, seed)
            rec = R.EpisodeRecorder(d, {"policy": "smvla", "side": "official-observer", "task": task,
                                        "source_episode": ep, "seed": seed, "never_degrade": True,
                                        "argv": sys.argv, "host": os.uname().nodename, "group": len(specs)},
                                    fps=30)
            with _lock:
                _state.update(rec=rec, step=0, decision=0)
        except Exception:
            _hook_error("episode.open")
        ret, exc = None, None
        try:
            ret = orig(args, pool, batched, buffer_factory, normalize_state, task, specs, *a, **kw)
            return ret
        except BaseException as e:
            exc = f"{type(e).__name__}: {e}"
            raise
        finally:
            with _lock:
                _state["rec"] = None
            if rec is not None:
                try:
                    details = kw.get("details")
                    res = rec.close({"return": ret, "exception": exc,
                                     "details": [dict(x) for x in details] if details else None,
                                     "env_steps_recorded": _state["step"], "decisions": _state["decision"]})
                    print(f"{R.verdict_line(res)} episode={rec.out_dir.name} encode_cpu_s={res['encode_cpu_s']} "
                          f"queue_wait_s={res['queue_wait_s']} finalize_s={res['finalize_s']}", flush=True)
                    C.JsonlLog(_state["root"] / "recorder-index.jsonl").write(
                        {"episode": rec.out_dir.name, "exception": exc,
                         **{k: res[k] for k in ("RECORDER_VERIFY", "frames", "encoded_frames", "bytes",
                                                "decode_mismatch", "dropped", "reordered", "encode_cpu_s",
                                                "queue_wait_s", "finalize_s", "level")}})
                except Exception:
                    _hook_error("episode.close")

    return run_group


def install(argv: list[str]) -> dict:
    _state["root"] = C.rec_root()
    seeds = C.manifest_seeds(C.parse_flag(argv, ("--episode_manifest",)))
    C.PostImportHooks({"robomme_sim.inproc_pool": _patch_pool, "robomme_sim.batched_policy": _patch_policy}).install()
    return seeds


def main() -> None:
    argv = sys.argv[1:]
    # 与 ``python -m`` 一致：sys.path[0] 为当前目录
    sys.path[0] = os.getcwd()
    if argv[:1] == ["--v75-preflight"]:
        install([])
        import robomme_sim.batched_policy as bp
        import robomme_sim.inproc_pool as ip

        assert getattr(ip.InProcSimPool, "_v75_hooked", False) and getattr(bp.BatchedEvalPolicy, "_v75_hooked", False)
        R.check_encode_cpus()
        print(f"OBSERVER_PREFLIGHT=PASS robomme_sim={ip.__file__} recorder={R.__file__} ffmpeg={R.find_ffmpeg()} "
              f"encode_cpus={os.environ.get('V75_ENCODE_CPUS', '')}", flush=True)
        return
    seeds = install(argv)
    run_observed("robomme_sim.eval_success", argv, seeds)


def run_observed(modname: str, argv: list[str], seeds: dict) -> None:
    """执行模块体（__name__ 不是 "__main__"，故不自动调 main），替换活模块命名空间里的 run_group 后调 main()。

    注意不能用 runpy.run_module 的返回值打补丁：它返回的是模块全局变量的副本，函数仍引用原命名空间。
    """
    import importlib.util

    spec = importlib.util.find_spec(modname)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    sys.argv = [spec.origin] + argv
    spec.loader.exec_module(mod)
    mod.run_group = _wrap_run_group(mod.run_group, seeds)
    mod.main()


if __name__ == "__main__":
    main()
