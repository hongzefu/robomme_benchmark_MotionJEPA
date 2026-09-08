"""冻结清单迁移认证：真实序列化、伪物理运行和严格负例。"""

from contextlib import nullcontext
import copy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace

import h5py
import numpy as np
import pytest

from scripts._icl import recertify as module
from robomme_icl.errors import TaskExecutionError
from robomme_icl.io.hdf5 import RecordError, ReproducibilityError, read_episode, write_episode
from robomme_icl.io.paths import repository_root
from robomme_icl.io.pipeline import CandidateRejected
from robomme_icl.suite import candidate_for_slot, load_configs, load_suite, plan_slots, save_suite


def _frames():
    """包含颜色图、不同浮点 dtype 和有符号零，不能用数值容差蒙混通过。"""
    return [{
        "observation": {"base_rgb": np.arange(12, dtype=np.uint8).reshape(2, 2, 3),
                        "wrist_rgb": np.zeros((2, 2, 3), dtype=np.uint8),
                        "qpos": np.array([-0.0, 1.0], dtype=np.float64)},
        "joint_action": np.array([0.1], dtype=np.float64),
        "info": {"success": True, "fail": False, "step": 1},
    }]


class _Manager:
    """仅替换多进程外壳，函数主体和 HDF5 核对均为正式代码。"""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def Event(self):
        return threading.Event()

    def BoundedSemaphore(self, value):
        return nullcontext()


@pytest.fixture
def scenario(monkeypatch):
    cache = repository_root() / ".cache" / "robomme_icl_tests"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="recertify-", dir=cache) as directory:
        root = Path(directory)
        configs = load_configs()
        slots = plan_slots(*configs, tasks=["BinFill", "VideoRepick"], episodes_per_task=2)
        specs = [candidate_for_slot(slot, 0) for slot in slots]
        current = {"icl_source_hash": "new-source", "legacy_source_hash": "same-legacy",
                   "uv_lock_hash": "same-lock", "gpu_devices": ["gpu0", "gpu1"],
                   "thread_environment": {"OMP_NUM_THREADS": "1"}}

        def fingerprint(*, render_gpu=None):
            return {**copy.deepcopy(current), "render_gpu": render_gpu}

        certification = {}
        for spec in specs:
            gpu = spec.seed % 2
            old_fp = {**fingerprint(render_gpu=gpu), "icl_source_hash": "old-source"}
            paths = [write_episode(root / "source" / f"{spec.seed}-{index}.h5", spec, _frames(),
                                   runtime_fingerprint=old_fp, source_commit="old-commit") for index in range(2)]
            first = read_episode(paths[0])
            certification[spec.spec_hash] = {
                "passed": True, "repeat_equal": True, "fresh_process": True,
                "content_hash": first.content_hash, "runtime_fingerprint": old_fp,
                "source_commit": "old-commit", "render_gpu": gpu, "candidate_index": 0,
                "record_paths": [str(path) for path in paths], "frame_count": len(first.frames),
            }
        source = save_suite(root / "source" / "suite.json", specs, configs, certification)
        calls = []

        def runner(spec, destination, *, render_gpu, timeout_seconds):
            calls.append((spec.to_dict(), render_gpu, timeout_seconds))
            return write_episode(destination, spec, _frames(),
                                 runtime_fingerprint=fingerprint(render_gpu=render_gpu), source_commit="new-commit")

        monkeypatch.setattr(module, "configure_runtime", lambda: None)
        monkeypatch.setattr(module, "runtime_fingerprint", fingerprint)
        monkeypatch.setattr(module, "source_commit", lambda: "new-commit")
        monkeypatch.setattr(module, "validate_spec_geometry", lambda spec: {"ok": True})
        monkeypatch.setattr(module, "_new_manager", _Manager)
        monkeypatch.setattr(module, "_run_process_jobs", lambda function, jobs, workers, stop: [function(job) for job in jobs])
        monkeypatch.setattr(module, "run_fresh_process", runner)
        yield SimpleNamespace(root=root, source=source, specs=specs, current=current,
                              fingerprint=fingerprint, calls=calls, runner=runner)


def test_source_change_recertifies_same_full_specs_gpu_and_frames(scenario):
    before = scenario.source.read_bytes()
    manifest = module.recertify_suite(scenario.source, scenario.root / "new")
    old, new = load_suite(scenario.source), load_suite(manifest)
    assert new["episodes"] == old["episodes"]
    assert new["configs"] == old["configs"]
    assert len(scenario.calls) == 2 * len(scenario.specs)
    for spec in scenario.specs:
        report = new["certification"][spec.spec_hash]
        assert report["source_suite_hash"] == old["suite_hash"]
        assert report["source_certification_commit"] == "old-commit"
        assert report["source_frames_equal"] is True
        assert report["runtime_fingerprint"]["icl_source_hash"] == "new-source"
        assert report["content_hash"] != old["certification"][spec.spec_hash]["content_hash"]
        assert report["render_gpu"] == spec.seed % 2
    assert scenario.source.read_bytes() == before


