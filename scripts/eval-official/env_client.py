#!/usr/bin/env python3
"""v7.5eval 新接口的环境侧（0929-v7.5eval-restructure-plan.md §2.4、§3.2 第 1 步 3、§4、§5）。

两部分：

1. ``EnvSession``：身份 → ``BenchmarkEnvBuilder(dataset="test-hard").make_env_for_episode`` → reset/step。
   * ``reset()`` 原样返回 ``(obs, info)``；reset 期间录制器只入队（``set_phase("reset")``），返回后切 ``"run"``；
   * ``step(action)`` 把 action **原样**交给 ``env.step``，并记录实际交出去的数组（``exec_action``）与返回的当前帧、
     状态、终态字段；``env.step`` 抛出的异常原样上抛（由策略客户端按旧官方语义处理）；
   * 逐段计时：环境构建、reset、逐步 env 时间、录制开销、close。
2. ``run`` 子命令：常驻客户端进程。import 与 Vulkan 设备只建一次，逐身份建 EnvSession + EpisodeRecorder，调用
   策略模块（``mme_client`` / ``smvla_client``）的 ``run_episode(session, identity, conn_info, recorder) -> dict``，
   结果写 ``<out>/results.jsonl``（合同格式），进度心跳写 ``<out>/progress.json``。

身份核对：``builder.resolve_identity(builder_episode)`` 的 seed、source_episode、tier 必须等于身份清单，否则
「运行阻塞」（写一条 ``run_blocked`` 记录、打印 ``RUN_BLOCKED``、退出码 3）。

退出码：0 全部完成；3 运行阻塞；75 单局墙钟超时（基础设施超时，已记录并回收认领，由 run_seat.sh 重起）。

本目录只挂在 ``sys.path`` 末尾（防止同目录模块遮蔽标准库），同目录模块按文件路径加载。
"""
from __future__ import annotations

import sys
from pathlib import Path as _Path

_HERE = str(_Path(__file__).resolve().parent)
sys.path[:] = [p for p in sys.path if p and str(_Path(p).resolve()) != _HERE] + [_HERE]

import argparse  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Callable  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
for _extra in (REPO / "src",):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

MAX_STEPS = 1300
XHARD0 = "xhard0"
EXIT_BLOCKED = 3
EXIT_WALL = 75
DEFAULT_SHUFFLE_SEED = 20260930


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=_json_default)


def _json_default(o: Any):
    try:
        import numpy as np

        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    return str(o)


def load_sibling(name: str, alias: str | None = None):
    """按文件路径加载本目录下的模块。"""
    alias = alias or name
    if alias in sys.modules:
        return sys.modules[alias]
    path = Path(_HERE) / f"{name}.py"
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


def sha(arr: Any) -> str:
    import numpy as np

    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()


def state8(joint, gripper):
    """与旧官方 ``pack_state`` 同式的 8 维状态（只用于摘要核对，不交给策略）。"""
    import numpy as np

    return np.concatenate([np.asarray(joint), np.asarray(gripper)[:1]], axis=0, dtype=np.float32)


class RecorderError(RuntimeError):
    """录制器（含磁盘写满）出错：归为基础设施故障（infra=True），不当成环境错误。"""


class _GuardedRecorder:
    """录制器代理：任何录制调用抛出的异常都转成 RecorderError（保留原因）。"""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        fn = getattr(self._inner, name)
        if not callable(fn):
            return fn

        def call(*a, **k):
            try:
                return fn(*a, **k)
            except RecorderError:
                raise
            except Exception as e:  # noqa: BLE001
                raise RecorderError(f"{name}: {type(e).__name__}: {e}") from e

        return call


class NullRecorder:
    """``--no-record`` 或单测用的空录制器（接口同 recorder.EpisodeRecorder）。"""

    def set_phase(self, phase):
        pass

    def add_frames(self, stream, frames, *, tag=""):
        return []

    def add_array(self, name, arr, *, step=None):
        pass

    def add_event(self, event):
        pass

    def close(self, summary):
        return {"RECORDER_VERIFY": "SKIP"}


# ── EnvSession ─────────────────────────────────────────────────────────────


