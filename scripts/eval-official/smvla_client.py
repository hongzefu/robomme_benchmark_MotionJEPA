"""SimpleMemVLA 新接口客户端（v7.5eval 方案 §2.3；运行在 benchmark .venv）。

``run_episode(session, identity, conn_info, recorder)`` 逐行复现旧官方
``4e0c04f robomme_sim/eval_success.py::run_group``（组大小 1、details 模式）与
``evaluate_manifest`` 的逐局收尾，以及 ``robomme_sim/robomme_env.py::SimEnvService`` 的
reset/step 打包语义；环境由 ``env_client.EnvSession`` 在本进程建，策略在 smvla_server 进程。

与旧官方的对应（行号指 SimpleMemVLA-official-xhard0 @4e0c04f）：
- reset：SimEnvService.reset（重试 reset_retries=2 次，帧/状态为空算失败，instruction 取
  info["task_goal"][0]）→ 发 reset + observe(全部演示帧 + 初始帧)，cur_state = states[-1] (float32)。
- 决策循环：hard_bound = ceil(max_steps/16)+2（1300 步时 84）；每次决策 infer → chunk =
  actions[:16] → SimEnvService.step 逐行 ``np.asarray(row, float64).reshape(-1)[:8]``，遇
  done / error / obs None 即停；返回帧一律 observe；steps += consumed。
- 终态：环境报 done 取环境 status（error 时带 error_message）；step 抛异常记
  ``step_exc: <e>``（steps 不加本块）；决策用尽而环境未报终态记 timeout，error 为
  ``策略循环 hard_bound=84 用尽，环境未报终态``（steps 通常为 1344）；其余异常记 error + traceback。

纯函数层（encode_frames / encode_states / instruction_from_info / step_chunk / hard_bound）与
IO 层（WSPolicyConn）分开，单测用假 session / 假连接直接驱动。
"""

from __future__ import annotations

import hashlib
import time
import traceback
from typing import Any

import numpy as np

MAX_STEPS = 1300
EXECUTE_HORIZON = 16
RESET_RETRIES = 2
FINAL_STATUSES = ("success", "fail", "timeout")
CAM_FRONT = "front"
CAM_WRIST = "wrist"


class ProtocolError(RuntimeError):
    """消息协议损坏（回包 sha 与发出内容不符、回包缺键）。属运行阻塞。"""


class ServerError(RuntimeError):
    """server 回包 {"error": traceback}：server 侧异常，不是环境结局。"""


# 基础设施故障标记（与 mme_client.INFRA_MARKERS 同表）：只决定 infra 标记（env_client 据此重试），不改 status。
INFRA_MARKERS = ("RecorderError", "svulkan2", "EXCLUSIVE", "Vulkan", "vk::", "out of memory", "RESOURCE_EXHAUSTED",
                 "CUDA_ERROR", "ConnectionClosed", "ConnectionRefused", "InvalidStatus", "Connection reset")
ENV_RESET_INFRA_MARKERS = ("svulkan2", "EXCLUSIVE", "Vulkan", "vk::")
SERVER_OOM_MARKERS = ("out of memory", "OutOfMemory", "CUDA", "CUBLAS", "cuDNN")


def _marker(text: str | None, markers) -> str | None:
    for m in markers:
        if m in (text or ""):
            return m
    return None


def classify_exception(e: BaseException, tb: str) -> str | None:
    """整局兜底异常 → infra_reason（None 表示非基础设施）。"""
    if isinstance(e, ServerError):
        return "server_oom" if _marker(str(e), SERVER_OOM_MARKERS) else "server_error"
    if isinstance(e, ProtocolError):
        return "protocol"
    try:
        from websockets.exceptions import ConnectionClosed, InvalidHandshake
        if isinstance(e, (ConnectionClosed, InvalidHandshake)):
            return f"connection:{type(e).__name__}"
    except ImportError:
        pass
    if isinstance(e, (OSError, TimeoutError)):  # ConnectionRefusedError / reset / 连接超时
        return f"connection:{type(e).__name__}"
    m = _marker(tb, INFRA_MARKERS)
    return f"marker:{m}" if m else None


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def frame_sha(frame: np.ndarray) -> str:
    """单帧指纹（与 recorder.frame_sha256、smvla_server.frame_sha 同一定义）。"""
    return hashlib.sha256(np.ascontiguousarray(frame).tobytes()).hexdigest()


