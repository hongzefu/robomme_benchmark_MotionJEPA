"""第一阶段 ②抽签：每任务每档攒候选（只 reset、不 step、不录像），导出 ``SpecRecorder`` 规格。

逻辑由 ``scripts/parity/v4_specs.py`` 的 ``_draw_one`` / ``draw_task`` / ``merge_task_rows`` / ``draw_rows`` 搬来，语义不变：
seed = ``offset(tier) + env_code×1e5 + episode×100 + attempt``；``max_reset_attempts`` 是每任务共享的总预算，
reset 失败计入 ``draw_stats``；多 worker 时每任务一个 spawn 子进程，按任务序合并，行序与单 worker 相同。
与原实现的差别只有两处：包名参数化（``pkg``，默认 ``robomme_hard``，子进程初始化后断言注册归属）；
输入是内存里的 sampling dict、输出是内存里的行与 ``draw_stats``，不读写文件。
"""

from __future__ import annotations

import functools
import importlib
import multiprocessing as mp
import os
import sys
import time
import traceback
from typing import Any

import _common  # noqa: F401  路径设置

from robomme_hard.env_record_wrapper.hard_specs import (  # noqa: E402
    RUNTIME,
    SpecsError,
    seed_for,
    spec_sha256,
)

DEFAULT_PKG = "robomme_hard"


def recovery_mode(episode: int) -> str | None:
    """新值档一律不开 fail recover（RECOVERY_RULE，用户 2026-09-22）；保留函数形态供统一调用。"""
    return None


def env_kwargs(seed: int, episode: int, difficulty: str) -> dict[str, Any]:
    """抽签与实跑共用的 gym.make 参数（不含 sampling_config / native_episode_spec）。"""
    kwargs = {**RUNTIME, "seed": seed, "difficulty": difficulty}
    mode = recovery_mode(episode)
    if mode is not None:
        kwargs["robomme_failure_recovery"] = True
        kwargs["robomme_failure_recovery_mode"] = mode
    return kwargs


def _draw_one(task: str, seed: int, episode: int, sampling: dict[str, Any],
              difficulty: str) -> tuple[bool, dict | None, str | None, str | None]:
    import gymnasium as gym

    env = None
    try:
        env = gym.make(task, sampling_config=sampling, **env_kwargs(seed, episode, difficulty))
        env.reset()
        recorder = env.unwrapped._spec
        recorder.identity.update({"task": task, "seed": seed, "difficulty": difficulty,
                                  "episode": episode, "recovery_mode": recovery_mode(episode)})
        return True, recorder.to_dict(), None, None
    except Exception as exc:  # noqa: BLE001 失败本身要归类记录
        return False, None, type(exc).__name__, f"{exc}\n{traceback.format_exc(limit=4)}"[:2000]
    finally:
        if env is not None:
            env.close()


