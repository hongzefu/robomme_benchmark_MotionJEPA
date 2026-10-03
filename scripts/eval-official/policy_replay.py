#!/usr/bin/env python3
"""v7.5eval 第 4 步：策略本身稳不稳定（开环回放）与新旧接口开环（0929-v7.5eval-restructure-plan.md §3.2 第 4 步、§3.1 开环）。

运行在 benchmark ``.venv``；不建环境，只经 websocket 与已起好的策略 server 通信（0 局、不占 reset）。

子命令：

- ``build-inputs --policy mme|smvla --rec <逐局录制目录> --kind new|official --out <输入目录>``
  从一局录制重建客户端当时发出的有序请求流。做法：把录下的观测（帧经 ``recorder.load_frames`` 无损解码、
  数值数组原样）与录下的模型输出喂给**新接口客户端的原函数**（MME：``mme_client.run_loop`` +
  ``EnvRunnerShim`` + ``pack_buffer``；SMVLA：``smvla_client.run_episode`` + ``encode_frames/encode_states``），
  由假连接逐条截下打包后的字节。官方录制（旧 MME 客户端钩子 + 代理、旧 SMVLA InProcSimPool 钩子）同样
  经新接口客户端重新打包（方案：「官方重跑一最早一片里的一局，经新接口客户端重新打包」）。
  新接口录制：重建字节的 sha256 必须逐条等于录下的发出 sha → ``BUILD_INPUTS=PASS|FAIL mismatch=<n>``；
  官方 MME 录制：与旧客户端钩子录下的线上字节 sha 比（即新旧打包是否逐字节相同，只报告）；
  官方 SMVLA 录制：旧版进程内直传、没有线上字节，只核对解码帧 sha 与录制一致。
  同时把「新客户端逻辑在录下的模型输出上会执行的动作」与录下的实际执行动作比（exec_equal）。
- ``replay --policy --inputs <输入目录> --host --port --repeats N --tag T --out <根>``
  每次重复一条新连接（与客户端每局一条连接相同），先 reset 再按序发；收齐每次推理的完整动作数组，写
  ``<根>/<T>/rep<k>/actions.npz``（键 ``model_action``，形状 [推理次数, H, D]）与 ``timing.json``。
- ``compare --a <rep 目录> --b <rep 目录> --kind replay|iface --cond --policy --mode same|restart|ABA|cache --det on|off``
  逐维平均绝对差、P95、最大绝对差、最大相对差、不相等元素数、首个有差的推理序号（复用 compare.py 的
  ``action_diff``）→ ``POLICY_REPLAY=INFO ...`` / ``IFACE_OPEN=INFO ...``。
- ``iface-open --policy --rec-official <官方逐局录制> [--proxy-rec] [--old-src] [--actions-new <rep 目录>]``
  同一份原始观测分别走旧官方打包（按路径从官方工作树用 ast 取出函数原文执行，不 import 其模块，避免
  cv2/sapien 等重依赖）与新接口打包，比模型输入字节（payload_equal）；相同则模型动作必然相同；
  再比新客户端逻辑在录下的模型输出上执行的动作与官方实际执行动作（维度、顺序、数量、终止位置）→
  ``IFACE_OPEN=INFO policy= payload_equal= action_diff= exec_equal=``。
- ``report --root <run_policy_replay.sh 的输出根> --cond --policy``
  汇总全部比较 JSON 与计时，按方案写死的规则给确定性标志默认值：
  det 开时同卡逐位一致、且单次推理耗时增加不超过 10% → 默认开，否则关 →
  ``DET_RULE=INFO policy= det_bitwise= slowdown_pct= default=<on|off>``，末行 ``POLICY_REPLAY_DONE cond= policy=``。

所有判定行单行；所有 json/jsonl ``sort_keys=True, ensure_ascii=False``。
"""
from __future__ import annotations

import sys
from pathlib import Path as _Path

_HERE = str(_Path(__file__).resolve().parent)
# 本目录只挂在 sys.path 末尾，防止同目录模块遮蔽标准库
sys.path[:] = [p for p in sys.path if p and str(_Path(p).resolve()) != _HERE] + [_HERE]

import argparse  # noqa: E402
import ast  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Callable  # noqa: E402

import numpy as np  # noqa: E402

NFS = Path("/nfs/turbo/coe-chaijy-unreplicated/hongzefu")
# 旧官方源码（只按路径读原文，不 import 模块）
OLD_MME_DIR = NFS / "robomme_policy_learning-official-xhard0" / "examples" / "robomme"
OLD_SMVLA_ENV = NFS / "SimpleMemVLA-official-xhard0" / "robomme_sim" / "robomme_env.py"
DET_SLOWDOWN_MAX_PCT = 10.0  # 方案写死：det 开时推理耗时增加不超过 10%
STEADY_SKIP = 3  # 计推理耗时时跳过每次回放的前 3 次推理（首次编译与预热）


# ───────────────────────────────────────────── 通用小工具


def dumps(obj: Any, indent: int | None = None) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=indent, default=_json_default)


def _json_default(o: Any) -> Any:
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    return repr(o)


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(bytes(b)).hexdigest()


def frame_sha(a: np.ndarray) -> str:
    """单帧／数组字节的 sha256（与 recorder.frame_sha256、mme_client.sha 同一定义）。"""
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def array_sha(a: np.ndarray) -> str:
    """字节 + dtype + shape 的 sha256（与 recorder.array_sha256 同一定义）。"""
    a = np.ascontiguousarray(a)
    h = hashlib.sha256(a.tobytes())
    h.update(a.dtype.str.encode())
    h.update(repr(tuple(a.shape)).encode())
    return h.hexdigest()


def load_module(name: str, alias: str | None = None):
    """按文件路径加载本目录下的模块；alias 不同即得到一份独立副本（用于换入旧官方函数）。"""
    alias = alias or f"v75_{name}"
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, Path(_HERE) / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


def fresh_module(name: str, alias: str):
    """每次都新建一份模块副本（不进 sys.modules 缓存）。"""
    spec = importlib.util.spec_from_file_location(alias, Path(_HERE) / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def packer():
    from openpi_client import msgpack_numpy

    return msgpack_numpy.Packer()


def unpackb(raw: bytes):
    from openpi_client import msgpack_numpy

    return msgpack_numpy.unpackb(raw)


def extract_defs(path: str | Path, names: list[str], extra: dict | None = None) -> dict:
    """从源文件用 ast 取出指定顶层函数／赋值的原文并执行，返回命名空间。不执行模块其余部分（无重依赖）。"""
    src = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    body = []
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            body.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            tn = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(t in names for t in tn):
                body.append(node)
                found.update(t for t in tn if t in names)
    missing = sorted(set(names) - found)
    if missing:
        raise KeyError(f"{path} 里找不到 {missing}")
    ns: dict[str, Any] = {"np": np, "Any": Any, "__name__": f"v75_old_{Path(path).stem}"}
    ns.update(extra or {})
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), ns)  # noqa: S102 只执行官方函数原文
    ns["__source_sha256__"] = hashlib.sha256(src.encode("utf-8")).hexdigest()
    return ns


