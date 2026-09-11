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


# ── swap 事件 ─────────────────────────────────────────────────────────────────
PAIRS3 = [{"initiator": "bin_0", "partner": "bin_2"}, {"initiator": "bin_1", "partner": "bin_0"}, {"initiator": "bin_2", "partner": "bin_1"}]


@pytest.mark.parametrize("n,demo_len", [(1, 114), (2, 168), (3, 216)])
def test_unmask_swaps_schedule(wt, n, demo_len):
    swaps = wt.unmask_swaps(n, PAIRS3)
    assert [s[:2] for s in swaps] == [[64 + 50 * k, 64 + 50 * (k + 1)] for k in range(n)]
    assert swaps[0][2] == "bin_0↔bin_2"
    # demo 段长 = 6·ceil((64+50n)/6)
    assert 6 * -(-(64 + 50 * n) // 6) == demo_len
    assert swaps[-1][1] <= demo_len


def test_static_start_from_deltas_reproduces_static_check(wt):
    # 帧 165 起：运动（>0.01）到 182，183 起静止；中途 190 抖一下重置计数 → 首个连续 20 帧静止是 191..210，S = 211
    deltas = [0.02] * 18 + [0.005] * 7 + [0.03] + [0.001] * 60
    assert wt.static_start_from_deltas(deltas, 165) == 165 + 18 + 7 + 1 + 20
    # 不抖动：183 起静止 → S = 203
    deltas = [0.02] * 18 + [0.005] * 60
    assert wt.static_start_from_deltas(deltas, 165) == 203
    assert wt.static_start_from_deltas([0.02] * 30, 165) is None
    assert wt.static_start_from_deltas([0.0] * 19, 165) is None


def test_solve_swap_end_and_first_change(wt):
    diffs = {t: v for t, v in zip(range(198, 320), [0] * 5 + [1791, 5487, 6912] + [17000] * 40 + [28000] + [120] * 73)}
    assert wt.solve_swap_end(diffs) == 198 + 5 + 3 + 40
    # 阈值 = 10% × 尖峰 = 2800：203 帧的 1791 低于阈值，首个超阈值帧是 204（真实 Unmask 的 64 帧是 2.5 万级跳变，不受此影响）
    assert wt.solve_swap_first_change(diffs) == 204
    # VideoRepick 口径：末尾无尖峰、收尾帧差两千级、之后严格为 0 → 绝对阈值 100 取最后一个非零帧
    diffs = {t: v for t, v in zip(range(198, 320), [0, 6, 9] + [1791, 5487] + [17000] * 46 + [34000] + [17000] * 46 + [2495, 2265] + [0] * 22)}
    assert wt.solve_swap_end(diffs, absolute=wt.FREEZE_THRESHOLD) == 198 + 3 + 2 + 93 + 1
    assert wt.solve_swap_end(diffs) == 198 + 3 + 2 + 93 - 1  # 相对阈值 3400 会把收尾两帧滤掉，这正是 Repick 不能用它的原因
    assert wt.solve_swap_end({}) is None


def test_repick_swaps_and_first_swap_static(wt):
    assert [s[:2] for s in wt.repick_swaps(203, 2, PAIRS3)] == [[203, 253], [253, 303]]
    segs = [[0, 119, "pick up the cube"], [119, 46, "drop the cube on the table"], [165, 54, "static"], [219, 54, "static"],
            [273, 54, "static"], [327, 100, "pick up the correct cube for the first time"], [427, 40, "static"]]
    assert wt.first_swap_static(segs, 327) == (165, 219)
    segs2 = [[0, 119, "pick up the cube"], [119, 46, "drop the cube on the table"], [165, 43, "static"], [208, 70, "static"]]
    assert wt.first_swap_static(segs2, 278) == (165, 208)  # 没有 48～60 的段时退到第 2 个 static
    assert wt.first_swap_static([[0, 10, "pick up the cube"]], 10) == (None, None)


def test_tables_include_swap_column(wt, tmp_path):
    data = _synthetic_timeline(wt)
    data["groups"]["VideoUnmaskSwap/easy"] = [
        {"episode": 0, "seed": 5000, "total": 335, "demo": 168, "recovery_mode": None,
         "segs": [[0, 168, "static"], [168, 156, "pick up the container that hides the red cube"], [324, 11, "All tasks completed"]],
         "swaps": wt.unmask_swaps(2, PAIRS3), "swap_source": "schedule", "swap_pixel_first": 64, "swap_pixel_end": 164, "swap_check": "PASS"}]
    data["groups"]["VideoRepick/easy"] = [
        {"episode": 2, "seed": 9200, "total": 700, "demo": 327, "recovery_mode": None,
         "segs": [[0, 119, "pick up the cube"], [119, 46, "drop the cube on the table"], [165, 54, "static"], [219, 54, "static"], [273, 54, "static"],
                  [327, 300, "pick up the correct cube for the first time"], [627, 73, "All tasks completed"]],
         "swaps": wt.repick_swaps(203, 2, PAIRS3), "swap_source": "joint_static", "swap_start": 203, "swap_start_joint": 204,
         "swap_start_pixel": 203, "swap_pixel_end": 303, "b1_minus_s": 16, "swap_check": "WARN"}]
    text, rows = wt.render_tables(data)
    assert rows == 5
    assert "| 段序列（短标 帧数，‖ = demo→exec） | swap 起止帧（发起者↔搭档） |" in text
    assert "| 1: 64–114 bin_0↔bin_2 · 2: 114–164 bin_1↔bin_0 |" in text
    assert "| ⚠WARN 1: 203–253 bin_0↔bin_2 · 2: 253–303 bin_1↔bin_0（关节法 S=204、像素法 S=203，取像素法，B1−S=16） |" in text
    data["groups"]["VideoRepick/easy"][0].update({"swap_start_joint": 203, "swap_check": "PASS"})
    text, _ = wt.render_tables(data)
    assert "bin_1↔bin_0（关节法 S=203 = 像素法，B1−S=16） |" in text and "⚠" not in text.split("### VideoRepick / easy")[1]
    # 非视频任务的表没有这一列
    assert "| 0 | 16000 | 300 | 150 | 7 | 8+8=16 | 9.6 | 42.7 | 绕左逆 50 · 绕右顺 50 · 绕右顺 50 ‖ 绕左逆 50 · 绕右顺 50 · 绕右顺 43 · 完成 7 |\n" in text


# ── xhard 扩展（2026-09-11）：14 组真源、5 色、多运行合并 ──────────────────────
def test_groups_是十四组且与注入组列表一致(wt):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.injection.specs import GROUPS_V3

    assert wt.GROUPS == list(GROUPS_V3) and len(wt.GROUPS) == 14
    assert wt.GROUPS[-3:] == [("RouteStick", "xhard"), ("VideoUnmaskSwap", "xhard"), ("VideoRepick", "xhard")]


def test_跑前图的swap颜色扩到五色且前三色不变():
    source = (Path(__file__).resolve().parents[2] / "scripts" / "injection-before-2d" / "plot_injection_before_2d.py").read_text(encoding="utf-8")
    assert 'SWAP_COLORS = ["#6a1b9a", "#ef6c00", "#00838f", "#ad1457", "#5d4037"]' in source


@pytest.mark.parametrize("n", [4, 5])
def test_unmask_xhard_四五次调度(wt, n):
    pairs = [{"initiator": f"bin_{k % 3}", "partner": f"bin_{(k + 1) % 3}"} for k in range(n)]
    swaps = wt.unmask_swaps(n, pairs)
    assert len(swaps) == n and swaps[0][0] == 64 and swaps[-1][1] == 64 + 50 * n
    assert all(swaps[k][1] == swaps[k + 1][0] for k in range(n - 1))


def test_extract_多运行后者覆盖前者(wt, tmp_path, monkeypatch):
    """两个运行的 episode_results.jsonl 合并：同 key 取后者；行里记 run_id；不开 h5（全部造成失败行）。"""
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        d.mkdir()
    a.joinpath("episode_results.jsonl").write_text(
        json.dumps({"task": "RouteStick", "difficulty": "hard", "episode": 0, "seed": 1, "ok": False, "error_type": "X"}) + "\n", encoding="utf-8")
    b.joinpath("episode_results.jsonl").write_text(
        json.dumps({"task": "RouteStick", "difficulty": "hard", "episode": 0, "seed": 1, "ok": False, "error_type": "Y"}) + "\n"
        + json.dumps({"task": "RouteStick", "difficulty": "xhard", "episode": 0, "seed": 1, "ok": False, "error_type": "Z"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(wt, "REPO_ROOT", tmp_path)
    payload = wt.extract(["run-a", "run-b"], [a, b])
    assert payload["rollout_run_ids"] == ["run-a", "run-b"] and payload["rollout_run_id"] == "run-a,run-b"
    by_key = {(r["task"], r["difficulty"], r["episode"]): r for r in payload["failed_rows"]}
    assert by_key[("RouteStick", "hard", 0)]["error_type"] == "Y"  # 后者覆盖前者
    assert by_key[("RouteStick", "xhard", 0)]["error_type"] == "Z"
    with pytest.raises(ValueError):
        wt.extract(["only-one"], [a, b])
