"""旧官方 MME 客户端的包装启动器：同进程 runpy 运行官方 ``examples/robomme/eval.py``，外挂只读钩子录制。

用法（cwd = 官方工作树 examples/robomme，REC_ROOT 必设）：
    python mme_client_wrap.py eval.py --args.host=127.0.0.1 --args.port=<代理端口> ...（参数原样透传给 eval.py）
    python mme_client_wrap.py --v75-preflight   # 只装钩子并核对导入，不跑评估

钩子（方案 §2.5「钩子铁律」：只复制主机端 numpy、不调随机函数、不做 GPU 运算、不改参数与返回值）：
- ``EnvRunner.get_init_obs``：reset 返回的全部演示帧 + 初始帧（前视、腕部）、8 维状态、task_goal；
  调用期间录制器处于 reset 阶段（只入队、不编码）。
- ``EnvRunner.step``：实际交给 env 的动作（调用前复制）与返回的 (img, wrist, state)、stop、status。
- ``websockets.sync.client.ClientConnection.send/recv``：每条发出／收到消息的帧类型、长度、sha256，
  写 ``REC_ROOT/client-transport-<pid>.jsonl``，供 transparency_check.py 与代理日志逐条对账。
- 局边界：``EpisodeEvaluator.eval_each_episode``（在 eval.py 调 ``tyro.cli`` 时从 ``__main__`` 取类挂上），
  每局一个 EpisodeRecorder 目录 ``<task>_<source_episode>_<seed>``。

钩子都在对应模块首次导入完成后才挂（PostImportHooks），不提前导入任何官方模块，导入顺序与直接运行一致。
钩子内部任何异常只记一行 ``OBSERVER_HOOK_ERROR``，绝不影响官方逻辑。
"""
from __future__ import annotations

import os
import runpy
import sys
import threading
import time
import traceback
from pathlib import Path

import numpy as np

_OBS_DIR = str(Path(__file__).resolve().parent)
if _OBS_DIR not in sys.path:
    sys.path.append(_OBS_DIR)
import _v75_obs_common as C  # noqa: E402

R = C.load_recorder()

_lock = threading.RLock()
_state = {"rec": None, "ep": None, "step": 0, "conn_seq": 0, "log": None, "root": None}


def _hook_error(where: str) -> None:
    print(f"OBSERVER_HOOK_ERROR where={where} {traceback.format_exc(limit=3)!r}", flush=True)


def _log():
    if _state["log"] is None:
        _state["log"] = C.JsonlLog(_state["root"] / f"client-transport-{os.getpid()}.jsonl")
    return _state["log"]


# ------------------------------------------------------------------ EnvRunner 钩子

def _patch_env_runner(mod) -> None:
    cls = mod.EnvRunner
    orig_init, orig_step = cls.get_init_obs, cls.step

    def get_init_obs(self):
        rec = _state["rec"]
        try:
            if rec is not None:
                rec.set_phase("reset")
        except Exception:
            _hook_error("get_init_obs.pre")
        out = orig_init(self)
        try:
            if rec is not None:
                fi = rec.add_frames("front", np.stack([np.asarray(x) for x in out["images"]]), tag="reset")
                wi = rec.add_frames("wrist", np.stack([np.asarray(x) for x in out["wrist_images"]]), tag="reset")
                st = np.stack([np.asarray(x) for x in out["states"]])
                rec.add_array("reset_state", st)
                rec.add_event({"kind": "reset", "env_id": self.env_id, "episode_id": self.episode_id,
                               "task_goal": out["task_goal"], "n_frames": len(fi), "front_idx": [fi[0], fi[-1]],
                               "wrist_idx": [wi[0], wi[-1]], "state_sha256": R.array_sha256(st),
                               "difficulty": getattr(self, "difficulty", None)})
                rec.set_phase("run")
        except Exception:
            _hook_error("get_init_obs.post")
        return out

    def step(self, action):
        rec = _state["rec"]
        a = None
        try:
            if rec is not None:
                a = np.array(action, copy=True)
        except Exception:
            _hook_error("step.pre")
        out = orig_step(self, action)
        try:
            if rec is not None:
                with _lock:
                    k = _state["step"]
                    _state["step"] += 1
                (img, wrist, state), stop, status = out
                ev = {"kind": "step", "k": k, "stop": bool(stop), "status": status}
                if a is not None:
                    rec.add_array("exec_action", a, step=k)
                    ev["action_sha256"] = R.array_sha256(a)
                if img is not None:
                    ev["front_idx"] = rec.add_frames("front", np.asarray(img), tag="step")[0]
                    ev["wrist_idx"] = rec.add_frames("wrist", np.asarray(wrist), tag="step")[0]
                    s = np.asarray(state)
                    rec.add_array("state", s, step=k)
                    ev["state_sha256"] = R.array_sha256(s)
                else:
                    ev["obs_none"] = True
                rec.add_event(ev)
        except Exception:
            _hook_error("step.post")
        return out

    cls.get_init_obs, cls.step = get_init_obs, step
    cls._v75_hooked = True


# ------------------------------------------------------------------ websocket 钩子

def _conn_id(ws) -> int:
    cid = getattr(ws, "_v75_conn", None)
    if cid is None:
        with _lock:
            cid = _state["conn_seq"]
            _state["conn_seq"] += 1
        ws._v75_conn = cid
        ws._v75_idx = {"send": 0, "recv": 0}
    return cid


