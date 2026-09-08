#!/usr/bin/env python3
"""主生成入口：对每个入选源（split × episode × env）枚举第一次 swap 的最近邻可达对
（每源 2~3 个），各产一条 110 帧 clip。源范围 = train ep90-99 + test/val ep0-49 三 split。

前置：必须先跑 `probe_original.py`（Phase 0）—— 窗口 ≥2 的固定槽位对与布局基线都
依赖它的 `original_index.json`（且必须是带 split 字段的新版索引）。

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
DATA_DIR = SCRIPT_DIR.parents[1] / SCRIPT_DIR.name
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from clip_plan import (  # noqa: E402
    CLIP_END,
    CLIP_LEN,
    CLIP_START,
    EVAL_TASKS,
    REPO_ROOT,
    SPLIT_CODE,
    add_source_selection_args,
    nearest_neighbor_pairs,
    parse_source_selection,
    select_sources,
    variant_specs,
)
from clip_worker import ClipJob, run_jobs  # noqa: E402

# 断点续跑与闸门对账的统一键形：(task, split, src_episode, variant_idx)
ResumeKey = tuple[str, str, int, int]


def _scan_jsonl(path: Path) -> tuple[dict[ResumeKey, dict], dict[ResumeKey, int]]:
    """扫描既有 JSONL：已成功的 clip（按 key 去重、保留最后一条）与各自的失败 attempt 数。

    支持断点续跑：已成功且产物还在的直接跳过。
    ⚠ 旧版（无 split 字段）记录的 key 里 split 为 None，与任何新键都不相等 ——
    等于被静默忽略。全量重生成前应删掉旧 clip_results.jsonl，避免新旧账混在一个文件里。
    """
    ok: dict[ResumeKey, dict] = {}
    fails: dict[ResumeKey, int] = {}
    if not path.is_file():
        return ok, fails
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            key = (
                record["task"],
                record.get("split"),
                record["src_episode"],
                record["variant_idx"],
            )
            if record.get("ok"):
                ok[key] = record
            else:
                fails[key] = fails.get(key, 0) + 1
    return ok, fails


def _load_original_index(path: Path) -> dict[tuple[str, str, int], dict]:
    """{(split, task, episode): record}。旧版（无 split 字段）索引直接 fail-loud。"""
    if not path.is_file():
        raise SystemExit(f"ERROR: 找不到 {path} —— 必须先跑 probe_original.py（Phase 0）")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("gate_failures") or payload.get("exhausted"):
        raise SystemExit(
            f"ERROR: {path} 里 Phase 0 未全绿（gate_failures="
            f"{payload.get('gate_failures')}），先解决红线再生成"
        )
    missing_split = [
        f"{record['task']}/ep{record['episode']}"
        for record in payload["records"]
        if not record.get("split")
    ]
    if missing_split:
        raise SystemExit(
            f"ERROR: {path} 是旧版索引（{len(missing_split)} 条记录无 split 字段，如 "
            f"{missing_split[0]}）—— 请重跑 probe_original.py 生成带 split 的新版索引"
        )
    return {
        (record["split"], record["task"], int(record["episode"])): record
        for record in payload["records"]
    }


def _parse_only_sources(raw: str | None, splits: tuple[str, ...]) -> set[tuple[str, int]] | None:
    """--only-sources 记法：`split:ep` 指定某 split 的某源；裸 `ep` 表示所有选中 split 的该源。"""
    if not raw:
        return None
    out: set[tuple[str, int]] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            split, episode = token.split(":", 1)
            if split not in SPLIT_CODE:
                raise SystemExit(f"ERROR: --only-sources 里未知 split：{split!r}")
            out.add((split, int(episode)))
        else:
            for split in splits:
                out.add((split, int(token)))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成单事件 swap clip 数据集")
    parser.add_argument("--output-dir", default=str(DATA_DIR / "outputs" / "event1"))
    parser.add_argument("--tasks", default=",".join(EVAL_TASKS))
    add_source_selection_args(parser)
    parser.add_argument(
        "--only-sources",
        default=None,
        help="调试用：只跑这些源，记法 `split:ep`（如 test:3,val:3）；裸 `ep` = 全部选中 split 的该源",
    )
    parser.add_argument(
        "--original-index", default=str(DATA_DIR / "outputs" / "phase0" / "original_index.json")
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
    splits, episodes_by_split = parse_source_selection(args)
    gpu_ids = tuple(item.strip() for item in args.gpus.split(",") if item.strip())
    only = _parse_only_sources(args.only_sources, splits)
    originals = _load_original_index(Path(args.original_index))
    selected = select_sources(tasks, splits, episodes_by_split)

    prior_ok, prior_fails = _scan_jsonl(output / "clip_results.jsonl")

    jobs: list[ClipJob] = []
    baseline: dict[tuple[str, str, int], dict] = {}
    legal_pairs: dict[tuple[str, str, int], list[tuple[int, int]]] = {}
    expected: dict[tuple[str, str, int], int] = {}
    seen_variant_seeds: dict[int, str] = {}
    seen_stagings: dict[tuple[str, int], str] = {}
    skipped = 0
    for task in tasks:
        for src in selected[task]:
            if only is not None and (src.split, src.episode) not in only:
                continue
            label = f"{task}/{src.split}/ep{src.episode}"
            key = (task, src.split, src.episode)
            if (src.split, task, src.episode) not in originals:
                print(f"ERROR: Phase 0 没覆盖 {label}", file=sys.stderr)
                return 1
            record = originals[(src.split, task, src.episode)]
            if record["num_bins_actual"] != src.num_bins:
                print(
                    f"ERROR: {label} 实测 bin 数 {record['num_bins_actual']} "
                    f"≠ 配置 {src.num_bins}，枚举空间不成立",
                    file=sys.stderr,
                )
                return 1
            baseline[key] = record["fingerprint"]
            slot_xy = (record.get("geometry") or {}).get("slot_xy")
            if not slot_xy:
                print(
                    f"ERROR: {label} 的 Phase 0 记录缺 geometry.slot_xy，"
                    "算不出最近邻合法对 —— 请重跑 probe_original.py",
                    file=sys.stderr,
                )
                return 1
            original_bin_pairs = tuple(tuple(pair) for pair in record["original_bin_pairs"])
            specs = variant_specs(src, original_bin_pairs, slot_xy)
            legal_pairs[key] = nearest_neighbor_pairs(slot_xy)
            # 交叉校验：纯函数层（clip_plan）与运行期几何层（swap_inject.slot_geometry）
            # 是两条独立的计算路径，这里把它们锁在一起。旧版 Phase 0 索引没有这个键，跳过。
            recorded = (record.get("geometry") or {}).get("legal_event_pairs")
            if recorded is not None:
                if [list(pair) for pair in legal_pairs[key]] != [list(p) for p in recorded]:
                    print(
                        f"ERROR: {label} 的最近邻合法对两条路径算出不同结果："
                        f"clip_plan={legal_pairs[key]} vs Phase 0 索引={recorded}",
                        file=sys.stderr,
                    )
                    return 1
            expected[key] = len(specs)
            for spec in specs:
                # ★ 唯一性闸门（入队前）：variant_seed 不编码 split，唯一性靠三个 split 的
                # env_seed 数值域不相交 —— 必须逐条断言，不能默认成立（跨任务也全局唯一，
                # 因为两任务 env_seed 数值域本就不同）。staging_episode 是**按任务**的
                # 命名空间（h5 文件名带 task），只在 task 内查重。
                spec_label = f"{label}/var{spec.variant_idx}"
                for value, seen, name in (
                    (spec.variant_seed, seen_variant_seeds, "variant_seed"),
                    ((task, spec.staging_episode), seen_stagings, "staging_episode"),
                ):
                    if value in seen:
                        print(
                            f"ERROR: {name} 碰撞：{spec_label} 与 {seen[value]} 同为 {value}",
                            file=sys.stderr,
                        )
                        return 1
                    seen[value] = spec_label
                variant_key = (task, src.split, src.episode, spec.variant_idx)
                prior = prior_ok.get(variant_key)
                if prior is not None and Path(prior["h5_path"]).is_file():
                    skipped += 1
                    continue
                jobs.append(
                    ClipJob(
                        task=task,
                        split=src.split,
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
        "splits": list(splits),
        "selected_episodes": {
            task: {
                split: [src.episode for src in selected[task] if src.split == split]
                for split in splits
            }
            for task in tasks
        },
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
    original_counts: dict[tuple[str, str, int], int] = {}
    tail_slots: dict[tuple[str, str, int], set] = {}
    event_slots_seen: dict[tuple[str, str, int], list[tuple[int, int]]] = {}
    manifest = []
    for result in sorted(
        all_ok.values(),
        key=lambda item: (
            item["task"],
            SPLIT_CODE.get(item.get("split"), 99),
            item["src_episode"],
            item["variant_idx"],
        ),
    ):
        key = (result["task"], result.get("split"), result["src_episode"])
        if key not in baseline:
            continue  # 本次未覆盖的源（--only-sources 调试、旧版无 split 记录）不参与闸门
        result_label = (
            f"{result['task']}/{result['split']}/ep{result['src_episode']}/var{result['variant_idx']}"
        )
        if result["fingerprint"] != baseline[key]:
            gate_failures.append(f"{result_label}: 布局指纹与 Phase 0 基线不符")
        if result["is_original"] == 1:
            original_counts[key] = original_counts.get(key, 0) + 1
        tail_slots.setdefault(key, set()).add(
            tuple(tuple(pair) for pair in result["slot_pairs"][1:])
        )
        event_slots_seen.setdefault(key, []).append(tuple(result["event_slots"]))
        manifest.append(
            {
                "task": result["task"],
                "split": result["split"],
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
        key_label = f"{key[0]}/{key[1]}/ep{key[2]}"
        actual = sum(
            1
            for item in manifest
            if (item["task"], item["split"], item["src_episode"]) == key
        )
        if actual != count:
            gate_failures.append(f"{key_label}: 成功 {actual} 条，期望 {count} 条")
        # ★ 最近邻闸门：实测事件槽位对集合必须恰等于该源的合法对集合（不多不少、无重复）
        seen = sorted(event_slots_seen.get(key, []))
        if seen != legal_pairs.get(key, []):
            gate_failures.append(
                f"{key_label}: 事件槽位对集合 {seen} ≠ 最近邻合法集合 {legal_pairs.get(key)}"
            )
        if original_counts.get(key, 0) != 1:
            gate_failures.append(
                f"{key_label}: is_original 数为 {original_counts.get(key, 0)}，应恰为 1"
            )
        # ★ 宗旨闸门：同源全部变体的窗口 ≥2 槽位对必须唯一
        if len(tail_slots.get(key, set())) > 1:
            gate_failures.append(
                f"{key_label}: 窗口 ≥2 的槽位对出现 {len(tail_slots[key])} 种，应恒为 1 种"
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
