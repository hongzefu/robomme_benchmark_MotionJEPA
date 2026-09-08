"""四入口及整批记录的负例验证，不运行仿真。"""

import importlib
import json
from pathlib import Path
import tempfile

import numpy as np
import pytest

from robomme_icl.io.hdf5 import write_episode
from robomme_icl.io.paths import repository_root
from robomme_icl.suite import (
    candidate_for_slot,
    load_configs,
    load_suite,
    plan_slots,
    save_suite,
)


@pytest.fixture
def entry_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(repository_root() / "scripts"))
    return {
        name: importlib.import_module(name)
        for name in (
            "prepare_suite",
            "generate_dataset",
            "replay_dataset",
            "plot_distribution",
        )
    }


@pytest.fixture
def local_root():
    cache = repository_root() / ".cache" / "robomme_icl_tests"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix="entry-") as path:
        yield Path(path)


def test_four_entrypoints_require_explicit_inputs(entry_modules):
    for module in entry_modules.values():
        with pytest.raises(SystemExit) as exc:
            module.build_parser().parse_args([])
        assert exc.value.code == 2


def test_recertification_cannot_change_configs(entry_modules):
    with pytest.raises(SystemExit):
        entry_modules["prepare_suite"].main(
            [
                "--source-suite",
                "old.json",
                "--task-config",
                "new.json",
                "--output-dir",
                "unused",
            ]
        )


def test_runtime_registration_and_module_entry_removed():
    root = repository_root()
    import tomllib

    package = tomllib.loads((root / "pyproject.toml").read_text())
    assert "robomme-icl" not in package["project"].get("scripts", {})
    assert not (root / "src/robomme_icl/__main__.py").exists()
    assert not (root / "src/robomme_icl/cli.py").exists()
    assert not (root / "src/robomme_icl/suite/preflight.py").exists()
    assert {path.name for path in (root / "scripts").glob("*.py")} == {
        "prepare_suite.py",
        "generate_dataset.py",
        "replay_dataset.py",
        "plot_distribution.py",
        "verify_native_parity.py",
    }


def test_phase_preserves_identity_and_allows_worker_change(entry_modules, local_root):
    common = importlib.import_module("_icl.common")
    output = local_root / "run"
    for workers in (1, 4):
        with common.run_phase(
            output, "prepare", {"configs": ({"a": 1}, {"b": 2})}, {"workers": workers}
        ):
            pass
    params = common.read_json(output / "run_parameters.json")
    assert len(params["invocations"]) == 2
    with pytest.raises(ValueError, match="来源或规格"):
        with common.run_phase(output, "prepare", {"configs": ({"a": 2}, {"b": 2})}, {}):
            pass


def test_phase_preserves_completed_hdf5_after_video_error(entry_modules, local_root):
    common = importlib.import_module("_icl.common")
    output = local_root / "run"
    with pytest.raises(RuntimeError, match="编码失败"):
        with common.run_phase(output, "generate", {"suite_hash": "fixed"}, {}) as (
            root,
            result,
        ):
            (root / "hdf5_files").mkdir()
            (root / "hdf5_files" / "proof").write_text("已完成数据")
            result["hdf5_count"] = 1
            raise RuntimeError("编码失败")
    assert (output / "hdf5_files" / "proof").read_text() == "已完成数据"
    assert (
        common.read_json(output / "run_summary.json")["phases"]["generate"][
            "hdf5_count"
        ]
        == 1
    )
    with common.run_phase(output, "generate", {"suite_hash": "fixed"}, {}) as (
        _,
        result,
    ):
        result.update(hdf5_count=1, video_count=1)
    assert common.read_json(output / "run_summary.json")["status"] == "passed"


def test_summary_retains_other_phase_failure_until_that_phase_recovers(
    entry_modules, local_root
):
    common = importlib.import_module("_icl.common")
    output = local_root / "run"
    with pytest.raises(RuntimeError, match="编码失败"):
        with common.run_phase(output, "generate", {"suite_hash": "fixed"}, {}):
            raise RuntimeError("编码失败")
    with common.run_phase(output, "prepare", {"source_suite_hash": "fixed"}, {}):
        pass
    summary = common.read_json(output / "run_summary.json")
    assert summary["phases"]["prepare"]["status"] == "passed"
    assert summary["phases"]["generate"]["status"] == "failed"
    assert summary["status"] == "failed"
    with common.run_phase(output, "generate", {"suite_hash": "fixed"}, {}):
        pass
    assert common.read_json(output / "run_summary.json")["status"] == "passed"


