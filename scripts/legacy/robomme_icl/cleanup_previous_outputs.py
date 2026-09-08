"""验收通过后按冻结清单清理旧产物；默认只盘点，显式 --apply 才删除。"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import traceback


ROOT = Path(__file__).resolve().parents[3]
TASKS = ("BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick")
STEMS = ("binfill", "routestick", "videounmaskswap", "videorepick")
SOURCE_SUFFIXES = {".py", ".pyc", ".pyo", ".sh", ".toml", ".lock", ".yaml", ".yml",
                   ".urdf", ".srdf", ".obj", ".stl", ".dae", ".glb", ".so", ".whl"}
CACHE_ARTIFACTS = {"plan-visuals-20260907-v1", "plot-smoke-check", "plot-smoke-check-final",
                   "plot-tracked-entry-smoke", "pytest-icl-integration", "pytest-icl-suite",
                   "pytest-legacy-baseline"}


def _require(condition, message):
    """安全判断不使用可能被优化模式关闭的 assert。"""
    if not condition:
        raise ValueError(message)


def _canonical(value):
    """沿用入口和验收报告的规范 JSON 字节定义。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _signed(value):
    """清理计划和结果也携带可复核的内容摘要。"""
    body = {key: item for key, item in value.items() if key != "report_hash"}
    return {**body, "report_hash": hashlib.sha256(_canonical(body).encode()).hexdigest()}


def _read_signed(path):
    """拒绝被改动或未完成写入的验收凭证。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict) and value.get("report_hash") == _signed(value)["report_hash"],
             f"报告摘要不符：{path}")
    return value


def _sha256(path):
    """流式计算媒体摘要，不读取旧 HDF5 内容。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _physical(value, *, must_exist=True):
    """所有入口与根路径均逐层拒绝符号链接，不接受仓库外位置。"""
    path = Path(value).expanduser()
    _require(".." not in path.parts, f"路径不得含父目录跳转：{path}")
    path = path if path.is_absolute() else ROOT / path
    _require(path != ROOT and ROOT in path.parents, f"路径必须严格位于当前仓库内：{path}")
    for part in (path, *path.parents):
        if part == ROOT:
            break
        _require(not part.is_symlink(), f"路径不能经过符号链接：{part}")
    _require(path.resolve(strict=False) == path, f"实体路径发生变化：{path}")
    if must_exist:
        _require(path.exists(), f"所需路径不存在：{path}")
    return path


def _existing_file(path, *, newer_than=None):
    """验收依赖必须仍是非空实体文件，且未在验收报告之后改写。"""
    path = _physical(path)
    _require(path.is_file() and path.stat().st_size > 0, f"所需实体文件为空或类型错误：{path}")
    if newer_than is not None:
        _require(path.stat().st_mtime_ns <= newer_than, f"产物在验收报告之后发生修改：{path}")
    return path


def _check_hdf5(path, spec, certification, verified_mtime):
    """重新读取完整标志、规格和内容摘要；全帧逐位检查由已签名验收负责。"""
    import h5py

    path = _existing_file(path, newer_than=verified_mtime)
    with h5py.File(path, "r") as handle:
        _require(bool(handle.attrs.get("complete", False)), f"HDF5 尚未完成：{path}")
        raw = handle["setup/episode_spec"][()]
        if isinstance(raw, bytes):
            raw = raw.decode()
        _require(json.loads(raw) == spec, f"HDF5 规格与新清单不同：{path}")
        _require(str(handle.attrs["content_hash"]) == certification["content_hash"], f"HDF5 内容摘要不同：{path}")
        _require(int(handle["steps"].attrs["length"]) == certification["frame_count"], f"HDF5 帧数不同：{path}")
    return path


