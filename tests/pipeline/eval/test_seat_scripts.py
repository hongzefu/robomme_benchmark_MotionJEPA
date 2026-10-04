"""C16 席位脚本（慢）：真 bash 运行真实 ``run_seat.sh``／``run_eval_gl.sh``／``run_official_hard.sh``／``pair_seat.sh``，
server、客户端与原侧驱动换成假引擎（``seat_fake_engine.py``），``nvidia-smi`` 换成空输出的替身，不碰 GPU；转码用真
ffmpeg（16×16 微型帧）。

覆盖：端口占用顺延、server 未就绪先死、客户端首推理放宽只给 server 新起后的第一个客户端、客户端重启预算、
server 中途死亡的重启预算（每次就绪记一个 server_epoch）、额度耗尽／阻塞／账本未齐（6）不重启、TERM 收尾（含 server
忽略 TERM 时的 KILL）、``SMVLA_PY`` 未设与 mme tokenizer 参数缺失的 RUN_BLOCKED、参数错误（含已删除的 ``--v8``）、
``--dataset``↔``--max-steps`` 配对与 mmesg 变体配对的 RUN_BLOCKED、pp 路线（/health 就绪、``--args.seed 0``、
results.epochs.jsonl）；``run_eval_gl.sh`` 的就地转码（帧数核对、删原始帧、并入轨迹）与按输出键原子发布、重复发布
不覆盖、中断收尾只写一次；``run_official_hard.sh`` 的分轮重试（先重启服务再重发、重试额度、synthetic 之外的正常路径）
与原侧转码发布；``pair_seat.sh`` 先原侧后新侧、前一侧服务退出后才起后一侧。轮询间隔用
``SEAT_POLL_S``／``SEAT_READY_POLL_S`` 缩短。
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
SCRIPTS = ("run_seat.sh", "run_eval_gl.sh", "run_official_hard.sh", "pair_seat.sh")

if shutil.which("setsid") is None or shutil.which("rsync") is None or shutil.which("ffmpeg") is None:  # pragma: no cover
    pytest.skip("未验证：缺 setsid、rsync 或 ffmpeg", allow_module_level=True)


def _port_free(p: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", p))
        except OSError:
            return False
    return True


def _free_seat_idx() -> int:
    """找一个席号，使其四个策略的基础端口段（各 +0～+9）都空闲。"""
    for idx in range(97, 40, -1):
        base = 18000 + 100 * idx
        if all(_port_free(base + d) for d in range(40)):
            return idx
    raise RuntimeError("找不到空闲端口段")


def _hard0_rows(n: int) -> list[dict]:
    """test-hard0 执行身份行（手写；假引擎不解析 builder）。"""
    out = []
    for k in range(n):
        seed = 510300 + k
        out.append({"task": "PickXtimes", "tier": "xhard0", "seed": seed, "candidate": None, "builder_episode": k,
                    "source_episode": k, "spec_sha256": None, "key": f"PickXtimes_xhard0_{seed}"})
    return out


@pytest.fixture
def rig(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fakepy = bin_dir / "fakepy"
    fakepy.write_text(f"""#!/usr/bin/env bash
case "$1" in
  -|-c) exec "{sys.executable}" "$@";;
  -m) if [[ "$2" == ponderpounce.eval.robomme_server ]]; then shift 2; exec "{sys.executable}" "{ENGINE}" server "$@"; fi
      exec "{sys.executable}" "$@";;
  *smvla_server.py|*serve_policy.py) shift; exec "{sys.executable}" "{ENGINE}" server "$@";;
  *env_client.py) shift; exec "{sys.executable}" "{ENGINE}" client "$@";;
  *pp_official_runner.py|*official_hard_runner.py) shift; exec "{sys.executable}" "{ENGINE}" runner "$@";;
  *) exec "{sys.executable}" "$@";;
