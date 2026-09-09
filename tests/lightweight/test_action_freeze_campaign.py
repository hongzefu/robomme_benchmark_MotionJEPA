"""验证真实记录映射、reset 原图转存及 worker 类级污染检测。"""

import base64
import zlib
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from tests._shared import parity_observer as observer
from tests._shared import parity_keyframes as frames
from tests._shared import parity_worker_isolation as isolation
from tests._shared import parity_review as review
from tests._shared.action_freeze_campaign import verify_runtime_coverage
import json


def test_event_mapping_uses_record_number_instead_of_environment_step():
    evidence = {"events": [
        {"name": "交换", "timing": {"start_step": 10, "end_step": 20, "cur_step": 10}},
        {"name": "高亮", "timing": {"start_step": 30, "end_step": 40, "cur_step": 30}}],
        "recordings": [
            {"event_begin": 0, "event_end": 1, "record_begin": 2, "record_end": 3},
            {"event_begin": 1, "event_end": 2, "record_begin": 3, "record_end": 3}]}
    result = frames.event_record_indices(evidence)
    assert result["indices"] == [2]
    assert result["unrecorded_events"][0]["env_step"] == 30
    with pytest.raises(ValueError, match="记录映射"):
        frames.event_record_indices({"events": []})


def test_wrapper_observer_preserves_original_calls_and_raw_reset_rgb(monkeypatch):
    rgb = torch.arange(48, dtype=torch.uint8).reshape(1, 4, 4, 3)
    obs = {"sensor_data": {name: {"rgb": rgb} for name in ("base_camera", "hand_camera")}}
    class Wrapper:
        def __init__(self):
            self.buffer = []
            self.unwrapped = SimpleNamespace(elapsed_steps=10)
            self.calls = 0
        def reset(self):
            return obs, {}
        def step(self, action):
            self.calls += 1
            self.unwrapped.elapsed_steps += 1
            self.buffer.append(action)
            return "原返回值"
    episode = observer._EpisodeEvidence("测试", 1, "easy")
    monkeypatch.setitem(observer._state, "episode", episode)
    observer._patch_record_wrapper(SimpleNamespace(RobommeRecordWrapper=Wrapper))
    wrapper = Wrapper()
    assert wrapper.reset()[0] is obs
    assert wrapper.step(4) == "原返回值"
    assert wrapper.calls == 1
    assert episode.recordings == [{"env_step_before": 10, "env_step_after": 11,
        "record_begin": 0, "record_end": 1, "event_begin": 0, "event_end": 0}]
    stored = episode.initial_obs["rgb"]["front_rgb"]
    restored = np.frombuffer(zlib.decompress(base64.b64decode(stored["zlib_base64"])), dtype=stored["dtype"]).reshape(stored["shape"])
    assert np.array_equal(restored, rgb[0].numpy())


def test_reset_montage_uses_raw_arrays_and_detects_pixel_difference(tmp_path):
    def encode(value):
        a = np.full((4, 4, 3), value, dtype=np.uint8)
        return {"dtype": "uint8", "shape": [4, 4, 3], "zlib_base64": base64.b64encode(zlib.compress(a.tobytes())).decode()}
    images = {label: {camera: encode(value) for camera in frames.CAMERAS} for label, value in (("A1", 0), ("B", 1), ("C", 0))}
    report = frames.build_montage({"A1": None, "B": None, "C": None}, -1, "初态", tmp_path / "reset.png", initial_rgb=images)
    assert report["difference"]["front_rgb.A1-B"]["max_abs"] == 1
    assert report["difference"]["front_rgb.A1-C"]["max_abs"] == 0


def test_real_worker_wrapper_detects_class_config_mutation(monkeypatch):
    state = {"BinFill": "初始散列"}
    monkeypatch.setattr(isolation, "_class_config_hashes", lambda: dict(state))
    def worker(job):
        state["BinFill"] = "污染后的散列"
        return {"ok": True}
    monkeypatch.setattr(isolation, "_PRODUCT_WORKER", worker)
    assert isolation._checked_worker(None)["worker_class_config_unchanged"] is False


def test_final_review_rejects_unseen_and_changed_images(tmp_path):
    original = tmp_path / "original.png"
    original.write_bytes(b"original")
    board = tmp_path / "board.png"
    board.write_bytes(b"board")
    review_dir = tmp_path / "case"
    review_dir.mkdir()
    manifest_path = review_dir / "manifest.json"
    manifest = {"boards": [{"number": 0, "path": str(board), "sha256": review.sha(board),
        "reviewed": False, "reviewer": "测试检查者", "note": "测试证据", "items": [{"cell": "case", "frame": "0", "sha256": review.sha(original)}]}]}
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"run": "test", "cells": {"case": {"not_rendered": [], "montages": {"0": {
        "montage": str(original), "montage_sha256": review.sha(original), "difference": {"A-B": {"max_abs": 0, "nonzero_pixels": 0}}}}}}}))
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="未目视"):
        review.finalize(index, tmp_path, tmp_path / "out.json")
    manifest["boards"][0]["reviewed"] = True
    manifest_path.write_text(json.dumps(manifest))
    original.write_bytes(b"changed")
    with pytest.raises(ValueError, match="原图版散列"):
        review.finalize(index, tmp_path, tmp_path / "out.json")
    original.write_bytes(b"original")
    report = review.finalize(index, tmp_path, tmp_path / "out.json")
    assert report["passed"] and report["image_count"] == 1


@pytest.mark.parametrize("use_global", [False, True])
def test_rng_observer_captures_both_states_without_consuming_randomness(monkeypatch, use_global):
    episode = observer._EpisodeEvidence("测试", 31, "easy")
    monkeypatch.setitem(observer._state, "episode", episode)
    original = torch.rand
    generator = None if use_global else torch.Generator().manual_seed(31)
    source = torch.default_generator if use_global else generator
    before = source.get_state().clone()
    expected = original(3, generator=generator)
    after = source.get_state().clone()
    source.set_state(before)
    module = SimpleNamespace(rand=original)
    observer._wrap_random(module, "rand")
    assert torch.equal(module.rand(3, generator=generator), expected)
    assert torch.equal(source.get_state(), after)
    record = episode.rng[0]
    assert record["rng_before"]["state_sha256"] == observer._digest(before.numpy().tobytes())
    assert record["rng"]["state_sha256"] == observer._digest(after.numpy().tobytes())
    assert record["rng_before"]["source"] == ("global" if use_global else "generator")
    assert record["rng_before"] != record["rng"]


def test_runtime_coverage_rejects_declared_but_unexercised_branch():
    case = {"task": "BinFill", "difficulty": "easy", "branch": "dynamic=True"}
    state = {"difficulty": "hard", "dynamic": False}
    evidence = {"boundaries": [{"stage": "after_load_scene", "task_state": state, "actors": {}}],
        "rng": [{"rng_before": {"state_sha256": "a"}, "rng": {"state_sha256": "b", "source": "generator"}}], "rng_total": 1}
    with pytest.raises(ValueError, match="实际难度"):
        verify_runtime_coverage(case, evidence)
    state["difficulty"] = "easy"
    with pytest.raises(ValueError, match="dynamic"):
        verify_runtime_coverage(case, evidence)
    state["dynamic"] = True
    assert verify_runtime_coverage(case, evidence)["both_rng_states_recorded"]
    evidence["rng"][0].pop("rng_before")
    with pytest.raises(ValueError, match="随机状态"):
        verify_runtime_coverage(case, evidence)