def _note_msg(ws, direction: str, msg) -> None:
    try:
        cid = _conn_id(ws)
        idx = ws._v75_idx[direction]
        ws._v75_idx[direction] += 1
        ftype, n, sha = C.payload_sha(msg)
        ep = _state["ep"]
        _log().write({"pid": os.getpid(), "conn": cid, "dir": direction, "idx": idx, "type": ftype, "len": n,
                      "sha256": sha, "t": time.time(), "episode": ep})
        rec = _state["rec"]
        if rec is not None:
            rec.add_event({"kind": "ws", "conn": cid, "dir": direction, "idx": idx, "type": ftype, "len": n,
                           "sha256": sha})
    except Exception:
        _hook_error(f"ws.{direction}")


def _patch_ws(mod) -> None:
    cls = mod.ClientConnection
    orig_send, orig_recv = cls.send, cls.recv

    def send(self, message, *args, **kwargs):
        r = orig_send(self, message, *args, **kwargs)
        _note_msg(self, "send", message)  # 先发出再记账：sha 计算与 server 计算重叠
        return r

    def recv(self, *args, **kwargs):
        msg = orig_recv(self, *args, **kwargs)
        _note_msg(self, "recv", msg)
        return msg

    cls.send, cls.recv = send, recv
    cls._v75_hooked = True


# ------------------------------------------------------------------ 局边界

def _patch_evaluator(main_mod, seeds: dict) -> None:
    cls = main_mod.EpisodeEvaluator
    orig = cls.eval_each_episode

    def eval_each_episode(self, env_runner, *args, **kwargs):
        rec = None
        try:
            task, ep = env_runner.env_id, int(env_runner.episode_id)
            seed = seeds.get((task, ep), -1)
            d = C.episode_dir(_state["root"], task, ep, seed)
            rec = R.EpisodeRecorder(d, {"policy": "mme", "side": "official-observer", "task": task,
                                        "source_episode": ep, "seed": seed, "never_degrade": True,
                                        "argv": sys.argv, "host": os.uname().nodename},
                                    fps=30)
            with _lock:
                _state.update(rec=rec, ep=d.name, step=0)
        except Exception:
            _hook_error("episode.open")
        ret, exc = None, None
        try:
            ret = orig(self, env_runner, *args, **kwargs)
            return ret
        except BaseException as e:
            exc = f"{type(e).__name__}: {e}"
            raise
        finally:
            with _lock:
                _state.update(rec=None, ep=None)
            if rec is not None:
                try:
                    res = rec.close({"return": ret, "exception": exc, "steps": getattr(self, "last_steps", None),
                                     "env_steps_recorded": _state["step"]})
                    line = R.verdict_line(res)
                    print(f"{line} episode={rec.out_dir.name} encode_cpu_s={res['encode_cpu_s']} "
                          f"queue_wait_s={res['queue_wait_s']} finalize_s={res['finalize_s']}", flush=True)
                    C.JsonlLog(_state["root"] / "recorder-index.jsonl").write(
                        {"episode": rec.out_dir.name, "return": ret, "exception": exc,
                         **{k: res[k] for k in ("RECORDER_VERIFY", "frames", "encoded_frames", "bytes",
                                                "decode_mismatch", "dropped", "reordered", "encode_cpu_s",
                                                "queue_wait_s", "finalize_s", "level")}})
                except Exception:
                    _hook_error("episode.close")

    cls.eval_each_episode = eval_each_episode
    cls._v75_hooked = True


def _patch_tyro(mod, seeds: dict) -> None:
    orig_cli = mod.cli

    def cli(*args, **kwargs):
        main_mod = sys.modules.get("__main__")
        try:
            if main_mod is not None and hasattr(main_mod, "EpisodeEvaluator"):
                _patch_evaluator(main_mod, seeds)
            else:
                print("OBSERVER_HOOK_ERROR where=tyro.cli 找不到 __main__.EpisodeEvaluator", flush=True)
        except Exception:
            _hook_error("tyro.cli")
        return orig_cli(*args, **kwargs)

    mod.cli = cli


def install(argv: list[str]) -> None:
    _state["root"] = C.rec_root()
    seeds = C.manifest_seeds(C.parse_flag(argv, ("--args.episode_manifest", "--args.episode-manifest")))
    C.PostImportHooks({
        "env_runner": _patch_env_runner,
        "websockets.sync.client": _patch_ws,
        "tyro": lambda m: _patch_tyro(m, seeds),
    }).install()


def main() -> None:
    argv = sys.argv[1:]
    if argv[:1] == ["--v75-preflight"]:
        install([])
        sys.path[0] = os.getcwd()
        import robomme  # noqa: F401
        import env_runner
        import websockets.sync.client as wsc

        assert getattr(env_runner.EnvRunner, "_v75_hooked", False), "EnvRunner 未挂钩"
        assert getattr(wsc.ClientConnection, "_v75_hooked", False), "ClientConnection 未挂钩"
        assert "robomme_hard" not in sys.modules
        R.check_encode_cpus()
        print(f"OBSERVER_PREFLIGHT=PASS robomme={robomme.__file__} recorder={R.__file__} ffmpeg={R.find_ffmpeg()} "
              f"encode_cpus={os.environ.get('V75_ENCODE_CPUS', '')}", flush=True)
        return
    if not argv or not argv[0].endswith(".py"):
        raise SystemExit("用法：mme_client_wrap.py eval.py [eval.py 参数...]")
    script = os.path.abspath(argv[0])
    install(argv[1:])
    # 与 ``python eval.py`` 一致：sys.path[0] 为脚本所在目录，sys.argv 为 [eval.py, 参数...]
    sys.path[0] = os.path.dirname(script)
    sys.argv = [argv[0]] + argv[1:]
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