def array_sha(arr: np.ndarray) -> str:
    """数值数组指纹（与 recorder.array_sha256、smvla_server.array_sha 同一定义）。"""
    a = np.ascontiguousarray(arr)
    h = hashlib.sha256(a.tobytes())
    h.update(a.dtype.str.encode())
    h.update(repr(tuple(a.shape)).encode())
    return h.hexdigest()


def hard_bound(max_steps: int = MAX_STEPS, execute_horizon: int = EXECUTE_HORIZON) -> int:
    """照抄 run_group：``max(1, -(-int(args.max_steps) // max(1, args.execute_horizon))) + 2``。"""
    return max(1, -(-int(max_steps) // max(1, execute_horizon))) + 2


def timeout_error(hb: int) -> str:
    return f"策略循环 hard_bound={hb} 用尽，环境未报终态"


# ---- 以下五个函数逐行照抄 robomme_sim/robomme_env.py（c564c17 = 4e0c04f）第 33–75 行 ----
def _to_uint8_hwc(img) -> np.ndarray:
    if hasattr(img, "detach"):
        img = img.detach().cpu().numpy()
    arr = np.asarray(img)
    if arr.ndim == 4 and arr.shape[0] == 1:
        arr = arr[0]
    return arr.astype(np.uint8, copy=False)


def _to_f32(vec) -> np.ndarray:
    if hasattr(vec, "detach"):
        vec = vec.detach().cpu().numpy()
    return np.asarray(vec, dtype=np.float32).reshape(-1)


def encode_frames(obs: dict) -> list[dict[str, np.ndarray]]:
    fronts = obs["front_rgb_list"]
    wrists = obs["wrist_rgb_list"]
    return [
        {CAM_FRONT: _to_uint8_hwc(f), CAM_WRIST: _to_uint8_hwc(w)}
        for f, w in zip(fronts, wrists)
    ]


def encode_states(obs: dict) -> list[np.ndarray]:
    joints = obs["joint_state_list"]
    grippers = obs["gripper_state_list"]
    states = []
    for j, g in zip(joints, grippers):
        jv = _to_f32(j)[:7]
        gv = _to_f32(g)
        g0 = gv[:1] if gv.size else np.zeros(1, dtype=np.float32)
        states.append(np.concatenate([jv, g0]).astype(np.float32))
    return states


def _scalar(x) -> float:
    if hasattr(x, "item"):
        try:
            return float(x.item())
        except Exception:
            return float(np.asarray(x.detach().cpu() if hasattr(x, "detach") else x).reshape(-1)[0])
    return float(x)
# ---- 照抄结束 ----


def instruction_from_info(info: dict, task_name: str) -> str:
    """照抄 SimEnvService.reset 取 instruction 的分支。"""
    task_goal = info.get("task_goal")
    if isinstance(task_goal, (list, tuple)) and task_goal:
        return str(task_goal[0])
    return str(task_goal) if task_goal else f"Complete the {task_name} task."


def reset_session(session, task_name: str, retries: int = RESET_RETRIES) -> dict:
    """照抄 SimEnvService.reset：最多 retries+1 次；返回 {ok, instruction, frames, states} 或 {ok: False, reason}。"""
    last_err = "unknown"
    for _attempt in range(retries + 1):
        try:
            obs, info = session.reset()
            frames = encode_frames(obs)
            states = encode_states(obs)
            if not frames or not states:
                raise RuntimeError("reset returned no frames")
            return {"ok": True, "instruction": instruction_from_info(info or {}, task_name),
                    "frames": frames, "states": states, "attempts": _attempt + 1}
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            try:  # 旧：出错后 env.close() 并置空，下一次重建
                session.close()
            except Exception:
                pass
    return {"ok": False, "reason": f"reset_failed: {last_err}"}


def step_chunk(session, action_chunk, on_exec=None) -> dict:
    """照抄 SimEnvService.step + RoboMMESimEnv.step_one（逐行执行、遇 done/error/obs None 即停）。

    on_exec(act8) 在每行交给环境前回调（记录实际执行动作）。
    """
    action_chunk = np.asarray(action_chunk, dtype=np.float64)
    frames, states, consumed = [], [], 0
    error = None
    status = "ongoing"
    done = False
    for action in action_chunk:
        act = np.asarray(action, dtype=np.float64).reshape(-1)
        if act.shape[0] < 8:
            raise ValueError(f"Expected an 8-dim joint_angle action, got shape {act.shape}")
        if on_exec is not None:
            on_exec(act[:8])
        obs, _reward, terminated, truncated, info = session.step(act[:8])
        term = bool(_scalar(terminated)) if terminated is not None else False
        trunc = bool(_scalar(truncated)) if truncated is not None else False
        info = info if isinstance(info, dict) else {}
        status = str(info.get("status", "ongoing"))
        done = term or trunc or status in ("success", "fail", "timeout", "error")
        consumed += 1
        if status == "error" or obs is None:
            error = str(info.get("error_message", "env step error"))
            break
        frames.extend(encode_frames(obs))
        states.extend(encode_states(obs))
        if done:
            break
    return {
        "frames": frames,
        "states": states,
        "consumed": consumed,
        "done": bool(done or error is not None),
        "success": status == "success",
        "status": status,
        "error_message": error,
    }


class WSPolicyConn:
    """到 smvla_server 的同步 websocket 连接（msgpack_numpy；compression=None、max_size=None、不走代理）。"""

    def __init__(self, host: str, port: int, open_timeout: float = 600.0):
        from openpi_client import msgpack_numpy
        from websockets.sync.client import connect

        self._m = msgpack_numpy
        self._packer = msgpack_numpy.Packer()
        self._ws = connect(f"ws://{host}:{int(port)}", compression=None, max_size=None, proxy=None,
                           open_timeout=open_timeout, ping_interval=None, ping_timeout=None)
        self.metadata = self._m.unpackb(self._ws.recv())

    def call(self, msg: dict) -> tuple[dict, bytes, bytes]:
        raw = self._packer.pack(msg)
        self._ws.send(raw)
        rep_raw = self._ws.recv()
        if isinstance(rep_raw, str):
            raise ProtocolError(f"server 返回文本帧：{rep_raw[:2000]}")
        return self._m.unpackb(rep_raw), raw, rep_raw

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass


class _NullRecorder:
    def set_phase(self, phase):
        pass

    def add_frames(self, stream, frames, *, tag=""):
        return []

    def add_array(self, name, arr, *, step=None):
        pass

    def add_event(self, event):
        pass


def episode_key(identity: dict) -> str:
    return f"{identity['task']}/{identity['source_episode']}/{identity['seed']}"


def run_episode(session, identity: dict, conn_info: dict, recorder=None, *, conn=None,
                max_steps: int = MAX_STEPS, execute_horizon: int = EXECUTE_HORIZON,
                reset_retries: int = RESET_RETRIES, record_frames: bool | None = None) -> dict:
    """跑一局；返回 {status, task_success, steps, error, decisions, timing, server_meta, protocol}。

    conn：测试注入的假连接（需有 metadata、call(msg)->(reply, raw, rep_raw)、close()）；为 None
    时按 conn_info={"host","port"} 建 WSPolicyConn。session 由调用方构造，本函数不 close。
    """
    rec = recorder if recorder is not None else _NullRecorder()
    # env_client.EnvSession 持有同一 recorder 时，原始帧、exec_action 与 reset/run 阶段已由环境侧记录，
    # 本函数只记策略侧（消息指纹、state、model_action、决策事件），避免重复。
    env_records = recorder is not None and getattr(session, "recorder", None) is recorder
    if record_frames is None:
        record_frames = not env_records
    task = identity["task"]
    hb = hard_bound(max_steps, execute_horizon)
    t_start = time.monotonic()
    timing: dict[str, Any] = {"reset_env_s": None, "infer_ms": [], "rtt_ms": [], "step_env_s": 0.0,
                              "observe_ms": [], "connect_s": None}
    out = {"status": "error", "task_success": False, "steps": 0, "error": None, "decisions": 0,
           "infra": False, "infra_reason": None,
           "hard_bound": hb, "timing": timing, "server_meta": None,
           "protocol": {"messages": 0, "frames_sent": 0, "sha_mismatch": 0}}
    proto = out["protocol"]
    frame_idx = {"front": 0, "wrist": 0}
    own_conn = conn is None

    def record_frames_(frames, tag):
        if not record_frames or not frames:
            return None
        idx = {}
        for cam in (CAM_FRONT, CAM_WRIST):
            idx[cam] = rec.add_frames(cam, np.stack([fr[cam] for fr in frames]), tag=tag)
        return {k: [v[0], v[-1]] if v else [] for k, v in idx.items()}

    def call(kind: str, msg: dict, extra: dict | None = None) -> dict:
        t0 = time.monotonic()
        reply, raw, rep_raw = conn.call(msg)
        rtt = (time.monotonic() - t0) * 1000.0
        proto["messages"] += 1
        ev = {"kind": "msg", "type": kind, "send_sha256": sha256_bytes(raw), "send_bytes": len(raw),
              "recv_sha256": sha256_bytes(rep_raw), "recv_bytes": len(rep_raw), "rtt_ms": round(rtt, 3)}
        if extra:
            ev.update(extra)
        rec.add_event(ev)
        if kind == "infer":
            timing["rtt_ms"].append(round(rtt, 3))
        if not isinstance(reply, dict):
            raise ProtocolError(f"{kind} 回包不是 dict：{type(reply)}")
        if "error" in reply:
            raise ServerError(f"server 报错（{kind}）：{reply['error']}")
        if reply.get("req_sha") != sha256_bytes(raw):
            proto["sha_mismatch"] += 1
            raise ProtocolError(f"{kind} 回包 req_sha 与发出字节不符")
        return reply

    def observe(frames, tag):
        if not frames:
            return
        idx = record_frames_(frames, tag)
        payload = [{CAM_FRONT: fr[CAM_FRONT], CAM_WRIST: fr[CAM_WRIST]} for fr in frames]
        reply = call("observe", {"observe": {"frames": payload}}, {"n_frames": len(frames), "tag": tag,
                                                                   "frame_idx": idx})
        sent = [{CAM_FRONT: frame_sha(fr[CAM_FRONT]), CAM_WRIST: frame_sha(fr[CAM_WRIST])} for fr in frames]
        if reply.get("n") != len(frames) or reply.get("frame_sha") != sent:
            proto["sha_mismatch"] += 1
            raise ProtocolError(f"observe 回包帧指纹与发出不符（发 {len(frames)} 帧，回 {reply.get('n')}）")
        proto["frames_sent"] += len(frames)
        timing["observe_ms"].append(round(float(reply.get("observe_time_ms", 0.0)), 3))

    status = None
    error = None
    steps = 0
    try:
        # ---- reset（旧：pool.reset → SimEnvService.reset）----
        if not env_records:
            rec.set_phase("reset")
        t0 = time.monotonic()
        r = reset_session(session, task, retries=reset_retries)
        timing["reset_env_s"] = round(time.monotonic() - t0, 3)
        if not env_records:
            rec.set_phase("run")
        if not r.get("ok"):
            status, error = "error", f"reset 失败：{r}"[:2000]
            m = _marker(r.get("reason"), ENV_RESET_INFRA_MARKERS)
            if m:
                out.update(infra=True, infra_reason=f"env_reset:{m}")
            rec.add_event({"kind": "reset_failed", "reason": r.get("reason")})
        else:
            rec.add_event({"kind": "reset_ok", "attempts": r["attempts"], "n_frames": len(r["frames"]),
                           "instruction": r["instruction"]})
            if own_conn:
                t0 = time.monotonic()
                conn = WSPolicyConn(conn_info["host"], conn_info["port"])
                timing["connect_s"] = round(time.monotonic() - t0, 3)
            out["server_meta"] = getattr(conn, "metadata", None)
            reply = call("reset", {"reset": {"episode_key": episode_key(identity)}})
            rec.add_event({"kind": "server_rng", "rng": reply.get("rng")})
            instruction = r["instruction"]
            observe(r["frames"], "reset")
            cur_state = np.asarray(r["states"][-1], dtype=np.float32)
            for i, s in enumerate(r["states"]):
                rec.add_array("reset_state", np.asarray(s, dtype=np.float32), step=i - len(r["states"]) + 1)

            success = False
            ended = False
            decisions = 0
            while decisions < hb:
                decisions += 1
                if success:  # 旧：act = [g for g in active if not success[g]]; if not act: break
                    break
                rec.add_array("state", cur_state, step=steps)
                reply = call("infer", {"infer": {"instruction": instruction, "state": cur_state}},
                             {"decision": decisions - 1, "step": steps, "state_sha": array_sha(cur_state)})
                if reply.get("recv_state_sha") != array_sha(cur_state) or \
                        reply.get("recv_instruction_sha") != sha256_bytes(instruction.encode("utf-8")):
                    proto["sha_mismatch"] += 1
                    raise ProtocolError("infer 回包的状态/指令指纹与发出不符")
                timing["infer_ms"].append(round(float(reply["infer_ms"]), 3))
                actions_full = np.asarray(reply["actions_full"])
                rec.add_array("model_action", actions_full, step=steps)
                chunk = np.asarray(reply["actions"])[:execute_horizon]
                if not np.array_equal(chunk, actions_full[:execute_horizon]):
                    raise ProtocolError("infer 回包 actions 与 actions_full[:16] 不符")
                rec.add_event({"kind": "decision", "decision": decisions - 1, "step": steps,
                               "subtask": reply.get("subtask"), "infer_ms": round(float(reply["infer_ms"]), 3),
                               "model_action_sha": array_sha(actions_full)})

                exec_step = [steps]

                def on_exec(act8, _s=exec_step):
                    if not env_records:
                        rec.add_array("exec_action", act8, step=_s[0])
                    _s[0] += 1

                t0 = time.monotonic()
                try:
                    res = step_chunk(session, chunk, on_exec=on_exec)
                except Exception as e:  # 旧：InProcSimPool.step 捕获为 {"error": f"step_exc: {e}"}
                    res = {"error": f"step_exc: {e}"}
                timing["step_env_s"] += time.monotonic() - t0
                if "error" in res:
                    status, error, ended = "error", str(res.get("error")), True
                    m = _marker(error, INFRA_MARKERS)
                    if m:
                        out.update(infra=True, infra_reason=f"env_step:{m}")
                    rec.add_event({"kind": "step_exc", "error": error})
                    break
                observe(res["frames"], "step")
                if res.get("states"):
                    cur_state = np.asarray(res["states"][-1], dtype=np.float32)
                success = bool(res.get("success", False))
                steps += int(res.get("consumed", 0) or 0)
                rec.add_event({"kind": "chunk_done", "decision": decisions - 1, "consumed": res["consumed"],
                               "steps": steps, "status": res["status"], "done": res["done"]})
                if res.get("done", False):
                    status = str(res.get("status") or ("success" if success else "fail"))
                    error = res.get("error_message")
                    ended = True
                    break
            out["decisions"] = decisions
            if not ended:
                status = "success" if success else "timeout"
                error = None if success else timeout_error(hb)
    except Exception as e:
        # 旧：evaluate_manifest 捕获 run_group 异常，error 取 traceback 末 2000 字符，steps 保留
        status = "error"
        tb = traceback.format_exc()
        error = tb[-2000:]
        if isinstance(e, ProtocolError):
            proto["broken"] = True
        reason = classify_exception(e, tb)
        if reason:
            out.update(infra=True, infra_reason=reason)
    finally:
        if own_conn and conn is not None:
            conn.close()
    if status not in FINAL_STATUSES + ("error",):
        error = f"未知终态 {status}；{error}"
        status = "error"
    timing["step_env_s"] = round(timing["step_env_s"], 3)
    timing["episode_s"] = round(time.monotonic() - t_start, 3)
    out.update(status=status, task_success=status == "success", steps=steps, error=error)
    rec.add_event({"kind": "episode_end", "status": status, "steps": steps, "error": error,
                   "decisions": out["decisions"]})
    return out
