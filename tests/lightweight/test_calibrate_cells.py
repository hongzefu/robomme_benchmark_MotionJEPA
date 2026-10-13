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


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP])
def test_outer_signal_cleans_exact_child_group_and_keeps_other_group(tmp_path, signum):
    # 外层测速进程与生成器各为独立会话，另起旁组验证没有全局杀进程。
    child_code = """
import json, os, subprocess, sys, time
from pathlib import Path
p = Path(sys.argv[1])
child = subprocess.Popen([sys.executable, '-u', '-c', 'import os,time; print(os.getpid(), flush=True); time.sleep(60)'],
                         stdout=subprocess.PIPE, text=True)
worker_pid = int(child.stdout.readline())
(p/'identities.json').write_text(json.dumps(dict(generator_pid=os.getpid(), pgid=os.getpgrp(), worker_pid=worker_pid)))
print('假生成器及 worker 就绪', flush=True)
time.sleep(60)
"""
    launcher = f"""
import importlib.util, json, sys
from pathlib import Path
from types import SimpleNamespace
spec = importlib.util.spec_from_file_location('signal_calib', {str(SPEC.origin)!r})
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)
class Sampler:
    def __init__(self, gpus):
        self.rows = []
        self.gpu_rows = []
        self.peak_worker_rss_mb = 0
    def start(self, pid):
        pass
    def stop(self):
        pass
c.ResourceSampler = Sampler
c.psutil.virtual_memory = lambda: SimpleNamespace(available=1000*2**30)
c._command = lambda *args: [sys.executable, '-u', '-c', {child_code!r}, str(args[1])]
summary = c.run_cell(c.Cell('T', 1, '0', True), Path(sys.argv[1]), 'BinFill', 4, '211', True)
sys.exit(1 if summary['aborted_by'] else 0)
"""
    outer = subprocess.Popen([sys.executable, "-u", "-c", launcher, str(tmp_path)],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             start_new_session=True)
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                             start_new_session=True)
    identities = None
    try:
        identity_file = tmp_path / "T" / "identities.json"
        deadline = time.monotonic() + 5
        while not identity_file.exists() and time.monotonic() < deadline and outer.poll() is None:
            time.sleep(0.01)
        identities = json.loads(identity_file.read_text())
        assert identities["pgid"] == identities["generator_pid"] != outer.pid
        assert os.getpgid(identities["worker_pid"]) == identities["pgid"]
        os.kill(outer.pid, signum)
        stdout, _ = outer.communicate(timeout=5)
        assert outer.returncode == 1
        summary = json.loads((tmp_path / "T" / "cell_summary.json").read_text())
        assert summary["aborted_by"] == f"signal:{signal.Signals(signum).name}"
        assert summary["termination"]["pgid"] == identities["pgid"]
        assert summary["termination"]["zero_residual"]
        assert not summary["complete"]
        assert calib._group_processes(identities["pgid"]) == []
        assert other.poll() is None and os.getpgid(other.pid) == other.pid
        assert "假生成器及 worker 就绪" in stdout
        assert (tmp_path / "T" / "generate.log").exists()
        assert (tmp_path / "T" / "resource_samples.json").exists()
        print(f"CALIB_SIGNAL_CLEANUP=PASS signal={signal.Signals(signum).name} outer_pid={outer.pid} "
              f"generator_pgid={identities['pgid']} worker_pid={identities['worker_pid']} "
              f"other_pgid={other.pid} remaining=0 other_alive=1 evidence={tmp_path / 'T'}")
    finally:
        if identities and calib._group_processes(identities["pgid"]):
            os.killpg(identities["pgid"], signal.SIGKILL)
        if outer.poll() is None:
            calib.terminate_group(outer, grace_s=0)
        calib.terminate_group(other, grace_s=0)


def test_aborted_truncated_jsonl_persists_error_and_stops_ladder(monkeypatch, tmp_path, cpu_only):
    # 正常首行也不挑出来当成功：整份记录失去完整性，原字节必须保留。
    _fake_command(monkeypatch, """
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
(p/'episode_results.jsonl').write_text('{"ok":true,"finished_at":1,"wall_s":1}\\n{"ok":')
(p/'run_summary.json').write_text(json.dumps(dict(stopped_by='pool_crash')))
print('进程池已损坏 stopped_by=pool_crash', flush=True)
sys.exit(3)
""")
    rows = calib.run_ladder(calib.parse_cells(calib.DEFAULT_CELLS), tmp_path,
                            {"rss_gb": 1, "vram_gb": 1, "gpu_gb": 80},
                            env="all", episodes=24, difficulty="211", keep=True,
                            mem_margin=1.2, mem_guard_gb=40)
    assert len(rows) == 1 and not (tmp_path / "L64").exists()
    output = tmp_path / "L32"
    summary = json.loads((output / "cell_summary.json").read_text())
    assert summary["aborted_by"] == "pool_crash"
    assert summary["parse_error"]["file"] == str(output / "episode_results.jsonl")
    assert summary["parse_error"]["message"]
    assert summary["success"] is None and summary["attempts"] is None
    assert summary["termination"]["zero_residual"] and not summary["complete"]
    assert summary["steady"]["throughput_ep_per_min"] is None
    assert (output / "episode_results.jsonl").read_text().endswith('{"ok":')
    assert (output / "resource_samples.json").exists()
    assert calib.choose_best(rows) is None
    print(f"CALIB_TRUNCATED_JSONL=PASS aborted_by={summary['aborted_by']} "
          f"complete=0 parse_error=1 cells_run=1 remaining=0 evidence={output}")


