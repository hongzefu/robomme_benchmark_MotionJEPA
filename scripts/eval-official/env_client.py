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

退出码：0 全部完成；3 运行阻塞；5 reset 额度耗尽（V8，run_seat.sh 不得重启）；75 单局墙钟超时（基础设施超时，
已记录，由 run_seat.sh 重起）。

V8 模式（``--v8``；1001-v8-post-evaluation-gl-plan.md 第一部分 §1 第 4 条、§3，契约 C2）：身份清单为
``eval_manifest.py`` 产出的分片 JSON；身份逐键核对 tier／seed／candidate／spec_sha256 与有效上限
``hard_specs.TIER_MAX_STEPS[tier]``；``EnvSession.step`` 在已执行 ``step_cap`` 步后不再进入环境、抛
``StepCapReached``，``run_one`` 一律收为 ``status=timeout``；``EnvSession.build``／``reset`` 每次实际调用前向持久账本
（``--ledger``，JSONL + fsync）领一次 reset 额度，耗尽抛 ``ResetBudgetExhausted`` → 退出码 5；infra 重试额度与每身份
至多 2 次尝试都从账本统计，进程重启不刷新；第一次终态写 ``accept``，之后的终态记 ``late``。不带 ``--v8`` 时一切同旧版。

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
import inspect  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Callable  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
for _extra in (REPO / "src",):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

MAX_STEPS = 1300
XHARD0 = "xhard0"
EXIT_BLOCKED = 3
EXIT_BUDGET = 5
EXIT_WALL = 75
DEFAULT_SHUFFLE_SEED = 20260930
TERMINAL_STATUSES = ("success", "fail", "timeout")
#: V8 每身份至多尝试次数（首试 + 1 次基础设施重试）
V8_MAX_ATTEMPTS = 2
#: V8 执行身份行（eval_manifest.py shard-NN.json 的元素）必须恰有的字段
V8_IDENTITY_KEYS = ("task", "tier", "seed", "candidate", "builder_episode", "source_episode", "spec_sha256",
                    "effective_max_steps", "key")


def tier_max_steps() -> dict:
    """V8 有效上限表：与 builder 同一份 ``hard_specs.TIER_MAX_STEPS``。"""
    from robomme_hard.env_record_wrapper import hard_specs

    return dict(hard_specs.TIER_MAX_STEPS)


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


class StepCapReached(RuntimeError):
    """V8：执行段已满 ``step_cap`` 步仍未成功，第 ``step_cap+1`` 次 ``step`` 不进入环境（run_one 收为 timeout）。"""


class ResetBudgetExhausted(RuntimeError):
    """V8：持久账本里的 reset 额度（build 与 reset 各算一次）已用尽（客户端以退出码 5 停止）。"""


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
                 progress_cb: Callable[[int], None] | None = None, progress_every: int = 16,
                 step_cap: int | None = None, claim_reset: Callable[[str], None] | None = None):
        self.task = task
        self.builder_episode = int(builder_episode)
        self.max_steps = int(max_steps)
        # V8：step_cap=None 时不截断（旧模式）；claim_reset(what) 在每次实际 build／reset 前调用，额度耗尽抛
        # ResetBudgetExhausted（旧模式 None，不领额度）
        self.step_cap = None if step_cap is None else int(step_cap)
        self.claim_reset = claim_reset
        self.cap_hit = False
        self.budget_exhausted = False
        self.reset_calls = 0
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

    def _claim(self, what: str) -> None:
        """V8：向持久账本领一次 reset 额度（build 与 reset 各算一次），领到后才计入 reset_calls。"""
        if self.claim_reset is not None:
            try:
                self.claim_reset(what)
            except ResetBudgetExhausted:
                self.budget_exhausted = True
                raise
        self.reset_calls += 1

    def build(self) -> None:
        """``make_env_for_episode(builder_episode, max_steps=1300)``（DemonstrationWrapper 内部 +2，与官方相同）。"""
        if self.env is not None:
            return
        self._claim("build")
        self._rec.set_phase("reset")
        t0 = time.perf_counter()
        self.env = self.builder.make_env_for_episode(self.builder_episode, max_steps=self.max_steps)
        self.timing["env_build_s"] = time.perf_counter() - t0

    def reset(self):
        """原样返回 ``env.reset()`` 的 ``(obs, info)``；返回后记录原始帧与数组（录制器此时仍在 reset 阶段，只入队）。"""
        import numpy as np

        self.build()
        self._claim("reset")
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
        """action 原样交给 ``env.step``；记录交出去的数组与返回的当前帧、状态、终态。

        V8（``step_cap`` 非空）：已执行 ``step_cap`` 步后再调用即不进入环境，置 ``cap_hit`` 并抛 ``StepCapReached``；
        第 ``step_cap`` 步及之前环境报的终态照常返回。"""
        import numpy as np

        if self.step_cap is not None and self.steps >= self.step_cap:
            self.cap_hit = True
            self._rec.add_event({"kind": "step_cap_reached", "step": self.steps, "cap": self.step_cap})
            raise StepCapReached(f"STEP_CAP exec_steps={self.steps} cap={self.step_cap}")
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


