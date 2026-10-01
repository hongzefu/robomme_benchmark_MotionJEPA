#!/usr/bin/env python3
"""v8 逐身份清单导出（v8 方案第二部分 §2.2 第 9 条；原 v7 版见 0928 方案第一部分 §5 第 3 条）。

**须在阶段 3b 换包后运行**：builder 按包内 ``TIERS``／``EXPECTED_CELLS`` 读规格，换包前它们仍是 v7 值，
即使 ``--specs-root`` 指向 v8 根也会因缺 xhard5、格表不符而失败或数不出 1262。

    uv run --no-sync python scripts/injection-dev/export_eval_identities.py \\
        --out artifacts/newtask-v8/eval-identities-1262.jsonl \\
        --official-out artifacts/newtask-v8/eval-official-xhard0-192.jsonl [--specs-root <v8 规格根>]

- 经 ``robomme_hard`` 的 ``BenchmarkEnvBuilder(task, "test-hard")`` 逐任务列出全部局：总数由表 2 推出
  1262 = 16 任务 × 1 档 × 12 局（xhard0）+ 43 格逐格局数之和 1070（``hard_specs.V8_CELLS``）；逐格局数也按
  ``V8_CELLS`` 核对。builder 读包内规格（阶段 3b 换包后即 v8）；``--specs-root`` 经 ``ROBOMME_HARD_SPECS_ROOT`` 覆盖。
- v8 不评估新局（用户 2026-10-01，第一部分引言 ⑥）：``round``／``shard`` 字段保留、一律置空（null）。
- 官方路线对照：xhard0 的 192 局（官方 test 的原 episode 号）仍按 ``TASK_SECONDS`` 贪心均衡切 10 片（3′ xhard0 评估用）。
- 行格式：``{task, episode, tier, seed, candidate, source_episode, round, shard}``；官方行 ``{task, source_episode, seed, shard}``。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import _common  # noqa: F401  路径设置

from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402

#: 每任务平均单局用时（秒；v6 SimpleMemVLA 实测，docs/eval-doc/testhard-0928/records 1100 局 elapsed_s 均值，
#: 策略仓库内留档）。原名 V6_SECONDS，随 V6 删除改名（v8 方案第一部分 §2.5）；用于官方路线分片均衡。
TASK_SECONDS = {
    "BinFill": 224.0, "ButtonUnmask": 116.5, "ButtonUnmaskSwap": 73.4, "InsertPeg": 152.2, "MoveCube": 180.3,
    "PatternLock": 79.8, "PickHighlight": 246.7, "PickXtimes": 114.2, "RouteStick": 74.1, "StopCube": 64.9,
    "SwingXtimes": 90.8, "VideoPlaceButton": 58.0, "VideoPlaceOrder": 61.7, "VideoRepick": 51.9, "VideoUnmask": 97.4,
    "VideoUnmaskSwap": 50.5,
}
SHARDS = 10
#: 表 2 推出的总局数：xhard0 16 × 12 + 新值 43 格 1070 = 1262
XHARD0_TOTAL = len(hard_specs.ALL_TASKS) * hard_specs.XHARD0_PER_TASK
EXPECTED_TOTAL = XHARD0_TOTAL + sum(hard_specs.V8_CELLS.values())
IDENTITIES_NAME = f"eval-identities-{EXPECTED_TOTAL}.jsonl"
assert EXPECTED_TOTAL == 1262, "表 2：1262 = 192 + 1070"


def balance(rows: list[dict], shards: int) -> None:
    """最长处理时间优先的贪心：按估计用时降序，逐局分给当前总用时最小的片（同用时取片号小者），就地写 ``shard``。"""
    load = [0.0] * shards
    for row in sorted(rows, key=lambda r: (-TASK_SECONDS[r["task"]], r["task"], r.get("episode", r.get("source_episode")))):
        k = min(range(shards), key=lambda i: (load[i], i))
        row["shard"] = k
        load[k] += TASK_SECONDS[row["task"]]


def check_rows(rows: list[dict], official: list[dict]) -> tuple[bool, dict]:
    """总数 1262、xhard0 192、逐格局数等于 V8_CELLS、round／shard 全空、官方 192。"""
    per_cell: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        if r["tier"] != hard_specs.XHARD0:
            per_cell[(r["task"], r["tier"])] += 1
    tiers: dict[str, int] = defaultdict(int)
    for r in rows:
        tiers[r["tier"]] += 1
    facts = {"episodes": len(rows), "xhard0": tiers.get(hard_specs.XHARD0, 0), "cells": len(per_cell),
             "cell_mismatch": sum(per_cell.get(k, 0) != n for k, n in hard_specs.V8_CELLS.items())
             + sum(k not in hard_specs.V8_CELLS for k in per_cell),
             "round_or_shard_set": sum(r.get("round") is not None or r.get("shard") is not None for r in rows),
             "official": len(official), "tiers": dict(sorted(tiers.items()))}
    ok = (facts["episodes"] == EXPECTED_TOTAL and facts["xhard0"] == XHARD0_TOTAL and facts["cell_mismatch"] == 0
          and facts["round_or_shard_set"] == 0 and facts["official"] == XHARD0_TOTAL)
    return ok, facts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=f"artifacts/newtask-v8/{IDENTITIES_NAME}")
    parser.add_argument("--official-out", default="artifacts/newtask-v8/eval-official-xhard0-192.jsonl")
    parser.add_argument("--specs-root", default=None, help="覆盖规格根（经 ROBOMME_HARD_SPECS_ROOT）")
    args = parser.parse_args()
    if args.specs_root:
        os.environ[hard_specs.SPECS_ROOT_ENV] = str(Path(args.specs_root).resolve())
    from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder

    rows = []
    for task in hard_specs.ALL_TASKS:
        builder = BenchmarkEnvBuilder(task, dataset="test-hard")
        items = []
        for ep in range(builder.get_episode_num()):
            ident = builder.resolve_identity(ep)
            items.append({"task": task, "episode": ep, "tier": ident["tier"], "seed": ident["seed"],
                          "candidate": ident.get("candidate"), "source_episode": ident.get("source_episode"),
                          "round": None, "shard": None})
        rows.extend(items)
    rows.sort(key=lambda r: (hard_specs.ALL_TASKS.index(r["task"]), r["episode"]))
    official = [{"task": r["task"], "source_episode": r["source_episode"], "seed": r["seed"]}
                for r in rows if r["tier"] == hard_specs.XHARD0]
    balance(official, SHARDS)
    official.sort(key=lambda r: (r["shard"], hard_specs.ALL_TASKS.index(r["task"]), r["source_episode"]))
    for path, data in ((args.out, rows), (args.official_out, official)):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in data))
    ok, facts = check_rows(rows, official)
    print(f"EVAL_IDENTITY_EXPORT={'PASS' if ok else 'FAIL'} episodes={facts['episodes']} expected={EXPECTED_TOTAL} "
          f"xhard0={facts['xhard0']} cells={facts['cells']} cell_mismatch={facts['cell_mismatch']} "
          f"round_or_shard_set={facts['round_or_shard_set']} official={facts['official']} shards={SHARDS} "
          f"tiers={facts['tiers']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
