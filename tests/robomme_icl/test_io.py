"""使用伪环境验证记录、篡改检测和同 seed 断点重试，不加载仿真。"""

from dataclasses import dataclass
import copy
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import types
import threading

import h5py
import numpy as np
import pytest

from robomme_icl.io.hdf5 import (
    RecordError,
    ReproducibilityError,
    assert_identical,
    read_episode,
    tree_hash,
    write_episode,
)
from robomme_icl.io.paths import output_path, repository_root
from robomme_icl.workflows.generate import generate_one
from robomme_icl.workflows.workers import retry_same_spec


@pytest.fixture
def local_dir():
    """测试产物同样留在仓库；只清理本 fixture 创建的临时目录。"""
    cache = repository_root() / ".cache" / "robomme_icl_tests"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix="io-") as directory:
        yield Path(directory)


@dataclass(frozen=True)
class FakeSpec:
    seed: int = 1900000001
    env_id: str = "RoboMME-ICL/BinFill-v0"
    task_kind: str = "BinFill"

    @property
    def spec_hash(self):
        return tree_hash({"seed": self.seed, "env_id": self.env_id})

    def to_dict(self):
        return {"seed": self.seed, "env_id": self.env_id, "spec_hash": self.spec_hash}

    @classmethod
    def from_dict(cls, value):
        return cls(seed=value["seed"], env_id=value["env_id"])


class FakeEnv:
    """输出包含 RGB、零维数组、不同浮点类型和 actor 路径名的帧。"""

    def frames(self):
        return [
            {
                "observation": {
                    "base_rgb": np.arange(18, dtype=np.uint8).reshape(2, 3, 3),
                    "wrist_rgb": np.zeros((1, 1, 3), dtype=np.uint8),
                    "qpos": np.array([0.1, -0.0], dtype=np.float64),
                    "qvel": np.array([0.0, 0.0], dtype=np.float32),
                    "actor_poses": {"cube/target": np.arange(7, dtype=np.float64)},
                    "scalar": np.asarray(1.0, dtype=">f4"),
                },
                "joint_action": None,
                "info": {
                    "success": True,
                    "fail": False,
                    "is_demonstration": False,
                    "phase": "evaluation",
                    "step": 0,
                    "task_events": ["完成"],
                    "operation": "reset_complete",
                    "geometry_report": {"ok": True},
                    "numpy_flag": np.bool_(True),
                    "tuple": (1, "x"),
                    "raw": b"\x00\xff",
                },
            }
        ]


def test_hdf5_roundtrip_preserves_every_dtype_shape_and_byte(local_dir):
    spec, frames = FakeSpec(), FakeEnv().frames()
    path = write_episode(local_dir / "episode.h5", spec, frames)
    actual = read_episode(path)
    assert actual.spec_hash == spec.spec_hash
    assert_identical(spec.to_dict(), actual.episode_spec)
    assert_identical(frames, actual.frames)


def test_hdf5_packed_native_state_roundtrip(local_dir):
    """走完整文件写入、摘要复核和读取链路，确认打包保留原版状态。"""
    spec, frames = FakeSpec(), FakeEnv().frames()
    frames[0]["native_state"] = {
        "actor/target": {
            "pose": np.array([-0.0, 0.2, 1.0], dtype=">f8"),
            "visible": np.bool_(True),
            "events": ("显现", 32),
        }
    }
    path = write_episode(local_dir / "packed.h5", spec, frames)
    with h5py.File(path, "r") as handle:
        nodes = []
        handle.visititems(
            lambda name, node: nodes.append(node.name)
            if node.attrs.get("kind") == "packed_tree_v1"
            else None
        )
        assert len(nodes) == 1
    actual = read_episode(path)
    assert_identical(frames, actual.frames)


def test_tampered_rgb_is_rejected_and_file_preserved(local_dir):
    path = write_episode(local_dir / "episode.h5", FakeSpec(), FakeEnv().frames())
    with h5py.File(path, "r+") as handle:
        handle["steps/00000000/observation/base_rgb"][0, 0, 0] = 255
    with pytest.raises(RecordError, match="摘要不匹配"):
        read_episode(path)
    assert path.exists()


