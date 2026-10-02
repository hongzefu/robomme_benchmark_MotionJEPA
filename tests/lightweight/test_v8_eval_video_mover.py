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
        # 录像器残留：非空 ffmpeg stderr 日志（recorder 不删）与 close 失败时保留的 .spool/
        (d / ".ffmpeg-front.log").write_text("[ffv1 @ 0x0] warning\n")
        (d / ".spool").mkdir(exist_ok=True)
        (d / ".spool" / "front.raw").write_bytes(b"\x00\x01")
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
    _, d_can = st.result("00", "mme", "SwingXtimes", "xhard5", 22, "success", accept=False, canary=True, media=False,
                         rec_dir="/tmp/R-s00/rec/mme/SwingXtimes_xhard5_22.canary.a1")
    d_can = st.rec("00", "mme", "SwingXtimes_xhard5_22.canary.a1")
    orphan = st.rec("01", "mme", "BinFill_xhard3_33.a1")  # 没有结果行：常驻模式不碰，--once 对账轮搬进 _orphan
    shas = {p.name: sha(p / "front.mkv") for p in (d_ok, d_err, d_retry, d_mme)}
    dest = tmp_path / "videos"
    proc = run_v8(st, dest, "--once")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    v = verdict(proc)
    assert v == {"_verdict": "PASS", "policies": "2", "expected": "3", "videos": "3", "missing": "0",
                 "decode_fail": "0", "sha_mismatch": "0", "error_attempt_videos": "1", "stage_left": "0",
                 "orphan_videos": "1"}, proc.stdout
    assert proc.stdout.strip().splitlines()[-1] == "EXIT_CODE=0"
    for d in (d_ok, d_err, d_retry, d_mme, d_can, orphan):
        assert not d.exists()
    assert (dest / "mme" / "_orphan" / "s01" / "BinFill_xhard3_33.a1" / "front.mkv").exists()
    assert (dest / "mme" / "xhard5" / "SwingXtimes" / "SwingXtimes_xhard5_22.canary.a1" / "wrist.mkv").exists()
    out_ok = dest / "smvla" / "xhard1" / "VideoUnmask" / "VideoUnmask_xhard1_11.a1"
    out_err = dest / "smvla" / "xhard5" / "SwingXtimes" / "SwingXtimes_xhard5_22.a1"
    assert sha(out_ok / "front.mkv") == shas[out_ok.name]
    # 录像器残留的点开头文件（非空 .ffmpeg-<stream>.log、.spool/）照常整目录搬走
    assert (out_ok / ".spool" / "front.raw").read_bytes() == b"\x00\x01"
    assert (out_ok / ".ffmpeg-front.log").read_text().startswith("[ffv1")
    assert (out_err / "wrist.mkv").exists() and (out_err / ".ffmpeg-front.log").exists()
    assert not (dest / ".incoming").exists() or not any((dest / ".incoming").iterdir())
    rows = [json.loads(l) for l in (dest / "moved.jsonl").read_text().splitlines()]
    assert len(rows) == 6 and all(r["mode"] == "v8" and r["src_left"] is False for r in rows)
    assert sum(r["orphan"] for r in rows) == 1 and sum(r["canary"] for r in rows) == 1
    err_row = next(r for r in rows if r["status"] == "error")
    assert err_row["files"]["front.mkv"] == shas[out_err.name]
    assert ".spool/front.raw" in err_row["files"] and ".ffmpeg-front.log" in err_row["files"]


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


def ns(st: Stage, dest: Path, **kw) -> argparse.Namespace:
    base = dict(stage=str(st.root), dest=str(dest), policies="smvla", once=True, stop_file=None, interval=0.05,
                stable_sec=0.0, decode_workers=1, once_max_wait=300.0)
    base.update(kw)
    return argparse.Namespace(**base)


