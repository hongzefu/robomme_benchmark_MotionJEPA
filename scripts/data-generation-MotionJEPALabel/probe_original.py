#!/usr/bin/env python3
"""Phase 0 控制跑：对 2 task × ep90-93 各跑一次**无注入**的完整 rollout。

产出（全部落 --output-dir）：
* `original_index.json` —— 每个源 episode 的原始 pair 序列（is_original 判定的唯一
  正确来源：第 2/3 窗口的 idx2 是运行时按前次交换后的位置取最近邻，静态算不出）、
  布局指纹基线、实测 bin 数、段长基线；
* 控制跑的 h5（含 swap_gt 标注）/ 视频 / trace，供后续变体对拍；
* 与官方 `/data/hongzefu/robomme_data_h5` 的逐元素 joint_action 比对结果。

红线：任一控制跑失败、或与官方 h5 数值比对超过 --joint-action-tol，退出码非零，
不得进入后续 Phase。
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

from variant_plan import (  # noqa: E402
    DEFAULT_SRC_EPISODES,
    EVAL_TASKS,
    REPO_ROOT,
    source_episode,
)
from variant_worker import (  # noqa: E402
    VariantJob,
    _segment_lengths,
    _sorted_timesteps,
    run_jobs,
)


def _compare_with_official(
    ours_path: Path, episode: int, official_dir: Path, task: str
) -> dict:
    """逐 timestep 逐元素比对 action/joint_action，并对拍段长。"""
    official_path = official_dir / f"record_dataset_{task}.h5"
    if not official_path.is_file():
        return {"available": False, "reason": f"官方 h5 不存在：{official_path}"}
    with h5py.File(ours_path, "r") as ours, h5py.File(official_path, "r") as official:
        name = f"episode_{episode}"
        if name not in official:
            return {"available": False, "reason": f"官方 h5 缺 {name}"}
        group_ours, group_off = ours[name], official[name]
        ts_ours = _sorted_timesteps(group_ours)
        ts_off = _sorted_timesteps(group_off)
        result: dict = {
            "available": True,
            "T_ours": len(ts_ours),
            "T_official": len(ts_off),
            "T_equal": len(ts_ours) == len(ts_off),
        }
        seg_ours = _segment_lengths(group_ours)
        seg_off = _segment_lengths(group_off)
        result["segments_ours"] = {"T": seg_ours[0], "demo_prefix": seg_ours[1], "exec_len": seg_ours[2]}
        result["segments_official"] = {"T": seg_off[0], "demo_prefix": seg_off[1], "exec_len": seg_off[2]}
        result["segments_equal"] = seg_ours == seg_off
        if not result["T_equal"]:
            return result
        max_diff = 0.0
        for name_ts in ts_ours:
            a = np.asarray(group_ours[name_ts]["action"]["joint_action"], dtype=np.float64)
            b = np.asarray(group_off[name_ts]["action"]["joint_action"], dtype=np.float64)
            if a.shape != b.shape:
                result["shape_mismatch_at"] = name_ts
                return result
            max_diff = max(max_diff, float(np.max(np.abs(a - b))))
        result["joint_action_max_abs_diff"] = max_diff
        return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Phase 0 控制跑：拿原始 swap 序列与布局基线")
    parser.add_argument("--output-dir", default=str(SCRIPT_DIR / "outputs" / "phase0"))
    parser.add_argument("--tasks", default=",".join(EVAL_TASKS))
    parser.add_argument(
        "--episodes", default=",".join(str(item) for item in DEFAULT_SRC_EPISODES)
    )
    parser.add_argument("--gpus", default="1", help="逗号分隔的物理卡号")
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

    jobs = []
    for task in tasks:
        for episode in episodes:
            src = source_episode(task, episode)
            jobs.append(
                VariantJob(
                    task=task,
                    src_episode=episode,
                    variant_idx=-1,
                    env_seed=src.env_seed,
                    variant_seed=src.env_seed,
                    wrapper_episode=episode,
                    difficulty=src.difficulty,
                    num_bins=src.num_bins,
                    pairs=None,
                    original_pairs=None,
                    attempt=0,
                    output_root=str(output),
                    repo_root=str(REPO_ROOT),
                )
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
        records.append(
            {
                "task": result["task"],
                "episode": result["src_episode"],
                "env_seed": result["env_seed"],
                "difficulty": result["difficulty"],
                "num_bins_actual": len(result["fingerprint"]["bins"]),
                "swap_times": len(result["pairs"]),
                "original_pairs": result["pairs"],
                "signature": result["signature"],
                "n_timesteps": result["n_timesteps"],
                "demo_prefix": result["demo_prefix"],
                "exec_len": result["exec_len"],
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
        "requested": len(jobs),
        "succeeded": len(succeeded),
        "exhausted": len(exhausted),
        "joint_action_tol": args.joint_action_tol,
        "gate_failures": gate_failures,
        "records": records,
    }
    index_path = output / "original_index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n控制跑 {len(succeeded)}/{len(jobs)} 成功，耗时 {elapsed:.1f}s")
    for record in records:
        comparison = record["official_comparison"]
        diff = comparison.get("joint_action_max_abs_diff")
        print(
            f"  {record['task']}/ep{record['episode']}: pairs={record['signature']}"
            f"  T={record['n_timesteps']} demo={record['demo_prefix']} exec={record['exec_len']}"
            f"  官方比对 max_diff={diff if diff is not None else 'N/A'}"
        )
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