@pytest.mark.parametrize("key,value", [
    ("uv_lock_hash", "changed-lock"), ("gpu_devices", ["replacement-gpu"]),
    ("legacy_source_hash", "changed-legacy"), ("thread_environment", {"OMP_NUM_THREADS": "4"}),
])
def test_other_fingerprint_changes_stop_before_physics(scenario, key, value):
    scenario.current[key] = value
    with pytest.raises(ReproducibilityError, match="运行条件"):
        module.recertify_suite(scenario.source, scenario.root / "new")
    assert not scenario.calls
    assert not (scenario.root / "new").exists()


def test_filter_preserves_source_order_episode_numbers_and_seeds(scenario):
    manifest = module.recertify_suite(scenario.source, scenario.root / "new",
                                     tasks=["VideoRepick"], episodes_per_task=1)
    selected = [spec.to_dict() for spec in scenario.specs if spec.task_kind == "VideoRepick"][:1]
    assert load_suite(manifest)["episodes"] == selected
    assert len(scenario.calls) == 2
    assert all(row[0] == selected[0] for row in scenario.calls)


@pytest.mark.parametrize("mode", ["rgb", "dtype", "signed_zero", "seed"])
def test_any_new_frame_or_spec_difference_stops_and_preserves_record(scenario, monkeypatch, mode):
    def changed(spec, destination, *, render_gpu, timeout_seconds):
        frames = _frames()
        if mode == "rgb":
            frames[0]["observation"]["base_rgb"][0, 0, 0] = 255
        elif mode == "dtype":
            frames[0]["joint_action"] = frames[0]["joint_action"].astype(np.float32)
        elif mode == "signed_zero":
            frames[0]["observation"]["qpos"][0] = 0.0
        else:
            spec = scenario.specs[1]
        return write_episode(destination, spec, frames, runtime_fingerprint=scenario.fingerprint(render_gpu=render_gpu))
    monkeypatch.setattr(module, "run_fresh_process", changed)
    with pytest.raises(RecordError):
        module.recertify_suite(scenario.source, scenario.root / "new")
    assert not (scenario.root / "new" / "suite.json").exists()
    assert list((scenario.root / "new").rglob("episode.h5"))


def test_old_record_tampering_is_rejected_before_new_physics(scenario):
    old = load_suite(scenario.source)
    path = old["certification"][scenario.specs[0].spec_hash]["record_paths"][1]
    with h5py.File(path, "r+") as handle:
        handle["steps/00000000/observation/base_rgb"][0, 0, 0] = 254
    with pytest.raises(RecordError, match="摘要不匹配"):
        module.recertify_suite(scenario.source, scenario.root / "new")
    assert not scenario.calls
    assert Path(path).exists()


def test_resume_revalidates_complete_files_without_new_physics(scenario, monkeypatch):
    output = scenario.root / "new"
    manifest = module.recertify_suite(scenario.source, output)
    before, count = manifest.read_bytes(), len(scenario.calls)
    monkeypatch.setattr(module, "source_commit", lambda: "later-documentation-commit")
    assert module.recertify_suite(scenario.source, output) == manifest
    assert len(scenario.calls) == count
    assert manifest.read_bytes() == before


def test_known_infrastructure_failure_retries_same_spec(scenario, monkeypatch):
    attempts = []
    def failing_once(spec, destination, **kwargs):
        attempts.append((spec.seed, spec.spec_hash))
        if len(attempts) == 1:
            Path(destination).write_bytes("模拟基础设施失败留下的不完整文件".encode("utf-8"))
            raise OSError("模拟设备短暂失败")
        return scenario.runner(spec, destination, **kwargs)
    monkeypatch.setattr(module, "run_fresh_process", failing_once)
    module.recertify_suite(scenario.source, scenario.root / "new", episodes_per_task=1, tasks=["BinFill"])
    assert attempts == [(scenario.specs[0].seed, scenario.specs[0].spec_hash)] * 3
    assert list((scenario.root / "new").rglob("infrastructure_error.json"))


def test_second_run_task_failure_is_reproducibility_failure(scenario, monkeypatch):
    def second_failure(spec, destination, **kwargs):
        if scenario.calls:
            raise CandidateRejected("第二次运行失败")
        return scenario.runner(spec, destination, **kwargs)
    monkeypatch.setattr(module, "run_fresh_process", second_failure)
    with pytest.raises(ReproducibilityError, match="禁止"):
        module.recertify_suite(scenario.source, scenario.root / "new")
    assert len(scenario.calls) == 1
    assert not (scenario.root / "new" / "suite.json").exists()


