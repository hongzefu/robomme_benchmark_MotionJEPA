#!/usr/bin/env python3
"""轻量测试：v8 单格补抽 ``scripts/injection-dev/append_candidates.py``（S3-SUP）。

纯 CPU 合成夹具，不起仿真：冻结根用 ``test_v8_delivery_flow`` 的合成抽签 + ``_freeze.freeze`` 封签，``split_v8`` 切两片
（两片都引用同一份 xhard2 冻结 identity），假 runner 让 BinFill/xhard2 备用耗尽；抽签用注入的假 ``draw_one``。覆盖：

* 追加后冻结根与片规格都过 /4 校验、旧行逐字不变、``per_env`` 递增、新行与冻结未选行同形；
* 片规格里缺额个新候选被标 selected（等价于 apply_results 的递补），冻结根新行保持未选；
* 两片 ``shard.json`` 的 xhard2 来源 identity／文件 sha 都更新、别档来源不动，备份文件留证；
* ``run_continue_v8 --resume`` 只跑新候选、失败继续递补、``V8_DELIVERY_SET=PASS``；之后 ``merge_v8`` 通过；
* 写后复核失败 → 全部按备份恢复、``APPEND_CANDIDATES=FAIL``；``--dry-run`` 不写盘；有未试备用时拒绝追加。

    uv run --no-sync python -m pytest tests/lightweight/test_v8_append_candidates.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "injection-dev"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _rollout  # noqa: E402
import append_candidates as AC  # noqa: E402
from robomme_hard.env_record_wrapper import hard_specs as H  # noqa: E402
from test_v8_delivery_flow import FakeRunner, build_root  # noqa: E402

AC.bootstrap(REPO)

CELLS = {("BinFill", "xhard1"): 2, ("BinFill", "xhard2"): 3, ("VideoUnmaskSwap", "xhard2"): 2}
SHARD_A = {("BinFill", "xhard1"): 2, ("BinFill", "xhard2"): 3}
SHARD_B = {("VideoUnmaskSwap", "xhard2"): 2}


def _snapshot(*roots: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for root in roots for p in sorted(root.rglob("*")) if p.is_file()}


class FakeDraw:
    """假 ``_draw._draw_one``：``fail={episode: 失败次数}`` 的 episode 先 reset 失败若干次。"""

    def __init__(self, tier: str, fail: dict[int, int] | None = None):
        self.tier, self.fail, self.calls = tier, dict(fail or {}), []

    def __call__(self, task, seed, episode, sampling):
        self.calls.append((task, seed, episode))
        if self.fail.get(episode, 0) > 0:
            self.fail[episode] -= 1
            return False, None, "ResetRejected", "合成 reset 拒绝"
        return True, {"spec_kind": "native-newvalue/2", "task": task, "tier": self.tier, "layout": {"x": episode}}, None, None


@pytest.fixture
def gen1(tmp_path, monkeypatch):
    """冻结根 + 两片；片 A 跑完且 BinFill/xhard2 备用耗尽（交付 2/3），片 B 全部交付。"""
    frozen = build_root(tmp_path / "frozen", CELLS, spare=1)
    out = tmp_path / "gen1"
    _rollout.split_v8(frozen, SHARD_A, out / "shardA", label="shardA")
    _rollout.split_v8(frozen, SHARD_B, out / "shardB", label="shardB")
    runner = FakeRunner({("xhard2", "BinFill", 0): "fail", ("xhard2", "BinFill", 3): "fail"})
    monkeypatch.setattr(_rollout, "run_batch", runner)
    summary = _rollout.run_continue_v8(out / "shardA" / "specs", SHARD_A, out / "shardA", src_root=REPO, workers=1,
                                       gpu="0", pkg="robomme_hard", code_baseline="fixture")
    assert "exhausted_cells=1" in summary["delivery_set"] and "problems=BinFill/xhard2:exhausted" in summary["delivery_set"]
    summary = _rollout.run_continue_v8(out / "shardB" / "specs", SHARD_B, out / "shardB", src_root=REPO, workers=1,
                                       gpu="0", pkg="robomme_hard", code_baseline="fixture")
    assert summary["delivery_set"].startswith("V8_DELIVERY_SET=PASS")
    return frozen, out


def _argv(frozen: Path, shard: Path, *extra) -> list[str]:
    return ["--frozen-root", str(frozen), "--shard-dir", str(shard), "--cell", "BinFill@xhard2",
            "--code-root", str(REPO), *map(str, extra)]


def _no_check(task, sampling):
    return None


def test_追加后校验通过且旧行逐字不变(gen1, capsys):
    frozen, out = gen1
    f_path, s_path = frozen / "xhard2" / "specs.jsonl", out / "shardA" / "specs" / "xhard2" / "specs.jsonl"
    f_old, s_old = f_path.read_text().splitlines(), s_path.read_text().splitlines()
    meta_old = {k: json.loads((out / k / "shard.json").read_text()) for k in ("shardA", "shardB")}
    draw = FakeDraw("xhard2", fail={5: 1})
    rc = AC.main(_argv(frozen, out / "shardA", "--extra", 3, "--max-reset-attempts", 10), draw_one=draw,
                 sampling_check=_no_check)
    text = capsys.readouterr().out
    assert rc == 0, text
    assert "APPEND_DRAW tried=4 ok=3 shortfall=0" in text
    assert [c[2] for c in draw.calls] == [4, 5, 5, 6]
    f_header, f_rows = H.load_specs(f_path, check_fingerprint=False)
    s_header, s_rows = H.load_specs(s_path, check_fingerprint=False)
    assert f"APPEND_CANDIDATES=PASS cell=BinFill@xhard2 extra=3 per_env=4→7 frozen_identity={f_header['identity_sha256'][:12]} " \
           f"shard_identity={s_header['identity_sha256'][:12]}" in text
    # 旧行逐字保留，新行追加在末尾
    f_new, s_new = f_path.read_text().splitlines(), s_path.read_text().splitlines()
    assert f_new[1:len(f_old)] == f_old[1:] and len(f_new) == len(f_old) + 3
    assert s_new[1:len(s_old)] == s_old[1:] and len(s_new) == len(s_old) + 3
    assert f_header["per_env"]["BinFill"] == s_header["per_env"]["BinFill"] == 7
    assert f_header["per_env"]["VideoUnmaskSwap"] == 3  # 别的任务不动
    assert f_header["select_rule"] == json.loads(f_old[0])["select_rule"]
    assert f_header["delivery_per_cell"] == json.loads(f_old[0])["delivery_per_cell"]
    assert f_header["identity_sha256"] != json.loads(f_old[0])["identity_sha256"]
    assert f_header["delivery_sha256"] == json.loads(f_old[0])["delivery_sha256"]
    new_f = [r for r in f_rows if r["task"] == "BinFill" and r["episode"] >= 4]
    assert [r["episode"] for r in new_f] == [4, 5, 6] and [r["attempt"] for r in new_f] == [0, 1, 0]
    rule = H.seed_rule_for("xhard2", "v8")
    assert all(r["seed"] == H.seed_for("BinFill", r["episode"], r["attempt"], rule) for r in new_f)
    assert all(not r["selected"] and not r["tried"] and not r["initial_selected"] and r["rollout"] is None
               and r["layout_parent"] is None for r in new_f)
    # 片里：缺额 1 → 编号最小的新候选（4）标 selected，其余备用
    new_s = {r["episode"]: r for r in s_rows if r["task"] == "BinFill" and r["episode"] >= 4}
    assert [e for e, r in sorted(new_s.items()) if r["selected"]] == [4]
    assert sum(r["selected"] for r in s_rows if r["task"] == "BinFill") == 3
    assert [a["appended"] for a in f_header["draw_stats"]["appends"]] == [3]
    assert s_header["draw_stats"]["appends"][0]["backfill_selected"] == [4]
    # 两片的 xhard2 来源都更新到新冻结根；片 A 的 xhard1 来源不动
    file_sha = _rollout.file_sha256(f_path)
    for k in ("shardA", "shardB"):
        meta = json.loads((out / k / "shard.json").read_text())
        assert meta["sources"]["xhard2"] == {"identity_sha256": f_header["identity_sha256"], "file_sha256": file_sha}
        assert meta["appends"][0]["old_source"] == meta_old[k]["sources"]["xhard2"]
    assert json.loads((out / "shardA" / "shard.json").read_text())["sources"]["xhard1"] == meta_old["shardA"]["sources"]["xhard1"]
    # 备份留证（原内容逐字节）
    backups = sorted(Path(p) for p in text.split("APPEND_BACKUPS ", 1)[1].splitlines()[0].split())
    assert len(backups) == 4
    assert next(b for b in backups if b.name.startswith("specs.jsonl") and "frozen" in str(b)).read_text().splitlines() == f_old
    assert not Path(str(f_path) + ".lock").exists() and not Path(str(s_path) + ".lock").exists()


def test_续跑只生成新候选并PASS_之后合并通过(gen1, monkeypatch, capsys):
    frozen, out = gen1
    assert AC.main(_argv(frozen, out / "shardA", "--extra", 3), draw_one=FakeDraw("xhard2"),
                   sampling_check=_no_check) == 0
    capsys.readouterr()
    # 新候选 4 失败 → 递补 5 → 成功
    runner = FakeRunner({("xhard2", "BinFill", 4): "fail"})
    monkeypatch.setattr(_rollout, "run_batch", runner)
    summary = _rollout.run_continue_v8(out / "shardA" / "specs", SHARD_A, out / "shardA", src_root=REPO, workers=1,
                                       gpu="0", pkg="robomme_hard", code_baseline="fixture", resume=True)
    assert runner.calls == [[("xhard2", "BinFill", 4)], [("xhard2", "BinFill", 5)]]
    assert summary["delivery_set"].startswith("V8_DELIVERY_SET=PASS tasks=1 cells=2 total=5 expected=5")
    ledger = _rollout.read_ledger(out / "shardA" / _rollout.LEDGER_NAME)
    rounds = [e["round"] for e in ledger if e["tier"] == "xhard2"]
    assert rounds == sorted(rounds)  # 轮次接着账本往后编
    report = _rollout.merge_v8(frozen, CELLS, [out / "shardA", out / "shardB"], out / "merged-specs", out / "merged")
    assert report["line"].startswith("V8_DELIVERY_SET=PASS tasks=2 cells=3 total=7 expected=7")
    merged = H.load_specs_v8(out / "merged-specs", CELLS, check_fingerprint=False)
    f_header, _ = H.load_specs(frozen / "xhard2" / "specs.jsonl", check_fingerprint=False)
    assert merged["xhard2"][0]["identity_sha256"] == f_header["identity_sha256"]
    assert merged["xhard2"][0]["per_env"]["BinFill"] == 7


def test_写后复核失败全部恢复(gen1, monkeypatch, capsys):
    frozen, out = gen1
    before = _snapshot(frozen, out)

    def boom(plan, result):
        raise H.SpecsError("合成复核失败")

    monkeypatch.setattr(AC, "verify_written", boom)
    rc = AC.main(_argv(frozen, out / "shardA", "--extra", 2), draw_one=FakeDraw("xhard2"), sampling_check=_no_check)
    text = capsys.readouterr().out
    assert rc == 1 and "APPEND_CANDIDATES=FAIL cell=BinFill@xhard2" in text and "已恢复 4/4" in text
    after = _snapshot(frozen, out)
    backups = [p for p in after if ".pre-append-" in p.name]
    assert len(backups) == 4
    assert {p: b for p, b in after.items() if p not in backups} == before  # 原文件逐字节恢复，无临时文件残留
    assert not any(p.name.endswith(".lock") for p in after)


def test_dry_run不写盘_有未试备用拒绝(gen1, tmp_path, capsys):
    frozen, out = gen1
    before = _snapshot(frozen, out)
    assert AC.main(_argv(frozen, out / "shardA", "--dry-run")) == 0
    text = capsys.readouterr().out
    assert "APPEND_PLAN cell=BinFill@xhard2 quota=3 selected=2 delivered=2 deficit=1 per_env=4 new_episodes=4..13" in text
    assert "APPEND_SHARDS update=shardA,shardB" in text and "APPEND_DRY_RUN=PASS" in text
    assert _snapshot(frozen, out) == before
    # 刚切片未跑的片：还有未试备用 → 拒绝
    fresh = tmp_path / "fresh"
    _rollout.split_v8(frozen, SHARD_A, fresh / "shardA", label="shardA")
    assert AC.main(_argv(frozen, fresh / "shardA", "--dry-run")) == 1
    assert "APPEND_CANDIDATES=FAIL" in capsys.readouterr().out
    # 片 B 不含 BinFill@xhard2 → 拒绝
    assert AC.main(_argv(frozen, out / "shardB", "--dry-run")) == 1
    assert "不含任务 BinFill" in capsys.readouterr().out
