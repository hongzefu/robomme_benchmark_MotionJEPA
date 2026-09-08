"""按认证套件逐局运行固定原版，并保留正常与错误动作的独立证据。"""

from pathlib import Path
import json

from ..io.hdf5 import read_episode, assert_identical
from ..io.fingerprint import runtime_fingerprint
from ..io.paths import output_path
from ..io.suite import load_suite
from ..specs import EpisodeSpec
from ..validation.parity import compare_episodes
from .workers import new_manager, gpu_limits, run_jobs, run_episode_process


def _verify_job(job):
    spec = EpisodeSpec.from_dict(job["spec"])
    directory = Path(job["output"])
    report = directory / "comparison.json"
    reference = directory / "original.h5"
    actual = Path(job["actual"])
    with job["gpu_limit"]:
        if job["probe"] is not None:
            actual = directory / "icl.h5"
            if not actual.exists():
                run_episode_process(
                    spec,
                    actual,
                    render_gpu=job["gpu"],
                    timeout_seconds=job["timeout"],
                    probe=job["probe"],
                )
        record = read_episode(actual)
        assert_identical(spec.to_dict(), record.episode_spec, path="验证输入")
        assert_identical(
            record.runtime_fingerprint,
            runtime_fingerprint(render_gpu=job["gpu"]),
            path="验证运行条件",
        )
        if not reference.exists():
            run_episode_process(
                spec,
                reference,
                render_gpu=job["gpu"],
                timeout_seconds=job["timeout"],
                reference_root=job["reference_root"],
                probe=job["probe"],
            )
    result = compare_episodes(reference, actual, report)
    print(
        f"原版对照通过 {spec.task_kind} seed={spec.seed} probe={job['probe']} operations={result['operations']}",
        flush=True,
    )
    return {key: value for key, value in result.items() if key != "events"}


def verify_suite(
    suite_path,
    output_dir,
    reference_root,
    *,
    workers=4,
    timeout_seconds=1200,
    probes=False,
):
    suite = load_suite(suite_path)
    output = output_path(output_dir, create_parent=True)
    output.mkdir(exist_ok=True)
    specs = [EpisodeSpec.from_dict(row) for row in suite["episodes"]]
    requested = [(spec, None) for spec in specs]
    if probes:
        cases = {
            "BinFill": ("early_button", "wrong_count"),
            "RouteStick": ("wrong_direction",),
            "VideoUnmaskSwap": ("wrong_target", "wrong_order"),
            "VideoRepick": ("early_button", "wrong_target", "incomplete_cycle"),
        }
        for task, names in cases.items():
            available = [spec for spec in specs if spec.task_kind == task]
            for name in names:
                choices = [
                    spec
                    for spec in available
                    if (
                        name != "wrong_order" or spec.task_parameters["pick_count"] == 2
                    )
                    and (
                        name != "incomplete_cycle"
                        or spec.task_parameters["repeat_count"] >= 2
                    )
                ]
                if not choices:
                    raise ValueError(f"套件缺少{name}验证需要的{task}分支")
                requested.append((choices[0], name))
    with new_manager() as manager:
        stop = manager.Event()
        gpus = sorted(
            {suite["certification"][spec.spec_hash]["render_gpu"] for spec in specs}
        )
        limits = gpu_limits(manager, gpus, workers)
        jobs = []
        for spec, probe in requested:
            cert = suite["certification"][spec.spec_hash]
            jobs.append(
                {
                    "spec": spec.to_dict(),
                    "actual": cert["record_paths"][0],
                    "gpu": cert["render_gpu"],
                    "output": str(
                        output / spec.task_kind / str(spec.seed) / (probe or "nominal")
                    ),
                    "reference_root": str(Path(reference_root).resolve()),
                    "timeout": timeout_seconds,
                    "probe": probe,
                    "gpu_limit": limits[cert["render_gpu"]],
                }
            )
        results = run_jobs(_verify_job, jobs, workers, stop)
    summary = {
        "passed": True,
        "suite_hash": suite["suite_hash"],
        "nominal_episodes": len(specs),
        "cases": len(results),
        "results": results,
    }
    target = output / "verification.json"
    if target.exists() and json.loads(target.read_text()) != summary:
        raise ValueError("验证汇总与已有结果不同")
    if not target.exists():
        target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary
