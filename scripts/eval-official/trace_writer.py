"""每局轨迹记录 ``trace.jsonl``（1003-oracle-subgoal-groundsg-eval-plan.md 第二部分 1.7）。

本文件先由主会话以「接口桩」形式提交（计划 1.8），S3～S5 的原侧／新侧驱动按这里的签名与字段约定调用；
S7 合入时补全实现与测试，签名与字段名不改。第二档对比工具 ``gate2_compare.py`` 只读本文件写出的字段。

文件格式：一局一个 ``trace.jsonl``，逐行一个 JSON 对象，``kind`` 区分行类型：

- ``header``（恰好一行，第一行）：``route``、``identity``（task / source_episode / seed / tier / dataset 等，
  由调用方给出）、``max_steps``、``schema``。
- ``demo``（恰好一行，紧随 header；无演示时 ``frames=0``）：演示帧数、逐帧 front／wrist 画面 sha256、
  演示阶段的状态与文本。
- ``request``：发给模型的每次请求（GroundSG 的 ``reset``／``add_buffer``／``infer``，PonderPounce 的每个协议帧，
  Astra 的规划／监视请求）规范化字节的 sha256 与字节数、``step``（发生在第几步之前）。
- ``response``：模型返回的完整动作块（``array_record``）。
- ``step``：每执行一步一行：``step``（从 1 计）、``front_sha256``、``wrist_sha256``、``state``、``action``
  （均为 ``array_record``：原始 dtype、shape、sha256，另附 float32×8 的 hex 便于人读）、``subgoal``、
  ``terminated``、``truncated``、``status``。画面哈希在画面进入视频编码器之前计算。
- ``history``：历史缓冲边界（如 MME ``add_buffer`` 覆盖的步号区间）。
- ``end``（恰好一行，最后一行）：``status``、``exec_steps``、``terminal_reason`` 与调用方附加字段。

``identical_trace`` 的含义只限于上述字段逐项相等（报告里照此写明覆盖范围）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = "sgeval-trace/1"


def image_sha256(img: Any) -> str | None:
    """画面的 sha256：按原始 dtype、shape 的连续字节计算；``None`` 原样返回 ``None``。"""
    if img is None:
        return None
    arr = np.ascontiguousarray(np.asarray(img))
    h = hashlib.sha256()
    h.update(f"{arr.dtype.str}|{arr.shape}|".encode())
    h.update(arr.tobytes())
    return h.hexdigest()


def array_record(x: Any) -> dict | None:
    """数组的身份记录：``{"dtype","shape","sha256","f32hex"}``；不先转 float32 再哈希。

    ``f32hex`` 只为人读：展平后转 float32 的前 8 个值的 hex，不参与相等判定。
    """
    if x is None:
        return None
    arr = np.ascontiguousarray(np.asarray(x))
    h = hashlib.sha256()
    h.update(arr.tobytes())
    flat = arr.reshape(-1)
    head = flat[:8].astype(np.float32) if flat.dtype.kind in "fiub" else np.zeros(0, np.float32)
    return {"dtype": arr.dtype.str, "shape": list(arr.shape), "sha256": h.hexdigest(), "f32hex": head.tobytes().hex()}


def bytes_record(payload: bytes) -> dict:
    """请求的规范化字节记录：``{"sha256","nbytes"}``。"""
    return {"sha256": hashlib.sha256(payload).hexdigest(), "nbytes": len(payload)}


class TraceWriter:
    """一局一个实例；按调用顺序逐行追加，``close`` 写 ``end`` 行。上下文管理器退出时未 close 则以 ``status="error"`` 收尾。"""

    def __init__(self, path: str | Path, *, route: str, identity: dict, max_steps: int) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")
        self._closed = False
        self.exec_steps = 0
        self._write({"kind": "header", "schema": SCHEMA, "route": route, "identity": identity, "max_steps": int(max_steps)})
        self._demo_written = False

    def _write(self, row: dict) -> None:
        self._fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        self._fh.flush()

    def log_demo(self, fronts: list, wrists: list, states: list | None = None, texts: list | None = None) -> None:
        """演示阶段（只调一次）：逐帧画面哈希、状态与文本。"""
        assert not self._demo_written, "log_demo 只能调用一次"
        self._demo_written = True
        self._write({
            "kind": "demo",
            "frames": len(fronts),
            "front_sha256": [image_sha256(f) for f in fronts],
            "wrist_sha256": [image_sha256(w) for w in wrists],
            "states": [array_record(s) for s in (states or [])],
            "texts": list(texts or []),
        })

    def log_request(self, name: str, payload: bytes, *, step: int) -> None:
        """发给模型的一次请求；``payload`` 为调用方规范化后的字节（如 msgpack 序列化结果）。"""
        self._write({"kind": "request", "name": name, "step": int(step), **bytes_record(payload)})

    def log_response(self, actions: Any, *, step: int) -> None:
        """模型返回的完整动作块。"""
        self._write({"kind": "response", "step": int(step), "actions": array_record(actions)})

    def log_history(self, start_step: int, end_step: int, *, note: str = "") -> None:
        """历史缓冲边界（闭区间步号）。"""
        self._write({"kind": "history", "start": int(start_step), "end": int(end_step), "note": note})

    def log_step(self, *, step: int, front: Any, wrist: Any, state: Any, action: Any, subgoal: str | None,
                 terminated: bool, truncated: bool, status: str | None) -> None:
        """执行完第 ``step`` 步（从 1 计）后的一行；画面为执行后的观测。"""
        if not self._demo_written:
            self.log_demo([], [])
        self.exec_steps = max(self.exec_steps, int(step))
        self._write({
            "kind": "step", "step": int(step),
            "front_sha256": image_sha256(front), "wrist_sha256": image_sha256(wrist),
            "state": array_record(state), "action": array_record(action),
            "subgoal": subgoal, "terminated": bool(terminated), "truncated": bool(truncated), "status": status,
        })

    def close(self, *, status: str, terminal_reason: str | None = None, **extra: Any) -> None:
        if self._closed:
            return
        if not self._demo_written:
            self.log_demo([], [])
        self._write({"kind": "end", "status": status, "exec_steps": self.exec_steps,
                     "terminal_reason": terminal_reason, **extra})
        self._fh.close()
        self._closed = True

    def __enter__(self) -> "TraceWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._closed:
            self.close(status="error", terminal_reason=f"exception:{exc_type.__name__}" if exc_type else "unclosed")


def read_trace(path: str | Path) -> list[dict]:
    """读回一局轨迹（供 gate2_compare 与测试使用）。"""
    with Path(path).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