esac
""", encoding="utf-8")
    (bin_dir / "nvidia-smi").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for p in (fakepy, bin_dir / "nvidia-smi"):
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    ckpt = tmp_path / "ckpt"
    ckpt.mkdir()
    (ckpt / "config.json").write_text("{}", encoding="utf-8")
    pp_ckpt = tmp_path / "pp-ckpt"
    pp_ckpt.mkdir()
    (pp_ckpt / "norm_stats.json").write_text("{}", encoding="utf-8")
    task, tier = F.v9_cells_sorted()[0]
    idents = [F.packaged_identity(task, tier, k) for k in range(2)]
    shard = tmp_path / "shard-00.json"
    shard.write_text(json.dumps(idents), encoding="utf-8")
    hard0 = _hard0_rows(2)
    shard0 = tmp_path / "shard0-00.json"
    shard0.write_text(json.dumps(hard0), encoding="utf-8")
    env = dict(os.environ)
    env.update(PATH=f"{bin_dir}:{env['PATH']}", BENCH_PY=str(fakepy), SMVLA_PY=str(fakepy), SMVLA_CKPT=str(ckpt),
               SGEVAL_CLIENT_PY=str(fakepy), PP_PY=str(fakepy),
               SEAT_POLL_S="0.2", SEAT_READY_POLL_S="0.1", FAKE_LOG=str(tmp_path / "fake.jsonl"),
               FAKE_STATE=str(tmp_path / "client-count"), FAKE_SERVER_MODE="ok", FAKE_CLIENT_CODES="0")
    yield {"tmp": tmp_path, "fakepy": fakepy, "env": env, "shard": shard, "idents": idents, "ckpt": ckpt,
           "pp_ckpt": pp_ckpt, "shard0": shard0, "hard0": hard0, "idx": _free_seat_idx()}
    # 测试侧兜底：无论生产收尾是否生效，本用例起过的假进程一律收干净
    _reap(tmp_path)
    left = [pid for pid in _recorded_pids(tmp_path) if _alive(pid) and _is_ours(pid)]
    assert left == [], f"teardown 后仍有存活进程 {left}"


def _seat_cmd(rig, *extra, out=None, policies="smvla", dataset="test-hard", max_steps=None, strict=None, ledger=True):
    out = out or rig["tmp"] / "out"
    max_steps = max_steps or (1300 if dataset == "test-hard0" else 1600)
    strict = (dataset == "test-hard") if strict is None else strict
    cmd = ["bash", str(EO / "run_seat.sh"), "--seat", "T", "--seat-idx", str(rig["idx"]), "--gpu", "0",
           "--cond", "C", "--out", str(out), "--identities", str(rig["shard"]), "--policies", policies,
           "--episode-wall-smvla", "30", "--dataset", dataset, "--max-steps", str(max_steps)]
    if strict:
        cmd.append("--strict-cap")
    if ledger:
        cmd += ["--ledger-dir", str(out / "ledger"), "--reset-budget", "10", "--infra-retry-budget", "2"]
    return cmd + list(extra)


def _killpg(pid: int, sig=signal.SIGKILL) -> None:
    """按进程组发信号；绝不对 pytest 自己所在的进程组发（那时退回只发给该进程）。"""
    try:
        pg = os.getpgid(pid)
    except ProcessLookupError:
        return
    try:
        if pg != os.getpgid(0):
            os.killpg(pg, sig)
        else:
            os.kill(pid, sig)
    except ProcessLookupError:
        pass


def _run(cmd, env, timeout=90):
    """bash 本身起在新会话里；超时或异常时按 pgid 杀整组。"""
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
    except BaseException:
        _killpg(p.pid)
        p.communicate()
        raise
    return p.returncode, out


def _popen(cmd, env):
    return subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            start_new_session=True)


def _recorded_pids(tmp: Path) -> list[int]:
    """本用例记下的全部 pid：假引擎每次启动的事件行，加脚本写的 ``.v8-pgids``（setsid 进程组首进程）。"""
    pids = {int(r["pid"]) for r in F.read_jsonl(tmp / "fake.jsonl") if r.get("event") == "start"}
    for f in tmp.rglob(".v8-pgids"):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit():
                pids.add(int(parts[1]))
    return sorted(pids)


def _is_ours(pid: int) -> bool:
    """防 PID 复用误杀：只认命令行确属假引擎、假解释器包装 ``fakepy``（exec 之前的瞬间）或本测试起的席位脚本的进程。"""
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return False
    return any(x in cmd for x in ("seat_fake_engine", "fakepy") + SCRIPTS)


def _reap(tmp: Path, grace: float = 3.0) -> list[int]:
    """对仍存活的已记录进程按进程组 SIGTERM，等至多 grace 秒，仍在的 SIGKILL 并再等至多 5 秒。返回动过手的 pid。"""
    live = [pid for pid in _recorded_pids(tmp) if _alive(pid) and _is_ours(pid)]
    for pid in live:
        _killpg(pid, signal.SIGTERM)
    t0 = time.time()
    while time.time() - t0 < grace and any(_alive(p) for p in live):
        time.sleep(0.05)
    for pid in live:
        if _alive(pid):
            _killpg(pid, signal.SIGKILL)
    t0 = time.time()
    while time.time() - t0 < 5 and any(_alive(p) for p in live):
        time.sleep(0.05)
    return live


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


def _wait_events(rig, event: str, count: int, timeout: float = 30.0) -> list[dict]:
    """轮询假引擎事件账本，直到 ``event`` 事件数 ≥ ``count``（有限超时）。日志里出现 CLIENT_START 只说明席位脚本
    已发起客户端，不保证客户端进程已写下自己的 start 事件；按事件数等才不会在两者之间的窗口里提前动手。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        rows = _events(rig, None, event)
        if len(rows) >= count:
            return rows
        time.sleep(0.05)
    raise AssertionError(f"{timeout}s 内 {event} 事件不足 {count} 条：{_events(rig, None, event)}")


