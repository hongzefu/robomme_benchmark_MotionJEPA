"""生成器真实 worker 的 CPU 替身链路与崩溃产物隔离。"""

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import h5py
import pytest

from robomme_xhard.tests.test_jobs import new_gen, _drive


def card(gen, tmp_path):
    return gen.EpisodeJob("VideoUnmaskSwap", 7, 0, 5700, "xhard20",
                          str(tmp_path / "xhard20"), str(gen.REPO_ROOT),
                          "xhard", "VideoUnmaskSwapXHard", "hard")


@pytest.fixture
def worker_mock(new_gen, monkeypatch, tmp_path):
    """仅在测试进程替换导入与录像器，不启动仿真。"""
    import gymnasium
    from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError

    u = SimpleNamespace(agent=SimpleNamespace(robot=SimpleNamespace(pose=None)))
    state = SimpleNamespace(u=u, make_error=None, solve_error=None)
    monkeypatch.setattr(gymnasium, "make", lambda *a, **kw: make())

    def make():
        if state.make_error:
            raise state.make_error
        return u

    class Wrapper:
        def __init__(self, env, **kw):
            self.unwrapped = env
            self.save_video = True

        def reset(self):
            pass

        def close(self):
            # 模拟释放时修改证据，检查 worker 已做独立复制。
            if hasattr(u, "_xhard_swap_plan"):
                u._xhard_swap_plan["pairs"].clear()
            path = new_gen._h5_path(Path(job.output_root), job)
            path.parent.mkdir(parents=True, exist_ok=True)
            with h5py.File(path, "w") as f:
                f.create_group("episode_7")
            video = Path(job.output_root) / "videos" / (path.stem + "_hard.mp4")
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes("本卡视频".encode())

    wrappers = ModuleType("robomme.env_record_wrapper")
    wrappers.FailsafeTimeout = type("FailsafeTimeout", (RuntimeError,), {})
    wrappers.RobommeRecordWrapper = Wrapper
    monkeypatch.setitem(sys.modules, wrappers.__name__, wrappers)
    monkeypatch.setattr(new_gen, "_planner_classes", lambda *a: (lambda *a, **kw: None,) * 2)

    def solve(*args):
        if state.solve_error:
            raise state.solve_error

    monkeypatch.setattr(new_gen, "_execute_tasks", solve)
    monkeypatch.setattr(new_gen, "_raw_summary", lambda p, j: {
        "h5_path": str(p), "timestep_count": 1, "task_success": True})
    job = card(new_gen, tmp_path)
    return state, job, SceneGenerationError


@pytest.mark.parametrize("has_evidence", [False, True])
def test_worker_copies_evidence_before_close(new_gen, worker_mock, has_evidence):
    state, job, _ = worker_mock
    if has_evidence:
        state.u._xhard_swap_plan = {"pairs": [{"a": 0, "b": 1}]}
        state.u._xhard_runtime_checks = [{"kind": "swap_sweep"}]
    result = new_gen._worker(job)
    assert result["ok"]
    assert result["task_success"] is True
    if has_evidence:
        assert result["swap_plan"]["pairs"] == [{"a": 0, "b": 1}]
        assert result["runtime_checks"] == [{"kind": "swap_sweep"}]
    else:
        assert "swap_plan" not in result and "runtime_checks" not in result


def test_make_rejection_uses_exception_fields(new_gen, worker_mock):
    state, job, scene_error = worker_mock
    class SwapCollisionError(scene_error):
        pass
    exc = SwapCollisionError("拒绝")
    exc.stage = "initial"
    exc.rejection = SimpleNamespace(as_dict=lambda: {"gap": -0.1})
    exc.detail = {"reason": "碰撞"}
    state.make_error = exc
    result = new_gen._worker(job)
    assert (result["ok"], result["failure_class"], result["stage"]) == (False, "task", "initial")
    assert result["rejection"] == {"gap": -0.1}
    assert result["detail"] == {"reason": "碰撞"}
    assert "swap_plan" not in result


@pytest.mark.parametrize("stage", ["segment_start", "substep_before", "substep_after"])
def test_runtime_fatal_is_task_failure_and_preserves_artifacts(new_gen, worker_mock, stage):
    state, job, _ = worker_mock
    fatal = {"error_type": "SwapCollisionError", "stage": stage, "k": 1,
             "rejection": {"gap": -0.01}, "control_step": 42}
    state.u._xhard_fatal = fatal
    result = new_gen._worker(job)
    assert (result["ok"], result["task_success"], result["failure_class"]) == (False, False, "task")
    assert result["stage"] == stage and result["detail"] == fatal
    assert result["rejection"] == fatal["rejection"]
    assert result["traceback"] is None
    assert len(result["failed_artifacts"]) == 2
    assert all(Path(p).name.startswith("FAILED_") and Path(p).is_file()
               for p in result["failed_artifacts"])
    assert not new_gen._h5_path(Path(job.output_root), job).exists()


