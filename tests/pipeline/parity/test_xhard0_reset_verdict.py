"""C15 ``hard_regression.py xhard0-reset-parity`` 的判定层（XHARD0_RESET_PARITY／XHARD0_DEMO_DIFF）。

GPU 探针 ``_run_probe`` 换成返回手写探针结果的替身（monkeypatch 模块属性，不注入 sys.modules）；真实的
``cmd_xhard0_reset_parity`` 逐字段比、仅改名判定、合并上一轮、写报告，再由真实 ``_xhard0_reset_verdict`` 出判定行。
每任务局数取一个小的测试值（不是业务常量）；任务清单取生产的 16 任务规范序。
"""
from __future__ import annotations

import copy
import json
import types

import pytest

import parity_fixtures as F

PER_TASK = 2


@pytest.fixture(scope="module")
def R():
    return F.hard_regression()


@pytest.fixture(scope="module")
def tasks():
    return tuple(F.hard_parity().hard_specs_light().ALL_TASKS)


def probe_row(side: str, task: str, ep: int, idx: int) -> dict:
    seed = 500000 + 100 * idx
    return {"episode": ep, "seed": seed, "difficulty": "hard" if side == "official" else "xhard0",
            "make_kwargs": {"env_id": task, "seed": seed}, "wrapper_chain": ["A", "B", task],
            "pre_demo_state": {"actors": {"cube_0": [0.1, 0.2], "button_left": [0.3, 0.4]},
                               "articulations": {"panda": [1.0]}},
            "task_goal": [f"do {task}"], "choices": [], "demo_frames": 5, "demo_digest": "d", "post_state": "p"}