def _mp4_frames(p: Path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return int(out.stdout.strip())


def _tsv_epochs(p: Path) -> list[list[str]]:
    return [line.split("\t") for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------- run_seat.sh


def test_normal_run_and_first_extra_only_on_fresh_server(rig):
    rc, out = _run(_seat_cmd(rig), rig["env"])
    assert rc == 0, out
    assert out.rstrip().splitlines()[-1] == "EXIT_CODE=0"
    assert "STEP_CAP_PAIRING=PASS dataset=test-hard max_steps=1600 strict_cap=1" in out
    assert "SERVER_READY policy=smvla" in out and "SERVER_STOPPED" in out
    assert "SEAT_DONE policy=smvla cond=C seat=T done=2 errors=0 infra=0" in out
    (c,) = _events(rig, "client", "start")
    assert c["first_extra_s"] == "600" and c["wall_s"] == "30"
    assert c["v8"] is False and c["dataset"] == "test-hard" and c["max_steps"] == "1600" and c["strict_cap"] is True
    assert c["ledger"].endswith("/ledger/smvla.ledger.jsonl")
    (s,) = _events(rig, "server", "start")
    assert s["port"] == 18000 + 100 * rig["idx"]
    assert _events(rig, "server", "term")  # 收尾时 server 被 TERM
    pdir = rig["tmp"] / "out" / "smvla"
    rep = json.loads((pdir / "seat-report.json").read_text())
    assert rep["done"] == 2 and rep["success"] == 2 and rep["loop_exit_status"] == 0
    # server_epoch：一次启动、结果行全属 epoch 1
    (ep,) = _tsv_epochs(pdir / "server-epochs.tsv")
    assert ep[:3] == ["1", "0", str(s["port"])]
    rows = F.read_jsonl(pdir / "results.epochs.jsonl")
    assert len(rows) == 2 and {r["server_epoch"] for r in rows} == {1}


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
    assert len(_tsv_epochs(rig["tmp"] / "out" / "smvla" / "server-epochs.tsv")) == 1  # 客户端重起不算新 epoch


def test_client_restart_budget_exhausted(rig):
    rig["env"]["FAKE_CLIENT_CODES"] = "75"
    rc, out = _run(_seat_cmd(rig), rig["env"])
    assert rc == 4
    line = next(x for x in out.splitlines() if x.startswith("INFRA_EXHAUSTED policy=smvla client_restarts="))
    restarts = int(line.split("client_restarts=")[1].split()[0])
    assert len(_events(rig, "client", "start")) == restarts  # 首次 + (restarts-1) 次重启，第 restarts 次超额即停
    assert out.rstrip().splitlines()[-1] == "EXIT_CODE=4"


@pytest.mark.parametrize("code,needle,want_rc", [(5, "RESET_BUDGET_EXHAUSTED policy=smvla", 5),
                                                 (3, "RUN_BLOCKED reason=client policy=smvla", 3),
                                                 (6, "RUN_INCOMPLETE_SEAT policy=smvla", 6)])
def test_budget_blocked_and_incomplete_are_not_restarted(rig, code, needle, want_rc):
    rig["env"]["FAKE_CLIENT_CODES"] = str(code)
    rc, out = _run(_seat_cmd(rig), rig["env"])
    assert rc == want_rc and needle in out
    assert len(_events(rig, "client", "start")) == 1
    assert len(_events(rig, "server", "start")) == 1  # 6 也不重启服务


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
    eps = _tsv_epochs(rig["tmp"] / "out" / "smvla" / "server-epochs.tsv")
    assert [e[0] for e in eps] == [str(i) for i in range(1, n + 1)]  # 每次就绪一个 epoch


@pytest.mark.parametrize("server_mode", ["ok", "ignore_term"])
def test_term_cleans_up_server_and_client(rig, server_mode):
    """TERM：收掉客户端与 server 的进程组；server 忽略 TERM 时等满宽限后 KILL（这一档约 60 s）。"""
    rig["env"].update(FAKE_SERVER_MODE=server_mode, FAKE_CLIENT_CODES="-1")
    log = rig["tmp"] / "out" / "seat-T.log"
    p = _popen(_seat_cmd(rig), rig["env"])
    try:
        _wait_line(log, "CLIENT_START policy=smvla")
        time.sleep(0.5)
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=120)
    finally:
        if p.poll() is None:
            _killpg(p.pid)
            p.wait()
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


@pytest.mark.parametrize("pol", ["mme", "mmesg"])
def test_mme_and_mmesg_require_tokenizer_args(rig, pol):
    extra = ["--mme-variant", "ground-sg-oracle"] if pol == "mmesg" else []
    rc, out = _run(_seat_cmd(rig, *extra, policies=pol), rig["env"])
    assert rc == 3 and "RUN_BLOCKED reason=tokenizer_sha" in out
    assert _events(rig) == []


@pytest.mark.parametrize("dataset,max_steps,strict", [("test-hard0", 1600, False), ("test-hard0", 1300, True),
                                                       ("test-hard", 1300, True), ("test-hard", 1600, False),
                                                       ("bogus", 1600, True)])
def test_step_cap_pairing_blocks_before_any_process(rig, dataset, max_steps, strict):
    rc, out = _run(_seat_cmd(rig, dataset=dataset, max_steps=max_steps, strict=strict), rig["env"])
    assert rc == 3 and "RUN_BLOCKED reason=step_cap_pairing" in out, out
    assert out.rstrip().splitlines()[-1] == "EXIT_CODE=3"
    assert _events(rig) == []


@pytest.mark.parametrize("pol,extra,detail", [
    ("mmesg", [], "mmesg_needs_variant"),
    ("mmesg", ["--mme-variant", "ground-sg-qwenvl"], "qwenvl_needs_adapter"),
    ("smvla", ["--mme-variant", "ground-sg-oracle"], "variant_without_mmesg")])
def test_variant_pairing_blocks(rig, pol, extra, detail):
    rc, out = _run(_seat_cmd(rig, *extra, policies=pol), rig["env"])
    assert rc == 3 and f"RUN_BLOCKED reason=variant_pairing policies={pol}" in out and detail in out, out
    assert _events(rig) == []


@pytest.mark.parametrize("extra", [["--episode-wall-mme", "abc"], ["--bogus"], ["--v8"], ["--max-steps", "x"]])
def test_bad_args_exit_2(rig, extra):
    rc, _ = _run(_seat_cmd(rig) + extra, rig["env"])
    assert rc == 2


def test_missing_ledger_args_exit_2(rig):
    rc, _ = _run(_seat_cmd(rig, ledger=False), rig["env"])
    assert rc == 2


def test_pp_route_health_ready_and_epochs(rig):
    """pp：/health 200 才就绪；服务 argv 带 --args.seed 0 与 checkpoint；客户端走 test-hard0／1300、不带 strict-cap。"""
    cmd = _seat_cmd(rig, "--pp-ckpt", str(rig["pp_ckpt"]), policies="pp", dataset="test-hard0")
    rc, out = _run(cmd, rig["env"])
    assert rc == 0, out
    assert "PP_PREFLIGHT=PASS" in out and "SERVER_CONFIG=INFO policy=pp health=200 seed=0" in out
    (s,) = _events(rig, "server", "start")
    assert s["port"] == 18000 + 100 * rig["idx"] + 30
    argv = s["argv"]
    assert argv[argv.index("--args.seed") + 1] == "0"
    assert argv[argv.index("--args.checkpoint_path") + 1] == str(rig["pp_ckpt"])
    assert argv[argv.index("--args.device") + 1] == "cuda:0"
    (c,) = _events(rig, "client", "start")
    assert (c["policy"], c["dataset"], c["max_steps"], c["strict_cap"]) == ("pp", "test-hard0", "1300", False)
    assert c["first_extra_s"] == "600" and c["wall_s"] == "1800"
    rows = F.read_jsonl(rig["tmp"] / "out" / "pp" / "results.epochs.jsonl")
    assert len(rows) == 2 and {r["server_epoch"] for r in rows} == {1}


# ---------------------------------------------------------------- run_eval_gl.sh／run_official_hard.sh／pair_seat.sh


@pytest.fixture
def gl_repo(rig):
    """执行副本最小形态：四个真实脚本、假解释器、空的 PonderPounce 子模块目录、原侧驱动占位文件。"""
    repo = rig["tmp"] / "repo"
    (repo / "scripts" / "eval-official").mkdir(parents=True)
    for name in SCRIPTS:
        shutil.copy2(EO / name, repo / "scripts" / "eval-official" / name)
    for name in ("pp_official_runner.py", "official_hard_runner.py"):
        (repo / "scripts" / "eval-official" / name).write_text("# 占位：由假解释器分派到假引擎\n", encoding="utf-8")
    (repo / "third_party" / "PonderPounce").mkdir(parents=True)
    for rel in (".venv/bin/python", "artifacts/v8-two/venvs/smvla-env/bin/python"):
        (repo / rel).parent.mkdir(parents=True)
        (repo / rel).symlink_to(rig["fakepy"])
    yield repo
    _reap(rig["tmp"])  # 各脚本的 .v8-pgids 落在运行根里，同样由 _recorded_pids 收集


def _gl_cmd(rig, repo, stage, seat, *extra, dataset="test-hard", max_steps=1600, strict=True):
    cmd = ["bash", str(repo / "scripts" / "eval-official" / "run_eval_gl.sh"), "--run-name", "R", "--seat", seat,
           "--repo", str(repo), "--stage", str(stage), "--shard", str(rig["shard"]), "--policies", "smvla",
           "--smvla-ckpt", str(rig["ckpt"]), "--reset-budget", "10", "--infra-retry-budget", "2",
           "--sync-interval", "1", "--local-root", str(rig["tmp"] / "local"), "--episode-wall-smvla", "30",
           "--dataset", dataset, "--max-steps", str(max_steps)]
    if strict:
        cmd.append("--strict-cap")
    return cmd + list(extra)


def test_gl_transcodes_publishes_by_output_key_and_rerun_does_not_overwrite(rig, gl_repo):
    seat = f"{rig['idx']:02d}"
    stage = rig["tmp"] / "stage"
    rc, out = _run(_gl_cmd(rig, gl_repo, stage, seat), rig["env"])
    assert rc == 0, out
    assert f"V8_SEAT_DONE seat={seat} outcome=pass rc=0" in out
    sync = F.verdict(out.splitlines(), "SEAT_REC_SYNC")
    assert sync[""] == "PASS" and sync["n"] == "2" and sync["left"] == "0"
    assert sync["transcoded"] == "2" and sync["frame_mismatch"] == "0" and sync["transcode_fail"] == "0"
    pub = stage / "media" / "smvla" / "test-hard" / "new"
    for ident in rig["idents"]:
        d = pub / f"{ident['key']}.a1"
        assert sorted(p.name for p in d.glob("*.mp4")) == ["episode.mp4"]
        assert _mp4_frames(d / "episode.mp4") == 4  # 录像器 4 条帧记录（含一帧重复）全部展开
        assert not list(d.glob("*.mkv")) and not (d / ".spool").exists()  # 原始帧已删
        assert (d / "trace.jsonl").is_file() and (d / "summary.json").is_file()  # 轨迹并入、摘要保留
        assert json.loads((d / "transcode.json").read_text())["result"] == "ok"
    assert not (pub / ".incoming").exists() or not any((pub / ".incoming").iterdir())
    assert not any((rig["tmp"] / "local" / "rec" / "smvla").iterdir())  # 节点副本已删
    assert not any((rig["tmp"] / "local" / "trace" / "smvla").iterdir())
    assert F.read_jsonl(stage / f"s{seat}" / "smvla" / "results.epochs.jsonl")[0]["server_epoch"] == 1
    # 同一运行根再跑一遍：同名目录不覆盖，发布成 .dup1
    (rig["tmp"] / "client-count").unlink()
    rc2, out2 = _run(_gl_cmd(rig, gl_repo, stage, seat), rig["env"])
    assert rc2 == 0, out2
    assert out2.count("REC_SYNC_DUP") == 2
    assert all((pub / f"{i['key']}.a1.dup1" / "episode.mp4").is_file() for i in rig["idents"])
    assert (pub / f"{rig['idents'][0]['key']}.a1" / "episode.mp4").is_file()


def test_gl_step_cap_pairing_blocks(rig, gl_repo):
    rc, out = _run(_gl_cmd(rig, gl_repo, rig["tmp"] / "stage", "01", dataset="test-hard0", max_steps=1600, strict=False),
                   rig["env"])
    assert rc == 3 and "RUN_BLOCKED reason=step_cap_pairing dataset=test-hard0 max_steps=1600" in out, out
    assert "V8_SEAT_DONE seat=01 outcome=fail rc=3" in out
    assert _events(rig) == []


def test_gl_term_finalizes_once(rig, gl_repo):
    seat = f"{rig['idx']:02d}"
    stage = rig["tmp"] / "stage"
    rig["env"]["FAKE_CLIENT_CODES"] = "-1"
    p = _popen(_gl_cmd(rig, gl_repo, stage, seat), rig["env"])
    try:
        _wait_line(stage / f"s{seat}" / "smvla" / f"seat-{seat}.log", "CLIENT_START policy=smvla")
        time.sleep(0.5)
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=120)
    finally:
        if p.poll() is None:
            _killpg(p.pid)
            p.wait()
    assert p.returncode == 143
    assert out.count("V8_SEAT_DONE") == 1 and f"V8_SEAT_DONE seat={seat} outcome=aborted rc=143" in out
    assert out.rstrip().splitlines()[-1] == "EXIT_CODE=143"
    for r in _events(rig, None, "start"):
        assert not _alive(r["pid"]), r