def draw_task(task: str, sampling: dict[str, Any], candidates_per_env: int, max_reset_attempts: int,
              draw_one=None, difficulty: str = "xhard1", seed_rule: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """单环境抽签循环：攒够 ``candidates_per_env`` 条 reset 成功或尝试满 ``max_reset_attempts`` 次为止。"""
    if draw_one is None:
        draw_one = functools.partial(_draw_one, difficulty=difficulty)
    rows: list[dict[str, Any]] = []
    episode = attempt = total = 0
    while episode < candidates_per_env and total < max_reset_attempts:
        seed = seed_for(task, episode, attempt, seed_rule)
        started = time.time()
        ok, spec, fail_class, error = draw_one(task, seed, episode, sampling)
        rows.append({
            "record": "draft", "task": task, "difficulty": difficulty, "episode": episode,
            "attempt": attempt, "seed": seed, "reset_ok": ok, "fail_class": fail_class,
            "error": error, "spec": spec, "spec_sha256": spec_sha256(spec) if spec else None,
            "wall_s": round(time.time() - started, 2),
        })
        total += 1
        print(f"DRAW {task} ep={episode} attempt={attempt} seed={seed} ok={ok} {fail_class or ''}", flush=True)
        if ok:
            episode, attempt = episode + 1, 0
        else:
            attempt += 1
    print(f"DRAW_TASK {task} ok={episode} attempted={total} shortfall={candidates_per_env - episode}", flush=True)
    return rows


def merge_task_rows(tasks: list[str], rows_by_task: dict[str, list[dict[str, Any]]],
                    seed_rule: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """按任务序拼接；每个环境的 (episode, attempt) 必须与抽签循环推进规则一致，否则拒绝合并。"""
    missing = [task for task in tasks if task not in rows_by_task]
    extra = sorted(set(rows_by_task) - set(tasks))
    if missing or extra:
        raise SpecsError(f"多 worker 合并：缺少环境 {missing}，多出环境 {extra}")
    merged: list[dict[str, Any]] = []
    for task in tasks:
        episode = attempt = 0
        for row in rows_by_task[task]:
            if row["task"] != task or (row["episode"], row["attempt"]) != (episode, attempt) \
                    or row["seed"] != seed_for(task, episode, attempt, seed_rule):
                raise SpecsError(f"多 worker 合并：{task} 的行序与抽签规则不符（期望 ep={episode} attempt={attempt}）")
            if row["reset_ok"]:
                episode, attempt = episode + 1, 0
            else:
                attempt += 1
            merged.append(row)
    return merged


def _draw_worker_init(gpu_queue, src_root: str, pkg: str) -> None:
    """spawn 子进程初始化：领一张 GPU，注册环境，并断言 16 个 id 归 ``pkg``。"""
    if gpu_queue is not None:
        try:
            gpu = gpu_queue.get(timeout=30)
        except Exception:  # noqa: BLE001 领不到就沿用父进程环境
            gpu = None
        if gpu is not None:
            os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    assert_registry_owner(pkg)


def assert_registry_owner(pkg: str) -> None:
    module = importlib.import_module(f"{pkg}.robomme_env")
    from mani_skill.utils.registration import REGISTERED_ENVS

    ids = getattr(module, "ENV_IDS", None) or [t for t in REGISTERED_ENVS if REGISTERED_ENVS[t].cls.__module__.startswith(pkg)]
    stray = {uid: REGISTERED_ENVS[uid].cls.__module__ for uid in ids
             if not REGISTERED_ENVS[uid].cls.__module__.startswith(f"{pkg}.")}
    if stray:
        raise SpecsError(f"抽签进程注册归属不符（期望 {pkg}）：{stray}")


def parse_gpus(text: str | None) -> list[str] | None:
    if text is None or not str(text).strip():
        return None
    return [item.strip() for item in str(text).split(",") if item.strip()]


def parse_task_max_reset_attempts(text: str | None, difficulty: str) -> dict[str, int]:
    """``TASK[@TIER]=N,...``；带 ``@TIER`` 的条目只对该档生效。"""
    result: dict[str, int] = {}
    if not text:
        return result
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        key, _, value = item.partition("=")
        task, _, tier = key.partition("@")
        if not task or not value.isdigit():
            raise SpecsError(f"--task-max-reset-attempts 条目格式应为 TASK[@TIER]=N：{item!r}")
        if tier and tier != difficulty:
            continue
        result[task] = int(value)
    return result


def draw_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_task: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = per_task.setdefault(row["task"], {"attempted": 0, "ok": 0, "fail_class": {}})
        entry["attempted"] += 1
        if row["reset_ok"]:
            entry["ok"] += 1
        else:
            key = row.get("fail_class") or "unknown"
            entry["fail_class"][key] = entry["fail_class"].get(key, 0) + 1
    return {"per_task": per_task, "attempted": sum(v["attempted"] for v in per_task.values()),
            "ok": sum(v["ok"] for v in per_task.values())}


def draw_rows(tasks: list[str], samplings: dict[str, dict[str, Any]], candidates_per_env: int,
              max_reset_attempts: int, workers: int = 1, gpus: list[str] | None = None, *,
              difficulty: str, seed_rule: dict[str, Any], pkg: str = DEFAULT_PKG,
              max_reset_attempts_by_task: dict[str, int] | None = None,
              draw_one=None, executor_factory=None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """全部环境的抽签行与 ``draw_stats``。``draw_one``/``executor_factory`` 只供单测注入。"""
    by_task = dict(max_reset_attempts_by_task or {})
    attempts_for = lambda task: int(by_task.get(task, max_reset_attempts))  # noqa: E731
    if workers <= 1:
        if draw_one is None:
            if gpus:
                os.environ["CUDA_VISIBLE_DEVICES"] = gpus[0]
            assert_registry_owner(pkg)
        rows: list[dict[str, Any]] = []
        for task in tasks:
            rows.extend(draw_task(task, samplings[task], candidates_per_env, attempts_for(task), draw_one,
                                  difficulty, seed_rule))
        return rows, draw_stats(rows)
    workers = min(workers, len(tasks))
    if executor_factory is None:
        from concurrent.futures import ProcessPoolExecutor

        ctx = mp.get_context("spawn")
        gpu_queue = None
        if gpus:
            gpu_queue = ctx.Queue()
            for index in range(workers):
                gpu_queue.put(gpus[index % len(gpus)])
        executor = ProcessPoolExecutor(max_workers=workers, mp_context=ctx, initializer=_draw_worker_init,
                                       initargs=(gpu_queue, str(_common.REPO_ROOT / "src"), pkg))
        target = importlib.import_module("_draw").draw_task
    else:
        executor = executor_factory(workers)
        target = draw_task
    rows_by_task: dict[str, list[dict[str, Any]]] = {}
    failures: list[str] = []
    from concurrent.futures import as_completed

    with executor:
        futures = {executor.submit(target, task, samplings[task], candidates_per_env, attempts_for(task), draw_one,
                                   difficulty, seed_rule): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                rows_by_task[task] = future.result()
            except BaseException as exc:  # noqa: BLE001 子进程崩溃不吞，汇总后整体失败
                failures.append(f"{task}: {type(exc).__name__}: {exc}")
    if failures:
        raise SpecsError(f"多 worker 抽签有环境未完成：{failures}")
    rows = merge_task_rows(tasks, rows_by_task, seed_rule)
    return rows, draw_stats(rows)