# ───────────────────────────────────────────── 录制读取 → 统一的逐局轨迹


class Rec:
    """一个 EpisodeRecorder 目录的只读视图。"""

    def __init__(self, d: str | Path):
        self.dir = Path(d)
        self.meta = self._json("meta.json")
        self.summary = self._json("summary.json")
        ev = self.dir / "events.jsonl"
        self.events = [json.loads(l) for l in ev.read_text(encoding="utf-8").splitlines() if l.strip()] if ev.exists() else []
        self.index: dict[str, list[dict]] = {}
        idx = self.dir / "arrays-index.jsonl"
        if idx.exists():
            for line in idx.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.index.setdefault(r["name"], []).append(r)
        for rows in self.index.values():
            rows.sort(key=lambda r: r["k"])
        self._npz = np.load(self.dir / "arrays.npz", allow_pickle=False) if (self.dir / "arrays.npz").exists() else None
        self._frames: dict[str, tuple[list[dict], list]] = {}

    def _json(self, name: str) -> dict:
        p = self.dir / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def arrays(self, name: str) -> list[tuple[int | None, np.ndarray]]:
        """按记录顺序返回 (step, 数组)。"""
        return [(r["step"], np.asarray(self._npz[r["key"]])) for r in self.index.get(name, [])]

    def by_step(self, name: str) -> dict[int, np.ndarray]:
        return {int(s): a for s, a in self.arrays(name) if s is not None}

    def frames(self, stream: str) -> tuple[list[dict], list]:
        if stream not in self._frames:
            rec_mod = load_module("recorder")
            recs, imgs = rec_mod.load_frames(self.dir, stream)
            bad = [r["idx"] for r, im in zip(recs, imgs) if im is None or frame_sha(im) != r["sha256"]]
            if bad:
                raise RuntimeError(f"{self.dir}/{stream} 解码帧缺失或 sha 不符：{bad[:5]}（共 {len(bad)}）")
            self._frames[stream] = (recs, imgs)
        return self._frames[stream]

    def kinds(self, kind: str) -> list[dict]:
        return [e for e in self.events if e.get("kind") == kind]


def _identity(meta: dict) -> dict:
    return {"task": meta.get("task"), "source_episode": meta.get("source_episode"), "seed": meta.get("seed")}


def _step_rec(front, wrist, joint, gripper, *, terminated=False, truncated=False, status="ongoing", obs_none=False,
              exception=None) -> dict:
    return {"front": front, "wrist": wrist, "joint": joint, "gripper": gripper, "terminated": bool(terminated),
            "truncated": bool(truncated), "status": status, "obs_none": bool(obs_none), "exception": exception}


def trace_new(rec: Rec, policy: str) -> dict:
    """新接口录制（env_client.EnvSession + mme_client／smvla_client）→ 轨迹。"""
    frec, fimg = rec.frames("front")
    wrec, wimg = rec.frames("wrist")
    by_tag_f: dict[str, list] = {}
    by_tag_w: dict[str, list] = {}
    for r, im in zip(frec, fimg):
        by_tag_f.setdefault(r["tag"], []).append(im)
    for r, im in zip(wrec, wimg):
        by_tag_w.setdefault(r["tag"], []).append(im)
    resets = rec.kinds("env_reset")
    if not resets:
        raise RuntimeError(f"{rec.dir} 没有 env_reset 事件")
    goal = resets[-1]["task_goal"]
    # 重试过的 reset（smvla reset_retries）只取最后一次：帧按 tag=reset 依次追加，取末尾 frames 个
    n_reset = int(resets[-1]["frames"])
    rj = rec.arrays("reset_joint_state")[-1][1]
    rg = rec.arrays("reset_gripper_state")[-1][1]
    reset = {"front": by_tag_f["reset"][-n_reset:], "wrist": by_tag_w["reset"][-n_reset:],
             "joint": list(rj), "gripper": list(rg)}
    joints, grips = rec.by_step("joint_state"), rec.by_step("gripper_state")
    exc = {int(e["step"]): e["error"] for e in rec.kinds("env_step_exception")}
    steps = []
    ev_steps = {int(e["step"]): e for e in rec.kinds("env_step")}
    n = max(list(ev_steps) + list(exc) + [-1]) + 1
    for k in range(n):
        if k in exc:
            steps.append(_step_rec(None, None, None, None, status="error", exception=exc[k]))
            continue
        e = ev_steps[k]
        if e.get("obs_none"):
            steps.append(_step_rec(None, None, None, None, terminated=e["terminated"], truncated=e["truncated"],
                                   status=e.get("status"), obs_none=True))
            continue
        steps.append(_step_rec(by_tag_f[f"step{k}"], by_tag_w[f"step{k}"], joints[k], grips[k],
                               terminated=e["terminated"], truncated=e["truncated"], status=e.get("status")))
    model = [a for _, a in rec.arrays("model_action")]
    exec_rows = [a for _, a in rec.arrays("exec_action")]
    if policy == "mme":
        wire = [e["sha"] for e in sorted(rec.kinds("ws_send"), key=lambda e: e["seq"])]
    else:
        wire = [e["send_sha256"] for e in rec.kinds("msg")]
    summ = rec.summary.get("summary", {})
    return {"policy": policy, "kind": "new", "rec": str(rec.dir), "identity": _identity(rec.meta), "goal": goal,
            "reset": reset, "steps": steps, "model_actions": model, "exec_rows": exec_rows, "wire_sha": wire,
            "wire_basis": "new_client_send_sha", "final": {"status": summ.get("status"), "steps": summ.get("steps")}}


