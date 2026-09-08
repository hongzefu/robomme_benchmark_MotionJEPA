"""严格回放 ICL HDF5，并保存回放 HDF5 和双相机 MP4。"""

import argparse
from pathlib import Path

from _icl.common import add_execution_options, run_phase, safe_output


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="单个 ICL HDF5、数据目录或整批输出根")
    parser.add_argument("--output-dir", type=Path, required=True, help="独立回放输出根，不能覆盖输入")
    add_execution_options(parser, video=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    from _icl.workflow import check_replay_destinations, discover_inputs, export_videos, replay_records, replay_scan_root, validate_bindings

    output = safe_output(args.output_dir)
    scan_root = replay_scan_root(args.input)
    check_replay_destinations([], output, scan_root=scan_root)
    rows = discover_inputs(args.input, tasks=args.tasks, episodes_per_task=args.episodes_per_task)
    check_replay_destinations(rows, output, scan_root=scan_root)
    validate_bindings([row["runtime_fingerprint"] for row in rows])
    identity = {"inputs": [{key: row[key] for key in ("path", "spec_hash", "content_hash", "render_gpu")} for row in rows]}
    execution = {"workers": args.workers, "video_workers": args.video_workers, "timeout_seconds": args.timeout_seconds}
    with run_phase(output, "replay", identity, execution) as (root, result):
        records = replay_records(rows, root, workers=args.workers, timeout_seconds=args.timeout_seconds, scan_root=scan_root)
        result.update(hdf5_count=len(records), records=records)
        videos = export_videos(records, root, workers=args.video_workers)
        result.update(video_count=len(videos), videos=videos)
        print(f"严格回放完成：{len(records)} 条，已保存 {len(videos)} 个 MP4；目录 {root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