def verify_gate(run_root, report_dir):
    """要求本批次384份HDF5、192视频及四图已通过，并重新核对留存实体。"""
    from robomme_icl.suite import load_suite

    verification_path = _existing_file(report_dir / "verification.json")
    verification = _read_signed(verification_path)
    verified_mtime = verification_path.stat().st_mtime_ns
    _require(verification.get("schema_version") == 1 and verification.get("status") == "passed", "整批验收尚未通过")
    _require(verification.get("episodes") == 96 and verification.get("hdf5_verified") == 384
             and verification.get("videos_verified") == 192, "验收必须覆盖96条、384份HDF5和192视频")
    for key in ("source_specs_unchanged", "configs_unchanged", "strict_original_frames_equal"):
        _require(verification.get(key) is True, f"验收缺少严格通过标志：{key}")
    _require(verification.get("run_root") == str(run_root), "验收属于另一输出批次")
    suite_path = _existing_file(run_root / "suite/suite.json", newer_than=verified_mtime)
    source_path = _existing_file(run_root / "provenance/source_suite.json", newer_than=verified_mtime)
    _require(verification.get("suite") == str(suite_path), "验收新清单路径不同")
    suite, source = load_suite(suite_path), load_suite(source_path)
    _require(verification.get("suite_hash") == suite["suite_hash"]
             and verification.get("source_suite_hash") == source["suite_hash"], "新清单或来源快照摘要不同")
    _require(suite["episodes"] == source["episodes"] and suite["configs"] == source["configs"], "来源快照与新清单不同")
    specs = suite["episodes"]
    _require(len(specs) == 96 and Counter(row["task_kind"] for row in specs) == Counter({task: 24 for task in TASKS}), "实际任务配额不是四任务各24条")
    _require(Counter((row["task_kind"], row["difficulty"]) for row in specs)
             == Counter({(task, level): 8 for task in TASKS for level in ("easy", "medium", "hard")}), "实际难度配额不是每档8条")
    verified = verification.get("episodes_verified", [])
    _require(len(verified) == 96 and len({row["spec_hash"] for row in verified}) == 96, "逐条验收明细缺失或重复")
    indexed = {row["spec_hash"]: row for row in verified}
    _require(set(indexed) == {row["spec_hash"] for row in specs}, "实际规格与逐条验收集合不同")
    expected_h5, expected_videos, frames = set(), set(), 0
    for spec in specs:
        cert, row = suite["certification"][spec["spec_hash"]], indexed[spec["spec_hash"]]
        _require(row.get("strict_equal") is True and cert.get("source_frames_equal") is True, "逐条原始帧验收没有通过")
        for key, value in {"task_kind": spec["task_kind"], "seed": spec["seed"], "content_hash": cert["content_hash"],
                           "frames": cert["frame_count"], "render_gpu": cert["render_gpu"]}.items():
            _require(row.get(key) == value, f"逐条验收字段不同：{spec['spec_hash']} {key}")
        frames += row["frames"]
        _require(len(cert.get("record_paths", [])) == 2, "新认证没有保存两份记录")
        paths = []
        for value in cert["record_paths"]:
            path = Path(value)
            path = path if path.is_absolute() else suite_path.parent / path
            _require(run_root in path.parents, "新认证记录仍位于准备删除的旧批次")
            paths.append(_check_hdf5(path, spec, cert, verified_mtime))
        videos = row.get("videos", [])
        _require(len(videos) == 2 and {item["stage"] for item in videos} == {"generate", "replay"}, "逐条验收没有生成及回放两份视频")
        for stage in ("generate", "replay"):
            base = run_root if stage == "generate" else run_root / "replay"
            h5 = base / "hdf5_files" / spec["task_kind"] / f"seed_{spec['seed']}.h5"
            paths.append(_check_hdf5(h5, spec, cert, verified_mtime))
            video = _existing_file(base / "videos" / spec["task_kind"] / f"seed_{spec['seed']}.mp4", newer_than=verified_mtime)
            sidecar_path = _existing_file(video.with_suffix(".json"), newer_than=verified_mtime)
            evidence = next(item for item in videos if item["stage"] == stage)
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            _require(evidence.get("path") == str(video) and evidence.get("sidecar") == str(sidecar_path), "视频验收路径不同")
            _require(evidence.get("sha256") == sidecar.get("video_sha256") == _sha256(video), "视频内容已偏离验收摘要")
            _require(sidecar.get("spec_hash") == spec["spec_hash"] and sidecar.get("source_content_hash") == cert["content_hash"], "视频来源身份不同")
            expected_h5.add(h5)
            expected_videos.add(video)
        _require(len({(path.stat().st_dev, path.stat().st_ino) for path in paths}) == 4, "四份新记录不能用同一个实体文件冒充")
    _require(frames == verification.get("frames_per_pass"), "累计帧数不同")
    for base in (run_root, run_root / "replay"):
        # 与正式验证器一致：.staging保留重试硬链接，只检查对外发布的文件集合。
        for name, suffix, expected in (("hdf5_files", ".h5", expected_h5), ("videos", ".mp4", expected_videos)):
            directory = base / name
            actual = {path for path in directory.rglob(f"*{suffix}")
                      if not any(part.startswith(".") for part in path.relative_to(directory).parts)}
            _require(actual == {path for path in expected if directory in path.parents}, f"{name} 正式文件集合不同")
    figures = verification.get("figures", {})
    _require(figures.get("image_count") == 4 and figures.get("actual_counts_equal") is True
             and figures.get("position_coverage_equal") is True, "四任务图表尚未完整通过")
    summary_path = _existing_file(run_root / "distributions/distribution_summary.json", newer_than=verified_mtime)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    _require(summary.get("suite_hash") == suite["suite_hash"] and summary.get("episodes_total") == 96, "图表来源清单不同")
    image_rows = figures.get("figures", [])
    _require(len(image_rows) == 4 and {row["task_kind"] for row in image_rows} == set(TASKS), "四图验收明细不完整")
    for task, stem in zip(TASKS, STEMS):
        image = _existing_file(run_root / "distributions" / f"{stem}.png", newer_than=verified_mtime)
        _existing_file(image.with_suffix(".json"), newer_than=verified_mtime)
        row = next(item for item in image_rows if item["task_kind"] == task)
        _require(row.get("path") == str(image) and row.get("image_sha256") == _sha256(image), "图表内容偏离验收摘要")
    return {"verification_hash": verification["report_hash"], "verification_file_sha256": _sha256(verification_path),
            "suite_hash": suite["suite_hash"], "source_suite_hash": source["suite_hash"],
            "episodes": 96, "hdf5_verified": 384, "videos_verified": 192, "figures_verified": 4}