class EnvSession:
    """一局环境。``builder`` 可由常驻进程按任务缓存后传入（与旧官方「每任务一个 EnvRunner」一致）。"""

    def __init__(self, task: str, builder_episode: int, *, max_steps: int = MAX_STEPS, recorder=None, builder=None,
                 progress_cb: Callable[[int], None] | None = None, progress_every: int = 16):
        self.task = task
        self.builder_episode = int(builder_episode)
        self.max_steps = int(max_steps)
        self.recorder = recorder if recorder is not None else NullRecorder()
        self._rec = _GuardedRecorder(self.recorder)  # 内部录制一律经代理；对外仍暴露原录制器（策略客户端靠 is 判断）
        self._builder = builder
        self.env = None
        self.steps = 0
        self.progress_cb = progress_cb
        self.progress_every = max(1, int(progress_every))
        self.timing: dict[str, Any] = {}
        self._step_s: list[float] = []
        self._rec_s = 0.0
        self.task_goal = None

    @property
    def builder(self):
        if self._builder is None:
            from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder

            t0 = time.perf_counter()
            self._builder = BenchmarkEnvBuilder(env_id=self.task, dataset="test-hard", action_space="joint_angle",
                                                max_steps=self.max_steps)
            self.timing["builder_init_s"] = time.perf_counter() - t0
        return self._builder

    def identity(self) -> dict:
        return self.builder.resolve_identity(self.builder_episode)

    def build(self) -> None:
        """``make_env_for_episode(builder_episode, max_steps=1300)``（DemonstrationWrapper 内部 +2，与官方相同）。"""
        if self.env is not None:
            return
        self._rec.set_phase("reset")
        t0 = time.perf_counter()
        self.env = self.builder.make_env_for_episode(self.builder_episode, max_steps=self.max_steps)
        self.timing["env_build_s"] = time.perf_counter() - t0

    def reset(self):
        """原样返回 ``env.reset()`` 的 ``(obs, info)``；返回后记录原始帧与数组（录制器此时仍在 reset 阶段，只入队）。"""
        import numpy as np

        self.build()
        self._rec.set_phase("reset")
        t0 = time.perf_counter()
        obs, info = self.env.reset()
        self.timing["reset_s"] = time.perf_counter() - t0
        t1 = time.perf_counter()
        goal = info.get("task_goal") if isinstance(info, dict) else None
        self.task_goal = goal[0] if isinstance(goal, list) else goal
        front = np.stack(obs["front_rgb_list"])
        wrist = np.stack(obs["wrist_rgb_list"])
        self._rec.add_frames("front", front, tag="reset")
        self._rec.add_frames("wrist", wrist, tag="reset")
        for key in ("joint_state_list", "gripper_state_list", "eef_state_list"):
            if key in obs and obs[key] is not None and len(obs[key]):
                self._rec.add_array(f"reset_{key[:-5]}", np.stack([np.asarray(x) for x in obs[key]]))
        s8 = [sha(state8(j, g)) for j, g in zip(obs["joint_state_list"], obs["gripper_state_list"])]
        self._rec.add_event({"kind": "env_reset", "task": self.task, "builder_episode": self.builder_episode,
                                 "frames": int(front.shape[0]), "demo_frames": int(front.shape[0]) - 1,
                                 "front": [sha(f) for f in front], "wrist": [sha(f) for f in wrist], "state8": s8,
                                 "task_goal": self.task_goal, "status": info.get("status") if isinstance(info, dict) else None,
                                 "reset_s": self.timing["reset_s"]})
        self._rec_s += time.perf_counter() - t1
        self.timing["demo_frames"] = int(front.shape[0]) - 1
        self._rec.set_phase("run")
        return obs, info

    def step(self, action):
        """action 原样交给 ``env.step``；记录交出去的数组与返回的当前帧、状态、终态。"""
        import numpy as np

        t0 = time.perf_counter()
        a = np.array(action, copy=True)
        self._rec.add_array("exec_action", a, step=self.steps)
        self._rec.add_event({"kind": "env_step_action", "step": self.steps, "sha": sha(a), "dtype": a.dtype.str,
                                 "shape": list(a.shape)})
        t1 = time.perf_counter()
        try:
            out = self.env.step(action)
        except Exception as e:
            self._step_s.append(time.perf_counter() - t1)
            self._rec.add_event({"kind": "env_step_exception", "step": self.steps,
                                     "error": f"{type(e).__name__}: {e}"[:800]})
            self.steps += 1
            raise
        t2 = time.perf_counter()
        self._step_s.append(t2 - t1)
        obs, reward, terminated, truncated, info = out
        status = info.get("status") if isinstance(info, dict) else None
        ev: dict[str, Any] = {"kind": "env_step", "step": self.steps, "terminated": bool(terminated),
                              "truncated": bool(truncated), "status": status, "reward": _scalar(reward)}
        if obs is None:
            ev.update(front=None, wrist=None, obs_none=True)
        else:
            front = np.stack(obs["front_rgb_list"])
            wrist = np.stack(obs["wrist_rgb_list"])
            self._rec.add_frames("front", front, tag=f"step{self.steps}")
            self._rec.add_frames("wrist", wrist, tag=f"step{self.steps}")
            joint, grip = obs["joint_state_list"][-1], obs["gripper_state_list"][-1]
            self._rec.add_array("joint_state", np.asarray(joint), step=self.steps)
            self._rec.add_array("gripper_state", np.asarray(grip), step=self.steps)
            if obs.get("eef_state_list"):
                self._rec.add_array("eef_state", np.asarray(obs["eef_state_list"][-1]), step=self.steps)
            ev.update(front=[sha(f) for f in front], wrist=[sha(f) for f in wrist], state8=sha(state8(joint, grip)))
        self._rec.add_event(ev)
        self.steps += 1
        self._rec_s += (t1 - t0) + (time.perf_counter() - t2)
        if self.progress_cb is not None and self.steps % self.progress_every == 0:
            self.progress_cb(self.steps)
        return out

    def close(self) -> None:
        import numpy as np

        if self.env is not None:
            t0 = time.perf_counter()
            try:
                self.env.close()
            finally:
                self.timing["env_close_s"] = time.perf_counter() - t0
                self.env = None
        if self._step_s:
            s = np.array(self._step_s)
            self.timing.update(step_n=int(s.size), step_total_s=float(s.sum()), step_mean_s=float(s.mean()),
                               step_p50_s=float(np.percentile(s, 50)), step_p95_s=float(np.percentile(s, 95)),
                               step_first_s=float(s[0]))
        self.timing["record_overhead_s"] = self._rec_s


