"""C16 席位脚本（慢）：真 bash 运行真实 ``run_seat.sh``／``run_eval_gl.sh``，server 与客户端换成假引擎
（``seat_fake_engine.py``），``nvidia-smi`` 换成空输出的替身，不碰 GPU。

覆盖：端口占用顺延、server 未就绪先死、客户端首推理放宽只给 server 新起后的第一个客户端、客户端重启预算、
server 中途死亡的重启预算、额度耗尽与阻塞不重启、TERM 收尾（含 server 忽略 TERM 时的 KILL）、``SMVLA_PY`` 未设
与 mme tokenizer 参数缺失的 RUN_BLOCKED、参数错误；``run_eval_gl.sh`` 的录像原子发布、重复发布不覆盖、
中断收尾只写一次。轮询间隔用 ``SEAT_POLL_S``／``SEAT_READY_POLL_S`` 缩短。
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

import eval_fakes as F

pytestmark = pytest.mark.slow

EO = F.REPO / "scripts" / "eval-official"
ENGINE = Path(__file__).resolve().parent / "seat_fake_engine.py"

if shutil.which("setsid") is None or shutil.which("rsync") is None:  # pragma: no cover
    pytest.skip("未验证：缺 setsid 或 rsync", allow_module_level=True)


def _port_free(p: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", p))
        except OSError:
            return False
    return True


def _free_seat_idx() -> int:
    """找一个席号，使其 smvla／mme 两个基础端口段（各 +0～+9）都空闲。"""
    for idx in range(97, 40, -1):
        base = 18000 + 100 * idx
        if all(_port_free(base + d) for d in range(20)):
            return idx
    raise RuntimeError("找不到空闲端口段")


@pytest.fixture
def rig(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fakepy = bin_dir / "fakepy"
    fakepy.write_text(f"""#!/usr/bin/env bash
case "$1" in
  -|-c) exec "{sys.executable}" "$@";;
  *smvla_server.py) shift; exec "{sys.executable}" "{ENGINE}" server "$@";;
  *env_client.py) shift; exec "{sys.executable}" "{ENGINE}" client "$@";;
  *) exec "{sys.executable}" "$@";;
