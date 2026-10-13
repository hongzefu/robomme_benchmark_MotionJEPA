"""纯 CPU 对账、独立成功字段、分布与旧根防覆盖验证。"""

import json
from copy import deepcopy
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
                   error_type="SwapCollisionError", rejection={"reason": "uncertified", "stage": "geometry"})
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


@pytest.mark.parametrize("stage,detail", [("graph", "达到 MAX_DEPTH"),
                                          ("sweep", "达到 MAX_INTERVALS"),
                                          ("segment_start", "四元数退化")])
def test_numerical_uncertified_is_normal_task_rejection(stage, detail):
    record = dict(ok=False, task_success=False, failure_class="task",
                  error_type="SwapCollisionError", stage=stage,
                  rejection=dict(reason="uncertified", stage=stage, detail=detail))
    assert report.classify(record) == "task_reject"


@pytest.mark.parametrize("prefix", ["孤立槽=[0]; 原始边证据=", "可行槽对不足=2/3; 原始边证据="])
@pytest.mark.parametrize("stage,expected", [("graph", "task_reject"), ("geometry", "infra")])
def test_aggregated_graph_reason_reads_original_stage(stage, expected, prefix):
    original = dict(reason="uncertified", stage=stage, detail="原始拒绝")
    detail = prefix + json.dumps({"rejected_edges": {"0-1": original}})
    record = dict(ok=False, task_success=False, failure_class="task",
                  error_type="SwapCollisionError", stage="graph",
                  rejection=dict(reason="uncertified", stage="graph", detail=detail))
    assert report.classify(record) == expected


def test_runtime_interface_uncertified_still_infra():
    record = dict(ok=False, task_success=False, failure_class="task",
                  error_type="SwapCollisionError", stage="substep_before",
                  detail={"check": "uncertified", "detail": {"exception_type": "AttributeError"}})
    assert report.classify(record) == "infra"


def test_aggregated_malformed_evidence_is_infra():
    record = dict(ok=False, task_success=False, failure_class="task", error_type="SwapCollisionError",
                  rejection={"reason": "uncertified", "stage": "graph", "detail": "原始边证据=损坏"})
    assert report.classify(record) == "infra"


def graph_plan(edges):
    """专供 v3 的矩阵夹具，旧版 records 无 graph 的语义保持原样。"""
    adj = [[False]*4 for _ in range(4)]
    for a, b in edges:
        adj[a][b] = adj[b][a] = True
    a, b = edges[0]
    usage = [int(i in (a, b)) for i in range(4)]
    return dict(pairs=[[a, b, .1, .01]], slot_pairs=[[a, b]], usage=usage,
                initiator_usage=[int(i == a) for i in range(4)],
                partner_usage=[int(i == b) for i in range(4)], initial_gap=.01,
                s_max=11, spread_full=1, spread_prefix=1, tries=1,
                slots=[[0., 0.], [0., .1], [.1, .1], [.1, 0.]],
                graph=dict(adj=adj, gaps={"0-1": 0.0}))


def v3_fixture():
    m = {"tasks": {task: [] for task in report.TASKS}}
    m["tasks"]["VideoUnmaskSwap"] = [dict(episode=i, seed=5000+i,
                                           source_difficulty=SOURCE_DIFFICULTY["VideoUnmaskSwap"])
                                     for i in range(2)]
    old = records(m)
    for row in old:
        if row["card_role"] == "xhard":
            edges = [(0, 3), (1, 2)] if row["seed"] == 5000 else [(0, 1), (1, 2), (2, 3)]
            row["swap_plan"] = graph_plan(edges)
    new = deepcopy(old)
    for row in new:
        if row["card_role"] == "xhard":
            if row["seed"] == 5000:
                reject_graph(row)
            else:
                row["swap_plan"]["graph"]["feasible_edges"] = report._plan_edges(row["swap_plan"])
    return m, old, new


def reject_graph(row, kind="min_pair_kinds"):
    prefix = "可行槽对不足=2/3; 原始边证据=" if kind == "min_pair_kinds" else "孤立槽=[3]; 原始边证据="
    payload = dict(rejected_edges={}, gaps={}, feasible_edges=[[0, 3], [1, 2]])
    row.update(ok=False, task_success=False, failure_class="task", error_type="SwapCollisionError",
               stage="graph", detail=None, swap_plan=None,
               rejection=dict(reason="contact", stage="graph", detail=prefix+json.dumps(payload)))