def _protected(run_root, report_dir, inventory):
    """保护源码、依赖、官方参考集及最终留存批次，并保护这些目录的祖先。"""
    names = ("data", "src", "tests", "assets", "doc", "configs", ".git", ".venv", "challenge_interface",
             "scripts/legacy", "scripts/_icl", "scripts/README.md", "scripts/prepare_suite.py",
             "scripts/generate_dataset.py", "scripts/replay_dataset.py", "scripts/plot_distribution.py",
             "artifacts/generated/robomme-icl/scripts-v1", "artifacts/reports/robomme-icl/scripts-v1",
             "pyproject.toml", "uv.lock", "AGENTS.md", "CLAUDE.md", "readme.md",
             ".cache/uv", ".cache/maniskill", ".cache/huggingface", ".cache/torch", ".cache/xdg",
             ".cache/matplotlib", ".cache/matplotlib-plan", ".cache/matplotlib-icl-certified")
    return [run_root, report_dir, *[ROOT / name for name in names],
            *[_physical(path, must_exist=False) for path in inventory.get("protected_paths", [])]]


def _allowed(path):
    """清单不能把新增危险位置变成授权目标；仅允许原产物区及明确旧临时区。"""
    if any(parent in path.parents for parent in (ROOT / "artifacts/generated", ROOT / "artifacts/reports")):
        return True
    old = [ROOT / "scripts" / name / child
           for name in ("data-generation", "data-generation-newSeed", "data-generation-MotionJEPALabel", "patternlock-routestick-params")
           for child in ("reports", "outputs")]
    old += [ROOT / "scripts/400ep-dataset" / name for name in ("run-log.md", "run_parameters.json", "run_summary.json")]
    old += [ROOT / ".cache" / name for name in CACHE_ARTIFACTS]
    if any(path == parent or parent in path.parents for parent in old):
        return True
    return path.parent == ROOT / ".cache" and path.name.startswith("icl-scripts-") and path.suffix == ".log"


def _identity(value):
    """不使用ctime/nlink，以免同批删除硬链接时误判未改写的另一名称。"""
    return {"device": value.st_dev, "inode": value.st_ino, "mode": value.st_mode,
            "size": value.st_size, "mtime_ns": value.st_mtime_ns}