@pytest.mark.parametrize(
    "first,second",
    [
        ("prepare", "replay"),
        ("generate", "replay"),
        ("replay", "prepare"),
        ("replay", "generate"),
    ],
)
def test_replay_and_generation_roots_cannot_mix_roles(
    entry_modules, local_root, first, second
):
    common = importlib.import_module("_icl.common")
    output = local_root / "run"
    with common.run_phase(output, first, {}, {}):
        pass
    parameters = (output / "run_parameters.json").read_bytes()
    summary = (output / "run_summary.json").read_bytes()
    with pytest.raises(ValueError, match="独立输出根"):
        with common.run_phase(output, second, {}, {}):
            pytest.fail("角色冲突必须在进入执行阶段前拒绝")
    assert (output / "run_parameters.json").read_bytes() == parameters
    assert (output / "run_summary.json").read_bytes() == summary


def test_generation_checks_batch_manifest_before_entering_run(
    entry_modules, local_root
):
    configs = load_configs()
    slots = plan_slots(*configs, tasks=["BinFill"], episodes_per_task=2)
    specs = [candidate_for_slot(slot, 0) for slot in slots]
    certificates = {
        spec.spec_hash: {"passed": True, "repeat_equal": True} for spec in specs
    }
    local = save_suite(
        local_root / "run/suite/suite.json",
        [specs[0]],
        configs,
        {specs[0].spec_hash: certificates[specs[0].spec_hash]},
    )
    external = save_suite(
        local_root / "external/suite.json",
        [specs[1]],
        configs,
        {specs[1].spec_hash: certificates[specs[1].spec_hash]},
    )
    before = local.read_bytes()
    with pytest.raises(ValueError, match="环境清单与 --suite 不同"):
        entry_modules["generate_dataset"].main(
            ["--suite", str(external), "--output-dir", str(local_root / "run")]
        )
    assert local.read_bytes() == before
    assert not (local_root / "run/run_parameters.json").exists()
    workflow = importlib.import_module("_icl.workflow")
    workflow.check_generation_suite(load_suite(local), local_root / "run")


def test_unknown_output_and_reference_paths_are_rejected(entry_modules, local_root):
    common = importlib.import_module("_icl.common")
    (local_root / "unknown").write_text("不能覆盖")
    with pytest.raises(ValueError, match="缺少运行身份"):
        with common.run_phase(local_root, "generate", {}, {}):
            pass
    for path in (
        repository_root() / "data/robomme_data_h5/new",
        repository_root() / "src/new",
    ):
        with pytest.raises(ValueError, match="不得写入"):
            common.safe_output(path)


def test_replay_discovers_only_published_inputs(entry_modules, local_root):
    workflow = importlib.import_module("_icl.workflow")
    spec = candidate_for_slot(
        plan_slots(*load_configs(), tasks=["BinFill"], episodes_per_task=1)[0], 0
    )
    frames = [
        {
            "observation": {"base_rgb": np.zeros((2, 2, 3), dtype=np.uint8)},
            "joint_action": np.zeros(8),
            "info": {"success": True, "fail": False},
        }
    ]
    path = local_root / "hdf5_files/BinFill/seed_2000000000.h5"
    write_episode(path, spec, frames, runtime_fingerprint={"render_gpu": 0})
    duplicate = local_root / "hdf5_files/.staging/duplicate.h5"
    write_episode(duplicate, spec, frames, runtime_fingerprint={"render_gpu": 0})
    rows = workflow.discover_inputs(local_root)
    assert len(rows) == 1 and rows[0]["path"] == str(path)
    with pytest.raises(ValueError, match="输出与输入相同"):
        workflow.check_replay_destinations(rows, local_root)
    exposed = local_root / "hdf5_files/duplicate.h5"
    write_episode(exposed, spec, frames, runtime_fingerprint={"render_gpu": 0})
    with pytest.raises(ValueError, match="重复"):
        workflow.discover_inputs(local_root)


@pytest.mark.parametrize("directory_name", ["hdf5_files", "data"])
def test_replay_scan_root_blocks_nested_output_but_allows_batch_replay(
    entry_modules, local_root, directory_name
):
    workflow = importlib.import_module("_icl.workflow")
    scan_root = local_root / directory_name
    scan_root.mkdir()
    assert workflow.replay_scan_root(local_root) == scan_root
    assert workflow.replay_scan_root(scan_root) == scan_root
    for output in (scan_root, scan_root / "replayed"):
        with pytest.raises(ValueError, match="实际 HDF5 扫描目录"):
            entry_modules["replay_dataset"].main(
                ["--input", str(local_root), "--output-dir", str(output)]
            )
        assert not (output / "run_parameters.json").exists()
    workflow.check_replay_destinations([], local_root / "replay", scan_root=scan_root)
    assert not (local_root / "replay").exists()


def test_replay_raw_directory_and_single_file_have_explicit_scan_roots(
    entry_modules, local_root
):
    workflow = importlib.import_module("_icl.workflow")
    raw = local_root / "raw"
    raw.mkdir()
    assert workflow.replay_scan_root(raw) == raw
    with pytest.raises(ValueError, match="实际 HDF5 扫描目录"):
        workflow.check_replay_destinations([], raw / "replayed", scan_root=raw)
    single = raw / "episode.h5"
    single.write_bytes(b"input")
    assert workflow.replay_scan_root(single) is None
