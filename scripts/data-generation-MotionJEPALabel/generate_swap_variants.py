#!/usr/bin/env python3
"""主生成入口：对每个源 episode 穷举全部 swap 变体并 rollout。

前置：必须先跑 `probe_original.py`（Phase 0）——is_original 判定与布局基线
都依赖它的 `original_index.json`。

产物（--output-dir 下）：
* `hdf5_files/{Task}_ep{staging}_seed{variant_seed}.h5`（含 swap_gt 逐帧标注）
* `videos/`、`traces/`
* `variant_results.jsonl`（逐 attempt，边跑边写）
* `variants_manifest.json`（成功变体总账：编号/seed/pairs/签名/净置换/is_original/段长）
* `run_parameters.json` / `run_summary.json`

退出码非零的情形：有变体用尽 attempt、布局指纹与 Phase 0 基线不符、
is_original 不恰好每源 episode 一条。
"""

from __future__ import annotations

import os

_THREAD_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "OPENCV_FOR_THREADS_NUM",
)
if os.environ.get("MJLABEL_LIMIT_THREADS", "1") != "0":
    for _name in _THREAD_VARS:
        os.environ[_name] = "1"

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from variant_plan import (  # noqa: E402
    DEFAULT_SRC_EPISODES,
    EVAL_TASKS,
    REPO_ROOT,
    source_episode,
    variant_specs,
)
from variant_worker import VariantJob, run_jobs  # noqa: E402


def _scan_jsonl(path: Path) -> tuple[dict[tuple[str, int, int], dict], dict[tuple[str, int, int], int]]:
    """扫描既有 JSONL：已成功的变体（按 key 去重、保留最后一条）与各变体的失败 attempt 数。

    支持断点续跑：已成功的跳过；有失败史的直接从 attempt 1 起步（失败是确定性的，
    不必重证，且 attempt≥1 会启用 ButtonUnmaskSwap 的抓取前 hold）。
    """
    ok: dict[tuple[str, int, int], dict] = {}
    fails: dict[tuple[str, int, int], int] = {}
    if not path.is_file():
        return ok, fails
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            key = (record["task"], record["src_episode"], record["variant_idx"])
            if record.get("ok"):
                ok[key] = record
            else:
                fails[key] = fails.get(key, 0) + 1
    return ok, fails


