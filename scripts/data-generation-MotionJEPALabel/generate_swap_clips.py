#!/usr/bin/env python3
"""主生成入口：对每个源 episode 枚举第一次 swap 的 6 种槽位对，各产一条 110 帧 clip。

前置：必须先跑 `probe_original.py`（Phase 0）—— 窗口 ≥2 的固定槽位对与布局基线都
依赖它的 `original_index.json`。

产物（--output-dir 下）：
* `clips/{Task}_ep{staging}_seed{variant_seed}.h5`（110 帧，含逐帧 + setup 级 swap_gt）
* `videos/`（截断 rollout 的完整录像）、`traces/`（clip 区间位姿 npz）
* `clip_results.jsonl`（逐 attempt，边跑边写）
* `clips_manifest.json`（成功 clip 总账）、`run_parameters.json`、`run_summary.json`

退出码非零的情形：有 clip 用尽 attempt、布局指纹与 Phase 0 基线不符、
is_original 不恰好每源一条、或同源变体的窗口 ≥2 槽位对不唯一。
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

from clip_plan import (  # noqa: E402
    CANDIDATE_EPISODES,
    CLIP_END,
    CLIP_LEN,
    CLIP_START,
    EVAL_TASKS,
    REPO_ROOT,
    select_sources,
    variant_specs,
)
from clip_worker import ClipJob, run_jobs  # noqa: E402


def _scan_jsonl(path: Path) -> tuple[dict[tuple[str, int, int], dict], dict[tuple[str, int, int], int]]:
    """扫描既有 JSONL：已成功的 clip（按 key 去重、保留最后一条）与各自的失败 attempt 数。

    支持断点续跑：已成功且产物还在的直接跳过。
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
        raise SystemExit(f"ERROR: 找不到 {path} —— 必须先跑 probe_original.py（Phase 0）")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("gate_failures") or payload.get("exhausted"):
        raise SystemExit(
            f"ERROR: {path} 里 Phase 0 未全绿（gate_failures="
            f"{payload.get('gate_failures')}），先解决红线再生成"
        )
    return {(record["task"], int(record["episode"])): record for record in payload["records"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成单事件 swap clip 数据集")
    parser.add_argument("--output-dir", default=str(SCRIPT_DIR / "outputs" / "event1"))
    parser.add_argument("--tasks", default=",".join(EVAL_TASKS))
    parser.add_argument(
        "--episodes",
        default=",".join(str(item) for item in CANDIDATE_EPISODES),
        help="候选源 episode（筛选前）",
    )
    parser.add_argument(
        "--only-episodes", default=None, help="调试用：只跑这些源 episode（逗号分隔）"
    )
    parser.add_argument(
        "--original-index", default=str(SCRIPT_DIR / "outputs" / "phase0" / "original_index.json")
    )
    parser.add_argument("--gpus", default="0", help="逗号分隔的物理卡号")
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--max-tasks-per-child", type=int, default=8)
    args = parser.parse_args(argv)

    output = Path(args.output_dir).resolve()
    if REPO_ROOT.resolve() not in output.parents:
        print(f"ERROR: 输出目录必须在仓库内：{output}", file=sys.stderr)
        return 1
    output.mkdir(parents=True, exist_ok=True)
    (output / "hdf5_files").mkdir(exist_ok=True)
    (output / "clips").mkdir(exist_ok=True)

    tasks = tuple(item.strip() for item in args.tasks.split(",") if item.strip())
    episodes = tuple(int(item) for item in args.episodes.split(",") if item.strip())
    gpu_ids = tuple(item.strip() for item in args.gpus.split(",") if item.strip())
    only = (
        {int(item) for item in args.only_episodes.split(",") if item.strip()}
        if args.only_episodes
        else None
    )
    originals = _load_original_index(Path(args.original_index))
    selected = select_sources(tasks, episodes)

    prior_ok, prior_fails = _scan_jsonl(output / "clip_results.jsonl")

    jobs: list[ClipJob] = []
    baseline: dict[tuple[str, int], dict] = {}
    expected: dict[tuple[str, int], int] = {}
    skipped = 0
    for task in tasks:
        for src in selected[task]:
            if only is not None and src.episode not in only:
                continue
            key = (task, src.episode)
            if key not in originals:
                print(f"ERROR: Phase 0 没覆盖 {task}/ep{src.episode}", file=sys.stderr)
                return 1
            record = originals[key]
            if record["num_bins_actual"] != src.num_bins:
                print(
                    f"ERROR: {task}/ep{src.episode} 实测 bin 数 {record['num_bins_actual']} "
                    f"≠ 配置 {src.num_bins}，枚举空间不成立",
                    file=sys.stderr,
                )
                return 1
            baseline[key] = record["fingerprint"]
            original_bin_pairs = tuple(tuple(pair) for pair in record["original_bin_pairs"])
            specs = variant_specs(src, original_bin_pairs)
            expected[key] = len(specs)
            for spec in specs:
                variant_key = (task, src.episode, spec.variant_idx)
                prior = prior_ok.get(variant_key)
                if prior is not None and Path(prior["h5_path"]).is_file():
                    skipped += 1
                    continue
                jobs.append(
                    ClipJob(
                        task=task,
                        src_episode=src.episode,
                        variant_idx=spec.variant_idx,
                        env_seed=spec.env_seed,
                        variant_seed=spec.variant_seed,
                        wrapper_episode=spec.staging_episode,
                        difficulty=spec.difficulty,
                        num_bins=spec.num_bins,
                        mode="clip",
                        bin_pairs=spec.bin_pairs,
                        slot_pairs=spec.slot_pairs,
                        is_original=spec.is_original,
                        attempt=1 if prior_fails.get(variant_key) else 0,
                        output_root=str(output),
                        repo_root=str(REPO_ROOT),
                    )
                )
    if skipped:
        print(f"断点续跑：跳过已成功的 {skipped} 条 clip", flush=True)

    parameters = {
        "output_dir": str(output),
        "tasks": list(tasks),
        "selected_episodes": {task: [src.episode for src in selected[task]] for task in tasks},
        "clip": {"start": CLIP_START, "end": CLIP_END, "length": CLIP_LEN},
        "expected_total": sum(expected.values()),
        "queued": len(jobs),
        "gpus": list(gpu_ids),
        "workers": args.workers,
        "max_attempts": args.max_attempts,
        "original_index": str(args.original_index),
    }
    (output / "run_parameters.json").write_text(
        json.dumps(parameters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"共 {len(jobs)} 条 clip 待生成（期望总量 {sum(expected.values())}，"
        f"clip = env step [{CLIP_START},{CLIP_END}) 共 {CLIP_LEN} 帧）",
        flush=True,
    )

    started = time.monotonic()
    succeeded, exhausted = run_jobs(
        jobs=jobs,
        gpu_ids=gpu_ids,
        workers=args.workers,
        jsonl_path=output / "clip_results.jsonl",
        max_attempts=args.max_attempts,
        max_tasks_per_child=args.max_tasks_per_child,
    ) if jobs else ([], [])
    elapsed = time.monotonic() - started

    # ── 事后闸门：从 JSONL 全量重扫（含历史 run），保证断点续跑后的 manifest 完整 ──
    all_ok, _ = _scan_jsonl(output / "clip_results.jsonl")
    gate_failures: list[str] = []
    original_counts: dict[tuple[str, int], int] = {}
    tail_slots: dict[tuple[str, int], set] = {}
    manifest = []
    for result in sorted(
        all_ok.values(), key=lambda item: (item["task"], item["src_episode"], item["variant_idx"])
    ):
        key = (result["task"], result["src_episode"])
        if key not in baseline:
            continue  # 本次未覆盖的源（--only-episodes 调试）不参与闸门
        if result["fingerprint"] != baseline[key]:
            gate_failures.append(
                f"{result['task']}/ep{result['src_episode']}/var{result['variant_idx']}: "
                "布局指纹与 Phase 0 基线不符"
            )
        if result["is_original"] == 1:
            original_counts[key] = original_counts.get(key, 0) + 1
        tail_slots.setdefault(key, set()).add(
            tuple(tuple(pair) for pair in result["slot_pairs"][1:])
        )
        manifest.append(
            {
                "task": result["task"],
                "src_episode": result["src_episode"],
                "variant_idx": result["variant_idx"],
                "staging_episode": result["wrapper_episode"],
                "variant_seed": result["variant_seed"],
                "env_seed": result["env_seed"],
                "difficulty": result["difficulty"],
                "slot_pairs": result["slot_pairs"],
                "bin_pairs": result["bin_pairs"],
                "signature": result["signature"],
                "event_slots": result["event_slots"],
                "topo_class": result["topo_class"],
                "net_permutation": result["net_permutation"],
                "is_original": result["is_original"],
                "n_timesteps": result["n_timesteps"],
                "demo_prefix": result["demo_prefix"],
                "exec_len": result["exec_len"],
                "min_clearance": result["min_clearance"],
                "bystander_net_max": result["bystander_net_max"],
                "bystander_path_max": result["bystander_path_max"],
                "disturbed_bins": result["disturbed_bins"],
                "contacts": result.get("contacts"),
                "geometry": result["geometry"],
                "buttons": result["fingerprint"].get("buttons"),
                "attempt": result["attempt"],
                "last_env_step": result.get("last_env_step"),
                "h5_path": result["h5_path"],
                "intended_use": "eval-only",
            }
        )
    for key, count in expected.items():
        actual = sum(
            1
            for item in manifest
            if (item["task"], item["src_episode"]) == key
        )
        if actual != count:
            gate_failures.append(f"{key[0]}/ep{key[1]}: 成功 {actual} 条，期望 {count} 条")
        if original_counts.get(key, 0) != 1:
            gate_failures.append(
                f"{key[0]}/ep{key[1]}: is_original 数为 {original_counts.get(key, 0)}，应恰为 1"
            )
        # ★ 宗旨闸门：同源全部变体的窗口 ≥2 槽位对必须唯一
        if len(tail_slots.get(key, set())) > 1:
            gate_failures.append(
                f"{key[0]}/ep{key[1]}: 窗口 ≥2 的槽位对出现 {len(tail_slots[key])} 种，应恒为 1 种"
            )

    (output / "clips_manifest.json").write_text(
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
        "success_count_total": len(manifest),
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
        print(f"ERROR: {len(exhausted)} 条 clip 用尽 attempt", file=sys.stderr)
        return 1
    if gate_failures:
        print("ERROR: 事后闸门未过：", file=sys.stderr)
        for line in gate_failures:
            print(f"  {line}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