def runtime_reject(row, failure="task", stage="segment_start"):
    row.update(ok=False, task_success=False, failure_class=failure,
               error_type="SwapCollisionError", stage=stage,
               rejection=dict(reason="contact", stage=stage, gap_m=-.01))


def fixture_report(tmp_path, m, old, new):
    write(tmp_path/"old", old)
    write(tmp_path/"new", new)
    return report.build_report(tmp_path/"old", tmp_path/"new", m)


def fixture_cli(tmp_path, m):
    seeds = tmp_path/"seeds.json"
    seeds.write_text(json.dumps(m))
    return report.main(["--v1", str(tmp_path/"old"), "--v2", str(tmp_path/"new"),
                        "--seeds", str(seeds), "--out-md", str(tmp_path/"result.md"),
                        "--out-json", str(tmp_path/"result.json")])


def test_graph_reject_kind_two_markers():
    row = {}
    for kind in ("isolated_slots", "min_pair_kinds"):
        reject_graph(row, kind)
        assert report.graph_reject_kind(row) == kind
        assert report.plan_metrics(row)["graph_reject_kind"] == kind
        row["stage"] = "segment_start"
        assert report.graph_reject_kind(row) is None
    for rejection in (None, {}, {"detail": None}, {"detail": []}):
        assert report.graph_reject_kind(dict(stage="graph", rejection=rejection)) is None
    assert report.graph_reject_kind(dict(stage="graph", detail="孤立槽=[0]")) is None


def test_kinds_gate_expected_vs_actual(tmp_path, capsys):
    m, old, new = v3_fixture()
    result = fixture_report(tmp_path, m, old, new)
    assert result["kinds_gate"] == dict(seeds=2, **{"pass": 1}, reject_kinds=1,
                                       reject_isolated=0, runtime_fail=0, mixed=0, expected_reject_kinds=1)
    assert result["identity_match"]["mismatches"] == 0
    assert result["plan_unchanged"]["cards"] == result["plan_unchanged"]["expected"] == 5
    assert fixture_cli(tmp_path, m) == 0
    output = capsys.readouterr().out
    assert "SWAP_V3_KINDS_GATE=PASS" in output and "V3_IDENTITY_MATCH=PASS" in output
    assert "PLAN_UNCHANGED=PASS cards=5 expected=5 missing=0 diffs=0 float_tol=1e-9" in output
    assert "## 闸门" in report.markdown_report(result) and "feasible_edges" in report.markdown_report(result)
    failed = tmp_path/"failed"; failed.mkdir()
    all_ok = deepcopy(old)
    for row in all_ok:
        if isinstance(row["swap_plan"], dict):
            row["swap_plan"]["graph"]["feasible_edges"] = report._plan_edges(row["swap_plan"])
    result = fixture_report(failed, m, old, all_ok)
    assert result["kinds_gate"]["reject_kinds"] == 0
    assert result["kinds_gate"]["expected_reject_kinds"] == 1
    assert fixture_cli(failed, m) == 2
    assert "SWAP_V3_KINDS_GATE=FAIL" in capsys.readouterr().out


def test_plan_unchanged_ignores_feasible_edges_key(tmp_path):
    m, old, new = v3_fixture()
    # 不成功但带完整规划的运行期卡也必须进入固定预期集合。
    runtime_reject(old[-1]); runtime_reject(new[-1])
    result = fixture_report(tmp_path, m, old, new)
    assert result["plan_unchanged"]["cards"] == 5
    assert result["plan_unchanged"]["diffs"] == 0
    new[-1]["swap_plan"]["slot_pairs"][0][0] = 3
    changed = tmp_path/"changed"; changed.mkdir()
    assert fixture_report(changed, m, old, new)["plan_unchanged"]["diffs"] == 1


