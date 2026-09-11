"""采样窗口数轴数据层（scripts/injection-before-2d/window_timeline.py）的轻量测试：

* 窗口公式与上一会话 artifact「采样窗口与 eval 成功率」的数字逐条对拍；
* BinFill「同一条重复两遍」的模拟 demo；
* 31 种 subgoal 文本的短标规则全部命中；
* 自动表写入／校验往返无漂移。
不依赖数据集、不开 h5。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "injection-before-2d" / "window_timeline.py"


@pytest.fixture(scope="module")
def wt():
    spec = importlib.util.spec_from_file_location("window_timeline", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["window_timeline"] = module
    spec.loader.exec_module(module)
    return module


# artifact DATA 里的代表条：(T, demo) → (demo 窗口, exec 窗口)
ARTIFACT_CASES = [
    ((50, 25), (0, 0)),      # PatternLock easy 最短：两段都不足 33 帧
    ((138, 69), (3, 3)),     # PatternLock easy 中位：range(0, 37, 16) = 3
    ((200, 100), (5, 5)),    # RouteStick easy 最短
    ((300, 150), (8, 8)),    # RouteStick easy 中位
    ((700, 350), (20, 20)),  # RouteStick hard 最长
    ((249, 0), (0, 14)),     # BinFill easy 最短（artifact 原版无 demo）：range(0, 217, 16) = 14
]


@pytest.mark.parametrize("shape,expected", ARTIFACT_CASES)
def test_window_counts_match_artifact(wt, shape, expected):
    total, demo = shape
    assert wt.window_counts({"total": total, "demo": demo}) == expected


def test_window_starts_formula(wt):
    assert wt.window_starts(32) == []
    assert wt.window_starts(33) == [0]
    assert wt.window_starts(48) == [0]
    assert wt.window_starts(49) == [0, 16]
    assert wt.window_starts(100) == [0, 16, 32, 48, 64]


def test_frame_path_and_deltas(wt):
    assert wt.frame_path(50, 8) == [0, 7, 14, 21, 28, 35, 42, 49]
    assert wt.frame_path(300, 8) == [0, 43, 85, 128, 171, 214, 256, 299]
    assert wt.frame_path(200, 32)[0] == 0 and wt.frame_path(200, 32)[-1] == 199
    d32, d8 = wt.deltas(200)
    assert (round(d32, 1), round(d8, 1)) == (6.4, 28.4)
    assert tuple(round(v, 1) for v in wt.deltas(300)) == (9.6, 42.7)
    # JS Math.round 口径：x.5 向上
    assert wt.frame_path(4, 3) == [0, 2, 3]


def test_simulate_binfill_demo(wt):
    row = {"episode": 0, "seed": 4000, "total": 678, "demo": 0,
           "segs": [[0, 130, "pick up the first blue cube"], [130, 70, "put it into the bin"], [200, 478, "All tasks completed"]]}
    sim = wt.simulate_binfill_demo(row)
    assert (sim["total"], sim["demo"], sim["original_total"], sim["simulated_demo"]) == (1356, 678, 678, True)
    assert sim["segs"][:3] == row["segs"]
    assert sim["segs"][3:] == [[678, 130, "pick up the first blue cube"], [808, 70, "put it into the bin"], [878, 478, "All tasks completed"]]
    assert wt.window_counts(sim) == (41, 41)
    assert round(wt.deltas(sim["total"])[0], 1) == 43.7
    assert row["total"] == 678  # 不改原行


KNOWN_TEXTS = {
    "All tasks completed": "完成", "static": "静止", "put it into the bin": "投箱",
    "move to the nearest left target by circling around the stick counterclockwise": "绕左逆",
    "move to the nearest left target by circling around the stick clockwise": "绕左顺",
    "move to the nearest right target by circling around the stick clockwise": "绕右顺",
    "move to the nearest right target by circling around the stick counterclockwise": "绕右逆",
    "put it down": "放下", "press the button": "按钮", "pick up the cube": "抓块", "drop the cube on the table": "放桌",
    "pick up the correct cube for the first time": "抓对1", "pick up the correct cube for the second time": "抓对2",
    "pick up the correct cube for the third time": "抓对3", "press the button to finish": "按钮停",
    "pick up the container that hides the red cube": "抓红容", "pick up the container that hides the green cube": "抓绿容",
    "pick up the container that hides the blue cube": "抓蓝容", "put down the container": "放容",
    "pick up the first green cube": "抓绿1", "pick up the first blue cube": "抓蓝1", "pick up the first red cube": "抓红1",
    "pick up the second green cube": "抓绿2", "pick up the second red cube": "抓红2", "pick up the second blue cube": "抓蓝2",
    "pick up the third blue cube": "抓蓝3", "pick up the third green cube": "抓绿3", "pick up the third red cube": "抓红3",
    "pick up the fourth blue cube": "抓蓝4", "pick up the fourth red cube": "抓红4", "pick up the fourth green cube": "抓绿4",
}


def test_short_label_covers_all_observed_texts(wt):
    assert len(KNOWN_TEXTS) == 31
    for text, expected in KNOWN_TEXTS.items():
        label, known = wt.short_label(text)
        assert known, text
        assert label == expected, text
    label, known = wt.short_label("some brand new instruction")
    assert not known and label == "some b"


def test_phase_segments_and_representatives(wt):
    assert wt.phase_segments({"total": 300, "demo": 150}) == [(0, 150, "demo"), (150, 150, "exec")]
    assert wt.phase_segments({"total": 300, "demo": 0}) == [(0, 300, "exec")]
    rows = [{"episode": e, "total": t} for e, t in [(0, 300), (1, 200), (2, 250), (3, 200)]]
    reps = wt.representatives(rows)
    assert (reps["最短"]["episode"], reps["中位"]["episode"], reps["最长"]["episode"]) == (1, 2, 0)


def _synthetic_timeline(wt):
    groups = {f"{t}/{d}": [] for t, d in wt.GROUPS}
    groups["RouteStick/easy"] = [
        {"episode": 0, "seed": 16000, "total": 300, "demo": 150, "recovery_mode": None,
         "segs": [[0, 50, "move to the nearest left target by circling around the stick counterclockwise"],
                  [50, 50, "move to the nearest right target by circling around the stick clockwise"],
                  [100, 50, "move to the nearest right target by circling around the stick clockwise"],
                  [150, 50, "move to the nearest left target by circling around the stick counterclockwise"],
                  [200, 50, "move to the nearest right target by circling around the stick clockwise"],
                  [250, 43, "move to the nearest right target by circling around the stick clockwise"],
                  [293, 7, "All tasks completed"]]},
        {"episode": 1, "seed": 16100, "total": 200, "demo": 100, "recovery_mode": "z",
         "segs": [[0, 50, "move to the nearest left target by circling around the stick counterclockwise"],
                  [50, 50, "move to the nearest right target by circling around the stick clockwise"],
                  [100, 50, "move to the nearest left target by circling around the stick counterclockwise"],
                  [150, 43, "move to the nearest right target by circling around the stick clockwise"],
                  [193, 7, "All tasks completed"]]},
    ]
    groups["BinFill/easy"] = [wt.simulate_binfill_demo(
        {"episode": 0, "seed": 4000, "total": 249, "demo": 0, "recovery_mode": None,
         "segs": [[0, 103, "pick up the first green cube"], [103, 59, "put it into the bin"], [162, 51, "press the button"], [213, 36, "All tasks completed"]]})]
    return {"rollout_run_id": "synthetic", "source": "x", "window": 33, "stride": 16, "budgets": [32, 8], "binfill_simulated_demo": True,
            "episodes": 3, "groups": groups,
            "skipped": [{"task": "VideoRepick", "difficulty": "easy", "episode": 0, "reason": "OSError"}],
            "failed_rows": [{"task": "BinFill", "difficulty": "easy", "episode": 10, "error_type": "DatasetGenerationError"}],
            "unknown_labels": {}}


def test_tables_roundtrip(wt, tmp_path):
    json_path = tmp_path / "wt.json"
    json_path.write_text(json.dumps(_synthetic_timeline(wt), ensure_ascii=False), encoding="utf-8")
    doc_path = tmp_path / "doc.md"
    doc_path.write_text(f"# x\n\n{wt.BEGIN}\n{wt.END}\n", encoding="utf-8")
    assert wt.check(json_path, doc_path) == (False, 3, 1) or wt.check(json_path, doc_path)[0] is False
    assert wt.main(["tables", "--json", str(json_path), "--doc", str(doc_path), "--write"]) == 0
    assert wt.check(json_path, doc_path) == (True, 3, 0)
    text = doc_path.read_text(encoding="utf-8")
    assert "| 0 | 16000 | 300 | 150 | 7 | 8+8=16 | 9.6 | 42.7 | 绕左逆 50 · 绕右顺 50 · 绕右顺 50 ‖ 绕左逆 50 · 绕右顺 50 · 绕右顺 43 · 完成 7 |" in text
    assert "| 1 | 16100 | 200 | 100 | 5 | 5+5=10 | 6.4 | 28.4 |" in text
    assert "| 0 | 4000 | 498 = 2×249 | 249 | 8 | 14+14=28 |" in text
    assert "| BinFill/easy（模拟 demo） | 1 |" in text and "| VideoRepick/easy | 0 | — | — | — | — | 1 |" in text
    # 手改表 → 漂移
    doc_path.write_text(text.replace("8+8=16", "8+8=17"), encoding="utf-8")
    ok, rows, drift = wt.check(json_path, doc_path)
    assert (ok, rows) == (False, 3) and drift >= 2
