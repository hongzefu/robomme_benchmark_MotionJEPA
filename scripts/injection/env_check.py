#!/usr/bin/env python3
"""候选规格的「可产生环境」核验：只做 ``gym.make`` → ``reset`` → 读证据 → ``close``。

用途：每组（任务／难度）在实跑区间之后再备 50 条**只出候选、不出 h5** 的规格，
需要证明这些候选「能产生环境」。核验刻意只覆盖环境构造与一次 reset：

* **不套** ``RobommeRecordWrapper``（不建 h5、不录视频）；
* **不建** planner、**不 step**；
* 零文件产物（除了本模块自己写的 JSONL 结果行）。

因此 reset 通过 **≠** 能出 h5，语义边界见 :data:`SEMANTIC_NOTE`。

⚠ 与 ``scripts/generate_dataset_newseed.py`` 同一条约束：本模块顶层**只能** import 标准库。
池用的是该模块的 ``_pool_init``，spawn 子进程 bootstrap 会重跑被引用模块的顶层，
而那早于 ``_pool_init()`` 写 ``CUDA_VISIBLE_DEVICES``；gymnasium／torch／sapien
一律在 worker 函数体内 import。
"""

from __future__ import annotations

import copy
import json
import os
import resource
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

# 本文件位于 scripts/injection/，向上两级是仓库根（与 run.py 同深度，勿改成 parents[1]）
REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (str(REPO_ROOT),):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from scripts.injection.run import (  # noqa: E402
    OUTCOME_NOT_RUN,
    OUTCOME_PASS,
    OUTCOME_TIMEOUT,
    classify_outcome,
)

#: reset 被父进程按墙钟杀掉时合成的 error_type（对应 ``classify_outcome`` 的「超时」）。
RESET_TIMEOUT_ERROR_TYPE = "EnvResetWallClockTimeout"

#: 属于「该候选不通」的任务性失败；其余异常一律记 ``code``（真 bug／环境问题）。
#: 与 ``generate_dataset_newseed._worker`` 的 retryable 口径同源，只去掉 step 期才可能出现的几类。
TASK_FAILURE_TYPES = (
    "SceneGenerationError",
    "BinCollisionError",
    "SpecBindingError",
    "EpisodeSpecError",
    "DatasetGenerationError",
)

#: 语义边界说明：写进 payload 的 ``note``，避免核验结果被当成「能出 h5」的证明。
SEMANTIC_NOTE = (
    "本核验只覆盖 gym.make + 一次 env.reset()（即 _load_scene 与 _initialize_episode，"
    "含两个视频任务在 _initialize_episode 里对实际 actor 初态所做的碰撞复核）；"
    "不套 RobommeRecordWrapper、不建 planner、不 step，因此不覆盖 step 期的 SpecBindingError、"
    "规划可解性（螺旋／RRT* 能否解出轨迹）、录像器的步数保护与任务成功判定。"
    "结论只到「该候选能产生环境」为止：reset 通过 ≠ 能出 h5。"
)


# ── 计划与作业 ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class EnvCheckPlan:
    """一组（任务／难度）的核验计划。

    从 ``episode=start`` 起按 episode 升序核验，攒够 ``need`` 条通过即停；
    ``limit`` 给出时最多核验 ``limit`` 条候选（smoke 用，防止冒烟跑成全量）。
    """

    task: str
    difficulty: str
    start: int
    need: int
    limit: int | None = None

    @property
    def key(self) -> str:
        return f"{self.task}/{self.difficulty}"


@dataclass(frozen=True)
class EnvCheckJob:
    """一条候选的核验作业。``record`` 是规格记录的独立深拷贝，worker 之间不共享可变状态。"""

    task: str
    difficulty: str
    episode: int
    seed: int
    spec_sha256: str
    record: dict[str, Any] = field(default_factory=dict)
    #: 采样配置 **文件路径**（不是已解析的字典）：作业要跨进程 pickle，传路径比传整份配置便宜，
    #: 由 worker 自己 load 并取该任务那一份，语义与 ``_worker`` 的 ``sampling_config`` kwarg 一致。
    sampling_config: str | None = None
    repo_root: str = str(REPO_ROOT)


