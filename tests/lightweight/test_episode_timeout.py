"""生成器单条墙钟超时（pebble 池）：合成记录字段、run.py 归类、真起池验证超时只杀该任务且池仍可用。"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import h5py
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "generate_dataset_newseed.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.injection.run import _is_resource_failure, classify_outcome, execution_state  # noqa: E402


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("generate_dataset_newseed", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_dataset_newseed"] = module
    spec.loader.exec_module(module)
    return module


def _job(gen, root: Path):
    return gen.EpisodeJob(task="VideoUnmaskSwap", episode=7, attempt=0, seed=5700, difficulty="xhard",
                          output_root=str(root), repo_root=str(REPO_ROOT))


def test_超时合成记录字段齐全且归类为超时(gen, tmp_path: Path):
    row = gen._synth_timeout(_job(gen, tmp_path), 600.0, wall_s=612.3, cleanup={"discarded": ["a.h5"], "orphan_h5": None})
    assert row["ok"] is False
    assert (row["failure_class"], row["error_type"], row["timed_out"]) == ("timeout", "EpisodeWallClockTimeout", True)
    assert row["timeout_s"] == 600.0 and row["wall_s"] == 612.3
    assert row["video"]["status"] == gen.VIDEO_STATUS_NO_CLOSE and row["video"]["reason"]
    assert row["discarded"] == ["a.h5"] and row["orphan_h5"] is None
    for key in ("phases", "peak_rss_mb", "runtime_checks", "injection_evidence", "finished_at"):
        assert key in row
    assert classify_outcome(row) == "超时"
    assert execution_state(row) == "timeout"
    assert _is_resource_failure({**row, "execution_state": "timeout"}) is False


def test_超时清理只删_stub_保留有内容的_h5(gen, tmp_path: Path):
    job = _job(gen, tmp_path)
    (tmp_path / "hdf5_files").mkdir()
    (tmp_path / "videos").mkdir()
    stub = gen._h5_path(tmp_path, job)
    with h5py.File(stub, "w"):
        pass  # 只有文件头、没有 episode 组：与被杀 worker 留下的 96 字节 stub 同构
    (tmp_path / "videos" / gen.BINFILL_TMP_DIRNAME).mkdir()
    leftover = tmp_path / "videos" / gen.BINFILL_TMP_DIRNAME / "VideoUnmaskSwap_ep7_seed5700_x.mp4"
    leftover.write_bytes(b"x")
    cleanup = gen._discard_timeout_artifacts(tmp_path, job)
    assert not stub.exists() and not leftover.exists()
    assert sorted(cleanup["discarded"]) == sorted([str(stub), str(leftover)]) and cleanup["orphan_h5"] is None

    with h5py.File(stub, "w") as handle:
        handle.create_group("episode_7")
    cleanup = gen._discard_timeout_artifacts(tmp_path, job)
    assert stub.exists() and cleanup["orphan_h5"] == str(stub)


def test_run_jobs_新参数有默认值(gen):
    import inspect

    params = inspect.signature(gen._run_jobs).parameters
    assert params["episode_timeout_s"].default == gen.DEFAULT_EPISODE_TIMEOUT_S == 600.0
    assert gen.EpisodeJob.__dataclass_fields__["binfill_demo"].default is False


def _sleep(seconds: float) -> str:
    time.sleep(seconds)
    return "done"


def test_pebble_超时只杀该任务且池仍可用():
    from pebble import ProcessPool

    with ProcessPool(max_workers=2, max_tasks=0) as pool:
        slow = pool.schedule(_sleep, args=(5.0,), timeout=0.5)
        fast = pool.schedule(_sleep, args=(0.1,))
        assert fast.result(timeout=30) == "done"
        with pytest.raises(TimeoutError):
            slow.result(timeout=30)
        # 超时之后池没有崩：再派一个任务照常返回
        assert pool.schedule(_sleep, args=(0.1,)).result(timeout=30) == "done"
