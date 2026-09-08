"""只读核验四入口的整批产物；不启动仿真、不补生成 HDF5、视频或图片。"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from _icl.common import canonical, positive_int, read_json, safe_output, script_fingerprint, signed


TASKS = ("BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick")
BASELINE = "a69e9bc"


def _require(condition, message):
    """所有不满足的条件都显式报错，不依赖可被优化掉的 assert。"""
    if not condition:
        raise ValueError(message)


def _existing(path):
    """读取入口也核对实体路径，缺失文件必须在并行重读取前报错。"""
    from robomme_icl.io.paths import output_path

    target = output_path(path)
    if not target.is_file():
        raise FileNotFoundError(f"验收所需文件不存在：{target}")
    return target


def _sha256(path):
    """分块计算文件摘要，不把整个视频或 HDF5 再次载入内存。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _phase(root, name, count):
    """验签并核对阶段的汇总数量，不能以部分成功视作整批完成。"""
    parameters = read_json(_existing(root / "run_parameters.json"))
    summary = read_json(_existing(root / "run_summary.json"))
    _require(summary.get("status") == "passed", f"{root} 整批状态未通过")
    phase = summary.get("phases", {}).get(name, {})
    _require(phase.get("status") == "passed", f"{name} 阶段未通过")
    _require(parameters.get("scripts_hash") == script_fingerprint(), f"{name} 入口源码指纹与当前版本不符")
    _require(phase.get("hdf5_count") == phase.get("video_count") == count, f"{name} HDF5/视频数量不符")
    _require(len(phase.get("records", [])) == len(phase.get("videos", [])) == count, f"{name} 明细数量不符")
    return parameters, phase


def _record_path(path, suite_dir):
    """相对认证路径只相对其清单目录解析。"""
    candidate = Path(path)
    return _existing(candidate if candidate.is_absolute() else suite_dir / candidate)


def _source_record_path(path, suite_dir):
    """旧记录只核对快照中的规范路径，清理后不要求实体存在或重新读取帧。"""
    from robomme_icl.io.paths import output_path

    candidate = Path(path)
    return output_path(candidate if candidate.is_absolute() else suite_dir / candidate)


def _index_rows(rows, label):
    """按 task/seed 建立无重复明细索引。"""
    indexed = {}
    for row in rows:
        key = (row["task_kind"], row["seed"])
        _require(key not in indexed, f"{label} 含重复条目：{key}")
        indexed[key] = row
    return indexed


def _same_inventory(directory, expected, suffix):
    """只排除内部暂存目录，其余正式文件集合必须精确对应清单。"""
    actual = {path.resolve() for path in directory.rglob(f"*{suffix}")
              if not any(part.startswith(".") for part in path.relative_to(directory).parts)}
    _require(actual == set(expected), f"{directory} 文件集合不同：缺少 {sorted(set(expected)-actual)}；多出 {sorted(actual-set(expected))}")


