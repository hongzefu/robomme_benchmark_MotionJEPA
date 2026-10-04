"""C13-SG-MODEL-REPORT：四模型评估总报告的覆盖、成功率（按任务、按档）、第二档并入与预算判定。期望值手写。"""
from __future__ import annotations

import json

from tests._support.loaders import load_script

import sgx_report_fixtures as F


def M():
    return load_script("eval-official/model_eval_report.py")


def _v9(task, tier, seed, status, **kw):
    return {"task": task, "tier": tier, "seed": seed, "status": status, "canary": False, "infra": False, "late": False,
            "reset_calls": 2, "dataset": "test-hard", "max_steps": 1600, "strict_cap": True, **kw}


def _x0(task, ep, seed, status, **kw):
    return {**F.result_row(task=task, source_episode=ep, seed=seed, status=status), "reset_calls": 2, **kw}


def _sets(tmp_path):
    v9 = F.write_jsonl(tmp_path / "v9.jsonl", [
        _v9("A", "xhard1", 1, "success"), _v9("A", "xhard1", 2, "fail"), _v9("A", "xhard2", 3, "success"),
        _v9("B", "xhard1", 4, "timeout"),
        {**_v9("B", "xhard1", 5, "error"), "infra": True},  # 基础设施尝试：计入预算，不计覆盖
        _v9("B", "xhard1", 5, "success"),
    ])
    x0 = F.write_jsonl(tmp_path / "x0" / "shard-00.jsonl", [_x0("A", 3, 11, "success"), _x0("B", 3, 12, "fail")])
    return [
        {"policy": "mmesg", "variant": "ground-sg-oracle", "dataset": "test-hard", "side": "new", "site": "gl",
         "results": [str(v9)], "expect_total": 5},
        {"policy": "pp", "dataset": "test-hard0", "side": "orig", "results": [str(tmp_path / "x0" / "shard-*.jsonl")],
         "expect_total": 3},
    ]


def test_coverage_rates_by_task_and_tier(tmp_path):
    rep = M().build_report(_sets(tmp_path))
    a, b = rep["sets"]
    assert a["label"] == "mmesg-ground-sg-oracle/test-hard/new@gl"
    assert (a["covered"], a["missing"], a["success"], a["success_rate"], a["complete"]) == (5, 0, 3, 0.6, True)
    assert a["status"] == {"fail": 1, "success": 3, "timeout": 1}
    assert a["by_tier"] == {"xhard1": {"success": 2, "n": 4, "rate": 0.5}, "xhard2": {"success": 1, "n": 1, "rate": 1.0}}
    assert a["by_task"]["B"] == {"success": 1, "n": 2, "rate": 0.5}
    assert (a["attempts"], a["resets"]) == (6, 12)
    assert b["label"] == "pp/test-hard0/orig" and b["by_tier"] == {"xhard0": {"success": 1, "n": 2, "rate": 0.5}}
    assert (b["covered"], b["missing"], b["complete"]) == (2, 1, False)
    assert rep["verdict"] == "PARTIAL" and rep["incomplete"] == 1
    l1, l2 = M().verdict_lines(rep)
    assert l1 == "MODEL_EVAL_REPORT=PARTIAL sets=2 complete=1 incomplete=1 episodes=7 gate2=0"
    assert l2 == "EVAL_BUDGET=NA attempts=8 resets=16 source=results"


def test_duplicate_conflict_and_manifest(tmp_path):
    rows = [_v9("A", "xhard1", 1, "success"), _v9("A", "xhard1", 1, "fail"),
            _v9("A", "xhard1", 2, "fail"), _v9("A", "xhard1", 2, "fail"), _v9("Z", "xhard1", 9, "fail")]
    res = F.write_jsonl(tmp_path / "r.jsonl", rows)
    man = F.write_jsonl(tmp_path / "m.jsonl", [{"task": "A", "tier": "xhard1", "seed": s} for s in (1, 2, 3)])
    s = M().summarize_set({"policy": "mme", "dataset": "test-hard", "results": [str(res)], "manifest": str(man)})
    assert (s["conflicting"], s["duplicate"], s["missing"], s["extra"], s["complete"]) == (1, 1, 1, 1, False)


def test_gate2_merge_budget_from_ledger_and_cli(tmp_path, capsys):
    sets = _sets(tmp_path)
    sets[1]["expect_total"] = 2
    cfg = tmp_path / "sets.json"
    cfg.write_text(json.dumps({"sets": sets}), encoding="utf-8")
    g = tmp_path / "g.json"
    g.write_text(json.dumps({"summary": {"policy": "mmesg-oracle", "verdict": "INFO", "compared": 192,
                                         "same_terminal": 180, "identical_trace": 150, "first_episode_identical": 3,
                                         "server_epochs": 4, "missing_orig": []}}), encoding="utf-8")
    led = F.write_jsonl(tmp_path / "led" / "seat-01.jsonl", [
        {"kind": "budget"}, {"kind": "attempt_start"}, {"kind": "reset_claim"}, {"kind": "reset_claim"},
        {"kind": "attempt_start"}, {"kind": "attempt_end"}, {"kind": "accept"}])
    out, md = tmp_path / "o" / "r.json", tmp_path / "o" / "r.md"
    rc = M().main(["--sets", str(cfg), "--gate2", str(g), "--ledger", str(tmp_path / "led" / "*.jsonl"),
                   "--max-attempts", "2", "--max-resets", "2", "--out-json", str(out), "--out-md", str(md)])
    lines = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert lines == ["MODEL_EVAL_REPORT=PASS sets=2 complete=2 incomplete=0 episodes=7 gate2=1",
                     "EVAL_BUDGET=PASS attempts=2<=2 resets=2<=2 source=ledger"]
    text = md.read_text(encoding="utf-8")
    assert "| mmesg-oracle | gl | INFO | 192 | 180 | 150 | 3/4 |" in text
    assert json.loads(out.read_text(encoding="utf-8"))["lines"] == lines
    rc = M().main(["--sets", str(cfg), "--max-attempts", "7", "--max-resets", "100"])
    assert rc == 1
    assert capsys.readouterr().out.strip().splitlines()[-1] == "EVAL_BUDGET=FAIL attempts=8<=7 resets=16<=100 source=results"
