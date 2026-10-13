"""纯 CPU 对账、独立成功字段、分布与旧根防覆盖验证。"""

import json
from pathlib import Path
import pytest

from robomme_xhard.tools import swap_v2_report as report
from robomme_xhard.configs import SOURCE_DIFFICULTY


def manifest():
    return {"tasks": {task: [{"episode": i, "seed": 5000+i,
                              "source_difficulty": SOURCE_DIFFICULTY[task]}]
                      for i, task in enumerate(report.TASKS)}}


def records(m=None):
    result = []
    for task, episode, seed, level in report.expected_identities(m or manifest()):
        result.append(dict(task=task, mother_episode=episode, seed=seed,
                           difficulty=SOURCE_DIFFICULTY[task] if level == "mother" else level,
                           card_role="mother" if level == "mother" else "xhard",
                           ok=True, task_success=True, timestep_count=900,
                           swap_plan=None if level == "mother" else dict(
                               pairs=[[0, 1, .1, .01], [1, 0, .1, .01]], usage=[2, 2],
                               slot_pairs=[[0, 1], [1, 0]], spread_full=0, spread_prefix=0)))
    return result


def write(root, rows):
    root.mkdir()
    (root/"episode_results.jsonl").write_text("\n".join(json.dumps(row) for row in rows)+"\n")


def test_complete_180_identity_and_distribution(tmp_path):
    m = {"tasks": {task: [dict(episode=i, seed=5000+i,
                              source_difficulty=SOURCE_DIFFICULTY[task]) for i in range(10)]
                   for task in report.TASKS}}
    v1, v2 = tmp_path/"v1", tmp_path/"v2"
    write(v1, records(m)); write(v2, records(m))
    result = report.build_report(v1, v2, m)
    assert result["seeds"] == 30 and result["rows_count"] == 180
    assert result["audits"]["v2"]["summary"]["complete"]
    group = result["distributions"]["v2"]["VideoRepick/xhard20"]
    assert group == dict(spread_prefix={"0": 10}, spread_full={"0": 10},
                         net_identity_count=10, net_identity_denominator=10, net_identity_ratio=1.)
    assert result["rows"][0]["v2"]["net_identity"] is None
    assert "# 交换配对两轮对比" in report.markdown_report(result)


@pytest.mark.parametrize("problem", ["missing", "duplicate", "state", "identity", "malformed"])
def test_missing_duplicate_unknown_fail(tmp_path, problem):
    rows = records()
    if problem == "missing":
        rows.pop()
    elif problem == "duplicate":
        rows.append(dict(rows[0]))
    elif problem == "state":
        rows[0]["ok"] = "完成"
    elif problem == "identity":
        rows[0]["seed"] = 9999
    else:
        rows.append(None)
    root = tmp_path/"run"
    write(root, rows)
    audit, unique = report.reconcile(root, report.expected_identities(manifest()))
    s = audit["summary"]
    assert not s["complete"]
    assert s[{"missing": "missing", "duplicate": "dup", "state": "unknown",
              "identity": "unknown", "malformed": "unknown"}[problem]] > 0


def test_normal_failure_and_infra_separated(tmp_path):
    rows = records()
    rows[0].update(ok=False, task_success=False, failure_class="task",
                   error_type="SwapCollisionError", stage="graph",
                   rejection={"reason": "contact", "gap_m": -.01})
    rows[1].update(ok=False, task_success=False, failure_class="task",
                   error_type="SwapCollisionError", rejection={"reason": "uncertified"})
    rows[2].update(ok=False, task_success=False, failure_class="infra", error_type="BrokenProcessPool")
    rows[3].update(ok=True, task_success=False)
    root = tmp_path/"run"; write(root, rows)
    audit, _ = report.reconcile(root, report.expected_identities(manifest()))
    assert audit["summary"]["task_reject"] == 2
    assert audit["summary"]["infra"] == 2
    assert not audit["summary"]["complete"]


@pytest.mark.parametrize("record,state", [
    (dict(ok=True, task_success=False), "task_reject"),
    (dict(ok=True), "unknown"),
    (dict(ok=False, task_success=True), "unknown"),
    (dict(ok=False, task_success=False, failure_class="task", error_type="Mystery"), "unknown"),
    (dict(ok=False, task_success=False, failure_class="task", error_type="SceneGenerationError",
          error="按钮包络读取失败"), "infra"),
    (dict(ok=False, task_success=False, failure_class="task", error_type="SwapBindingError",
          detail={"check": "slot_binding"}), "task_reject"),
])
def test_state_contract(record, state):
    assert report.classify(record) == state


def test_duplicate_manifest_rejected():
    m = manifest()
    m["tasks"]["VideoRepick"].append(m["tasks"]["VideoRepick"][0])
    with pytest.raises(ValueError, match="重复"):
        report.expected_identities(m)


def test_old_output_and_symlink_rejected(tmp_path):
    old = tmp_path/"old"; old.mkdir()
    link = tmp_path/"link"; link.symlink_to(old, target_is_directory=True)
    with pytest.raises(ValueError, match="旧目录"):
        report.validate_outputs(old, link/"result.md", tmp_path/"result.json")
    with pytest.raises(ValueError, match="旧目录"):
        report.validate_outputs(old, old/".."/"old"/"result.md", tmp_path/"result.json")
    existing = tmp_path/"existing"; existing.write_text("旧证据")
    with pytest.raises(ValueError, match="已存在"):
        report.validate_outputs(old, existing, tmp_path/"result.json")
    assert existing.read_text() == "旧证据"
    with pytest.raises(ValueError, match="不同"):
        report.validate_outputs(old, tmp_path/"same", tmp_path/"same")


def test_cli_reports_incomplete_and_no_overwrite(tmp_path, capsys):
    v1, v2 = tmp_path/"v1", tmp_path/"v2"
    write(v1, records()); write(v2, records()[:-1])
    seeds = tmp_path/"seeds.json"; seeds.write_text(json.dumps(manifest()))
    md, js = tmp_path/"report/out.md", tmp_path/"report/out.json"
    argv = ["--v1", str(v1), "--v2", str(v2), "--seeds", str(seeds),
            "--out-md", str(md), "--out-json", str(js)]
    assert report.main(argv) == 2
    output = capsys.readouterr().out
    assert "XHARD_FULL_DERIVE=INCOMPLETE" in output and "missing=1" in output
    assert "REPORT_V1V2=FAIL" in output
    assert json.loads(js.read_text())["audits"]["v2"]["summary"]["missing"] == 1
    before = js.read_bytes()
    with pytest.raises(ValueError, match="已存在"):
        report.main(argv)
    assert js.read_bytes() == before


def test_directory_only_ledger_and_mismatched_directory(tmp_path):
    rows = records()
    root = tmp_path/"run"; root.mkdir()
    for row in rows:
        level = "mother" if row["card_role"] == "mother" else row["difficulty"]
        path = root/level/"episode_results.jsonl"
        path.parent.mkdir(exist_ok=True)
        with path.open("a") as out:
            out.write(json.dumps(row)+"\n")
    audit, _ = report.reconcile(root, report.expected_identities(manifest()))
    assert audit["summary"]["complete"]
    wrong = dict(rows[1]); wrong["difficulty"] = "xhard20"
    with (root/"xhard12"/"episode_results.jsonl").open("a") as out:
        out.write(json.dumps(wrong)+"\n")
    audit, _ = report.reconcile(root, report.expected_identities(manifest()))
    assert audit["summary"]["unknown"] == 1

