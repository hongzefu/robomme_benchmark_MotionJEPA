"""scripts/eval-official/recorder.py 的无仿真夹具：无损往返、反压不丢不乱序、降级档位、线程安全、核对失败路径。"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("v75_recorder_under_test", ROOT / "scripts/eval-official/recorder.py")
R = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = R
_SPEC.loader.exec_module(R)

pytestmark = pytest.mark.skipif(not Path("/usr/bin/ffmpeg").exists() and __import__("shutil").which("ffmpeg") is None,
                                reason="无 ffmpeg")


def _frames(n, seed=0, hw=(32, 48)):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (n, hw[0], hw[1], 3), dtype=np.uint8)


def _recs(d, stream):
    return [json.loads(l) for l in (Path(d) / f"frames-{stream}.jsonl").read_text().splitlines()]


def _big_free(_p):
    return 4000.0


def test_lossless_round_trip(tmp_path):
    fr = _frames(40)
    r = R.EpisodeRecorder(tmp_path / "ep", {"k": 1}, free_gib_fn=_big_free)
    r.set_phase("reset")
    r.add_frames("front", fr[:10], tag="demo")  # reset 期间只入队
    r.set_phase("run")
    for i in range(10, 40):
        r.add_frames("front", fr[i], tag="step")
    r.add_frames("front", fr[5])  # 重复帧：去重，不重新编码
    r.add_array("exec_action", np.arange(8, dtype=np.float64), step=0)
    r.add_event({"kind": "x"})
    res = r.close({"status": "success"})
    assert res["RECORDER_VERIFY"] == "PASS", res
    assert res["frames"] == 41 and res["encoded_frames"] == 40 and res["decode_mismatch"] == 0
    assert not (tmp_path / "ep/.spool").exists()
    recs, imgs = R.load_frames(tmp_path / "ep", "front")
    assert [r_["idx"] for r_ in recs] == list(range(41))
    for rec, im, src in zip(recs, imgs, list(fr) + [fr[5]]):
        assert R.frame_sha256(im) == rec["sha256"] == R.frame_sha256(src)
    assert recs[40]["enc"] == recs[5]["enc"]
    z = np.load(tmp_path / "ep/arrays.npz")
    assert np.array_equal(z["exec_action__00000"], np.arange(8, dtype=np.float64))
    summ = json.loads((tmp_path / "ep/summary.json").read_text())
    assert summ["summary"] == {"status": "success"}


def test_backpressure_no_drop_no_reorder(tmp_path):
    fr = _frames(60, seed=1)
    r = R.EpisodeRecorder(tmp_path / "ep", {}, queue_frames=2, encode_delay_s=0.01, free_gib_fn=_big_free)
    r.set_phase("run")
    for i in range(60):
        r.add_frames("wrist", fr[i])
    res = r.close({})
    assert res["RECORDER_VERIFY"] == "PASS"
    assert res["dropped"] == 0 and res["reordered"] == 0 and res["frames"] == 60
    assert res["queue_wait_s"] > 0.1  # 队列只有 2 格、编码慢：调用方确实被反压
    recs, imgs = R.load_frames(tmp_path / "ep", "wrist")
    assert [R.frame_sha256(im) for im in imgs] == [R.frame_sha256(f) for f in fr]


def test_reset_phase_does_not_feed_encoder(tmp_path):
    fr = _frames(20, seed=2)
    r = R.EpisodeRecorder(tmp_path / "ep", {}, free_gib_fn=_big_free)
    r.set_phase("reset")
    r.add_frames("front", fr)
    import time

    time.sleep(0.5)
    st = r._streams["front"]
    assert st.n_fed == 0 and st.proc is None  # reset 期间 ffmpeg 未启动
    r.set_phase("run")
    res = r.close({})
    assert res["RECORDER_VERIFY"] == "PASS" and res["frames"] == 20


def test_degrade_levels(tmp_path, capsys):
    R._LAST_LEVEL = 0
    fr = _frames(120, seed=3)
    r1 = R.EpisodeRecorder(tmp_path / "l1", {}, free_gib_fn=lambda p: 400.0)
    assert r1.level == 1
    r1.set_phase("run")
    r1.add_frames("front", fr[:10])
    res1 = r1.close({})
    assert res1["RECORDER_VERIFY"] == "PASS" and res1["lossless"] is False
    assert "STORAGE_DEGRADE level=1 free_gib=400.0" in capsys.readouterr().out
    # 2 档：只留首尾各 50 帧，sha 清单仍完整
    r2 = R.EpisodeRecorder(tmp_path / "l2", {}, free_gib_fn=lambda p: 100.0)
    assert r2.level == 2
    r2.set_phase("run")
    r2.add_frames("front", fr)
    res2 = r2.close({})
    assert res2["RECORDER_VERIFY"] == "PASS" and res2["frames"] == 120 and res2["encoded_frames"] == 100
    recs = _recs(tmp_path / "l2", "front")
    assert len(recs) == 120 and all(r_["sha256"] for r_ in recs)
    assert [r_["enc"] is None for r_ in recs] == [False] * 50 + [True] * 20 + [False] * 50
    assert "STORAGE_DEGRADE level=2" in capsys.readouterr().out
    # 基准条件：空间再紧也无损
    r3 = R.EpisodeRecorder(tmp_path / "l3", {"baseline": True}, free_gib_fn=lambda p: 100.0)
    assert r3.level == 0
    r3.close({})
    r4 = R.EpisodeRecorder(tmp_path / "l4", {"never_degrade": True}, free_gib_fn=lambda p: 10.0)
    assert r4.level == 0
    r4.close({})
    R._LAST_LEVEL = 0


def test_thread_safety(tmp_path):
    r = R.EpisodeRecorder(tmp_path / "ep", {}, queue_frames=4, free_gib_fn=_big_free)
    r.set_phase("run")
    per = {s: _frames(30, seed=10 + k) for k, s in enumerate(["front", "wrist"])}
    got: dict[str, list[int]] = {"front": [], "wrist": []}

    def work(stream):
        for i in range(30):
            got[stream] += r.add_frames(stream, per[stream][i])
            r.add_array(f"a_{stream}", np.full(3, i), step=i)
            r.add_event({"kind": "step", "stream": stream, "i": i})

    ts = [threading.Thread(target=work, args=(s,)) for s in per]
    [t.start() for t in ts]
    [t.join() for t in ts]
    res = r.close({})
    assert res["RECORDER_VERIFY"] == "PASS" and res["frames"] == 60
    for s in per:
        assert got[s] == list(range(30))
        recs, imgs = R.load_frames(tmp_path / "ep", s)
        assert [R.frame_sha256(im) for im in imgs] == [R.frame_sha256(f) for f in per[s]]
    seqs = [json.loads(l)["seq"] for l in (tmp_path / "ep/events.jsonl").read_text().splitlines()]
    assert seqs == list(range(len(seqs)))


def test_verify_fail_path_keeps_spool(tmp_path, monkeypatch):
    fr = _frames(10, seed=4)
    r = R.EpisodeRecorder(tmp_path / "ep", {}, free_gib_fn=_big_free)
    r.set_phase("run")
    r.add_frames("front", fr)
    # 模拟解码结果被破坏：核对必须 FAIL，且原始块保留（可重编码，不重跑环境）
    real = R.decode_raw_frames

    def broken(ffmpeg, path, shape):
        out = real(ffmpeg, path, shape)
        out[3] = bytes(len(out[3]))
        return out

    monkeypatch.setattr(R, "decode_raw_frames", broken)
    res = r.close({})
    assert res["RECORDER_VERIFY"] == "FAIL" and res["decode_mismatch"] >= 1 and res["reencoded_streams"] == 1
    assert (tmp_path / "ep/.spool/front.raw").stat().st_size == 10 * fr[0].nbytes
    assert "RECORDER_VERIFY=FAIL" in R.verdict_line(res)


def test_reencode_recovers_from_encoder_failure(tmp_path):
    fr = _frames(10, seed=5)
    r = R.EpisodeRecorder(tmp_path / "ep", {}, free_gib_fn=_big_free)
    r.set_phase("reset")  # reset 期间不喂 ffmpeg，保证下一行注入的失败必然生效
    r.add_frames("front", fr)
    r._streams["front"].encode_error = "模拟编码失败"  # 写线程停喂；收尾从原始块重编码
    res = r.close({})
    assert res["RECORDER_VERIFY"] == "PASS" and res["reencoded_streams"] == 1


def test_refuses_existing_summary(tmp_path):
    r = R.EpisodeRecorder(tmp_path / "ep", {}, free_gib_fn=_big_free)
    r.close({})
    with pytest.raises(FileExistsError):
        R.EpisodeRecorder(tmp_path / "ep", {}, free_gib_fn=_big_free)


def test_sync_mode(tmp_path):
    fr = _frames(12, seed=6)
    r = R.EpisodeRecorder(tmp_path / "ep", {}, encode_async=False, free_gib_fn=_big_free)
    r.add_frames("front", fr)
    res = r.close({})
    assert res["RECORDER_VERIFY"] == "PASS" and res["frames"] == 12


def test_writer_death_raises_and_close_does_not_hang(tmp_path, monkeypatch):
    """写线程失败（模拟 ENOSPC）：add_frames 抛 RecorderError 而非永久阻塞；close 返回 FAIL。"""
    fr = _frames(30, seed=7)
    r = R.EpisodeRecorder(tmp_path / "ep", {}, queue_frames=2, free_gib_fn=_big_free)
    r.set_phase("run")

    def enospc(st, enc, b):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(r, "_spool_write", enospc)
    import time

    t = time.time()
    with pytest.raises(R.RecorderError):
        for i in range(30):
            r.add_frames("front", fr[i])
            time.sleep(0.01)
    with pytest.raises(R.RecorderError):
        r.add_array("x", np.zeros(3))
    res = r.close({})
    assert time.time() - t < 30
    assert res["RECORDER_VERIFY"] == "FAIL" and any("No space" in e for e in res["errors"])


def test_writer_thread_dead_detected(tmp_path):
    r = R.EpisodeRecorder(tmp_path / "ep", {}, queue_frames=1, free_gib_fn=_big_free)
    r._q.put(R._SENTINEL)  # 让写线程提前退出（模拟线程意外死亡）
    r._writer.join(5)
    fr = _frames(5, seed=8)
    with pytest.raises(R.RecorderError):
        for i in range(5):
            r.add_frames("front", fr[i])
    res = r.close({})
    assert res["RECORDER_VERIFY"] == "FAIL"


def test_encode_cpus_validation(tmp_path, monkeypatch):
    import os

    allowed = sorted(os.sched_getaffinity(0))
    monkeypatch.setenv("V75_ENCODE_CPUS", str(max(allowed) + 1000))
    with pytest.raises(R.RecorderError):
        R.EpisodeRecorder(tmp_path / "bad", {}, free_gib_fn=_big_free)
    monkeypatch.setenv("V75_ENCODE_CPUS", str(allowed[-1]))
    r = R.EpisodeRecorder(tmp_path / "ok", {}, free_gib_fn=_big_free)
    r.set_phase("run")
    r.add_frames("front", _frames(3, seed=9))
    res = r.close({})
    assert res["RECORDER_VERIFY"] == "PASS"
    assert R.parse_cpu_list("1,3-4") == {1, 3, 4}


def test_refuses_non_empty_dir_unless_overwrite(tmp_path):
    d = tmp_path / "ep"
    d.mkdir()
    (d / "junk").write_text("x")
    with pytest.raises(FileExistsError):
        R.EpisodeRecorder(d, {}, free_gib_fn=_big_free)
    r = R.EpisodeRecorder(d, {}, free_gib_fn=_big_free, overwrite=True)
    assert not (d / "junk").exists()
    r.close({})
