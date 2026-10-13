"""八档循环的父进程与伪池验证；不建真实环境，不启动 GPU worker。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from concurrent.futures import Future
from pathlib import Path

import pytest

from robomme_xhard.tests.test_jobs import new_gen
from robomme_xhard.tests.test_worker_evidence import worker_mock


ROOT = Path(__file__).resolve().parents[2]
GEN_PATH = ROOT / "scripts/data-generation-newSeed/generate_dataset_newseed.py"
CYCLE = "easy,medium,hard,xhard12,xhard14,xhard16,xhard18,xhard20"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("_mixed_cycle_gen", GEN_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_configs_load_without_package_initialization():
    code = (
        "import importlib.util,sys; "
        f"s=importlib.util.spec_from_file_location('_isolated_cycle_gen',{str(GEN_PATH)!r}); "
        "m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m); "
        "c=m._load_xhard_configs();assert len(c.DIFFICULTIES)==5; "
        "assert not any(k=='robomme_xhard' or k.startswith('robomme_xhard.') for k in sys.modules); "
        "assert 'torch' not in sys.modules"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("extra", [
    ["--difficulty", "211"], ["--difficulty", "xhard12"],
    ["--mother-manifest", "m.json"], ["--with-mother"], ["--mother-rank", "0"],
])
def test_cli_cycle_mutual_exclusion(gen, extra):
    with pytest.raises(SystemExit) as exc:
        gen._args(["--output-dir", "OUT", "--difficulty-cycle", CYCLE, *extra])
    assert exc.value.code == 2


def test_cli_defaults_and_stop_switch(gen):
    args = gen._args(["--output-dir", "OUT"])
    assert args.difficulty_ratio == "211"
    assert args.difficulty_cycle is None
    assert args.stop_on_pool_crash is False
    args = gen._args(["--output-dir", "OUT", "--difficulty-cycle", CYCLE, "--stop-on-pool-crash"])
    assert args.difficulty_cycle == CYCLE
    assert args.stop_on_pool_crash is True


def _job(gen, root, episode=0, task="VideoRepick", difficulty="xhard14"):
    return gen.EpisodeJob(task=task, episode=episode, attempt=0,
                          seed=gen.get_layout("train").seed(task, episode, 0),
                          difficulty=difficulty, output_root=str(root), repo_root=str(ROOT),
                          xhard_values=gen._load_xhard_configs().DIFFICULTIES, recovery=None)


def test_cycle_job_identity_and_bump(gen, tmp_path):
    job = _job(gen, tmp_path)
    assert job.is_xhard and job.cycle_mode and not job.fixed_seed
    assert job.gym_id == "VideoRepickXHard"
    assert job.card_role is job.make_name is job.source_difficulty is None
    assert job.recovery_mode is None
    bumped = job.bump(job.seed + 1)
    assert bumped.attempt == 1 and bumped.seed == job.seed + 1
    assert bumped.recovery == job.recovery and bumped.xhard_values == job.xhard_values
    base = gen.replace(job, difficulty="easy", recovery="z")
    assert not base.is_xhard and base.gym_id == "VideoRepick" and base.recovery_mode == "z"
    old = gen.replace(base, recovery="auto", xhard_values=())
    assert not old.cycle_mode and old.recovery_mode == "z"


@pytest.mark.parametrize("task,length,xy", [
    ("BinFill", 8, [8, 9, 10]), ("StopCube", 7, []),
    ("PickHighlight", 6, [6, 7, 8]), ("VideoPlaceButton", 5, [5, 6, 7]),
    ("VideoUnmask", 4, [4, 5, 6]), ("MoveCube", 3, []),
])
def test_recovery_absolute_episode_rank(gen, task, length, xy):
    configs = gen._load_xhard_configs()
    cycle = gen.filter_cycle(gen.parse_difficulty_cycle(CYCLE, configs.DIFFICULTIES),
                             configs.TIER_CONFIGS.get(task, {}))
    assert len(cycle) == length
    assigned = {mode: [e for e in range(400) if gen._cycle_recovery(task, e, cycle) == mode]
                for mode in ("z", "xy")}
    assert assigned["xy"] == xy
    assert assigned["z"] == ([0, 1, 2] if task in gen.FAIL_RECOVER_TASKS else [])
    for episode in range(400):
        if cycle[episode % length].startswith("xhard"):
            assert gen._cycle_recovery(task, episode, cycle) is None


def test_five_tasks_never_receive_recovery(gen):
    configs = gen._load_xhard_configs()
    cycle = gen.parse_difficulty_cycle(CYCLE, configs.DIFFICULTIES)
    for task in ("StopCube", "MoveCube", "InsertPeg", "PatternLock", "RouteStick"):
        effective = gen.filter_cycle(cycle, configs.TIER_CONFIGS.get(task, {}))
        assert all(gen._cycle_recovery(task, e, effective) is None for e in range(400))
    assert len(gen.FAIL_RECOVER_TASKS) == 11


def _generate_fake(gen, monkeypatch, root, **kwargs):
    root.mkdir()
    captured = {}

    def run(jobs, **options):
        captured.update(jobs=jobs, options=options)
        return [{"task": job.task, "episode": job.episode, "seed": job.seed,
                 "difficulty": job.difficulty, "ok": True} for job in jobs], []

    monkeypatch.setattr(gen, "_prepare_output", lambda value: Path(value))
    monkeypatch.setattr(gen, "_run_jobs", run)
    summary = gen.generate_dataset_newseed(root, episodes=8, difficulty_cycle=CYCLE, **kwargs)
    return captured, summary


def test_all_jobs_parameters_order_and_full_recovery_map(gen, monkeypatch, tmp_path):
    captured, summary = _generate_fake(gen, monkeypatch, tmp_path / "full")
    jobs = captured["jobs"]
    assert len(jobs) == 16 * 8
    assert tuple(dict.fromkeys(job.task for job in jobs)) == gen.TASK_ORDER
    parameters = json.loads((tmp_path / "full/run_parameters.json").read_text())
    assert parameters["tasks"] == list(gen.TASK_ORDER)
    assert parameters["difficulty_ratio"] is None
    assert parameters["difficulty_cycle"] == CYCLE.split(",")
    assert parameters["effective_cycles"]["MoveCube"] == ["easy", "medium", "hard"]
    assert parameters["recovery_assignment"]["BinFill"] == {"z": [0, 1, 2], "xy": [8, 9, 10]}
    assert captured["options"]["xhard_mode"] is True
    assert captured["options"]["stop_on_pool_crash"] is False
    assert summary["success_count"] == 128
    for job in jobs:
        assert job.seed == gen.get_layout("train").seed(job.task, job.episode, 0)
        assert job.difficulty == parameters["effective_cycles"][job.task][job.episode % len(parameters["effective_cycles"][job.task])]
        assert not job.fixed_seed


def test_slice_recovery_matches_full_sequence(gen, monkeypatch, tmp_path):
    full, _ = _generate_fake(gen, monkeypatch, tmp_path / "full", env="BinFill")
    # 单独从 ep8 起跑，其 xy 标签仍由全序列决定。
    root = tmp_path / "slice"
    root.mkdir()
    captured = {}
    monkeypatch.setattr(gen, "_run_jobs", lambda jobs, **options: (captured.setdefault("jobs", jobs) and [], []))
    gen.generate_dataset_newseed(root, env="BinFill", episodes=1, episode_start=8, difficulty_cycle=CYCLE)
    job = captured["jobs"][0]
    assert job.recovery_mode == "xy"
    assert job.difficulty == "easy"
    assert job.seed == gen.get_layout("train").seed("BinFill", 8, 0)
    assert json.loads((root / "run_parameters.json").read_text())["recovery_assignment"]["BinFill"] == {
        "z": [0, 1, 2], "xy": [8, 9, 10]}
    assert all(j.recovery_mode == "z" for j in full["jobs"][:3])


def _write_artifacts(gen, job):
    raw = gen._h5_path(Path(job.output_root), job)
    raw.parent.mkdir(exist_ok=True)
    raw.write_bytes("崩溃时未完成的H5".encode())
    videos = Path(job.output_root) / "videos"
    videos.mkdir(exist_ok=True)
    video = videos / (raw.stem + "_video.mp4")
    video.write_bytes("视频证据".encode())
    return raw, video


def test_crashed_artifacts_are_isolated_per_attempt(gen, tmp_path):
    job = _job(gen, tmp_path)
    raw, video = _write_artifacts(gen, job)
    result = gen._isolate_crashed_card(job)
    assert len(result["crashed_artifacts"]) == 2
    assert not raw.exists() and not video.exists()
    assert all(Path(p).exists() and Path(p).name.startswith("CRASHED_") for p in result["crashed_artifacts"])
    next_job = job.bump(job.seed + 1)
    new_raw, new_video = _write_artifacts(gen, next_job)
    gen._isolate_crashed_card(next_job)
    assert not new_raw.exists() and not new_video.exists()
    assert len(list((tmp_path / "hdf5_files").iterdir())) == 2


def _fake_pools(gen, monkeypatch, kind="broken", submit_break=False):
    pools = []
    submitted = []
    events = []

    class Process:
        def is_alive(self):
            return True

        def terminate(self):
            events.append("terminate")

        def join(self):
            events.append("join")

    class Pool:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.futures = []
            self._processes = {1: Process()}
            pools.append(self)

        def submit(self, func, job):
            submitted.append(job)
            _write_artifacts(gen, job)
            if submit_break:
                raise gen.BrokenProcessPool("提交时发现损坏")
            future = Future()
            if kind == "broken":
                future.set_exception(gen.BrokenProcessPool("伪池损坏"))
            else:
                future.set_result(gen._synth_failure(job, RuntimeError("伪失败"), kind))
            self.futures.append(future)
            return future

        def shutdown(self, **kwargs):
            events.append(("shutdown", kwargs))

    monkeypatch.setattr(gen, "ProcessPoolExecutor", Pool)
    # 每轮只报告一条损坏 Future，另一条必须通过池重建支路连带退回。
    monkeypatch.setattr(gen, "wait", lambda futures, **kwargs: ({futures[0]}, set(futures[1:])))
    return pools, submitted, events


def _run_pool(gen, root, jobs, **kwargs):
    return gen._run_jobs(jobs, gpu_ids=("0",), workers=2, layout_name="train",
                         jsonl_path=root / "episode_results.jsonl", max_attempts=100,
                         max_tasks_per_child=None, cpu_plan={"0": None}, **kwargs)


def test_pool_collateral_crashes_count_strikes(gen, monkeypatch, tmp_path):
    pools, submitted, _ = _fake_pools(gen, monkeypatch)
    jobs = [_job(gen, tmp_path, episode=e) for e in (0, 1)]
    succeeded, exhausted = _run_pool(gen, tmp_path, jobs)
    assert succeeded == [] and len(exhausted) == 2
    assert len(submitted) == 6
    for episode in (0, 1):
        assert sorted(job.attempt for job in submitted if job.episode == episode) == [0, 1, 2]
    records = [json.loads(line) for line in (tmp_path / "episode_results.jsonl").read_text().splitlines()]
    assert len(records) == 6
    assert all(len(row["crashed_artifacts"]) == 2 for row in records)
    assert all(p.name.startswith("CRASHED_") for p in (tmp_path / "hdf5_files").iterdir())


def test_non_task_failure_isolates_before_retry(gen, monkeypatch, tmp_path):
    _, submitted, _ = _fake_pools(gen, monkeypatch, kind="code")
    succeeded, exhausted = _run_pool(gen, tmp_path, [_job(gen, tmp_path)])
    assert not succeeded and len(exhausted) == 1
    assert [job.attempt for job in submitted] == [0, 1, 2]
    assert all(p.name.startswith("CRASHED_") for p in (tmp_path / "hdf5_files").iterdir())


@pytest.mark.parametrize("submit_break", [False, True])
def test_stop_on_first_pool_crash_terminates_all_pools(gen, monkeypatch, tmp_path, submit_break):
    pools, submitted, events = _fake_pools(gen, monkeypatch, submit_break=submit_break)
    jobs = [_job(gen, tmp_path, episode=e) for e in range(4)]
    with pytest.raises(gen.PoolCrashStopped) as caught:
        gen._run_jobs(jobs, gpu_ids=("0", "1"), workers=2, layout_name="train",
                      jsonl_path=tmp_path / "episode_results.jsonl", max_attempts=100,
                      max_tasks_per_child=None, cpu_plan={"0": None, "1": None},
                      stop_on_pool_crash=True)
    count = 1 if submit_break else 2
    assert len(pools) == 2 and len(submitted) == count
    assert events[:4] == ["terminate", "terminate", "join", "join"]
    assert all(event[1]["cancel_futures"] for event in events[4:])
    assert caught.value.succeeded == [] and len(caught.value.exhausted) == count
    assert all(p.name.startswith("CRASHED_") for p in (tmp_path / "hdf5_files").iterdir())


def test_cycle_task_failure_uses_all_100_formula_seeds(gen, monkeypatch, tmp_path):
    _, submitted, _ = _fake_pools(gen, monkeypatch, kind="task")
    job = _job(gen, tmp_path)
    succeeded, exhausted = _run_pool(gen, tmp_path, [job])
    assert not succeeded and len(exhausted) == 1
    assert [item.attempt for item in submitted] == list(range(100))
    assert [item.seed for item in submitted] == list(range(job.seed, job.seed + 100))
    records = [json.loads(line) for line in (tmp_path / "episode_results.jsonl").read_text().splitlines()]
    assert len(records) == 100 and records[-1]["attempt"] == 99
    assert all("crashed_artifacts" not in row for row in records)


def test_stop_summary_and_exit_code(gen, monkeypatch, tmp_path):
    root = tmp_path / "stopped"
    root.mkdir()
    monkeypatch.setattr(gen, "_prepare_output", lambda value: Path(value))

    def run(jobs, **kwargs):
        assert kwargs["stop_on_pool_crash"]
        success = {"task": jobs[0].task, "episode": jobs[0].episode, "seed": jobs[0].seed,
                   "difficulty": jobs[0].difficulty, "ok": True}
        raise gen.PoolCrashStopped([success], [])

    monkeypatch.setattr(gen, "_run_jobs", run)
    assert gen.main(["--output-dir", str(root), "--env", "BinFill", "--episodes", "8",
                     "--difficulty-cycle", CYCLE, "--stop-on-pool-crash"]) == 3
    summary = json.loads((root / "run_summary.json").read_text())
    assert summary["stopped_by"] == "pool_crash" and summary["success_count"] == 1
    assert summary["requested_count"] == 8


def test_initial_rejection_evidence_is_deep_copied(gen, tmp_path):
    job = _job(gen, tmp_path)
    rejection = {"reason": ["同形前提失败"]}
    exc = RuntimeError("初始化拒绝")
    exc.stage = "initialization"
    exc.rejection = types.SimpleNamespace(as_dict=lambda: rejection)
    exc.detail = {"pair": [1, 2]}
    evidence = gen._exception_evidence(exc, job)
    rejection["reason"].clear()
    exc.detail["pair"].clear()
    assert evidence["stage"] == "initialization"
    assert evidence["rejection"] == {"reason": ["同形前提失败"]}
    assert evidence["detail"] == {"pair": [1, 2]}
    assert gen._exception_evidence(exc, gen.replace(job, xhard_values=(), recovery="auto")) == {}


def test_cycle_worker_copies_all_evidence_before_close(new_gen, worker_mock, monkeypatch):
    state, old_job, _ = worker_mock
    job = new_gen.replace(old_job, card_role=None, make_name=None, source_difficulty=None,
                          xhard_values=("xhard20",), recovery=None)
    state.u._xhard_swap_plan = {"pairs": [{"a": 0, "b": 1}]}
    state.u._xhard_runtime_checks = [{"kind": "swap_sweep"}]
    state.u.xhard_knobs = {"swap_count": 20}
    state.u.xhard_label = "xhard20"
    wrapper = sys.modules["robomme.env_record_wrapper"].RobommeRecordWrapper
    old_close = wrapper.close

    def close(self):
        old_close(self)
        state.u._xhard_runtime_checks.clear()
        state.u.xhard_knobs.clear()
        state.u.xhard_label = "已释放"

    monkeypatch.setattr(wrapper, "close", close)
    result = new_gen._worker(job)
    assert result["ok"]
    assert result["swap_plan"]["pairs"] == [{"a": 0, "b": 1}]
    assert result["runtime_checks"] == [{"kind": "swap_sweep"}]
    assert result["xhard_knobs"] == {"swap_count": 20}
    assert result["xhard_label"] == "xhard20"


def test_cycle_worker_runtime_rejection_keeps_failed_artifacts(new_gen, worker_mock):
    state, old_job, _ = worker_mock
    job = new_gen.replace(old_job, card_role=None, make_name=None, source_difficulty=None,
                          xhard_values=("xhard20",), recovery=None)
    fatal = {"error_type": "SwapCollisionError", "stage": "segment_start", "k": 1,
             "rejection": {"gap": -0.01}}
    state.u._xhard_fatal = fatal
    result = new_gen._worker(job)
    assert result["ok"] is False and result["task_success"] is False
    assert result["failure_class"] == "task" and result["detail"] == fatal
    assert len(result["failed_artifacts"]) == 2
    assert all(Path(path).exists() and Path(path).name.startswith("FAILED_")
               for path in result["failed_artifacts"])


def test_cycle_worker_initial_rejection_preserves_fields(new_gen, worker_mock):
    state, old_job, error_class = worker_mock
    job = new_gen.replace(old_job, card_role=None, make_name=None, source_difficulty=None,
                          xhard_values=("xhard20",), recovery=None)
    exc = error_class("初始化拒绝")
    exc.stage = "initial"
    exc.rejection = types.SimpleNamespace(as_dict=lambda: {"gap": -0.1})
    exc.detail = {"reason": "碰撞"}
    state.make_error = exc
    result = new_gen._worker(job)
    assert result["ok"] is False and result["failure_class"] == "task"
    assert result["stage"] == "initial" and result["rejection"] == {"gap": -0.1}
    assert result["detail"] == {"reason": "碰撞"}