def test_gl_rejects_no_record(rig, gl_repo):
    cmd = _gl_cmd(rig, gl_repo, rig["tmp"] / "stage", "01") + ["--no-record"]
    rc, out = _run(cmd, rig["env"])
    assert rc == 2 and "V8_SEAT_DONE seat=01 outcome=fail rc=2 reason=bad_args" in out


def _official_cmd(rig, repo, stage, seat, *extra, budget=1):
    return ["bash", str(repo / "scripts" / "eval-official" / "run_official_hard.sh"), "--run-name", "R", "--seat", seat,
            "--repo", str(repo), "--stage", str(stage), "--shard", str(rig["shard0"]), "--policy", "pp",
            "--pp-ckpt", str(rig["pp_ckpt"]), "--dataset", "test-hard0", "--max-steps", "1300",
            "--infra-retry-budget", str(budget), "--sync-interval", "1", "--local-root", str(rig["tmp"] / "local"),
            *extra]


def test_official_pp_retries_after_server_restart_and_publishes(rig, gl_repo):
    seat = f"{rig['idx']:02d}"
    stage = rig["tmp"] / "stage"
    rig["env"]["FAKE_RUNNER_INFRA_ONCE"] = "1"
    rc, out = _run(_official_cmd(rig, gl_repo, stage, seat), rig["env"])
    assert rc == 0, out
    assert f"OFFICIAL_SEAT_DONE seat={seat} policy=pp outcome=pass rc=0" in out
    assert out.rstrip().splitlines()[-1] == "EXIT_CODE=0"
    k1, k2 = (r["key"] for r in rig["hard0"])
    runs = _events(rig, "runner", "start")
    assert [(r["attempt"], r["only"]) for r in runs] == [(1, [k1, k2]), (2, [k2])]
    assert all(r["max_steps"] == "1300" and r["variant"] is None for r in runs)
    servers = _events(rig, "server", "start")
    assert len(servers) == 2  # 重试前先重启服务
    assert _events(rig, "server", "term")[0]["t"] < runs[1]["t"]  # 旧服务先收掉，再重发同一身份
    rows = F.read_jsonl(stage / f"s{seat}" / "orig" / "pp" / "results.epochs.jsonl")
    assert [(r["key"], r["attempt"], r["infra"], r["server_epoch"]) for r in rows] == \
        [(k1, 1, False, 1), (k2, 1, True, 1), (k2, 2, False, 2)]
    sync = F.verdict(out.splitlines(), "SEAT_REC_SYNC")
    assert sync[""] == "PASS" and sync["transcoded"] == "3" and sync["frame_mismatch"] == "0"
    pub = stage / "media" / "pp" / "test-hard0" / "orig"
    for name in (f"{k1}.a1", f"{k2}.a1", f"{k2}.a2"):
        d = pub / name
        assert _mp4_frames(d / "episode.mp4") == 3
        assert not list((d / "frames").glob("*.rgb24")) and (d / "frames" / "frames.json").is_file()
        assert (d / "trace.jsonl").is_file()


