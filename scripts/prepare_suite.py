"""生成并认证 ICL 环境清单，或按原冻结规格重新认证入口迁移后的版本。"""

import argparse
from pathlib import Path

from _icl.common import add_execution_options, gpu_list, run_phase, safe_output, select_specs


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-config", type=Path)
    parser.add_argument("--position-config", type=Path)
    parser.add_argument("--source-suite", type=Path, help="按现有冻结 spec 重新认证，不重选位置、次数或 seed")
    parser.add_argument("--output-dir", type=Path, required=True, help="整批输出根；清单保存到其中的 suite/")
    parser.add_argument("--gpus", type=gpu_list, help="新配置模式默认0,1；源套件模式不允许改绑定")
    parser.add_argument("--max-candidates", type=int)
    add_execution_options(parser)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.source_suite and (args.task_config or args.position_config or args.max_candidates is not None):
        parser.error("source-suite 不能与重新编译配置或候选上限同时使用")
    if args.max_candidates is not None and args.max_candidates < 1:
        parser.error("max-candidates 必须大于零")
    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    from robomme_icl.suite import load_configs, load_suite
    from _icl.workflow import validate_bindings

    output = safe_output(args.output_dir)
    if args.source_suite:
        source = load_suite(args.source_suite)
        specs = select_specs(source, args.tasks, args.episodes_per_task)
        source_gpus = sorted({row["render_gpu"] for row in source["certification"].values()})
        if args.gpus is not None and args.gpus != source_gpus:
            parser.error("源套件模式不能重新分配物理 GPU")
        identity = {"source_suite_hash": source["suite_hash"], "spec_hashes": [spec.spec_hash for spec in specs]}
    else:
        configs = load_configs(args.task_config, args.position_config)
        identity = {"configs": configs, "tasks": args.tasks, "episodes_per_task": args.episodes_per_task,
                    "gpus": args.gpus or [0, 1]}
    execution = {"workers": args.workers, "timeout_seconds": args.timeout_seconds}
    with run_phase(output, "prepare", identity, execution) as (root, result):
        if args.source_suite:
            from _icl.recertify import recertify_suite
            manifest = recertify_suite(args.source_suite, root / "suite", workers=args.workers,
                                       timeout_seconds=args.timeout_seconds, tasks=args.tasks,
                                       episodes_per_task=args.episodes_per_task)
        elif (root / "suite/suite.json").exists():
            manifest = root / "suite/suite.json"
            existing = load_suite(manifest)
            from robomme_icl.suite import candidate_for_slot, plan_slots
            from robomme_icl.io.hdf5 import assert_identical
            assert_identical({"task": configs[0], "position": configs[1]}, existing["configs"], path="已有清单配置")
            slots = plan_slots(*configs, tasks=args.tasks, episodes_per_task=args.episodes_per_task)
            if len(slots) != len(existing["episodes"]):
                raise ValueError("已有清单条数与当前配额不同")
            for slot, stored in zip(slots, existing["episodes"]):
                candidate = existing["certification"][stored["spec_hash"]]["candidate_index"]
                assert_identical(candidate_for_slot(slot, candidate).to_dict(), stored, path="已有冻结候选")
            validate_bindings([row["runtime_fingerprint"] for row in existing["certification"].values()])
        else:
            from robomme_icl.io.pipeline import prepare_suite
            manifest = prepare_suite(root / "suite", task_config=args.task_config,
                                     position_config=args.position_config, tasks=args.tasks,
                                     episodes_per_task=args.episodes_per_task, workers=args.workers,
                                     max_candidates=args.max_candidates, timeout_seconds=args.timeout_seconds,
                                     gpus=args.gpus or [0, 1])
        suite = load_suite(manifest)
        result.update(suite=str(manifest), suite_hash=suite["suite_hash"], episodes=len(suite["episodes"]))
        print(f"清单已保存：{manifest}；共 {len(suite['episodes'])} 条", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
