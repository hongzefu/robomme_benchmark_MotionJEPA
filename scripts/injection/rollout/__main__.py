"""实跑阶段：独立候选副本、恢复、HDF5、一次 reset、图表和报告。"""
from __future__ import annotations

import argparse
from pathlib import Path

from .state import ROOT, RunStore, StateError, file_sha, import_candidates, run_root, write_json
from .run import invoke_generator, recover
from .reset_check import run_reset
from .report import report


def execute(args):
    root = run_root(args.run_id)
    target = root / "candidates/candidates.jsonl"
    source = Path(args.candidates).resolve() if args.candidates else None
    source_sha = None
    if source and source != target.resolve():
        source_sha = file_sha(source)
        import_candidates(source, target, args.run_id)
    if not target.exists():
        raise StateError("缺少 candidates.jsonl，请先生成或显式导入")
    if args.tier < 1:
        raise StateError("tier 必须为正")
    label = args.label or ("smoke" if args.purpose == "smoke" else None)
    store = RunStore(root, label)
    with store.locked():
        recover(store)
        write_json(store.logs / "run_parameters.json", vars(args))
        invocation = invoke_generator(store, groups=args.groups, episodes=args.episodes, gpus=args.gpus,
                                      tier=args.tier, wall_limit_h=args.wall_limit_h, episode_range=args.episode_range)
        reset = run_reset(store, groups=args.groups, gpus=args.gpus, tier=args.tier,
                          limit=args.reset_limit, purpose=args.purpose)
        if not args.no_figures:
            from .windows import generate_windows
            generate_windows(store)
        result = report(store, args.purpose)
        if source_sha is not None:
            intact = source_sha == file_sha(source)
            write_json(store.logs / "source_integrity.json", {"source": str(source), "before": source_sha,
                                                              "after": file_sha(source), "passed": intact})
            if not intact:
                raise StateError("独立对拍改变了源候选")
            print("PARITY_SOURCE_INTACT=PASS", flush=True)
        print(f"RUN=PASS purpose={args.purpose} h5_executed={invocation['executed']} reset_executed={reset['executed']}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidates")
    parser.add_argument("--purpose", choices=("delivery", "parity", "smoke"), default="delivery")
    parser.add_argument("--groups", nargs="+")
    parser.add_argument("--episodes", type=int)
    parser.add_argument("--episode-range")
    parser.add_argument("--skip-done", action="store_true", help="终态始终复用，此参数显式表达续跑意图")
    parser.add_argument("--wall-limit-h", type=float, default=0)
    parser.add_argument("--tier", type=int, default=20)
    parser.add_argument("--gpus", default="0,1")
    parser.add_argument("--reset-limit", type=int)
    parser.add_argument("--label")
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args()
    execute(args)


if __name__ == "__main__":
    main()