def test_setup_seed_tampering_is_rejected(local_dir):
    path = write_episode(local_dir / "episode.h5", FakeSpec(), FakeEnv().frames())
    with h5py.File(path, "r+") as handle:
        handle["setup/seed"][()] = 5
    with pytest.raises(RecordError, match="setup seed"):
        read_episode(path)


def test_strict_compare_rejects_dtype_shape_and_signed_zero():
    with pytest.raises(ReproducibilityError, match="dtype/shape"):
        assert_identical(np.ones(1, dtype=np.float32), np.ones(1, dtype=np.float64))
    with pytest.raises(ReproducibilityError, match="dtype/shape"):
        assert_identical(np.ones(1), np.ones((1, 1)))
    with pytest.raises(ReproducibilityError, match="字节不同"):
        assert_identical(np.array([-0.0]), np.array([0.0]))


def test_generation_retry_and_resume_keep_identical_spec_seed(local_dir):
    spec = FakeSpec()
    calls = []

    def runner(candidate, path):
        calls.append((candidate.seed, candidate.spec_hash))
        if len(calls) == 1:
            raise OSError("模拟进程临时失败")
        return write_episode(path, candidate, FakeEnv().frames())

    path = local_dir / "episode.h5"
    first = generate_one(spec, path, runner=runner)
    second = generate_one(spec, path, runner=runner)
    assert calls == [(spec.seed, spec.spec_hash)] * 2
    assert first["resumed"] is False and second["resumed"] is True
    assert first["content_hash"] == second["content_hash"]


def test_incomplete_resume_stops_without_overwrite(local_dir):
    path = local_dir / "incomplete.h5"
    with h5py.File(path, "x") as handle:
        handle.attrs["schema_version"] = 2
        handle.attrs["complete"] = False
    before = path.read_bytes()
    with pytest.raises(RecordError, match="不完整"):
        generate_one(FakeSpec(), path)
    assert path.read_bytes() == before


def test_generation_mismatch_stops_and_preserves_evidence(local_dir):
    path = local_dir / "episode.h5"
    with pytest.raises(ReproducibilityError, match="认证内容不同"):
        generate_one(
            FakeSpec(),
            path,
            runner=lambda spec, destination: write_episode(
                destination, spec, FakeEnv().frames()
            ),
            expected_content_hash="invalid",
        )
    assert not path.exists()
    assert (path.parent / ".staging" / path.name / "attempt_0000.h5").exists()


def test_non_infra_exception_is_never_retried():
    calls = []

    def operation(spec):
        calls.append(spec.seed)
        raise ValueError("配置错误不能重试")

    with pytest.raises(ValueError):
        retry_same_spec(FakeSpec(), operation)
    assert calls == [FakeSpec().seed]


def test_output_symlink_and_repository_escape_are_rejected(local_dir):
    link = local_dir / "link"
    link.symlink_to(local_dir, target_is_directory=True)
    with pytest.raises(ValueError, match="符号链接"):
        output_path(link / "episode.h5")
    with pytest.raises(ValueError, match="仓库内"):
        output_path(repository_root().parent / "outside.h5")


def _fake_suite(monkeypatch):
    """只替换清单编译入口，仍然跑真实认证调度及 HDF5 往返。"""
    module = types.ModuleType("robomme_icl.suite")
    module.load_configs = lambda *_: ({}, {})
    module.plan_slots = lambda *_, **__: [
        {"slot_id": "BinFill-easy-0", "max_candidates": 3, "seed": 1900000001}
    ]
    module.candidate_for_slot = lambda _, index: FakeSpec(seed=1900000001 + index)
    module.EpisodeSpec = FakeSpec
    saved = []

    def save(path, specs, configs, certification):
        saved.append((specs, certification))
        path.write_text("已认证", encoding="utf-8")

    module.save_suite = save
    monkeypatch.setitem(sys.modules, "robomme_icl.suite", module)
    from robomme_icl.workflows import prepare as pipeline, workers
    from robomme_icl import config
    from robomme_icl.sampling import tasks, compiler
    from robomme_icl.io import suite as storage

    monkeypatch.setattr(
        config, "load_configs", lambda *args: module.load_configs(*args)
    )
    monkeypatch.setattr(
        tasks, "plan_slots", lambda *args, **kwargs: module.plan_slots(*args, **kwargs)
    )
    monkeypatch.setattr(
        compiler, "candidate_for_slot", lambda *args: module.candidate_for_slot(*args)
    )
    monkeypatch.setattr(storage, "save_suite", save)
    monkeypatch.setattr(pipeline, "EpisodeSpec", FakeSpec)
    monkeypatch.setattr(
        pipeline,
        "runtime_fingerprint",
        lambda **kwargs: {"testing": "fixed", "render_gpu": kwargs.get("render_gpu")},
    )
    monkeypatch.setattr(pipeline, "source_commit", lambda: "测试基线")
    monkeypatch.setattr(
        pipeline,
        "new_manager",
        lambda: nullcontext(
            types.SimpleNamespace(
                Event=threading.Event, BoundedSemaphore=threading.BoundedSemaphore
            )
        ),
    )
    monkeypatch.setattr(
        workers,
        "ProcessPoolExecutor",
        lambda **kwargs: ThreadPoolExecutor(max_workers=min(kwargs["max_workers"], 2)),
    )
    return saved