def test_identity_match_detects_swap(tmp_path, capsys):
    m, old, new = v3_fixture()
    for row in old:
        if row["card_role"] == "xhard" and row["seed"] == 5001:
            row["swap_plan"] = graph_plan([(0, 1), (0, 2), (0, 3), (1, 2), (2, 3)])
    new = deepcopy(old)
    for row in new:
        if row["card_role"] == "xhard" and row["seed"] == 5001:
            reject_graph(row)
        elif row["card_role"] == "xhard":
            row["swap_plan"]["graph"]["feasible_edges"] = report._plan_edges(row["swap_plan"])
    result = fixture_report(tmp_path, m, old, new)
    gate = result["kinds_gate"]
    assert gate["reject_kinds"] == gate["expected_reject_kinds"] == 1
    assert gate["mixed"] == 0 and result["rows_count"] == 12
    assert result["identity_match"]["mismatches"] == 10
    assert len(result["identity_match"]["details"]) == 10
    assert fixture_cli(tmp_path, m) == 2
    output = capsys.readouterr().out
    assert "SWAP_V3_KINDS_GATE=PASS" in output and "V3_IDENTITY_MATCH=FAIL cards=12 mismatches=10" in output


@pytest.mark.parametrize("absent", ["record", "plan"])
def test_plan_unchanged_missing_card_fails(tmp_path, capsys, absent):
    m, old, new = v3_fixture()
    if absent == "record":
        new.pop()
    else:
        new[-1]["swap_plan"] = None
    result = fixture_report(tmp_path, m, old, new)
    plan = result["plan_unchanged"]
    assert plan["missing"] == 1 and plan["cards"] == plan["expected"]-1
    assert fixture_cli(tmp_path, m) == 2
    assert "PLAN_UNCHANGED=FAIL cards=4 expected=5 missing=1" in capsys.readouterr().out


@pytest.mark.parametrize("mode,wanted", [("mixed", "mixed"), ("runtime", "runtime_fail"),
                                        ("infra", "mixed"), ("other_stage", "mixed"),
                                        ("isolated", "reject_isolated")])
def test_kinds_gate_mixed_and_runtime_definition(tmp_path, capsys, mode, wanted):
    m, old, new = v3_fixture()
    rows = [row for row in new if row["seed"] == 5001 and row["card_role"] == "xhard"]
    for row in rows:
        if mode == "mixed":
            if row["difficulty"] in report.DIFFICULTIES[-2:]:
                reject_graph(row)
        elif mode == "isolated":
            reject_graph(row, "isolated_slots")
        else:
            runtime_reject(row, failure="infra" if mode == "infra" else "task",
                           stage="other" if mode == "other_stage" else "segment_start")
    result = fixture_report(tmp_path, m, old, new)
    gate = result["kinds_gate"]
    assert gate[wanted] == 1 and gate["reject_kinds"] == 1
    assert sum(gate[key] for key in ("pass", "reject_kinds", "reject_isolated", "runtime_fail", "mixed")) == 2
    if wanted == "mixed":
        assert gate["runtime_fail"] == 0
        assert fixture_cli(tmp_path, m) == 2
        assert "SWAP_V3_KINDS_GATE=FAIL" in capsys.readouterr().out


@pytest.mark.parametrize("delta,diffs", [(5e-10, 0), (2e-9, 1)])
def test_plan_unchanged_float_tolerance(tmp_path, delta, diffs):
    m, old, new = v3_fixture()
    new[-1]["swap_plan"]["graph"]["gaps"]["0-1"] += delta
    result = fixture_report(tmp_path, m, old, new)
    assert result["plan_unchanged"]["diffs"] == diffs
    assert result["plan_unchanged"]["max_float_delta"] == delta
    new[-1]["swap_plan"]["usage"][0] += 1
    integer = tmp_path/"integer"; integer.mkdir()
    assert fixture_report(integer, m, old, new)["plan_unchanged"]["diffs"] == 1


@pytest.mark.parametrize("fault", ["missing_edges", "wrong_edges", "float_integer", "bool_integer", "extra_key"])
def test_plan_unchanged_structure_and_edge_evidence(tmp_path, fault):
    m, old, new = v3_fixture()
    plan = new[-1]["swap_plan"]
    if fault == "missing_edges":
        del plan["graph"]["feasible_edges"]
    elif fault == "wrong_edges":
        plan["graph"]["feasible_edges"][0] = [0, 3]
    elif fault == "float_integer":
        plan["usage"][0] = float(plan["usage"][0])
    elif fault == "bool_integer":
        plan["usage"][0] = bool(plan["usage"][0])
    else:
        plan["graph"]["unknown"] = 1
    assert fixture_report(tmp_path, m, old, new)["plan_unchanged"]["diffs"] == 1