def v8_key(row: dict) -> str:
    """V8 身份键：结果、账本、录像目录统一用它。"""
    return f"{row['task']}_{row['tier']}_{int(row['seed'])}"


def key_of(row: dict) -> str:
    """旧模式 ``<task>_<seed>``；V8 身份行与结果行带 ``key``（= ``<task>_<tier>_<seed>``），直接用它。"""
    if row.get("key"):
        return str(row["key"])
    return f"{row['task']}_{int(row['seed'])}"


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_v8_identity(row: dict, tier_max: dict | None = None) -> str | None:
    """V8 执行身份行的结构核对（字段齐全、nullable 严格、key 与有效上限自洽）；不符返回说明。"""
    bad = []
    missing = [k for k in V8_IDENTITY_KEYS if k not in row]
    if missing:
        return f"missing_fields={missing}"
    if not _is_int(row["seed"]) or not _is_int(row["builder_episode"]):
        bad.append("seed/builder_episode 非整数")
    if row["candidate"] is not None and not _is_int(row["candidate"]):
        bad.append(f"candidate={row['candidate']!r}")
    if row["source_episode"] is not None and not _is_int(row["source_episode"]):
        bad.append(f"source_episode={row['source_episode']!r}")
    if not isinstance(row["spec_sha256"], str) or len(row["spec_sha256"]) != 64:
        bad.append(f"spec_sha256={row['spec_sha256']!r}")
    if not bad and row["key"] != v8_key(row):
        bad.append(f"key={row['key']} want={v8_key(row)}")
    if tier_max is not None and row.get("effective_max_steps") != tier_max.get(row["tier"]):
        bad.append(f"effective_max_steps={row.get('effective_max_steps')} tier_max={tier_max.get(row['tier'])}")
    return "; ".join(bad) or None


def check_identity(resolved: dict, want: dict, *, v8: bool = False, tier_max: dict | None = None) -> str | None:
    """builder 解析出的身份必须与清单一致；不一致返回说明（运行阻塞）。

    旧模式：tier 必须是 xhard0，seed、source_episode 相等。V8：tier／seed／candidate／spec_sha256 逐键严格相等
    （candidate 可空，两边同为 null 或同一整数），且身份行的 ``effective_max_steps`` 等于 ``TIER_MAX_STEPS[tier]``。"""
    bad = []
    if v8:
        if resolved.get("tier") != want.get("tier"):
            bad.append(f"tier builder={resolved.get('tier')} want={want.get('tier')}")
        for k in ("seed", "candidate"):
            rv, wv = resolved.get(k), want.get(k)
            if not ((rv is None and wv is None) or (_is_int(rv) and _is_int(wv) and rv == wv)):
                bad.append(f"{k} builder={rv!r} want={wv!r}")
        if not (isinstance(want.get("spec_sha256"), str) and resolved.get("spec_sha256") == want.get("spec_sha256")):
            bad.append(f"spec_sha256 builder={resolved.get('spec_sha256')} want={want.get('spec_sha256')}")
        tm = (tier_max or {}).get(want.get("tier"))
        if tm is None or want.get("effective_max_steps") != tm:
            bad.append(f"effective_max_steps={want.get('effective_max_steps')} tier_max={tm}")
        return "; ".join(bad) or None
    if resolved.get("tier") != XHARD0:
        bad.append(f"tier={resolved.get('tier')}")
    if int(resolved.get("seed", -1)) != int(want["seed"]):
        bad.append(f"seed builder={resolved.get('seed')} want={want['seed']}")
    if int(resolved.get("source_episode", -1)) != int(want["source_episode"]):
        bad.append(f"source_episode builder={resolved.get('source_episode')} want={want['source_episode']}")
    return "; ".join(bad) or None


def order_identities(rows: list[dict], order: str, shuffle_seed: int, *, v8: bool = False) -> list[dict]:
    rows = list(rows)
    if order == "reverse":
        rows.reverse()
    elif order == "shuffle":
        if v8:  # 新值局 source_episode 为空：按 (task, tier, seed) 定序后再打乱
            rows.sort(key=lambda r: (r["task"], r["tier"], int(r["seed"])))
        else:
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


# ── V8 持久尝试账本 ─────────────────────────────────────────────────────────