def test_prepare_rejects_geometry_then_certifies_same_slot_candidate(
    local_dir, monkeypatch
):
    from robomme_icl.workflows import prepare as pipeline

    saved = _fake_suite(monkeypatch)
    calls = []

    def run(spec, destination, **_):
        if spec.seed == 1900000001:
            from robomme_icl.errors import CandidateRejected

            raise CandidateRejected("模拟真实初始碰撞")
        calls.append((spec.seed, spec.spec_hash))
        return write_episode(
            destination,
            spec,
            FakeEnv().frames(),
            runtime_fingerprint={"testing": "fixed", "render_gpu": 1},
        )

    monkeypatch.setattr(pipeline, "run_episode_process", run)
    manifest = pipeline.prepare_suite(local_dir / "prepared", max_candidates=3)
    assert manifest.exists()
    assert calls == [(1900000002, FakeSpec(seed=1900000002).spec_hash)] * 2
    assert len(saved) == 1 and saved[0][0][0].seed == 1900000002
    assert (
        manifest.parent / "certification/BinFill-easy-0/candidate_0000/rejected.json"
    ).exists()


def test_prepare_reproducibility_mismatch_never_tries_next_candidate(
    local_dir, monkeypatch
):
    from robomme_icl.workflows import prepare as pipeline

    saved = _fake_suite(monkeypatch)
    calls = []

    def run(spec, destination, **_):
        calls.append(spec.seed)
        frames = FakeEnv().frames()
        frames[0]["observation"]["base_rgb"][0, 0, 0] = len(calls)
        return write_episode(
            destination,
            spec,
            frames,
            runtime_fingerprint={"testing": "fixed", "render_gpu": 1},
        )

    monkeypatch.setattr(pipeline, "run_episode_process", run)
    with pytest.raises(ReproducibilityError, match="字节不同"):
        pipeline.prepare_suite(local_dir / "prepared", max_candidates=3)
    assert calls == [1900000001, 1900000001]
    assert saved == []
    assert not (local_dir / "prepared/suite.json").exists()


def test_runtime_fingerprint_is_part_of_hdf5_integrity(local_dir):
    path = write_episode(
        local_dir / "episode.h5",
        FakeSpec(),
        FakeEnv().frames(),
        runtime_fingerprint={"driver": "固定版本"},
        source_commit="首次提交",
    )
    original = read_episode(path)
    assert original.runtime_fingerprint == {"driver": "固定版本"}
    # 留档提交不同不改变帧数据认证；运行指纹不同则必须拒绝。
    with h5py.File(path, "r+") as handle:
        handle["setup/source_commit"][()] = "报告提交"
    assert read_episode(path).content_hash == original.content_hash
    with h5py.File(path, "r+") as handle:
        handle["setup/runtime_fingerprint"][()] = '{"driver":"其他版本"}'
    with pytest.raises(RecordError, match="摘要不匹配"):
        read_episode(path)