esac
""", encoding="utf-8")
    (bin_dir / "nvidia-smi").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for p in (fakepy, bin_dir / "nvidia-smi"):
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    ckpt = tmp_path / "ckpt"
    ckpt.mkdir()
    (ckpt / "config.json").write_text("{}", encoding="utf-8")
    task, tier = F.v9_cells_sorted()[0]
    idents = [F.packaged_identity(task, tier, k) for k in range(2)]
    shard = tmp_path / "shard-00.json"
    shard.write_text(json.dumps(idents), encoding="utf-8")
    env = dict(os.environ)
    env.update(PATH=f"{bin_dir}:{env['PATH']}", BENCH_PY=str(fakepy), SMVLA_PY=str(fakepy), SMVLA_CKPT=str(ckpt),
               SEAT_POLL_S="0.2", SEAT_READY_POLL_S="0.1", FAKE_LOG=str(tmp_path / "fake.jsonl"),
               FAKE_STATE=str(tmp_path / "client-count"), FAKE_SERVER_MODE="ok", FAKE_CLIENT_CODES="0")
    return {"tmp": tmp_path, "fakepy": fakepy, "env": env, "shard": shard, "idents": idents, "ckpt": ckpt,
            "idx": _free_seat_idx()}


def _seat_cmd(rig, *extra, out=None, policies="smvla", v8=True):
    out = out or rig["tmp"] / "out"
    cmd = ["bash", str(EO / "run_seat.sh"), "--seat", "T", "--seat-idx", str(rig["idx"]), "--gpu", "0",
           "--cond", "C", "--out", str(out), "--identities", str(rig["shard"]), "--policies", policies,
           "--episode-wall-smvla", "30"]
    if v8:
        cmd += ["--v8", "--ledger-dir", str(out / "smvla"), "--reset-budget", "10", "--infra-retry-budget", "2"]
    return cmd + list(extra)


def _run(cmd, env, timeout=90):
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout


def _events(rig, role=None, event=None):
    rows = F.read_jsonl(rig["tmp"] / "fake.jsonl")
    return [r for r in rows if (role is None or r["role"] == role) and (event is None or r["event"] == event)]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # 僵尸进程也算已结束
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


def _wait_line(path: Path, needle: str, timeout: float = 30.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if path.exists() and needle in path.read_text(encoding="utf-8", errors="replace"):
            return
        time.sleep(0.1)
    raise AssertionError(f"{timeout}s 内日志 {path} 没有出现 {needle!r}")


# ---------------------------------------------------------------- run_seat.sh


def test_normal_run_and_first_extra_only_on_fresh_server(rig):
    rc, out = _run(_seat_cmd(rig), rig["env"])
    assert rc == 0, out
    assert out.rstrip().splitlines()[-1] == "EXIT_CODE=0"
    assert "SERVER_READY policy=smvla" in out and "SERVER_STOPPED" in out
    assert "SEAT_DONE policy=smvla cond=C seat=T done=2 errors=0 infra=0" in out
    (c,) = _events(rig, "client", "start")
    assert c["first_extra_s"] == "600" and c["v8"] is True and c["wall_s"] == "30"
    (s,) = _events(rig, "server", "start")
    assert s["port"] == 18000 + 100 * rig["idx"]
    assert _events(rig, "server", "term")  # 收尾时 server 被 TERM
    rep = json.loads((rig["tmp"] / "out" / "smvla" / "seat-report.json").read_text())
    assert rep["done"] == 2 and rep["success"] == 2 and rep["loop_exit_status"] == 0


def test_port_busy_moves_to_next_pair(rig):
    base = 18000 + 100 * rig["idx"]
    with socket.socket() as hold:
        hold.bind(("127.0.0.1", base))
        hold.listen(1)
        rc, out = _run(_seat_cmd(rig), rig["env"])
    assert rc == 0, out
    assert f"SERVER_START policy=smvla port={base + 2} " in out
    assert _events(rig, "client", "start")[0]["port"] == str(base + 2)


def test_server_dies_before_ready(rig):
    rig["env"]["FAKE_SERVER_MODE"] = "die_before_ready"
    rc, out = _run(_seat_cmd(rig), rig["env"])
    assert rc != 0 and out.rstrip().splitlines()[-1] == f"EXIT_CODE={rc}"
    assert "SERVER_DIED_BEFORE_READY policy=smvla" in out
    assert _events(rig, "client") == []


def test_client_infra_exit_restarts_without_first_extra(rig):
    rig["env"]["FAKE_CLIENT_CODES"] = "75,0"
    rc, out = _run(_seat_cmd(rig), rig["env"])
    assert rc == 0, out
    starts = _events(rig, "client", "start")
    assert [c["first_extra_s"] for c in starts] == ["600", "0"]
    assert "CLIENT_EXIT policy=smvla rc=75" in out
    assert len(_events(rig, "server", "start")) == 1  # 只重起客户端，server 不动


def test_client_restart_budget_exhausted(rig):
    rig["env"]["FAKE_CLIENT_CODES"] = "75"
    rc, out = _run(_seat_cmd(rig), rig["env"])
    assert rc == 4
    line = next(x for x in out.splitlines() if x.startswith("INFRA_EXHAUSTED policy=smvla client_restarts="))
    restarts = int(line.split("client_restarts=")[1].split()[0])
    assert len(_events(rig, "client", "start")) == restarts  # 首次 + (restarts-1) 次重启，第 restarts 次超额即停
    assert out.rstrip().splitlines()[-1] == "EXIT_CODE=4"


@pytest.mark.parametrize("code,needle,want_rc", [(5, "RESET_BUDGET_EXHAUSTED policy=smvla", 5),
                                                 (3, "RUN_BLOCKED reason=client policy=smvla", 3)])
def test_budget_and_blocked_are_not_restarted(rig, code, needle, want_rc):
    rig["env"]["FAKE_CLIENT_CODES"] = str(code)
    rc, out = _run(_seat_cmd(rig), rig["env"])
    assert rc == want_rc and needle in out
    assert len(_events(rig, "client", "start")) == 1


def test_server_death_restart_budget(rig):
    rig["env"].update(FAKE_SERVER_MODE="die_after", FAKE_SERVER_LIFE="1", FAKE_CLIENT_CODES="-1")
    rc, out = _run(_seat_cmd(rig), rig["env"], timeout=120)
    assert rc == 4, out
    line = next(x for x in out.splitlines() if x.startswith("INFRA_EXHAUSTED policy=smvla server_restarts="))
    n = int(line.split("server_restarts=")[1].split()[0])
    assert len(_events(rig, "server", "start")) == n  # 首次 + (n-1) 次重起
    assert out.count("SERVER_DIED policy=smvla") == n
    for c in _events(rig, "client", "start"):  # 每个客户端都已被收掉
        assert not _alive(c["pid"])


@pytest.mark.parametrize("server_mode", ["ok", "ignore_term"])
def test_term_cleans_up_server_and_client(rig, server_mode):
    """TERM：收掉客户端与 server 的进程组；server 忽略 TERM 时等满宽限后 KILL（这一档约 60 s）。"""
    rig["env"].update(FAKE_SERVER_MODE=server_mode, FAKE_CLIENT_CODES="-1")
    log = rig["tmp"] / "out" / "seat-T.log"
    p = subprocess.Popen(_seat_cmd(rig), env=rig["env"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        _wait_line(log, "CLIENT_START policy=smvla")
        time.sleep(0.5)
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=120)
    finally:
        if p.poll() is None:
            p.kill()
    assert p.returncode == 143 and out.rstrip().splitlines()[-1] == "EXIT_CODE=143"
    for r in _events(rig, None, "start"):
        assert not _alive(r["pid"]), r
    if server_mode == "ignore_term":
        assert not _events(rig, "server", "term")


def test_smvla_py_unset_blocks(rig):
    rig["env"].pop("SMVLA_PY")
    rc, out = _run(_seat_cmd(rig), rig["env"])
    assert rc == 3 and "RUN_BLOCKED reason=smvla_py_unset" in out
    assert _events(rig) == []


def test_mme_v8_requires_tokenizer_args(rig):
    rc, out = _run(_seat_cmd(rig, policies="mme"), rig["env"])
    assert rc == 3 and "RUN_BLOCKED reason=tokenizer_sha" in out
    assert _events(rig) == []


@pytest.mark.parametrize("extra", [["--ledger-dir", "x"], ["--episode-wall-mme", "abc"], ["--bogus"]])
def test_bad_args_exit_2(rig, extra):
    cmd = _seat_cmd(rig, v8=False) + extra
    rc, _ = _run(cmd, rig["env"])
    assert rc == 2


# ---------------------------------------------------------------- run_eval_gl.sh


@pytest.fixture
def gl_repo(rig):
    """run_eval_gl.sh 把解释器写死在 <repo> 下：建一个只含两个真实脚本与假解释器的最小 repo。"""
    repo = rig["tmp"] / "repo"
    (repo / "scripts" / "eval-official").mkdir(parents=True)
    for name in ("run_seat.sh", "run_eval_gl.sh"):
        shutil.copy2(EO / name, repo / "scripts" / "eval-official" / name)
    for rel in (".venv/bin/python", "artifacts/v8-two/venvs/smvla-env/bin/python"):
        (repo / rel).parent.mkdir(parents=True)
        (repo / rel).symlink_to(rig["fakepy"])
    return repo


def _gl_cmd(rig, repo, stage, seat):
    return ["bash", str(repo / "scripts" / "eval-official" / "run_eval_gl.sh"), "--run-name", "R", "--seat", seat,
            "--repo", str(repo), "--stage", str(stage), "--shard", str(rig["shard"]), "--policies", "smvla",
            "--smvla-ckpt", str(rig["ckpt"]), "--reset-budget", "10", "--infra-retry-budget", "2",
            "--sync-interval", "1", "--local-root", str(rig["tmp"] / "local"), "--episode-wall-smvla", "30"]


def test_gl_publishes_recordings_atomically_and_rerun_does_not_overwrite(rig, gl_repo):
    seat = f"{rig['idx']:02d}"
    stage = rig["tmp"] / "stage"
    rc, out = _run(_gl_cmd(rig, gl_repo, stage, seat), rig["env"])
    assert rc == 0, out
    assert f"V8_SEAT_DONE seat={seat} outcome=pass rc=0" in out
    sync = next(x for x in out.splitlines() if x.startswith("SEAT_REC_SYNC="))
    assert sync.startswith("SEAT_REC_SYNC=PASS n=2 ") and " left=0 " in sync
    rec = stage / f"s{seat}" / "smvla" / "rec"
    for ident in rig["idents"]:
        d = rec / f"{ident['key']}.a1"
        assert (d / "front.mkv").read_bytes() == b"front-" + ident["key"].encode()
        assert (d / "summary.json").is_file()
    assert not (rec / ".incoming").exists() or not any((rec / ".incoming").iterdir())
    assert not any((rig["tmp"] / "local" / "rec" / "smvla").iterdir())  # 节点副本已删
    # 同一运行根再跑一遍：同名目录不覆盖，发布成 .dup1
    (rig["tmp"] / "client-count").unlink()
    rc2, out2 = _run(_gl_cmd(rig, gl_repo, stage, seat), rig["env"])
    assert rc2 == 0, out2
    assert out2.count("REC_SYNC_DUP") == 2
    assert all((rec / f"{i['key']}.a1.dup1").is_dir() for i in rig["idents"])
    assert (rec / f"{rig['idents'][0]['key']}.a1" / "front.mkv").is_file()


def test_gl_term_finalizes_once(rig, gl_repo):
    seat = f"{rig['idx']:02d}"
    stage = rig["tmp"] / "stage"
    rig["env"]["FAKE_CLIENT_CODES"] = "-1"
    p = subprocess.Popen(_gl_cmd(rig, gl_repo, stage, seat), env=rig["env"], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    try:
        _wait_line(stage / f"s{seat}" / "smvla" / f"seat-{seat}.log", "CLIENT_START policy=smvla")
        time.sleep(0.5)
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=120)
    finally:
        if p.poll() is None:
            p.kill()
    assert p.returncode == 143
    assert out.count("V8_SEAT_DONE") == 1 and f"V8_SEAT_DONE seat={seat} outcome=aborted rc=143" in out
    assert out.rstrip().splitlines()[-1] == "EXIT_CODE=143"
    for r in _events(rig, None, "start"):
        assert not _alive(r["pid"]), r


def test_gl_rejects_no_record(rig, gl_repo):
    cmd = _gl_cmd(rig, gl_repo, rig["tmp"] / "stage", "01") + ["--no-record"]
    rc, out = _run(cmd, rig["env"])
    assert rc == 2 and "V8_SEAT_DONE seat=01 outcome=fail rc=2 reason=bad_args" in out
