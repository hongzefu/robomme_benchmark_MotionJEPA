#!/usr/bin/env python3
"""第一阶段入口：定规则 → 抽签 → 封存，只落一份 jsonl（0927 计划第一部分 §5.1）。

    uv run --no-sync python scripts/injection-dev/freeze_specs.py \
      --tier xhard3 --tasks all --candidates-per-env 10 --select default \
      --max-reset-attempts 30 --workers 4 --gpus 0,1 --out <新路径>/specs.jsonl

- ①定规则：``_extract.build_sampling``（``--pkg`` 默认 robomme_hard）；②抽签：``_draw.draw_rows``（只 reset）；
  ③封存：``_freeze.freeze`` → ``--out``（排他发布，唯一落盘文件；不再产生 sampling_config.json 与 drafts.jsonl）。
- ``--dry-run``：只打印将执行的参数与预算（任务数 × 最多尝试数），不起环境、不写盘。
- ``--self-check``：跑完后以 ``find -newer`` 快照差集核对本次只写出一个文件 → ``FREEZE_ONLY_JSONL``。
- 中断即整批重抽，重抽次数计入预算（P3）。
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from pathlib import Path

import _common  # noqa: F401  路径设置
import _draw  # noqa: E402
import _extract  # noqa: E402
import _freeze  # noqa: E402

from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402

RECOVERY_RULE = {"rule": "V4 全部不开 fail recover（用户 2026-09-22）"}


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tier", required=True, choices=hard_specs.TIERS)
    parser.add_argument("--tasks", default="all")
    parser.add_argument("--candidates-per-env", type=int, default=10)
    parser.add_argument("--select", default="default", help="default（0,3,6）、逗号分隔的候选 index 或 a..b 区间（v7：0..19）")
    parser.add_argument("--seed-profile", default="v7", choices=("v6", "v7"),
                        help="v7（默认）：四档同 offset 14e6，xhard4 母布局，header 写 layout_rule（hard-specs/3）")
    parser.add_argument("--whitelist", default=str(hard_specs.PACKAGED_SPECS_ROOT / "layout_whitelist.json"),
                        help="v7：布局白名单（其 sha256 写进 header.layout_rule）")
    parser.add_argument("--max-reset-attempts", type=int, default=30)
    parser.add_argument("--task-max-reset-attempts", default=None, help="TASK[@TIER]=N,...")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--gpus", default=None)
    parser.add_argument("--pkg", default=_extract.DEFAULT_PKG)
    parser.add_argument("--release", default=_extract.DEFAULT_RELEASE)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()

    tasks = list(hard_specs.ALL_TASKS) if args.tasks == "all" else args.tasks.split(",")
    select = _freeze.parse_select(args.select)
    if args.seed_profile == "v7" and args.tier != "xhard4":
        raise SystemExit("v7 只在 xhard4 上抽母布局；xhard1～3 由 derive_specs.py 派生（0928 方案第二部分 §1.4）")
    seed_rule = hard_specs.seed_rule_for(args.tier, args.seed_profile)
    by_task = _draw.parse_task_max_reset_attempts(args.task_max_reset_attempts, args.tier)
    budget = sum(by_task.get(t, args.max_reset_attempts) for t in tasks)
    out = Path(args.out)
    print(f"FREEZE_PLAN tier={args.tier} tasks={len(tasks)} candidates_per_env={args.candidates_per_env} "
          f"select={list(select)} reset_budget<={len(tasks)}x{args.max_reset_attempts}={budget} "
          f"workers={args.workers} pkg={args.pkg} out={out}", flush=True)
    if out.exists():
        raise SystemExit(f"{out} 已存在，禁止覆盖")
    if args.dry_run:
        return 0
    started = time.time()
    sampling = _extract.build_sampling(tasks, pkg=args.pkg, release=args.release)
    samplings = {task: sampling["tasks"][task] for task in tasks}
    rows, stats = _draw.draw_rows(tasks, samplings, args.candidates_per_env, args.max_reset_attempts, args.workers,
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
    if args.seed_profile == "v7":
        import hashlib  # noqa: PLC0415

        parts["layout_rule"] = {"mode": "shared", "parent_tier": "xhard4",
                                "whitelist_sha256": hashlib.sha256(Path(args.whitelist).read_bytes()).hexdigest()}
    header, spec_rows = _freeze.freeze(rows, parts, select, args.candidates_per_env)
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
