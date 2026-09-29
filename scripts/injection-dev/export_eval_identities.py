#!/usr/bin/env python3
"""v7 评估逐身份清单导出（0928 方案第一部分 §5 第 3 条；阶段 8）。

    uv run --no-sync python scripts/injection-dev/export_eval_identities.py \
        --out artifacts/newtask-v7/eval-identities-1292.jsonl \
        --official-out artifacts/newtask-v7/eval-official-xhard0-192.jsonl [--specs-root <v7 规格根>]

- v7 路线：经 ``robomme_hard`` 的 ``BenchmarkEnvBuilder(task, "test-hard")`` 逐任务列出全部局（1292 = 16 任务 × 1 档 × 12 局
  + 55 格 × 20 局）。分轮沿用 v6 口径（用户 2026-09-29「仍旧采用上一次v6生成的eval分法」）：每格按 ``candidate`` 升序前 10 局第一轮、
  后 10 局第二轮；xhard0 每任务按原 episode 升序前 6 局第一轮、后 6 局第二轮 → 每轮 646。
- 每轮切 10 片：646 不能被 10 整除，按 v6 实测每任务平均单局用时（下表）做贪心均衡，不要求每片局数相同。
- 官方路线对照（阶段 10′）：xhard0 的 192 局（官方 test 的原 episode 号），同法均衡切 10 片。
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

#: v6 SimpleMemVLA 实测每任务平均单局用时（秒；docs/eval-doc/testhard-0928/records 1100 局 elapsed_s 均值，策略仓库内留档）
V6_SECONDS = {
    "BinFill": 224.0, "ButtonUnmask": 116.5, "ButtonUnmaskSwap": 73.4, "InsertPeg": 152.2, "MoveCube": 180.3,
    "PatternLock": 79.8, "PickHighlight": 246.7, "PickXtimes": 114.2, "RouteStick": 74.1, "StopCube": 64.9,
    "SwingXtimes": 90.8, "VideoPlaceButton": 58.0, "VideoPlaceOrder": 61.7, "VideoRepick": 51.9, "VideoUnmask": 97.4,
    "VideoUnmaskSwap": 50.5,
}
SHARDS = 10
XHARD0_ROUND1 = 6
PER_ROUND = 10


def balance(rows: list[dict], shards: int) -> None:
    """最长处理时间优先的贪心：按估计用时降序，逐局分给当前总用时最小的片（同用时取片号小者），就地写 ``shard``。"""
    load = [0.0] * shards
    for row in sorted(rows, key=lambda r: (-V6_SECONDS[r["task"]], r["task"], r.get("episode", r.get("source_episode")))):
        k = min(range(shards), key=lambda i: (load[i], i))
        row["shard"] = k
        load[k] += V6_SECONDS[row["task"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--official-out", required=True)
    parser.add_argument("--specs-root", default=None, help="换包前用 v7 规格根（经 ROBOMME_HARD_SPECS_ROOT）")
    args = parser.parse_args()
    if args.specs_root:
        os.environ[hard_specs.SPECS_ROOT_ENV] = str(Path(args.specs_root).resolve())
    from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder

    rows = []
    for task in hard_specs.ALL_TASKS:
        builder = BenchmarkEnvBuilder(task, dataset="test-hard")
        by_tier: dict[str, list[dict]] = defaultdict(list)
        for ep in range(builder.get_episode_num()):
            ident = builder.resolve_identity(ep)
            by_tier[ident["tier"]].append({"task": task, "episode": ep, "tier": ident["tier"], "seed": ident["seed"],
                                           "candidate": ident.get("candidate"),
                                           "source_episode": ident.get("source_episode")})
        for tier, items in by_tier.items():
            if tier == hard_specs.XHARD0:
                items.sort(key=lambda r: r["source_episode"])
                cut = XHARD0_ROUND1
            else:
                items.sort(key=lambda r: r["candidate"])
                cut = PER_ROUND
            for rank, row in enumerate(items):
                row["round"] = 1 if rank < cut else 2
            rows.extend(items)
    for rnd in (1, 2):
        balance([r for r in rows if r["round"] == rnd], SHARDS)
    rows.sort(key=lambda r: (r["round"], r["shard"], hard_specs.ALL_TASKS.index(r["task"]), r["episode"]))
    official = [{"task": r["task"], "source_episode": r["source_episode"], "seed": r["seed"]}
                for r in rows if r["tier"] == hard_specs.XHARD0]
    balance(official, SHARDS)
    official.sort(key=lambda r: (r["shard"], hard_specs.ALL_TASKS.index(r["task"]), r["source_episode"]))
    for path, data in ((args.out, rows), (args.official_out, official)):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in data))
    counts = {rnd: sum(r["round"] == rnd for r in rows) for rnd in (1, 2)}
    tiers = defaultdict(int)
    for r in rows:
        tiers[r["tier"]] += 1
    loads = {rnd: [round(sum(V6_SECONDS[r["task"]] for r in rows if r["round"] == rnd and r["shard"] == k) / 60)
                   for k in range(SHARDS)] for rnd in (1, 2)}
    ok = len(rows) == 1292 and counts == {1: 646, 2: 646} and len(official) == 192 and tiers.get("xhard0") == 192
    print(f"EVAL_IDENTITY_EXPORT={'PASS' if ok else 'FAIL'} episodes={len(rows)} round1={counts[1]} round2={counts[2]} "
          f"shards={SHARDS} official={len(official)} tiers={dict(sorted(tiers.items()))} est_minutes_per_shard={loads}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
