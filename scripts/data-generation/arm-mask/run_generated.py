#!/usr/bin/env python3
"""模式②编排：同 seed 重新生成 → 产 mask → 实测 → 删数据。

一条命令跑完模式②的四步。每步都是独立入口的子进程调用，输出实时透传——编排层不
重新实现任何逻辑，只负责串联与清理。

    生成（gt-data/generate_dataset.py，planner 重新规划，不回放 joint angle）
      → 产 mask（make_mask.py，全程不看 GT）
      → 实测（evaluate.py，读 sidecar + GT，pixel/grid 双口径）
      → 删数据集（用户拍板：跑完即删；--keep-dataset 可保留）

## ⚠ 两点必须知道

- **不含任何 replay**：动作由 planner 重新规划，同 seed 只保证场景初始摆放与官方
  一致，轨迹会不同，**RGB 观察与官方不完全一致**；planner 失败的 episode 会被跳过，
  因此实测样本量可能少于「任务数 × episode 数」，实测 JSON 里如实记录。
- **数据集体量约 60 GB**（16 任务 × 10 ep）。默认跑完即删，只留 sidecar 与实测 JSON。
  删除范围严格限定为本次生成的那个目录，且必须位于 artifacts/ 下。

## 用法（在仓库根）

    uv run --locked python scripts/data-generation/arm-mask/run_generated.py \\
      --episodes 10 --workers 16 --gpus 0,1

    # 保留数据集供换参重跑
    uv run --locked python scripts/data-generation/arm-mask/run_generated.py --keep-dataset
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
GT_DATA_DIR = SCRIPT_DIR.parent / "gt-data"
REPO_ROOT = SCRIPT_DIR.parents[2]

DEFAULT_DATASET_DIR = REPO_ROOT / "artifacts" / "generated" / "gt-train-ep0-9"
DEFAULT_SIDECAR_DIR = SCRIPT_DIR / "outputs" / "arm_grid_mask_generated"
DEFAULT_MASK_JSON = SCRIPT_DIR / "outputs" / "json" / "make_mask_generated.json"
DEFAULT_EVAL_JSON = SCRIPT_DIR / "outputs" / "json" / "generated_eval.json"


def _run(step: str, command: Sequence[str]) -> None:
    """跑一步，输出实时透传；非零退出码立刻中止整条编排。"""
    print(f"\n{'=' * 70}\n[{step}] {' '.join(command)}\n{'=' * 70}", flush=True)
    result = subprocess.run(command, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        raise SystemExit(f"[{step}] 失败，退出码 {result.returncode}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="all", help="all 或逗号分隔任务名")
    parser.add_argument("--episodes", type=int, default=10, help="每任务从 ep0 起的条数")
    parser.add_argument("--split", default="train", choices=("train", "val", "test"))
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--gpus", default="0,1")
    parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR))
    parser.add_argument("--sidecar-dir", default=str(DEFAULT_SIDECAR_DIR))
    parser.add_argument("--mask-json", default=str(DEFAULT_MASK_JSON))
    parser.add_argument("--eval-json", default=str(DEFAULT_EVAL_JSON))
    parser.add_argument(
        "--keep-dataset",
        action="store_true",
        help="跑完保留生成的数据集（约 60 GB）；默认删除",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="跳过生成，直接对已存在的 --dataset-dir 产 mask 并实测（隐含保留数据集）",
    )
    args = parser.parse_args(argv)

    dataset_dir = Path(args.dataset_dir)
    episode_range = f"0-{args.episodes - 1}" if args.episodes > 1 else "0"
    python = sys.executable

    if not args.skip_generate:
        _run(
            "1/3 生成带 GT 数据",
            [
                python,
                str(GT_DATA_DIR / "generate_dataset.py"),
                "--output-dir", str(dataset_dir),
                "--env", args.env,
                "--episodes", str(args.episodes),
                "--split", args.split,
                "--workers", str(args.workers),
                "--gpus", args.gpus,
            ],
        )
    elif not dataset_dir.is_dir():
        raise SystemExit(f"--skip-generate 要求 --dataset-dir 已存在：{dataset_dir}")

    _run(
        "2/3 产 mask",
        [
            python,
            str(SCRIPT_DIR / "make_mask.py"),
            "--source", str(dataset_dir),
            "--tasks", args.env,
            "--episodes", episode_range,
            "--out-dir", args.sidecar_dir,
            "--json", args.mask_json,
            "--workers", str(args.workers),
            # ⚠ 模式②必须跳过金丝雀，理由有两层：
            # ① 金丝雀是**无 GT 时的替代监测**，而这里数据源带 GT，下一步 evaluate.py 的
            #    刚性红线（误标物体像素恒 0）是严格更强的判据，再跑金丝雀纯属冗余；
            # ② 自生数据本身就是模式①的基线来源，此刻没有基线可比，双判据会退化成纯绝对值
            #    判据，直接误杀 RouteStick（2.19%）与 InsertPeg（0.82%）——它们的高未见率
            #    来自运行时动态创建的路线曲线等，是任务固有属性而非迁移症状。
            "--no-canary",
            "--no-baseline",
        ],
    )

    _run(
        "3/3 实测（pixel + grid 双口径）",
        [
            python,
            str(SCRIPT_DIR / "evaluate.py"),
            "--sidecar-dir", args.sidecar_dir,
            "--source", str(dataset_dir),
            "--tasks", args.env,
            "--episodes", episode_range,
            "--workers", str(args.workers),
            "--json", args.eval_json,
        ],
    )

    if args.keep_dataset or args.skip_generate:
        print(f"\n数据集保留在 {dataset_dir}")
    else:
        # 只删本次生成的目录，且必须落在 artifacts/ 下——防手滑传进别的路径
        resolved = dataset_dir.resolve()
        artifacts = (REPO_ROOT / "artifacts").resolve()
        if artifacts not in resolved.parents:
            raise SystemExit(f"拒绝删除 artifacts/ 之外的目录：{resolved}")
        size_gb = sum(f.stat().st_size for f in resolved.rglob("*") if f.is_file()) / 1e9
        shutil.rmtree(resolved)
        print(f"\n数据集已删除（回收约 {size_gb:.1f} GB）：{resolved}")

    print(f"\n保留产物：\n  sidecar  {args.sidecar_dir}\n  实测 JSON {args.eval_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
