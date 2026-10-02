#!/usr/bin/env python3
"""轻量测试：scripts/eval-official/v8_report.py（契约 C4 第一段；纯 CPU、临时目录，不碰真实 NFS）。

覆盖：零缺失、正常失败、error、重复结果行、迟到终态（late）、冲突终态、exec_steps 超 1600、--partial。
全部用例过后最后一个用例打印 ``V8_EVAL_REPORT_TESTS=PASS``。

    uv run --no-sync python -m pytest tests/lightweight/test_v8_eval_report.py -q -s
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
REPORT = REPO_ROOT / "scripts" / "eval-official" / "v8_report.py"
_spec = importlib.util.spec_from_file_location("v8_report_under_test", REPORT)
v8r = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v8r)

POLICIES = ("smvla", "mme")
# 2 任务 × 2 档 × 若干局；分母 6 / 模型，两片
IDENTS = [
    ("VideoUnmask", "xhard1", 1001, 0, "00"),
    ("VideoUnmask", "xhard1", 1002, 1, "00"),
    ("VideoUnmask", "xhard2", 1003, 0, "01"),
    ("SwingXtimes", "xhard5", 2001, 3, "00"),
    ("SwingXtimes", "xhard5", 2002, 4, "01"),
    ("SwingXtimes", "xhard1", 2003, 0, "01"),
]


def ident_row(task, tier, seed, cand, shard):
    return {"task": task, "tier": tier, "seed": seed, "candidate": cand, "builder_episode": seed % 100,
            "source_episode": None, "spec_sha256": f"sha-{task}-{tier}-{seed}", "effective_max_steps": 1600,
            "key": f"{task}_{tier}_{seed}", "_shard": shard}


def write_manifest(root: Path) -> Path:
    rows = [ident_row(*x) for x in IDENTS]
    cells: dict[str, int] = {}
    shards: dict[str, list] = {}
    for r in rows:
        cells[f"{r['task']}@{r['tier']}"] = cells.get(f"{r['task']}@{r['tier']}", 0) + 1
        shards.setdefault(r.pop("_shard"), []).append(r)
    mdir = root / "manifest"
    mdir.mkdir(parents=True)
    doc = {"schema": "v8-eval-manifest/1", "total": len(rows), "xhard0_dropped": 192, "cells": cells,
           "shards": {k: len(v) for k, v in shards.items()}, "rows": rows}
    (mdir / "manifest.json").write_text(json.dumps(doc))
    for sid, items in shards.items():
        (mdir / f"shard-{sid}.json").write_text(json.dumps(items))
    return mdir / "manifest.json"


class Stage:
    """按契约 C2／C3 伪造 sNN/<policy>/results.jsonl、<policy>.ledger.jsonl、rec/<key>.a<n>/。"""

    def __init__(self, root: Path):
        self.root = root / "stage"
        self.shard_of = {f"{t}_{tier}_{s}": sh for t, tier, s, _c, sh in IDENTS}
        self.ident = {f"{t}_{tier}_{s}": ident_row(t, tier, s, c, sh) for t, tier, s, c, sh in IDENTS}

    def _dir(self, policy, key):
        d = self.root / f"s{self.shard_of.get(key, '00')}" / policy
        d.mkdir(parents=True, exist_ok=True)
        return d

    def ledger(self, policy, key, **row):
        d = self._dir(policy, key)
        with (d / f"{policy}.ledger.jsonl").open("a") as fh:
            fh.write(json.dumps({"t": 0, "key": key, "seat": self.shard_of.get(key), "policy": policy, **row}) + "\n")

    def result(self, policy, key, status, *, attempt_no=1, attempt_id=None, accept=True, late=False,
               exec_steps=100, media=True, wall=10.0, write_ledger=True, accept_error=False, **extra):
        aid = attempt_id or uuid.uuid4().hex
        d = self._dir(policy, key)
        ident = self.ident.get(key) or {"task": key.split("_")[0], "tier": key.split("_")[1],
                                        "seed": int(key.split("_")[2]), "candidate": 0, "spec_sha256": "x"}
        name = f"{key}.a{attempt_no}"
        row = {"v8": True, "key": key, "task": ident["task"], "tier": ident["tier"], "seed": ident["seed"],
               "candidate": ident["candidate"], "spec_sha256": ident["spec_sha256"], "policy": policy,
               "attempt_id": aid, "attempt_no": attempt_no, "status": status,
               "task_success": status == "success", "exec_steps": exec_steps, "effective_max_steps": 1600,
               "cap_hit": status == "timeout", "infra": False, "rec_dir": f"/tmp/R-s00/rec/{policy}/{name}",
               "recorder_verify": "PASS", "timing": {"episode_wall_s": wall}, **extra}
        with (d / "results.jsonl").open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        if write_ledger:
            self.ledger(policy, key, kind="attempt_start", attempt_id=aid, attempt_no=attempt_no)
            for _ in range(2):
                self.ledger(policy, key, kind="reset_claim", attempt_id=aid, attempt_no=attempt_no)
            self.ledger(policy, key, kind="attempt_end", attempt_id=aid, attempt_no=attempt_no, status=status,
                        late=late)
            if (accept and status in ("success", "fail", "timeout")) or accept_error:
                self.ledger(policy, key, kind="accept", attempt_id=aid, accepted_attempt_id=aid, attempt_no=attempt_no)
        if media:
            rd = d / "rec" / name
            rd.mkdir(parents=True, exist_ok=True)
            for f in ("front.mkv", "wrist.mkv", "summary.json", "meta.json"):
                (rd / f).write_text("x")
        return aid

    def budget(self, policy, seat="00", reset=428, infra=2):
        d = self.root / f"s{seat}" / policy
        d.mkdir(parents=True, exist_ok=True)
        with (d / f"{policy}.ledger.jsonl").open("a") as fh:
            fh.write(json.dumps({"t": 0, "kind": "budget", "seat": seat, "policy": policy, "reset_budget": reset,
                                 "infra_retry_budget": infra}) + "\n")

    def all_ok(self, *, skip=(), statuses=None):
        for pol in POLICIES:
            self.budget(pol, "00")
            self.budget(pol, "01")
            for k in self.ident:
                if (pol, k) in skip:
                    continue
                self.result(pol, k, (statuses or {}).get((pol, k), "success"))


def run(manifest: Path, stage: Stage, out: Path, *extra: str) -> tuple[int, dict, list[str]]:
    proc = subprocess.run([sys.executable, str(REPORT), "--manifest", str(manifest), "--stage", str(stage.root),
                           "--policies", ",".join(POLICIES), "--out", str(out), "--expect-total", str(len(IDENTS)),
                           *extra], capture_output=True, text=True, timeout=120)
    lines = proc.stdout.strip().splitlines()
    rep = json.loads((out / "report.json").read_text()) if (out / "report.json").exists() else {}
    assert lines, proc.stderr
    return proc.returncode, rep, lines


def kv(line: str) -> dict:
    head, *rest = line.split()
    out = dict(x.split("=", 1) for x in rest)
    out["_verdict"] = head.split("=", 1)[1]
    return out


def setup(tmp_path):
    return write_manifest(tmp_path), Stage(tmp_path)


def test_zero_missing_all_pass(tmp_path):
    man, st = setup(tmp_path)
    st.all_ok(statuses={("smvla", "SwingXtimes_xhard5_2001"): "fail", ("mme", "VideoUnmask_xhard2_1003"): "timeout"})
    rc, rep, lines = run(man, st, tmp_path / "out")
    cov, r = kv(lines[-2]), kv(lines[-1])
    assert lines[-2].startswith("V8_EVAL_COVERAGE=PASS") and lines[-1].startswith("V8_EVAL_REPORT=PASS"), lines
    assert cov == {"_verdict": "PASS", "policies": "2", "missing": "0", "extra": "0", "duplicate": "0",
                   "conflicting_terminal": "0", "late_ignored": "0", "error_final": "0"}
    assert r == {"_verdict": "PASS", "count_mismatch": "0", "media_unexplained": "0", "exec_over_cap": "0"}
    assert rc == 0
    sm = rep["per_policy"]["smvla"]
    assert sm["denominator"] == 6 and sm["outcomes"]["success"] == 5 and sm["outcomes"]["fail"] == 1
    assert abs(sm["micro_success_rate"] - 5 / 6) < 1e-9
    # 任务宏平均：VideoUnmask 3/3，SwingXtimes 2/3
    assert abs(sm["task_macro_success_rate"] - (1 + 2 / 3) / 2) < 1e-9
    assert sm["cells"]["SwingXtimes@xhard5"] == {**sm["cells"]["SwingXtimes@xhard5"], "denominator": 2, "success": 1,
                                                 "fail": 1}
    assert rep["per_policy"]["mme"]["outcomes"]["timeout"] == 1
    assert sm["budget"]["reset_claim_total"] == 12 and sm["budget"]["seats"]["s00"]["reset_budget"] == 428
    idx = [json.loads(l) for l in (tmp_path / "out" / "video-index.jsonl").read_text().splitlines()]
    assert len(idx) == 12 and all(x["media_ok"] and x["accepted"] for x in idx)
    md = (tmp_path / "out" / "report.md").read_text()
    assert "任务×档成功率" in md and "V8_EVAL_COVERAGE=PASS" in md


def test_error_identity_and_infra_retry(tmp_path):
    man, st = setup(tmp_path)
    k_retry, k_err = "VideoUnmask_xhard1_1001", "SwingXtimes_xhard1_2003"
    st.all_ok(skip={("smvla", k_retry), ("smvla", k_err)})
    # 先 infra 错误（无录像），重试成功
    st.result("smvla", k_retry, "error", attempt_no=1, infra=True, infra_reason="env_build", media=False)
    st.result("smvla", k_retry, "success", attempt_no=2)
    # 只有错误尝试（额度耗尽），无终态
    st.result("smvla", k_err, "error", attempt_no=1, budget_exhausted=True, error="ResetBudgetExhausted", media=False)
    rc, rep, lines = run(man, st, tmp_path / "out")
    cov, r = kv(lines[-2]), kv(lines[-1])
    assert cov["_verdict"] == "FAIL" and cov["missing"] == "1" and cov["conflicting_terminal"] == "0"
    assert cov["error_final"] == "0"
    assert r["_verdict"] == "PASS" and r["media_unexplained"] == "0", lines  # 无录像的错误行有原因
    sm = rep["per_policy"]["smvla"]
    # 额度耗尽的错误尝试没有 accept：身份记 missing（错误尝试另列废弃），不是 error 终局
    assert sm["outcomes"]["error"] == 0 and sm["outcomes"]["missing"] == 1 and sm["outcomes"]["success"] == 5
    assert sm["budget"]["infra_retries_total"] == 1 and sm["budget"]["seats"]["s01"]["budget_exhausted"] == 1
    assert {x["key"] for x in sm["abandoned"]} == {k_retry, k_err}
    assert {x["key"] for x in sm["errors_without_video"]} == {k_retry, k_err}
    assert rc == 1


def test_error_final_accept_and_ledger_only_attempt(tmp_path):
    man, st = setup(tmp_path)
    k_fin, k_infra, k_dang = "VideoUnmask_xhard2_1003", "SwingXtimes_xhard5_2002", "SwingXtimes_xhard1_2003"
    st.all_ok(skip={("mme", k_fin), ("mme", k_infra), ("mme", k_dang)})
    # 非 infra 错误终局：E-A 写 accept 指向 error 行 → 合法结局，记 error、占分母、不算成功
    st.result("mme", k_fin, "error", accept_error=True, error="EnvError: scene invalid", exec_steps=37)
    # accept 指向 infra=true 的 error 行 → 仍算冲突
    st.result("mme", k_infra, "error", accept_error=True, infra=True, infra_reason="env_build", media=False)
    # 悬空尝试恢复：账本有 attempt_end(infra) 而 results.jsonl 无对应行 → 计入废弃尝试，不报错；随后重试成功
    st.ledger("mme", k_dang, kind="attempt_start", attempt_id="dangling01", attempt_no=1)
    st.ledger("mme", k_dang, kind="attempt_end", attempt_id="dangling01", attempt_no=1, status="error", infra=True,
              infra_reason="episode_wall_recovered")
    st.result("mme", k_dang, "success", attempt_no=2)
    rc, rep, lines = run(man, st, tmp_path / "out")
    cov, r = kv(lines[-2]), kv(lines[-1])
    assert cov["error_final"] == "1" and cov["missing"] == "0" and cov["conflicting_terminal"] == "1", lines
    assert r["_verdict"] == "PASS", lines
    mm = rep["per_policy"]["mme"]
    assert mm["outcomes"]["error"] == 1 and mm["outcomes"]["conflict"] == 1 and mm["outcomes"]["success"] == 4
    assert mm["cells"]["VideoUnmask@xhard2"]["error"] == 1 and mm["cells"]["VideoUnmask@xhard2"]["done"] == 1
    assert [c["reason"] for c in mm["conflicts"]] == ["accept_infra_error"]
    dang = [x for x in mm["abandoned"] if x["attempt_id"] == "dangling01"]
    assert len(dang) == 1 and dang[0]["key"] == k_dang
    assert rc == 1  # 冲突照判 FAIL
    # 去掉冲突那一条后：error 终局不影响覆盖 PASS
    man2, st2 = setup(tmp_path / "b")
    st2.all_ok(skip={("mme", k_fin)})
    st2.result("mme", k_fin, "error", accept_error=True, error="EnvError: scene invalid")
    rc, _, lines = run(man2, st2, tmp_path / "b" / "out")
    assert lines[-2].startswith("V8_EVAL_COVERAGE=PASS") and lines[-2].endswith("error_final=1") and rc == 0, lines


def test_accept_without_row_only_conflict(tmp_path):
    """accept 已写但结果行未出现：正式汇总只计 conflicting_terminal，不重复计 missing、不算废弃尝试。"""
    man, st = setup(tmp_path)
    k = "VideoUnmask_xhard2_1003"
    st.all_ok(skip={("smvla", k)})
    st.ledger("smvla", k, kind="attempt_start", attempt_id="noresult01", attempt_no=1)
    st.ledger("smvla", k, kind="attempt_end", attempt_id="noresult01", attempt_no=1, status="success")
    st.ledger("smvla", k, kind="accept", attempt_id="noresult01", accepted_attempt_id="noresult01")
    rc, rep, lines = run(man, st, tmp_path / "out")
    cov = kv(lines[-2])
    assert (cov["conflicting_terminal"], cov["missing"]) == ("1", "0"), lines
    sm = rep["per_policy"]["smvla"]
    assert sm["abandoned"] == [] and sm["outcomes"]["conflict"] == 1 and sm["outcomes"]["missing"] == 0
    assert rc == 1
    # --partial 下当作未完成：不判冲突
    _, _, lines = run(man, st, tmp_path / "o2", "--partial")
    assert kv(lines[-2])["conflicting_terminal"] == "0"


def test_partial_seat_from_observed_stage_dir(tmp_path):
    """分片重分到别的 sNN（manifest shard 字段未改）：进度按运行根里实际所在席位估算；--shard-files 覆盖未开跑身份。"""
    man, st = setup(tmp_path)
    for pol in POLICIES:
        st.budget(pol, "00")
    k_moved = "VideoUnmask_xhard2_1003"  # manifest 分片 01
    st.shard_of[k_moved] = "10"
    st.result("smvla", k_moved, "success", wall=50.0)
    (tmp_path / "newshards").mkdir()
    (tmp_path / "newshards" / "shard-11.json").write_text(json.dumps(
        [{"task": "SwingXtimes", "tier": "xhard1", "seed": 2003}]))
    proc = subprocess.run([sys.executable, str(REPORT), "--manifest", str(man), "--stage", str(st.root),
                           "--policies", "smvla", "--out", str(tmp_path / "o"), "--expect-total", "6", "--partial",
                           "--shard-files", str(tmp_path / "newshards" / "shard-*.json")],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    pr = json.loads((tmp_path / "o" / "report.json").read_text())["progress"]
    assert pr["seats"]["10"]["detail"]["smvla"]["remaining"] == 0
    assert pr["seats"]["11"]["detail"]["smvla"]["remaining"] == 1
    assert pr["seats"]["01"]["detail"]["smvla"]["remaining"] == 1  # 01 只剩 SwingXtimes_xhard5_2002
    assert pr["seats"]["00"]["detail"]["smvla"]["remaining"] == 3


def test_duplicate_result_rows(tmp_path):
    man, st = setup(tmp_path)
    k = "VideoUnmask_xhard2_1003"
    st.all_ok(skip={("mme", k)})
    aid = st.result("mme", k, "fail")
    st.result("mme", k, "fail", attempt_id=aid, write_ledger=False)  # 同一尝试结果行写了两遍
    rc, rep, lines = run(man, st, tmp_path / "out")
    cov = kv(lines[-2])
    assert cov["_verdict"] == "FAIL" and cov["duplicate"] == "1" and cov["conflicting_terminal"] == "0"
    assert rep["per_policy"]["mme"]["outcomes"]["fail"] == 1  # 去重后只算一次
    assert rc == 1


def test_late_terminal_is_ignored(tmp_path):
    man, st = setup(tmp_path)
    k = "SwingXtimes_xhard5_2002"
    st.all_ok(skip={("smvla", k)})
    st.result("smvla", k, "fail", attempt_no=1)
    # 被判死后又写回来的同一身份终态：账本 attempt_end late=true、不再 accept；即使是 success 也不入分数
    st.result("smvla", k, "success", attempt_no=2, accept=False, late=True)
    rc, rep, lines = run(man, st, tmp_path / "out")
    cov = kv(lines[-2])
    assert cov["_verdict"] == "PASS" and cov["late_ignored"] == "1", lines
    sm = rep["per_policy"]["smvla"]
    assert sm["outcomes"]["fail"] == 1 and sm["outcomes"]["success"] == 5  # 权威终态是 fail，不是「最后一条」
    assert sm["late"][0]["ledger_late"] is True and sm["late"][0]["status"] == "success"
    assert rc == 0


def test_conflicting_terminal(tmp_path):
    man, st = setup(tmp_path)
    k1, k2 = "VideoUnmask_xhard1_1002", "SwingXtimes_xhard5_2001"
    st.all_ok(skip={("mme", k1), ("mme", k2)})
    st.result("mme", k1, "fail", attempt_no=1)
    st.result("mme", k1, "success", attempt_no=2)  # 同一身份第二条 accept → 冲突
    aid = st.result("mme", k2, "error", attempt_no=1, accept=False, error="boom", media=False,
                    budget_exhausted=True)  # 额度耗尽的错误不是合法终局
    st.ledger("mme", k2, kind="accept", attempt_id=aid, accepted_attempt_id=aid)  # accept 指向非终态 → 冲突
    rc, rep, lines = run(man, st, tmp_path / "out")
    cov = kv(lines[-2])
    assert cov["_verdict"] == "FAIL" and cov["conflicting_terminal"] == "2" and cov["missing"] == "0", lines
    reasons = sorted(c["reason"] for c in rep["per_policy"]["mme"]["conflicts"])
    assert reasons == ["accept_not_terminal", "multiple_accept"]
    assert rep["per_policy"]["mme"]["outcomes"]["conflict"] == 2  # 冲突不择优、不算成功
    assert rc == 1


def test_exec_steps_over_cap(tmp_path):
    man, st = setup(tmp_path)
    k = "VideoUnmask_xhard1_1001"
    st.all_ok(skip={("smvla", k)})
    st.result("smvla", k, "timeout", exec_steps=1601)
    rc, rep, lines = run(man, st, tmp_path / "out")
    r = kv(lines[-1])
    assert r["_verdict"] == "FAIL" and r["exec_over_cap"] == "1"
    assert lines[-2].startswith("V8_EVAL_COVERAGE=PASS")
    assert rc == 1


def test_missing_media_and_extra_identity(tmp_path):
    man, st = setup(tmp_path)
    k = "VideoUnmask_xhard1_1001"
    st.all_ok(skip={("mme", k)})
    st.result("mme", k, "success", media=False)  # 终态却没有录像 → media_unexplained
    st.result("mme", "Ghost_xhard1_9", "success")  # manifest 之外 → extra
    rc, rep, lines = run(man, st, tmp_path / "out")
    cov, r = kv(lines[-2]), kv(lines[-1])
    assert cov["extra"] == "1" and r["media_unexplained"] == "1" and r["_verdict"] == "FAIL"
    # 搬到本机视频根后能找到 → 不再算缺
    vd = tmp_path / "videos" / "mme" / "xhard1" / "VideoUnmask" / f"{k}.a1"
    vd.mkdir(parents=True)
    for f in ("front.mkv", "wrist.mkv", "summary.json"):
        (vd / f).write_text("x")
    _, _, lines = run(man, st, tmp_path / "out2", "--videos", str(tmp_path / "videos"))
    assert kv(lines[-1])["media_unexplained"] == "0"


def test_partial_progress(tmp_path):
    man, st = setup(tmp_path)
    for pol in POLICIES:
        st.budget(pol, "00")
    # smvla 只完成两局（都在片 00），mme 一局都没有
    st.result("smvla", "VideoUnmask_xhard1_1001", "success", wall=100.0)
    st.result("smvla", "SwingXtimes_xhard5_2001", "fail", wall=300.0)
    rc, rep, lines = run(man, st, tmp_path / "out", "--partial")
    assert lines[0].startswith("V8_EVAL_PROGRESS ")
    cov, r = kv(lines[-2]), kv(lines[-1])
    assert cov["_verdict"] == "PASS" and cov["missing"] == "0" and r["_verdict"] == "PASS", lines
    pr = rep["progress"]
    assert pr["policies"]["smvla"]["done"] == 2 and pr["policies"]["mme"]["done"] == 0
    assert pr["policies"]["smvla"]["cells_done"]["VideoUnmask@xhard1"] == 1
    # mme 无任何观测 → 剩余时间未观测
    assert pr["est_remaining_s"] is None and len(pr["unobserved_cells"]["mme"]) == 4
    assert "未观测" in (tmp_path / "out" / "report.md").read_text()
    assert rc == 0
    # 只看 smvla：片 00 剩 VideoUnmask_xhard1_1002（任务均值 100）；片 01 剩 VideoUnmask 100 + SwingXtimes 300×2
    proc = subprocess.run([sys.executable, str(REPORT), "--manifest", str(man), "--stage", str(st.root),
                           "--policies", "smvla", "--out", str(tmp_path / "o3"), "--expect-total", "6", "--partial"],
                          capture_output=True, text=True, timeout=120)
    pr = json.loads((tmp_path / "o3" / "report.json").read_text())["progress"]
    assert pr["seats"]["00"]["est_remaining_s"] == 100.0
    assert pr["seats"]["01"]["est_remaining_s"] == 700.0
    assert pr["est_remaining_s"] == 700.0 and pr["slowest_seat"] == "01", proc.stdout
    # 不带 --partial 时同样数据判缺失 FAIL
    _, _, lines = run(man, st, tmp_path / "o4")
    assert kv(lines[-2])["_verdict"] == "FAIL" and kv(lines[-2])["missing"] == "10"


def test_missing_fields_and_canary(tmp_path):
    man, st = setup(tmp_path)
    k1, k2 = "VideoUnmask_xhard1_1001", "SwingXtimes_xhard5_2001"
    st.all_ok(skip={("smvla", k1), ("smvla", k2)})
    aid = uuid.uuid4().hex
    d = st._dir("smvla", k1)
    row = {"v8": True, "key": k1, "task": "VideoUnmask", "tier": "xhard1", "seed": 1001, "policy": "smvla",
           "attempt_id": aid, "attempt_no": 1, "status": "fail", "task_success": False, "rec_dir": f"/x/{k1}.a1"}
    with (d / "results.jsonl").open("a") as fh:  # 缺 exec_steps 与 spec_sha256
        fh.write(json.dumps(row) + "\n")
    st.ledger("smvla", k1, kind="accept", attempt_id=aid, accepted_attempt_id=aid)
    st._dir("smvla", k1).joinpath("rec", f"{k1}.a1").mkdir(parents=True)
    for f in ("front.mkv", "wrist.mkv", "summary.json"):
        (d / "rec" / f"{k1}.a1" / f).write_text("x")
    # 金丝雀成功局：不进分母、不算迟到；正式局另有 fail
    st.result("smvla", k2, "success", canary=True, accept=False, rec_dir=f"/x/{k2}.canary.a1")
    st.result("smvla", k2, "fail")
    rc, rep, lines = run(man, st, tmp_path / "out")
    cov, r = kv(lines[-2]), kv(lines[-1])
    assert r["_verdict"] == "FAIL" and r["count_mismatch"] == "1", lines
    assert "exec_steps" in rep["count_mismatch_detail"][0] and "spec_sha256" in rep["count_mismatch_detail"][0]
    assert cov["late_ignored"] == "0" and cov["_verdict"] == "PASS"
    assert rep["per_policy"]["smvla"]["outcomes"]["fail"] == 2
    assert rc == 1


# ---------------------------------------------------------------- V9：--reuse 合并复用（1002 方案 S1-F）

def _v9_rows(n_new=80, n_reused=720):
    """新评 80 行（MoveCube／InsertPeg xhard4）与复用 720 行（其余任务五档）；MoveCube 新评与 V8 同 seed 不同 spec。"""
    new = []
    for i in range(n_new):
        task = "MoveCube" if i < 50 else "InsertPeg"
        cand = i if i < 50 else 29 + i - 50
        seed = 22_000_000 + (0 if task == "MoveCube" else 100_000) + cand
        new.append({"task": task, "tier": "xhard4", "seed": seed, "candidate": cand, "builder_episode": cand,
                    "source_episode": None, "spec_sha256": f"{'9' * 56}{i:08d}", "effective_max_steps": 1600,
                    "key": f"{task}_xhard4_{seed}", "shard": f"{i % 10:02d}"})
    reused = []
    tasks = ("PickXtimes", "VideoUnmask", "BinFill", "StopCube")
    for i in range(n_reused):
        task, tier = tasks[i % 4], f"xhard{1 + (i // 4) % 5}"
        seed = 16_000_000 + i
        reused.append({"task": task, "tier": tier, "seed": seed, "candidate": i, "builder_episode": i,
                       "source_episode": None, "spec_sha256": f"{'8' * 56}{i:08d}", "effective_max_steps": 1600,
                       "key": f"{task}_{tier}_{seed}", "shard": "00"})
    return new, reused


def _write_stage_rows(stage: Path, rows: list[dict], status_of, *, seat_of=lambda r: "00", rec_root=None,
                      late_status=None):
    """按契约写 sNN/<policy>/results.jsonl 与账本（每身份一次尝试 + accept）；rec_root 给出时按 V8 搬运布局落录像。"""
    for pol in POLICIES:
        for r in rows:
            d = stage / f"s{seat_of(r)}" / pol
            d.mkdir(parents=True, exist_ok=True)
            aid = uuid.uuid4().hex
            st = status_of(pol, r)
            name = f"{r['key']}.a1"
            res = {"v8": True, "key": r["key"], "task": r["task"], "tier": r["tier"], "seed": r["seed"],
                   "candidate": r["candidate"], "spec_sha256": r["spec_sha256"], "policy": pol, "attempt_id": aid,
                   "attempt_no": 1, "status": st, "task_success": st == "success", "exec_steps": 100,
                   "infra": False, "rec_dir": f"/tmp/R/rec/{pol}/{name}", "recorder_verify": "PASS"}
            led = [{"kind": "attempt_start", "attempt_id": aid, "attempt_no": 1},
                   {"kind": "attempt_end", "attempt_id": aid, "attempt_no": 1, "status": st},
                   {"kind": "accept", "attempt_id": aid, "accepted_attempt_id": aid, "attempt_no": 1}]
            with (d / "results.jsonl").open("a") as fh:
                fh.write(json.dumps(res) + "\n")
                if late_status and late_status(pol, r):  # accept 之后迟到的另一终态：不得被当成终态
                    fh.write(json.dumps(dict(res, attempt_id=uuid.uuid4().hex, attempt_no=2,
                                             status=late_status(pol, r),
                                             task_success=late_status(pol, r) == "success")) + "\n")
            with (d / f"{pol}.ledger.jsonl").open("a") as fh:
                for x in led:
                    fh.write(json.dumps({"t": 0, "key": r["key"], "policy": pol, **x}) + "\n")
            if rec_root is not None:
                vd = rec_root / pol / r["tier"] / r["task"] / name
                vd.mkdir(parents=True, exist_ok=True)
                for f in ("front.mkv", "wrist.mkv", "summary.json"):
                    (vd / f).write_text(f"{pol}-{name}-{f}")


def _v9_setup(tmp_path):
    new, reused_rows = _v9_rows()
    # V8：复用 720 行 + V8 同 seed 的 MoveCube 旧局（spec 不同，不得被认成复用）
    v8_extra = [dict(r, spec_sha256="7" * 64) for r in new[:20]]
    v8_rows = reused_rows + v8_extra
    v8_dir = tmp_path / "v8"
    (v8_dir / "manifest").mkdir(parents=True)
    v8_man = v8_dir / "manifest" / "manifest.json"
    v8_man.write_text(json.dumps({"schema": "v8-eval-manifest/1", "total": len(v8_rows), "rows": v8_rows}))
    # V8 账本：smvla 偶数号成功、mme 全失败；每身份另写一条迟到 success（不入分数）
    _write_stage_rows(v8_dir / "nfs-records" / "run", v8_rows,
                      lambda pol, r: "success" if pol == "smvla" and r["candidate"] % 2 == 0 else "fail",
                      late_status=lambda pol, r: "success" if pol == "mme" else None)
    # V9 新评：smvla 全成功、mme 前 10 局成功
    stage, videos = tmp_path / "v9stage", tmp_path / "v9videos"
    _write_stage_rows(stage, new, lambda pol, r: "success" if pol == "smvla" or r["candidate"] < 10 else "fail",
                      seat_of=lambda r: r["shard"], rec_root=videos)
    # moved.jsonl：逐文件 sha256（与 V8 搬运脚本同格式）
    import hashlib
    with (videos / "moved.jsonl").open("w") as fh:
        for pol in POLICIES:
            for r in new:
                d = videos / pol / r["tier"] / r["task"] / f"{r['key']}.a1"
                fh.write(json.dumps({"mode": "v8", "policy": pol, "key": r["key"], "task": r["task"], "tier": r["tier"],
                                     "dest": str(d), "files": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                                                               for f in sorted(d.iterdir())}}) + "\n")
    mdir = tmp_path / "v9run" / "manifest"
    mdir.mkdir(parents=True)
    rdoc = {"schema": "v9-eval-reused/1", "v8_manifest": str(v8_man),
            "v8_manifest_sha256": hashlib.sha256(v8_man.read_bytes()).hexdigest(), "count": len(reused_rows),
            "rows": sorted(({"task": r["task"], "tier": r["tier"], "seed": r["seed"], "spec_sha256": r["spec_sha256"],
                             "v8_key": r["key"]} for r in reused_rows), key=lambda x: (x["task"], x["tier"], x["seed"]))}

    def write_reused(doc):
        text = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        (mdir / "reused.json").write_text(text)
        cells: dict[str, int] = {}
        for r in new:
            cells[f"{r['task']}@{r['tier']}"] = cells.get(f"{r['task']}@{r['tier']}", 0) + 1
        man = {"schema": "v8-eval-manifest/1", "total": len(new), "xhard0_dropped": 192, "cells": cells,
               "shards": {}, "rows": new,
               "reused": {"path": "reused.json", "sha256": hashlib.sha256(text.encode()).hexdigest(),
                          "count": doc["count"], "v8_manifest": str(v8_man),
                          "v8_manifest_sha256": doc["v8_manifest_sha256"]}}
        (mdir / "manifest.json").write_text(json.dumps(man))

    write_reused(rdoc)
    return {"new": new, "reused": reused_rows, "v8_dir": v8_dir, "v8_man": v8_man, "stage": stage, "videos": videos,
            "manifest": mdir / "manifest.json", "rdoc": rdoc, "write_reused": write_reused}


def _run_v9(fx, out, capsys, monkeypatch):
    monkeypatch.setattr(v8r, "count_media_frames", lambda path, videos: 7)
    rc = v8r.main(["--manifest", str(fx["manifest"]), "--stage", str(fx["stage"]), "--videos", str(fx["videos"]),
                   "--policies", ",".join(POLICIES), "--out", str(out), "--reuse", str(fx["v8_dir"]),
                   "--reuse-manifest", str(fx["v8_man"])])
    lines = capsys.readouterr().out.strip().splitlines()
    rep = json.loads((out / "report.json").read_text())
    return rc, rep, lines


def _tree_digest(root: Path) -> dict:
    import hashlib
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_v9报告合并复用(tmp_path, capsys, monkeypatch):
    fx = _v9_setup(tmp_path)
    before = _tree_digest(fx["v8_dir"])
    rc, rep, lines = _run_v9(fx, tmp_path / "out", capsys, monkeypatch)
    assert lines[-3:] == [
        "V9_EVAL_COVERAGE=PASS policies=2 expected=80 missing=0 extra=0 duplicate=0 conflicting_terminal=0 error_final=0",
        "V9_EVAL_REPORT=PASS total=800 new=80 reused=720 count_mismatch=0 media_unexplained=0",
        "V9_EVAL_VIDEOS=PASS policies=2 expected=160 videos=160 missing=0 decode_fail=0 sha_mismatch=0 "
        "moved_record_absent=0",
    ], (lines, rep["v9"]["count_mismatch_detail"][:5])
    assert rc == 0
    assert _tree_digest(fx["v8_dir"]) == before  # 不改写 V8 任何文件
    t = rep["v9"]["totals"]
    # 复用终态取 V8 账本 accepted_attempt_id：smvla 偶数号成功 360；mme 全 fail（迟到 success 不入分数）
    assert t["smvla"]["denominator"] == t["mme"]["denominator"] == 800
    assert t["smvla"]["reused_success"] == 360 and t["smvla"]["new_success"] == 80 and t["smvla"]["success"] == 440
    assert t["mme"]["reused_success"] == 0 and t["mme"]["new_success"] == 10 and t["mme"]["success"] == 10
    assert sum(v["denominator"] for v in t["smvla"]["tasks"].values()) == 800
    assert t["smvla"]["tasks"]["MoveCube"] == {"denominator": 50, "success": 50, "success_rate": 1.0}
    assert sum(v["denominator"] for v in t["mme"]["tiers"].values()) == 800
    assert rep["v9"]["v8_stage"].endswith("nfs-records/run")
    # 新评分表仍按 V8 口径，分母 80；per_policy.cells 只含新评两格（站点 S1-E 逐格对账依赖），800 局只在 v9.totals
    assert rep["per_policy"]["smvla"]["denominator"] == 80
    for pol in POLICIES:
        cells = rep["per_policy"][pol]["cells"]
        assert set(cells) == {"MoveCube@xhard4", "InsertPeg@xhard4"}
        assert cells["MoveCube@xhard4"]["denominator"] == 50 and cells["InsertPeg@xhard4"]["denominator"] == 30
        assert sum(v["denominator"] for v in cells.values()) == 80
        assert sum(v["denominator"] for v in rep["v9"]["totals"][pol]["cells"].values()) == 800
    assert rep["per_policy"]["mme"]["cells"]["MoveCube@xhard4"]["success"] == 10
    md = (tmp_path / "out" / "report.md").read_text()
    assert md.startswith("# V9 双模型评估汇总") and "800 局总表" in md and "新评身份分表" in md

    # 篡改 reused.json 一条 spec_sha256（同步更新 manifest 里的 sha，使只剩四元组不符）→ count_mismatch
    doc = json.loads(json.dumps(fx["rdoc"]))
    doc["rows"][0]["spec_sha256"] = "0" * 64
    fx["write_reused"](doc)
    rc, rep, lines = _run_v9(fx, tmp_path / "out2", capsys, monkeypatch)
    r = kv(lines[-2])
    assert r["_verdict"] == "FAIL" and int(r["count_mismatch"]) >= 1 and rc == 1
    assert any("四元组" in x for x in rep["v9"]["count_mismatch_detail"])

    # 篡改 reused.json 但不更新 manifest.reused.sha256 → count_mismatch
    fx["write_reused"](fx["rdoc"])
    (fx["manifest"].parent / "reused.json").write_text(json.dumps(doc))
    rc, rep, lines = _run_v9(fx, tmp_path / "out3", capsys, monkeypatch)
    assert kv(lines[-2])["_verdict"] == "FAIL" and any("sha256" in x for x in rep["v9"]["count_mismatch_detail"])


def test_v9视频缺失与sha不符(tmp_path, capsys, monkeypatch):
    import shutil
    fx = _v9_setup(tmp_path)
    r0, r1 = fx["new"][0], fx["new"][1]
    shutil.rmtree(fx["videos"] / "mme" / "xhard4" / r0["task"] / f"{r0['key']}.a1")
    (fx["videos"] / "smvla" / "xhard4" / r1["task"] / f"{r1['key']}.a1" / "front.mkv").write_text("tampered")
    rc, rep, lines = _run_v9(fx, tmp_path / "out", capsys, monkeypatch)
    v = kv(lines[-1])
    assert v["_verdict"] == "FAIL" and v["expected"] == "160" and v["videos"] == "158"
    assert v["missing"] == "1" and v["sha_mismatch"] == "1" and rc == 1


def test_v9_moved记录缺失即FAIL(tmp_path, capsys, monkeypatch):
    fx = _v9_setup(tmp_path)
    mv = fx["videos"] / "moved.jsonl"
    lines_in = mv.read_text().splitlines()
    mv.write_text("\n".join(lines_in[1:]) + "\n")  # 删掉一条新评局的搬运记录
    rc, rep, lines = _run_v9(fx, tmp_path / "out", capsys, monkeypatch)
    v = kv(lines[-1])
    assert v["_verdict"] == "FAIL" and v["moved_record_absent"] == "1" and v["videos"] == "159"
    assert v["missing"] == "0" and v["sha_mismatch"] == "0" and rc == 1


def test_v9_partial按严格口径判FAIL(tmp_path, capsys, monkeypatch):
    fx = _v9_setup(tmp_path)
    monkeypatch.setattr(v8r, "count_media_frames", lambda path, videos: 7)
    rc = v8r.main(["--manifest", str(fx["manifest"]), "--stage", str(fx["stage"]), "--videos", str(fx["videos"]),
                   "--policies", ",".join(POLICIES), "--out", str(tmp_path / "out"), "--reuse", str(fx["v8_dir"]),
                   "--reuse-manifest", str(fx["v8_man"]), "--partial"])
    lines = capsys.readouterr().out.strip().splitlines()
    assert rc == 1 and all(kv(x)["_verdict"] == "FAIL" and kv(x)["partial"] == "1" for x in lines[-3:]), lines


def test_zz_summary_line(request):
    """放在最后（pytest 按定义顺序执行）：本次会话前面没有失败、也没有跳过才打印 PASS。"""
    assert request.session.testsfailed == 0, "前面有用例失败"
    tr = request.config.pluginmanager.get_plugin("terminalreporter")
    skipped = len(tr.stats.get("skipped", [])) if tr is not None else 0
    print("V8_EVAL_REPORT_TESTS=SKIPPED" if skipped else "V8_EVAL_REPORT_TESTS=PASS")