def test_public_cli_flags_match_approved_interface(monkeypatch):
    monkeypatch.syspath_prepend(str(repository_root() / "scripts"))
    import prepare_suite
    import generate_dataset
    import replay_dataset
    import plot_distribution

    prepare = prepare_suite.build_parser().parse_args(
        [
            "--output-dir",
            "artifacts/prepared",
            "--tasks",
            "BinFill",
            "--episodes-per-task",
            "1",
        ]
    )
    assert prepare.output_dir == Path("artifacts/prepared") and prepare.tasks == [
        "BinFill"
    ]
    assert (
        prepare.gpus is None
        and prepare.workers == 32
        and prepare.timeout_seconds == 1200
    )
    replay = replay_dataset.build_parser().parse_args(
        ["--input", "artifacts/input.h5", "--output-dir", "artifacts/replayed"]
    )
    assert replay.input == Path("artifacts/input.h5")
    generate = generate_dataset.build_parser().parse_args(
        ["--suite", "artifacts/suite.json", "--output-dir", "artifacts/generated"]
    )
    assert generate.output_dir == Path("artifacts/generated")
    assert generate.video_workers == replay.video_workers == 4
    plot = plot_distribution.build_parser().parse_args(
        ["--suite", "artifacts/suite.json", "--output-dir", "artifacts/plots"]
    )
    assert plot.output_dir == Path("artifacts/plots")


def test_public_api_uses_certified_spec_and_forwards_wrapper_options(monkeypatch):
    from robomme_icl import api, suite
    from robomme_icl.io import fingerprint

    spec = FakeSpec()
    catalog = {
        "certification": {
            spec.spec_hash: {"runtime_fingerprint": {"fixed": True}, "render_gpu": 1}
        }
    }
    monkeypatch.setattr(api, "configure_runtime", lambda: None)
    monkeypatch.setattr(suite, "load_suite", lambda path: catalog)
    seen = []

    def find(value, *, task, seed):
        assert value is catalog and (task, seed) == (spec.task_kind, spec.seed)
        return spec

    monkeypatch.setattr(suite, "find_spec", find)
    monkeypatch.setattr(
        fingerprint, "runtime_fingerprint", lambda **kwargs: {"fixed": True}
    )
    monkeypatch.setattr(
        api,
        "make_env_from_spec",
        lambda value, **kwargs: seen.append((value, kwargs)) or "新环境",
    )
    assert (
        api.make_env(
            task=spec.task_kind,
            seed=spec.seed,
            suite="suite.json",
            record_demonstration=False,
        )
        == "新环境"
    )
    assert seen == [(spec, {"record_demonstration": False, "render_gpu": 1})]
    with pytest.raises(ValueError, match="不能更改"):
        api.make_env(
            task=spec.task_kind, seed=spec.seed, suite="suite.json", render_gpu=0
        )
    assert len(seen) == 1


def test_public_api_rejects_changed_runtime_before_creating_environment(monkeypatch):
    from robomme_icl import api, suite
    from robomme_icl.errors import ReproducibilityError as PublicReproducibilityError
    from robomme_icl.io import fingerprint

    spec = FakeSpec()
    monkeypatch.setattr(api, "configure_runtime", lambda: None)
    monkeypatch.setattr(
        suite,
        "load_suite",
        lambda _: {
            "certification": {
                spec.spec_hash: {
                    "runtime_fingerprint": {"driver": "原版本"},
                    "render_gpu": 0,
                }
            }
        },
    )
    monkeypatch.setattr(suite, "find_spec", lambda *args, **kwargs: spec)
    monkeypatch.setattr(
        fingerprint, "runtime_fingerprint", lambda **kwargs: {"driver": "新版本"}
    )
    monkeypatch.setattr(
        api,
        "make_env_from_spec",
        lambda *_, **__: pytest.fail("指纹错误时禁止创建环境"),
    )
    with pytest.raises(PublicReproducibilityError, match="指纹不同"):
        api.make_env(task=spec.task_kind, seed=spec.seed, suite="suite.json")