def test_v8_sha_mismatch_keeps_source_and_existing_copy(tmp_path, mkv, monkeypatch):
    st = Stage(tmp_path, mkv)
    st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    dest = tmp_path / "videos"
    # 本机早已有一份（此前核对过的）副本：sha 不符时也不能删它
    prior = dest / "smvla" / "xhard1" / "VideoUnmask" / "VideoUnmask_xhard1_11.a1"
    prior.mkdir(parents=True)
    (prior / "front.mkv").write_bytes(b"older-verified-copy")
    real = mover.sha256

    def fake(path: Path) -> str:  # 临时目录一侧的文件 sha 总是对不上
        return "0" * 64 if ".incoming" in str(path) else real(path)

    monkeypatch.setattr(mover, "sha256", fake)
    assert mover.v8_main(ns(st, dest)) == 1
    src = st.root / "s00" / "smvla" / "rec" / "VideoUnmask_xhard1_11.a1"
    assert (src / "front.mkv").exists() and (src / "summary.json").exists()  # 源一个文件都没删
    assert (prior / "front.mkv").read_bytes() == b"older-verified-copy"  # 本机已有副本未动
    assert not any((dest / ".incoming").iterdir())  # 只删了临时目录
    assert not (dest / "moved.jsonl").exists() or not (dest / "moved.jsonl").read_text().strip()


def test_v8_sha_mismatch_verdict_line(tmp_path, mkv, monkeypatch, capsys):
    st = Stage(tmp_path, mkv)
    st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    dest = tmp_path / "videos"
    real = mover.sha256
    monkeypatch.setattr(mover, "sha256", lambda p: "f" * 64 if ".incoming" in str(p) else real(p))
    assert mover.v8_main(ns(st, dest)) == 1
    out = capsys.readouterr().out
    line = [l for l in out.splitlines() if l.startswith("V8_EVAL_VIDEOS=")][0]
    assert line == ("V8_EVAL_VIDEOS=FAIL policies=1 expected=1 videos=0 missing=1 decode_fail=0 sha_mismatch=1 "
                    "error_attempt_videos=0 stage_left=1 orphan_videos=0")
    assert out.strip().splitlines()[-1] == "EXIT_CODE=1"


def test_v8_existing_different_target_goes_to_dup(tmp_path, mkv):
    st = Stage(tmp_path, mkv)
    st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    dest = tmp_path / "videos"
    prior = dest / "smvla" / "xhard1" / "VideoUnmask" / "VideoUnmask_xhard1_11.a1"
    prior.mkdir(parents=True)
    (prior / "front.mkv").write_bytes(b"different")
    mover.v8_main(ns(st, dest))
    assert (prior / "front.mkv").read_bytes() == b"different"
    dup = prior.parent / "VideoUnmask_xhard1_11.a1.dup1"
    assert (dup / "wrist.mkv").exists()
    row = json.loads((dest / "moved.jsonl").read_text().splitlines()[0])
    assert row["dest"] == str(dup)


def test_v8_nfs_placeholder_src_left(tmp_path, mkv):
    st = Stage(tmp_path, mkv)
    _, d = st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    (d / ".nfs000000001234abcd00000001").write_bytes(b"busy")  # NFS 删除占位：不搬不删、目录删不掉
    dest = tmp_path / "videos"
    assert mover.v8_main(ns(st, dest)) == 0
    row = json.loads((dest / "moved.jsonl").read_text().splitlines()[0])
    assert row["src_left"] is True and not any(".nfs" in k for k in row["files"])
    assert (d / ".nfs000000001234abcd00000001").exists() and not (d / "front.mkv").exists()


def test_v8_rsync_tmp_pending_then_give_up(tmp_path, mkv, capsys):
    """有 rsync 临时文件（.<name>.<6 位随机>）的目录判正在写；--once 超过 --once-max-wait 即放弃、FAIL、不死循环。"""
    st = Stage(tmp_path, mkv)
    _, d = st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    (d / ".wrist.mkv.Ab3dE9").write_bytes(b"partial")
    assert mover.v8_main(ns(st, tmp_path / "videos", once_max_wait=0.3)) == 1
    out = capsys.readouterr().out
    line = [l for l in out.splitlines() if l.startswith("V8_EVAL_VIDEOS=")][0]
    assert "stage_left=1" in line and line.startswith("V8_EVAL_VIDEOS=FAIL") and "unstable" in out
    assert (d / "front.mkv").exists()