def test_official_retry_budget_zero_leaves_missing(rig, gl_repo):
    seat = f"{rig['idx']:02d}"
    rig["env"]["FAKE_RUNNER_INFRA_ONCE"] = "1"
    rc, out = _run(_official_cmd(rig, gl_repo, rig["tmp"] / "stage", seat, budget=0), rig["env"])
    assert rc == 6, out
    assert "RUN_INCOMPLETE side=orig policy=pp" in out and "missing=1" in out
    assert len(_events(rig, "runner", "start")) == 1


def test_pair_seat_runs_orig_then_new_on_released_gpu(rig, gl_repo):
    seat = f"{rig['idx']:02d}"
    stage = rig["tmp"] / "stage"
    cmd = ["bash", str(gl_repo / "scripts" / "eval-official" / "pair_seat.sh"), "--run-name", "R", "--seat", seat,
           "--repo", str(gl_repo), "--stage", str(stage), "--shard", str(rig["shard0"]), "--policy", "pp",
           "--pp-ckpt", str(rig["pp_ckpt"]), "--reset-budget", "10", "--infra-retry-budget", "2",
           "--orig-infra-retry-budget", "1", "--sync-interval", "1", "--local-root", str(rig["tmp"] / "local")]
    rc, out = _run(cmd, rig["env"], timeout=120)
    assert rc == 0, out
    assert f"PAIR_SEAT_DONE seat={seat} policy=pp orig_rc=0 new_rc=0 rc=0 outcome=pass" in out
    assert out.count("SIDE_RELEASED") == 2
    servers = _events(rig, "server", "start")
    terms = _events(rig, "server", "term")
    runner = _events(rig, "runner", "start")
    client = _events(rig, "client", "start")
    assert len(servers) == 2 and len(runner) == 1 and len(client) == 1
    # 原侧服务收掉之后才起新侧服务；新侧客户端是 test-hard0／1300、不带 strict-cap
    orig_term = next(t for t in terms if t["pid"] == servers[0]["pid"])
    assert orig_term["t"] < servers[1]["t"]
    assert (client[0]["dataset"], client[0]["max_steps"], client[0]["strict_cap"]) == ("test-hard0", "1300", False)
    for side in ("orig", "new"):
        pub = stage / "media" / "pp" / "test-hard0" / side
        assert sorted(p.name for p in pub.iterdir() if not p.name.startswith(".")) == \
            sorted(f"{r['key']}.a1" for r in rig["hard0"])
        assert all((pub / f"{r['key']}.a1" / "episode.mp4").is_file() for r in rig["hard0"])