# ── worker ──────────────────────────────────────────────────────────────────
def _bound_info() -> dict[str, Any]:
    """取池 initializer（``generate_dataset_newseed._pool_init``）记下的绑卡信息。

    只从 ``sys.modules`` 里读，不主动 import：submit 钩子模式下根本没有池，读不到就给空壳。
    """
    for name in ("scripts.generate_dataset_newseed", "generate_dataset_newseed", "__mp_main__"):
        module = sys.modules.get(name)
        bound = getattr(module, "_BOUND", None) if module is not None else None
        if isinstance(bound, Mapping):
            return dict(bound)
    return {"gpu": os.environ.get("CUDA_VISIBLE_DEVICES"), "pid": os.getpid()}


def check_one(job: EnvCheckJob) -> dict[str, Any]:
    """池 worker：建环境、reset 一次、取证据、close。不写任何文件。

    env kwargs 与 ``generate_dataset_newseed._worker`` 逐字一致（少了录像器与 recovery），
    否则「能产生环境」的结论对不上正式实跑的口径。
    """
    clock = time.monotonic()
    phases: dict[str, float] = {}
    env: Any | None = None
    caught: BaseException | None = None
    error_traceback: str | None = None
    injection_evidence: dict[str, Any] = {}
    runtime_checks: list[Any] = []

    def base(ok: bool) -> dict[str, Any]:
        return {
            "task": job.task,
            "difficulty": job.difficulty,
            "episode": job.episode,
            "seed": job.seed,
            "spec_sha256": job.spec_sha256,
            "ok": ok,
            "bound": _bound_info(),
            "injection_bound": bool(injection_evidence),
            "runtime_checks_total": len(runtime_checks),
            "phases": {name: round(value, 3) for name, value in phases.items()},
            "wall_s": round(time.monotonic() - clock, 3),
            "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        }

    def failed(exc: BaseException, tb: str | None) -> dict[str, Any]:
        name = type(exc).__name__
        return {
            **base(False),
            "failure_class": "task" if name in TASK_FAILURE_TYPES else "code",
            "error_type": name,
            "error": str(exc),
            "traceback": tb,
        }

    # import 单独成段：这里失败的话下面 except 子句引用的异常类还没定义，会变成 NameError
    try:
        source_root = Path(job.repo_root) / "src"
        if str(source_root) not in sys.path:
            sys.path.insert(0, str(source_root))
        import gymnasium as gym
        import robomme.robomme_env  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return failed(exc, traceback.format_exc())

    try:
        kwargs: dict[str, Any] = {
            "obs_mode": "rgb+depth+segmentation",
            "control_mode": "pd_joint_pos",
            "render_mode": "rgb_array",
            "reward_mode": "dense",
            "seed": job.seed,
            "difficulty": job.difficulty,
        }
        if job.sampling_config is not None:
            from scripts.generate_dataset_newseed import load_sampling_config

            task_configs = load_sampling_config(job.sampling_config, Path(job.repo_root))
            if job.task in task_configs:
                kwargs["sampling_config"] = task_configs[job.task]
        if job.record:
            kwargs["episode_spec"] = copy.deepcopy(dict(job.record))

        mark = time.monotonic()
        env = gym.make(job.task, **kwargs)
        phases["make_s"] = time.monotonic() - mark

        mark = time.monotonic()
        env.reset()
        phases["reset_s"] = time.monotonic() - mark
    except Exception as exc:  # noqa: BLE001
        caught = exc
        error_traceback = traceback.format_exc()
    finally:
        if env is not None:
            # ⚠ 证据必须在 close() **之前**取：close 之后环境被拆掉，
            # _initialize_episode 里累积的 _runtime_checks 与 _injection_evidence 就没了。
            try:
                runtime_checks = list(getattr(env.unwrapped, "_runtime_checks", []) or [])
            except Exception:  # noqa: BLE001 - 取证据失败不能影响主流程
                runtime_checks = []
            try:
                injection_evidence = dict(getattr(env.unwrapped, "_injection_evidence", {}) or {})
            except Exception:  # noqa: BLE001
                injection_evidence = {}
            mark = time.monotonic()
            try:
                env.close()
            except Exception as close_exc:  # noqa: BLE001
                if caught is None:
                    caught = close_exc
                    error_traceback = traceback.format_exc()
            phases["close_s"] = time.monotonic() - mark

    if caught is not None:
        return failed(caught, error_traceback)
    return {**base(True), "failure_class": None, "error_type": None, "error": None, "traceback": None}


def classify_reset_outcome(record: Mapping[str, Any]) -> str:
    """把一条核验结果翻成七类互斥结果，口径与实跑完全共用 ``run.classify_outcome``。"""
    return classify_outcome(dict(record))


def render_verdict_line(verdict: Mapping[str, Any]) -> str:
    """渲染一行判定：``NAME=PASS k=v …``（与 campaign.Verdicts 的行格式一致）。"""
    fields = verdict.get("fields") or {}
    rendered = " ".join(f"{key}={value}" for key, value in fields.items())
    status = "PASS" if verdict.get("passed") else "FAIL"
    return f"{verdict['name']}={status}" + (f" {rendered}" if rendered else "")


# ── 编排 ────────────────────────────────────────────────────────────────────
def _synth_timeout(job: EnvCheckJob, timeout_s: float, wall_s: float) -> dict[str, Any]:
    """父进程按墙钟杀掉 worker 后合成的一条结果：归「超时」，不冒充物理不可行。"""
    return {
        "task": job.task,
        "difficulty": job.difficulty,
        "episode": job.episode,
        "seed": job.seed,
        "spec_sha256": job.spec_sha256,
        "ok": False,
        "failure_class": "timeout",
        "error_type": RESET_TIMEOUT_ERROR_TYPE,
        "error": f"建环境加一次 reset 的墙钟超过 {timeout_s:g} 秒被终止",
        "traceback": None,
        "bound": {},
        "injection_bound": False,
        "runtime_checks_total": 0,
        "phases": {},
        "wall_s": round(wall_s, 3),
        "peak_rss_mb": None,
    }


def _synth_failure(job: EnvCheckJob, exc: BaseException) -> dict[str, Any]:
    """worker 意外死亡／调度层异常：记 infra，同样不冒充物理不可行。"""
    return {
        "task": job.task,
        "difficulty": job.difficulty,
        "episode": job.episode,
        "seed": job.seed,
        "spec_sha256": job.spec_sha256,
        "ok": False,
        "failure_class": "infra",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": None,
        "bound": {},
        "injection_bound": False,
        "runtime_checks_total": 0,
        "phases": {},
        "wall_s": None,
        "peak_rss_mb": None,
    }


class _GroupState:
    """一组候选的派发游标与计数。"""

    def __init__(self, plan: EnvCheckPlan, episodes: Sequence[int]) -> None:
        self.plan = plan
        # 只取 start 及之后的候选，按 episode 升序；limit 在这里就截断，派发逻辑不必再判
        pool = sorted(number for number in episodes if number >= plan.start)
        if plan.limit is not None:
            pool = pool[: max(0, int(plan.limit))]
        self.pool: list[int] = pool
        self.cursor = 0
        self.checked = 0
        self.passed = 0
        self.failed = 0
        self.delivered: list[int] = []
        self.outcome_counts: dict[str, int] = {}

    @property
    def satisfied(self) -> bool:
        return self.passed >= self.plan.need

    @property
    def exhausted(self) -> bool:
        return self.cursor >= len(self.pool)

    def next_episode(self) -> int | None:
        """还需要就吐下一条；已攒够或候选耗尽返回 None。"""
        if self.satisfied or self.exhausted:
            return None
        episode = self.pool[self.cursor]
        self.cursor += 1
        return episode


def _seed_for(task: str, episode: int) -> int:
    """与实跑同一条 seed 公式：``SeedLayout("train").seed(task, episode, 0)``。"""
    from scripts.seed_layout import get_layout

    return get_layout("train").seed(task, episode, 0)


def run_env_check(
    documents: Mapping[tuple[str, str], Mapping[str, Any]],
    plans: Sequence[EnvCheckPlan],
    *,
    gpus: Sequence[str],
    workers_per_gpu: int,
    sampling_config: Path | None,
    out_dir: Path,
    repo_root: Path,
    timeout_s: float = 120.0,
    max_tasks_per_child: int = 8,
    submit: Callable[[EnvCheckJob], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """按组核验候选规格能否产生环境，边跑边写 JSONL，返回判定 payload。

    ``documents`` 就是 ``campaign.load_group_documents`` 的第三个返回值：
    每组一份 doc，``doc["episodes"]`` 是该组的规格记录列表。

    派发：每张卡一个 pebble 池（``initializer=generate_dataset_newseed._pool_init``，
    initargs 与 ``_run_jobs`` 同源），总 worker 数 = ``workers_per_gpu × 卡数``；
    按组从 ``start`` 起按 episode 升序、每批总 worker 数条地派发。各组独立计数，
    某组累计通过 ≥ ``need`` 即不再派该组新任务——**已在飞的照常收结果**，只是记 ``counted=false``，
    以免「攒够了就丢掉在途证据」。候选池耗尽仍不足 ``need`` 记该组 shortfall。

    ``submit`` 是测试钩子：``None`` 时走 pebble 池；给出时同步串行调用，不开任何进程。
    """
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    clock = time.monotonic()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    states: list[_GroupState] = []
    for plan in plans:
        doc = documents.get((plan.task, plan.difficulty)) or {}
        episodes = [int(item["episode"]) for item in (doc.get("episodes") or [])]
        states.append(_GroupState(plan, episodes))
    specs: dict[tuple[str, str], dict[int, Mapping[str, Any]]] = {}
    for key, doc in documents.items():
        specs[key] = {int(item["episode"]): item for item in (doc.get("episodes") or [])}

    config_path = str(sampling_config) if sampling_config is not None else None

    def make_job(state: _GroupState, episode: int) -> EnvCheckJob:
        plan = state.plan
        record = specs.get((plan.task, plan.difficulty), {}).get(episode, {})
        return EnvCheckJob(
            task=plan.task,
            difficulty=plan.difficulty,
            episode=episode,
            seed=_seed_for(plan.task, episode),
            spec_sha256=str(record.get("spec_sha256") or ""),
            # 每条作业一份独立深拷贝：worker 之间、同一 worker 的前后两条之间不共享可变缓存
            record=copy.deepcopy(dict(record)),
            sampling_config=config_path,
            repo_root=str(repo_root),
        )

    sinks: dict[str, Any] = {}

    def write_row(state: _GroupState, job: EnvCheckJob, result: Mapping[str, Any], counted: bool, delivered: bool) -> None:
        path = out_dir / job.task / f"{job.difficulty}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        sink = sinks.get(str(path))
        if sink is None:
            sink = path.open("a", buffering=1, encoding="utf-8")
            sinks[str(path)] = sink
        row = {
            "task": job.task,
            "difficulty": job.difficulty,
            "episode": job.episode,
            "seed": job.seed,
            "spec_sha256": job.spec_sha256,
            "outcome": classify_reset_outcome(result),
            "error_type": result.get("error_type"),
            "error": (result.get("error") or "")[:400],
            "wall_s": result.get("wall_s"),
            "phases": result.get("phases") or {},
            "bound": {
                "gpu": (result.get("bound") or {}).get("gpu"),
                "pid": (result.get("bound") or {}).get("pid"),
            },
            "injection_bound": bool(result.get("injection_bound")),
            "counted": bool(counted),
            "delivered": bool(delivered),
        }
        sink.write(json.dumps(row, ensure_ascii=False) + "\n")

    def absorb(state: _GroupState, job: EnvCheckJob, result: Mapping[str, Any]) -> None:
        """收一条结果：先判是否仍在计数窗口内，再登记、落盘。"""
        counted = not state.satisfied
        outcome = classify_reset_outcome(result)
        state.outcome_counts[outcome] = state.outcome_counts.get(outcome, 0) + 1
        delivered = False
        if counted:
            state.checked += 1
            if outcome == OUTCOME_PASS:
                state.passed += 1
                # 交付集 = 按 episode 序最前的 need 条通过者；派发本身就是升序，直接追加即可
                if len(state.delivered) < state.plan.need:
                    state.delivered.append(job.episode)
                    delivered = True
            else:
                state.failed += 1
        write_row(state, job, result, counted=counted, delivered=delivered)

    total_workers = max(1, int(workers_per_gpu) * max(1, len(gpus)))

    def next_batch() -> list[tuple[_GroupState, EnvCheckJob]]:
        """按组轮转取一批，最多总 worker 数条；同组内严格 episode 升序。"""
        batch: list[tuple[_GroupState, EnvCheckJob]] = []
        while len(batch) < total_workers:
            grew = False
            for state in states:
                if len(batch) >= total_workers:
                    break
                episode = state.next_episode()
                if episode is None:
                    continue
                batch.append((state, make_job(state, episode)))
                grew = True
            if not grew:
                break
        return batch

    try:
        if submit is not None:
            # 测试钩子：同步串行，不开进程，也不碰 pebble／CUDA
            while True:
                batch = next_batch()
                if not batch:
                    break
                for state, job in batch:
                    try:
                        result = submit(job)
                    except BaseException as exc:  # noqa: BLE001
                        result = _synth_failure(job, exc)
                    absorb(state, job, result)
        else:
            _run_with_pools(
                states,
                next_batch,
                absorb,
                gpus=list(gpus),
                workers_per_gpu=int(workers_per_gpu),
                repo_root=Path(repo_root),
                timeout_s=float(timeout_s),
                max_tasks_per_child=int(max_tasks_per_child),
            )
    finally:
        for sink in sinks.values():
            try:
                sink.close()
            except Exception:  # noqa: BLE001
                pass

    groups: dict[str, Any] = {}
    verdicts: list[dict[str, Any]] = []
    total_checked = total_passed = total_delivered = total_shortfall = 0
    for state in states:
        shortfall = max(0, state.plan.need - len(state.delivered))
        groups[state.plan.key] = {
            "start": state.plan.start,
            "need": state.plan.need,
            "checked": state.checked,
            "passed": state.passed,
            "failed": state.failed,
            "delivered": list(state.delivered),
            "outcome_counts": dict(state.outcome_counts),
            "shortfall": shortfall,
            "exhausted": state.exhausted,
        }
        total_checked += state.checked
        total_passed += state.passed
        total_delivered += len(state.delivered)
        total_shortfall += shortfall
        verdicts.append(
            {
                "name": "ENV_RESET",
                "passed": shortfall == 0,
                "fields": {
                    "group": state.plan.key,
                    "start": state.plan.start,
                    "checked": state.checked,
                    "passed": state.passed,
                    "failed": state.failed,
                    "delivered": len(state.delivered),
                },
            }
        )
    verdicts.append(
        {
            "name": "ENV_CHECK",
            "passed": total_shortfall == 0,
            "fields": {
                "groups": len(states),
                "checked": total_checked,
                "passed": total_passed,
                "delivered": total_delivered,
                "shortfall": total_shortfall,
            },
        }
    )
    return {
        "gpus": list(gpus),
        "workers_per_gpu": int(workers_per_gpu),
        "timeout_s": float(timeout_s),
        "started_utc": started_utc,
        "elapsed_s": round(time.monotonic() - clock, 3),
        "groups": groups,
        "verdicts": verdicts,
        "passed": all(item["passed"] for item in verdicts),
        "note": SEMANTIC_NOTE,
    }


def _run_with_pools(
    states: Sequence[_GroupState],
    next_batch: Callable[[], list[tuple[_GroupState, EnvCheckJob]]],
    absorb: Callable[[_GroupState, EnvCheckJob, Mapping[str, Any]], None],
    *,
    gpus: Sequence[str],
    workers_per_gpu: int,
    repo_root: Path,
    timeout_s: float,
    max_tasks_per_child: int,
) -> None:
    """真派发：每卡一个 pebble 池，复用实跑的 ``_pool_init`` 与 CPU 亲和切分。

    ⚠ 这些 import 全部延迟到这里：``generate_dataset_newseed`` 顶层会 import h5py/numpy，
    而 spawn 子进程 bootstrap 会重跑被引用模块的顶层；本模块顶层保持纯标准库，
    正是为了让 ``_pool_init`` 的绑卡仍然发生在任何 CUDA 初始化之前。
    """
    import multiprocessing as mp
    from concurrent.futures import FIRST_COMPLETED, wait

    from pebble import ProcessExpired, ProcessPool

    from scripts import generate_dataset_newseed as gen

    gpu_ids = list(gpus) or ["0"]
    context = mp.get_context("spawn")
    # CPU 亲和计划直接复用实跑的 _cpu_plan：把本进程可见的核按卡等分，
    # 口径与 --affinity exclusive 的实跑完全一致，避免两条链路对 CPU 的假设不同。
    cpu_plan = gen._cpu_plan(gpu_ids, "exclusive")
    timeout = float(timeout_s) if timeout_s and timeout_s > 0 else None

    pools = {
        gpu: ProcessPool(
            max_workers=max(1, workers_per_gpu),
            max_tasks=int(max_tasks_per_child or 0),  # pebble 里 0 才是「永不回收」
            initializer=gen._pool_init,
            initargs=(gpu, cpu_plan.get(gpu), str(Path(repo_root) / "src")),
            context=context,
        )
        for gpu in gpu_ids
    }
    try:
        while True:
            batch = next_batch()
            if not batch:
                break
            inflight: dict[Any, tuple[_GroupState, EnvCheckJob, float]] = {}
            for index, (state, job) in enumerate(batch):
                gpu = gpu_ids[index % len(gpu_ids)]
                future = pools[gpu].schedule(check_one, args=(job,), timeout=timeout)
                inflight[future] = (state, job, time.monotonic())
            # ⚠ 批内结果乱序返回，但登记必须按 episode 升序：交付集定义是「最前的 need 条通过者」，
            # 按到达顺序登记会让快返回的靠后 episode 插队。所以先收齐一批，再排序登记。
            harvested: list[tuple[tuple[str, str, int], _GroupState, EnvCheckJob, dict[str, Any]]] = []
            while inflight:
                finished, _ = wait(list(inflight), return_when=FIRST_COMPLETED)
                for future in finished:
                    state, job, submitted = inflight.pop(future)
                    elapsed = time.monotonic() - submitted
                    try:
                        result = future.result()
                    except TimeoutError as exc:
                        # 3.11 起 concurrent.futures.TimeoutError 就是内建 TimeoutError（OSError 子类），
                        # worker import 阶段的 OSError 家族也长这样：再核一次确实跑满才算超时
                        if timeout is not None and elapsed >= 0.95 * timeout:
                            result = _synth_timeout(job, timeout, elapsed)
                        else:
                            result = _synth_failure(job, exc)
                    except ProcessExpired as exc:
                        result = _synth_failure(job, exc)
                    except BaseException as exc:  # noqa: BLE001
                        result = _synth_failure(job, exc)
                    harvested.append(((job.task, job.difficulty, job.episode), state, job, result))
            for _key, state, job, result in sorted(harvested, key=lambda item: item[0]):
                absorb(state, job, result)
    except BaseException:
        for pool in pools.values():
            try:
                pool.stop()
                pool.join()
            except Exception:  # noqa: BLE001
                pass
        raise
    for pool in pools.values():
        try:
            pool.close()
            pool.join()
        except Exception:  # noqa: BLE001
            pass


__all__ = [
    "EnvCheckJob",
    "EnvCheckPlan",
    "OUTCOME_NOT_RUN",
    "OUTCOME_PASS",
    "OUTCOME_TIMEOUT",
    "RESET_TIMEOUT_ERROR_TYPE",
    "SEMANTIC_NOTE",
    "check_one",
    "classify_reset_outcome",
    "render_verdict_line",
    "run_env_check",
]
