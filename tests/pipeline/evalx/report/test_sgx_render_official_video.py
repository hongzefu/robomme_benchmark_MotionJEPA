"""官方原类逐位对照与真实编解码；覆盖存量 strict cap、精度恢复及坏轨迹拒绝。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from tests._support.loaders import load_script


def _module():
    return load_script("eval-official/render_official_video.py")


def _official_root(repo_root):
    # worktree 子模块未初始化时只读引用主检出；测试不初始化或修改 gitlink。
    if (repo_root / "third_party/mme-vla/examples/robomme/utils.py").is_file():
        return repo_root
    return Path(os.environ["SGEVAL_THIRD_PARTY"]).parent


def _array(a):
    a = np.asarray(a)
    return {"dtype": a.dtype.str, "shape": list(a.shape), "sha256": hashlib.sha256(a.tobytes()).hexdigest(),
            "f32hex": a.astype("<f4").tobytes().hex()}


def _rows(*, demo=2, steps=3, max_steps=10, terminal="success", status=None, task="VideoUnmask", action_dtype="<f4"):
    identity = {"task": task, "tier": "xhard0", "seed": 123, "dataset": "test-hard", "source_episode": 3,
                "builder_episode": 0, "key": f"{task}_xhard0_123"}
    rows = [{"kind": "header", "schema": "sgeval-trace/1", "route": "mmesg/ground-sg-oracle/new",
             "identity": identity, "max_steps": max_steps},
            {"kind": "demo", "frames": demo + 1, "front_sha256": ["front"] * (demo + 1),
             "wrist_sha256": ["wrist"] * (demo + 1), "states": [_array(np.arange(8, dtype="<f4") / 9)] * (demo + 1),
             "texts": ["press button"]}]
    for step in range(1, steps + 1):
        rows.append({"kind": "step", "step": step, "state": _array(np.arange(8, dtype="<f4") / 7),
                     "action": _array(np.arange(8, dtype=action_dtype) / 11), "front_sha256": "front",
                     "wrist_sha256": "wrist", "subgoal": f"move to <3, 5> {step}", "terminated": False,
                     "truncated": False, "status": "unknown"})
    rows.append({"kind": "end", "demo_frames": demo, "exec_steps": steps, "terminal_reason": terminal,
                 "status": status or terminal})
    return rows


def _trace(tmp_path, rows):
    path = tmp_path / "trace.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return _module().load_trace(path)


@pytest.mark.parametrize("task", ["VideoUnmask", "BinFill"])
def test_feed_matches_official_recorder_bitwise(tmp_path, repo_root, task):
    mod = _module()
    trace = _trace(tmp_path, _rows(task=task))
    Recorder, demo_tasks = mod.load_official(_official_root(repo_root))
    left, right = Recorder(tmp_path / "left", trace.task_goal), Recorder(tmp_path / "right", trace.task_goal)
    frames = np.random.default_rng(42).integers(0, 256, (6, 8, 8, 3), dtype=np.uint8)
    wrists = np.random.default_rng(43).integers(0, 256, (6, 8, 8, 3), dtype=np.uint8)
    # 独立对照按官方 init_episode 的 3 个输入与执行循环的 3 个输入直接调原类。
    for i in range(3):
        left.record(frames[i].copy(), wrists[i].copy(), trace.init_states[i].copy(),
                    is_video_demo=task in demo_tasks and i < 2, subgoal="[initializing...]")
    for i in range(3):
        st = trace.steps[i]
        left.record(frames[i + 3].copy(), wrists[i + 3].copy(), st["state"].copy(),
                    action=st["action"].copy(), subgoal=st["subgoal"])
    mod.feed_official_recorder(right, frames, wrists, trace, task, demo_tasks)
    assert len(left.total_images) == len(right.total_images) == 6
    assert all(np.array_equal(a, b) for a, b in zip(left.total_images, right.total_images))
    print("RENDER_PARITY=PASS frames=6 mismatch=0")


def test_f32hex_roundtrip_and_shape_guard():
    mod = _module()
    a = np.linspace(-1, 1, 8, dtype="<f4")
    assert np.array_equal(mod.f32_from_record(_array(a)), a)
    for bad in ({**_array(a), "shape": [1, 8]}, {**_array(a), "f32hex": "00"},
                {**_array(a), "sha256": "0" * 64}, _array(np.full(8, np.nan, dtype="<f4"))):
        with pytest.raises(ValueError):
            mod.f32_from_record(bad)


def test_restore_float64_action_with_verified_npz(tmp_path):
    mod = _module()
    rows = _rows(demo=0, steps=1, action_dtype="<f8")
    action = np.array([0, 0.8404500172406898, 0, 0, 0, 0, 0, 0], dtype="<f8")
    rows[2]["action"] = _array(action)
    path = tmp_path / "trace.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(ValueError, match="丢失原数组精度"):
        mod.load_trace(path)
    np.savez(tmp_path / "arrays.npz", exec_action__00000=action)
    trace = mod.load_trace(path)
    assert trace.steps[0]["action"].dtype == np.dtype("<f8")
    assert np.array_equal(trace.steps[0]["action"], action)
    assert f"{trace.steps[0]['action'][1]:.4f}" == "0.8405"
    assert f"{mod.f32_from_record(_array(action))[1]:.4f}" == "0.8404"
    np.savez(tmp_path / "arrays.npz", exec_action__00000=action + 1)
    with pytest.raises(ValueError, match="sha256"):
        mod.load_trace(path)


@pytest.mark.parametrize("terminal,status,steps,omitted", [("timeout", "timeout", 3, 1),
                                                           ("error", "timeout", 2, 0),
                                                           ("timeout", "timeout", 2, 0)])
def test_timeout_only_omits_official_unrecorded_overrun(tmp_path, repo_root, terminal, status, steps, omitted):
    mod = _module()
    trace = _trace(tmp_path, _rows(demo=0, steps=steps, max_steps=2, terminal=terminal, status=status))
    Recorder, demo_tasks = mod.load_official(_official_root(repo_root))
    rec = Recorder(tmp_path / "out", trace.task_goal)
    images = np.zeros((steps + 1, 8, 8, 3), np.uint8)
    mod.feed_official_recorder(rec, images, images, trace, "VideoUnmask", demo_tasks)
    assert trace.omitted_timeout_frames == omitted
    assert len(rec.total_images) == steps + 1 - omitted
    assert trace.terminal_reason == terminal and trace.end_status == status


def test_no_demo_no_subgoal_and_wrong_frame_count(tmp_path, repo_root):
    mod = _module()
    rows = _rows(demo=0, steps=1, task="BinFill")
    rows[0]["route"] = "mme/new"
    rows[2]["subgoal"] = None
    trace = _trace(tmp_path, rows)
    assert trace.init_subgoal is None and trace.demo_frames == 0 and trace.source_frames == 2
    Recorder, demo_tasks = mod.load_official(_official_root(repo_root))
    rec = Recorder(tmp_path / "out", trace.task_goal)
    images = np.zeros((2, 8, 8, 3), np.uint8)
    mod.feed_official_recorder(rec, images, images, trace, "BinFill", demo_tasks)
    assert len(rec.total_images) == 2
    with pytest.raises(ValueError, match="frame_count"):
        mod.feed_official_recorder(rec, images[:1], images, trace, "BinFill", demo_tasks)


@pytest.mark.parametrize("defect", ["double_init", "reordered", "duplicate_end", "missing_state", "end_count", "bad_terminal"])
def test_malformed_trace_rejected(tmp_path, defect):
    rows = _rows()
    if defect == "double_init":
        rows[1]["frames"] += 1
    elif defect == "reordered":
        rows[2], rows[3] = rows[3], rows[2]
    elif defect == "duplicate_end":
        rows.append(rows[-1])
    elif defect == "missing_state":
        rows[1]["states"] = []
    elif defect == "end_count":
        rows[-1]["exec_steps"] -= 1
    else:
        rows[-1]["status"] = "success"
        rows[-1]["terminal_reason"] = "error"
    with pytest.raises(ValueError):
        _trace(tmp_path, rows)


def test_safe_filename_preserves_full_semantics_with_utf8_limit():
    mod = _module()
    short = "official-rerender__VideoUnmask_ep3a1_success_goal_xhard0.mp4"
    assert mod.safe_filename(short) == short
    a, b = "official-rerender__" + "目标" * 110 + "_xhard1.mp4", "official-rerender__" + "目标" * 110 + "_xhard2.mp4"
    assert len(mod.safe_filename(a).encode()) <= 255
    assert mod.safe_filename(a) != mod.safe_filename(b)
    assert "/" not in mod.safe_filename("goal/with/slash.mp4")


@pytest.mark.slow
def test_end_to_end_with_real_ffmpeg(tmp_path, repo_root, capsys):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("未验证：缺少 ffmpeg/ffprobe")
    mod = _module()
    ep = tmp_path / "VideoUnmask_xhard0_123.a1"
    ep.mkdir()
    rows = _rows(demo=1, steps=2)
    (ep / "trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=512x256:rate=30",
                    "-frames:v", "4", "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", str(ep / "episode.mp4")], check=True)
    source_before = mod.fingerprint(ep / "episode.mp4")
    official = _official_root(repo_root)
    assert mod.main([str(ep), "--official-root", str(official)]) == 0
    assert "OFFICIAL_RENDER_SUMMARY=PASS total=1 ok=1 fail=0" in capsys.readouterr().out
    result = json.loads((ep / "official/render.json").read_text())
    assert result["safe_name"] == "official-rerender__VideoUnmask_ep3a1_success_press button_xhard0.mp4"
    assert result["frames"] == 4 and result["fps"] == "30"
    assert result["width"] == 512 and result["height"] == 512
    assert result["render_status"] == "rendered" and result["status"] == "success"
    assert mod.render_episode(ep, official_root=official)["render_status"] == "reused"
    result["source_trace"]["sha256"] = "0" * 64
    (ep / "official/render.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="拒绝覆盖"):
        mod.render_episode(ep, official_root=official)
    replaced = mod.render_episode(ep, official_root=official, overwrite=True)
    assert replaced["render_status"] == "rendered"
    assert mod.fingerprint(ep / "episode.mp4") == source_before
