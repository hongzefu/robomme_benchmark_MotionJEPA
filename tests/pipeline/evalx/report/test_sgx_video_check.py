"""C13-SG-VIDEO-CHECK：逐局压缩视频核对。非 slow 用例用 ffprobe／ffmpeg 替身；slow 用例真起 ffmpeg 编出 h264。期望值手写。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests._support.loaders import load_script

import sgx_report_fixtures as F


def V():
    return load_script("eval-official/video_check.py")


class FakeTools:
    """按文件内容决定替身结果：内容形如 ``codec=h264 ok=1 frames=10``。"""

    def _meta(self, p: Path) -> dict:
        return dict(kv.split("=") for kv in p.read_text().split())

    def codec(self, p):
        return self._meta(p)["codec"]

    def decode(self, p):
        m = self._meta(p)
        return m["ok"] == "1", int(m["frames"]), "" if m["ok"] == "1" else "corrupt"


def _row(seed, *, demo=2, exec_steps=5, attempt=1, **kw):
    return {**F.result_row(task="VideoUnmask", source_episode=3, seed=seed, exec_steps=exec_steps, attempt=attempt),
            "key": f"VideoUnmask_xhard0_{seed}", "policy": "mmesg", "policy_variant": "ground-sg-oracle",
            "demo_frames": demo, **kw}


def _ep(root: Path, seed: int, content: str = "codec=h264 ok=1 frames=8", attempt: int = 1, side: str = "new") -> Path:
    d = root / "mmesg-ground-sg-oracle" / "test-hard0" / side / f"VideoUnmask_xhard0_{seed}.a{attempt}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "episode.mp4").write_text(content)
    (d / "summary.json").write_text("{}")
    (d / "trace.jsonl").write_text("")
    return d


def _run(tmp_path, rows, *extra, capsys=None, tools=None):
    res = F.write_jsonl(tmp_path / "res.jsonl", rows)
    rc = V().main(["--route", "mmesg-oracle-new", "--root", str(tmp_path / "root"), "--results", str(res),
                   "--side", "new", "--frame-offset", "1", *extra], tools=tools or FakeTools())
    return rc, capsys.readouterr().out.strip().splitlines()[-1] if capsys else None


def test_pass_layout_and_frame_formula(tmp_path, capsys):
    root = tmp_path / "root"
    _ep(root, 1)  # 期望 2 + 5 + 1 = 8
    _ep(root, 2, "codec=h264 ok=1 frames=9")
    infra = {**_row(3, attempt=1), "infra": True}  # 作废尝试：目录可有可无，不算缺失
    rc, line = _run(tmp_path, [_row(1), _row(2, exec_steps=6), infra, _row(3, attempt=2, exec_steps=0, demo=7)],
                    capsys=capsys)
    assert rc == 1  # 第 3 个身份的 a2 目录没建 → missing
    assert line.startswith("VIDEO_SAVED=FAIL route=mmesg-oracle-new episodes=3 missing=1 decode_fail=0 "
                           "frame_mismatch=0 raw_left=0")
    _ep(root, 3, "codec=h264 ok=1 frames=8", attempt=2)
    rc, line = _run(tmp_path, [_row(1), _row(2, exec_steps=6), infra, _row(3, attempt=2, exec_steps=0, demo=7)],
                    capsys=capsys)
    assert rc == 0 and line == ("VIDEO_SAVED=PASS route=mmesg-oracle-new episodes=3 missing=0 decode_fail=0 "
                                "frame_mismatch=0 raw_left=0 bytes=72 codec_bad=0 multi_mp4=0 key_mismatch=0")


def test_each_failure_kind_counted(tmp_path, capsys):
    root = tmp_path / "root"
    _ep(root, 1, "codec=mpeg4 ok=1 frames=8")       # 编码不是 h264
    _ep(root, 2, "codec=h264 ok=0 frames=3")        # 解码出错（帧数也不符）
    d3 = _ep(root, 3, "codec=h264 ok=1 frames=7")   # 帧数差 1
    d4 = _ep(root, 4)
    (d4 / ".spool").mkdir()                          # 残留原始块目录
    (d4 / "front.mkv").write_text("x")               # 残留无损原始视频
    (d4 / "sub").mkdir()
    (d4 / "sub" / "f0.png").write_text("x")
    d5 = _ep(root, 5)
    (d5 / "second.mp4").write_text("codec=h264 ok=1 frames=8")
    _ep(root, 99)                                    # 不对应任何结果行 → orphan
    rows = [_row(s) for s in (1, 2, 3, 4, 5)]
    rc, line = _run(tmp_path, rows, capsys=capsys)
    assert rc == 1
    assert line.startswith("VIDEO_SAVED=FAIL route=mmesg-oracle-new episodes=5 missing=0 decode_fail=1 "
                           "frame_mismatch=2 raw_left=3 ")
    assert line.endswith("codec_bad=1 multi_mp4=1 key_mismatch=1")
    assert d3.exists()


def test_duplicate_rows_and_rules(tmp_path, capsys):
    root = tmp_path / "root"
    _ep(root, 1)
    rc, line = _run(tmp_path, [_row(1), _row(1)], capsys=capsys)
    assert rc == 1 and line.endswith("key_mismatch=1")  # 两条最终行指向同一目录
    rc, line = _run(tmp_path, [_row(1, video_frames=8)], "--frames-rule", "field", capsys=capsys)
    assert rc == 0
    rc, line = _run(tmp_path, [_row(1)], "--frames-rule", "fixed", "--expect-frames", "9", capsys=capsys)
    assert rc == 1 and "frame_mismatch=1" in line
    rc, line = _run(tmp_path, [_row(1, demo_frames=None)], capsys=capsys)
    assert rc == 1 and "frame_mismatch=1" in line  # 缺字段按不符计
    rc, line = _run(tmp_path, [_row(1, demo_frames=None)], "--frames-rule", "none", capsys=capsys)
    assert rc == 0
    extra = tmp_path / "node-tmp"
    (extra / "x").mkdir(parents=True)
    (extra / "x" / "front.raw").write_text("x")
    rc, line = _run(tmp_path, [_row(1)], "--raw-root", str(extra), capsys=capsys)
    assert rc == 1 and "raw_left=1" in line
    rc, line = _run(tmp_path, [], capsys=capsys)
    assert rc == 1 and "episodes=0" in line  # 没有任何局不算通过


# ── slow：真实 ffmpeg ─────────────────────────────────────────────────────────


def _encode(path: Path, frames: int, codec: str) -> None:
    ff = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
    extra = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "23",
                                    "-movflags", "+faststart"] if codec == "h264" \
        else ["-c:v", "mpeg4"]
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30", "-frames:v",
                    str(frames), *extra, str(path)], check=True, timeout=120)


@pytest.mark.slow
def test_real_ffmpeg_h264_decode_and_counts(tmp_path, capsys):
    root = tmp_path / "root"
    d1 = _ep(root, 1)
    (d1 / "episode.mp4").unlink()
    _encode(d1 / "episode.mp4", 8, "h264")
    d2 = _ep(root, 2)
    (d2 / "episode.mp4").unlink()
    _encode(d2 / "episode.mp4", 8, "mpeg4")
    d3 = _ep(root, 3)
    (d3 / "episode.mp4").unlink()
    _encode(d3 / "episode.mp4", 40, "h264")
    data = (d3 / "episode.mp4").read_bytes()
    (d3 / "episode.mp4").write_bytes(data[: len(data) // 2])  # 截断 → 解码出错
    res = F.write_jsonl(tmp_path / "res.jsonl", [_row(1), _row(2), _row(3, exec_steps=37)])
    rc = V().main(["--route", "real", "--root", str(root), "--results", str(res), "--side", "new", "--frame-offset", "1"])
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert rc == 1
    assert "episodes=3 missing=0 decode_fail=1 " in line and "codec_bad=1" in line
    # 只留合格的那一局再核一次：PASS
    res1 = F.write_jsonl(tmp_path / "res1.jsonl", [_row(1)])
    shutil.rmtree(d2)
    shutil.rmtree(d3)
    rc = V().main(["--route", "real", "--root", str(root), "--results", str(res1), "--side", "new", "--frame-offset", "1"])
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert rc == 0 and line.startswith("VIDEO_SAVED=PASS route=real episodes=1 missing=0 decode_fail=0 frame_mismatch=0 "
                                       "raw_left=0 bytes=")
