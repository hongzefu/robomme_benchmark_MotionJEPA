#!/usr/bin/env python3
"""第一阶段入口：定规则 → 抽签 → 封存，只落一份 jsonl（0927 计划第一部分 §5.1；v8 方案第二部分 §2.2 第 5、6 条）。

    # v7（默认 profile，只抽 xhard4 母布局，封 hard-specs/3）
    uv run --no-sync python scripts/injection-dev/freeze_specs.py \\
      --tier xhard4 --tasks all --candidates-per-env 30 --select 0..19 \\
      --max-reset-attempts 60 --workers 4 --gpus 0,1 --out <新路径>/xhard4/specs.jsonl
    # v8（按档 seed 偏移，每档一次冻结、档内逐任务独立抽，只抽该档的交付格，封 hard-specs/4）
    uv run --no-sync python scripts/injection-dev/freeze_specs.py \\
      --tier xhard1 --seed-profile v8 --cells full --workers 4 --gpus 0 \\
      --out artifacts/newtask-v8/specs-frozen/xhard1/specs.jsonl
    # v8 冒烟（7 格各 1 局，候选数默认等于局数）
    uv run --no-sync python scripts/injection-dev/freeze_specs.py \\
      --tier xhard1 --seed-profile v8 --cells smoke --out artifacts/newtask-v8/smoke/specs/xhard1/specs.jsonl

- ①定规则：``_extract.build_sampling``（``--pkg`` 默认 robomme_hard）；②抽签：``_draw.draw_task``（只 reset）；
  ③封存：``_freeze.freeze(schema=...)`` → ``--out``（排他发布，唯一落盘文件）。
- v8 的格表 ``--cells``：``full``（表 2 的 43 格）、``smoke``（2b 冒烟 7 格各 1 局）、``shard1``～``shard4``
  （按任务切的四片）或格表 JSON 路径（``{"Task@tier": 局数, ...}``）；本档的任务集合与逐格配额都取自格表。
- v8 逐任务参数：``--candidates-per-env TASK=N,...``（也接受全局整数）；``--select TASK=a..b,...``（也接受全局
  写法；默认每任务 ``0..配额-1``）；``--task-max-reset-attempts TASK[@TIER]=N,...``（优先于 ``--max-reset-attempts``；
  都不给时每格默认 ⌈候选数 ÷ 接受率 × 1.5⌉，接受率见 ``_freeze.V8_DRAW_ACCEPT``）。
- ``--dry-run``：只打印逐格候选数与 reset 上限（``FREEZE_CELL`` 每格一行 + ``FREEZE_PLAN`` 合计），不起环境、不写盘。
- ``--self-check``：跑完后以 ``find -newer`` 快照差集核对本次只写出一个文件 → ``FREEZE_ONLY_JSONL``。
- 中断即整批重抽，重抽次数计入预算（P3）。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path
from typing import Any

import _common  # noqa: F401  路径设置
import _draw  # noqa: E402
import _extract  # noqa: E402
import _freeze  # noqa: E402
import _rollout  # noqa: E402

from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402
from robomme_hard.env_record_wrapper.hard_specs import SpecsError  # noqa: E402

RECOVERY_RULE = {"rule": "V4 全部不开 fail recover（用户 2026-09-22）"}
#: --tier 合法值：v7 四档 ∪ v8 五档（v8 不经全局 TIERS 拒绝 xhard5）
TIER_CHOICES = tuple(dict.fromkeys((*hard_specs.TIERS, *hard_specs.V8_TIERS)))


def _snapshot(root: Path, since: float) -> set[str]:
    out = set()
    for dirpath, _dirs, files in os.walk(root):
        if "/.git" in dirpath or "__pycache__" in dirpath:
            continue
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                if os.stat(path).st_mtime >= since:
                    out.add(path)
            except FileNotFoundError:
                continue
    return out


def draw_rows_by_task(tasks: list[str], samplings: dict[str, dict[str, Any]], candidates: dict[str, int],
                      attempts: dict[str, int], workers: int = 1, gpus: list[str] | None = None, *,
                      difficulty: str, seed_rule: dict[str, Any], pkg: str = _draw.DEFAULT_PKG,
                      draw_one=None, executor_factory=None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """v8 逐任务候选数的抽签：语义同 ``_draw.draw_rows``（逐任务 ``_draw.draw_task`` 循环、多 worker 时每任务一个
    spawn 子进程、按任务序 ``merge_task_rows`` 合并），只是候选数与 reset 上限按任务取。``draw_one``／
    ``executor_factory`` 只供单测注入。"""
    if workers <= 1:
        if draw_one is None:
            if gpus:
                os.environ["CUDA_VISIBLE_DEVICES"] = gpus[0]
            _draw.assert_registry_owner(pkg)
        rows: list[dict[str, Any]] = []
        for task in tasks:
            rows.extend(_draw.draw_task(task, samplings[task], candidates[task], attempts[task], draw_one,
                                        difficulty, seed_rule))
        return rows, _draw.draw_stats(rows)
    workers = min(workers, len(tasks))
    if executor_factory is None:
        from concurrent.futures import ProcessPoolExecutor  # noqa: PLC0415

        ctx = mp.get_context("spawn")
        gpu_queue = None
        if gpus:
            gpu_queue = ctx.Queue()
            for index in range(workers):
                gpu_queue.put(gpus[index % len(gpus)])
        executor = ProcessPoolExecutor(max_workers=workers, mp_context=ctx, initializer=_draw._draw_worker_init,
                                       initargs=(gpu_queue, str(_common.REPO_ROOT / "src"), pkg))
        target = importlib.import_module("_draw").draw_task
    else:
        executor = executor_factory(workers)
        target = _draw.draw_task
    rows_by_task: dict[str, list[dict[str, Any]]] = {}
    failures: list[str] = []
    from concurrent.futures import as_completed  # noqa: PLC0415

    with executor:
        futures = {executor.submit(target, task, samplings[task], candidates[task], attempts[task], draw_one,
                                   difficulty, seed_rule): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                rows_by_task[task] = future.result()
            except BaseException as exc:  # noqa: BLE001 子进程崩溃不吞，汇总后整体失败
                failures.append(f"{task}: {type(exc).__name__}: {exc}")
    if failures:
        raise SpecsError(f"多 worker 抽签有环境未完成：{failures}")
    rows = _draw.merge_task_rows(tasks, rows_by_task, seed_rule)
    return rows, _draw.draw_stats(rows)


def plan_v8(tier: str, cells: dict[tuple[str, str], int], tasks_arg: str, candidates_arg: str | None,
            select_arg: str, max_reset_arg: int | None, task_reset_arg: str | None) -> dict[str, Any]:
    """v8 一档的抽签计划：任务集合、逐任务候选数／选取区间／reset 上限（纯函数，``--dry-run`` 与实跑共用）。"""
    cell_tasks = [task for task in hard_specs.ALL_TASKS if (task, tier) in cells]
    if not cell_tasks:
        raise SpecsError(f"格表里没有 {tier} 档的格")
    if tasks_arg == "all":
        tasks = cell_tasks
    else:
        tasks = [t.strip() for t in tasks_arg.split(",") if t.strip()]
        stray = [t for t in tasks if (t, tier) not in cells]
        if stray:
            raise SpecsError(f"--tasks 含不在 {tier} 交付格里的任务（不交付的格不抽）：{stray}")
    quota = {task: int(cells[(task, tier)]) for task in tasks}
    default_cands = _freeze.v8_default_candidates({(task, tier): quota[task] for task in tasks})
    candidates = _freeze.parse_int_by_task(candidates_arg, tasks, {t: default_cands[(t, tier)] for t in tasks},
                                           "--candidates-per-env")
    select = _freeze.parse_select_by_task(select_arg, tasks, {t: tuple(range(quota[t])) for t in tasks})
    for task in tasks:
        if len(select[task]) != quota[task]:
            raise SpecsError(f"{task}/{tier} 的 --select 选 {len(select[task])} 个 ≠ 格表配额 {quota[task]}")
        if candidates[task] < quota[task] or max(select[task]) >= candidates[task]:
            raise SpecsError(f"{task}/{tier} 候选数 {candidates[task]} 不足以覆盖选取 {list(select[task])}")
    caps = {task: _freeze.v8_reset_cap(task, candidates[task]) if max_reset_arg is None else int(max_reset_arg)
            for task in tasks}
    caps.update(_draw.parse_task_max_reset_attempts(task_reset_arg, tier))
    stray = sorted(set(caps) - set(tasks))
    if stray:
        raise SpecsError(f"--task-max-reset-attempts 含本档未抽的任务：{stray}")
    return {"tasks": tasks, "quota": quota, "candidates": candidates, "select": select, "reset_caps": caps}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tier", required=True, choices=TIER_CHOICES)
    parser.add_argument("--tasks", default="all", help="v7：all＝16 任务；v8：all＝格表在本档的全部任务")
    parser.add_argument("--candidates-per-env", default=None,
                        help="全局整数或 TASK=N,...（v7 缺省 10；v8 缺省按候选表 §2.2 第 6 条）")
    parser.add_argument("--select", default="default",
                        help="v7：default（0,3,6）、逗号索引或 a..b；v8：default（每任务 0..配额-1）、全局写法或 TASK=a..b,...")
    parser.add_argument("--seed-profile", default="v7", choices=("v7", "v8"),
                        help="v7（默认）：四档同 offset 14e6，xhard4 母布局（hard-specs/3）；"
                             "v8：按档 seed 偏移、各档布局独立抽（hard-specs/4）")
    parser.add_argument("--cells", default="full", help="v8 格表：full／smoke／shard1..shard4；V9：v9shard1／v9smoke；或格表 JSON 路径")
    parser.add_argument("--whitelist", default=str(hard_specs.PACKAGED_SPECS_ROOT / "layout_whitelist.json"),
                        help="v7：布局白名单（其 sha256 写进 header.layout_rule）")
    parser.add_argument("--max-reset-attempts", type=int, default=None,
                        help="每任务 reset 总预算（v7 缺省 30；v8 缺省每格 ⌈候选数 ÷ 接受率 × 1.5⌉）")
    parser.add_argument("--task-max-reset-attempts", default=None, help="TASK[@TIER]=N,...（优先于 --max-reset-attempts）")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--gpus", default=None)
    parser.add_argument("--pkg", default=_extract.DEFAULT_PKG)
    parser.add_argument("--release", default=_extract.DEFAULT_RELEASE)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()

    out = Path(args.out)
    v8 = args.seed_profile == "v8"
    if v8:
        if args.tier not in hard_specs.V8_TIERS:
            raise SystemExit(f"v8 只认档位 {hard_specs.V8_TIERS}")
        cells = _rollout.resolve_cells(args.cells)
        plan = plan_v8(args.tier, cells, args.tasks, args.candidates_per_env, args.select, args.max_reset_attempts,
                       args.task_max_reset_attempts)
        tasks = plan["tasks"]
        for task in tasks:
            print(f"FREEZE_CELL tier={args.tier} task={task} quota={plan['quota'][task]} "
                  f"candidates={plan['candidates'][task]} spare={plan['candidates'][task] - plan['quota'][task]} "
                  f"accept={_freeze.V8_DRAW_ACCEPT.get(task, _freeze.V8_DRAW_ACCEPT_DEFAULT)} "
                  f"reset_cap={plan['reset_caps'][task]} select={_rollout.compact_range(plan['select'][task])} "
                  f"quota_by_way={_freeze.format_quota_by_way(_freeze.default_quota_by_way(task, args.tier, plan['quota'][task]))}",
                  flush=True)
        print(f"FREEZE_PLAN profile=v8 tier={args.tier} cells={args.cells} tasks={len(tasks)} "
              f"quota={sum(plan['quota'].values())} candidates={sum(plan['candidates'].values())} "
              f"reset_budget<={sum(plan['reset_caps'].values())} workers={args.workers} pkg={args.pkg} out={out}",
              flush=True)
    else:
        if args.cells != "full":
            raise SystemExit("--cells 只用于 --seed-profile v8")
        tasks = list(hard_specs.ALL_TASKS) if args.tasks == "all" else args.tasks.split(",")
        if args.tier != "xhard4":
            raise SystemExit("v7 只在 xhard4 上抽母布局；xhard1～3 由 derive_specs.py 派生（0928 方案第二部分 §1.4）")
        if args.candidates_per_env is not None and "=" in str(args.candidates_per_env):
            raise SystemExit("v7 的 --candidates-per-env 只接受全局整数")
        candidates_v7 = 10 if args.candidates_per_env is None else int(args.candidates_per_env)
        select = _freeze.parse_select(args.select)
        max_reset = 30 if args.max_reset_attempts is None else args.max_reset_attempts
        by_task = _draw.parse_task_max_reset_attempts(args.task_max_reset_attempts, args.tier)
        budget = sum(by_task.get(t, max_reset) for t in tasks)
        print(f"FREEZE_PLAN tier={args.tier} tasks={len(tasks)} candidates_per_env={candidates_v7} "
              f"select={list(select)} reset_budget<={len(tasks)}x{max_reset}={budget} "
              f"workers={args.workers} pkg={args.pkg} out={out}", flush=True)
    seed_rule = hard_specs.seed_rule_for(args.tier, args.seed_profile)
    if out.exists():
        raise SystemExit(f"{out} 已存在，禁止覆盖")
    if args.dry_run:
        return 0
    started = time.time()
    sampling = _extract.build_sampling(tasks, pkg=args.pkg, release=args.release)
    samplings = {task: sampling["tasks"][task] for task in tasks}
    if v8:
        rows, stats = draw_rows_by_task(tasks, samplings, plan["candidates"], plan["reset_caps"], args.workers,
                                        _draw.parse_gpus(args.gpus), difficulty=args.tier, seed_rule=seed_rule,
                                        pkg=args.pkg)
    else:
        rows, stats = _draw.draw_rows(tasks, samplings, candidates_v7, max_reset, args.workers,
                                      _draw.parse_gpus(args.gpus), difficulty=args.tier, seed_rule=seed_rule,
                                      pkg=args.pkg, max_reset_attempts_by_task=by_task)
    parts = {
        "difficulty": args.tier, "tasks": tasks, "seed_rule": seed_rule, "sampling_config": samplings,
        "recovery_rule": RECOVERY_RULE, "identity_source": "formula",
        "run_id": args.run_id or out.parent.name, "draw_stats": stats,
        "provenance": {"base_fingerprint": hard_specs.base_fingerprint(),
                       "hard_fingerprint": hard_specs.hard_fingerprint(), "env_package": args.pkg,
                       "frozen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
    }
    if v8:
        header, spec_rows = _freeze.freeze(rows, parts, plan["select"], plan["candidates"],
                                           schema=hard_specs.SCHEMA_V8)
    else:
        parts["layout_rule"] = {"mode": "shared", "parent_tier": "xhard4",
                                "whitelist_sha256": hashlib.sha256(Path(args.whitelist).read_bytes()).hexdigest()}
        header, spec_rows = _freeze.freeze(rows, parts, select, candidates_v7, schema=hard_specs.SCHEMA_V7)
    _freeze.write_jsonl_exclusive(out, [header, *spec_rows])
    print(f"FREEZE_DONE rows={len(spec_rows)} selected={sum(r['selected'] for r in spec_rows)} "
          f"reset_attempted={stats['attempted']} identity={header['identity_sha256'][:12]} out={out}", flush=True)
    if args.self_check:
        written = _snapshot(_common.REPO_ROOT, started) | (_snapshot(out.parent, started) if not str(out.resolve()).startswith(str(_common.REPO_ROOT)) else set())
        written = {p for p in written if not p.endswith(".pyc")}
        ok = written == {str(out.resolve())} or written == {str(out)}
        print(f"FREEZE_ONLY_JSONL={'PASS' if ok else 'FAIL'} files_written={len(written)}"
              + ("" if ok else f" detail={sorted(written)[:10]}"))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