def test_crash_written_card_quarantines_without_requeue(new_gen, monkeypatch, tmp_path):
    job = card(new_gen, tmp_path)
    raw = new_gen._h5_path(Path(job.output_root), job)
    raw.parent.mkdir(parents=True)
    with h5py.File(raw, "w") as f:
        f.create_group("episode_7")
    video = raw.parent.parent / "videos" / (raw.stem + "_hard.mp4")
    video.parent.mkdir()
    video.write_bytes("保留证据".encode())
    neighbor = video.with_name(video.name.replace("seed5700", "seed57000"))
    neighbor.write_bytes("他卡".encode())
    script = {(job.task, job.episode, job.difficulty): [new_gen.BrokenProcessPool("写完后崩溃")]}
    ok, failed, submitted, lines = _drive(new_gen, monkeypatch, tmp_path, [job], script, 1)
    assert not ok and submitted == [job]
    assert failed[0]["quarantined"] and failed[0]["failure_class"] == "infra"
    assert failed[0]["seed"] == 5700 and failed[0]["attempt"] == 0
    assert len(failed[0]["quarantine_files"]) == 2
    assert all(Path(p).exists() for p in failed[0]["quarantine_files"])
    assert not raw.exists() and not video.exists() and neighbor.exists()
    assert lines[0]["quarantine_path"] == failed[0]["quarantine_path"]


def test_quarantine_refuses_overwrite(new_gen, tmp_path):
    job = card(new_gen, tmp_path)
    raw = new_gen._h5_path(Path(job.output_root), job)
    raw.parent.mkdir(parents=True)
    with h5py.File(raw, "w") as f:
        f.create_group("episode_7")
    destination = Path(job.output_root).parent / "_quarantine" / ("xhard20_" + raw.stem)
    destination.mkdir(parents=True)
    with pytest.raises(new_gen.DatasetGenerationError):
        new_gen._quarantine_written_card(job)
    assert raw.exists()


@pytest.mark.parametrize("prefix", ["", "FAILED_", "success_NO_OBJECT_", "FAILED_NO_OBJECT_"])
def test_crash_h5_shell_with_video_quarantines_without_requeue(new_gen, monkeypatch, tmp_path, prefix):
    """可读空壳不能掩盖同卡已写或半写视频，邻卡证据不动。"""
    job = card(new_gen, tmp_path)
    raw = new_gen._h5_path(Path(job.output_root), job)
    raw.parent.mkdir(parents=True)
    with h5py.File(raw, "w"):
        pass
    video = raw.parent.parent / "videos" / (prefix + raw.stem + "_hard.mp4")
    video.parent.mkdir()
    video.write_bytes(b"partial-video")
    neighbor = video.with_name(video.name.replace("seed5700", "seed57000"))
    neighbor.write_bytes(b"neighbor")
    script = {(job.task, job.episode, job.difficulty): [new_gen.BrokenProcessPool("视频写入后崩溃")]}
    ok, failed, submitted, lines = _drive(new_gen, monkeypatch, tmp_path, [job], script, 1)
    assert not ok and submitted == [job] and len(failed) == len(lines) == 1
    assert failed[0]["quarantined"] and failed[0]["failure_class"] == "infra"
    assert len(failed[0]["quarantine_files"]) == 2
    assert all(Path(p).exists() for p in failed[0]["quarantine_files"])
    assert not raw.exists() and not video.exists()
    assert neighbor.read_bytes() == b"neighbor"
    saved_video = next(Path(p) for p in failed[0]["quarantine_files"] if p.endswith(".mp4"))
    assert saved_video.read_bytes() == b"partial-video"


