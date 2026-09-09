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
