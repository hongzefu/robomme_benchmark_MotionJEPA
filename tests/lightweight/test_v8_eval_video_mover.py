#!/usr/bin/env python3
"""轻量测试：eval_video_mover.py ``--mode v8``（契约 C4 第二段）与旧 v7 模式回归（纯 CPU、临时目录，不碰真实 NFS）。

覆盖：完成目录整目录搬走且删源、进行中目录（结果行未写出）不搬、error 尝试目录也搬、sha 不符不删源、
moved.jsonl 续跑幂等、解码失败判 FAIL、常驻模式 --stop-file 退出、旧 v7 默认模式回归、--once 判定行。
录像夹具用 ffmpeg 生成两帧 FFV1 小 mkv（找不到 ffmpeg 时用 imageio-ffmpeg 自带二进制；都没有则跳过解码相关用例）。

    uv run --no-sync python -m pytest tests/lightweight/test_v8_eval_video_mover.py -q -s
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
MOVER = REPO_ROOT / "scripts" / "injection-dev" / "eval_video_mover.py"
_spec = importlib.util.spec_from_file_location("eval_video_mover_under_test", MOVER)
mover = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mover)


def _ffmpeg() -> str | None:
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


@pytest.fixture(scope="module")
def mkv(tmp_path_factory) -> Path:
    ff = _ffmpeg()
    if ff is None:
        pytest.skip("没有 ffmpeg 也没有 imageio-ffmpeg，跳过需要真实 mkv 的用例")
    out = tmp_path_factory.mktemp("mkv") / "two.mkv"
    subprocess.run([ff, "-v", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc=size=32x32:rate=10",
                    "-frames:v", "2", "-c:v", "ffv1", str(out)], check=True, timeout=60)
    return out


class Stage:
    def __init__(self, root: Path, mkv: Path | None):
        self.root = root / "stage"
        self.mkv = mkv

    def rec(self, seat: str, policy: str, name: str, *, broken: bool = False) -> Path:
        d = self.root / f"s{seat}" / policy / "rec" / name
        d.mkdir(parents=True, exist_ok=True)
        for m in ("front.mkv", "wrist.mkv"):
            if broken or self.mkv is None:
                (d / m).write_bytes(b"not-a-video")
            else:
                shutil.copy(self.mkv, d / m)
        (d / "summary.json").write_text('{"RECORDER_VERIFY": "PASS"}\n')
        (d / "events.jsonl").write_text('{"seq": 0}\n')
        (d / "spool").mkdir(exist_ok=True)
        (d / "spool" / "chunk-0.bin").write_bytes(b"\x00\x01")  # 子目录也整目录搬
        return d

    def result(self, seat, policy, task, tier, seed, status, *, attempt_no=1, accept=True, media=True,
               broken=False, **extra) -> tuple[str, Path]:
        key = f"{task}_{tier}_{seed}"
        name = f"{key}.a{attempt_no}"
        aid = uuid.uuid4().hex
        d = self.root / f"s{seat}" / policy
        d.mkdir(parents=True, exist_ok=True)
        rd = self.rec(seat, policy, name, broken=broken) if media else d / "rec" / name
        row = {"v8": True, "key": key, "task": task, "tier": tier, "seed": seed, "policy": policy,
               "attempt_id": aid, "attempt_no": attempt_no, "status": status, "task_success": status == "success",
               "exec_steps": 10, "infra": status == "error", "rec_dir": f"/tmp/R-s{seat}/rec/{policy}/{name}", **extra}
        with (d / "results.jsonl").open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        with (d / f"{policy}.ledger.jsonl").open("a") as fh:
            fh.write(json.dumps({"kind": "attempt_start", "key": key, "attempt_id": aid, "attempt_no": attempt_no,
                                 "policy": policy}) + "\n")
            if accept and status in ("success", "fail", "timeout"):
                fh.write(json.dumps({"kind": "accept", "key": key, "attempt_id": aid, "accepted_attempt_id": aid,
                                     "policy": policy}) + "\n")
        return aid, rd


def run_v8(stage: Stage, dest: Path, *extra: str, policies="smvla,mme") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(MOVER), "--mode", "v8", "--stage", str(stage.root), "--dest", str(dest),
                           "--policies", policies, "--stable-sec", "0", "--interval", "0.05", *extra],
                          capture_output=True, text=True, timeout=120)


def verdict(proc) -> dict:
    line = [l for l in proc.stdout.splitlines() if l.startswith("V8_EVAL_VIDEOS=")][-1]
    head, *rest = line.split()
    out = dict(x.split("=", 1) for x in rest)
    out["_verdict"] = head.split("=", 1)[1]
    return out


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_v8_once_moves_completed_and_error_dirs(tmp_path, mkv):
    st = Stage(tmp_path, mkv)
    _, d_ok = st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    _, d_err = st.result("00", "smvla", "SwingXtimes", "xhard5", 22, "error", accept=False, infra_reason="env_build")
    _, d_retry = st.result("00", "smvla", "SwingXtimes", "xhard5", 22, "timeout", attempt_no=2)
    _, d_mme = st.result("01", "mme", "VideoUnmask", "xhard1", 11, "fail")
    inflight = st.rec("01", "mme", "BinFill_xhard3_33.a1")  # 结果行尚未写出 → 不碰
    shas = {p.name: sha(p / "front.mkv") for p in (d_ok, d_err, d_retry, d_mme)}
    dest = tmp_path / "videos"
    proc = run_v8(st, dest, "--once")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    v = verdict(proc)
    assert v == {"_verdict": "PASS", "policies": "2", "expected": "3", "videos": "3", "missing": "0",
                 "decode_fail": "0", "sha_mismatch": "0", "error_attempt_videos": "1"}, proc.stdout
    assert proc.stdout.strip().splitlines()[-1] == "EXIT_CODE=0"
    for d in (d_ok, d_err, d_retry, d_mme):
        assert not d.exists()
    assert inflight.exists() and (inflight / "front.mkv").exists()
    out_ok = dest / "smvla" / "xhard1" / "VideoUnmask" / "VideoUnmask_xhard1_11.a1"
    out_err = dest / "smvla" / "xhard5" / "SwingXtimes" / "SwingXtimes_xhard5_22.a1"
    assert sha(out_ok / "front.mkv") == shas[out_ok.name]
    assert (out_ok / "spool" / "chunk-0.bin").read_bytes() == b"\x00\x01"
    assert (out_err / "wrist.mkv").exists()
    rows = [json.loads(l) for l in (dest / "moved.jsonl").read_text().splitlines()]
    assert len(rows) == 4 and all(r["mode"] == "v8" for r in rows)
    err_row = next(r for r in rows if r["status"] == "error")
    assert err_row["files"]["front.mkv"] == shas[out_err.name] and "spool/chunk-0.bin" in err_row["files"]


def test_v8_moved_jsonl_resume_idempotent(tmp_path, mkv):
    st = Stage(tmp_path, mkv)
    st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    st.result("00", "mme", "VideoUnmask", "xhard1", 11, "success")
    dest = tmp_path / "videos"
    assert run_v8(st, dest, "--once").returncode == 0
    before = (dest / "moved.jsonl").read_text()
    proc = run_v8(st, dest, "--once")  # 第二轮：源已搬走，什么也不做，对账照样 PASS
    assert proc.returncode == 0 and "VMOVE mode=v8 moved=0" in proc.stdout
    assert (dest / "moved.jsonl").read_text() == before
    assert verdict(proc)["videos"] == "2"
    # 新增一局后续跑只搬新增的
    st.result("01", "mme", "SwingXtimes", "xhard5", 22, "fail")
    proc = run_v8(st, dest, "--once")
    assert "VMOVE mode=v8 moved=1" in proc.stdout and verdict(proc)["expected"] == "3"
    assert len((dest / "moved.jsonl").read_text().splitlines()) == 3


def test_v8_sha_mismatch_keeps_source(tmp_path, mkv, monkeypatch):
    st = Stage(tmp_path, mkv)
    st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    dest = tmp_path / "videos"
    real = mover.sha256

    def fake(path: Path) -> str:  # 本机一侧的文件 sha 总是对不上
        return "0" * 64 if str(dest) in str(path) else real(path)

    monkeypatch.setattr(mover, "sha256", fake)
    args = argparse.Namespace(stage=str(st.root), dest=str(dest), policies="smvla", once=True, stop_file=None,
                              interval=0.05, stable_sec=0.0, decode_workers=1)
    rc = mover.v8_main(args)
    assert rc == 1
    src = st.root / "s00" / "smvla" / "rec" / "VideoUnmask_xhard1_11.a1"
    assert (src / "front.mkv").exists() and (src / "summary.json").exists()  # 源一个文件都没删
    assert not (dest / "smvla" / "xhard1" / "VideoUnmask" / "VideoUnmask_xhard1_11.a1").exists()  # 不完整副本已删
    assert not (dest / "moved.jsonl").exists() or not (dest / "moved.jsonl").read_text().strip()


def test_v8_sha_mismatch_verdict_line(tmp_path, mkv, monkeypatch, capsys):
    st = Stage(tmp_path, mkv)
    st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    dest = tmp_path / "videos"
    real = mover.sha256
    monkeypatch.setattr(mover, "sha256", lambda p: "f" * 64 if str(dest) in str(p) else real(p))
    args = argparse.Namespace(stage=str(st.root), dest=str(dest), policies="smvla", once=True, stop_file=None,
                              interval=0.05, stable_sec=0.0, decode_workers=1)
    assert mover.v8_main(args) == 1
    out = capsys.readouterr().out
    line = [l for l in out.splitlines() if l.startswith("V8_EVAL_VIDEOS=")][0]
    assert line == ("V8_EVAL_VIDEOS=FAIL policies=1 expected=1 videos=0 missing=1 decode_fail=0 sha_mismatch=1 "
                    "error_attempt_videos=0")
    assert out.strip().splitlines()[-1] == "EXIT_CODE=1"


def test_v8_decode_fail_and_missing(tmp_path, mkv):
    st = Stage(tmp_path, mkv)
    st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success", broken=True)  # 不是视频 → decode_fail
    st.result("00", "smvla", "VideoUnmask", "xhard1", 12, "fail", media=False)  # 录像还没同步到运行根 → missing
    proc = run_v8(st, tmp_path / "videos", "--once", policies="smvla")
    assert proc.returncode == 1
    v = verdict(proc)
    assert (v["_verdict"], v["expected"], v["videos"], v["missing"], v["decode_fail"]) == ("FAIL", "2", "0", "1", "1")


def test_v8_resident_stop_file(tmp_path, mkv):
    st = Stage(tmp_path, mkv)
    _, d = st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    stop = tmp_path / "STOP"
    stop.write_text("")
    proc = run_v8(st, tmp_path / "videos", "--stop-file", str(stop))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not d.exists() and "V8_EVAL_VIDEOS=" not in proc.stdout
    assert proc.stdout.strip().splitlines()[-1] == "EXIT_CODE=0"


def test_v7_default_mode_regression(tmp_path):
    """旧 v7 形状（results-r*-shard*.jsonl、video 绝对路径、episode／tier 字段），不带 --mode 时行为不变。"""
    stage = tmp_path / "stage" / "r1"
    stage.mkdir(parents=True)
    video = stage / "PickXtimes_xhard2_5.mp4"
    video.write_bytes(b"fake-mp4")
    digest = hashlib.sha256(b"fake-mp4").hexdigest()
    rec = {"task": "PickXtimes", "episode": 5, "tier": "xhard2", "seed": 777, "status": "timeout",
           "video": str(video)}
    log = tmp_path / "results-r1-shard0.jsonl"
    log.write_text(json.dumps({**rec, "status": "error"}) + "\n" + json.dumps(rec) + "\n")
    proc = subprocess.run([sys.executable, str(MOVER), "--policy", "simplememvla", "--records-glob", str(log),
                           "--stage", str(tmp_path / "stage"), "--dest", str(tmp_path / "dest"), "--stable-sec", "0",
                           "--interval", "0.1", "--once"], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = tmp_path / "dest" / "xhard2" / "PickXtimes" / "PickXtimes_xhard2_5_777.mp4"
    assert out.exists() and not video.exists()
    row = json.loads((tmp_path / "dest" / "moved.jsonl").read_text().splitlines()[0])
    assert (row["policy"], row["episode"], row["tier"], row["seed"], row["status"], row["sha256"]) == \
        ("simplememvla", 5, "xhard2", 777, "timeout", digest)
    assert "VMOVE moved=1 pending=0" in proc.stdout and "V8_EVAL_VIDEOS" not in proc.stdout
    assert proc.stdout.strip().splitlines()[-1] == "EXIT_CODE=0"
    # v7 模式缺必填参数仍报错退出
    bad = subprocess.run([sys.executable, str(MOVER), "--stage", str(tmp_path), "--dest", str(tmp_path / "d2")],
                         capture_output=True, text=True, timeout=60)
    assert bad.returncode == 2 and "--policy" in bad.stderr


def test_zz_summary_line(request):
    """放在最后：本次会话（与 test_v8_eval_report.py 同跑时含其全部用例）没有任何失败才打印判定行。"""
    assert request.session.testsfailed == 0, "前面有用例失败"
    print("V8_EVAL_VIDEO_MOVER_TESTS=PASS")
    print("V8_EVAL_REPORT_TESTS=PASS")