# ---------------------------------------------------------------- 测试侧兜底本身


def test_teardown_reaps_orphans_when_production_cleanup_is_bypassed(rig):
    """故意让生产清理失效：server 忽略 TERM、客户端常驻，测试侧直接 SIGKILL 掉 run_seat.sh 整个进程组（trap 与
    cleanup 都来不及跑）。setsid 起的 server／客户端成为孤儿仍存活；兜底函数必须把它们收干净。"""
    rig["env"].update(FAKE_SERVER_MODE="ignore_term", FAKE_CLIENT_CODES="-1")
    p = _popen(_seat_cmd(rig), rig["env"])
    try:
        _wait_line(rig["tmp"] / "out" / "seat-T.log", "CLIENT_START policy=smvla")
        _wait_events(rig, "start", 2)  # server 与客户端都已起来、各记一条 start，再杀
        _killpg(p.pid, signal.SIGKILL)
        p.wait(timeout=10)
    finally:
        if p.poll() is None:
            _killpg(p.pid)
            p.wait()
    orphans = [r["pid"] for r in _events(rig, None, "start")]
    assert len(orphans) == 2 and all(_alive(x) for x in orphans)  # 生产收尾确实没生效
    assert set(_recorded_pids(rig["tmp"])) >= set(orphans)
    reaped = _reap(rig["tmp"])
    assert set(reaped) >= set(orphans)
    assert [x for x in orphans if _alive(x)] == []
