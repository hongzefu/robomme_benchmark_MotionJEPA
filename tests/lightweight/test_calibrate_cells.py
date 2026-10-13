"""测速协议的 CPU 单测：资源读数为夹具，子进程只有等待和写 JSON。"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "mixed8_calibration", ROOT / "scripts/data-generation-newSeed/utils/calibrate_parallelism.py"
)
calib = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = calib
SPEC.loader.exec_module(calib)
pytestmark = pytest.mark.lightweight


class FakeSampler:
    """绝不查询实际 GPU；固定探针读数用于准入与持久化测试。"""

    def __init__(self, gpus):
        self.peak_worker_rss_mb = 8192
        self.rows = []
        self.gpu_rows = [{"t": time.time(), "index": int(gpu), "util": 0,
                          "mem_mb": 8192, "total_mb": 81920} for gpu in gpus.split(",")]

    def start(self, pid):
        self.pid = pid

    def stop(self):
        pass


@pytest.fixture
def cpu_only(monkeypatch):
    monkeypatch.setattr(calib, "ResourceSampler", FakeSampler)
    monkeypatch.setattr(calib.psutil, "virtual_memory", lambda: SimpleNamespace(available=1000 * 2**30))


def _fake_command(monkeypatch, code):
    monkeypatch.setattr(calib, "_command", lambda *args: [
        sys.executable, "-u", "-c", code, str(args[1])
    ])


def _eligible(workers, throughput=100):
    return {"cell": f"L{workers}", "workers": workers, "gpus": "0", "requested": 384,
            "complete": True, "returncode": 0, "aborted_by": None,
            "tiers_completed": list(calib.MIXED_CYCLE),
            "steady": {"trimmed": True, "throughput_ep_per_min": throughput}}


def test_default_cells_and_divisibility():
    cells = calib.parse_cells(calib.DEFAULT_CELLS)
    assert [(cell.name, cell.workers, len(cell.gpu_ids)) for cell in cells] == [
        ("L32", 32, 4), ("L64", 64, 8), ("L128", 128, 8)
    ]
    assert [cell.workers // len(cell.gpu_ids) for cell in cells] == [8, 8, 16]


@pytest.mark.parametrize("text", ["", "L:0:0:on", "L:33:0,1:on", "L:32:0,0:on",
                                 "L:8::on", "L:8:0:wat", "../x:8:0:on", "L:8:0:on;L:8:0:on"])
def test_bad_cells_rejected(text):
    with pytest.raises(ValueError):
        calib.parse_cells(text)


def test_command_forwards_cycle_and_uses_stop_contract(tmp_path):
    command = calib._command(calib.Cell("L32", 32, "0,1,2,3", False), tmp_path, "all", 24,
                             "211", ",".join(calib.MIXED_CYCLE), 8, 100, "per-gpu")
    for flag, value in (("--episode-start", "8"), ("--max-attempts", "100"),
                        ("--affinity", "per-gpu"), ("--gpus", "0,1,2,3")):
        assert command[command.index(flag) + 1] == value
    assert "--difficulty-cycle" in command and "--difficulty" not in command
    assert "--stop-on-pool-crash" in command and "--no-limit-threads" in command


def test_memory_budget_exact_boundary():
    cell = calib.Cell("L32", 32, "0,1,2,3", True)
    probe = {"rss_gb": 8, "vram_gb": 1, "gpu_gb": 9.6}
    assert calib.memory_admitted(cell, probe, 32 * 8 * 1.2 + 40)
    assert not calib.memory_admitted(cell, probe, 32 * 8 * 1.2 + 40 - 0.001)
    assert not calib.memory_admitted(cell, {**probe, "gpu_gb": 9.599}, 1000)


def test_steady_window_never_falls_back():
    results = [{"ok": True, "finished_at": n + 1, "wall_s": 2} for n in range(96)]
    assert calib._steady_window(results[:65], 32)["throughput_ep_per_min"] is None
    steady = calib._steady_window(results, 32)
    assert steady["trimmed"] and steady["episodes"] == 32
    assert (steady["t_start"], steady["t_end"]) == (33, 64)
    assert calib._steady_window([{**row, "finished_at": 1} for row in results], 32)["throughput_ep_per_min"] is None


def test_champion_requires_complete_eight_tiers_and_three_w():
    assert calib.choose_best([_eligible(32, 97), _eligible(64, 100), _eligible(128, 99)])["workers"] == 32
    for override in ({"complete": False}, {"requested": 95}, {"tiers_completed": ["easy"]},
                     {"steady": {"trimmed": False, "throughput_ep_per_min": 999}}):
        assert calib.choose_best([{**_eligible(32), **override}]) is None
    assert calib.choose_best([_eligible(32, 96.9), _eligible(64, 100)])["workers"] == 64


@pytest.mark.parametrize("reason", ["pool_crash", "mem_guard", "timeout"])
def test_ladder_stops_after_any_guard(monkeypatch, tmp_path, cpu_only, reason):
    calls = []

    def run(cell, root, **kwargs):
        calls.append(cell.workers)
        return {**_eligible(cell.workers), "complete": False, "aborted_by": reason}

    monkeypatch.setattr(calib, "run_cell", run)
    rows = calib.run_ladder(calib.parse_cells(calib.DEFAULT_CELLS), tmp_path,
                            {"rss_gb": 1, "vram_gb": 1, "gpu_gb": 80},
                            mem_margin=1.2, mem_guard_gb=40)
    assert calls == [32] and len(rows) == 1 and rows[0]["aborted_by"] == reason


def test_ladder_skips_memory_and_48(monkeypatch, tmp_path, cpu_only):
    calls = []
    monkeypatch.setattr(calib, "run_cell", lambda cell, root, **kwargs: calls.append(cell.workers) or _eligible(cell.workers))
    rows = calib.run_ladder(calib.parse_cells("L32:32:0:on;L48:48:0:on;L64:64:0:on"), tmp_path,
                            {"rss_gb": 20, "vram_gb": 1, "gpu_gb": 80},
                            mem_margin=1.2, mem_guard_gb=40)
    assert calls == [32]
    assert rows[1]["skipped_by"] == "user_skip_48"
    assert rows[2]["skipped_by"] == "mem_budget"


def test_existing_cell_keeps_evidence(tmp_path, cpu_only):
    output = tmp_path / "L32"
    output.mkdir()
    evidence = output / "generate.log"
    evidence.write_text("旧证据", encoding="utf-8")
    with pytest.raises(FileExistsError):
        calib.run_cell(calib.Cell("L32", 32, "0", True), tmp_path, "all", 24, "211", False)
    assert evidence.read_text(encoding="utf-8") == "旧证据"


def test_real_cpu_fake_generator_keeps_logs_removes_only_artifacts(monkeypatch, tmp_path, cpu_only, capsys):
    _fake_command(monkeypatch, """
