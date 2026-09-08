"""从认证清单生成逐 episode HDF5、双相机 MP4 和实际分布图。"""

import argparse
from pathlib import Path

from _icl.common import add_execution_options, run_phase, safe_output, select_specs


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    add_execution_options(parser, video=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    from robomme_icl.suite import load_suite, save_suite
    from _icl.workflow import check_generation_suite, export_videos, generate_records, validate_bindings
    from _icl.plots import plot_distributions

    suite = load_suite(args.suite)
    specs = select_specs(suite, args.tasks, args.episodes_per_task)
    check_generation_suite(suite, args.output_dir)
    validate_bindings([suite["certification"][spec.spec_hash]["runtime_fingerprint"] for spec in specs])
    identity = {"suite_hash": suite["suite_hash"], "spec_hashes": [spec.spec_hash for spec in specs]}
    execution = {"workers": args.workers, "video_workers": args.video_workers, "timeout_seconds": args.timeout_seconds}
    with run_phase(safe_output(args.output_dir), "generate", identity, execution) as (root, result):
        records = generate_records(suite, specs, root, workers=args.workers, timeout_seconds=args.timeout_seconds)
        result.update(hdf5_count=len(records), records=records)
        videos = export_videos(records, root, workers=args.video_workers)
        result.update(video_count=len(videos), videos=videos)
        selected_path = args.suite
        if len(specs) != len(suite["episodes"]):
            selected_path = root / "selection/suite.json"
            selected_cert = {spec.spec_hash: suite["certification"][spec.spec_hash] for spec in specs}
            if selected_path.exists():
                selected = load_suite(selected_path)
                if (selected["episodes"] != [spec.to_dict() for spec in specs]
                        or selected["certification"] != selected_cert or selected["configs"] != suite["configs"]):
                    raise ValueError("已有绘图清单与本次生成选择不同")
            else:
                selected_path.parent.mkdir(parents=True, exist_ok=True)
                save_suite(selected_path, specs, (suite["configs"]["task"], suite["configs"]["position"]), selected_cert)
        result["distributions"] = plot_distributions(selected_path, root / "distributions")
        print(f"生成完成：{len(records)} 个 HDF5、{len(videos)} 个 MP4；目录 {root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