class AttemptLedger:
    """V8 持久尝试账本（JSONL，追加写 + fsync；契约 C2）。一个账本只有一个写者（一席一策略一个客户端进程）。

    行：``{"t","kind","key","attempt_id","attempt_no","seat","policy",...}``，kind ∈
    ``budget | budget_raise | attempt_start | reset_claim | attempt_end | accept``。
    全部计数从账本内容推出（进程重启读回，不刷新）：

    * reset 额度：``reset_claim`` 行数（历史账本里的金丝雀行同样计入）对 ``--reset-budget``；
    * 作废尝试：``attempt_end.budget_exhausted=true`` 的尝试没有执行段（额度在 build／reset 前就被拒），不计入每身份
      2 次上限、也不计入 infra 重试额度；
    * infra 重试：``attempt_start.retry=true`` 且未作废的尝试数，对 ``--infra-retry-budget``；
    * 权威终态：每身份第一条 ``accept`` 行的 ``accepted_attempt_id``；success／fail／timeout 与非 infra 错误
      （status=error、infra=false）都 accept，infra 错误不 accept（重试额度或 2 次用满时该身份无 accept，汇总计 missing）。
    """

    def __init__(self, path: Path | str, *, seat: str, policy: str):
        self.path = Path(path)
        self.seat = str(seat)
        self.policy = str(policy)
        self.reset_budget: int | None = None
        self.infra_retry_budget: int | None = None
        self.reset_claims = 0
        self.budget_hist_max: int | None = None
        self.starts: dict[str, list[dict]] = {}  # key -> attempt_start 行（含作废）
        self.ended: dict[str, dict] = {}  # attempt_id -> attempt_end 行
        self.accepted: dict[str, str] = {}  # key -> accepted_attempt_id
        self._lock = threading.Lock()
        for row in read_results(self.path):
            self._apply(row)

    # 状态推导
    def _apply(self, row: dict) -> None:
        kind = row.get("kind")
        if kind == "reset_claim":
            self.reset_claims += 1
        elif kind == "budget":
            self.budget_hist_max = max(self.budget_hist_max or 0, int(row["reset_budget"]))
        elif kind == "budget_raise":
            self.budget_hist_max = max(self.budget_hist_max or 0, int(row["to"]))
        elif kind == "attempt_start":
            self.starts.setdefault(row["key"], []).append(row)
        elif kind == "attempt_end":
            self.ended[row["attempt_id"]] = row
        elif kind == "accept":
            self.accepted.setdefault(row["key"], row["accepted_attempt_id"])

    def _void(self, attempt_id: str) -> bool:
        end = self.ended.get(attempt_id)
        return bool(end and end.get("budget_exhausted"))

    def append(self, row: dict) -> dict:
        row = {"t": time.time(), "seat": self.seat, "policy": self.policy, **row}
        with self._lock:
            append_result(self.path, row)
            self._apply(row)
        return row

    # 进程启动：记预算；命令行额度大于账本历史最大值即记一次提升
    def start(self, reset_budget: int, infra_retry_budget: int, *, reason: str = "cli_reset_budget") -> None:
        reset_budget, infra_retry_budget = int(reset_budget), int(infra_retry_budget)
        prev = self.budget_hist_max
        if prev is not None and reset_budget > prev:
            self.append({"kind": "budget_raise", "from": prev, "to": reset_budget, "reason": reason})
            print(f"RESET_BUDGET_RAISE from={prev} to={reset_budget} reason={reason}", flush=True)
        self.append({"kind": "budget", "reset_budget": reset_budget, "infra_retry_budget": infra_retry_budget,
                     "pid": os.getpid(), "host": socket.gethostname()})
        self.reset_budget, self.infra_retry_budget = reset_budget, infra_retry_budget

    # 计数
    def reset_left(self) -> int:
        return int(self.reset_budget or 0) - self.reset_claims

    def attempts_total(self, key: str) -> int:
        """含作废尝试；新尝试编号 = 此数 + 1（录像目录名唯一）。"""
        return len(self.starts.get(key, []))

    def attempts_used(self, key: str) -> int:
        """不含作废尝试：对每身份 2 次上限。"""
        return sum(not self._void(r["attempt_id"]) for r in self.starts.get(key, []))

    def infra_retries_used(self) -> int:
        return sum(bool(r.get("retry")) and not self._void(r["attempt_id"])
                   for rows in self.starts.values() for r in rows)

    def infra_retries_left(self) -> int:
        return int(self.infra_retry_budget or 0) - self.infra_retries_used()

    def last_end_final(self, key: str) -> bool:
        """最后一次未作废尝试的 attempt_end 是否已是最终结局（非 infra 错误等）：是则该身份不再重跑。"""
        live = [r for r in self.starts.get(key, []) if not self._void(r["attempt_id"])]
        if not live:
            return False
        end = self.ended.get(live[-1]["attempt_id"])
        return bool(end) and self.is_final(end)

    def dangling(self) -> list[dict]:
        """有 attempt_start、无 attempt_end 的尝试（进程被杀等）。"""
        return [r for rows in self.starts.values() for r in rows if r["attempt_id"] not in self.ended]

    # 写入
    def claim_reset(self, *, key: str, attempt_id: str, attempt_no: int, what: str, canary: bool = False) -> None:
        with self._lock:
            if self.reset_claims >= int(self.reset_budget or 0):
                raise ResetBudgetExhausted(f"reset 额度耗尽 claims={self.reset_claims} budget={self.reset_budget}")
            row = {"t": time.time(), "seat": self.seat, "policy": self.policy, "kind": "reset_claim", "key": key,
                   "attempt_id": attempt_id, "attempt_no": attempt_no, "what": what, "canary": bool(canary),
                   "n": self.reset_claims + 1}
            append_result(self.path, row)
            self._apply(row)

    def attempt_start(self, *, key: str, attempt_id: str, attempt_no: int, retry: bool, **extra) -> None:
        self.append({"kind": "attempt_start", "key": key, "attempt_id": attempt_id, "attempt_no": attempt_no,
                     "retry": bool(retry), **extra})

    @staticmethod
    def is_final(record: dict) -> bool:
        """该尝试是否构成身份的最终结局（主会话 2026-10-02 口径裁定）：success／fail／timeout，以及非基础设施错误
        （status=error、infra=false、非 budget_exhausted、非 run_blocked——如 reset 失败、环境自报 error、客户端
        TypeError 等）。infra=true 的错误不是结局（可在额度内重试；额度或 2 次用满则不 accept，汇总计 missing）。"""
        status = record.get("status")
        if status in TERMINAL_STATUSES:
            return True
        return (status == "error" and not record.get("infra") and not record.get("budget_exhausted")
                and not record.get("run_blocked"))

    def is_late(self, record: dict) -> bool:
        return self.is_final(record) and record["key"] in self.accepted

    def attempt_end(self, record: dict) -> bool:
        """写 attempt_end；最终结局且该身份尚无 accept 时再写 accept（status 可为 error）。返回 late。"""
        key, status = record["key"], record.get("status")
        late = self.is_late(record)
        base = {"key": key, "attempt_id": record["attempt_id"], "attempt_no": record["attempt_no"]}
        self.append({"kind": "attempt_end", **base, "status": status, "infra": bool(record.get("infra")),
                     "cap_hit": bool(record.get("cap_hit")), "exec_steps": record.get("exec_steps"),
                     "budget_exhausted": bool(record.get("budget_exhausted")), "late": late,
                     **({"recovered": True} if record.get("recovered") else {})})
        if self.is_final(record) and not late:
            self.append({"kind": "accept", **base, "accepted_attempt_id": record["attempt_id"], "status": status})
        return late


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
        self._lock = threading.Lock()
        self._current: dict | None = None
        self._built_once = False
        rec_root = getattr(args, "rec_root", None)
        self.rec_root = Path(rec_root) if rec_root else self.out / "rec"
        self.v8 = bool(getattr(args, "v8", False))
        self.ledger: AttemptLedger | None = None
        self.tier_max: dict | None = None
        if self.v8:
            if not getattr(args, "ledger", None):
                raise ValueError("V8 模式必须给 --ledger")
            if getattr(args, "reset_budget", None) is None or getattr(args, "infra_retry_budget", None) is None:
                raise ValueError("V8 模式必须给 --reset-budget 与 --infra-retry-budget")
            self.tier_max = tier_max_steps()
            self.ledger = AttemptLedger(args.ledger, seat=args.seat, policy=args.policy)
            self.ledger.start(args.reset_budget, args.infra_retry_budget,
                              reason=getattr(args, "budget_raise_reason", None) or "cli_reset_budget")

    # 进度心跳：原子替换写 progress.json
    def progress(self, step: int = 0, **extra) -> None:
        cur = self._current or {}
        doc = {"pid": os.getpid(), "host": socket.gethostname(), "seat": self.args.seat, "policy": self.args.policy,
               "cond": self.args.cond, "key": cur.get("key"), "step": step, "t": time.time(),
               "episodes_done": self.episodes_done, **extra}
        tmp = self.progress_path.with_suffix(".json.tmp")
        tmp.write_text(dumps(doc), encoding="utf-8")
        os.replace(tmp, self.progress_path)

    def builder_for(self, task: str, max_steps: int | None = None):
        """按 (task, 有效上限) 缓存 builder，避免跨档沿用旧上限。旧模式上限即 ``--max-steps``。"""
        ms = int(self.args.max_steps if max_steps is None else max_steps)
        ck = (task, ms)
        if ck not in self.builders:
            if self.builder_factory is not None:
                try:
                    n_params = len(inspect.signature(self.builder_factory).parameters)
                except (TypeError, ValueError):
                    n_params = 1
                self.builders[ck] = self.builder_factory(task, ms) if (self.v8 and n_params >= 2) \
                    else self.builder_factory(task)
            else:
                from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder

                self.builders[ck] = BenchmarkEnvBuilder(env_id=task, dataset="test-hard", action_space="joint_angle",
                                                        max_steps=ms)
        return self.builders[ck]

    def policy_kwargs(self, effective_max_steps: int) -> dict:
        """V8：策略 ``run_episode`` 签名里有 ``max_steps``／``reset_retries`` 关键字（smvla）就显式传
        ``max_steps=有效上限``、``reset_retries=0``；没有（mme，只读 conn_info）就不传。旧模式一律不传。"""
        if not self.v8:
            return {}
        try:
            params = inspect.signature(self.policy_mod.run_episode).parameters
        except (TypeError, ValueError):
            return {}
        kw: dict[str, Any] = {}
        if "max_steps" in params:
            kw["max_steps"] = int(effective_max_steps)
        if "reset_retries" in params:
            kw["reset_retries"] = 0
        return kw

    def base_record(self, ident: dict, *, attempt: int) -> dict:
        # 结果行保留 canary 字段（恒为 False），下游读结果的工具按该键过滤，格式不变
        if self.v8:
            ident_full = {"tier": ident["tier"], "seed": int(ident["seed"]), "candidate": ident["candidate"],
                          "spec_sha256": ident["spec_sha256"], "builder_episode": int(ident["builder_episode"])}
            return {"v8": True, "key": key_of(ident), "task": ident["task"], "tier": ident["tier"],
                    "seed": int(ident["seed"]), "candidate": ident["candidate"], "spec_sha256": ident["spec_sha256"],
                    "source_episode": ident.get("source_episode"), "identity": ident_full,
                    "builder_episode": int(ident["builder_episode"]), "policy": self.args.policy,
                    "cond": self.args.cond, "seat": self.args.seat, "host": socket.gethostname(), "attempt": attempt,
                    "attempt_no": attempt, "canary": False,
                    "gpu_name": self.proc_info.get("gpu_name"), "gpu_uuid": self.proc_info.get("gpu_uuid"),
                    "git_commit": self.proc_info.get("git_commit"), "git_dirty": self.proc_info.get("git_dirty"),
                    "max_steps": ident.get("effective_max_steps"),
                    "effective_max_steps": ident.get("effective_max_steps")}
        return {"task": ident["task"], "source_episode": int(ident["source_episode"]), "seed": int(ident["seed"]),
                "identity": {"tier": XHARD0, "seed": int(ident["seed"]), "source_episode": int(ident["source_episode"])},
                "builder_episode": int(ident["builder_episode"]), "policy": self.args.policy, "cond": self.args.cond,
                "seat": self.args.seat, "host": socket.gethostname(), "attempt": attempt, "canary": False,
                "gpu_name": self.proc_info.get("gpu_name"), "gpu_uuid": self.proc_info.get("gpu_uuid"),
                "git_commit": self.proc_info.get("git_commit"), "git_dirty": self.proc_info.get("git_dirty"),
                "max_steps": self.args.max_steps}

    def run_one(self, ident: dict, *, attempt: int = 1, retry: bool = False) -> dict:
        v8 = self.v8
        key = key_of(ident)
        if v8:
            rec_dir = self.rec_root / f"{key}.a{attempt}"
            eff = ident.get("effective_max_steps")
        else:
            suffix = f".a{attempt}" if attempt > 1 else ""
            rec_dir = self.rec_root / f"{key}{suffix}"
            eff = self.args.max_steps
        record = self.base_record(ident, attempt=attempt)
        record["rec_dir"] = str(rec_dir)
        attempt_id = uuid.uuid4().hex
        if v8:
            record.update(attempt_id=attempt_id, exec_steps=0, client_steps=None, chunks=None, hard_bound=None,
                          cap_hit=False, demo_frames=None, reset_calls=0, late=False)
        self._current = {"key": key, "t0": time.time()}
        self.progress(0, phase="start")
        if v8:
            bad = validate_v8_identity(ident, self.tier_max)
            builder = self.builder_for(ident["task"], int(eff)) if bad is None else None
        else:
            bad, builder = None, self.builder_for(ident["task"])
        resolved = builder.resolve_identity(int(ident["builder_episode"])) if builder is not None else None
        if bad is None:
            bad = check_identity(resolved, ident, v8=v8, tier_max=self.tier_max)
        if bad:
            record.update(status="error", task_success=False, steps=0, error=f"IDENTITY_MISMATCH {bad}",
                          run_blocked=True, infra=False, resolved_identity=resolved)
            append_result(self.results_path, record)
            print(f"RUN_BLOCKED reason=identity key={key} detail={bad}", flush=True)
            raise SystemExit(EXIT_BLOCKED)
        claim_reset = None
        if v8:
            if self.ledger.reset_left() <= 0:  # 开局前就没有额度：不开尝试、不写结果，直接停
                self._budget_stop(key)
            self.ledger.attempt_start(key=key, attempt_id=attempt_id, attempt_no=attempt, retry=retry,
                                      task=ident["task"], tier=ident["tier"],
                                      builder_episode=int(ident["builder_episode"]))

            def claim_reset(what, _k=key, _a=attempt_id, _n=attempt):
                self.ledger.claim_reset(key=_k, attempt_id=_a, attempt_no=_n, what=what)
        meta = dict(record, resolved_identity=resolved, env=self.proc_info.get("env"),
                    never_degrade=bool(self.args.never_degrade), baseline=bool(self.args.baseline))
        try:
            recorder = self.recorder_factory(rec_dir, meta) if self.recorder_factory else NullRecorder()
        except Exception as e:  # noqa: BLE001 录制器建不起来（如磁盘满）= 基础设施故障
            record.update(status="error", task_success=False, steps=0, infra=True, infra_reason="recorder",
                          error=f"RecorderError: init: {type(e).__name__}: {e}"[:800])
            self._finish(record)
            if v8:
                self._print_done_v8(record)
            else:
                print(f"EPISODE_DONE policy={self.args.policy} key={key} status=error infra=True reason=recorder_init",
                      flush=True)
            return record
        session = EnvSession(ident["task"], int(ident["builder_episode"]), max_steps=int(eff),
                             recorder=recorder, builder=builder, progress_cb=lambda s: self.progress(s),
                             step_cap=int(eff) if v8 else None, claim_reset=claim_reset)
        conn_info = {"host": self.args.host, "port": self.args.port, "max_steps": int(eff),
                     "policy": self.args.policy, "seat": self.args.seat}
        policy_kw = self.policy_kwargs(int(eff))
        limit = self.args.episode_wall_s + (self.args.first_extra_s if self.episodes_done == 0 else 0)
        # first_extra_s 只给「server 刚（重）起后的第一局」：由 run_seat.sh 在 server 新起时传 600，客户端单独重起时传 0
        state = {"finished": False, "session": session}
        timer = None
        if limit > 0:
            timer = threading.Timer(limit, self._on_wall_timeout, args=(record, limit, state))
            timer.daemon = True
            timer.start()
        t0 = time.perf_counter()
        first_build = not self._built_once
        try:
            try:
                session.build()
                self._built_once = True
            except Exception as e:  # noqa: BLE001 构建失败（如 Vulkan）按基础设施故障记；额度耗尽不算基础设施
                res = {"status": "error", "task_success": False, "steps": 0, "error": f"{type(e).__name__}: {e}"[:800],
                       "infra": not isinstance(e, ResetBudgetExhausted),
                       "infra_reason": None if isinstance(e, ResetBudgetExhausted) else "env_build"}
            else:
                res = self.policy_mod.run_episode(session, ident, conn_info, recorder, **policy_kw)
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
            rsum = recorder.close({"status": res.get("status"), "steps": res.get("steps"),
                                   **({"exec_steps": session.steps, "cap_hit": session.cap_hit} if v8 else {})})
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
        if v8:
            # 执行段步数以环境侧计数为准；客户端自报另记。额度耗尽与步数到顶的分类覆盖客户端的记法。
            record.update(exec_steps=session.steps, client_steps=res.get("steps"), cap_hit=session.cap_hit,
                          chunks=res.get("decisions") if "hard_bound" in res else None,
                          hard_bound=res.get("hard_bound"), demo_frames=session.timing.get("demo_frames"),
                          reset_calls=session.reset_calls, effective_max_steps=int(eff))
            if session.budget_exhausted:
                record.update(status="error", infra=False, infra_reason=None, budget_exhausted=True,
                              client_error=res.get("error"),
                              error=f"RESET_BUDGET_EXHAUSTED claims={self.ledger.reset_claims} "
                                    f"budget={self.ledger.reset_budget}")
            elif session.cap_hit:
                record.update(status="timeout", infra=False, infra_reason=None, client_status=res.get("status"),
                              client_error=res.get("error"),
                              error=f"STEP_CAP exec_steps={session.steps} cap={int(eff)} 未成功，按 timeout 计")
        record["task_success"] = record.get("status") == "success"
        record["timing"] = timing
        record["recorder_verify"] = (rsum or {}).get("RECORDER_VERIFY")
        self._finish(record)
        self.episodes_done += 1
        self.progress(record.get("steps", 0), phase="done")
        if v8:
            self._print_done_v8(record)
            if record.get("budget_exhausted"):
                self._budget_stop(key)
        else:
            print(f"EPISODE_DONE policy={self.args.policy} key={key} status={record['status']} "
                  f"steps={record.get('steps')} wall_s={wall:.1f} infra={record.get('infra')} "
                  f"recorder={record['recorder_verify']}", flush=True)
        return record

    def _finish(self, record: dict) -> None:
        """写结果行；V8 再写账本 attempt_end（终态且首个 → accept）。late 先算好写进结果行。"""
        if self.v8:
            record["late"] = self.ledger.is_late(record)
        append_result(self.results_path, record)
        if self.v8:
            self.ledger.attempt_end(record)

    def _print_done_v8(self, record: dict) -> None:
        print(f"EPISODE_DONE policy={self.args.policy} key={record['key']} status={record['status']} "
              f"exec_steps={record.get('exec_steps')} cap_hit={record.get('cap_hit')} infra={record.get('infra')} "
              f"attempt_no={record.get('attempt_no')}", flush=True)

    def _budget_stop(self, key: str) -> None:
        print(f"RESET_BUDGET_EXHAUSTED policy={self.args.policy} seat={self.args.seat} key={key} "
              f"claims={self.ledger.reset_claims} budget={self.ledger.reset_budget}", flush=True)
        raise SystemExit(EXIT_BUDGET)

    def _on_wall_timeout(self, record: dict, limit: float, state: dict) -> None:
        with self._lock:
            if state["finished"]:
                return
            rec = dict(record, status="error", task_success=False, steps=None, infra=True, infra_reason="episode_wall",
                       error=f"INFRA_TIMEOUT episode_wall>{limit:.0f}s")
            if self.v8:  # 取 session 实际值；拿不到写 null（不写 0）
                sess = state.get("session")
                rec.update(exec_steps=getattr(sess, "steps", None), reset_calls=getattr(sess, "reset_calls", None),
                           cap_hit=getattr(sess, "cap_hit", None),
                           demo_frames=(getattr(sess, "timing", None) or {}).get("demo_frames"))
                self._finish(rec)
            else:
                append_result(self.results_path, rec)
            print(f"INFRA_TIMEOUT key={key_of(record)} limit_s={limit:.0f}", flush=True)
            sys.stdout.flush()
            os._exit(EXIT_WALL)

    # ── 身份清单来源 ────────────────────────────────────────────────────────
    def run_identities(self, rows: list[dict]) -> int:
        if self.v8:
            return self.run_identities_v8(rows)
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

    def recover_dangling(self) -> int:
        """账本里有 attempt_start 无 attempt_end 的尝试（进程被杀、写账本前崩溃）：结果行里找得到同 attempt_id 的
        就按结果行补 attempt_end（终态且首个 → accept），找不到就记为基础设施错误（未作废，占一次尝试）。"""
        by_id = {r.get("attempt_id"): r for r in read_results(self.results_path) if r.get("attempt_id")}
        n = 0
        for st in self.ledger.dangling():
            row = by_id.get(st["attempt_id"])
            if row is None:
                row = {"key": st["key"], "attempt_id": st["attempt_id"], "attempt_no": st["attempt_no"],
                       "status": "error", "infra": True, "exec_steps": None}
            self.ledger.attempt_end(dict(row, recovered=True))
            print(f"LEDGER_RECOVER key={st['key']} attempt_id={st['attempt_id']} status={row.get('status')}", flush=True)
            n += 1
        return n

    def run_identities_v8(self, rows: list[dict]) -> int:
        """V8：已有 accept 的身份跳过；已用满 2 次尝试的跳过；最后一次未作废尝试已是最终结局（含非 infra 错误，
        即使账本缺 accept）的跳过、不占 infra 额度；只有最后一次为 infra 错误的才按 infra 重试额度重跑。"""
        led = self.ledger
        self.recover_dangling()
        pending: list[dict] = []
        skip_acc = skip_full = skip_budget = 0
        for ident in rows:
            k = key_of(ident)
            if k in led.accepted or led.last_end_final(k):
                skip_acc += 1
            elif led.attempts_used(k) >= V8_MAX_ATTEMPTS:
                skip_full += 1
            else:
                pending.append(ident)
        print(f"RUN_PLAN policy={self.args.policy} total={len(rows)} resume_skip={skip_acc + skip_full} "
              f"accepted={skip_acc} attempts_full={skip_full} todo={len(pending)} reset_left={led.reset_left()} "
              f"infra_retry_left={led.infra_retries_left()}", flush=True)
        while pending:
            ident = pending.pop(0)
            k = key_of(ident)
            used = led.attempts_used(k)
            if k in led.accepted or led.last_end_final(k) or used >= V8_MAX_ATTEMPTS:
                continue
            retry = used >= 1
            if retry and led.infra_retries_left() <= 0:
                skip_budget += 1
                print(f"INFRA_RETRY_BUDGET_EXHAUSTED policy={self.args.policy} key={k} "
                      f"used={led.infra_retries_used()} budget={led.infra_retry_budget}", flush=True)
                continue
            rec = self.run_one(ident, attempt=led.attempts_total(k) + 1, retry=retry)
            if rec.get("status") == "error" and rec.get("infra") and led.attempts_used(k) < V8_MAX_ATTEMPTS:
                pending.insert(0, ident)  # 原身份立即重试一次（额度在下一轮判断）
        if skip_budget:
            print(f"RUN_PARTIAL policy={self.args.policy} infra_retry_skipped={skip_budget}", flush=True)
        return 0