def _scalar(x):
    try:
        return float(x)
    except Exception:  # noqa: BLE001
        return None


# ── 进程级信息 ──────────────────────────────────────────────────────────────


def timed_imports() -> dict:
    """分记 torch / sapien / mani_skill / robomme_hard 的 import 时间（按依赖顺序先后 import，后者不含前者）。"""
    out: dict[str, Any] = {}
    for name in ("numpy", "torch", "sapien", "mani_skill", "gymnasium", "robomme_hard"):
        t0 = time.perf_counter()
        __import__(name)
        out[f"import_{name}_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    import robomme_hard.robomme_env  # noqa: F401 注册 16 个环境
    from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder  # noqa: F401

    out["import_robomme_hard_env_s"] = time.perf_counter() - t0
    return out


def env_versions() -> dict:
    import mani_skill
    import numpy
    import sapien
    import torch

    import robomme_hard

    return {"sapien": getattr(sapien, "__version__", None), "mani_skill": getattr(mani_skill, "__version__", None),
            "torch": torch.__version__, "numpy": numpy.__version__, "python": sys.version.split()[0],
            "robomme_hard_file": robomme_hard.__file__, "executable": sys.executable}


def gpu_info() -> dict:
    cvd = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    first = cvd.split(",")[0].strip() if cvd else "0"
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,uuid,driver_version", "--format=csv,noheader", "-i", first],
                             capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
        name, uuid, drv = [x.strip() for x in out[0].split(",")]
        return {"gpu_name": name, "gpu_uuid": uuid, "gpu_driver": drv, "cuda_visible_devices": cvd}
    except Exception as e:  # noqa: BLE001
        return {"gpu_name": None, "gpu_uuid": None, "gpu_driver": None, "cuda_visible_devices": cvd,
                "gpu_error": repr(e)}


def git_info() -> dict:
    def run(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True).stdout.strip()

    return {"git_commit": run("rev-parse", "HEAD"),
            "git_dirty": bool(run("status", "--porcelain", "--", "scripts/eval-official", "src"))}


def cpu_info() -> dict:
    try:
        model = next((l.split(":", 1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines()
                      if l.startswith("model name")), None)
    except OSError:
        model = None
    return {"cpu_model": model, "affinity_n": len(os.sched_getaffinity(0)),
            "affinity": sorted(os.sched_getaffinity(0))}


# ── 身份 ────────────────────────────────────────────────────────────────────


def key_of(row: dict) -> str:
    return f"{row['task']}_{int(row['seed'])}"


def parse_canary(spec: str) -> dict:
    """``Task:source_episode:seed`` 或 JSON 对象。builder_episode = (source_episode-3)//4（官方 test 里 hard 局）。"""
    if spec.strip().startswith("{"):
        row = json.loads(spec)
    else:
        task, se, seed = spec.split(":")
        row = {"task": task, "source_episode": int(se), "seed": int(seed)}
    row.setdefault("builder_episode", (int(row["source_episode"]) - 3) // 4)
    return row


def check_identity(resolved: dict, want: dict) -> str | None:
    """builder 解析出的身份必须与清单一致；不一致返回说明（运行阻塞）。"""
    bad = []
    if resolved.get("tier") != XHARD0:
        bad.append(f"tier={resolved.get('tier')}")
    if int(resolved.get("seed", -1)) != int(want["seed"]):
        bad.append(f"seed builder={resolved.get('seed')} want={want['seed']}")
    if int(resolved.get("source_episode", -1)) != int(want["source_episode"]):
        bad.append(f"source_episode builder={resolved.get('source_episode')} want={want['source_episode']}")
    return "; ".join(bad) or None


def order_identities(rows: list[dict], order: str, shuffle_seed: int) -> list[dict]:
    rows = list(rows)
    if order == "reverse":
        rows.reverse()
    elif order == "shuffle":
        rows.sort(key=lambda r: (r["task"], int(r["source_episode"])))
        random.Random(shuffle_seed).shuffle(rows)
    return rows


def read_results(path: Path) -> list[dict]:
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 崩溃留下的半行
    return rows


def append_result(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                f.write(b"\n")
        f.write((dumps(record) + "\n").encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())


# ── 常驻客户端 ──────────────────────────────────────────────────────────────


class SeatRunner:
    """一个席位上一个策略的常驻客户端。``policy_mod`` / ``recorder_factory`` / ``builder_factory`` 可注入（单测）。"""

    def __init__(self, args, *, policy_mod=None, recorder_factory=None, builder_factory=None, proc_info=None):
        self.args = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.results_path = self.out / "results.jsonl"
        self.progress_path = self.out / "progress.json"
        self.policy_mod = policy_mod
        self.recorder_factory = recorder_factory
        self.builder_factory = builder_factory
        self.builders: dict[str, Any] = {}
        self.proc_info = proc_info or {}
        self.episodes_done = 0
        self.queue = None
        self._lock = threading.Lock()
        self._current: dict | None = None
        self._built_once = False

    # 进度心跳：原子替换写 progress.json；同时刷新队列认领的 mtime
    def progress(self, step: int = 0, **extra) -> None:
        cur = self._current or {}
        doc = {"pid": os.getpid(), "host": socket.gethostname(), "seat": self.args.seat, "policy": self.args.policy,
               "cond": self.args.cond, "key": cur.get("key"), "step": step, "t": time.time(),
               "episodes_done": self.episodes_done, **extra}
        tmp = self.progress_path.with_suffix(".json.tmp")
        tmp.write_text(dumps(doc), encoding="utf-8")
        os.replace(tmp, self.progress_path)
        if self.queue is not None and cur.get("claim") is not None:
            self.queue.heartbeat(cur["claim"])

    def builder_for(self, task: str):
        if task not in self.builders:
            if self.builder_factory is not None:
                self.builders[task] = self.builder_factory(task)
            else:
                from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder

                self.builders[task] = BenchmarkEnvBuilder(env_id=task, dataset="test-hard", action_space="joint_angle",
                                                          max_steps=self.args.max_steps)
        return self.builders[task]

    def base_record(self, ident: dict, *, attempt: int, canary: bool) -> dict:
        return {"task": ident["task"], "source_episode": int(ident["source_episode"]), "seed": int(ident["seed"]),
                "identity": {"tier": XHARD0, "seed": int(ident["seed"]), "source_episode": int(ident["source_episode"])},
                "builder_episode": int(ident["builder_episode"]), "policy": self.args.policy, "cond": self.args.cond,
                "seat": self.args.seat, "host": socket.gethostname(), "attempt": attempt, "canary": canary,
                "gpu_name": self.proc_info.get("gpu_name"), "gpu_uuid": self.proc_info.get("gpu_uuid"),
                "git_commit": self.proc_info.get("git_commit"), "git_dirty": self.proc_info.get("git_dirty"),
                "max_steps": self.args.max_steps}

    def run_one(self, ident: dict, *, attempt: int = 1, canary: bool = False, claim=None) -> dict:
        key = key_of(ident)
        suffix = (".canary" if canary else "") + (f".a{attempt}" if attempt > 1 else "")
        rec_dir = self.out / "rec" / f"{key}{suffix}"
        record = self.base_record(ident, attempt=attempt, canary=canary)
        record["rec_dir"] = str(rec_dir)
        if claim is not None:
            record["claim_token"] = claim.token
        self._current = {"key": key, "claim": claim, "t0": time.time()}
        self.progress(0, phase="start")
        builder = self.builder_for(ident["task"])
        resolved = builder.resolve_identity(int(ident["builder_episode"]))
        bad = check_identity(resolved, ident)
        if bad:
            record.update(status="error", task_success=False, steps=0, error=f"IDENTITY_MISMATCH {bad}",
                          run_blocked=True, infra=False, resolved_identity=resolved)
            append_result(self.results_path, record)
            print(f"RUN_BLOCKED reason=identity key={key} detail={bad}", flush=True)
            raise SystemExit(EXIT_BLOCKED)
        meta = dict(record, resolved_identity=resolved, env=self.proc_info.get("env"),
                    never_degrade=bool(self.args.never_degrade), baseline=bool(self.args.baseline))
        try:
            recorder = self.recorder_factory(rec_dir, meta) if self.recorder_factory else NullRecorder()
        except Exception as e:  # noqa: BLE001 录制器建不起来（如磁盘满）= 基础设施故障
            record.update(status="error", task_success=False, steps=0, infra=True, infra_reason="recorder",
                          error=f"RecorderError: init: {type(e).__name__}: {e}"[:800])
            append_result(self.results_path, record)
            print(f"EPISODE_DONE policy={self.args.policy} key={key} status=error infra=True reason=recorder_init", flush=True)
            return record
        session = EnvSession(ident["task"], int(ident["builder_episode"]), max_steps=self.args.max_steps,
                             recorder=recorder, builder=builder, progress_cb=lambda s: self.progress(s))
        conn_info = {"host": self.args.host, "port": self.args.port, "max_steps": self.args.max_steps,
                     "policy": self.args.policy, "seat": self.args.seat}
        limit = self.args.episode_wall_s + (self.args.first_extra_s if self.episodes_done == 0 else 0)
        # first_extra_s 只给「server 刚（重）起后的第一局」：由 run_seat.sh 在 server 新起时传 600，客户端单独重起时传 0
        state = {"finished": False}
        timer = None
        if limit > 0:
            timer = threading.Timer(limit, self._on_wall_timeout, args=(record, claim, limit, state))
            timer.daemon = True
            timer.start()
        t0 = time.perf_counter()
        first_build = not self._built_once
        try:
            try:
                session.build()
                self._built_once = True
            except Exception as e:  # noqa: BLE001 构建失败（如 Vulkan）按基础设施故障记
                res = {"status": "error", "task_success": False, "steps": 0, "error": f"{type(e).__name__}: {e}"[:800],
                       "infra": True, "infra_reason": "env_build"}
            else:
                res = self.policy_mod.run_episode(session, ident, conn_info, recorder)
        finally:
            with self._lock:
                state["finished"] = True
            if timer is not None:
                timer.cancel()
        try:
            session.close()
        except Exception as e:  # noqa: BLE001
            res.setdefault("close_error", repr(e))
        wall = time.perf_counter() - t0
        try:
            rsum = recorder.close({"status": res.get("status"), "steps": res.get("steps")})
        except Exception as e:  # noqa: BLE001 收尾失败（如磁盘满）= 基础设施故障
            rsum = {"RECORDER_VERIFY": "ERROR", "error": f"{type(e).__name__}: {e}"[:800]}
            res.update(infra=True, infra_reason="recorder_close")
        if "RecorderError" in str(res.get("error") or "") or "RecorderError" in str(res.get("env_exception") or ""):
            res.update(infra=True, infra_reason="recorder")
        timing = {"episode_wall_s": wall, "first_build_in_process": first_build, "env": dict(session.timing),
                  "policy": res.pop("timing", None), "recorder": rsum, "episode_index_in_process": self.episodes_done}
        if self.episodes_done == 0:
            timing["process_init"] = self.proc_info.get("init_timing")
        record.update(res)
        record["task_success"] = record.get("status") == "success"
        record["timing"] = timing
        record["recorder_verify"] = (rsum or {}).get("RECORDER_VERIFY")
        append_result(self.results_path, record)
        self.episodes_done += 1
        self.progress(record.get("steps", 0), phase="done")
        print(f"EPISODE_DONE policy={self.args.policy} key={key} status={record['status']} steps={record.get('steps')} "
              f"wall_s={wall:.1f} infra={record.get('infra')} canary={canary} recorder={record['recorder_verify']}",
              flush=True)
        return record

    @staticmethod
    def _claim_heartbeat(q, claim, stop: threading.Event, every_s: float = 60.0) -> None:
        """持有认领期间每 60 s 刷新认领 mtime（长局、首次编译期间也不被当成死席位回收）；进程死了线程随之消失。"""
        while not stop.wait(every_s):
            try:
                q.heartbeat(claim)
            except Exception:  # noqa: BLE001
                pass

    def _on_wall_timeout(self, record: dict, claim, limit: float, state: dict) -> None:
        with self._lock:
            if state["finished"]:
                return
            rec = dict(record, status="error", task_success=False, steps=None, infra=True, infra_reason="episode_wall",
                       error=f"INFRA_TIMEOUT episode_wall>{limit:.0f}s")
            append_result(self.results_path, rec)
            if self.queue is not None and claim is not None:
                self.queue.fail_infra(claim, rec)
            print(f"INFRA_TIMEOUT key={key_of(record)} limit_s={limit:.0f}", flush=True)
            sys.stdout.flush()
            os._exit(EXIT_WALL)

    # ── 两种来源 ────────────────────────────────────────────────────────
    def run_identities(self, rows: list[dict]) -> int:
        prev = read_results(self.results_path)
        done = {key_of(r) for r in prev if not r.get("infra") and not r.get("canary") and not r.get("run_blocked")}
        attempts: dict[str, int] = {}
        for r in prev:
            if not r.get("canary"):
                attempts[key_of(r)] = attempts.get(key_of(r), 0) + 1
        todo = [r for r in rows if key_of(r) not in done]
        print(f"RUN_PLAN policy={self.args.policy} total={len(rows)} resume_skip={len(rows) - len(todo)} todo={len(todo)}",
              flush=True)
        retry_left = self.args.infra_retries
        pending = list(todo)
        while pending:
            ident = pending.pop(0)
            k = key_of(ident)
            attempts[k] = attempts.get(k, 0) + 1
            rec = self.run_one(ident, attempt=attempts[k])
            if rec.get("infra") and retry_left > 0:
                retry_left -= 1
                pending.append(ident)
        return 0

    def run_queue(self, q) -> int:
        self.queue = q
        rec = q.recover_seat(self.args.seat, self.results_path)
        if rec["acked"] or rec["failed"]:
            print(f"QUEUE_RECOVER seat={self.args.seat} acked={len(rec['acked'])} failed={len(rec['failed'])}", flush=True)
        n = 0
        while True:
            claim = q.claim_next(self.args.seat)
            if claim is None:
                # 没有可认领的：全部有终态才退出；否则回收死席位的无进展认领，等 30 s 再试
                if q.all_terminal():
                    break
                reaped = q.reap_stale(self.args.reap_threshold_s)
                if reaped:
                    print(f"QUEUE_REAP seat={self.args.seat} keys={','.join(reaped)}", flush=True)
                    continue
                self.progress(0, phase="waiting_open_claims")
                time.sleep(self.args.poll_s)
                continue
            ident = q.identity(claim.key)
            hb_stop = threading.Event()
            hb = threading.Thread(target=self._claim_heartbeat, args=(q, claim, hb_stop), daemon=True)
            hb.start()
            try:
                record = self.run_one(ident, attempt=int(claim["attempt"]), claim=claim)
            finally:
                hb_stop.set()
            if record.get("infra"):
                outcome = q.fail_infra(claim, record)
                print(f"QUEUE_INFRA key={claim.key} outcome={outcome}", flush=True)
            else:
                ok = q.complete(claim, record)
                if not ok:
                    print(f"QUEUE_LATE key={claim.key} token={claim.token}", flush=True)
            n += 1
            if self.args.limit and n >= self.args.limit:
                break
        return 0


def cmd_run(args) -> int:
    t_proc = time.perf_counter()
    init = timed_imports()
    proc = {"init_timing": init, "env": env_versions(), **gpu_info(), **git_info(), **cpu_info()}
    policy_mod = load_sibling(f"{args.policy}_client")
    recorder_factory = None
    if not args.no_record:
        recorder_mod = load_sibling("recorder")

        def recorder_factory(rec_dir, meta):
            return recorder_mod.EpisodeRecorder(rec_dir, meta)
    init["process_ready_s"] = time.perf_counter() - t_proc
    print(f"CLIENT_READY policy={args.policy} seat={args.seat} cond={args.cond} host={socket.gethostname()} "
          f"gpu={proc.get('gpu_name')} sapien={proc['env']['sapien']} torch={proc['env']['torch']} "
          f"robomme_hard={proc['env']['robomme_hard_file']} git={proc['git_commit'][:12]} dirty={proc['git_dirty']} "
          f"init_s={init['process_ready_s']:.1f}", flush=True)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / f"process-{os.getpid()}.json").write_text(dumps(proc), encoding="utf-8")
    runner = SeatRunner(args, policy_mod=policy_mod, recorder_factory=recorder_factory, proc_info=proc)
    if args.canary:
        runner.run_one(parse_canary(args.canary), canary=True)
    if args.queue:
        qmod = load_sibling("claim_queue")
        rc = runner.run_queue(qmod.ClaimQueue(Path(args.queue) / args.policy))
    else:
        rows = json.loads(Path(args.identities).read_text(encoding="utf-8"))
        if args.only:
            want = set(args.only.split(","))
            rows = [r for r in rows if key_of(r) in want]
        rows = order_identities(rows, args.order, args.shuffle_seed)
        if args.limit:
            rows = rows[: args.limit]
        rc = runner.run_identities(rows)
    runner.progress(0, phase="finished")
    print(f"全部完成 policy={args.policy} seat={args.seat} episodes={runner.episodes_done}", flush=True)
    return rc


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="v7.5eval 新接口环境侧常驻客户端")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--policy", required=True, choices=["mme", "smvla"])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--identities", help="身份清单 json（list of {task, source_episode, seed, builder_episode}）")
    src.add_argument("--queue", help="队列根目录（其下 <policy>/）")
    p.add_argument("--cond", required=True, help="条件代号，如 E1／N")
    p.add_argument("--seat", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--order", default="forward", choices=["forward", "reverse", "shuffle"])
    p.add_argument("--shuffle-seed", type=int, default=DEFAULT_SHUFFLE_SEED)
    p.add_argument("--canary", default=None, help="Task:source_episode:seed，先跑 1 局金丝雀（只记录不拦截）")
    p.add_argument("--only", default=None, help="只跑这些 <task>_<seed>（逗号分隔）")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--max-steps", type=int, default=MAX_STEPS)
    p.add_argument("--episode-wall-s", type=float, default=0.0, help="单局墙钟上限（0=不限）；超时记基础设施超时并退出 75")
    p.add_argument("--first-extra-s", type=float, default=600.0,
                   help="本进程第一局额外放宽（首次推理编译）；run_seat.sh 只在 server 新（重）起后传 600，否则传 0")
    p.add_argument("--reap-threshold-s", type=float, default=1200.0, help="队列模式：认领无进展多久算死席位")
    p.add_argument("--poll-s", type=float, default=30.0, help="队列模式：等待别席未完成认领时的轮询间隔")
    p.add_argument("--infra-retries", type=int, default=2, help="identities 模式下基础设施失败的重试局数上限")
    p.add_argument("--no-record", action="store_true")
    p.add_argument("--never-degrade", action="store_true")
    p.add_argument("--baseline", action="store_true")
    p.set_defaults(func=cmd_run)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
