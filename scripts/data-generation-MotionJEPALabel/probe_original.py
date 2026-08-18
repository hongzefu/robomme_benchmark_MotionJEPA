#!/usr/bin/env python3
"""Phase 0 控制跑：对入选的 4 源 × 2 env 各跑一次**无注入的完整 rollout**（8 条）。

为什么必须完整跑（而正式产物是截断的）：窗口 2/3 的 `swap_pair{k}_idx2` 是运行时进入
该窗口那一刻按「前次交换后的位置」取最近邻回填的，静态算不出 —— 只能实跑到那一步再
读回。ButtonUnmaskSwap 的 k=3 源（ep91/ep99）第三个窗口到 env step 214 才结束，而截断
点在 press2 结束（~200），够不着。8 条完整跑约 2-3 分钟，不值得为此做特殊截断。

产出（全部落 --output-dir）：

* `original_index.json` —— 每源的原始 bin 对序列与换算出的**原始槽位对序列**
  （窗口 ≥2 固定值之源）、布局指纹基线、槽位几何、按钮位置、子目标边界、段长，
  以及与官方 h5 的 joint_action 比对；
* 控制跑的完整 h5 / 视频 / trace，供后续 clip 对拍。

红线：任一控制跑失败、或与官方 h5 的 joint_action 偏差超过 --joint-action-tol，
退出码非零，不得进入后续 Phase。
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

import h5py  # noqa: E402
import numpy as np  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from clip_plan import (  # noqa: E402
    CANDIDATE_EPISODES,
    CLIP_END,
    CLIP_START,
    EVAL_TASKS,
    REPO_ROOT,
    select_sources,
    signature_of,
    slot_pairs_from_bin_pairs,
)
from clip_worker import (  # noqa: E402
    ClipJob,
    run_jobs,
    segment_lengths,
    sorted_timesteps,
)


def _joint_action(group: h5py.Group, name: str) -> np.ndarray:
    return np.asarray(group[name]["action"]["joint_action"], dtype=np.float64)


def _compare_with_official(ours_path: Path, episode: int, official_dir: Path, task: str) -> dict:
    """逐 timestep 逐元素比对 joint_action（全程 + clip 区间两个口径），并对拍段长。"""
    official_path = official_dir / f"record_dataset_{task}.h5"
    if not official_path.is_file():
        return {"available": False, "reason": f"官方 h5 不存在：{official_path}"}
    with h5py.File(ours_path, "r") as ours, h5py.File(official_path, "r") as official:
        name = f"episode_{episode}"
        if name not in official:
            return {"available": False, "reason": f"官方 h5 缺 {name}"}
        group_ours, group_off = ours[name], official[name]
        ts_ours, ts_off = sorted_timesteps(group_ours), sorted_timesteps(group_off)
        seg_ours, seg_off = segment_lengths(group_ours), segment_lengths(group_off)
        result: dict = {
            "available": True,
            "T_ours": len(ts_ours),
            "T_official": len(ts_off),
            "T_equal": len(ts_ours) == len(ts_off),
            "segments_ours": dict(zip(("T", "demo_prefix", "exec_len"), seg_ours)),
            "segments_official": dict(zip(("T", "demo_prefix", "exec_len"), seg_off)),
            "segments_equal": seg_ours == seg_off,
        }
        if not result["T_equal"]:
            return result
        max_all = 0.0
        max_clip = 0.0
        for name_ts in ts_ours:
            a, b = _joint_action(group_ours, name_ts), _joint_action(group_off, name_ts)
            if a.shape != b.shape:
                result["shape_mismatch_at"] = name_ts
                return result
            diff = float(np.max(np.abs(a - b)))
            max_all = max(max_all, diff)
            if CLIP_START <= int(name_ts.rsplit("_", 1)[1]) < CLIP_END:
                max_clip = max(max_clip, diff)
        result["joint_action_max_abs_diff"] = max_all
        result["joint_action_max_abs_diff_clip"] = max_clip
        return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Phase 0 控制跑：拿原始槽位序列与布局基线")
    parser.add_argument("--output-dir", default=str(SCRIPT_DIR / "outputs" / "phase0"))
    parser.add_argument("--tasks", default=",".join(EVAL_TASKS))
    parser.add_argument(
        "--episodes",
        default=",".join(str(item) for item in CANDIDATE_EPISODES),
        help="候选源 episode（筛选前）；实际用哪些由三重筛选决定",
    )
    parser.add_argument("--gpus", default="0", help="逗号分隔的物理卡号")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--official-h5-dir", default="/data/hongzefu/robomme_data_h5")
    parser.add_argument("--joint-action-tol", type=float, default=1e-6)
    args = parser.parse_args(argv)

    output = Path(args.output_dir).resolve()
    if REPO_ROOT.resolve() not in output.parents:
        print(f"ERROR: 输出目录必须在仓库内：{output}", file=sys.stderr)
        return 1
    output.mkdir(parents=True, exist_ok=True)
    (output / "hdf5_files").mkdir(exist_ok=True)

    tasks = tuple(item.strip() for item in args.tasks.split(",") if item.strip())
    episodes = tuple(int(item) for item in args.episodes.split(",") if item.strip())
    gpu_ids = tuple(item.strip() for item in args.gpus.split(",") if item.strip())

    selected = select_sources(tasks, episodes)
    jobs = []
    for task in tasks:
        for src in selected[task]:
            jobs.append(
                ClipJob(
                    task=task,
                    src_episode=src.episode,
                    variant_idx=-1,
                    env_seed=src.env_seed,
                    variant_seed=src.env_seed,
                    wrapper_episode=src.episode,
                    difficulty=src.difficulty,
                    num_bins=src.num_bins,
                    mode="control",
                    bin_pairs=None,
                    slot_pairs=None,
                    is_original=True,  # 控制跑本身就是原始序列
                    attempt=0,
                    output_root=str(output),
                    repo_root=str(REPO_ROOT),
                )
            )
    if not jobs:
        print("ERROR: 三重筛选后没有任何源 episode", file=sys.stderr)
        return 1
    print(
        f"Phase 0 控制跑 {len(jobs)} 条："
        + "，".join(f"{task} ep{[s.episode for s in selected[task]]}" for task in tasks),
        flush=True,
    )

    started = time.monotonic()
    succeeded, exhausted = run_jobs(
        jobs=jobs,
        gpu_ids=gpu_ids,
        workers=args.workers,
        jsonl_path=output / "episode_results.jsonl",
        max_attempts=args.max_attempts,
    )
    elapsed = time.monotonic() - started

    official_dir = Path(args.official_h5_dir)
    records = []
    gate_failures: list[str] = []
    for result in sorted(succeeded, key=lambda item: (item["task"], item["src_episode"])):
        comparison = _compare_with_official(
            Path(result["h5_path"]), result["src_episode"], official_dir, result["task"]
        )
        label = f"{result['task']}/ep{result['src_episode']}"
        if comparison.get("available"):
            diff = comparison.get("joint_action_max_abs_diff")
            if not comparison["T_equal"]:
                gate_failures.append(
                    f"{label}: 帧数 {comparison['T_ours']} ≠ 官方 {comparison['T_official']}"
                )
            elif diff is None or diff >= args.joint_action_tol:
                gate_failures.append(
                    f"{label}: joint_action 最大偏差 {diff} ≥ 阈值 {args.joint_action_tol}"
                )
        else:
            gate_failures.append(f"{label}: 无法比对官方数据（{comparison.get('reason')}）")

        bin_pairs_seq = [tuple(pair) for pair in result["bin_pairs"]]
        num_bins = len(result["fingerprint"]["bins"])
        slot_pairs = slot_pairs_from_bin_pairs(bin_pairs_seq, num_bins)
        records.append(
            {
                "task": result["task"],
                "episode": result["src_episode"],
                "env_seed": result["env_seed"],
                "difficulty": result["difficulty"],
                "num_bins_actual": num_bins,
                "swap_times": len(bin_pairs_seq),
                # ★ 后续窗口固定值之源：原始 bin 对 → 原始槽位对
                "original_bin_pairs": [list(pair) for pair in bin_pairs_seq],
                "original_slot_pairs": [list(pair) for pair in slot_pairs],
                "signature": signature_of(slot_pairs),
                "n_timesteps": result["n_timesteps"],
                "demo_prefix": result["demo_prefix"],
                "exec_len": result["exec_len"],
                "subgoal_boundaries": result.get("subgoal_boundaries"),
                "buttons": result["fingerprint"].get("buttons"),
                "geometry": result["geometry"],
                "min_clearance": result["min_clearance"],
                "h5_path": result["h5_path"],
                "trace_path": result["trace_path"],
                "fingerprint": result["fingerprint"],
                "official_comparison": comparison,
            }
        )

    index = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(elapsed, 1),
        "clip": {"start": CLIP_START, "end": CLIP_END},
        "requested": len(jobs),
        "succeeded": len(succeeded),
        "exhausted": len(exhausted),
        "joint_action_tol": args.joint_action_tol,
        "gate_failures": gate_failures,
        "records": records,
    }
    index_path = output / "original_index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n控制跑 {len(succeeded)}/{len(jobs)} 成功，耗时 {elapsed:.1f}s")
    for record in records:
        comparison = record["official_comparison"]
        boundaries = record.get("subgoal_boundaries") or []
        print(
            f"  {record['task']}/ep{record['episode']}: "
            f"bin={'|'.join(f'{i}{j}' for i, j in record['original_bin_pairs'])} "
            f"slot={record['signature']}  T={record['n_timesteps']} "
            f"demo={record['demo_prefix']} exec={record['exec_len']}  "
            f"官方 max_diff={comparison.get('joint_action_max_abs_diff')} "
            f"(clip 区间 {comparison.get('joint_action_max_abs_diff_clip')})"
        )
        print("      子目标边界：" + "、".join(f"{b['step']}:{b['subgoal']}" for b in boundaries))
    if exhausted:
        print(f"ERROR: {len(exhausted)} 条控制跑失败，红线触发", file=sys.stderr)
        return 2
    if gate_failures:
        print("ERROR: 官方比对红线触发：", file=sys.stderr)
        for line in gate_failures:
            print(f"  {line}", file=sys.stderr)
        return 2
    print(f"original_index 已写入 {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