def load_identities(args) -> list[dict]:
    """读身份清单 JSON 数组，按 ``--only`` 过滤、``--order`` 排序、``--limit`` 截断。

    V8：每行须为 ``eval_manifest.py`` 的执行身份行（字段齐全、nullable 严格、key 自洽、key 不重复），不符即运行阻塞。"""
    v8 = bool(getattr(args, "v8", False))
    rows = json.loads(Path(args.identities).read_text(encoding="utf-8"))
    if v8:
        bad = [(i, b) for i, r in enumerate(rows) for b in [validate_v8_identity(r)] if b]
        keys = [key_of(r) for r in rows]
        dup = len(keys) - len(set(keys))
        if bad or dup:
            print(f"RUN_BLOCKED reason=identities n_bad={len(bad)} dup_keys={dup} first={bad[:3]}", flush=True)
            raise SystemExit(EXIT_BLOCKED)
    if args.only:
        want = set(args.only.split(","))
        rows = [r for r in rows if key_of(r) in want]
    rows = order_identities(rows, args.order, args.shuffle_seed, v8=v8)
    if args.limit:
        rows = rows[: args.limit]
    return rows


def check_v8_args(args) -> str | None:
    if not getattr(args, "v8", False):
        return None
    miss = [n for n, v in (("--ledger", args.ledger), ("--reset-budget", args.reset_budget),
                           ("--infra-retry-budget", args.infra_retry_budget), ("--identities", args.identities))
            if v is None]
    if miss:
        return f"V8 模式必须给 {' '.join(miss)}"
    return None