def test_unknown_or_broken_resume_records_are_preserved(scenario):
    output = scenario.root / "new"
    module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    unknown = output / "unknown.txt"
    unknown.write_text("未知来源", encoding="utf-8")
    count = len(scenario.calls)
    with pytest.raises(RecordError, match="未知"):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    assert unknown.read_text(encoding="utf-8") == "未知来源"
    assert len(scenario.calls) == count


def test_broken_complete_resume_record_stops_without_physics(scenario):
    output = scenario.root / "new"
    manifest = module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    certification = next(iter(load_suite(manifest)["certification"].values()))
    path = Path(certification["record_paths"][0])
    with h5py.File(path, "r+") as handle:
        handle["steps/00000000/observation/base_rgb"][0, 0, 0] = 253
    count = len(scenario.calls)
    with pytest.raises(RecordError, match="摘要不匹配"):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    assert len(scenario.calls) == count
    assert path.exists()


def test_geometry_rejection_never_searches_replacement(scenario, monkeypatch):
    monkeypatch.setattr(module, "validate_spec_geometry", lambda spec: {"ok": False, "reasons": ["碰撞"]})
    with pytest.raises(ReproducibilityError, match="禁止换候选"):
        module.recertify_suite(scenario.source, scenario.root / "new")
    assert not scenario.calls


def test_output_must_not_touch_source_or_reuse_different_selection(scenario):
    with pytest.raises(ValueError, match="隔离"):
        module.recertify_suite(scenario.source, scenario.source.parent / "new")
    output = scenario.root / "new"
    module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    with pytest.raises(ReproducibilityError, match="恢复上下文"):
        module.recertify_suite(scenario.source, output, tasks=["VideoRepick"], episodes_per_task=1)


@pytest.mark.parametrize("state", ["missing", "incomplete", "truncated", "complete"])
def test_interrupted_bound_attempt_resumes_same_spec_without_overwriting(scenario, monkeypatch, state):
    output = scenario.root / "new"
    attempted = []

    def interrupted(spec, destination, **kwargs):
        attempted.append((spec.seed, spec.spec_hash))
        if state == "incomplete":
            with h5py.File(destination, "x") as handle:
                handle.attrs["complete"] = False
        elif state == "truncated":
            Path(destination).write_bytes(b"partial-hdf5")
        elif state == "complete":
            scenario.runner(spec, destination, **kwargs)
        raise KeyboardInterrupt("模拟父进程在完成消息前中断")

    monkeypatch.setattr(module, "run_fresh_process", interrupted)
    with pytest.raises(KeyboardInterrupt):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    attempt = next(output.rglob("attempt_0000"))
    identity_before = (attempt / "identity.json").read_bytes()
    record = attempt / "episode.h5"
    record_before = record.read_bytes() if record.exists() else None
    assert not list(output.rglob("failure_latched.json"))
    monkeypatch.setattr(module, "run_fresh_process", scenario.runner)
    manifest = module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    assert len(load_suite(manifest)["episodes"]) == 1
    assert attempted == [(scenario.specs[0].seed, scenario.specs[0].spec_hash)]
    assert (attempt / "identity.json").read_bytes() == identity_before
    if record_before is not None:
        assert record.read_bytes() == record_before
    assert len(scenario.calls) == 2
    assert all(call[0] == scenario.specs[0].to_dict() for call in scenario.calls)
    if state == "complete":
        assert (attempt / "completed.json").exists()
        assert not (attempt / "interrupted.json").exists()
    else:
        assert (attempt / "interrupted.json").exists()
        assert (attempt.parent / "attempt_0001" / "completed.json").exists()


def test_interruption_after_first_success_only_runs_second_repeat(scenario, monkeypatch):
    output = scenario.root / "new"

    def second_interrupted(spec, destination, **kwargs):
        if scenario.calls:
            raise KeyboardInterrupt("第二次物理进程中断")
        return scenario.runner(spec, destination, **kwargs)

    monkeypatch.setattr(module, "run_fresh_process", second_interrupted)
    with pytest.raises(KeyboardInterrupt):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    first_receipt = next(output.rglob("completed.json"))
    first_data = first_receipt.with_name("episode.h5").read_bytes()
    monkeypatch.setattr(module, "run_fresh_process", scenario.runner)
    module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    assert len(scenario.calls) == 2
    assert first_receipt.with_name("episode.h5").read_bytes() == first_data