def test_v8_non_authoritative_rsync_fail_is_fail(tmp_path, mkv, monkeypatch, capsys):
    st = Stage(tmp_path, mkv)
    st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    _, d_err = st.result("00", "smvla", "VideoUnmask", "xhard1", 12, "error", accept=False, error="boom")
    real = mover.v8_move_dir
    monkeypatch.setattr(mover, "v8_move_dir",
                        lambda item, dest, log: ("rsync_fail", 0) if item["src"] == d_err else real(item, dest, log))
    assert mover.v8_main(ns(st, tmp_path / "videos")) == 1
    line = [l for l in capsys.readouterr().out.splitlines() if l.startswith("V8_EVAL_VIDEOS=")][0]
    assert line.startswith("V8_EVAL_VIDEOS=FAIL") and "videos=1 missing=0" in line and "stage_left=1" in line


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
    _, d_err = st.result("00", "smvla", "VideoUnmask", "xhard1", 12, "error", accept=False, error="boom")
    inflight = st.rec("00", "smvla", "BinFill_xhard3_33.a1")  # 结果行尚未写出 → 常驻模式不碰
    stop = tmp_path / "STOP"
    stop.write_text("")
    proc = run_v8(st, tmp_path / "videos", "--stop-file", str(stop))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not d.exists() and not d_err.exists() and "V8_EVAL_VIDEOS=" not in proc.stdout
    assert inflight.exists() and (inflight / "front.mkv").exists()
    assert proc.stdout.strip().splitlines()[-1] == "EXIT_CODE=0"


def test_v8_node_incoming_skipped_and_dup_moved(tmp_path, mkv):
    """节点同步的 rec/.incoming/ 不碰、不算孤儿；rec/<名>.dupN/ 随同一结果行照常搬，目的地沿用 .dupN 名。"""
    st = Stage(tmp_path, mkv)
    _, d = st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    dup = st.rec("00", "smvla", "VideoUnmask_xhard1_11.a1.dup1")
    (dup / "front.mkv").write_bytes((dup / "front.mkv").read_bytes())
    incoming = st.rec("00", "smvla", ".incoming")
    dest = tmp_path / "videos"
    proc = run_v8(st, dest, "--once", policies="smvla")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    v = verdict(proc)
    assert (v["stage_left"], v["orphan_videos"], v["videos"]) == ("0", "0", "1"), proc.stdout
    assert not d.exists() and not dup.exists() and incoming.exists()
    base = dest / "smvla" / "xhard1" / "VideoUnmask"
    assert (base / "VideoUnmask_xhard1_11.a1" / "front.mkv").exists()
    assert (base / "VideoUnmask_xhard1_11.a1.dup1" / "front.mkv").exists()
    assert not (dest / "smvla" / "_orphan").exists()


def test_v8_resident_stop_file_does_not_hang_on_unstable(tmp_path, mkv):
    st = Stage(tmp_path, mkv)
    _, d = st.result("00", "smvla", "VideoUnmask", "xhard1", 11, "success")
    (d / ".front.mkv.Qw12Er").write_bytes(b"partial")  # 残留 rsync 临时文件
    stop = tmp_path / "STOP"
    stop.write_text("")
    proc = run_v8(st, tmp_path / "videos", "--stop-file", str(stop), "--once-max-wait", "0.3")
    assert proc.returncode == 0 and "持续不稳" in proc.stdout, proc.stdout + proc.stderr
    assert (d / "front.mkv").exists()


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
    """放在最后：本次会话（与 test_v8_eval_report.py 同跑时含其全部用例）没有失败才打印判定行；有跳过则打印 SKIPPED。"""
    assert request.session.testsfailed == 0, "前面有用例失败"
    tr = request.config.pluginmanager.get_plugin("terminalreporter")
    skipped = len(tr.stats.get("skipped", [])) if tr is not None else 0
    verdict_word = "SKIPPED" if skipped else "PASS"
    print(f"V8_EVAL_VIDEO_MOVER_TESTS={verdict_word}")
    print(f"V8_EVAL_REPORT_TESTS={verdict_word}")