def run(R, tasks, tmp_path, monkeypatch, capsys, mutate=None, only_tasks=None, merge_with=None):
    """mutate(side, task, idx, row) 就地改替身返回值。返回 (退出码, 判定行, 报告行)。"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest = {"rows": [{"task": t, "episode": 3 + 4 * i} for t in tasks for i in range(PER_TASK)]}
    (tmp_path / "m.json").write_text(json.dumps(manifest))

    def fake_probe(side, task, src, eps, gpu):
        out = []
        for idx, ep in enumerate(eps):
            row = probe_row(side, task, ep, idx)
            if mutate:
                mutate(side, task, idx, row)
            out.append(row)
        return out

    monkeypatch.setattr(R, "_run_probe", fake_probe)
    monkeypatch.setattr(R, "_hard_specs", lambda: types.SimpleNamespace(ALL_TASKS=tasks, XHARD0_PER_TASK=PER_TASK))
    monkeypatch.setattr(R, "_require_xhard0_in_test_hard", lambda hs: None)
    args = types.SimpleNamespace(manifest=str(tmp_path / "m.json"), out=str(tmp_path / "out"), src_root=str(tmp_path),
                                 gpu="0", tasks=",".join(only_tasks) if only_tasks else None,
                                 merge_with=merge_with, report_name="r.jsonl")
    rc = R.cmd_xhard0_reset_parity(args)
    out = capsys.readouterr().out.strip().splitlines()
    report = [json.loads(t) for t in (tmp_path / "out" / "r.jsonl").read_text().splitlines()]
    return rc, out, report


def verdict_line(out):
    return next(t for t in out if t.startswith("XHARD0_RESET_PARITY="))


def test_两侧逐位相同_PASS(R, tasks, tmp_path, monkeypatch, capsys):
    rc, out, report = run(R, tasks, tmp_path, monkeypatch, capsys)
    n = len(tasks) * PER_TASK
    assert rc == 0 and len(report) == n
    line = verdict_line(out)
    assert line.startswith("XHARD0_RESET_PARITY=PASS ") and line.endswith(f" compared={n} det_diff=0 name_only=0 first_det_diff=-")
    assert out[-1] == f"XHARD0_DEMO_DIFF=INFO frames_equal={n} max_frame_diff=0 demo_equal={n} post_equal={n}"
    assert sum(t.startswith("XHARD0_RESET_TASK ") for t in out) == len(tasks)


@pytest.mark.parametrize("field,value", [
    ("seed", 1), ("make_kwargs", {"env_id": "X"}), ("wrapper_chain", ["A"]), ("task_goal", ["other"]),
    ("choices", ["a"]), ("pre_demo_state", {"actors": {"cube_0": [9.0, 0.2], "button_left": [0.3, 0.4]},
                                            "articulations": {"panda": [1.0]}}),
])
def test_确定性层任一字段不同即FAIL(R, tasks, tmp_path, monkeypatch, capsys, field, value):
    target = tasks[3]

    def mutate(side, task, idx, row):
        if side == "hard" and task == target and idx == 1:
            row[field] = value
    rc, out, report = run(R, tasks, tmp_path, monkeypatch, capsys, mutate)
    line = verdict_line(out)
    assert rc == 1 and line.startswith("XHARD0_RESET_PARITY=FAIL ") and " det_diff=1 " in line
    assert f"first_det_diff={target}/ep7:['{field}']" in line
    assert sum(bool(r["det_bad"]) for r in report) == 1


def test_官方侧难度名不是hard也算不一致(R, tasks, tmp_path, monkeypatch, capsys):
    def mutate(side, task, idx, row):
        if side == "official" and task == tasks[0] and idx == 0:
            row["difficulty"] = "medium"
    rc, out, _ = run(R, tasks, tmp_path, monkeypatch, capsys, mutate)
    assert rc == 1 and "['difficulty']" in verdict_line(out)


def test_演示前状态只是实体改名_记name_only不计差异(R, tasks, tmp_path, monkeypatch, capsys):
    target = tasks[5]

    def mutate(side, task, idx, row):
        if side == "hard" and task == target:
            actors = row["pre_demo_state"]["actors"]
            actors["button_right"] = actors.pop("button_left")
    rc, out, report = run(R, tasks, tmp_path, monkeypatch, capsys, mutate)
    line = verdict_line(out)
    assert rc == 0 and f" name_only={PER_TASK} " in line and f"name_only_tasks=['{target}']" in line
    assert all(r["det_bad"] == [] for r in report)


def test_现状记录_同键互换取值也被当成仅改名(R, tasks, tmp_path, monkeypatch, capsys):
    """现状记录（已报告为生产风险）：两个同形 actor 键集合不变、互换取值时，``_name_agnostic`` 的有序多重集相同，
    本子命令判 name_only、不计 det_diff；``env-digest-compare`` 在同一情形会判真差异（见 test_env_digest）。"""
    def mutate(side, task, idx, row):
        if side == "hard" and task == tasks[0] and idx == 0:
            actors = row["pre_demo_state"]["actors"]
            actors["cube_0"], actors["button_left"] = actors["button_left"], actors["cube_0"]
    rc, out, report = run(R, tasks, tmp_path, monkeypatch, capsys, mutate)
    assert rc == 0 and " name_only=1 " in verdict_line(out)


def test_演示层差异只报告(R, tasks, tmp_path, monkeypatch, capsys):
    def mutate(side, task, idx, row):
        if side == "hard" and task == tasks[1] and idx == 0:
            row.update(demo_frames=8, demo_digest="x", post_state="y")
    rc, out, _ = run(R, tasks, tmp_path, monkeypatch, capsys, mutate)
    n = len(tasks) * PER_TASK
    assert rc == 0
    assert out[-1] == (f"XHARD0_DEMO_DIFF=INFO frames_equal={n - 1} max_frame_diff=3 demo_equal={n - 1} "
                       f"post_equal={n - 1}")


def test_局数不齐即FAIL_合并上一轮补齐后PASS(R, tasks, tmp_path, monkeypatch, capsys):
    rc, out, report = run(R, tasks, tmp_path / "a", monkeypatch, capsys, only_tasks=tasks[:2])
    assert rc == 1 and f"compared={2 * PER_TASK} " in verdict_line(out)
    full_rc, _out, full = run(R, tasks, tmp_path / "b", monkeypatch, capsys)
    assert full_rc == 0
    prev = tmp_path / "prev.jsonl"
    stale = copy.deepcopy(full)
    for r in stale:
        if r["task"] == tasks[0]:
            r["det_bad"] = ["seed"]  # 上一轮这个任务坏了；本轮重跑它，应整段替换
    prev.write_text("".join(json.dumps(r) + "\n" for r in stale))
    rc, out, report = run(R, tasks, tmp_path / "c", monkeypatch, capsys, only_tasks=tasks[:1], merge_with=str(prev))
    assert rc == 0 and len(report) == len(tasks) * PER_TASK and " det_diff=0 " in verdict_line(out)


def test_判定函数_局数多一局也FAIL(R, tasks):
    rows = [{"task": t, "source_episode": i, "det_bad": [], "name_only": False, "demo_frames": [1, 1],
             "demo_equal": True, "post_equal": True} for t in tasks for i in range(PER_TASK)]
    assert R._xhard0_reset_verdict(rows, PER_TASK) == 0
    assert R._xhard0_reset_verdict(rows + [dict(rows[0])], PER_TASK) == 1
    assert R._xhard0_reset_verdict(rows[:-1], PER_TASK) == 1
    assert R._xhard0_reset_verdict([], PER_TASK) == 1