def _split_state(s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """官方录制只存了打包后的 8 维 float32 状态：拆回 joint7 + gripper1（float32 原样，重新打包逐字节不变）。"""
    s = np.asarray(s, dtype=np.float32)
    return s[:7].copy(), s[7:8].copy()


def find_proxy_conn(client_rec: Rec, proxy_root: Path) -> Path | None:
    """在代理日志根目录里找出与本局客户端 ws 发出 sha 序列完全一致的连接目录。"""
    want = [e["sha256"] for e in sorted((e for e in client_rec.kinds("ws") if e["dir"] == "send"), key=lambda e: e["idx"])]
    for d in sorted(proxy_root.glob("conn-*")):
        ev = d / "events.jsonl"
        if not ev.exists():
            continue
        got = []
        for line in ev.read_text(encoding="utf-8").splitlines():
            if '"c2s"' in line:
                e = json.loads(line)
                if e.get("kind") == "msg" and e.get("dir") == "c2s":
                    got.append((e["idx"], e["sha256"]))
        if [s for _, s in sorted(got)] == want and want:
            return d
    return None


def trace_official_mme(rec: Rec, proxy_rec: str | Path | None) -> dict:
    """旧官方 MME 录制（mme_client_wrap 钩子 + mme_proxy 连接目录）→ 轨迹。"""
    frec, fimg = rec.frames("front")
    wrec, wimg = rec.frames("wrist")
    r0 = rec.kinds("reset")[-1]
    a, b = r0["front_idx"]
    wa, wb = r0["wrist_idx"]
    rs = rec.arrays("reset_state")[-1][1]
    jr, gr = zip(*[_split_state(s) for s in rs])
    reset = {"front": fimg[a:b + 1], "wrist": wimg[wa:wb + 1], "joint": list(jr), "gripper": list(gr)}
    states = rec.by_step("state")
    steps = []
    for e in sorted(rec.kinds("step"), key=lambda e: e["k"]):
        k = int(e["k"])
        if e.get("obs_none"):
            # 旧 EnvRunner.step 捕获了 env.step 异常并返回 None 观测；这里在假环境里抛异常以同样落入 EnvRunnerShim 分支
            steps.append(_step_rec(None, None, None, None, status="error", exception="official obs None"))
            continue
        j, g = _split_state(states[k])
        steps.append(_step_rec([fimg[e["front_idx"]]], [wimg[e["wrist_idx"]]], j, g, terminated=e["stop"],
                               status=e.get("status")))
    # --proxy-rec 可给单个连接目录（conn-<pid>-<NNNN>，本身含 events.jsonl），也可给代理日志根目录
    # （多局分片：一局一条连接，另有观察器预检等连接）；后者按本局客户端发出 sha 序列逐字匹配出唯一连接。
    root = Path(proxy_rec) if proxy_rec is not None else rec.dir.parent / "proxy"
    if (root / "events.jsonl").exists() and not any(root.glob("conn-*")):
        conn_dir = root
    else:
        conn_dir = find_proxy_conn(rec, root) if root.is_dir() else None
        if conn_dir is None:
            raise RuntimeError(f"在 {root} 下找不到与 {rec.dir.name} 客户端发出序列一致的代理连接目录")
    proxy_rec = conn_dir
    prx = Rec(proxy_rec)
    model = [a for _, a in prx.arrays("s2c.actions")]
    wire = [e["sha256"] for e in sorted((e for e in rec.kinds("ws") if e["dir"] == "send"), key=lambda e: e["idx"])]
    c2s = [e["sha256"] for e in sorted((e for e in prx.kinds("msg") if e.get("dir") == "c2s"), key=lambda e: e["idx"])]
    if c2s != wire:  # 连接目录与本局不对应（显式给错单个连接目录时）
        raise RuntimeError(f"代理连接 {proxy_rec} 的 c2s 序列（{len(c2s)} 条）与 {rec.dir.name} 客户端发出序列（{len(wire)} 条）不一致")
    exec_rows = [a for _, a in rec.arrays("exec_action")]
    summ = rec.summary.get("summary", {})
    return {"policy": "mme", "kind": "official", "rec": str(rec.dir), "proxy_rec": str(proxy_rec),
            "identity": _identity(rec.meta), "goal": r0["task_goal"], "reset": reset, "steps": steps,
            "model_actions": model, "exec_rows": exec_rows, "wire_sha": wire, "wire_basis": "official_client_send_sha",
            "final": {"status": summ.get("return"), "steps": summ.get("steps")}}


def trace_official_smvla(rec: Rec) -> dict:
    """旧官方 SMVLA 录制（smvla_wrap 的 InProcSimPool / generate_batch 钩子）→ 轨迹。"""
    frec, fimg = rec.frames("front")
    wrec, wimg = rec.frames("wrist")
    r0 = [e for e in rec.kinds("reset") if e.get("ok")][-1]
    a, b = r0["front_idx"]
    wa, wb = r0["wrist_idx"]
    rs = rec.arrays("reset_state")[-1][1]
    jr, gr = zip(*[_split_state(s) for s in rs])
    reset = {"front": fimg[a:b + 1], "wrist": wimg[wa:wb + 1], "joint": list(jr), "gripper": list(gr)}
    states = rec.by_step("state")
    steps = []
    for e in sorted(rec.kinds("step"), key=lambda e: e["k"]):
        k = int(e["k"])
        if "pool_error" in e:
            steps.append(_step_rec(None, None, None, None, status="error", exception=str(e["pool_error"])))
            break
        c = int(e["consumed"])
        nf = int(e.get("n_frames", 0))
        fidx, widx = e.get("front_idx", []), e.get("wrist_idx", [])
        st = states.get(k)
        for j in range(c):
            last = j == c - 1
            if j < nf:
                jj, gg = _split_state(st[j])
                steps.append(_step_rec([fimg[fidx[j]]], [wimg[widx[j]]], jj, gg,
                                       terminated=bool(e.get("done")) and last,
                                       status=e.get("status") if last else "ongoing"))
            else:  # 该行 obs 为 None／error（step_one 停在这一行）
                steps.append(_step_rec(None, None, None, None, status="error", obs_none=True,
                                       terminated=True))
                steps[-1]["error_message"] = e.get("error_message")
    exec_rows = []
    for _, arr in rec.arrays("exec_action"):
        exec_rows.extend(list(np.asarray(arr)))
    model = [a for _, a in rec.arrays("model_action")]
    det = (rec.summary.get("summary", {}).get("details") or [{}])[0]
    return {"policy": "smvla", "kind": "official", "rec": str(rec.dir), "identity": _identity(rec.meta),
            "goal": r0["instruction"], "reset": reset, "steps": steps, "model_actions": model, "exec_rows": exec_rows,
            "wire_sha": None, "wire_basis": "none_inproc", "final": {"status": det.get("status"), "steps": det.get("steps")}}


def load_trace(policy: str, rec_dir: str | Path, kind: str, proxy_rec: str | None = None) -> dict:
    rec = Rec(rec_dir)
    if kind == "new":
        return trace_new(rec, policy)
    if policy == "mme":
        return trace_official_mme(rec, proxy_rec)
    return trace_official_smvla(rec)


# ───────────────────────────────────────────── 假环境 / 假连接：用新接口客户端原函数重建请求流


class Exhausted(RuntimeError):
    """新客户端逻辑走到了录制之外（多要了一步环境或一次推理）。"""


class FakeEnv:
    """按录制逐步回放环境观测；记录交给环境的每个动作（与 EnvSession.step 同样复制）。"""

    def __init__(self, trace: dict, gripper_dim: int | None = None):
        self.t = trace
        self.k = 0
        self.exec_rows: list[np.ndarray] = []
        self.exhausted = False
        self.recorder = None  # smvla_client.run_episode 以此判断环境侧是否已录制

    def obs_of(self, frames, wrist, joint, gripper) -> dict:
        return {"front_rgb_list": list(frames), "wrist_rgb_list": list(wrist),
                "joint_state_list": [joint] * len(frames), "gripper_state_list": [gripper] * len(frames)}

    def reset(self):
        r = self.t["reset"]
        obs = {"front_rgb_list": list(r["front"]), "wrist_rgb_list": list(r["wrist"]),
               "joint_state_list": list(r["joint"]), "gripper_state_list": list(r["gripper"])}
        return obs, {"task_goal": [self.t["goal"]], "status": "ongoing"}

    def step(self, action):
        self.exec_rows.append(np.array(action, copy=True))
        if self.k >= len(self.t["steps"]):
            self.exhausted = True
            raise Exhausted(f"录制只有 {len(self.t['steps'])} 步，新客户端逻辑要第 {self.k + 1} 步")
        s = self.t["steps"][self.k]
        self.k += 1
        if s["exception"] is not None:
            raise RuntimeError(s["exception"])
        info = {"status": s["status"]}
        if s.get("error_message"):
            info["error_message"] = s["error_message"]
        if s["obs_none"]:
            return None, 0.0, s["terminated"], s["truncated"], info
        obs = self.obs_of(s["front"], s["wrist"], s["joint"], s["gripper"])
        return obs, 0.0, s["terminated"], s["truncated"], info

    def close(self):
        pass


class FakeMMEClient:
    """与 mme_client.RecordingClient 同样打包（openpi_client Packer）；推理按序返回录下的模型输出。"""

    def __init__(self, model_actions: list[np.ndarray], keep_objects: bool = False):
        self.model = model_actions
        self.msgs: list[dict] = []
        self.n_infer = 0
        self.exhausted = False
        self._packer = packer()
        self.keep = keep_objects

    def _send(self, kind: str, obj: dict, decision: int | None = None) -> None:
        raw = self._packer.pack(obj)
        m = {"kind": kind, "raw": raw, "decision": decision}
        if self.keep:
            m["obj"] = obj
        self.msgs.append(m)

    def reset(self):
        self._send("reset", {"reset": True})
        return {"reset_finished": True}

    def add_buffer(self, buffer):
        self._send("add_buffer", buffer)
        return {"add_buffer_finished": True}

    def infer(self, obs):
        self._send("infer", obs, decision=self.n_infer)
        if self.n_infer >= len(self.model):
            self.exhausted = True
            raise Exhausted(f"录制只有 {len(self.model)} 次推理输出")
        a = self.model[self.n_infer]
        self.n_infer += 1
        return {"actions": np.asarray(a)}


class FakeSMVLAConn:
    """与 smvla_client.WSPolicyConn 同样打包；回包按 smvla_server 协议构造（含 req_sha 等核对字段）。"""

    def __init__(self, model_actions: list[np.ndarray], keep_objects: bool = False, execute_horizon: int = 16):
        self.model = model_actions
        self.msgs: list[dict] = []
        self.n_infer = 0
        self.exhausted = False
        self.metadata = {"fake": True}
        self._packer = packer()
        self.keep = keep_objects
        self.h = execute_horizon

    def call(self, msg: dict):
        raw = self._packer.pack(msg)
        key = next(iter(msg))
        m = {"kind": key, "raw": raw, "decision": self.n_infer if key == "infer" else None}
        if self.keep:
            m["obj"] = msg
        self.msgs.append(m)
        rep: dict[str, Any] = {"req_sha": sha_bytes(raw)}
        if key == "reset":
            rep.update(reset_finished=True, rng=None)
        elif key == "observe":
            frs = msg["observe"]["frames"]
            rep.update(n=len(frs), frame_sha=[{k: frame_sha(v) for k, v in sorted(fr.items())} for fr in frs],
                       observe_time_ms=0.0)
        else:
            p = msg["infer"]
            if self.n_infer >= len(self.model):
                self.exhausted = True
                raise Exhausted(f"录制只有 {len(self.model)} 次推理输出")
            a = np.asarray(self.model[self.n_infer])
            self.n_infer += 1
            rep.update(actions=a[:self.h], actions_full=a, subtask="", infer_ms=0.0,
                       recv_state_sha=array_sha(np.array(p["state"], copy=True)),
                       recv_instruction_sha=sha_bytes(str(p["instruction"]).encode("utf-8")))
        return rep, raw, b""

    def close(self):
        pass


def simulate(trace: dict, *, mod=None, keep_objects: bool = False) -> dict:
    """用新接口客户端原函数（或换入旧函数的模块副本 mod）在录下的观测与模型输出上重走一局。

    返回 {msgs, exec_rows, status, steps, error, exhausted}。"""
    policy = trace["policy"]
    env = FakeEnv(trace)
    if policy == "mme":
        m = mod or load_module("mme_client")
        client = FakeMMEClient(trace["model_actions"], keep_objects=keep_objects)
        runner = m.EnvRunnerShim(env.step)
        progress = m._Progress()

        def reset_fn():
            obs, info = env.reset()
            return m.pre_traj_from_reset(obs, info)

        error = None
        try:
            flag = m.run_loop(client, runner, reset_fn, progress)
        except Exception as e:  # noqa: BLE001 与 evaluate_one 同样整局兜底
            flag, error = "error", f"{type(e).__name__}: {e}"
        status = flag if flag in m.NORMAL else "error"
        if status == "error" and error is None:
            error = f"success_flag={flag}"
        return {"msgs": client.msgs, "exec_rows": env.exec_rows, "status": status, "steps": progress.last_steps,
                "error": error, "exhausted": env.exhausted or client.exhausted, "decisions": progress.decisions}
    m = mod or load_module("smvla_client")
    conn = FakeSMVLAConn(trace["model_actions"], keep_objects=keep_objects)
    ident = dict(trace["identity"])
    res = m.run_episode(env, ident, {}, None, conn=conn)
    return {"msgs": conn.msgs, "exec_rows": env.exec_rows, "status": res["status"], "steps": res["steps"],
            "error": res["error"], "exhausted": env.exhausted or conn.exhausted, "decisions": res["decisions"]}


def exec_compare(sim_rows: list[np.ndarray], rec_rows: list[np.ndarray], sim_final: dict, rec_final: dict) -> dict:
    """执行动作对比：维度、顺序（逐行字节）、数量、终止位置（步数与终态）。"""
    n = min(len(sim_rows), len(rec_rows))
    dims_equal = all(np.asarray(a).shape == np.asarray(b).shape and np.asarray(a).dtype == np.asarray(b).dtype
                     for a, b in zip(sim_rows[:n], rec_rows[:n]))
    first = next((i for i in range(n) if array_sha(sim_rows[i]) != array_sha(rec_rows[i])), None)
    count_equal = len(sim_rows) == len(rec_rows)
    term_equal = (sim_final.get("status") == rec_final.get("status")
                  and (rec_final.get("steps") is None or int(sim_final.get("steps") or 0) == int(rec_final["steps"])))
    return {"dims_equal": bool(dims_equal), "order_equal": first is None, "first_diff_row": first,
            "count_sim": len(sim_rows), "count_rec": len(rec_rows), "count_equal": count_equal,
            "term_sim": [sim_final.get("status"), sim_final.get("steps")],
            "term_rec": [rec_final.get("status"), rec_final.get("steps")], "term_equal": bool(term_equal),
            "exec_equal": bool(dims_equal and first is None and count_equal and term_equal)}


# ───────────────────────────────────────────── build-inputs


def write_inputs(out: Path, trace: dict, sim: dict, extra_meta: dict) -> dict:
    """输入目录：messages.bin（逐条原始字节首尾相接）+ stream.jsonl（种类、偏移、长度、sha256）+ meta.json
    + reference.npz（录下的模型输出、录下与重走的执行动作）。"""
    out.mkdir(parents=True, exist_ok=True)
    off = 0
    rows = []
    with open(out / "messages.bin", "wb") as fh:
        for i, m in enumerate(sim["msgs"]):
            fh.write(m["raw"])
            rows.append({"i": i, "kind": m["kind"], "offset": off, "len": len(m["raw"]), "sha256": sha_bytes(m["raw"]),
                         "decision": m["decision"]})
            off += len(m["raw"])
    (out / "stream.jsonl").write_text("".join(dumps(r) + "\n" for r in rows), encoding="utf-8")
    ref = {}
    if trace["model_actions"]:
        try:
            ref["recorded_model_action"] = np.stack([np.asarray(a) for a in trace["model_actions"]])
        except ValueError:
            pass
    if trace["exec_rows"]:
        ref["recorded_exec_action"] = np.stack([np.asarray(a) for a in trace["exec_rows"]])
    if sim["exec_rows"]:
        ref["sim_exec_action"] = np.stack([np.asarray(a) for a in sim["exec_rows"]])
    np.savez(out / "reference.npz", **ref)
    meta = {"policy": trace["policy"], "kind": trace["kind"], "rec": trace["rec"], "proxy_rec": trace.get("proxy_rec"),
            "identity": trace["identity"], "goal": trace["goal"], "messages": len(rows),
            "infers": sum(1 for r in rows if r["kind"] == "infer"), "bytes": off,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **extra_meta}
    (out / "meta.json").write_text(dumps(meta, indent=1), encoding="utf-8")
    return meta


def wire_mismatch(sim_msgs: list[dict], wire: list[str] | None) -> tuple[int | None, int | None]:
    """重建字节 vs 录下的发出 sha：返回 (不符条数, 首个不符序号)；条数不同也计入。"""
    if wire is None:
        return None, None
    got = [sha_bytes(m["raw"]) for m in sim_msgs]
    bad = [i for i in range(min(len(got), len(wire))) if got[i] != wire[i]]
    n = len(bad) + abs(len(got) - len(wire))
    first = bad[0] if bad else (min(len(got), len(wire)) if len(got) != len(wire) else None)
    return n, first


def cmd_build_inputs(args) -> int:
    trace = load_trace(args.policy, args.rec, args.kind, args.proxy_rec)
    sim = simulate(trace)
    mism, first = wire_mismatch(sim["msgs"], trace["wire_sha"])
    ex = exec_compare(sim["exec_rows"], trace["exec_rows"], sim, trace["final"])
    meta = write_inputs(Path(args.out), trace, sim, {
        "wire_basis": trace["wire_basis"], "wire_mismatch": mism, "wire_first_mismatch": first,
        "sim": {k: sim[k] for k in ("status", "steps", "error", "exhausted", "decisions")}, "exec": ex,
        "recorded_final": trace["final"]})
    if args.kind == "new":
        ok = mism == 0 and not sim["exhausted"]
        print(f"BUILD_INPUTS={'PASS' if ok else 'FAIL'} policy={args.policy} kind=new messages={meta['messages']} "
              f"infers={meta['infers']} mismatch={mism} first_mismatch={first} exec_equal={ex['exec_equal']} "
              f"out={args.out}", flush=True)
        return 0 if ok else 1
    ok = not sim["exhausted"] and mism in (None, 0)  # 官方 MME 有线上字节 sha 时也要求逐条一致
    print(f"BUILD_INPUTS={'PASS' if ok else 'FAIL'} policy={args.policy} kind=official messages={meta['messages']} "
          f"infers={meta['infers']} basis={trace['wire_basis']} mismatch={'n/a' if mism is None else mism} "
          f"first_mismatch={first} exec_equal={ex['exec_equal']} out={args.out}", flush=True)
    return 0 if ok else 1


# ───────────────────────────────────────────── replay


def read_inputs(d: str | Path) -> tuple[dict, list[dict], bytes]:
    d = Path(d)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in (d / "stream.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    data = (d / "messages.bin").read_bytes()
    for r in rows:
        if sha_bytes(data[r["offset"]:r["offset"] + r["len"]]) != r["sha256"]:
            raise RuntimeError(f"{d} 第 {r['i']} 条消息字节与 stream.jsonl 的 sha256 不符")
    return meta, rows, data


def _connect(host: str, port: int, open_timeout: float):
    from websockets.sync.client import connect

    t0 = time.monotonic()
    while True:
        try:
            return connect(f"ws://{host}:{int(port)}", compression=None, max_size=None, proxy=None,
                           open_timeout=open_timeout, ping_interval=None, ping_timeout=None, close_timeout=60)
        except (ConnectionRefusedError, OSError):
            if time.monotonic() - t0 > open_timeout:
                raise
            time.sleep(2)


def replay_once(policy: str, rows: list[dict], data: bytes, host: str, port: int, open_timeout: float = 600.0) -> dict:
    """一条连接回放一遍：reset 在前（输入流第 0 条即 reset），逐条发、逐条收；收齐推理动作与计时。"""
    ws = _connect(host, port, open_timeout)
    try:
        server_meta = unpackb(ws.recv())
        actions, subtasks, rtt_ms, server_ms, reset_reply = [], [], [], [], None
        protocol_bad = 0
        for r in rows:
            raw = data[r["offset"]:r["offset"] + r["len"]]
            t0 = time.monotonic()
            ws.send(raw)
            rep = ws.recv()
            dt = (time.monotonic() - t0) * 1000.0
            if isinstance(rep, str):
                raise RuntimeError(f"server 返回文本帧（第 {r['i']} 条 {r['kind']}）：{rep[:2000]}")
            obj = unpackb(rep)
            if policy == "smvla":
                if "error" in obj:
                    raise RuntimeError(f"server 报错（第 {r['i']} 条）：{obj['error']}")
                if obj.get("req_sha") != r["sha256"]:
                    protocol_bad += 1
            if r["kind"] == "reset":
                reset_reply = {k: v for k, v in obj.items() if isinstance(v, (bool, int, float, str, dict, type(None)))}
            elif r["kind"] == "infer":
                a = obj["actions_full"] if policy == "smvla" else obj["actions"]
                actions.append(np.array(a, copy=True))
                subtasks.append(str(obj.get("subtask", "")))
                rtt_ms.append(dt)
                server_ms.append(server_infer_ms(obj))
        return {"actions": actions, "subtasks": subtasks, "rtt_ms": rtt_ms, "server_ms": server_ms,
                "reset_reply": reset_reply, "server_meta": server_meta, "protocol_bad": protocol_bad}
    finally:
        try:
            ws.close()
        except Exception:  # noqa: BLE001
            pass


def server_infer_ms(obj: dict) -> float:
    """server 回包里的推理耗时（SMVLA infer_ms；MME infer_time_ms 或 server_timing.infer_ms）；都没有则 NaN。"""
    for v in (obj.get("infer_ms"), obj.get("infer_time_ms"),
              (obj.get("server_timing") or {}).get("infer_ms") if isinstance(obj.get("server_timing"), dict) else None):
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return float("nan")


def timing_basis(policy: str, server_ms: list[float], rtt_ms: list[float]) -> tuple[str, list[float]]:
    """确定性测速用哪组数：MME 一律用往返耗时 rtt（server 的 infer_time_ms 在 jax 异步派发下可能没含完计算，
    且旧版本 server 可能不回该字段）；SMVLA 用 server infer_ms（已 cuda.synchronize），缺失时退回 rtt。"""
    if policy == "mme":
        return "rtt_ms", list(rtt_ms)
    if server_ms and all(x == x for x in server_ms):
        return "server_infer_ms", list(server_ms)
    return "rtt_ms", list(rtt_ms)


def rng_restored(policy: str, reset_reply: dict | None) -> bool:
    """MME：reset 已被 server 执行（policy.reset() 把 rng 设回 key(seed)）；SMVLA：reset 后随机状态摘要等于参照。"""
    if not reset_reply:
        return False
    if policy == "mme":
        return bool(reset_reply.get("reset_finished"))
    return bool(reset_reply.get("rng_matches_ref"))


def _meta_summary(policy: str, m: Any) -> dict:
    if not isinstance(m, dict):
        return {"type": type(m).__name__}
    keep = ("ckpt", "ckpt_config_sha256", "det", "warmup", "gpu_name", "versions", "episode_seed", "cublas_workspace_config")
    return {k: m[k] for k in keep if k in m} if policy == "smvla" else {k: v for k, v in m.items()
                                                                        if isinstance(v, (str, int, float, bool))}


def cmd_replay(args) -> int:
    meta, rows, data = read_inputs(args.inputs)
    if meta["policy"] != args.policy:
        raise SystemExit(f"输入目录是 {meta['policy']} 的，与 --policy {args.policy} 不符")
    base = Path(args.out) / args.tag
    for k in range(args.repeats):
        d = base / f"rep{k + args.start_index}"
        if (d / "actions.npz").exists() and not args.force:
            raise SystemExit(f"{d} 已存在（加 --force 覆盖）")
        t0 = time.monotonic()
        res = replay_once(args.policy, rows, data, args.host, args.port, args.open_timeout)
        wall = time.monotonic() - t0
        d.mkdir(parents=True, exist_ok=True)
        np.savez(d / "actions.npz", model_action=np.stack(res["actions"]))
        rr = rng_restored(args.policy, res["reset_reply"])
        basis, det_ms = timing_basis(args.policy, res["server_ms"], res["rtt_ms"])
        timing = {"policy": args.policy, "inputs": str(Path(args.inputs).resolve()), "tag": args.tag, "rep": k + args.start_index,
                  "label": args.label, "wall_s": wall, "rtt_ms": res["rtt_ms"], "server_ms": res["server_ms"],
                  "timing_basis": basis, "det_ms": det_ms, "run_id": args.run_id,
                  "subtasks": res["subtasks"], "reset_reply": res["reset_reply"], "rng_restored": rr,
                  "protocol_bad": res["protocol_bad"], "server_meta": _meta_summary(args.policy, res["server_meta"]),
                  "infers": len(res["actions"]), "actions_sha": [array_sha(a) for a in res["actions"]],
                  "input_identity": meta.get("identity"), "input_kind": meta.get("kind")}
        (d / "timing.json").write_text(dumps(timing, indent=1), encoding="utf-8")
        srv = np.asarray(det_ms[STEADY_SKIP:] or det_ms, dtype=float)
        print(f"REPLAY_DONE policy={args.policy} tag={args.tag} rep={k + args.start_index} infers={len(res['actions'])} "
              f"wall_s={wall:.1f} basis={basis} infer_ms_first={det_ms[0] if det_ms else 'nan'} "
              f"infer_ms_steady_median={float(np.median(srv)) if srv.size else float('nan'):.1f} "
              f"rng_restored={rr} protocol_bad={res['protocol_bad']}", flush=True)
        if res["protocol_bad"]:
            return 1
    return 0


# ───────────────────────────────────────────── compare


def _load_actions(d: str | Path) -> np.ndarray:
    p = Path(d)
    if p.is_dir():
        p = p / "actions.npz"
    with np.load(p, allow_pickle=False) as z:
        key = "model_action" if "model_action" in z.files else z.files[0]
        return np.asarray(z[key])


def _fmt(x: Any) -> str:
    if x is None:
        return "None"
    if isinstance(x, float):
        return f"{x:.6g}"
    return str(x)


def _vec(xs) -> str:
    return ",".join(f"{float(v):.6g}" for v in xs)


def diff_line(res: dict, *, kind: str, cond: str, policy: str, mode: str, det: str, label: str = "") -> str:
    ref = res.get("ref", {})
    if kind == "iface":
        return (f"IFACE_OPEN=INFO policy={policy} payload_equal=n/a action_diff={_fmt(res.get('max_abs'))} exec_equal=n/a "
                f"neq={res.get('neq')} first_diff_step={res.get('first_diff_step')} label={label or 'n/a'}")
    return (f"POLICY_REPLAY=INFO cond={cond} policy={policy} det={det} mode={mode} "
            f"bitwise={'yes' if res.get('bitwise') else 'no'} dim_mean_abs={_vec(res.get('dim_mean_abs', []))} "
            f"dim_p95={_vec(res.get('dim_p95', []))} dim_max_abs={_vec(res.get('dim_max_abs', []))} "
            f"max_rel={_fmt(res.get('max_rel'))} neq={res.get('neq')} first_diff_step={res.get('first_diff_step')} "
            f"unit=infer vs_action_max={ref.get('side', 'n/a')} label={label or 'n/a'}")


def compare_dirs(a: str | Path, b: str | Path) -> dict:
    cmpm = load_module("compare")
    xa, xb = _load_actions(a), _load_actions(b)
    res = cmpm.action_diff(xa, xb)
    res["bitwise"] = bool(res.get("comparable") and res.get("shape_equal") and res.get("neq") == 0)
    if res.get("comparable"):
        res["ref"] = {"name": "action_max", "value": cmpm.REF_ACTION_MAX,
                      "side": "above" if res["max_abs"] > cmpm.REF_ACTION_MAX else "below"}
    return res


def cmd_compare(args) -> int:
    res = compare_dirs(args.a, args.b)
    res.update(a=str(args.a), b=str(args.b), kind=args.kind, cond=args.cond, policy=args.policy, mode=args.mode,
               det=args.det, label=args.label, run_id=args.run_id)
    line = diff_line(res, kind=args.kind, cond=args.cond, policy=args.policy, mode=args.mode, det=args.det, label=args.label)
    res["line"] = line
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(dumps(res, indent=1), encoding="utf-8")
    print(line, flush=True)
    return 0


# ───────────────────────────────────────────── iface-open


def old_mme_module(old_dir: str | Path):
    """mme_client 的一份副本，其中 pack_buffer / pack_state 换成旧官方原文（utils.py / env_runner.py）。"""
    old_dir = Path(old_dir)
    ns_u = extract_defs(old_dir / "utils.py", ["pack_buffer"])
    ns_e = extract_defs(old_dir / "env_runner.py", ["pack_state"])
    m = fresh_module("mme_client", "v75_mme_client_oldpack")
    m.pack_buffer = ns_u["pack_buffer"]
    m.pack_state = ns_e["pack_state"]
    return m, {"utils.py": ns_u["__source_sha256__"], "env_runner.py": ns_e["__source_sha256__"]}


def old_smvla_module(old_env: str | Path):
    """smvla_client 的一份副本，其中 encode_frames / encode_states 等换成旧官方 robomme_env.py 原文。"""
    names = ["CAM_FRONT", "CAM_WRIST", "_to_uint8_hwc", "_to_f32", "encode_frames", "encode_states", "_scalar"]
    ns = extract_defs(old_env, names)
    m = fresh_module("smvla_client", "v75_smvla_client_oldenc")
    for n in names:
        setattr(m, n, ns[n])
    return m, {"robomme_env.py": ns["__source_sha256__"]}


def smvla_model_inputs(msgs: list[dict], *, via_wire: bool) -> list[str]:
    """SMVLA 交到模型侧的输入指纹序列。

    旧官方：encode_frames 的输出直接进 ``buffer.observe(to_full(fr))``（to_full 做 np.asarray(v, uint8)），
    状态 ``np.asarray(states[-1], float32)`` 进 state_norm；新接口：同样的 dict 经 msgpack 打包 → server 解包 →
    ``np.array(v, copy=True)`` → to_full。两侧在同一换算后取 array_sha（字节 + dtype + shape）。"""
    out = []
    for m in msgs:
        obj = unpackb(m["raw"]) if via_wire else m["obj"]
        key = next(iter(obj))
        if key == "observe":
            for fr in obj["observe"]["frames"]:
                fr = {k: (np.array(v, copy=True) if via_wire else v) for k, v in fr.items()}
                out.append("frame:" + "|".join(f"{k}={array_sha(np.asarray(v, dtype=np.uint8))}" for k, v in sorted(fr.items())))
        elif key == "infer":
            p = obj["infer"]
            s = np.array(p["state"], copy=True) if via_wire else p["state"]
            out.append(f"infer:state={array_sha(np.asarray(s, dtype=np.float32))}|instr={sha_bytes(str(p['instruction']).encode())}")
        else:
            out.append("reset")
    return out


def cmd_iface_open(args) -> int:
    trace = load_trace(args.policy, args.rec_official, "official", args.proxy_rec)
    new = simulate(trace, keep_objects=True)
    if args.policy == "mme":
        mod, src_sha = old_mme_module(args.old_src or OLD_MME_DIR)
        old = simulate(trace, mod=mod, keep_objects=True)
        a = [sha_bytes(m["raw"]) for m in new["msgs"]]
        b = [sha_bytes(m["raw"]) for m in old["msgs"]]
        wire_n, wire_first = wire_mismatch(new["msgs"], trace["wire_sha"])
    else:
        mod, src_sha = old_smvla_module(args.old_src or OLD_SMVLA_ENV)
        old = simulate(trace, mod=mod, keep_objects=True)
        a = smvla_model_inputs(new["msgs"], via_wire=True)
        b = smvla_model_inputs(old["msgs"], via_wire=False)
        wire_n, wire_first = None, None
    diff = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
    payload_mismatch = len(diff) + abs(len(a) - len(b))
    payload_equal = payload_mismatch == 0 and (wire_n in (None, 0))
    ex_new = exec_compare(new["exec_rows"], trace["exec_rows"], new, trace["final"])
    ex_old = exec_compare(old["exec_rows"], trace["exec_rows"], old, trace["final"])
    action = {"basis": "payload_equal→同输入同模型，动作必然相同" if payload_equal else "payload 不同，动作需回放比较"}
    action_diff_val: str = "0(by_payload)" if payload_equal else "n/a"
    if args.actions_new:
        rec_model = trace["model_actions"]
        rep = _load_actions(args.actions_new)
        cmpm = load_module("compare")
        r = cmpm.action_diff(np.stack([np.asarray(x) for x in rec_model]), rep)
        action["official_recorded_vs_new_replay"] = r
        action_diff_val = f"{r.get('max_abs')}"
    res = {"policy": args.policy, "rec_official": str(args.rec_official), "old_src_sha256": src_sha,
           "messages_new": len(a), "messages_old": len(b), "payload_mismatch": payload_mismatch,
           "payload_first_mismatch": diff[0] if diff else None, "wire_mismatch_vs_official": wire_n,
           "wire_first_mismatch": wire_first, "payload_equal": payload_equal, "action": action,
           "exec_new_vs_official": ex_new, "exec_oldpack_vs_official": ex_old,
           "sim_new": {k: new[k] for k in ("status", "steps", "error", "exhausted")}, "recorded_final": trace["final"]}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(dumps(res, indent=1), encoding="utf-8")
    print(f"IFACE_OPEN=INFO policy={args.policy} payload_equal={'yes' if payload_equal else 'no'} "
          f"action_diff={action_diff_val} exec_equal={'yes' if ex_new['exec_equal'] else 'no'} "
          f"payload_mismatch={payload_mismatch} wire_mismatch={'n/a' if wire_n is None else wire_n} "
          f"exec_count={ex_new['count_sim']}/{ex_new['count_rec']} "
          f"term={':'.join(map(str, ex_new['term_sim']))}/{':'.join(map(str, ex_new['term_rec']))}",
          flush=True)
    return 0


# ───────────────────────────────────────────── report / DET_RULE


def steady_infer_ms(timing_files: list[Path]) -> tuple[float | None, list[str]]:
    """若干次回放的稳态推理耗时中位数（每次回放跳过前 STEADY_SKIP 次推理）；返回 (中位数, 用到的测速口径)。
    优先 timing.json 的 det_ms（按 timing_basis 选定），旧文件退回 server_ms。"""
    vals: list[float] = []
    bases: set[str] = set()
    for f in timing_files:
        t = json.loads(f.read_text(encoding="utf-8"))
        src = t.get("det_ms", t.get("server_ms", []))
        bases.add(t.get("timing_basis", "server_ms"))
        vals.extend(x for x in src[STEADY_SKIP:] if x == x)
    return (float(np.median(vals)) if vals else None), sorted(bases)


def det_rule(on_bitwise: list[bool], ms_off: float | None, ms_on: float | None) -> dict:
    """方案写死：det 开时同卡逐位一致、且单次推理耗时增加不超过 10% → 第 5 步默认开；否则关。"""
    det_bitwise = bool(on_bitwise) and all(on_bitwise)
    slowdown = None if (ms_off is None or ms_on is None or ms_off <= 0) else (ms_on / ms_off - 1.0) * 100.0
    default = "on" if (det_bitwise and slowdown is not None and slowdown <= DET_SLOWDOWN_MAX_PCT) else "off"
    return {"det_bitwise": det_bitwise, "slowdown_pct": slowdown, "infer_ms_off": ms_off, "infer_ms_on": ms_on,
            "default": default, "n_on_comparisons": len(on_bitwise)}


def cmd_report(args) -> int:
    root = Path(args.root)
    rid = args.run_id

    def mine(obj: dict) -> bool:  # 只汇总本次运行（run_id 相同）的产物；未给 run_id 时全收
        return not rid or obj.get("run_id") == rid

    comps = []
    for f in sorted((root / "compare").glob("*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        if mine(c):
            comps.append(c)
    on_same_card = [c["bitwise"] for c in comps if c.get("det") == "on" and c.get("mode") in ("same", "restart")]
    # 编译缓存那几次（开了 JAX 调试日志）不计入确定性测速
    def timings(det: str) -> list[Path]:
        return sorted(f for f in (root / f"det-{det}").glob("**/timing.json")
                      if "/cache-" not in str(f) and mine(json.loads(f.read_text(encoding="utf-8"))))

    t_off, t_on = timings("off"), timings("on")
    ms_off, b_off = steady_infer_ms(t_off)
    ms_on, b_on = steady_infer_ms(t_on)
    rule = det_rule(on_same_card, ms_off, ms_on)
    rule["timing_basis"] = sorted(set(b_off) | set(b_on))
    rng = {}
    for f in sorted(root.glob("**/timing.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        if mine(t):
            rng[str(f.parent.relative_to(root))] = bool(t.get("rng_restored"))
    # SMVLA 预热后随机状态核对（server metadata 的 warmup.rng_restored）
    warm = {}
    for f in sorted((root / "server-logs").glob("metadata-*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        if not rid or rid in f.name:
            w = m.get("warmup") or {}
            warm[f.name] = {"rng_restored": w.get("rng_restored"), "rng_consumed_by_warmup": w.get("rng_consumed_by_warmup"),
                            "det": m.get("det")}
    busy = []
    bf = root / "gpu-busy.jsonl"
    if bf.exists():
        busy = [b for b in (json.loads(l) for l in bf.read_text(encoding="utf-8").splitlines() if l.strip()) if mine(b)]
    extra = {}
    for f in sorted(root.glob("*.json")):
        if f.name not in ("report.json",):  # 如 cache-check.json（驱动每次开跑前已清掉旧的）
            try:
                extra[f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
    rep = {"cond": args.cond, "policy": args.policy, "run_id": rid, "comparisons": comps, "det_rule": rule,
           "rng_restored_all": all(rng.values()) if rng else False, "rng_restored": rng, "extra": extra,
           "smvla_warmup_rng": warm, "smvla_warmup_rng_all": all(bool(v["rng_restored"]) for v in warm.values()) if warm else None,
           "gpu_busy": busy, "gpu_busy_events": len(busy),
           "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    (root / "report.json").write_text(dumps(rep, indent=1), encoding="utf-8")
    sp = "n/a" if rule["slowdown_pct"] is None else f"{rule['slowdown_pct']:.2f}"
    print(f"RNG_RESTORE=INFO policy={args.policy} all={'yes' if rep['rng_restored_all'] else 'no'} runs={len(rng)} "
          f"smvla_warmup_all={rep['smvla_warmup_rng_all']} gpu_busy_events={len(busy)}", flush=True)
    print(f"DET_RULE=INFO policy={args.policy} det_bitwise={'yes' if rule['det_bitwise'] else 'no'} slowdown_pct={sp} "
          f"default={rule['default']} infer_ms_off={_fmt(rule['infer_ms_off'])} infer_ms_on={_fmt(rule['infer_ms_on'])} "
          f"on_comparisons={rule['n_on_comparisons']} basis={','.join(rule['timing_basis']) or 'n/a'}", flush=True)
    print(f"POLICY_REPLAY_DONE cond={args.cond} policy={args.policy} comparisons={len(comps)} report={root / 'report.json'}",
          flush=True)
    return 0


# ───────────────────────────────────────────── 命令行


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="v7.5eval 第 4 步：开环回放与新旧接口开环")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("build-inputs", help="从一局录制重建有序请求流")
    p.add_argument("--policy", choices=("mme", "smvla"), required=True)
    p.add_argument("--rec", required=True)
    p.add_argument("--kind", choices=("new", "official"), required=True)
    p.add_argument("--proxy-rec", default=None, help="官方 MME：代理连接目录（缺省在 <rec>/../proxy 下按 sha 序列自动匹配）")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_build_inputs)

    p = sub.add_parser("replay", help="把请求流发给运行中的 server，收完整动作")
    p.add_argument("--policy", choices=("mme", "smvla"), required=True)
    p.add_argument("--inputs", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--start-index", type=int, default=0)
    p.add_argument("--tag", required=True)
    p.add_argument("--label", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--open-timeout", type=float, default=600.0)
    p.add_argument("--force", action="store_true")
    p.add_argument("--run-id", default="", help="本次运行编号（report 只汇总同一编号）")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("compare", help="两次回放的动作逐维差")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--kind", choices=("replay", "iface"), default="replay")
    p.add_argument("--cond", default="n/a")
    p.add_argument("--policy", default="n/a")
    p.add_argument("--mode", choices=("same", "restart", "ABA", "cache"), default="same")
    p.add_argument("--det", choices=("on", "off"), default="off")
    p.add_argument("--label", default="")
    p.add_argument("--out", default=None)
    p.add_argument("--run-id", default="")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("iface-open", help="新旧接口开环：同一原始观测走旧／新打包")
    p.add_argument("--policy", choices=("mme", "smvla"), required=True)
    p.add_argument("--rec-official", required=True)
    p.add_argument("--proxy-rec", default=None)
    p.add_argument("--old-src", default=None, help="MME：旧 examples/robomme 目录；SMVLA：旧 robomme_env.py")
    p.add_argument("--actions-new", default=None, help="可选：新接口回放 rep 目录，与官方录下的模型输出比")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_iface_open)

    p = sub.add_parser("report", help="汇总比较结果并给确定性标志默认值")
    p.add_argument("--root", required=True)
    p.add_argument("--cond", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--run-id", default="")
    p.set_defaults(func=cmd_report)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