import json, sys, time
from pathlib import Path
p = Path(sys.argv[1])
for name in ('hdf5_files', 'videos'):
    (p/name).mkdir()
    (p/name/'样本').write_text('夹具')
rows = [dict(ok=True, finished_at=time.time()+i, wall_s=1, difficulty='easy', peak_rss_mb=1024) for i in range(4)]
(p/'episode_results.jsonl').write_text(''.join(json.dumps(row)+'\\n' for row in rows))
(p/'run_summary.json').write_text(json.dumps(dict(requested_count=4, success_count=4, exhausted_count=0)))
print('stopped_by=None', flush=True)
""")
    summary = calib.run_cell(calib.Cell("T", 1, "0", True), tmp_path, "BinFill", 4, "211", False)
    output = tmp_path / "T"
    assert summary["complete"] and summary["termination"]["zero_residual"]
    assert not (output / "hdf5_files").exists() and not (output / "videos").exists()
    for name in ("episode_results.jsonl", "run_summary.json", "generate.log", "cell_summary.json"):
        assert (output / name).exists()
    assert "stopped_by=None" in capsys.readouterr().out


@pytest.mark.parametrize("reason", ["timeout", "mem_guard", "pool_crash"])
def test_real_cpu_run_cell_guards(monkeypatch, tmp_path, cpu_only, reason):
    if reason == "pool_crash":
        code = """
import json,sys,subprocess
from pathlib import Path
p=Path(sys.argv[1])
subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
(p/'run_summary.json').write_text(json.dumps(dict(stopped_by='pool_crash')))
print('进程池已损坏 stopped_by=pool_crash', flush=True)
sys.exit(3)
"""
    else:
        code = "import time; time.sleep(60)"
    _fake_command(monkeypatch, code)
    if reason == "mem_guard":
        monkeypatch.setattr(calib.psutil, "virtual_memory", lambda: SimpleNamespace(available=39 * 2**30))
    summary = calib.run_cell(calib.Cell("T", 1, "0", True), tmp_path, "BinFill", 4, "211", True,
                              timeout_s=0.01 if reason == "timeout" else 5)
    assert summary["aborted_by"] == reason
    assert not summary["complete"] and summary["termination"]["zero_residual"]
    assert calib._group_processes(summary["termination"]["pgid"]) == []


def test_terminate_group_escalates_and_leaves_other_group_alone():
    # 两个 CPU 假进程组；目标组有忽略 TERM 的子进程，旁组必须保持存活。
    target = subprocess.Popen([sys.executable, "-u", "-c", """
