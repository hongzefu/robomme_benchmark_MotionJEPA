#!/usr/bin/env python3
"""V6 组合覆盖（口径 14 / N11 / H3；NEWTASK_RELEASE_V4_PLAN 步 3c）。

读一份**冻结的组合清单**（JSON），对每个组合把 xhard 声明范围收窄到该组合的取值（离散量逐值、连续量取端点），
用与正式生成逐字相同的 ``generate_dataset_newseed._worker`` 跑 ``--samples`` 条演示，两级都报：
reset 级（有没有抛生成期异常）与演示级（整局成功）。**以演示级为准**：任一组合演示成功数为 0 即
``zero_success_combinations`` 计 1，须停下回报用户重定参数（不许实施方自行收窄）。

组合清单格式（``scripts/configs/newtask-v4/combos.json``，冻结进 Git）::

    {"schema": "v4-combos/1",
     "tasks": {"PickXtimes": [
         {"name": "num=6", "set": {"decision.number_range.xhard": [6, 6]}},
         {"name": "num=15", "set": {"decision.number_range.xhard": [15, 15]}}]}}

``set`` 的键是 ``{decision, native}`` 配置里的点分路径，值整体替换；守卫只允许改已申报的 xhard 条目，
改到原三档可见部分会当场被 ``assert_native_decision`` 拒绝（这正是想要的）。

    uv run --no-sync python -m scripts.parity.v4_combos --combos scripts/configs/newtask-v4/combos.json \
        --samples 3 --out artifacts/newtask-v4/combos/<run> [--tasks PickXtimes]
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.parity.v4_specs import DEFAULT_SAMPLING, task_sampling  # noqa: E402

# 与抽签/正式实跑都不重叠的 seed 段：7_000_000 + env_code*100_000 + combo*1000 + sample
COMBO_SEED_OFFSET = 7_000_000


def apply_set(config: dict, assignments: dict) -> dict:
    out = copy.deepcopy(config)
    for dotted, value in assignments.items():
        node = out
        parts = dotted.split(".")
        for part in parts[:-1]:
            if part not in node:
                raise KeyError(f"组合路径不存在：{dotted}")
            node = node[part]
        if parts[-1] not in node:
            raise KeyError(f"组合路径不存在：{dotted}")
        node[parts[-1]] = copy.deepcopy(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--combos", required=True)
    parser.add_argument("--sampling-config", default=str(DEFAULT_SAMPLING))
    parser.add_argument("--samples", type=int, required=True, help="每组合跑几条（样本量按 G3 由用户定）")
    parser.add_argument("--tasks", default="all")
    parser.add_argument("--gpu", default=os.environ.get("CUDA_VISIBLE_DEVICES", "0"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import generate_dataset_newseed as gen
    from seed_layout import env_code

    combos = json.loads(Path(args.combos).read_text(encoding="utf-8"))
    if combos.get("schema") != "v4-combos/1":
        raise SystemExit("组合清单版本不符")
    sampling = json.loads(Path(args.sampling_config).read_text(encoding="utf-8"))
    gen._pool_init(args.gpu, None, str(REPO_ROOT / "src"))
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows_path = out / "combos.jsonl"
    tasks = list(combos["tasks"]) if args.tasks == "all" else args.tasks.split(",")
    total = missing = zero = 0
    for task in tasks:
        base = task_sampling(sampling, task)
        for index, combo in enumerate(combos["tasks"].get(task, [])):
            total += 1
            config = apply_set(base, combo["set"])
            reset_ok = demo_ok = 0
            failures: dict[str, int] = {}
            for sample in range(args.samples):
                seed = COMBO_SEED_OFFSET + env_code(task) * 100_000 + index * 1000 + sample
                job = gen.EpisodeJob(task=task, episode=9, attempt=0, seed=seed, difficulty="xhard",
                                     output_root=str(out / "episodes"), repo_root=str(REPO_ROOT),
                                     sampling_config=config)
                started = time.time()
                result = gen._worker(job)
                # reset 级：_worker 在 reset 返回后才写 phases["reset_s"]；成功局必然过了 reset
                phase_reset = bool(result.get("ok")) or "reset_s" in (result.get("phases") or {})
                reset_ok += bool(phase_reset)
                demo_ok += bool(result.get("ok"))
                if not result.get("ok"):
                    key = f"{result.get('failure_class')}:{result.get('error_type')}"
                    failures[key] = failures.get(key, 0) + 1
                print(f"COMBO {task} [{combo['name']}] seed={seed} ok={result.get('ok')} "
                      f"{result.get('error_type') or ''} {time.time() - started:.0f}s", flush=True)
            if args.samples == 0:
                missing += 1
            zero += demo_ok == 0
            row = {"task": task, "combo": combo["name"], "set": combo["set"], "samples": args.samples,
                   "reset_ok": reset_ok, "demo_ok": demo_ok, "failures": failures}
            with rows_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    status = "PASS" if missing == 0 and zero == 0 else "FAIL"
    print(f"COMBO_COVERAGE={status} combos={total} missing_combinations={missing} zero_success_combinations={zero}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