def test_v1_graph_unavailable_fails_new_gate(tmp_path, capsys):
    m = manifest()
    result = fixture_report(tmp_path, m, records(), records())
    assert result["rows"][1]["v1"]["feasible_edges"] is None
    assert result["kinds_gate"]["expected_reject_kinds"] is None
    assert fixture_cli(tmp_path, m) == 2
    output = capsys.readouterr().out
    assert "REPORT_V1V2=PASS" in output
    assert "SWAP_V3_KINDS_GATE=FAIL" in output and "expected_reject_kinds=NA" in output


def test_plan_metrics_graph_rejected_edges():
    row = {}
    reject_graph(row)
    assert report.plan_metrics(row)["feasible_edges"] == 2
    row["rejection"]["detail"] = "孤立槽=[3]; 原始边证据=" + json.dumps(dict(
        gaps={"0-1": None, "0-2": .01, "0-3": -.01, "1-2": .02, "1-3": -.02, "2-3": -.03},
        rejected_edges={"0-1": {}, "0-3": {}, "1-3": {}, "2-3": {}}))
    assert report.plan_metrics(row)["feasible_edges"] == 2
    row["rejection"]["detail"] = "孤立槽=[3]; 原始边证据=损坏"
    assert report.plan_metrics(row)["feasible_edges"] is None


@pytest.mark.parametrize("field,value", [("stage", "sweep"), ("error_type", "SwapCollisionError")])
def test_identity_retained_success_fields_match(tmp_path, field, value):
    m, old, new = v3_fixture()
    new[-1][field] = value
    result = fixture_report(tmp_path, m, old, new)
    assert result["identity_match"]["mismatches"] == 1
    mismatch = result["identity_match"]["details"][0]
    assert mismatch["expected"][field] is None and mismatch["actual"][field] == value


def test_complete_v3_180_cards_and_105_fixed_plans(tmp_path, capsys):
    """与计划同规模的合成账本验证五类总数，包含五张运行期失败规划。"""
    m = {"tasks": {task: [dict(episode=i, seed=5000+i, source_difficulty=SOURCE_DIFFICULTY[task])
                          for i in range(10)] for task in report.TASKS}}
    old = records(m)
    low = {("VideoUnmaskSwap", 0), ("VideoUnmaskSwap", 1), ("ButtonUnmaskSwap", 0),
           ("VideoRepick", 0), ("VideoRepick", 1), ("VideoRepick", 2)}
    isolated = {("ButtonUnmaskSwap", 1), ("VideoRepick", 3), ("VideoRepick", 4)}
    runtime = ("VideoRepick", 5)
    for row in old:
        if row["card_role"] != "xhard":
            continue
        key = (row["task"], row["mother_episode"])
        if key in isolated:
            reject_graph(row, "isolated_slots")
            continue
        row["swap_plan"] = graph_plan([(0, 3), (1, 2)] if key in low else [(0, 1), (1, 2), (2, 3)])
        if key == runtime:
            runtime_reject(row)
    new = deepcopy(old)
    for row in new:
        if row["card_role"] != "xhard" or row["swap_plan"] is None:
            continue
        if (row["task"], row["mother_episode"]) in low:
            reject_graph(row)
        else:
            row["swap_plan"]["graph"]["feasible_edges"] = report._plan_edges(row["swap_plan"])
    result = fixture_report(tmp_path, m, old, new)
    assert result["kinds_gate"] == dict(seeds=30, **{"pass": 20}, reject_kinds=6,
                                       reject_isolated=3, runtime_fail=1, mixed=0, expected_reject_kinds=6)
    assert result["identity_match"]["cards"] == 180 and result["identity_match"]["mismatches"] == 0
    assert result["plan_unchanged"]["expected"] == result["plan_unchanged"]["cards"] == 105
    assert fixture_cli(tmp_path, m) == 0
    output = capsys.readouterr().out
    assert "ok=130 task_reject=50 infra=0" in output
    assert "V3_IDENTITY_MATCH=PASS cards=180 mismatches=0" in output
    assert "PLAN_UNCHANGED=PASS cards=105 expected=105 missing=0 diffs=0" in output
