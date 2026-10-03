#!/usr/bin/env python3
"""v8／v9 逐身份清单导出（v8 方案第二部分 §2.2 第 9 条；v9 见 1002 方案 §2.4.2 第 7 步；原 v7 版见 0928 方案第一部分 §5 第 3 条）。

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

**v9**（1002 方案）：总数与逐格局数改由格表推出——格表取 ``--specs-root`` 各档 header 的逐任务配额
（``hard_parity.root_cell_table``：完整 V9 根恰为 V9_CELLS），不给 ``--specs-root`` 时取包内 ``EXPECTED_CELLS``
（v9 阶段 3b 切换后即 V9）。V9：992 = 192 + 800，默认文件名 ``eval-identities-992.jsonl``，默认目录
``artifacts/newtask-v9/``；V8 仍 1262 与 ``artifacts/newtask-v8/``。V9 运行时：

* ``--delivery`` 必给（v9 assemble 的 800 行 ``delivery.local.json``）：builder 列出的 800 个新值身份
  (task, tier, seed) 须与清单逐一相同（``delivery_mismatch``）；
* ``--official-out`` **必须显式给 V9 路径**（审计 10）：其默认值仍指向 V8 根
  ``artifacts/newtask-v8/eval-official-xhard0-192.jsonl``，V9 运行时用默认值即报错退出，避免覆写 V8 产物::

    uv run --no-sync python scripts/injection-dev/export_eval_identities.py \\
        --specs-root artifacts/newtask-v9/specs-root --delivery artifacts/newtask-v9/delivery/delivery.local.json \\
        --out artifacts/v9-evaluation/inputs/eval-identities-992.jsonl \\
        --official-out artifacts/v9-evaluation/inputs/eval-official-xhard0-192.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import _common  # noqa: F401  路径设置

import hard_parity  # noqa: E402  scripts/parity（_common 已加路径；纯标准库）
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
XHARD0_TOTAL = len(hard_specs.ALL_TASKS) * hard_specs.XHARD0_PER_TASK
#: 官方路线 xhard0 清单的默认路径（V8 根；V9 必须显式给，审计 10）
OFFICIAL_OUT_DEFAULT = "artifacts/newtask-v8/eval-official-xhard0-192.jsonl"


def expected_total(cells: dict[tuple[str, str], int]) -> int:
    """格表推出的总局数：xhard0 16 × 12 + 新值格局数之和（V8 1262 = 192 + 1070；V9 992 = 192 + 800）。"""
    return XHARD0_TOTAL + sum(cells.values())


def identities_name(cells: dict[tuple[str, str], int]) -> str:
    return f"eval-identities-{expected_total(cells)}.jsonl"


#: 包内当前格表（EXPECTED_CELLS）推出的总局数与默认文件名：v9 阶段 3b 切换前 1262，切换后 992
EXPECTED_TOTAL = expected_total(hard_specs.EXPECTED_CELLS)
IDENTITIES_NAME = identities_name(hard_specs.EXPECTED_CELLS)


def balance(rows: list[dict], shards: int) -> None:
    """最长处理时间优先的贪心：按估计用时降序，逐局分给当前总用时最小的片（同用时取片号小者），就地写 ``shard``。"""
    load = [0.0] * shards
    for row in sorted(rows, key=lambda r: (-TASK_SECONDS[r["task"]], r["task"], r.get("episode", r.get("source_episode")))):
        k = min(range(shards), key=lambda i: (load[i], i))
        row["shard"] = k
        load[k] += TASK_SECONDS[row["task"]]


def check_rows(rows: list[dict], official: list[dict], cells: dict[tuple[str, str], int] | None = None,
               delivery_ids: set[tuple[str, str, int]] | None = None) -> tuple[bool, dict]:
    """总数 = :func:`expected_total`（V8 1262／V9 992）、xhard0 192、逐格局数等于格表（缺省 EXPECTED_CELLS）、
    round／shard 全空、官方 192；给 ``delivery_ids`` 时新值身份 (task, tier, seed) 须与之逐一相同。"""
    cells = hard_specs.EXPECTED_CELLS if cells is None else cells
    per_cell: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        if r["tier"] != hard_specs.XHARD0:
            per_cell[(r["task"], r["tier"])] += 1
    tiers: dict[str, int] = defaultdict(int)
    for r in rows:
        tiers[r["tier"]] += 1
    facts = {"episodes": len(rows), "xhard0": tiers.get(hard_specs.XHARD0, 0), "cells": len(per_cell),
             "cell_mismatch": sum(per_cell.get(k, 0) != n for k, n in cells.items())
             + sum(k not in cells for k in per_cell),
             "round_or_shard_set": sum(r.get("round") is not None or r.get("shard") is not None for r in rows),
             "official": len(official), "tiers": dict(sorted(tiers.items())), "expected": expected_total(cells)}
    if delivery_ids is not None:
        new_ids = {(r["task"], r["tier"], int(r["seed"])) for r in rows if r["tier"] != hard_specs.XHARD0}
        facts["delivery_mismatch"] = len(new_ids ^ delivery_ids)
    ok = (facts["episodes"] == facts["expected"] and facts["xhard0"] == XHARD0_TOTAL and facts["cell_mismatch"] == 0
          and facts["round_or_shard_set"] == 0 and facts["official"] == XHARD0_TOTAL
          and facts.get("delivery_mismatch", 0) == 0)
    return ok, facts


def resolve_table(specs_root: str | None) -> tuple[str, dict[tuple[str, str], int]]:
    """格表：``--specs-root`` 的 header 逐任务配额推出（V9 根 → V9_CELLS），否则包内 EXPECTED_CELLS。"""
    if specs_root:
        found = hard_parity.root_cell_table(specs_root, hard_specs)
        if found is not None:
            return found
    return hard_parity.table_version(hard_specs.EXPECTED_CELLS, hard_specs), hard_specs.EXPECTED_CELLS


def read_delivery_ids(path: str) -> set[tuple[str, str, int]]:
    """交付清单（v8-delivery/1 或 v9 的 800 行清单）的新值身份集合 (task, tier, seed)。"""
    return {hard_parity.ident(r) for r in hard_parity.read_delivery(Path(path))["rows"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=None,
                        help="逐身份清单输出；缺省 artifacts/newtask-<版本>/eval-identities-<总数>.jsonl"
                             "（V8 → newtask-v8/eval-identities-1262.jsonl，V9 → newtask-v9/eval-identities-992.jsonl）")
    parser.add_argument("--official-out", default=OFFICIAL_OUT_DEFAULT,
                        help=f"官方路线 xhard0 192 局清单输出；默认 {OFFICIAL_OUT_DEFAULT} 是 V8 根——"
                             "V9 必须显式给（如 artifacts/v9-evaluation/inputs/eval-official-xhard0-192.jsonl），"
                             "V9 运行时用默认值即报错退出（审计 10）")
    parser.add_argument("--specs-root", default=None,
                        help="覆盖规格根（经 ROBOMME_HARD_SPECS_ROOT）；格表按其各档 header 的逐任务配额推出（V9 根 → 992）")
    parser.add_argument("--delivery", default=None,
                        help="交付清单 json（V9 必给：v9 assemble 的 800 行 delivery.local.json）；新值身份须与之逐一相同")
    args = parser.parse_args(argv)
    version, cells = resolve_table(args.specs_root)
    if version == "v9":
        if args.delivery is None:
            parser.error("V9 格表须给 --delivery（v9 assemble 的 800 行交付清单）")
        if args.official_out == OFFICIAL_OUT_DEFAULT:
            parser.error(f"V9 格表须显式给 --official-out（默认值 {OFFICIAL_OUT_DEFAULT} 是 V8 根，不得覆写）")
    out = args.out or f"artifacts/newtask-{version}/{identities_name(cells)}"
    delivery_ids = read_delivery_ids(args.delivery) if args.delivery else None
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
    for path, data in ((out, rows), (args.official_out, official)):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in data))
    ok, facts = check_rows(rows, official, cells, delivery_ids)
    print(f"EVAL_IDENTITY_EXPORT={'PASS' if ok else 'FAIL'} version={version} episodes={facts['episodes']} "
          f"expected={facts['expected']} "
          f"xhard0={facts['xhard0']} cells={facts['cells']} cell_mismatch={facts['cell_mismatch']} "
          + (f"delivery_mismatch={facts['delivery_mismatch']} " if "delivery_mismatch" in facts else "") +
          f"round_or_shard_set={facts['round_or_shard_set']} official={facts['official']} shards={SHARDS} "
          f"tiers={facts['tiers']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