@pytest.mark.parametrize("damage", ["missing", "bad_header"])
def test_completion_receipt_prevents_treating_lost_complete_record_as_interruption(scenario, monkeypatch, damage):
    output = scenario.root / "new"

    def second_interrupted(spec, destination, **kwargs):
        if scenario.calls:
            raise KeyboardInterrupt("第二次中断，尚未发布认证报告")
        return scenario.runner(spec, destination, **kwargs)

    monkeypatch.setattr(module, "run_fresh_process", second_interrupted)
    with pytest.raises(KeyboardInterrupt):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    receipt = next(output.rglob("completed.json"))
    record = receipt.with_name("episode.h5")
    if damage == "missing":
        record.unlink()
    else:
        record.write_bytes(b"damaged-complete-file")
    monkeypatch.setattr(module, "run_fresh_process", scenario.runner)
    with pytest.raises((OSError, RecordError)):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    assert len(scenario.calls) == 1
    assert receipt.exists()


@pytest.mark.parametrize("error_type", [CandidateRejected, TaskExecutionError])
def test_explicit_task_failure_is_latched_before_future_retries(scenario, monkeypatch, error_type):
    output = scenario.root / "new"

    def failure(spec, destination, **kwargs):
        raise error_type("实际任务失败")

    monkeypatch.setattr(module, "run_fresh_process", failure)
    with pytest.raises(ReproducibilityError, match="实际任务失败"):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    latch = next(output.rglob("failure_latched.json"))
    before = latch.read_bytes()
    monkeypatch.setattr(module, "run_fresh_process", scenario.runner)
    with pytest.raises(ReproducibilityError, match="已有锁存失败"):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    assert not scenario.calls
    assert latch.read_bytes() == before


def test_frame_difference_latches_and_cannot_be_retried_as_crash(scenario, monkeypatch):
    output = scenario.root / "new"

    def difference(spec, destination, *, render_gpu, **kwargs):
        frames = _frames()
        frames[0]["observation"]["base_rgb"][0, 0, 0] = 252
        return write_episode(destination, spec, frames, runtime_fingerprint=scenario.fingerprint(render_gpu=render_gpu))

    monkeypatch.setattr(module, "run_fresh_process", difference)
    with pytest.raises(ReproducibilityError, match="数组字节不同"):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    monkeypatch.setattr(module, "run_fresh_process", scenario.runner)
    with pytest.raises(ReproducibilityError, match="已有锁存失败"):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    assert not scenario.calls


def test_complete_but_tampered_attempt_without_receipt_is_never_resampled(scenario, monkeypatch):
    output = scenario.root / "new"

    def interrupted_after_corruption(spec, destination, **kwargs):
        scenario.runner(spec, destination, **kwargs)
        with h5py.File(destination, "r+") as handle:
            handle["steps/00000000/observation/base_rgb"][0, 0, 0] = 251
        raise KeyboardInterrupt("在完整 HDF5 验证前中断")

    monkeypatch.setattr(module, "run_fresh_process", interrupted_after_corruption)
    with pytest.raises(KeyboardInterrupt):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    assert not list(output.rglob("completed.json"))
    monkeypatch.setattr(module, "run_fresh_process", scenario.runner)
    with pytest.raises(RecordError, match="摘要不匹配"):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    assert len(scenario.calls) == 1
    assert list(output.rglob("failure_latched.json"))


@pytest.mark.parametrize("damage", ["identity_missing", "unknown_file"])
def test_interrupted_attempt_requires_identity_and_known_files(scenario, monkeypatch, damage):
    output = scenario.root / "new"

    def interrupted(spec, destination, **kwargs):
        raise KeyboardInterrupt("模拟中断")

    monkeypatch.setattr(module, "run_fresh_process", interrupted)
    with pytest.raises(KeyboardInterrupt):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    attempt = next(output.rglob("attempt_0000"))
    if damage == "identity_missing":
        (attempt / "identity.json").unlink()
    else:
        (attempt / "unknown.txt").write_text("未知文件", encoding="utf-8")
    monkeypatch.setattr(module, "run_fresh_process", scenario.runner)
    with pytest.raises(RecordError):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    assert not scenario.calls


def test_old_recovery_schema_cannot_masquerade_as_interruption(scenario):
    output = scenario.root / "new"
    module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    state_path = output / "recertify_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["schema_version"] == 2
    state["schema_version"] = 1
    state_path.write_text(json.dumps(state), encoding="utf-8")
    count = len(scenario.calls)
    with pytest.raises(ReproducibilityError, match="恢复上下文"):
        module.recertify_suite(scenario.source, output, tasks=["BinFill"], episodes_per_task=1)
    assert len(scenario.calls) == count
