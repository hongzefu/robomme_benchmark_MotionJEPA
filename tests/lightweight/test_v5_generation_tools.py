#!/usr/bin/env python3
"""轻量测试：V5 生成工具链（NEWTASK_RELEASE_V5_PLAN 3.1～3.3 S4～S6）。

纯 CPU、不起仿真环境：
* ``v4_specs draw --workers N`` 的多 worker 合并：假 reset + 线程池，结果与单 worker 逐行相同（除墙钟），
  合并产物 freeze 能直接读；行序乱了或缺环境拒绝合并；
* ``v5_generation report`` 的解析：小型假 drafts/specs/results + 假 rng_trace + 真实小 h5；
  字段缺失时记 N/A 不崩；
* ``v5_generation pipeline`` 的落点推导与 ``--resume``；``v4_rollout run --gpu`` 透传；
  ``train_split_config extract --release`` 的默认落点与说明文字。

    uv run --no-sync python -m pytest tests/lightweight/test_v5_generation_tools.py -q
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
for extra in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.parity import v4_specs as V  # noqa: E402
from scripts.parity import v5_generation as G  # noqa: E402

TASKS = ["PatternLock", "RouteStick", "VideoRepick"]


# ── 抽签多 worker ──────────────────────────────────────────────────────────


def _fake_draw_one(task, seed, episode, sampling):
    """确定性假 reset：seed 能被 3 整除的失败；成功时规格只依赖 seed（与进程无关）。"""
    time.sleep(random.random() * 0.01)  # 打乱完成顺序
    if seed % 3 == 0:
        return False, None, "SceneGenerationError", "fake"
    return True, {"spec_kind": "native-newvalue/1", "task": task, "objects": {"seed": seed}}, None, None


def _strip_wall(rows):
    return [{k: v for k, v in row.items() if k != "wall_s"} for row in rows]


def _samplings():
    sampling = json.loads(V.DEFAULT_SAMPLING.read_text(encoding="utf-8"))
    return sampling, {t: V.task_sampling(sampling, t) for t in TASKS}


def test_draw_task_follows_seed_rule_and_budget() -> None:
    rows = V.draw_task("PatternLock", {}, candidates_per_env=4, max_reset_attempts=30, draw_one=_fake_draw_one)
    ok = [r for r in rows if r["reset_ok"]]
    assert [r["episode"] for r in ok] == [0, 1, 2, 3]
    for row in rows:
        assert row["seed"] == V.seed_for("PatternLock", row["episode"], row["attempt"])
        assert (row["seed"] % 3 == 0) == (not row["reset_ok"])
    # 预算先到：尝试满即停，成功数不足
    short = V.draw_task("PatternLock", {}, candidates_per_env=10, max_reset_attempts=3, draw_one=_fake_draw_one)
    assert len(short) == 3


@pytest.mark.parametrize("workers", [2, 3, 8])
def test_multi_worker_rows_identical_to_single_worker(workers: int) -> None:
    _, samplings = _samplings()
    single = V.draw_rows(TASKS, samplings, 5, 30, workers=1, draw_one=_fake_draw_one)
    multi = V.draw_rows(TASKS, samplings, 5, 30, workers=workers, draw_one=_fake_draw_one,
                        executor_factory=lambda n: ThreadPoolExecutor(max_workers=n))
    assert _strip_wall(multi) == _strip_wall(single)
    # 行序：按任务序，每环境内按抽签先后
    assert [r["task"] for r in multi] == sorted([r["task"] for r in multi], key=TASKS.index)


def test_merged_drafts_freeze_directly(tmp_path: Path) -> None:
    sampling, samplings = _samplings()
    header = V.build_draw_header("t", sampling, TASKS)
    rows = V.draw_rows(TASKS, header["sampling_config"], 7, 30, workers=3, draw_one=_fake_draw_one,
                       executor_factory=lambda n: ThreadPoolExecutor(max_workers=n))
    drafts = tmp_path / "drafts.jsonl"
    V._write_jsonl(drafts, [header, *rows])
    result = V.freeze(drafts, V.DEFAULT_SAMPLING, tmp_path / "specs.jsonl", candidates_per_env=10)
    assert result["selected"] == 3 * len(TASKS)
    assert all(v["candidate_shortfall"] == 3 for v in result["per_env"].values())
    lines = drafts.read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if '"record":"header"' in line) == 1


def test_merge_rejects_bad_order_or_missing_task() -> None:
    rows = {t: V.draw_task(t, {}, 3, 30, draw_one=_fake_draw_one) for t in TASKS}
    with pytest.raises(V.SpecsError, match="缺少环境"):
        V.merge_task_rows(TASKS, {t: rows[t] for t in TASKS[:2]})
    shuffled = dict(rows)
    shuffled["RouteStick"] = list(reversed(rows["RouteStick"]))
    with pytest.raises(V.SpecsError, match="行序"):
        V.merge_task_rows(TASKS, shuffled)
    swapped = dict(rows)
    swapped["PatternLock"] = rows["RouteStick"]
    with pytest.raises(V.SpecsError, match="行序"):
        V.merge_task_rows(TASKS, swapped)


def test_worker_failure_blocks_writing() -> None:
    def crash(task, seed, episode, sampling):
        if task == "RouteStick":
            raise RuntimeError("子进程崩溃")
        return _fake_draw_one(task, seed, episode, sampling)

    _, samplings = _samplings()
    with pytest.raises(V.SpecsError, match="RouteStick"):
        V.draw_rows(TASKS, samplings, 2, 30, workers=2, draw_one=crash,
                    executor_factory=lambda n: ThreadPoolExecutor(max_workers=n))


def test_parse_gpus() -> None:
    assert V._parse_gpus(None) is None
    assert V._parse_gpus("") is None
    assert V._parse_gpus("0, 1") == ["0", "1"]


# ── 生成报告 ─────────────────────────────────────────────────────────────


def _write_jsonl(path: Path, rows) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


REPORT_TASKS = ["PatternLock", "RouteStick", "VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick", "InsertPeg"]


def _spec(task: str, episode: int) -> dict:
    spec = {"task": task, "objects": {}}
    if task == "VideoUnmaskSwap":
        spec["objects"]["n_swaps"] = 3
        # ep0 字典形态且相等；ep3 列表形态但少一个窗口
        spec["actions"] = {"distractor_swap_pairs": {"0": [1, 2], "1": [3, 4], "2": [1, 5]}} if episode == 0 \
            else {"distractor_swap_pairs": [[1, 2], [3, 4]]}
    if task == "ButtonUnmaskSwap":
        spec["objects"]["n_swaps"] = 2  # 不带外环字段 ⇒ N/A
    if task == "VideoRepick" and episode == 0:
        spec["actions"] = {"swap_pairs": {str(k): {"initiator": f"bin_{k % 6}", "partner": f"bin_{(k + 1) % 6}"}
                                          for k in range(6)}}
    return spec


def _fixture(tmp_path: Path):
    header = {"record": "header", "run_id": "fake", "tasks": REPORT_TASKS}
    drafts = [header]
    specs = [{"record": "header", "tasks": REPORT_TASKS, "select_indices": [0, 3, 6], "identity_sha256": "x"}]
    for task in REPORT_TASKS:
        n_ok = 5 if task == "InsertPeg" else 10  # InsertPeg 候选不足 5 条
        if task == "VideoRepick":
            drafts.append({"record": "draft", "task": task, "episode": 0, "attempt": 0, "reset_ok": False,
                           "fail_class": "BinCollisionError", "spec": None})
        for ep in range(n_ok):
            spec = _spec(task, ep)
            drafts.append({"record": "draft", "task": task, "episode": ep, "attempt": int(task == "VideoRepick" and ep == 0),
                           "reset_ok": True, "fail_class": None, "spec": spec})
            specs.append({"record": "spec", "task": task, "episode": ep, "spec": spec, "selected": ep in (0, 3, 6)})
    rollout = tmp_path / "rollout" / "run1"
    results = []

    def add(task, ep, ok, role="selected", error_type=None, frames=None, trace=None):
        ep_dir = rollout / "episodes" / f"{task}_episode_{ep}"
        h5 = None
        if ok:
            (ep_dir / "hdf5_files").mkdir(parents=True, exist_ok=True)
            h5 = ep_dir / "hdf5_files" / f"{task}_ep{ep}.h5"
            h5.write_text(str(frames or 0), encoding="utf-8")  # 假 h5：内容就是帧数，由注入的计数器读
        if trace is not None:
            ep_dir.mkdir(parents=True, exist_ok=True)
            (ep_dir / "rng_trace.json").write_text(json.dumps({"calls": trace}), encoding="utf-8")
        results.append({"task": task, "episode": ep, "seed": 1000 + ep, "ok": ok, "role": role,
                        "error_type": error_type, "h5": str(h5) if h5 else None})

    for ep, frames in ((0, 700), (3, 800), (6, 1050)):
        add("PatternLock", ep, True, frames=frames)
    for ep, frames in ((0, 750), (3, 1051), (6, 900)):
        add("RouteStick", ep, True, frames=frames)
    add("VideoUnmaskSwap", 0, True)
    add("VideoUnmaskSwap", 3, False, error_type="BinCollisionError")
    add("VideoUnmaskSwap", 1, True, role="backfill")
    add("VideoUnmaskSwap", 6, True)
    for ep in (0, 3, 6):
        add("ButtonUnmaskSwap", ep, True)
    add("VideoRepick", 0, True)  # 规格里有 swap_pairs：6 块全参与
    add("VideoRepick", 3, True, trace=[  # V4 形态：只在 rng_trace 里有运行时记录
        {"path": "actions.swap_pairs.0", "drawn": {"initiator": "bin_1", "partner": "bin_2"}},
        {"path": "actions.swap_pairs.1", "drawn": {"initiator": "bin_2", "partner": "bin_1"}},
        {"path": "actions.swap_pairs.0.first_choice", "drawn": 4},  # 更深的子路径不算
    ])
    add("VideoRepick", 6, True, trace=[{"path": "actions.swap_pairs.0", "drawn": {"weird": 1}}])  # 认不出 ⇒ N/A
    for ep in (0, 3):
        add("InsertPeg", ep, False, error_type="PlannerExhausted")
    add("InsertPeg", 6, False, error_type="DatasetGenerationError")
    add("InsertPeg", 1, True, role="backfill")
    add("InsertPeg", 2, False, role="backfill", error_type="PlannerExhausted")
    add("InsertPeg", 4, False, role="backfill", error_type="PlannerExhausted")
    return (_write_jsonl(tmp_path / "drafts.jsonl", drafts), _write_jsonl(tmp_path / "specs.jsonl", specs),
            _write_jsonl(rollout / "results.jsonl", results) and rollout)


def _counter(path: Path) -> int:
    return int(Path(path).read_text(encoding="utf-8"))


def test_report_totals_and_line(tmp_path: Path) -> None:
    drafts, specs, rollout = _fixture(tmp_path)
    report = G.build_report(drafts, specs, rollout, frame_counter=_counter)
    t = report["totals"]
    assert t["tasks"] == 6
    assert t["draft_ok"] == 55 and t["draft_attempted"] == 56 and t["candidate_shortfall"] == 5
    assert t["draft_bin_collision"] == 1
    assert t["rollout_attempted"] == 22 and t["rollout_ok"] == 16
    assert t["backfilled"] == 2 and t["selected_shortfall"] == 1  # InsertPeg 目标 2（只有 5 条候选）只成 1
    assert t["demo_frames_checked"] == 6 and t["demo_frames_out_of_band"] == 2  # 700 与 1051
    assert t["outer_swap_checked"] == 4 and t["outer_swap_mismatch"] == 3  # VUS 除 ep0 外规划 2 ≠ 3
    assert t["bin_collision"] == 1
    assert t["vr_checked"] == 2 and t["vr_min_participants"] == 2
    assert report["line"] == ("V5_GENERATION=REPORT tasks=6 draft_ok=55 rollout_ok=16 backfilled=2 "
                              "selected_shortfall=1 demo_frames_out_of_band=2 outer_swap_mismatch=3 "
                              "bin_collision=1 vr_min_participants=2")
    env = report["per_env"]["InsertPeg"]
    assert env["selected_target"] == 2  # 只有 5 条候选 ⇒ index 0/3 两条被选中
    assert env["by_class"] == {"DatasetGenerationError": 1, "PlannerExhausted": 4}
    assert env["candidate_shortfall"] == 5
    vr = {r["episode"]: r for r in report["vr_participants"]}
    assert (vr[0]["participants"], vr[0]["source"]) == (6, "spec")
    assert (vr[3]["participants"], vr[3]["source"], vr[3]["n_pairs"]) == (2, "rng_trace", 2)
    assert vr[6]["participants"] is None
    bus = [r for r in report["outer_swap"] if r["task"] == "ButtonUnmaskSwap"]
    assert all(r["equal"] is None and "distractor_swap_pairs" in r["note"] for r in bus)


def test_report_na_when_fields_missing(tmp_path: Path) -> None:
    drafts = _write_jsonl(tmp_path / "drafts.jsonl", [
        {"record": "header", "tasks": ["VideoUnmaskSwap", "VideoRepick"]},
        {"record": "draft", "task": "VideoUnmaskSwap", "episode": 0, "attempt": 0, "reset_ok": True,
         "spec": {"objects": {"n_swaps": 4}}},
        {"record": "draft", "task": "VideoRepick", "episode": 0, "attempt": 0, "reset_ok": True, "spec": {}},
    ])
    rollout = tmp_path / "run1"
    _write_jsonl(rollout / "results.jsonl", [
        {"task": "VideoUnmaskSwap", "episode": 0, "ok": False, "role": "selected", "error_type": "X"},
        {"task": "VideoRepick", "episode": 0, "ok": True, "role": "selected", "h5": None},
    ])
    report = G.build_report(drafts, None, rollout, frame_counter=_counter)
    t = report["totals"]
    assert t["demo_frames_out_of_band"] == G.NA
    assert t["outer_swap_mismatch"] == G.NA
    assert t["vr_min_participants"] == G.NA
    assert "vr_min_participants=N/A" in report["line"]
    assert report["per_env"]["VideoUnmaskSwap"]["selected_target"] == 1  # 无 specs ⇒ 按 0/3/6 推算
    assert any("全部取不到" in w for w in report["warnings"])
    # markdown 与 JSON 都能写
    md = G.render_markdown(report)
    assert "## 逐环境" in md and "N/A" in md
    json.dumps(report, ensure_ascii=False)


def test_count_demo_frames_reads_real_h5(tmp_path: Path) -> None:
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "x.h5"
    with h5py.File(path, "w") as handle:
        episode = handle.create_group("episode_0")
        episode.create_group("setup")
        for index in range(12):
            info = episode.create_group(f"timestep_{index}").create_group("info")
            info.create_dataset("is_video_demo", data=bool(index < 7))
    assert G.count_demo_frames(path) == 7


def test_parse_pair_forms() -> None:
    assert G.parse_pair([1, 2]) == (1, 2)
    assert G.parse_pair({"initiator": "bin_3", "partner": "bin_0"}) == (3, 0)
    assert G.parse_pair({"pair": ["bin_4", 5], "u": 0.3}) == (4, 5)
    assert G.parse_pair({"first_choice": 0, "second_choice": 1}) is None
    assert G.parse_pair([1, 2, 3]) is None
    assert G.indexed_items({"1": "b", "0": "a", "10": "c"}) == ["a", "b", "c"]
    assert G.indexed_items({"x": 1}) is None


# ── 一条命令、参数化 ─────────────────────────────────────────────────────


def _pipe_args(**kw) -> argparse.Namespace:
    args = G.build_parser().parse_args(["pipeline", "--run-id", "v5-01", "--draw-workers", "6", "--workers", "8",
                                        "--draw-gpus", "0,1", "--rollout-gpu", "1"])
    for key, value in kw.items():
        setattr(args, key, value)
    return args


def test_pipeline_plan_paths_and_resume(tmp_path: Path) -> None:
    steps = G.plan_pipeline(_pipe_args(), root=tmp_path)
    assert [s["name"] for s in steps] == ["draw", "freeze", "run", "report"]
    draw, freeze, run, report = (" ".join(s["cmd"]) for s in steps)
    assert "v4_specs draw --run-id v5-01" in draw and "--workers 6" in draw and "--gpus 0,1" in draw
    assert "--sampling-config scripts/configs/newtask-v5/sampling_config.json" in draw
    assert "--out artifacts/newtask-v5/v5-01/draft/drafts.jsonl" in draw
    assert "--out scripts/configs/newtask-v5/v5-01/specs.jsonl" in freeze and "--select 0,3,6" in freeze
    assert "v4_rollout run" in run and "--workers 8" in run and "--gpu 1" in run
    assert "--output artifacts/newtask-v5/v5-01/rollout" in run and "--label run1" in run
    assert "--rollout artifacts/newtask-v5/v5-01/rollout/run1" in report
    assert not any(s["skip"] for s in steps)
    (tmp_path / "artifacts/newtask-v5/v5-01/draft").mkdir(parents=True)
    (tmp_path / "artifacts/newtask-v5/v5-01/draft/drafts.jsonl").write_text("{}\n")
    resumed = G.plan_pipeline(_pipe_args(resume=True), root=tmp_path)
    assert [s["skip"] for s in resumed] == [True, False, False, False]
    assert not any(s["skip"] for s in G.plan_pipeline(_pipe_args(), root=tmp_path))  # 不带 --resume 不跳


def test_rollout_passes_gpu_to_runner(tmp_path: Path, monkeypatch) -> None:
    from scripts.parity import v4_rollout as R

    captured = {}

    def fake_run(command, text, capture_output):
        captured["cmd"] = command
        results = Path(command[command.index("--results-json") + 1])
        results.write_text(json.dumps({"results": [{"task": "PatternLock", "episode": 0, "ok": True}]}))
        return argparse.Namespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    row = {"task": "PatternLock", "episode": 0, "seed": 1, "attempt": 0, "spec": {}, "spec_sha256": "s",
           "_role": "selected"}
    header = {"sampling_config": {"PatternLock": {}}}
    for gpu, expected in ((None, "0"), ("1", "1")):
        args = argparse.Namespace(official_root=str(tmp_path), workers=4, label="run1")
        if gpu is not None:
            args.gpu = gpu
        out = tmp_path / f"out_{expected}"
        R._run_batch([row], header, out, args, 0)
        cmd = captured["cmd"]
        assert cmd[cmd.index("--gpu") + 1] == expected and cmd[cmd.index("--workers") + 1] == "4"


def test_train_split_config_release_output_and_note(tmp_path: Path, capsys) -> None:
    from scripts.parity import train_split_config as C

    assert C.DEFAULT_OUTPUT == REPO_ROOT / "scripts" / "configs" / "newtask-v4" / "sampling_config.json"
    assert C.RELEASE_NOTES["newtask-v4"].startswith("V4 快照：原三档部分等于原值")
    out = tmp_path / "v5.json"
    assert C.main(["extract", "--release", "newtask-v5", "--env", "PatternLock", "--output", str(out)]) == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["note"] == C.RELEASE_NOTES["newtask-v5"] and document["tasks_ready"] == ["PatternLock"]
    v4 = tmp_path / "v4.json"
    assert C.main(["extract", "--env", "PatternLock", "--output", str(v4)]) == 0
    assert json.loads(v4.read_text(encoding="utf-8"))["note"] == C.RELEASE_NOTES["newtask-v4"]