def cmd_run(args) -> int:
    bad = check_v8_args(args)
    if bad:
        print(f"RUN_BLOCKED reason=args detail={bad}", flush=True)
        return EXIT_BLOCKED
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
    rc = runner.run_identities(load_identities(args))
    runner.progress(0, phase="finished")
    print(f"全部完成 policy={args.policy} seat={args.seat} episodes={runner.episodes_done}", flush=True)
    return rc


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="v7.5eval 新接口环境侧常驻客户端")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--policy", required=True, choices=["mme", "smvla"])
    p.add_argument("--identities", required=True,
                   help="身份清单 json（list of {task, source_episode, seed, builder_episode}；V8 为 shard-NN.json）")
    p.add_argument("--cond", required=True, help="条件代号，如 E1／N")
    p.add_argument("--seat", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--order", default="forward", choices=["forward", "reverse", "shuffle"])
    p.add_argument("--shuffle-seed", type=int, default=DEFAULT_SHUFFLE_SEED)
    p.add_argument("--only", default=None, help="只跑这些 <task>_<seed>（逗号分隔）")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--max-steps", type=int, default=MAX_STEPS)
    p.add_argument("--episode-wall-s", type=float, default=0.0, help="单局墙钟上限（0=不限）；超时记基础设施超时并退出 75")
    p.add_argument("--first-extra-s", type=float, default=600.0,
                   help="本进程第一局额外放宽（首次推理编译）；run_seat.sh 只在 server 新（重）起后传 600，否则传 0")
    p.add_argument("--infra-retries", type=int, default=2, help="identities 模式下基础设施失败的重试局数上限")
    p.add_argument("--no-record", action="store_true")
    p.add_argument("--never-degrade", action="store_true")
    p.add_argument("--baseline", action="store_true")
    p.add_argument("--rec-root", default=None, help="录像目录根（默认 <out>/rec）；V8 录像目录名 <key>.a<attempt_no>")
    v8 = p.add_argument_group("V8 模式（契约 C2；不带 --v8 时以下参数不生效、一切同旧版）")
    v8.add_argument("--v8", action="store_true", help="V8 模式：--identities 为 eval_manifest.py 的 shard-NN.json")
    v8.add_argument("--ledger", default=None, help="持久尝试账本 JSONL（追加写、fsync），V8 必填")
    v8.add_argument("--reset-budget", type=int, default=None, help="本账本可领的底层 reset 额度（build 与 reset 各算一次）")
    v8.add_argument("--infra-retry-budget", type=int, default=None,
                    help="本账本可用的基础设施重试局数（每身份至多重试 1 次）")
    v8.add_argument("--budget-raise-reason", default=None,
                    help="--reset-budget 大于账本历史最大值时写进 budget_raise 行与 RESET_BUDGET_RAISE 的原因（默认 cli_reset_budget）")
    p.set_defaults(func=cmd_run)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
