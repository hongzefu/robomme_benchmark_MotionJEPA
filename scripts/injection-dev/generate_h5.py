#!/usr/bin/env python3
"""第二阶段入口：只读 jsonl → 生成 h5 → 按状态机回写（0927 计划第一部分 §5.2）。

    # 正常生产：跑每格 selected 且未生成的行，失败递补，结束持锁回写 --specs
    uv run --no-sync python scripts/injection-dev/generate_h5.py --mode continue \
        --specs <specs.jsonl> --output <输出目录> --workers 16 --gpu 0
    # 对拍专用：按身份清单只读重放，不递补、不回写（默认读包内四档 jsonl）
    uv run --no-sync python scripts/injection-dev/generate_h5.py --mode replay \
        --identities artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json --output <输出目录>

- ``--redo TASK:CANDIDATE,...``：continue 模式下显式重跑这些身份（已 ok 的行默认不重跑）。
- ``--resume``：沿用已有 ``--output`` 续跑；有 h5 却无 partial 记录的身份标 UNKNOWN 并停止。
- ``--self-check``：continue 跑完后核 ``identity_sha256`` 未变 → ``ROLLBACK_WRITE``。
- 环境包由 ``--pkg``（默认 robomme_hard）经 ``ROBOMME_ENV_PACKAGE`` 传给 worker。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import _common  # noqa: F401  路径设置
import _rollout  # noqa: E402

from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402


def _launch_facts(src_root: Path) -> dict[str, str]:
    """GPU 型号、驱动、src_commit、节点与作业号（写进 launch 记录，gen1／gen2 比对前核对同型号同驱动）。"""
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip().splitlines()
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if out and visible and visible.isdigit() and int(visible) < len(out):
        out = [out[int(visible)]]
    name, driver = (out[0].split(",")[0].strip(), out[0].split(",")[1].strip()) if out else ("unknown", "unknown")
    commit = subprocess.run(["git", "-C", str(src_root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return {"gpu_model": name, "driver": driver, "src_commit": commit or "unknown", "host": os.uname().nodename,
            "slurm_job": os.environ.get("SLURM_JOB_ID")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", required=True, choices=("continue", "replay"))
    parser.add_argument("--specs", default=None, help="continue 模式必填；replay 模式缺省读包内四档")
    parser.add_argument("--identities", default=None, help="replay 模式的身份清单（final-delivery.json 或 jsonl）")
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--pkg", default="robomme_hard", choices=("robomme", "robomme_hard"))
    parser.add_argument("--src-root", default=str(_common.REPO_ROOT))
    parser.add_argument("--redo", default="")
    parser.add_argument("--tasks", default="all", help="continue 模式只跑这些任务（逗号分隔）；其余任务的待跑行留到下次")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--dev-smoke", action="store_true", help="放行非 A40（本机开发冒烟）；正式生成一律 A40（v7 D-9）")
    args = parser.parse_args()

    output = Path(args.output)
    src_root = Path(args.src_root).resolve()
    facts = _launch_facts(src_root)
    if not args.dev_smoke and "A40" not in facts["gpu_model"]:
        raise SystemExit(f"正式生成只许在 A40 上跑：当前 {facts}")
    output.mkdir(parents=True, exist_ok=True)
    (output / f"launch-{int(time.time())}.json").write_text(json.dumps(
        {"schema": "generate-h5-launch/1", "mode": args.mode, "specs": args.specs, "identities": args.identities,
         "workers": args.workers, "gpu": args.gpu, "pkg": args.pkg, "dev_smoke": args.dev_smoke, **facts},
        ensure_ascii=False, indent=2) + "\n")
    specs_dir = Path(args.specs) if args.specs and Path(args.specs).is_dir() else None
    if args.mode == "replay":
        if not args.identities:
            raise SystemExit("replay 模式必须给 --identities")
        specs_paths = None
        if specs_dir is not None:
            # v7：规格根目录（xhard{1..4}/specs.jsonl，gen2 按 gen1 交付清单重放）
            hard_specs.load_specs_v7(specs_dir, check_fingerprint=False)
            specs_paths = {tier: specs_dir / tier / "specs.jsonl" for tier in hard_specs.TIERS}
        elif args.specs:
            header, _ = hard_specs.load_specs(args.specs, check_fingerprint=False)
            specs_paths = {header["difficulty"]: Path(args.specs)}
        summary = _rollout.run_replay(_rollout.load_identities(Path(args.identities)), output, src_root=src_root,
                                      workers=args.workers, gpu=args.gpu, pkg=args.pkg, resume=args.resume,
                                      specs_paths=specs_paths)
        print(f"GENERATE_REPLAY_DONE scheduled={summary['scheduled']} ok={summary['ok']} failed={summary['failed']} "
              f"out={output}")
        return 0
    if not args.specs:
        raise SystemExit("continue 模式必须给 --specs")
    if specs_dir is not None:
        # v7 gen1：候选池四档同步作废与递补，收尾写 delivery.json（V7_DELIVERY_SET）
        summary = _rollout.run_continue_v7(specs_dir, output, src_root=src_root, workers=args.workers, gpu=args.gpu,
                                           pkg=args.pkg, code_baseline=facts["src_commit"], resume=args.resume)
        print(f"GENERATE_CONTINUE_DONE attempted={summary['attempted']} rounds={summary['rounds']} "
              f"infra_retries={summary['infra_retries']} delivered={summary['delivered']} "
              f"sync_dropped={summary['sync_dropped']} backfills={summary['backfills']} out={output}")
        return 0 if summary["delivery_set"].startswith("V7_DELIVERY_SET=PASS") else 1
    specs = Path(args.specs)
    before, _ = hard_specs.load_specs(specs, check_fingerprint=False)
    redo = set()
    for item in filter(None, args.redo.split(",")):
        task, _, cand = item.partition(":")
        redo.add((task, int(cand)))
    code_baseline = subprocess.run(["git", "-C", str(src_root), "rev-parse", "HEAD"], capture_output=True,
                                   text=True).stdout.strip() or "unknown"
    summary = _rollout.run_continue(specs, output, src_root=src_root, workers=args.workers, gpu=args.gpu,
                                    pkg=args.pkg, code_baseline=code_baseline, redo=redo, resume=args.resume,
                                    tasks=None if args.tasks == "all" else set(args.tasks.split(",")))
    print(f"GENERATE_CONTINUE_DONE attempted={summary['attempted']} rounds={summary['rounds']} "
          f"infra_retries={summary['infra_retries']} delivered={summary['delivered']} out={output}")
    if args.self_check:
        after, rows = hard_specs.load_specs(specs, check_fingerprint=False)
        same = after["identity_sha256"] == before["identity_sha256"]
        print(f"ROLLBACK_WRITE={'PASS' if same else 'FAIL'} identity_unchanged={int(same)} "
              f"delivered={sum(hard_specs.delivered(r) for r in rows)}")
        return 0 if same else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