def _load_original_index(path: Path) -> dict[tuple[str, int], dict]:
    if not path.is_file():
        raise SystemExit(
            f"ERROR: 找不到 {path} —— 必须先跑 probe_original.py（Phase 0）"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("gate_failures") or payload.get("exhausted"):
        raise SystemExit(
            f"ERROR: {path} 里 Phase 0 未全绿（gate_failures="
            f"{payload.get('gate_failures')}），先解决红线再生成"
        )
    return {
        (record["task"], int(record["episode"])): record for record in payload["records"]
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="穷举生成 swap 变体数据集")
    parser.add_argument("--output-dir", default=str(SCRIPT_DIR / "outputs" / "full"))
    parser.add_argument("--tasks", default=",".join(EVAL_TASKS))
    parser.add_argument(
        "--src-episodes", default=",".join(str(item) for item in DEFAULT_SRC_EPISODES)
    )
    parser.add_argument(
        "--original-index",
        default=str(SCRIPT_DIR / "outputs" / "phase0" / "original_index.json"),
    )
    parser.add_argument("--gpus", default="0", help="逗号分隔的物理卡号")
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--max-tasks-per-child", type=int, default=8)
    parser.add_argument(
        "--no-repeat-adjacent",
        dest="allow_repeat_adjacent",
        action="store_false",
        help="过滤相邻重复对（默认保留——用户已拍板 744/318 口径）",
    )
    args = parser.parse_args(argv)

    output = Path(args.output_dir).resolve()
    if REPO_ROOT.resolve() not in output.parents:
        print(f"ERROR: 输出目录必须在仓库内：{output}", file=sys.stderr)
        return 1
    output.mkdir(parents=True, exist_ok=True)
    (output / "hdf5_files").mkdir(exist_ok=True)

    tasks = tuple(item.strip() for item in args.tasks.split(",") if item.strip())
    episodes = tuple(int(item) for item in args.src_episodes.split(",") if item.strip())
    gpu_ids = tuple(item.strip() for item in args.gpus.split(",") if item.strip())
    originals = _load_original_index(Path(args.original_index))

    prior_ok, prior_fails = _scan_jsonl(output / "variant_results.jsonl")

    jobs: list[VariantJob] = []
    baseline: dict[tuple[str, int], dict] = {}
    skipped = 0
    for task in tasks:
        for episode in episodes:
            key = (task, episode)
            if key not in originals:
                print(f"ERROR: Phase 0 没覆盖 {task}/ep{episode}", file=sys.stderr)
                return 1
            record = originals[key]
            src = source_episode(task, episode)
            if record["num_bins_actual"] != src.num_bins:
                print(
                    f"ERROR: {task}/ep{episode} 实测 bin 数 {record['num_bins_actual']} "
                    f"≠ 配置 {src.num_bins}，枚举空间不成立",
                    file=sys.stderr,
                )
                return 1
            baseline[key] = record["fingerprint"]
            original_pairs = tuple(tuple(pair) for pair in record["original_pairs"])
            for spec in variant_specs(src, args.allow_repeat_adjacent):
                variant_key = (task, episode, spec.variant_idx)
                prior = prior_ok.get(variant_key)
                if prior is not None and Path(prior["h5_path"]).is_file():
                    skipped += 1
                    continue
                jobs.append(
                    VariantJob(
                        task=task,
                        src_episode=episode,
                        variant_idx=spec.variant_idx,
                        env_seed=spec.env_seed,
                        variant_seed=spec.variant_seed,
                        wrapper_episode=spec.staging_episode,
                        difficulty=spec.difficulty,
                        num_bins=spec.num_bins,
                        pairs=spec.pairs,
                        original_pairs=original_pairs,
                        attempt=1 if prior_fails.get(variant_key) else 0,
                        output_root=str(output),
                        repo_root=str(REPO_ROOT),
                    )
                )
    if skipped:
        print(f"断点续跑：跳过已成功的 {skipped} 条变体", flush=True)

    parameters = {
        "output_dir": str(output),
        "tasks": list(tasks),
        "src_episodes": list(episodes),
        "allow_repeat_adjacent": args.allow_repeat_adjacent,
        "variant_count": len(jobs),
        "gpus": list(gpu_ids),
        "workers": args.workers,
        "max_attempts": args.max_attempts,
        "original_index": str(args.original_index),
    }
    (output / "run_parameters.json").write_text(
        json.dumps(parameters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"共 {len(jobs)} 条变体待生成（{', '.join(tasks)} × ep{episodes}）", flush=True)

    started = time.monotonic()
    succeeded, exhausted = run_jobs(
        jobs=jobs,
        gpu_ids=gpu_ids,
        workers=args.workers,
        jsonl_path=output / "variant_results.jsonl",
        max_attempts=args.max_attempts,
        max_tasks_per_child=args.max_tasks_per_child,
    )
    elapsed = time.monotonic() - started

    # ── 事后闸门：布局指纹必须与 Phase 0 基线逐位相同；is_original 每源恰一条 ──
    # 从 JSONL 全量重扫（含历史 run 的成功记录），保证断点续跑后的 manifest 完整。
    all_ok, _ = _scan_jsonl(output / "variant_results.jsonl")
    gate_failures: list[str] = []
    original_counts: dict[tuple[str, int], int] = {}
    manifest = []
    for result in sorted(
        all_ok.values(), key=lambda item: (item["task"], item["src_episode"], item["variant_idx"])
    ):
        key = (result["task"], result["src_episode"])
        if result["fingerprint"] != baseline[key]:
            gate_failures.append(
                f"{result['task']}/ep{result['src_episode']}/var{result['variant_idx']}: "
                "布局指纹与 Phase 0 基线不符"
            )
        if result["is_original"] == 1:
            original_counts[key] = original_counts.get(key, 0) + 1
        manifest.append(
            {
                "task": result["task"],
                "src_episode": result["src_episode"],
                "variant_idx": result["variant_idx"],
                "staging_episode": result["wrapper_episode"],
                "variant_seed": result["variant_seed"],
                "env_seed": result["env_seed"],
                "difficulty": result["difficulty"],
                "pairs": result["pairs"],
                "signature": result["signature"],
                "net_permutation": result["net_permutation"],
                "is_original": result["is_original"],
                "n_timesteps": result["n_timesteps"],
                "demo_prefix": result["demo_prefix"],
                "exec_len": result["exec_len"],
                "min_clearance": result["min_clearance"],
                "bystander_net_max": result["bystander_net_max"],
                "bystander_path_max": result["bystander_path_max"],
                "disturbed_bins": result["disturbed_bins"],
                "attempt": result["attempt"],
                "pickup_hold_step": result.get("pickup_hold_step"),
                "h5_path": result["h5_path"],
                "intended_use": "eval-only",
            }
        )
    for task in tasks:
        for episode in episodes:
            count = original_counts.get((task, episode), 0)
            if count != 1:
                gate_failures.append(
                    f"{task}/ep{episode}: is_original 变体数为 {count}，应恰为 1"
                )

    (output / "variants_manifest.json").write_text(
        json.dumps(
            {"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "records": manifest},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = {
        "parameters": parameters,
        "requested_count": len(jobs),
        "success_count_this_run": len(succeeded),
        "success_count_total": len(all_ok),
        "exhausted_count": len(exhausted),
        "gate_failures": gate_failures,
        "elapsed_s": round(elapsed, 1),
        "throughput_ep_per_min": round(len(succeeded) / (elapsed / 60), 2) if elapsed > 0 else None,
    }
    (output / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if exhausted:
        print(f"ERROR: {len(exhausted)} 条变体用尽 attempt", file=sys.stderr)
        return 1
    if gate_failures:
        print("ERROR: 事后闸门未过：", file=sys.stderr)
        for line in gate_failures:
            print(f"  {line}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
