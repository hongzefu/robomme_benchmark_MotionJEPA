#!/usr/bin/env python3
"""V4 本机演示探针：按给定难度（默认 xhard）跑若干 seed 的完整演示，报 reset 级与演示级成败。

用途：步 3b 实施中快速看「某环境 xhard 能不能真生成成功」（口径 14 的两级判据：reset 级＋演示级），
以及 G3 / V6 前期的小样本摸底。它**直接调用主入口 ``generate_dataset_newseed._worker``**，
gym.make 参数、录像器、规划器、失败分类都与正式生成逐字相同；只是不走进程池、不做 seed 重试。

⚠ 本机（sm_89）结果只用于调试，不进判据（口径 10）；正式的 V4f / V6 在 A40 上跑。

    uv run --no-sync python -m scripts.parity.v4_demo_probe --task PickXtimes --n 4 \
        --out artifacts/newtask-v4/demo-probe/pickx-01
    # 用外部配置收窄 xhard 范围（守卫只允许改已申报的 xhard 条目）：
    uv run --no-sync python -m scripts.parity.v4_demo_probe --task MoveCube --n 4 \
        --sampling-config my_cfg.json --out ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import generate_dataset_newseed as gen  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", required=True)
    parser.add_argument("--difficulty", default="xhard")
    parser.add_argument("--n", type=int, default=3, help="跑几个 seed")
    parser.add_argument("--seed-base", type=int, default=910000, help="第 i 条用 seed-base + 101*i")
    parser.add_argument("--seeds", default=None, help="显式 seed 列表（逗号分隔），给了就忽略 --n/--seed-base")
    parser.add_argument("--episode", type=int, default=9, help="episode 号只决定 recovery 分档：≤2 z，≤5 xy，其余无")
    parser.add_argument("--sampling-config", default=None, help="单任务 {decision, native} JSON，用于收窄 xhard 范围")
    parser.add_argument("--gpu", default=os.environ.get("CUDA_VISIBLE_DEVICES", "0"))
    parser.add_argument("--out", required=True, help="仓库内输出目录（h5/视频/summary.jsonl）")
    args = parser.parse_args()

    gen._pool_init(args.gpu, None, str(REPO_ROOT / "src"))
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sampling = json.loads(Path(args.sampling_config).read_text(encoding="utf-8")) if args.sampling_config else None
    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else [args.seed_base + 101 * i for i in range(args.n)]
    summary_path = out / "summary.jsonl"
    ok = 0
    by_class: dict[str, int] = {}
    for index, seed in enumerate(seeds):
        job = gen.EpisodeJob(
            task=args.task, episode=args.episode, attempt=0, seed=seed, difficulty=args.difficulty,
            output_root=str(out), repo_root=str(REPO_ROOT), sampling_config=sampling,
        )
        started = time.time()
        result = gen._worker(job)
        wall = time.time() - started
        row = {
            "task": args.task, "seed": seed, "difficulty": args.difficulty, "ok": bool(result.get("ok")),
            "failure_class": result.get("failure_class"), "error_type": result.get("error_type"),
            "error": (result.get("error") or "")[:500], "wall_s": round(wall, 1),
            "timesteps": result.get("timesteps") or result.get("timestep_count"),
        }
        with summary_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        ok += row["ok"]
        if not row["ok"]:
            key = f"{row['failure_class']}:{row['error_type']}"
            by_class[key] = by_class.get(key, 0) + 1
        print(f"[{index + 1}/{len(seeds)}] {args.task} seed={seed} ok={row['ok']} "
              f"{row['error_type'] or ''} {row['error'][:160]} {wall:.0f}s", flush=True)
    print(f"DEMO_PROBE task={args.task} difficulty={args.difficulty} ok={ok}/{len(seeds)} by_class={by_class}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
