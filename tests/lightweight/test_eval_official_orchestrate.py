"""scripts/eval-official/orchestrate.py 与 watchdog.sh 的轻量测试（不触发仿真，玩具步骤 echo + 写报告 JSON）。

覆盖 AGENTS.md P4：完成 → 读真实报告 → 下一步；缺报告 / 判定不符 → 停该分支；非阻塞失败照跑依赖方；
跨线依赖；恢复只做未完成步骤；心跳 JSON 零计数键；看门狗独立发现编排器死亡；kill -9 后重启接续；
GL 派发 argv 与 SLURM_* 清空。
"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCH = REPO_ROOT / "scripts" / "eval-official" / "orchestrate.py"
WATCHDOG = REPO_ROOT / "scripts" / "eval-official" / "watchdog.sh"
_spec = importlib.util.spec_from_file_location("v75_orchestrate", ORCH)
orch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(orch)
HOST = socket.gethostname()


def _step(name, cmd, needs=(), verdict="^OK_DONE", report=None, **kw):
    d = {"name": name, "cmd": cmd, "needs": list(needs), "verdict_regex": verdict,
         "report": report or "{state}/r_" + name + ".json"}
    d.update(kw)
    return d


def _ok(name, extra=""):
    """玩具成功步骤：打判定行并写报告。"""
    return f"{extra} echo OK_DONE step={name}; echo '{{\"n\": 0}}' > {{state}}/r_{name}.json"


def _plan(tmp_path, lanes):
    p = tmp_path / "plan.json"
    p.write_text(json.dumps({"lanes": lanes}))
    return p


def _run(tmp_path, plan, *extra, env=None, timeout=40):
    state = tmp_path / "state"
    cmd = [sys.executable, str(ORCH), "--plan", str(plan), "--state", str(state), "--workdir", str(tmp_path),
           "--poll-s", "0.05", "--heartbeat-s", "0.3", *extra]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    return r, state


def _events(state):
    p = state / "events.log"
    return p.read_text().splitlines() if p.exists() else []


def _find(lines, kind, step=None):
    out = []
    for i, ln in enumerate(lines):
        if ln.split(" ", 1)[0] == kind and (step is None or f" step={step} " in ln + " "):
            out.append(i)
    return out


def _kv(line):
    return dict(tok.split("=", 1) for tok in line.split()[1:] if "=" in tok)


def test_completion_gates_next_step(tmp_path):
    # A 先睡再写报告；B 启动时要求 A 的报告已存在
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        _step("A", _ok("A", "sleep 0.5;")),
        _step("B", "test -f {state}/r_A.json || exit 7; " + _ok("B")),
    ]}])
    r, state = _run(tmp_path, plan)
    assert r.returncode == 0, r.stdout + r.stderr
    ev = _events(state)
    assert _find(ev, "STEP_DONE", "A")[0] < _find(ev, "STEP_START", "B")[0]
    assert (state / "A.done").exists() and (state / "B.done").exists()
    done = json.loads((state / "A.done").read_text())
    assert done["verdict_line"].startswith("OK_DONE") and len(done["report_sha256"]) == 64
    assert "EXIT_CODE=0" in (state / "logs" / "A.log").read_text()
    assert _find(ev, "LANE_DONE") and "verdict=PASS" in ev[-1] and ev[-1].startswith("ORCH_DONE")
    assert list((state / "notify").glob("*-stage_done-orch.json"))


def test_report_missing_fails_and_blocks(tmp_path):
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        _step("A", "echo OK_DONE"),            # 判定行有、报告没写
        _step("B", _ok("B")),                  # 同线后继：阻塞
        _step("C", _ok("C")),                  # 传递阻塞
    ]}, {"name": "M", "where": "local", "steps": [_step("D", _ok("D"), needs=["A"])]}])
    r, state = _run(tmp_path, plan)
    assert r.returncode == 1
    ev = _events(state)
    fa = ev[_find(ev, "STEP_FAIL", "A")[0]]
    assert "reason=report_missing" in fa and "blocking=1" in fa
    for s in ("B", "C", "D"):
        line = ev[_find(ev, "STEP_FAIL", s)[0]]
        assert "reason=upstream" in line, line
        assert not _find(ev, "STEP_START", s)
    assert not (state / "r_B.json").exists()
    assert list((state / "notify").glob("*-lane_stop-L.json"))
    assert "verdict=FAIL" in ev[-1]


def test_verdict_mismatch_fails(tmp_path):
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        _step("A", "echo ENV_DIGEST_DONE cell=x rows=47; echo '{}' > {state}/r_A.json",
              verdict=r"^ENV_DIGEST_DONE .*rows=48\b")]}])
    r, state = _run(tmp_path, plan)
    assert r.returncode == 1
    line = _events(state)[_find(_events(state), "STEP_FAIL", "A")[0]]
    assert "reason=verdict_mismatch" in line
    info = json.loads((state / "A.fail").read_text())
    assert info["reason"] == "verdict_mismatch" and not (state / "A.done").exists()


def test_invalid_report_and_nonzero_exit(tmp_path):
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        _step("A", "echo OK_DONE; echo 'not json' > {state}/r_A.json", blocking=False),
        _step("B", _ok("B") + "; exit 3", blocking=False),
        _step("C", _ok("C")),
    ]}])
    r, state = _run(tmp_path, plan)
    ev = _events(state)
    assert "reason=report_invalid" in ev[_find(ev, "STEP_FAIL", "A")[0]]
    assert "reason=exit" in ev[_find(ev, "STEP_FAIL", "B")[0]]
    assert _find(ev, "STEP_DONE", "C")
    assert r.returncode == 0  # 只有非阻塞失败
    assert "verdict=PARTIAL" in ev[-1]


def test_nonblocking_failure_dependents_run(tmp_path):
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        _step("A", "echo nope", blocking=False),
        _step("B", _ok("B"), needs=["A"]),
    ]}])
    r, state = _run(tmp_path, plan)
    ev = _events(state)
    assert "blocking=0" in ev[_find(ev, "STEP_FAIL", "A")[0]]
    assert _find(ev, "STEP_DONE", "B")
    assert r.returncode == 0


def test_cross_lane_needs(tmp_path):
    plan = _plan(tmp_path, [
        {"name": "L1", "where": "local", "steps": [_step("A", _ok("A", "sleep 0.8;"))]},
        {"name": "L2", "where": "local", "steps": [
            _step("P", _ok("P")),
            _step("B", "test -f {state}/r_A.json || exit 9; " + _ok("B"), needs=["A"])]},
    ])
    r, state = _run(tmp_path, plan)
    assert r.returncode == 0, r.stdout
    ev = _events(state)
    assert _find(ev, "STEP_DONE", "P")[0] < _find(ev, "STEP_DONE", "A")[0] < _find(ev, "STEP_START", "B")[0]


def test_timeout_and_infra_retries(tmp_path):
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        _step("A", "echo run >> {state}/count_A; sleep 20", timeout_s=0.6, retries=1)]}])
    r, state = _run(tmp_path, plan)
    ev = _events(state)
    assert len(_find(ev, "STEP_START", "A")) == 2 and _find(ev, "STEP_RETRY", "A")
    assert "reason=timeout" in ev[_find(ev, "STEP_FAIL", "A")[0]]
    assert (state / "count_A").read_text().count("run") == 2
    assert (state / "logs" / "A.log").read_text().count("EXIT_CODE=timeout") == 2


def test_resume_skips_done_and_reruns_missing_report(tmp_path):
    state = tmp_path / "state"
    (state / "logs").mkdir(parents=True)
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        _step("A", "touch {state}/ran_A; " + _ok("A")),
        _step("B", "echo x >> {state}/ran_B; " + _ok("B")),
        _step("C", "touch {state}/ran_C; " + _ok("C")),
        _step("D", _ok("D")),
    ]}])
    # A 已完成（预算不得重放）
    (state / "A.done").write_text(json.dumps({"step": "A"}))
    (state / "r_A.json").write_text("{}")
    # B 上次在跑、子进程已死、报告缺失 → 重跑
    (state / "B.running").write_text(json.dumps({"pid": 999999999, "pid_start": "1", "host": HOST, "attempt": 1,
                                                 "log_offset": 0}))
    # C 上次在跑、报告已在、日志里有判定行 → 直接采纳，不重跑
    (state / "logs" / "C.log").write_text("=== ATTEMPT 1 ===\nOK_DONE step=C\n")
    (state / "C.running").write_text(json.dumps({"pid": 999999999, "pid_start": "1", "host": HOST, "attempt": 1,
                                                 "log_offset": 0}))
    (state / "r_C.json").write_text('{"n": 0}')
    r, state = _run(tmp_path, plan)
    assert r.returncode == 0, r.stdout
    ev = _events(state)
    assert not (state / "ran_A").exists() and not _find(ev, "STEP_START", "A")
    assert (state / "ran_B").read_text().count("x") == 1
    assert "attempt=2" in ev[_find(ev, "STEP_START", "B")[0]]
    assert not (state / "ran_C").exists() and not _find(ev, "STEP_START", "C")
    assert "action=adopt_report" in ev[_find(ev, "STEP_RESUME", "C")[0]]
    assert _find(ev, "STEP_DONE", "D")
    # 第二次重启：全部 .done，零执行
    r2, _ = _run(tmp_path, plan)
    assert r2.returncode == 0
    assert (state / "ran_B").read_text().count("x") == 1


def test_resume_existing_report_unverified_needs_human(tmp_path):
    state = tmp_path / "state"
    (state / "logs").mkdir(parents=True)
    (state / "logs" / "A.log").write_text("=== ATTEMPT 1 ===\nhalf\n")
    (state / "A.running").write_text(json.dumps({"pid": 999999999, "pid_start": "1", "host": HOST, "attempt": 1,
                                                 "log_offset": 0}))
    (state / "r_A.json").write_text("{}")
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [_step("A", "touch {state}/ran_A; " + _ok("A"))]}])
    r, state = _run(tmp_path, plan)
    assert not (state / "ran_A").exists()
    assert "reason=resume_unverified" in _events(state)[_find(_events(state), "STEP_FAIL", "A")[0]]
    assert list((state / "notify").glob("*-needs_human-A.json"))
    # 已失败的步骤重启后默认不重跑
    _run(tmp_path, plan)
    assert not (state / "ran_A").exists()


def test_heartbeat_zero_count_keys(tmp_path):
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [_step("A", _ok("A"))]},
                            {"name": "M", "where": "local", "steps": []}])
    r, state = _run(tmp_path, plan)
    hb = json.loads((state / "orch.heartbeat").read_text())  # 序列化后再读回
    assert hb["phase"] == "done"
    assert set(hb["counts"]) == set(orch.STATUS_KEYS)
    assert hb["counts"] == {"pending": 0, "running": 0, "done": 1, "fail": 0, "skipped": 0}
    assert set(hb["fail_reasons"]) == set(orch.FAIL_REASONS) and all(v == 0 for v in hb["fail_reasons"].values())
    assert hb["lanes"]["M"] == {k: 0 for k in orch.STATUS_KEYS}


def test_watchdog_detects_stale_heartbeat(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    hb = state / "orch.heartbeat"
    hb.write_text(json.dumps({"phase": "running"}, indent=1))
    p = subprocess.Popen(["bash", str(WATCHDOG), "--heartbeat", str(hb), "--stale", "2", "--interval", "0.3"],
                         stdout=subprocess.PIPE, text=True)
    try:
        time.sleep(3.6)                       # 超过 stale：只报一次
        ev = (state / "events.log").read_text()
        assert ev.count("ORCH_DEAD") == 1
        hb.write_text(json.dumps({"phase": "running"}, indent=1))   # 恢复
        time.sleep(0.8)
        assert "ORCH_ALIVE" in (state / "events.log").read_text()
        hb.write_text(json.dumps({"phase": "done"}, indent=1))      # 正常收尾 → 看门狗退出
        out, _ = p.communicate(timeout=5)
    finally:
        if p.poll() is None:
            p.kill()
    assert p.returncode == 0
    assert "WATCHDOG_EXIT" in out and out.rstrip().endswith("EXIT_CODE=0")
    assert list((state / "notify").glob("*-needs_human-orch_dead.json"))


def test_watchdog_missing_heartbeat_and_sigterm(tmp_path):
    hb = tmp_path / "orch.heartbeat"
    p = subprocess.Popen(["bash", str(WATCHDOG), "--heartbeat", str(hb), "--stale", "2", "--interval", "0.2"],
                         stdout=subprocess.PIPE, text=True)
    time.sleep(0.6)
    p.send_signal(signal.SIGTERM)
    out, _ = p.communicate(timeout=5)
    assert "ORCH_DEAD" in out and "age_s=-1" in out and "EXIT_CODE=143" in out


def _wait_for(pred, timeout=15.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_kill9_then_restart_adopts_running_child(tmp_path):
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        _step("A", _ok("A")),
        _step("B", "echo x >> {state}/ran_B; sleep 5; " + _ok("B")),
        _step("C", "test -f {state}/r_B.json || exit 5; " + _ok("C")),
    ]}])
    state = tmp_path / "state"
    cmd = [sys.executable, str(ORCH), "--plan", str(plan), "--state", str(state), "--workdir", str(tmp_path),
           "--poll-s", "0.05", "--heartbeat-s", "0.3"]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert _wait_for(lambda: (state / "B.running").exists() and (state / "ran_B").exists())
    os.kill(p.pid, signal.SIGKILL)            # 编排器崩溃，子进程（独立会话）仍在跑
    p.wait()
    # 看门狗独立发现编排器已死
    wd = subprocess.run(["bash", "-c", f"timeout 3 bash {WATCHDOG} --heartbeat {state}/orch.heartbeat "
                                       f"--stale 1 --interval 0.3; true"],
                        capture_output=True, text=True, timeout=10)
    assert "ORCH_DEAD" in wd.stdout
    r, _ = _run(tmp_path, plan)
    assert r.returncode == 0, r.stdout
    ev = _events(state)
    assert _find(ev, "STEP_ADOPT", "B")
    assert (state / "ran_B").read_text().count("x") == 1     # 未重复派发
    assert _find(ev, "STEP_DONE", "B")[0] < _find(ev, "STEP_START", "C")[-1]
    assert len(_find(ev, "STEP_START", "A")) == 1
    assert "EXIT_CODE=unknown(adopted)" in (state / "logs" / "B.log").read_text()


def test_kill9_with_child_killed_reruns(tmp_path):
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        _step("B", "echo x >> {state}/ran_B; sleep 30; " + _ok("B"))]}])
    state = tmp_path / "state"
    cmd = [sys.executable, str(ORCH), "--plan", str(plan), "--state", str(state), "--workdir", str(tmp_path),
           "--poll-s", "0.05"]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert _wait_for(lambda: (state / "B.running").exists())
    info = json.loads((state / "B.running").read_text())
    os.kill(p.pid, signal.SIGKILL)
    os.killpg(info["pid"], signal.SIGKILL)    # 整个步骤一起死（如节点重启）
    p.wait()
    assert _wait_for(lambda: orch._proc_start(info["pid"]) is None)
    plan2 = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        _step("B", "echo x >> {state}/ran_B; " + _ok("B"))]}])
    r, _ = _run(tmp_path, plan2)
    assert r.returncode == 0, r.stdout
    ev = _events(state)
    assert "action=rerun" in ev[_find(ev, "STEP_RESUME", "B")[0]]
    assert (state / "ran_B").read_text().count("x") == 2


def test_gl_srun_argv_and_slurm_env_stripped(monkeypatch):
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setenv("SLURM_CPU_BIND", "x")
    monkeypatch.setenv("KEEP_ME", "1")
    argv, env = orch.build_command({"gl_jobid": 62608440}, "echo hi")
    assert argv == ["srun", "--jobid=62608440", "--overlap", "--exact", "--ntasks=1", "--cpus-per-task=4",
                    "--gpu_cmode=shared", "bash", "-c", "echo hi"]
    argv, _ = orch.build_command({"gl_jobid": 62608440}, "echo hi", step="env-yi")
    assert argv == ["srun", "--jobid=62608440", "--overlap", "--exact", "--ntasks=1", "--cpus-per-task=4",
                    "--gpu_cmode=shared", "--job-name=v75-env-yi", "bash", "-c", "echo hi"]
    assert not [k for k in env if k.startswith("SLURM_")] and env["KEEP_ME"] == "1"
    argv, env = orch.build_command("local", "echo hi")
    assert argv == ["bash", "-c", "echo hi"] and env["SLURM_JOB_ID"] == "123"

    # 模拟 Popen：核对编排器真正传给子进程的 argv / env
    seen = {}

    class FakePopen:
        def __init__(self, a, **kw):
            seen["argv"], seen["env"] = a, kw["env"]
            self.pid = os.getpid()

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(orch.subprocess, "Popen", FakePopen)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        plan = {"lanes": [{"name": "G", "where": {"gl_jobid": 7}, "steps": [
            {"name": "S", "cmd": "run {step}", "report": "{state}/r.json", "verdict_regex": "^X"}]}]}
        p = Path(td) / "plan.json"
        p.write_text(json.dumps(plan))
        o = orch.Orchestrator(orch.load_plan(p), Path(td) / "st", Path(td), heartbeat_s=10, seat_check_s=1e6,
                              squeue="/bin/false")
        o.run()
    assert seen["argv"] == orch.srun_argv(7, "run S", step="S")
    assert "--job-name=v75-S" in seen["argv"]
    assert not [k for k in seen["env"] if k.startswith("SLURM_")]


def test_gl_lane_fake_srun_and_seat_expiring(tmp_path):
    fake = tmp_path / "fake_srun"
    fake.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$FAKE_DIR/argv\"\nenv > \"$FAKE_DIR/env\"\n"
                    "shift 7\n[ \"$1\" = bash ] && [ \"$2\" = -c ] || exit 99\nexec bash -c \"$3\"\n")
    fake.chmod(0o755)
    sq = tmp_path / "fake_squeue"
    sq.write_text("#!/usr/bin/env bash\necho \"$@\" >> \"$FAKE_DIR/squeue_calls\"\necho 03:00:00\n")
    sq.chmod(0o755)
    plan = _plan(tmp_path, [{"name": "G", "where": {"gl_jobid": 62608595}, "steps": [
        _step("S1", "sleep 1; " + _ok("S1"))]}])
    env = dict(os.environ, SLURM_JOB_ID="62612889", SLURM_CPU_BIND="quiet", FAKE_DIR=str(tmp_path))
    r, state = _run(tmp_path, plan, "--srun", str(fake), "--squeue", str(sq), "--seat-check-s", "0.2", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    argv = (tmp_path / "argv").read_text().splitlines()
    assert argv[:8] == ["--jobid=62608595", "--overlap", "--exact", "--ntasks=1", "--cpus-per-task=4",
                        "--gpu_cmode=shared", "--job-name=v75-S1", "bash"]
    assert "SLURM_" not in (tmp_path / "env").read_text()
    ev = _events(state)
    exp = _find(ev, "SEAT_EXPIRING")
    assert len(exp) == 1 and _kv(ev[exp[0]])["left_s"] == "10800"
    assert "-h -j 62608595 -o %L" in (tmp_path / "squeue_calls").read_text()
    assert list((state / "notify").glob("*-needs_human-G.json"))


def test_parse_time_left():
    assert orch.parse_time_left("1-02:03:04") == 86400 + 7384
    assert orch.parse_time_left("05:06") == 306
    assert orch.parse_time_left("INVALID") is None
    assert orch.parse_time_left("UNLIMITED") == float("inf")


def test_dry_run_and_invalid_plan(tmp_path):
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [_step("A", "touch {state}/ran"),
                                                                      _step("B", "true", needs=["A"])]}])
    r, state = _run(tmp_path, plan, "--dry-run")
    assert r.returncode == 0 and "DRYRUN lane=L step=B" in r.stdout and "DRYRUN_OK lanes=1 steps=2" in r.stdout
    assert not state.exists()
    bad = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [_step("A", "true", needs=["B"]),
                                                                     _step("B", "true")]}])
    r, _ = _run(tmp_path, bad, "--dry-run")
    assert r.returncode == 2 and "PLAN_INVALID" in r.stdout
    bad2 = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [_step("A", "true", needs=["Z"])]}])
    r, _ = _run(tmp_path, bad2, "--dry-run")
    assert r.returncode == 2


def _fake_squeue(tmp_path, body):
    sq = tmp_path / "fake_squeue"
    sq.write_text("#!/usr/bin/env bash\necho \"$@\" >> \"$FAKE_DIR/squeue_calls\"\n" + body)
    sq.chmod(0o755)
    return sq


def _gl_running(state, step, host="otherhost"):
    (state / "logs").mkdir(parents=True, exist_ok=True)
    (state / "logs" / f"{step}.log").write_text("=== ATTEMPT 1 ===\n")
    (state / f"{step}.running").write_text(json.dumps({"pid": 4242, "pid_start": "7", "host": host, "attempt": 1,
                                                        "log_offset": 0}))


def test_cross_host_resume_adopts_live_gl_step(tmp_path):
    # 另一主机上的编排器留下 .running；远端作业步 v75-S1 仍在跑 → 接管等待、不重复派发
    state = tmp_path / "state"
    _gl_running(state, "S1")
    flag = tmp_path / "remote_alive"
    flag.write_text("1")
    sq = _fake_squeue(tmp_path, 'if [ "$2" = -s ]; then [ -e "$FAKE_DIR/remote_alive" ] && echo "62608595.3,v75-S1"; '
                                'else echo 2-00:00:00; fi\n')
    plan = _plan(tmp_path, [{"name": "G", "where": {"gl_jobid": 62608595}, "steps": [
        _step("S1", "touch {state}/ran_S1; " + _ok("S1"))]}])
    env = dict(os.environ, FAKE_DIR=str(tmp_path))
    cmd = [sys.executable, str(ORCH), "--plan", str(plan), "--state", str(state), "--workdir", str(tmp_path),
           "--poll-s", "0.05", "--remote-poll-s", "0.2", "--squeue", str(sq), "--srun", "/bin/false"]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    assert _wait_for(lambda: _find(_events(state), "STEP_ADOPT_REMOTE", "S1"))
    time.sleep(0.5)
    assert p.poll() is None
    # 远端步骤收尾：写判定行与报告后退出
    with open(state / "logs" / "S1.log", "a") as f:
        f.write("OK_DONE step=S1\n")
    (state / "r_S1.json").write_text("{}")
    flag.unlink()
    assert p.wait(timeout=10) == 0
    ev = _events(state)
    assert _find(ev, "STEP_DONE", "S1") and not _find(ev, "STEP_START", "S1")
    assert not (state / "ran_S1").exists()
    assert "-h -s -j 62608595 -o %i,%j" in (tmp_path / "squeue_calls").read_text()
    assert "EXIT_CODE=unknown(adopted_remote)" in (state / "logs" / "S1.log").read_text()


def test_cross_host_resume_unknown_needs_human(tmp_path):
    # squeue 查不了、又没有存活文件 → 不知道死活：需人工，绝不重跑
    state = tmp_path / "state"
    _gl_running(state, "S1")
    sq = _fake_squeue(tmp_path, "exit 1\n")
    plan = _plan(tmp_path, [{"name": "G", "where": {"gl_jobid": 62608595}, "steps": [
        _step("S1", "touch {state}/ran_S1; " + _ok("S1")), _step("S2", _ok("S2"))]}])
    r, state = _run(tmp_path, plan, "--squeue", str(sq), "--srun", "/bin/false",
                    env=dict(os.environ, FAKE_DIR=str(tmp_path)))
    assert r.returncode == 1
    ev = _events(state)
    assert "reason=resume_unknown" in ev[_find(ev, "STEP_FAIL", "S1")[0]]
    assert "reason=upstream" in ev[_find(ev, "STEP_FAIL", "S2")[0]]
    assert not _find(ev, "STEP_START") and not (state / "ran_S1").exists()
    assert list((state / "notify").glob("*-needs_human-S1.json"))


def test_cross_host_alive_file_stale_reruns(tmp_path):
    # 本机线、换了主机，但存活文件已过期 → 确认已死，报告缺失 → 重跑
    state = tmp_path / "state"
    _gl_running(state, "A")
    af = tmp_path / "alive_A"
    af.write_text("")
    os.utime(af, (time.time() - 100, time.time() - 100))
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        _step("A", "touch {state}/ran_A; " + _ok("A"), alive_file=str(af), alive_stale_s=5)]}])
    r, state = _run(tmp_path, plan)
    assert r.returncode == 0, r.stdout
    ev = _events(state)
    assert "action=rerun" in ev[_find(ev, "STEP_RESUME", "A")[0]]
    assert (state / "ran_A").exists()


def test_timeout_sigterm_grace_then_sigkill(tmp_path):
    plan = _plan(tmp_path, [{"name": "L", "where": "local", "steps": [
        # 收到 TERM 后做清理再退出：宽限内完成
        _step("A", "trap 'sleep 0.5; echo cleanup >> {state}/cleaned; exit 0' TERM; sleep 20 & wait",
              timeout_s=0.5, blocking=False),
        # 忽略 TERM：宽限到期后 SIGKILL
        _step("B", "trap '' TERM; sleep 20", timeout_s=0.5, blocking=False),
    ]}])
    t0 = time.time()
    r, state = _run(tmp_path, plan, "--term-grace-s", "2")
    assert time.time() - t0 < 12
    ev = _events(state)
    assert (state / "cleaned").read_text().strip() == "cleanup"
    for s in ("A", "B"):
        assert "reason=timeout" in ev[_find(ev, "STEP_FAIL", s)[0]]


def test_seat_not_in_queue(tmp_path):
    sq = _fake_squeue(tmp_path, "echo 'slurm_load_jobs error: Invalid job id specified' >&2; exit 1\n")
    plan = _plan(tmp_path, [{"name": "G", "where": {"gl_jobid": 1}, "steps": [
        _step("S1", "sleep 1; " + _ok("S1"))]}])
    fake = tmp_path / "fake_srun"
    fake.write_text("#!/usr/bin/env bash\nshift 7\nexec bash -c \"$3\"\n")
    fake.chmod(0o755)
    r, state = _run(tmp_path, plan, "--srun", str(fake), "--squeue", str(sq), "--seat-check-s", "0.2",
                    env=dict(os.environ, FAKE_DIR=str(tmp_path)))
    assert r.returncode == 0, r.stdout
    ev = _events(state)
    exp = _find(ev, "SEAT_EXPIRING")
    assert len(exp) == 1 and "reason=not_in_queue" in ev[exp[0]] and "left_s=0" in ev[exp[0]]
    assert not _find(ev, "SEAT_QUERY_FAIL")
    assert list((state / "notify").glob("*-needs_human-G.json"))