@pytest.mark.parametrize("task_success", [False, None])
def test_summary_preserves_every_evidence_field(new_gen, monkeypatch, tmp_path, task_success):
    manifest = tmp_path / "mother.json"
    manifest.write_text(json.dumps({"version": 1, "tasks": {"VideoUnmaskSwap": [
        {"episode": 7, "seed": 5700, "source_difficulty": "hard", "rank": 0}]}}))
    output = tmp_path / "output"
    monkeypatch.setattr(new_gen, "_prepare_output", lambda value: Path(value))
    output.mkdir()
    evidence = {"error_type": "SwapCollisionError", "stage": "segment_start",
                "rejection": {"gap": -0.01}, "detail": {"k": 1},
                "swap_plan": {"pairs": [{"a": 0, "b": 1}]},
                "runtime_checks": [{"kind": "swap_sweep"}],
                "failed_artifacts": ["FAILED_轨迹.h5"]}

    def run(jobs, **kwargs):
        job = jobs[0]
        result = {"task": job.task, "episode": job.episode, "seed": job.seed,
                  "difficulty": job.difficulty, "ok": False, "task_success": task_success, "failure_class": "task",
                  "error": "拒绝", **evidence}
        kwargs["jsonl_path"].write_text(json.dumps(result) + "\n")
        return [], [result]

    monkeypatch.setattr(new_gen, "_run_jobs", run)
    summary = new_gen.generate_dataset_newseed(output_dir=str(output), env="VideoUnmaskSwap",
                                               difficulty_ratio="xhard20",
                                               mother_manifest=str(manifest), mother_rank=0)
    row = summary["cards"][0]
    assert row["ok"] is False and row["task_success"] is task_success
    assert {key: row[key] for key in evidence} == evidence
    disk = json.loads((output / "run_summary.json").read_text())["cards"][0]
    assert {key: disk[key] for key in evidence} == evidence
    assert disk["task_success"] is task_success


def test_raw_summary_returns_checked_terminal_success(new_gen, monkeypatch, tmp_path):
    job = card(new_gen, tmp_path)
    raw = new_gen._h5_path(Path(job.output_root), job)
    raw.parent.mkdir(parents=True)
    with h5py.File(raw, "w") as f:
        f.create_group("episode_7")
    monkeypatch.setattr(new_gen, "inspect_episode_terminal", lambda *a: (["timestep_0"], True, []))
    assert new_gen._raw_summary(raw, job)["task_success"] is True
    monkeypatch.setattr(new_gen, "inspect_episode_terminal", lambda *a: (["timestep_0"], False, []))
    with pytest.raises(new_gen.DatasetGenerationError):
        new_gen._raw_summary(raw, job)


def test_terminal_error_propagates_false_to_worker_and_jsonl(new_gen, worker_mock, monkeypatch, tmp_path):
    _, job, _ = worker_mock
    def bad_summary(*args):
        raise new_gen.DatasetGenerationError("末帧失败")
    monkeypatch.setattr(new_gen, "_raw_summary", bad_summary)
    result = new_gen._worker(job)
    assert result["ok"] is False and result["task_success"] is False
    assert result["failure_class"] == "task" and result["error_type"] == "DatasetGenerationError"
    script = {(job.task, job.episode, job.difficulty): [result]}
    _, failed, submitted, lines = _drive(new_gen, monkeypatch, tmp_path, [job], script, 1)
    assert submitted == [job]
    assert failed[0]["task_success"] is False and lines[0]["task_success"] is False


def test_failed_artifacts_refuses_overwrite(new_gen, tmp_path):
    job = card(new_gen, tmp_path)
    raw = new_gen._h5_path(Path(job.output_root), job)
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"h5")
    target = raw.with_name("FAILED_" + raw.name)
    target.write_bytes(b"old")
    with pytest.raises(new_gen.DatasetGenerationError):
        new_gen._mark_failed_artifacts(job)
    assert raw.read_bytes() == b"h5" and target.read_bytes() == b"old"


def test_nonempty_corrupt_h5_is_quarantined(new_gen, tmp_path):
    job = card(new_gen, tmp_path)
    raw = new_gen._h5_path(Path(job.output_root), job)
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"half-written-h5")
    result = new_gen._quarantine_written_card(job)
    assert result["quarantined"] is True
    assert Path(result["quarantine_files"][0]).read_bytes() == b"half-written-h5"
    assert not raw.exists()


def test_readable_h5_shell_keeps_infra_retry_semantics(new_gen, tmp_path):
    job = card(new_gen, tmp_path)
    raw = new_gen._h5_path(Path(job.output_root), job)
    raw.parent.mkdir(parents=True)
    with h5py.File(raw, "w"):
        pass
    assert new_gen._quarantine_written_card(job) == {}
    assert raw.exists()


def test_quarantine_refuses_symlink_destination(new_gen, tmp_path):
    job = card(new_gen, tmp_path)
    raw = new_gen._h5_path(Path(job.output_root), job)
    raw.parent.mkdir(parents=True)
    with h5py.File(raw, "w") as f:
        f.create_group("episode_7")
    other = tmp_path / "other"
    other.mkdir()
    (tmp_path / "_quarantine").symlink_to(other, target_is_directory=True)
    with pytest.raises(new_gen.DatasetGenerationError):
        new_gen._quarantine_written_card(job)
    assert raw.exists() and list(other.iterdir()) == []