def test_non_aborted_bad_jsonl_still_raises(monkeypatch, tmp_path, cpu_only):
    _fake_command(monkeypatch, """
import sys
from pathlib import Path
(Path(sys.argv[1])/'episode_results.jsonl').write_text('{"ok":')
""")
    with pytest.raises(json.JSONDecodeError):
        calib.run_cell(calib.Cell("T", 1, "0", True), tmp_path, "BinFill", 4, "211", True)
    assert not (tmp_path / "T" / "cell_summary.json").exists()


@pytest.mark.parametrize("cause", ["parse_error", "signal:SIGTERM"])
def test_main_integrity_or_signal_abort_fails_even_after_good_l32(monkeypatch, tmp_path, cpu_only, cause):
    monkeypatch.setattr(calib, "run_cell", lambda *args, **kwargs: {
        "cell": "P8", "workers": 8, "gpus": "0", "complete": True,
        "tiers_completed": ["xhard18", "xhard20"], "peak_worker_rss_mb": 8192,
        "gpu_peaks": {"0": {"mem_mb": 8192, "total_mb": 81920}}
    })
    bad = {**_eligible(64), "complete": False, "aborted_by": "pool_crash" if cause == "parse_error" else cause,
           "parse_error": {"message": "截断"} if cause == "parse_error" else None}
    monkeypatch.setattr(calib, "run_ladder", lambda *args, **kwargs: [_eligible(32), bad])
    assert calib.main(["--root", str(tmp_path), "--difficulty-cycle", ",".join(calib.MIXED_CYCLE)]) == 1
    payload = json.loads((tmp_path / "calibration.json").read_text())
    assert payload["context"]["calib_line"].startswith("CALIB=FAIL ")


@pytest.mark.parametrize("phase", ["resource_write", "artifact_rmtree"])
@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP])
def test_tail_signal_persists_final_abort_and_stops_ladder(monkeypatch, tmp_path, cpu_only, phase, signum):
    # 生成器正常完成并已清理之后，在确定的尾部操作中给外层发信号。
    _fake_command(monkeypatch, """
import json, os, sys, time
from pathlib import Path
p = Path(sys.argv[1])
probe = p.name == 'P8'
count = 16 if probe else 384
tiers = ['xhard18', 'xhard20'] if probe else ['easy', 'medium', 'hard', 'xhard12', 'xhard14', 'xhard16', 'xhard18', 'xhard20']
rows = [dict(ok=True, finished_at=time.time()+i, wall_s=1, difficulty=tiers[i%len(tiers)], peak_rss_mb=8192) for i in range(count)]
(p/'episode_results.jsonl').write_text(''.join(json.dumps(row)+'\\n' for row in rows))
(p/'run_summary.json').write_text(json.dumps(dict(requested_count=count, success_count=count, exhausted_count=0)))
(p/'identities.json').write_text(json.dumps(dict(pgid=os.getpgrp())))
for name in ('hdf5_files', 'videos'):
    (p/name).mkdir()
    (p/name/'样本').write_text('夹具')
print('假生成器正常退出', flush=True)
""")
    sent_groups = []
    original_write = calib._write_json
    original_rmtree = calib.shutil.rmtree

    def interrupt(output):
        pgid = json.loads((output / "identities.json").read_text())["pgid"]
        assert calib._group_processes(pgid) == []
        sent_groups.append(pgid)
        os.kill(os.getpid(), signum)

    def write(path, payload):
        if phase == "resource_write" and path.name == "resource_samples.json" and path.parent.name == "L32":
            interrupt(path.parent)
        original_write(path, payload)

    def rmtree(path, *args, **kwargs):
        if phase == "artifact_rmtree" and path.name == "hdf5_files" and path.parent.name == "L32":
            interrupt(path.parent)
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(calib, "_write_json", write)
    monkeypatch.setattr(calib.shutil, "rmtree", rmtree)
    previous_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    exitcode = calib.main(["--root", str(tmp_path), "--difficulty-cycle", ",".join(calib.MIXED_CYCLE)])
    payload = json.loads((tmp_path / "calibration.json").read_text())
    summary = json.loads((tmp_path / "L32" / "cell_summary.json").read_text())
    good = (exitcode == 1 and len(payload["cells"]) == 1 and not summary["complete"]
            and summary["aborted_by"] == f"signal:{signal.Signals(signum).name}"
            and payload["context"]["calib_line"].startswith("CALIB=FAIL "))
    print(f"CALIB_TAIL_SIGNAL={'PASS' if good else 'FAIL'} phase={phase} "
          f"signal={signal.Signals(signum).name} generator_pgid={sent_groups[0]} "
          f"generator_exited=1 cells_run={sum('returncode' in row for row in payload['cells'])} complete={int(summary['complete'])} "
          f"aborted_by={summary['aborted_by']} exit={exitcode} evidence={tmp_path}")
    assert good
    assert len(sent_groups) == 1 and not (tmp_path / "L64").exists()
    assert summary["termination"]["zero_residual"]
    assert (tmp_path / "L32" / "resource_samples.json").exists()
    assert {sig: signal.getsignal(sig) for sig in previous_handlers} == previous_handlers