def _snapshot(path):
    """冻结逐文件树；内部符号链接只记录链接本身，不读取目标。"""
    value = path.lstat()
    row = {"path": str(path), "name": path.name, "identity": _identity(value)}
    if stat.S_ISLNK(value.st_mode):
        return {**row, "kind": "symlink", "target": os.readlink(path), "children": []}
    if stat.S_ISDIR(value.st_mode):
        return {**row, "kind": "directory", "children": [_snapshot(child) for child in sorted(path.iterdir())]}
    _require(stat.S_ISREG(value.st_mode), f"候选含非普通文件，停止：{path}")
    _require(path.suffix.lower() not in SOURCE_SUFFIXES, f"候选混入源码、配置、静态资产或依赖：{path}")
    return {**row, "kind": "file", "children": []}


def _flatten(row):
    """递归展开计划树，用于体积统计和进程占用核对。"""
    return [row, *[item for child in row["children"] for item in _flatten(child)]]


def _active_users(paths):
    """检查当前用户进程的工作目录和打开文件；只报告PID及匹配路径。"""
    busy = []
    for directory in Path("/proc").iterdir():
        if not directory.name.isdecimal() or int(directory.name) == os.getpid():
            continue
        try:
            if directory.stat().st_uid != os.getuid():
                continue
            # sd-pam等系统辅助进程的目录属用户、fd却属root；它们不属于本用户生成工作进程。
            if (directory / "fd").stat().st_uid != os.getuid():
                continue
            targets = []
            for link in [directory / "cwd", *(directory / "fd").iterdir()]:
                try:
                    text = os.readlink(link)
                except FileNotFoundError:
                    continue
                if text.startswith("/"):
                    targets.append(Path(text.removesuffix(" (deleted)")))
            for target in targets:
                if any(target == path or path in target.parents for path in paths):
                    busy.append({"pid": int(directory.name), "path": str(target)})
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            raise RuntimeError(f"不能核对同用户进程 {directory.name} 的文件占用，停止清理")
    _require(not busy, f"候选仍有进程使用，必须等待退出：{busy}")