import signal, subprocess, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen([sys.executable, '-u', '-c', 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print("子进程就绪", flush=True); time.sleep(60)'])
print('父进程就绪', flush=True)
time.sleep(60)
"""], stdout=subprocess.PIPE, text=True, start_new_session=True)
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    try:
        assert {target.stdout.readline().strip(), target.stdout.readline().strip()} == {"父进程就绪", "子进程就绪"}
        result = calib.terminate_group(target, grace_s=0.05)
        assert result["sigkill"] and result["zero_residual"]
        assert other.poll() is None
    finally:
        if target.poll() is None or calib._group_processes(target.pid):
            calib.terminate_group(target, grace_s=0)
        calib.terminate_group(other, grace_s=0)


def test_persistent_sampler_targets_only_requested_gpus(monkeypatch):
    calls = []

    class FakeGpu:
        stdout = io.StringIO("2, 0, 100, 80000\n3, 60, 200, 80000\n")

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(calib.subprocess, "Popen", lambda command, **kwargs: calls.append(command) or FakeGpu())
    sampler = calib.ResourceSampler("2,3")
    sampler.start(os.getpid())
    sampler.stop()
    assert len(calls) == 1
    assert calls[0][calls[0].index("-i") + 1] == "2,3"
    assert calls[0][calls[0].index("-lms") + 1] == "500"
    assert {row["index"] for row in sampler.gpu_rows} == {2, 3}


def test_resource_means_zero_fraction_and_slow_strata():
    cpu = [{"t": n, "cpu_percent": 20, "load1": 1, "mem_used_gb": 2} for n in (1, 2, 3)]
    gpu = [{"t": n, "index": 0, "util": util, "mem_mb": 200} for n, util in ((0, 100), (1, 0), (2, 100), (3, 50))]
    results = [{"ok": True, "finished_at": 2, "wall_s": 2}, {"ok": True, "finished_at": 3, "wall_s": 0.5}]
    summary = calib._resource_summary(cpu, 1, 3, gpu, results)
    data = summary["gpus"]["0"]
    assert data["util_mean"] == 50 and data["util_zero_fraction"] == pytest.approx(1/3)
    assert data["slow_util_mean"] == 50 and data["non_slow_util_mean"] == 50
    assert "median" not in json.dumps(summary)
    assert calib._resource_summary(cpu, None, None, gpu, results) == {}


@pytest.mark.parametrize("probe_ok,l32_ok", [(True, True), (False, True), (True, False)])
def test_main_probe_and_l32_gate(monkeypatch, tmp_path, cpu_only, capsys, probe_ok, l32_ok):
    calls = []

    def run(cell, root, env, episodes, **kwargs):
        calls.append((cell, env, episodes, kwargs))
        return {"cell": "P8", "workers": 8, "gpus": "0", "complete": probe_ok,
                "tiers_completed": ["xhard18", "xhard20"], "peak_worker_rss_mb": 8192,
                "gpu_peaks": {"0": {"mem_mb": 8192, "total_mb": 81920}}}

    monkeypatch.setattr(calib, "run_cell", run)
    monkeypatch.setattr(calib, "run_ladder", lambda *args, **kwargs: [
        {**_eligible(32), "complete": l32_ok}, _eligible(64)
    ])
    exitcode = calib.main(["--root", str(tmp_path), "--difficulty-cycle", ",".join(calib.MIXED_CYCLE)])
    assert exitcode == (0 if probe_ok and l32_ok else 1)
    assert calls[0][2] == 2 and calls[0][3]["timeout_s"] == 1800 and calls[0][3]["episode_start"] == 6
    payload = json.loads((tmp_path / "calibration.json").read_text())
    assert payload["probe_budget"]["vram_gb"] == 1
    assert f"MEM_PROBE={'PASS' if probe_ok else 'FAIL'}" in capsys.readouterr().out
    assert f"CALIB={'PASS' if probe_ok and l32_ok else 'FAIL'}" in payload["context"]["calib_line"]


def test_main_rejects_small_jobs_before_probe(monkeypatch, tmp_path):
    monkeypatch.setattr(calib, "run_cell", lambda *args, **kwargs: pytest.fail("不得起跑"))
    with pytest.raises(SystemExit) as caught:
        calib.main(["--root", str(tmp_path), "--episodes", "1"])
    assert caught.value.code == 2