def test_config_and_api_import_do_not_register_legacy_tasks():
    """在新 uv 子进程验证真实导入边界，不受其他测试导入顺序影响。"""
    uv = shutil.which("uv")
    assert uv is not None, "必须由 uv 启动隔离验证"
    code = "\n".join(
        [
            "import sys",
            f"sys.path.insert(0, {str(repository_root() / 'scripts')!r})",
            "import robomme_icl.api, robomme_icl.suite",
            "import prepare_suite, generate_dataset, replay_dataset, plot_distribution",
            "assert not any(name.startswith('robomme.robomme_env') for name in sys.modules)",
            "assert 'torch' not in sys.modules",
            "assert 'sapien' not in sys.modules",
            "assert 'gymnasium' not in sys.modules",
        ]
    )
    result = subprocess.run(
        [uv, "run", "--no-sync", "python", "-c", code],
        cwd=repository_root(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_replay_restores_demo_and_drives_only_recorded_evaluation_actions(
    local_dir, monkeypatch
):
    from robomme_icl.validation.reproducibility import replay_frames

    initial = FakeEnv().frames()[0]
    initial["info"]["success"] = False
    physical = copy.deepcopy(initial)
    physical["info"].update(operation="step", step=1)
    physical["joint_action"] = np.linspace(0, 1, 8)
    terminal = copy.deepcopy(physical)
    terminal["joint_action"] = None
    terminal["info"].update(
        operation="evaluate", solve_complete_eval=True, success=True
    )
    expected = types.SimpleNamespace(frames=[initial, physical, terminal])
    actions = []

    class Recorder:
        def __init__(self):
            self.frames = []

        def step(self, action):
            actions.append(action.copy())
            self.frames.append(copy.deepcopy(physical))

        def evaluate(self, *, solve_complete_eval):
            assert solve_complete_eval is True
            self.frames.append(copy.deepcopy(terminal))

    class ReplayEnv:
        def __init__(self):
            self.recorder = Recorder()
            self.native_wrapper = self.recorder

        def reset(self):
            self.recorder.frames = [copy.deepcopy(initial)]

    result = replay_frames(ReplayEnv(), expected)
    assert_identical(expected.frames, result)
    assert len(actions) == 1
    assert_identical(actions[0], physical["joint_action"])


def _write_partial(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "x") as handle:
        handle.attrs["schema_version"] = 2
        handle.attrs["complete"] = False
        handle.create_dataset("partial", data=np.arange(3))


def test_partial_generation_retries_same_seed_in_new_staging_and_publishes_only_complete(
    local_dir,
):
    spec, calls = FakeSpec(), []
    final = local_dir / "episode.h5"
    partial_bytes = []

    def runner(candidate, path):
        assert not final.exists(), "完整校验之前不允许发布最终路径"
        calls.append((candidate.seed, candidate.spec_hash, path))
        if len(calls) == 1:
            _write_partial(path)
            partial_bytes.append(path.read_bytes())
            raise OSError("模拟 HDF5 写到一半进程崩溃")
        return write_episode(path, candidate, FakeEnv().frames())

    result = generate_one(spec, final, runner=runner)
    assert [entry[:2] for entry in calls] == [(spec.seed, spec.spec_hash)] * 2
    assert calls[0][2] != calls[1][2] and all(entry[2] != final for entry in calls)
    assert calls[0][2].read_bytes() == partial_bytes[0]
    assert read_episode(final).content_hash == result["content_hash"]
    assert calls[1][2].exists(), "成功 staging 也保留为执行证据"


def test_prepare_resume_skips_rejected_candidate_and_completed_repeat(
    local_dir, monkeypatch
):
    from robomme_icl.workflows import prepare as pipeline

    saved = _fake_suite(monkeypatch)
    geometry_calls = []

    def geometry_check(spec):
        geometry_calls.append(spec.seed)
        return {"ok": spec.seed != 1900000001, "reasons": ["模拟几何拒绝"]}

    calls = []

    def first_run(spec, path, **_):
        if not geometry_check(spec)["ok"]:
            from robomme_icl.errors import CandidateRejected

            raise CandidateRejected("模拟真实几何拒绝")
        calls.append((spec.seed, path.name))
        if path.name.startswith("repeat_1_"):
            raise RuntimeError("模拟认证父流程中断")
        return write_episode(
            path,
            spec,
            FakeEnv().frames(),
            runtime_fingerprint={"testing": "fixed", "render_gpu": 1},
        )

    output = local_dir / "prepared"
    monkeypatch.setattr(pipeline, "run_episode_process", first_run)
    with pytest.raises(RuntimeError, match="父流程中断"):
        pipeline.prepare_suite(output, max_candidates=3)
    assert not (output / "suite.json").exists()

    def resumed_run(spec, path, **_):
        calls.append((spec.seed, path.name))
        return write_episode(
            path,
            spec,
            FakeEnv().frames(),
            runtime_fingerprint={"testing": "fixed", "render_gpu": 1},
        )

    monkeypatch.setattr(pipeline, "run_episode_process", resumed_run)
    manifest = pipeline.prepare_suite(output, max_candidates=3)
    assert manifest.exists() and len(saved) == 1
    assert sum(name.startswith("repeat_0_") for _, name in calls) == 1
    assert len(calls) == 3 and {seed for seed, _ in calls} == {1900000002}
    assert geometry_calls.count(1900000001) == 1, "已拒绝候选应按清单顺序直接跳过"
    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        pipeline.prepare_suite(output)


@pytest.mark.parametrize("change", ["fingerprint", "config"])
def test_prepare_resume_rejects_changed_fingerprint_before_running(
    local_dir, monkeypatch, change
):
    from robomme_icl.workflows import prepare as pipeline

    _fake_suite(monkeypatch)

    def interrupted(*_, **__):
        raise RuntimeError("模拟认证中断")

    output = local_dir / "prepared"
    monkeypatch.setattr(pipeline, "run_episode_process", interrupted)
    with pytest.raises(RuntimeError, match="认证中断"):
        pipeline.prepare_suite(output)
    if change == "fingerprint":
        monkeypatch.setattr(
            pipeline, "runtime_fingerprint", lambda **kwargs: {"testing": "changed"}
        )
    else:
        monkeypatch.setattr(
            sys.modules["robomme_icl.suite"],
            "load_configs",
            lambda *_: ({"changed": True}, {}),
        )
    monkeypatch.setattr(
        pipeline,
        "run_episode_process",
        lambda *_, **__: pytest.fail("错误指纹禁止运行"),
    )
    with pytest.raises(ReproducibilityError, match="恢复上下文"):
        pipeline.prepare_suite(output)


def test_prepare_resume_rejects_complete_repeat_with_wrong_fingerprint(
    local_dir, monkeypatch
):
    from robomme_icl.workflows import prepare as pipeline

    _fake_suite(monkeypatch)

    def interrupted(spec, path, **_):
        write_episode(
            path, spec, FakeEnv().frames(), runtime_fingerprint={"testing": "old"}
        )
        raise RuntimeError("模拟留下另一运行环境的完整记录")

    output = local_dir / "prepared"
    monkeypatch.setattr(pipeline, "run_episode_process", interrupted)
    with pytest.raises(RuntimeError, match="另一运行环境"):
        pipeline.prepare_suite(output)
    monkeypatch.setattr(
        pipeline,
        "run_episode_process",
        lambda *_, **__: pytest.fail("不能绕过错误指纹重跑"),
    )
    with pytest.raises(ReproducibilityError, match="runtime_fingerprint"):
        pipeline.prepare_suite(output)
    assert len(list(output.rglob("*.h5"))) == 1


def test_partial_replay_retries_in_new_staging_with_same_spec_and_actions(
    local_dir, monkeypatch
):
    from robomme_icl.workflows import replay as pipeline

    spec, frames = FakeSpec(), FakeEnv().frames()
    source = write_episode(
        local_dir / "source.h5",
        spec,
        frames,
        runtime_fingerprint={"testing": "fixed", "render_gpu": 0},
    )
    final = local_dir / "replayed.h5"
    monkeypatch.setattr(pipeline, "EpisodeSpec", FakeSpec)
    monkeypatch.setattr(
        pipeline,
        "runtime_fingerprint",
        lambda **kwargs: {"testing": "fixed", "render_gpu": 0},
    )
    calls = []

    def run(candidate, path, *, replay_source, **_):
        assert Path(replay_source) == source and not final.exists()
        calls.append((candidate.seed, candidate.spec_hash, path))
        if len(calls) == 1:
            _write_partial(path)
            raise OSError("模拟回放写出中断")
        return write_episode(
            path,
            candidate,
            read_episode(replay_source).frames,
            runtime_fingerprint={"testing": "fixed", "render_gpu": 0},
        )

    monkeypatch.setattr(pipeline, "run_episode_process", run)
    result = pipeline.replay_episode(source, final)
    assert result["passed"] is True and final.exists()
    assert [row[:2] for row in calls] == [(spec.seed, spec.spec_hash)] * 2
    assert calls[0][2] != calls[1][2] and calls[0][2].exists()
    assert read_episode(source).content_hash == read_episode(final).content_hash


def test_first_success_then_repeat_task_failure_stops_without_selecting_another_seed(
    local_dir, monkeypatch
):
    from robomme_icl.errors import TaskExecutionError
    from robomme_icl.workflows import prepare as pipeline

    saved = _fake_suite(monkeypatch)
    calls = []

    def run(spec, path, **_):
        calls.append(spec.seed)
        if len(calls) == 2:
            raise TaskExecutionError("相同候选第二次物理执行失败")
        return write_episode(
            path,
            spec,
            FakeEnv().frames(),
            runtime_fingerprint={"testing": "fixed", "render_gpu": 1},
        )

    monkeypatch.setattr(pipeline, "run_episode_process", run)
    with pytest.raises(ReproducibilityError, match="首次运行成功"):
        pipeline.prepare_suite(local_dir / "prepared", max_candidates=3)
    assert calls == [1900000001, 1900000001]
    assert saved == []
    assert not list((local_dir / "prepared").rglob("rejected.json"))


def test_gpu_binding_is_identical_across_worker_counts_and_gpu_argument_order(
    local_dir, monkeypatch
):
    from robomme_icl.workflows import prepare as pipeline

    saved = _fake_suite(monkeypatch)
    module = sys.modules["robomme_icl.suite"]
    module.plan_slots = lambda *_, **__: [
        {
            "slot_id": f"BinFill/easy/{index}",
            "max_candidates": 1,
            "seed": 1900000000 + index,
        }
        for index in range(2)
    ]
    module.candidate_for_slot = lambda slot, _: FakeSpec(seed=slot["seed"])
    calls = []

    def run(spec, path, *, render_gpu, **_):
        assert render_gpu == spec.seed % 2
        calls.append((spec.seed, render_gpu))
        return write_episode(
            path,
            spec,
            FakeEnv().frames(),
            runtime_fingerprint={"testing": "fixed", "render_gpu": render_gpu},
        )

    monkeypatch.setattr(pipeline, "run_episode_process", run)
    pipeline.prepare_suite(local_dir / "one", workers=1, gpus=[1, 0])
    pipeline.prepare_suite(local_dir / "four", workers=4, gpus=[0, 1])
    assert len(calls) == 8
    assert set(calls) == {(1900000000, 0), (1900000001, 1)}
    for specs, reports in saved:
        assert [reports[spec.spec_hash]["render_gpu"] for spec in specs] == [0, 1]


def test_gpu_slot_limits_cap_each_card_and_keep_single_worker_valid():
    from robomme_icl.workflows.workers import gpu_limits

    capacities = []
    manager = types.SimpleNamespace(
        BoundedSemaphore=lambda value: capacities.append(value) or value
    )
    assert gpu_limits(manager, [0, 1], 32) == {0: 16, 1: 16}
    assert gpu_limits(manager, [0, 1], 1) == {0: 1, 1: 1}
    assert capacities == [16, 16, 1, 1]


def test_generation_inherits_gpu_from_frozen_record_fingerprint(local_dir, monkeypatch):
    from robomme_icl.workflows import generate as pipeline

    spec = FakeSpec()
    fingerprint = {
        "render_gpu": 1,
        "render_gpu_uuid": "GPU-one",
        "render_gpu_pci": "0000:02:00.0",
    }
    cards = []

    def run(candidate, path, *, render_gpu, **_):
        cards.append(render_gpu)
        return write_episode(
            path, candidate, FakeEnv().frames(), runtime_fingerprint=fingerprint
        )

    monkeypatch.setattr(pipeline, "run_episode_process", run)
    generate_one(spec, local_dir / "bound.h5", expected_runtime_fingerprint=fingerprint)
    assert cards == [1]


def test_per_gpu_fingerprint_normalizes_pci_and_rejects_cuda_mapping(monkeypatch):
    from robomme_icl.io import fingerprint

    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.setattr(
        fingerprint.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(
            stdout=(
                "0, GPU-zero, RTX, fixed-driver, 00000000:01:00.0\n"
                "1, GPU-one, RTX, fixed-driver, 00000000:02:00.0\n"
            )
        ),
    )
    monkeypatch.setattr(fingerprint, "_tree_hash", lambda _: "source")
    monkeypatch.setattr(fingerprint, "_file_hash", lambda _: "lock")
    monkeypatch.setattr(
        fingerprint.importlib.metadata, "version", lambda _: "fixed-version"
    )
    common = fingerprint.runtime_fingerprint()
    selected = fingerprint.runtime_fingerprint(render_gpu=1)
    assert common["render_gpu"] is None and common["render_gpu_pci"] is None
    assert selected["render_gpu"] == 1 and selected["render_gpu_uuid"] == "GPU-one"
    assert selected["render_gpu_pci"] == "0000:02:00.0"
    with pytest.raises(ValueError, match="可用的物理"):
        fingerprint.runtime_fingerprint(render_gpu=2)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
    with pytest.raises(ValueError, match="CUDA_VISIBLE_DEVICES"):
        fingerprint.runtime_fingerprint(render_gpu=0)


def test_io_pool_reuses_workers_and_preserves_input_order_after_out_of_order_completion(
    monkeypatch,
):
    from robomme_icl.workflows import workers as pipeline

    observed, options, shutdown_calls = [], [], []
    ready = threading.Event()

    class Pool:
        def __init__(self, **kwargs):
            options.append(kwargs)
            self.pool = ThreadPoolExecutor(max_workers=kwargs["max_workers"])

        def submit(self, operation, job):
            return self.pool.submit(operation, job)

        def shutdown(self, **kwargs):
            shutdown_calls.append(kwargs)
            return self.pool.shutdown(**kwargs)

    def operation(job):
        index = job["index"]
        if index == 0:
            assert ready.wait(2), "第二个工作项应能独立完成"
        observed.append(index)
        if index == 1:
            ready.set()
        return index

    monkeypatch.setattr(pipeline, "ProcessPoolExecutor", Pool)
    result = pipeline.run_jobs(
        operation, [{"index": i} for i in range(5)], 2, threading.Event()
    )
    assert result == list(range(5)) and observed[0] == 1
    assert "max_tasks_per_child" not in options[0]
    assert shutdown_calls == [{"wait": True, "cancel_futures": True}]


def test_io_pool_bounds_submissions_and_does_not_refill_after_failure(monkeypatch):
    from robomme_icl.workflows import workers as pipeline

    submitted, unconsumed, peak, shutdown_calls = [], [0], [0], []

    class CompletedFuture(Future):
        def result(self, timeout=None):
            unconsumed[0] -= 1
            return super().result(timeout=timeout)

    class Pool:
        def __init__(self, **kwargs):
            assert "max_tasks_per_child" not in kwargs

        def submit(self, operation, job):
            submitted.append(job["index"])
            unconsumed[0] += 1
            peak[0] = max(peak[0], unconsumed[0])
            future = CompletedFuture()
            try:
                future.set_result(operation(job))
            except Exception as exc:
                future.set_exception(exc)
            return future

        def shutdown(self, **kwargs):
            shutdown_calls.append(kwargs)

    def operation(job):
        if job["index"] == 1:
            raise RuntimeError("模拟工作项失败")
        return job["index"]

    stop = threading.Event()
    monkeypatch.setattr(pipeline, "ProcessPoolExecutor", Pool)
    with pytest.raises(RuntimeError, match="工作项失败"):
        pipeline.run_jobs(operation, [{"index": i} for i in range(10)], 2, stop)
    assert submitted == [0, 1] and peak[0] == 2
    assert stop.is_set() and shutdown_calls == [{"wait": True, "cancel_futures": True}]


def test_io_pool_does_not_submit_when_already_stopped(monkeypatch):
    from robomme_icl.workflows import workers as pipeline

    shutdown_calls = []
    pool = types.SimpleNamespace(
        submit=lambda *args: pytest.fail("停止后不得提交"),
        shutdown=lambda **kwargs: shutdown_calls.append(kwargs),
    )
    monkeypatch.setattr(pipeline, "ProcessPoolExecutor", lambda **kwargs: pool)
    stop = threading.Event()
    stop.set()
    with pytest.raises(RecordError, match="调度已停止"):
        pipeline.run_jobs(lambda job: job, [{"index": 0}], 2, stop)
    assert shutdown_calls == [{"wait": True, "cancel_futures": True}]