def _exclusive_json(path, value):
    """首次计划与结果必须排他创建，未知文件绝不覆盖。"""
    payload = _signed(value)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(_canonical(payload) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return payload


def _save_owned_result(path, value, previous_hash):
    """只原子更新本进程已创建且摘要未变的结果文件，逐个落盘删除进度。"""
    _require(_read_signed(path)["report_hash"] == previous_hash, "清理结果被外部修改，停止覆盖")
    payload = _signed(value)
    descriptor, name = tempfile.mkstemp(prefix=".cleanup-result-", suffix=".json", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(_canonical(payload) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return payload["report_hash"]


def _delete_planned(parent_fd, row, record):
    """只删除快照列明的名称；目录新出现未知内容时rmdir失败并保留该内容。"""
    current = os.stat(row["name"], dir_fd=parent_fd, follow_symlinks=False)
    _require(_identity(current) == row["identity"], f"删除前文件身份发生变化：{row['path']}")
    if row["kind"] == "directory":
        descriptor = os.open(row["name"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            _require(os.fstat(descriptor).st_ino == row["identity"]["inode"], "目录打开期间身份改变")
            for child in row["children"]:
                _delete_planned(descriptor, child, record)
        finally:
            os.close(descriptor)
        os.rmdir(row["name"], dir_fd=parent_fd)
    else:
        os.unlink(row["name"], dir_fd=parent_fd)
    record({"path": row["path"], "kind": row["kind"], "status": "deleted", "size": row["identity"]["size"]})


def _open_directory(path):
    """从仓库根逐段打开目录，关闭祖先被并发替换为符号链接的窗口。"""
    descriptor = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.relative_to(ROOT).parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def cleanup(inventory_path, run_root, report_dir, *, apply=False):
    """先验收、再冻结最新计划；显式执行时逐项删除，失败后保留完整证据。"""
    inventory_path, run_root, report_dir = (_physical(value) for value in (inventory_path, run_root, report_dir))
    _require(run_root.is_dir() and report_dir.is_dir(), "本次数据与报告根必须存在")
    _require(run_root != report_dir and run_root not in report_dir.parents and report_dir not in run_root.parents,
             "本次数据与报告根不能相同或互相包含")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    _require(inventory.get("schema_version") == 1 and inventory.get("repository_root") == str(ROOT), "盘点清单不属于当前仓库")
    protected = _protected(run_root, report_dir, inventory) + [inventory_path]
    candidates, old_rows = [], inventory.get("candidates")
    _require(isinstance(old_rows, list) and old_rows, "盘点清单没有明确候选")
    for row in old_rows:
        path = _physical(row["path"], must_exist=False)
        _require(row.get("relative_path") == path.relative_to(ROOT).as_posix(), "盘点绝对与相对路径不同")
        _require(_allowed(path), f"不属于已授权的历史产物区域：{path}")
        _require(not any(path == p or p in path.parents or path in p.parents for p in protected), f"候选触及保留路径或其祖先：{path}")
        _require(not any(path == p or p in path.parents or path in p.parents for p in candidates), f"候选重复或互相包含：{path}")
        candidates.append(path)
    gate = verify_gate(run_root, report_dir)
    _active_users(candidates)
    snapshots, missing = [], []
    for path, old in zip(candidates, old_rows):
        if not path.exists():
            missing.append(str(path))
            continue
        snapshot = _snapshot(path)
        _require(snapshot["kind"] == old.get("type"), f"候选根类型已改变：{path}")
        snapshots.append({"snapshot": snapshot, "original_apparent_file_bytes": old.get("apparent_file_bytes"),
                          "current_apparent_file_bytes": sum(item["identity"]["size"] for item in _flatten(snapshot) if item["kind"] == "file")})
    plan_body = {"schema_version": 1, "repository_root": str(ROOT), "inventory": str(inventory_path),
                 "inventory_sha256": _sha256(inventory_path), "run_root": str(run_root), "report_dir": str(report_dir),
                 "verification": gate, "protected_paths": sorted({str(path) for path in protected}),
                 "candidates": snapshots, "already_absent": missing}
    plan_path = report_dir / "cleanup-plan.json"
    if plan_path.exists():
        plan = _read_signed(_existing_file(plan_path))
        _require({key: value for key, value in plan.items() if key != "report_hash"} == plan_body,
                 "已有清理计划与本次实体或验收不同，保留原计划并停止")
    else:
        plan = _exclusive_json(plan_path, plan_body)
    if not apply:
        print(f"仅盘点，未删除：{len(snapshots)} 个现有根；计划 {plan_path}", flush=True)
        return {"status": "planned", "plan": str(plan_path), "plan_hash": plan["report_hash"]}
    result_path = report_dir / "cleanup-result.json"
    _require(not result_path.exists(), "清理结果已经存在，禁止覆盖；先检查已有结果")
    result = {"schema_version": 1, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
              "pid": os.getpid(), "plan_hash": plan["report_hash"], "verification": gate,
              "already_absent": missing, "completed_roots": [], "deletions": []}
    current_hash = _exclusive_json(result_path, result)["report_hash"]

    def record(row):
        """每一次实际删除后立即持久保存进度，失败不伪装完成。"""
        nonlocal current_hash
        result["deletions"].append(row)
        current_hash = _save_owned_result(result_path, result, current_hash)

    try:
        for row in snapshots:
            snapshot = row["snapshot"]
            path = _physical(snapshot["path"])
            _require(_sha256(report_dir / "verification.json") == gate["verification_file_sha256"],
                     "删除期间验收凭证发生变化，停止")
            _active_users([path])
            _require(_snapshot(path) == snapshot, f"计划之后目录内容发生变化：{path}")
            descriptor = _open_directory(path.parent)
            try:
                _delete_planned(descriptor, snapshot, record)
            finally:
                os.close(descriptor)
            result["completed_roots"].append(str(path))
            current_hash = _save_owned_result(result_path, result, current_hash)
        result["status"] = "passed"
    except BaseException:
        result["status"] = "failed"
        result["error"] = traceback.format_exc()
        raise
    finally:
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_owned_result(result_path, result, current_hash)
    print(f"按计划清理完成：{len(result['completed_roots'])} 个根；结果 {result_path}", flush=True)
    return result


def main(argv=None):
    """维护入口默认只盘点；显式--apply执行已经授权的清理清单。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="验收通过后执行清单内删除，默认仅保存计划")
    args = parser.parse_args(argv)
    cleanup(args.inventory, args.run_root, args.report_dir, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
