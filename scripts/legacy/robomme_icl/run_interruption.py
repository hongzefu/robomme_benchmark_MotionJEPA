"""对一条认证记录注入真实子进程超时，验证同规格重试和完整文件复用。"""

import argparse
import json
from pathlib import Path
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--interrupt-after", type=float, default=12)
    args = parser.parse_args()
    if args.interrupt_after <= 0:
        raise ValueError("中断时限必须大于零")
    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    from robomme_icl.io.fingerprint import runtime_fingerprint, source_commit
    from robomme_icl.io.hdf5 import assert_identical
    from robomme_icl.io.paths import output_path
    from robomme_icl.io.pipeline import InfrastructureError, generate_one, run_fresh_process
    from robomme_icl.suite import EpisodeSpec, load_suite

    suite = load_suite(args.suite)
    spec = EpisodeSpec.from_dict(next(row for row in suite["episodes"] if row["task_kind"] == "VideoUnmaskSwap"))
    cert = suite["certification"][spec.spec_hash]
    gpu, fingerprint = cert["render_gpu"], cert["runtime_fingerprint"]
    assert_identical(fingerprint, runtime_fingerprint(render_gpu=gpu))
    target, report = output_path(args.output), output_path(args.report, create_parent=True)
    if target.exists() or report.exists():
        raise FileExistsError("中断验证必须使用新的输出与报告路径")
    attempts = []
    result = {"passed": False, "source_commit": source_commit(), "seed": spec.seed,
              "spec_hash": spec.spec_hash, "render_gpu": gpu, "runtime_fingerprint": fingerprint,
              "interrupt_after_seconds": args.interrupt_after, "attempts": attempts}

    def runner(candidate, destination):
        """只在第一次执行施加墙钟上限，之后交回新版现有重试机制处理。"""
        row = {"seed": candidate.seed, "spec_hash": candidate.spec_hash, "path": str(destination)}
        attempts.append(row)
        if len(attempts) == 1:
            try:
                run_fresh_process(candidate, destination, render_gpu=gpu,
                                  timeout_seconds=args.interrupt_after)
            except InfrastructureError as exc:
                row["forced_interruption"] = str(exc)
                raise
            raise AssertionError("预定中断未发生，不能把本次检查记为通过")
        return run_fresh_process(candidate, destination, render_gpu=gpu)

    try:
        generated = generate_one(spec, target, runner=runner, expected_content_hash=cert["content_hash"],
                                 expected_runtime_fingerprint=fingerprint)
        resumed = generate_one(spec, target, expected_content_hash=cert["content_hash"],
                               expected_runtime_fingerprint=fingerprint)
        assert len(attempts) == 2 and "forced_interruption" in attempts[0]
        assert all(row["seed"] == spec.seed and row["spec_hash"] == spec.spec_hash for row in attempts)
        assert resumed["resumed"] is True
        assert_identical(fingerprint, runtime_fingerprint(render_gpu=gpu))
        result.update(passed=True, generated=generated, resumed=resumed)
    except BaseException:
        result["error"] = traceback.format_exc()
        raise
    finally:
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(f"实际中断、同seed/spec重试和断点复用通过：{report}", flush=True)


if __name__ == "__main__":
    main()