def _verify_legacy():
    """与旧提交逐文件比较原版源码和 uv.lock，同时检查额外源码文件。"""
    baseline = subprocess.run(["git", "rev-parse", BASELINE], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    tree = subprocess.run(["git", "rev-parse", f"{baseline}:src/robomme"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    archive = subprocess.run(["git", "archive", baseline, "src/robomme", "uv.lock"], cwd=ROOT, capture_output=True, check=True).stdout
    expected = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as handle:
        for member in handle.getmembers():
            if member.isfile():
                expected[member.name] = hashlib.sha256(handle.extractfile(member).read()).hexdigest()
            elif member.issym() or member.islnk():
                raise ValueError(f"旧源码中出现链接，不能按普通文件验收：{member.name}")
    actual_files = {path.relative_to(ROOT).as_posix() for path in (ROOT / "src/robomme").rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo")}
    _require(actual_files == {name for name in expected if name.startswith("src/robomme/")}, "原版源码文件集合相对基线变化")
    for name, digest in expected.items():
        path = ROOT / name
        _require(not path.is_symlink() and _sha256(path) == digest, f"原版源码或依赖锁相对基线变化：{name}")
    return {"baseline_commit": baseline, "legacy_git_tree": tree, "source_files": len(actual_files),
            "legacy_source_unchanged": True, "uv_lock_unchanged": True, "uv_lock_sha256": expected["uv.lock"]}


def _verify_video(path, record, summary_row):
    """只验证已存在媒体，读取一次已验证记录供身份核对，绝不调用导出函数。"""
    from _icl.video import ENCODING, FFMPEG, _probe, _read_sidecar

    fps = record.episode_spec["schedule"]["control_freq"]
    first = record.frames[0]["observation"]
    width = int(first["base_rgb"].shape[1] + first["wrist_rgb"].shape[1])
    height = int(first["base_rgb"].shape[0])
    _require((width, height) == (512, 256), f"HDF5 两路图像拼接后不是 512×256：{path}")
    version = subprocess.run([FFMPEG, "-version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    identity = {"source_content_hash": record.content_hash, "spec_hash": record.spec_hash,
                "frames": len(record.frames), "fps": fps, "width": width, "height": height,
                "encoding": dict(ENCODING), "ffmpeg_version": version}
    sidecar = _existing(path.with_suffix(".json"))
    metadata = _read_sidecar(sidecar, identity)
    _require(metadata["video_sha256"] == _sha256(path), f"视频摘要不符：{path}")
    for key, expected in identity.items():
        _require(summary_row.get(key) == expected, f"视频汇总 {key} 与记录不一致：{path}")
    _require(summary_row.get("video_sha256") == metadata["video_sha256"], f"视频汇总摘要不同：{path}")
    _require(Path(summary_row["path"]).resolve() == path, f"视频汇总路径不同：{path}")
    _require(Path(summary_row["sidecar"]).resolve() == sidecar, f"视频 sidecar 汇总路径不同：{path}")
    validation = _probe(path, frames=len(record.frames), fps=fps, width=width, height=height)
    _require(metadata.get("verification") == validation, f"视频解码结果与 sidecar 不同：{path}")
    return {"path": str(path), "sidecar": str(sidecar), "sha256": metadata["video_sha256"], **validation}


def _verify_episode(job):
    """每个工作进程逐条验证四份 HDF5 和两份视频，限制同时驻留内存规模。"""
    from robomme_icl.io.hdf5 import assert_identical, assert_records_identical, read_episode

    spec, certification = job["spec"], job["certification"]
    expected_hash = certification["content_hash"]
    records = [read_episode(path) for path in job["certification_paths"]]
    for record in records:
        assert_identical(spec, record.episode_spec, path="认证 spec")
        assert_identical(certification["runtime_fingerprint"], record.runtime_fingerprint, path="认证运行指纹")
        _require(record.content_hash == expected_hash, "认证记录内容摘要与清单不同")
        _require(len(record.frames) == certification["frame_count"], "认证记录帧数与清单不同")
    assert_records_identical(records[0], records[1])
    baseline = records[0]
    del records
    media = []
    for stage in ("generate", "replay"):
        row = job[stage]
        record = read_episode(row["h5"])
        assert_records_identical(baseline, record)
        _require(record.content_hash == expected_hash, f"{stage} 内容摘要与认证不同")
        final = record.frames[-1]["info"]
        _require(final.get("success") is True and final.get("fail") is False, f"{stage} 最终判定不是成功且未失败")
        summary = row["record_summary"]
        for key, expected in {"content_hash": expected_hash, "spec_hash": spec["spec_hash"],
                              "seed": spec["seed"], "task_kind": spec["task_kind"],
                              "frame_count": len(record.frames), "render_gpu": certification["render_gpu"]}.items():
            _require(summary.get(key) == expected, f"{stage} 汇总 {key} 与实际 HDF5 不同")
        _require(Path(summary["path"]).resolve() == Path(row["h5"]), f"{stage} 汇总 HDF5 路径不同")
        video = _verify_video(Path(row["video"]), record, row["video_summary"])
        sidecar = json.loads(Path(video["sidecar"]).read_text(encoding="utf-8"))
        _require(Path(sidecar["source_h5"]).resolve() == Path(row["h5"]), f"{stage} 视频来源 HDF5 路径不同")
        _require(row["video_summary"]["render_gpu"] == certification["render_gpu"], f"{stage} 视频汇总 GPU 不同")
        media.append({"stage": stage, **video})
        del record
    print(f"已核验 {spec['task_kind']} seed={spec['seed']}：四份原始记录逐位相同，两份视频完整解码", flush=True)
    return {"task_kind": spec["task_kind"], "difficulty": spec["difficulty"], "seed": spec["seed"],
            "spec_hash": spec["spec_hash"], "render_gpu": certification["render_gpu"],
            "frames": len(baseline.frames), "content_hash": expected_hash, "strict_equal": True, "videos": media}


def _verify_figures(directory, suite):
    """重算计数与分层覆盖，同时核对四图的来源及文件摘要；不重新出图。"""
    from _icl import plots

    path = _existing(directory / "distribution_summary.json")
    summary = json.loads(path.read_text(encoding="utf-8"))
    identity = {"schema_version": 1, "suite_hash": suite["suite_hash"], "plot_code_sha256": _sha256(plots.__file__),
                "episode_spec_hashes": [row["spec_hash"] for row in suite["episodes"]]}
    _require(all(summary.get(key) == value for key, value in identity.items()), "分布统计来源或绘图源码摘要不同")
    _require(summary.get("episodes_total") == 96, "分布统计不是96条")
    _require(summary.get("tasks") == plots._actual_distribution(suite), "分布统计的实际计数或分层覆盖不同")
    _require(len(summary.get("figures", [])) == 4, "分布图数量不同")
    figures = {row["task_kind"]: row for row in summary["figures"]}
    _require(set(figures) == set(TASKS), "四任务图表集合不同")
    for task, row in figures.items():
        png = _existing(directory / f"{plots.STEMS[task]}.png")
        metadata = json.loads(_existing(png.with_suffix(".json")).read_text(encoding="utf-8"))
        _require(all(metadata.get(key) == value for key, value in identity.items()), f"{task} 图片来源不同")
        _require(metadata.get("task_kind") == task and row["image_sha256"] == metadata.get("image_sha256") == _sha256(png), f"{task} 图片摘要不同")
        _require(metadata.get("figure") == {key: value for key, value in row.items() if key not in ("path", "sidecar", "image_sha256")}, f"{task} 逐图统计不同")
        _require(Path(row["path"]).resolve() == png and Path(row["sidecar"]).resolve() == png.with_suffix(".json"), f"{task} 图像记录路径不同")
    return {"summary_path": str(path), "suite_hash": suite["suite_hash"], "image_count": 4,
            "actual_counts_equal": True, "position_coverage_equal": True,
            "figures": [{"task_kind": task, "path": row["path"], "image_sha256": row["image_sha256"]} for task, row in figures.items()]}


def verify_bundle(run_root, source_suite=None, *, workers=4):
    """验证完整96条交付，并返回可独占保存的验收报告。"""
    from robomme_icl.io.fingerprint import runtime_fingerprint
    from robomme_icl.io.hdf5 import assert_identical
    from robomme_icl.suite import load_suite

    started = time.monotonic()
    run_root = safe_output(run_root)
    source_path = Path(source_suite) if source_suite is not None else run_root / "provenance/source_suite.json"
    source_path = _existing(source_path if source_path.suffix == ".json" else source_path / "suite.json")
    new_path = _existing(run_root / "suite/suite.json")
    source, suite = load_suite(source_path), load_suite(new_path)
    _require(len(source["episodes"]) == len(suite["episodes"]) == 96, "源清单与新清单均必须为96条")
    assert_identical(source["episodes"], suite["episodes"], path="原、新冻结 spec/seed 顺序")
    assert_identical(source["configs"], suite["configs"], path="原、新配置")
    task_counts = Counter(row["task_kind"] for row in suite["episodes"])
    difficulty_counts = Counter((row["task_kind"], row["difficulty"]) for row in suite["episodes"])
    _require(task_counts == Counter({task: 24 for task in TASKS}), "任务配额不是每任务24条")
    _require(difficulty_counts == Counter({(task, difficulty): 8 for task in TASKS for difficulty in ("easy", "medium", "hard")}), "难度配额不是每档8条")
    gen_parameters, gen_phase = _phase(run_root, "generate", 96)
    replay_parameters, replay_phase = _phase(run_root / "replay", "replay", 96)
    root_summary = read_json(run_root / "run_summary.json")
    _require(root_summary["phases"].get("prepare", {}).get("status") == "passed", "重新认证阶段未通过")
    _require(root_summary["phases"]["prepare"].get("suite_hash") == suite["suite_hash"], "重新认证汇总 suite_hash 不同")
    _require(gen_parameters["phases"]["generate"] == {"suite_hash": suite["suite_hash"], "spec_hashes": [row["spec_hash"] for row in suite["episodes"]]}, "生成阶段身份与清单不符")
    _require(gen_parameters["phases"]["prepare"] == {"source_suite_hash": source["suite_hash"], "spec_hashes": [row["spec_hash"] for row in suite["episodes"]]}, "重新认证来源身份不同")
    indexes = {"generate": (_index_rows(gen_phase["records"], "生成 HDF5"), _index_rows(gen_phase["videos"], "生成视频")),
               "replay": (_index_rows(replay_phase["records"], "回放 HDF5"), _index_rows(replay_phase["videos"], "回放视频"))}
    expected_keys = {(row["task_kind"], row["seed"]) for row in suite["episodes"]}
    _require(all(set(index) == expected_keys for pair in indexes.values() for index in pair), "HDF5 或视频汇总任务/seed集合不同")
    fingerprints, jobs, replay_inputs, source_record_presence = {}, [], [], []
    inventories = {stage: {"h5": [], "mp4": []} for stage in indexes}
    for spec in suite["episodes"]:
        certification = suite["certification"][spec["spec_hash"]]
        old = source["certification"][spec["spec_hash"]]
        _require(all(certification.get(name) is True for name in ("passed", "repeat_equal", "source_frames_equal", "fresh_process")), "新认证缺少完整通过标志")
        _require(certification.get("source_suite_hash") == source["suite_hash"] and certification.get("source_content_hash") == old["content_hash"], "新认证的旧来源摘要不同")
        _require(certification.get("source_certification_commit") == old["source_commit"], "新认证引用的原认证提交不同")
        _require(certification.get("frame_count") == old["frame_count"], "新认证与原认证帧数不同")
        source_records = [_source_record_path(path, source_path.parent) for path in old["record_paths"]]
        referenced_records = [_source_record_path(path, source_path.parent) for path in certification["source_record_paths"]]
        _require(source_records == referenced_records, "新认证引用的原始记录路径不同")
        source_record_presence.extend({"path": str(path), "present": path.is_file()} for path in source_records)
        _require(certification.get("render_gpu") == old["render_gpu"], "重新认证修改了固定 GPU")
        _require(certification.get("candidate_index") == old["candidate_index"], "重新认证修改了冻结候选编号")
        gpu = certification["render_gpu"]
        if gpu not in fingerprints:
            fingerprints[gpu] = runtime_fingerprint(render_gpu=gpu)
        assert_identical(certification["runtime_fingerprint"], fingerprints[gpu], path="新认证与当前运行指纹")
        assert_identical({key: value for key, value in old["runtime_fingerprint"].items() if key != "icl_source_hash"},
                         {key: value for key, value in certification["runtime_fingerprint"].items() if key != "icl_source_hash"}, path="原、新运行条件")
        cert_paths = [_record_path(path, new_path.parent) for path in certification["record_paths"]]
        _require(len(cert_paths) == 2 and not cert_paths[0].samefile(cert_paths[1]), "两次认证记录不是独立实体文件")
        job = {"spec": spec, "certification": certification, "certification_paths": [str(path) for path in cert_paths]}
        for stage, pair in indexes.items():
            directory = run_root if stage == "generate" else run_root / "replay"
            h5 = _existing(directory / "hdf5_files" / spec["task_kind"] / f"seed_{spec['seed']}.h5")
            mp4 = _existing(directory / "videos" / spec["task_kind"] / f"seed_{spec['seed']}.mp4")
            _existing(mp4.with_suffix(".json"))
            inventories[stage]["h5"].append(h5)
            inventories[stage]["mp4"].append(mp4)
            key = (spec["task_kind"], spec["seed"])
            job[stage] = {"h5": str(h5), "video": str(mp4), "record_summary": pair[0][key], "video_summary": pair[1][key]}
            if stage == "generate":
                replay_inputs.append({"path": str(h5), "spec_hash": spec["spec_hash"], "content_hash": certification["content_hash"], "render_gpu": gpu})
        _require(not Path(job["generate"]["h5"]).samefile(job["replay"]["h5"]), "回放数据与生成数据指向同一实体文件")
        for stage in ("generate", "replay"):
            _require(all(not Path(job[stage]["h5"]).samefile(path) for path in cert_paths), "生成或回放数据与认证记录指向同一实体文件")
        jobs.append(job)
    _require(replay_parameters["phases"]["replay"] == {"inputs": replay_inputs}, "回放输入明细身份不同")
    for stage, inventory in inventories.items():
        base = run_root if stage == "generate" else run_root / "replay"
        _same_inventory(base / "hdf5_files", inventory["h5"], ".h5")
        _same_inventory(base / "videos", inventory["mp4"], ".mp4")
    figures = _verify_figures(run_root / "distributions", suite)
    legacy = _verify_legacy()
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as executor:
        rows = list(executor.map(_verify_episode, jobs))
    _require(script_fingerprint() == gen_parameters["scripts_hash"], "验收期间入口或辅助源码发生变化")
    for gpu, fingerprint in fingerprints.items():
        assert_identical(fingerprint, runtime_fingerprint(render_gpu=gpu), path="验收期间核心源码、依赖及运行条件")
    return {"schema_version": 1, "status": "passed", "verified_at": datetime.now(timezone.utc).isoformat(),
            "scope": "重新验签96条冻结spec、两份新认证及生成/回放原始记录；逐位比较；192视频完整解码；四任务真实分布；未重新运行物理。源清单使用本批 provenance 快照或显式指定文件；旧记录仅核对快照中的路径，允许清理后不存在，旧帧不再读取。旧原始帧的跨版本一致性采用新认证中的source_frames_equal证据。",
            "run_root": str(run_root), "source_suite": str(source_path), "suite": str(new_path),
            "source_suite_hash": source["suite_hash"], "suite_hash": suite["suite_hash"],
            "source_fingerprints": {str(gpu): next(value["runtime_fingerprint"] for value in source["certification"].values() if value["render_gpu"] == gpu) for gpu in fingerprints},
            "core_fingerprints": {str(gpu): value for gpu, value in fingerprints.items()}, "scripts_hash": script_fingerprint(),
            "verifier_sha256": _sha256(__file__), "legacy": legacy,
            "episodes": 96, "task_counts": dict(task_counts), "gpu_counts": dict(Counter(str(row["render_gpu"]) for row in rows)),
            "frames_per_pass": sum(row["frames"] for row in rows), "hdf5_verified": 384, "videos_verified": 192,
            "source_specs_unchanged": True, "configs_unchanged": True, "strict_original_frames_equal": True,
            "source_records_present": all(item["present"] for item in source_record_presence),
            "source_record_files_present": sum(item["present"] for item in source_record_presence),
            "source_record_files_total": len(source_record_presence), "source_records_read": False,
            "source_frame_comparison_evidence": "certification.source_frames_equal",
            "source_record_presence": source_record_presence,
            "figures": figures, "workers": workers, "seconds": time.monotonic() - started, "episodes_verified": rows}


def _save_reports(directory, report):
    """报告使用独占发布，失败证据同样保留且绝不覆盖已有验收。"""
    directory = safe_output(directory)
    paths = [safe_output(directory / name) for name in ("verification.json", "verification.md")]
    if any(path.exists() for path in paths):
        raise FileExistsError(f"验收报告已存在，禁止覆盖：{directory}")
    directory.mkdir(parents=True, exist_ok=True)
    if report["status"] == "passed":
        text = ("# scripts 整批产物验收\n\n"
                f"状态：通过。96 条环境、每任务 24 条，逐遍 {report['frames_per_pass']:,} 帧。\n\n"
                "384 份 HDF5（两份新认证、生成和回放）均通过内容摘要与原始帧逐位比较；192 个 MP4 均通过来源、摘要、帧数、FPS、512×256 尺寸及完整解码检查。\n\n"
                "四任务图表摘要、实际次数及位置分层覆盖通过；原版 src/robomme 与 uv.lock 对 a69e9bc 逐文件相同。\n\n"
                f"检查范围：{report['scope']}\n\n"
                f"旧记录实体仍存在：{report['source_record_files_present']}/{report['source_record_files_total']}；本次未读取旧帧，跨版本对照依据新认证的 source_frames_equal。\n\n"
                f"- 新清单：\x60{report['suite']}\x60\n- 来源清单：\x60{report['source_suite']}\x60\n"
                f"- 新清单摘要：\x60{report['suite_hash']}\x60\n- 入口摘要：\x60{report['scripts_hash']}\x60\n"
                f"- 并发：{report['workers']}；总耗时：{report['seconds']:.2f} 秒。\n\n"
                "逐条视频摘要、原/新运行指纹和验收证据保存在同目录 verification.json。\n")
    else:
        text = f"# scripts 整批产物验收\n\n状态：失败。未宣称整批完成。\n\n错误：\n\n```text\n{report['error']}\n```\n"
    payloads = [json.dumps(signed(report), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", text]
    for path, payload in zip(paths, payloads):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".verification-", dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    """归档维护入口；生产验收只读取全部已完成的产物。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=ROOT / "artifacts/generated/robomme-icl/scripts-v1")
    parser.add_argument("--source-suite", type=Path, default=None,
                        help="来源清单快照；未传时读取 --run-root/provenance/source_suite.json")
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--workers", type=positive_int, default=4)
    args = parser.parse_args(argv)
    if args.source_suite is None:
        args.source_suite = args.run_root / "provenance/source_suite.json"
    from robomme_icl.runtime import configure_runtime
    configure_runtime()
    for name in ("verification.json", "verification.md"):
        if safe_output(args.report_dir / name).exists():
            raise FileExistsError("指定报告已经存在，请保留旧证据并使用新目录")
    try:
        report = verify_bundle(args.run_root, args.source_suite, workers=args.workers)
    except BaseException:
        _save_reports(args.report_dir, {"schema_version": 1, "status": "failed", "error": traceback.format_exc(),
                                       "run_root": str(args.run_root), "source_suite": str(args.source_suite),
                                       "verified_at": datetime.now(timezone.utc).isoformat()})
        raise
    _save_reports(args.report_dir, report)
    print(f"整批验收通过：96 条、{report['frames_per_pass']} 帧、192 个视频；报告 {args.report_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
