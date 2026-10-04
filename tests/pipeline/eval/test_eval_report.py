"""C13 评估汇总 ``eval_report``（进程内调用真实 ``main``／``build_report``）：分母固定、唯一权威终态、各判定器的负例，
以及 V9 合并复用的 800 局总表逐格对 ``V9_CELLS``（F-3）。

运行根里的结果行与账本行都由本文件按生产格式手写（每条用例的期望直接写在用例里）；贯通生产者的用例见
``test_seat_runner_e2e.py``。
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

import eval_fakes as F

POL = "mme"


def _ident(i: int, task: str = "TaskA", tier: str = "xhard1") -> dict:
    seed = 7_000_000 + i
    return {"task": task, "tier": tier, "seed": seed, "candidate": i, "builder_episode": i, "source_episode": None,
            "spec_sha256": hashlib.sha256(f"{task}{tier}{seed}".encode()).hexdigest(), "effective_max_steps": 10,
            "key": f"{task}_{tier}_{seed}"}


class Stage:
    """按生产布局手写一个席位的结果行、账本行与录像目录。"""

    def __init__(self, root: Path, policy: str = POL, seat: str = "s00"):
        self.root, self.policy = Path(root), policy
        self.dir = self.root / seat / policy
        self.dir.mkdir(parents=True, exist_ok=True)

    def _append(self, name: str, row: dict):
        with open(self.dir / name, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def result(self, ident: dict, aid: str, no: int, status: str, *, infra: bool = False, media: bool = True,
               **kw) -> dict:
        row = {"v8": True, "key": ident["key"], "task": ident["task"], "tier": ident["tier"], "seed": ident["seed"],
               "candidate": ident["candidate"], "spec_sha256": ident["spec_sha256"],
               "identity": {k: ident[k] for k in ("tier", "seed", "candidate", "spec_sha256")},
               "policy": self.policy, "attempt_id": aid, "attempt_no": no, "status": status,
               "task_success": status == "success", "infra": infra, "exec_steps": 5,
               "rec_dir": str(self.dir / "rec" / f"{ident['key']}.a{no}"), "recorder_verify": "PASS"}
        row.update(kw)
        self._append("results.jsonl", row)
        if media:
            d = self.dir / "rec" / f"{ident['key']}.a{no}"
            d.mkdir(parents=True, exist_ok=True)
            for f in ("front.mkv", "wrist.mkv", "summary.json"):
                (d / f).write_text("x", encoding="utf-8")
        return row

    def ledger(self, kind: str, ident_or_key, aid: str, **kw):
        key = ident_or_key if isinstance(ident_or_key, str) else ident_or_key["key"]
        row = {"kind": kind, "key": key, "attempt_id": aid, "policy": self.policy, **kw}
        if kind == "accept":
            row.setdefault("accepted_attempt_id", aid)
        self._append(f"{self.policy}.ledger.jsonl", row)

    def accepted(self, ident: dict, aid: str, status: str, no: int = 1, **kw) -> dict:
        self.ledger("attempt_start", ident, aid, attempt_no=no)
        row = self.result(ident, aid, no, status, **kw)
        self.ledger("attempt_end", ident, aid, attempt_no=no, status=status)
        self.ledger("accept", ident, aid, status=status)
        return row


def _report(tmp_path, capsys, idents, *extra, manifest_extra=None):
    manifest = F.write_manifest(tmp_path / "m" / "manifest.json", idents, **(manifest_extra or {}))
    return F.run_report(capsys, manifest, tmp_path / "stage", [POL], tmp_path / "out",
                        "--expect-total", str(len(idents)), *extra)


def test_clean_report_rates_and_outcome_keys(tmp_path, capsys):
    a, b, c = _ident(0), _ident(1), _ident(2, task="TaskB")
    st = Stage(tmp_path / "stage")
    st.accepted(a, "a1", "success")
    st.accepted(b, "b1", "timeout")
    st.accepted(c, "c1", "success")
    rc, lines, rep = _report(tmp_path, capsys, [a, b, c])
    assert rc == 0
    assert F.verdict(lines, "V8_EVAL_COVERAGE")[""] == "PASS" and F.verdict(lines, "V8_EVAL_REPORT")[""] == "PASS"
    pp = rep["per_policy"][POL]
    assert pp["outcomes"] == {"success": 2, "fail": 0, "timeout": 1, "error": 0, "missing": 0, "conflict": 0}
    assert pp["micro_success_rate"] == pytest.approx(2 / 3)
    assert pp["task_macro_success_rate"] == pytest.approx((1 / 2 + 1 / 1) / 2)  # TaskA 1/2、TaskB 1/1
    assert pp["cells"]["TaskA@xhard1"]["denominator"] == 2 and pp["cells"]["TaskB@xhard1"]["success"] == 1


def test_denominator_is_manifest_not_result_rows(tmp_path, capsys):
    """4 条结果行、3 个身份：分母 3；没有任何尝试的身份记 missing；infra 废弃尝试单列不入分。"""
    a, b, c = _ident(0), _ident(1), _ident(2)
    st = Stage(tmp_path / "stage")
    st.ledger("attempt_start", a, "a1", attempt_no=1)
    st.result(a, "a1", 1, "error", infra=True)
    st.ledger("attempt_end", a, "a1", attempt_no=1, status="error")
    st.accepted(a, "a2", "success", no=2)
    st.ledger("attempt_start", b, "b1", attempt_no=1)
    st.result(b, "b1", 1, "error", infra=True)
    st.accepted(b, "b2", "fail", no=2)
    rc, lines, rep = _report(tmp_path, capsys, [a, b, c])
    pp = rep["per_policy"][POL]
    assert pp["denominator"] == 3 and sum(pp["outcomes"].values()) == 3
    assert pp["outcomes"]["missing"] == 1 and len(pp["abandoned"]) == 2
    cov = F.verdict(lines, "V8_EVAL_COVERAGE")
    assert cov[""] == "FAIL" and cov["missing"] == "1"
    assert pp["cells"]["TaskA@xhard1"]["denominator"] == 3
    assert rc == 1


def test_partial_does_not_fail_on_missing(tmp_path, capsys):
    a, b = _ident(0), _ident(1)
    Stage(tmp_path / "stage").accepted(a, "a1", "success")
    rc, lines, rep = _report(tmp_path, capsys, [a, b], "--partial")
    cov = F.verdict(lines, "V8_EVAL_COVERAGE")
    assert cov[""] == "PASS" and cov["missing"] == "0"
    assert rep["per_policy"][POL]["outcomes"]["missing"] == 1  # 结局表照实记缺失
    assert rep["progress"]["policies"][POL]["done"] == 1


@pytest.mark.parametrize("case,reason", [("accept_infra", "accept_infra_error"),
                                         ("two_accepts", "multiple_accept"),
                                         ("rows_disagree", "attempt_rows_disagree")])
def test_conflicting_terminal(tmp_path, capsys, case, reason):
    a = _ident(0)
    st = Stage(tmp_path / "stage")
    if case == "accept_infra":
        st.result(a, "a1", 1, "error", infra=True)
        st.ledger("accept", a, "a1", status="error")
    elif case == "two_accepts":
        st.accepted(a, "a1", "success")
        st.accepted(a, "a2", "fail", no=2)
    else:
        st.accepted(a, "a1", "success")
        st.result(a, "a1", 1, "fail")
    rc, lines, rep = _report(tmp_path, capsys, [a])
    pp = rep["per_policy"][POL]
    assert [c["reason"] for c in pp["conflicts"]] == [reason]
    assert pp["outcomes"]["conflict"] == 1 and pp["outcomes"]["missing"] == 0
    cov = F.verdict(lines, "V8_EVAL_COVERAGE")
    assert cov[""] == "FAIL" and cov["conflicting_terminal"] == "1" and cov["missing"] == "0"


def test_accept_without_row_counts_as_conflict_only_when_final(tmp_path, capsys):
    a = _ident(0)
    Stage(tmp_path / "stage").ledger("accept", a, "ghost", status="success")
    _, lines, _ = _report(tmp_path, capsys, [a])
    assert F.verdict(lines, "V8_EVAL_COVERAGE")["conflicting_terminal"] == "1"
    _, lines, rep = _report(tmp_path, capsys, [a], "--partial")
    assert F.verdict(lines, "V8_EVAL_COVERAGE")["conflicting_terminal"] == "0"
    assert rep["per_policy"][POL]["accept_without_row"] == [{"key": a["key"], "attempt_id": "ghost"}]


def test_extra_and_duplicate(tmp_path, capsys):
    a, stray = _ident(0), _ident(9)
    st = Stage(tmp_path / "stage")
    st.accepted(a, "a1", "success")
    st.result(a, "a1", 1, "success")  # 同一 attempt_id 重复一行
    st.accepted(stray, "s1", "success")  # 清单之外的身份
    _, lines, rep = _report(tmp_path, capsys, [a])
    cov = F.verdict(lines, "V8_EVAL_COVERAGE")
    assert cov[""] == "FAIL" and cov["extra"] == "1" and cov["duplicate"] == "1"
    assert rep["per_policy"][POL]["denominator"] == 1


def test_late_terminal_ignored(tmp_path, capsys):
    a = _ident(0)
    st = Stage(tmp_path / "stage")
    st.accepted(a, "a1", "fail")
    st.ledger("attempt_start", a, "a2", attempt_no=2)
    st.result(a, "a2", 2, "success")
    st.ledger("attempt_end", a, "a2", attempt_no=2, status="success", late=True)
    _, lines, rep = _report(tmp_path, capsys, [a])
    assert rep["per_policy"][POL]["outcomes"]["fail"] == 1 and rep["per_policy"][POL]["outcomes"]["success"] == 0
    assert F.verdict(lines, "V8_EVAL_COVERAGE")["late_ignored"] == "1"
    assert F.verdict(lines, "V8_EVAL_COVERAGE")[""] == "PASS"


def test_canary_rows_not_counted(tmp_path, capsys):
    a = _ident(0)
    st = Stage(tmp_path / "stage")
    st.result(a, "c0", 1, "success", canary=True)
    _, lines, rep = _report(tmp_path, capsys, [a])
    assert rep["per_policy"][POL]["outcomes"]["missing"] == 1
    assert F.verdict(lines, "V8_EVAL_COVERAGE")["duplicate"] == "0"


@pytest.mark.parametrize("mutate,field", [
    (lambda st, a: st.accepted(a, "a1", "success", task_success=False), "task_success"),
    (lambda st, a: st.accepted(a, "a1", "success", exec_steps=None), "exec_steps"),
    (lambda st, a: st.accepted(a, "a1", "success", spec_sha256="0" * 64,
                               identity={"tier": a["tier"], "seed": a["seed"], "candidate": a["candidate"],
                                         "spec_sha256": "0" * 64}), "spec_sha256"),
    (lambda st, a: st.accepted(a, "a1", "success", seed=a["seed"] + 1,
                               identity={"tier": a["tier"], "seed": a["seed"] + 1, "candidate": a["candidate"],
                                         "spec_sha256": a["spec_sha256"]}), "seed"),
], ids=["task_success", "exec_steps", "spec", "seed"])
def test_count_mismatch_negatives(tmp_path, capsys, mutate, field):
    a = _ident(0)
    mutate(Stage(tmp_path / "stage"), a)
    _, lines, rep = _report(tmp_path, capsys, [a])
    rp = F.verdict(lines, "V8_EVAL_REPORT")
    assert rp[""] == "FAIL" and int(rp["count_mismatch"]) >= 1
    assert any(field in x for x in rep["count_mismatch_detail"])


def test_manifest_header_negatives(tmp_path, capsys):
    a, b = _ident(0), _ident(1)
    st = Stage(tmp_path / "stage")
    st.accepted(a, "a1", "success")
    st.accepted(b, "b1", "success")
    # expect_total 与清单行数不等
    manifest = F.write_manifest(tmp_path / "m" / "manifest.json", [a, b])
    _, lines, rep = F.run_report(capsys, manifest, tmp_path / "stage", [POL], tmp_path / "o1", "--expect-total", "3")
    assert F.verdict(lines, "V8_EVAL_REPORT")[""] == "FAIL"
    assert any("expect_total" in x for x in rep["count_mismatch_detail"])
    # 清单 cells 与 rows 逐格计数不一致
    _, lines, rep = _report(tmp_path, capsys, [a, b], manifest_extra={"cells": {"TaskA@xhard1": 3}})
    assert any("cells" in x for x in rep["count_mismatch_detail"])
    # 清单 total 与 rows 不等
    _, lines, rep = _report(tmp_path, capsys, [a, b], manifest_extra={"total": 5})
    assert any("total" in x for x in rep["count_mismatch_detail"])


def test_exec_over_cap(tmp_path, capsys):
    a = _ident(0)
    cap = F.hard_specs().EXEC_CAP
    Stage(tmp_path / "stage").accepted(a, "a1", "timeout", exec_steps=cap + 1)
    _, lines, _ = _report(tmp_path, capsys, [a], "--cap", str(cap))
    rp = F.verdict(lines, "V8_EVAL_REPORT")
    assert rp[""] == "FAIL" and rp["exec_over_cap"] == "1"
    a2 = _ident(1)
    Stage(tmp_path / "stage2").accepted(a2, "b1", "timeout", exec_steps=cap)
    manifest = F.write_manifest(tmp_path / "m2" / "manifest.json", [a2])
    _, lines, _ = F.run_report(capsys, manifest, tmp_path / "stage2", [POL], tmp_path / "o2", "--expect-total", "1",
                               "--cap", str(cap))
    assert F.verdict(lines, "V8_EVAL_REPORT")["exec_over_cap"] == "0"  # 恰好等于上限不算越限


@pytest.mark.parametrize("status,kw,unexplained", [
    ("success", {}, 1),  # 已接受终态无录像
    ("error", {"error": "IK 失败"}, 0),  # 非 infra 错误终局，无录像但写明原因
    ("error", {"error": None}, 1),  # 非 infra 错误终局，无录像也无原因
])
def test_media_checks(tmp_path, capsys, status, kw, unexplained):
    a = _ident(0)
    Stage(tmp_path / "stage").accepted(a, "a1", status, media=False, **kw)
    _, lines, rep = _report(tmp_path, capsys, [a])
    assert F.verdict(lines, "V8_EVAL_REPORT")["media_unexplained"] == str(unexplained)


def test_recorder_verify_fail_is_unexplained(tmp_path, capsys):
    a = _ident(0)
    Stage(tmp_path / "stage").accepted(a, "a1", "success", recorder_verify="FAIL")
    _, lines, _ = _report(tmp_path, capsys, [a])
    assert F.verdict(lines, "V8_EVAL_REPORT")["media_unexplained"] == "1"


# ---------------------------------------------------------------- V9 合并复用：800 局总表逐格对 V9_CELLS（F-3）


def _packaged_identities() -> list[dict]:
    hs = F.hard_specs()
    out = []
    for tier in hs.TIERS:
        _, rows = hs.load_specs(hs.packaged_specs_path(tier), check_fingerprint=False)
        for r in rows:
            if hs.delivered(r):
                out.append({"task": r["task"], "tier": r["tier"], "seed": r["seed"], "candidate": r["candidate"],
                            "builder_episode": r["episode"], "source_episode": None, "spec_sha256": r["spec_sha256"],
                            "effective_max_steps": hs.TIER_MAX_STEPS[r["tier"]],
                            "key": f"{r['task']}_{r['tier']}_{r['seed']}"})
    return out


def _v9_fixture(tmp_path, move_one: bool):
    """新评 = 新评规则内的身份；复用 = 其余。move_one=True 时把一条复用身份在 reused.json、V8 manifest、V8 结果行里
    一致地换到另一格（总数不变、各处自洽），只有逐格对 V9_CELLS 才能发现。"""
    em = F.eval_manifest()
    allrows = _packaged_identities()
    new = [r for r in allrows if em.in_new_rule(r)]
    reused = [dict(r) for r in allrows if not em.in_new_rule(r)]
    if move_one:
        victim = reused[0]
        other = next(t for t, tier in F.v9_cells_sorted() if tier == victim["tier"] and t != victim["task"])
        victim["task"] = other
        victim["key"] = f"{other}_{victim['tier']}_{victim['seed']}"
    v8_manifest = tmp_path / "v8" / "manifest.json"
    v8_manifest.parent.mkdir(parents=True)
    v8_manifest.write_text(json.dumps({"schema": em.SCHEMA, "rows": [
        {k: r[k] for k in ("task", "tier", "seed", "spec_sha256", "key")} for r in reused]}), encoding="utf-8")
    v8_sha = hashlib.sha256(v8_manifest.read_bytes()).hexdigest()
    rdoc = {"schema": em.REUSED_SCHEMA, "v8_manifest": str(v8_manifest), "v8_manifest_sha256": v8_sha,
            "count": len(reused), "rows": [{"task": r["task"], "tier": r["tier"], "seed": r["seed"],
                                            "spec_sha256": r["spec_sha256"], "v8_key": r["key"]} for r in reused]}
    mdir = tmp_path / "v9" / "manifest"
    mdir.mkdir(parents=True)
    rtext = json.dumps(rdoc, ensure_ascii=False)
    (mdir / "reused.json").write_text(rtext, encoding="utf-8")
    manifest = F.write_manifest(mdir / "manifest.json", new, reused={
        "path": "reused.json", "sha256": hashlib.sha256(rtext.encode()).hexdigest(), "count": len(reused),
        "v8_manifest": str(v8_manifest), "v8_manifest_sha256": v8_sha})
    for pol in ("smvla", "mme"):
        v8 = Stage(tmp_path / "v8" / "run", pol)
        for i, r in enumerate(reused):
            v8.accepted(r, f"v8-{i}", "success" if i % 3 else "fail", media=False)
        cur = Stage(tmp_path / "v9" / "run", pol)
        for i, r in enumerate(new):
            cur.accepted(r, f"v9-{i}", "success")
    return manifest, v8_manifest, len(new), len(reused)


@pytest.mark.parametrize("move_one", [False, True], ids=["exact", "one_moved"])
def test_v9_total_table_matches_v9_cells(tmp_path, capsys, move_one):
    er = F.eval_report()
    manifest, v8_manifest, n_new, n_reused = _v9_fixture(tmp_path, move_one)
    capsys.readouterr()
    rc = er.main(["--manifest", str(manifest), "--stage", str(tmp_path / "v9" / "run"), "--policies", "smvla,mme",
                  "--out", str(tmp_path / "out"), "--reuse", str(tmp_path / "v8"), "--reuse-manifest",
                  str(v8_manifest), "--expect-total", str(n_new), "--expect-reused", str(n_reused)])
    lines = capsys.readouterr().out.splitlines()
    rep = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    v9 = rep["v9"]
    want = {f"{t}@{tier}": n for (t, tier), n in F.hard_specs().V9_CELLS.items()}
    assert v9["total"] == sum(want.values()) and v9["new"] == n_new and v9["reused"] == n_reused
    rp = F.verdict(lines, "V9_EVAL_REPORT")
    for pol in ("smvla", "mme"):
        got = {c: v["denominator"] for c, v in v9["totals"][pol]["cells"].items()}
        assert (got == want) is (not move_one)
    if move_one:
        assert rp[""] == "FAIL"
        assert len(v9["count_mismatch_detail"]) == 2 * 2  # 两个模型 × 一格少一局、一格多一局
        assert all("总表格" in x for x in v9["count_mismatch_detail"])
    else:
        assert rp[""] == "PASS" and v9["count_mismatch_detail"] == []
        assert F.verdict(lines, "V9_EVAL_COVERAGE")[""] == "PASS"
        assert rc == 1  # 未给 --videos：视频行照实 FAIL，退出码非零
        assert F.verdict(lines, "V9_EVAL_VIDEOS")[""] == "FAIL"
        tot = v9["totals"]["mme"]["outcomes"]
        assert sum(tot.values()) == sum(want.values())
        assert tot["fail"] == sum(1 for i in range(n_reused) if i % 3 == 0)


def test_v9_reused_sha_mismatch_is_counted(tmp_path, capsys):
    er = F.eval_report()
    manifest, v8_manifest, n_new, n_reused = _v9_fixture(tmp_path, False)
    (manifest.parent / "reused.json").write_text("{}", encoding="utf-8")
    capsys.readouterr()
    er.main(["--manifest", str(manifest), "--stage", str(tmp_path / "v9" / "run"), "--policies", "mme",
             "--out", str(tmp_path / "out"), "--reuse", str(tmp_path / "v8"), "--reuse-manifest", str(v8_manifest),
             "--expect-total", str(n_new), "--expect-reused", str(n_reused)])
    lines = capsys.readouterr().out.splitlines()
    rp = F.verdict(lines, "V9_EVAL_REPORT")
    assert rp[""] == "FAIL" and int(rp["count_mismatch"]) >= 1


def test_reuse_args_must_come_together(tmp_path):
    er = F.eval_report()
    with pytest.raises(SystemExit):
        er.main(["--manifest", "m", "--stage", "s", "--out", str(tmp_path), "--reuse", "x"])
