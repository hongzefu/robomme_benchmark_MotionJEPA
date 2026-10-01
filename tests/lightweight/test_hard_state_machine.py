"""STATE_MACHINE（0927 计划 §5.2、§6.3）：第二阶段 continue 模式的状态机与回写纪律，纯 CPU 夹具、不起仿真。

四个场景：①失败 → 递补 → 中断 → 恢复；②两个不同 --output 争同一 specs；③锁已存在；④文件在运行期间被他人改过。
runner 用注入的假 batch_runner 代替，故本测试不 reset、不 rollout。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "injection-dev"))

import _freeze  # noqa: E402
import _rollout  # noqa: E402
from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402

TIER = "xhard1"
#: v8 阶段 1：v6 seed 规则已删，夹具改用 v7 规则（/2 schema 同样接受 v7 规则）
RULE = hard_specs.seed_rule_for(TIER, "v7")


def _specs(tmp_path: Path, candidates: int = 5, select=(0, 1)) -> Path:
    drafts = []
    for task in ("BinFill", "PickXtimes"):
        for episode in range(candidates):
            spec = {"spec_kind": "native-newvalue/2", "task": task, "layout": {"x": episode}}
            drafts.append({"task": task, "difficulty": TIER, "episode": episode, "attempt": 0,
                           "seed": hard_specs.seed_for(task, episode, 0, RULE), "reset_ok": True,
                           "spec": spec, "spec_sha256": hard_specs.spec_sha256(spec)})
    parts = {"difficulty": TIER, "tasks": ["BinFill", "PickXtimes"], "seed_rule": RULE,
             "sampling_config": {"BinFill": {"decision": {}, "native": {}}, "PickXtimes": {"decision": {}, "native": {}}},
             "recovery_rule": {"rule": "off"}, "identity_source": "formula", "run_id": "fixture",
             "draw_stats": {}, "provenance": {}}
    header, rows = _freeze.freeze(drafts, parts, select, candidates)
    path = tmp_path / "specs.jsonl"
    _freeze.write_jsonl_exclusive(path, [header, *rows])
    return path


def _fake_runner(fail: set, crash_after: int | None = None, calls: list | None = None):
    def run(batch, header, round_index):
        out = []
        for index, row in enumerate(batch):
            if crash_after is not None and index >= crash_after:
                raise KeyboardInterrupt("模拟中断")
            ok = (row["task"], row["candidate"]) not in fail
            out.append({"task": row["task"], "tier": row["tier"], "candidate": row["candidate"],
                        "episode": row["episode"], "seed": row["seed"], "attempt": row["attempt"],
                        "spec_sha256": row["spec_sha256"], "ok": ok, "error_type": None if ok else "ScrewPlanFailure",
                        "error": None if ok else "规划失败", "round": round_index, "role": row.get("_role", "selected"),
                        "h5": f"/fake/{row['task']}_{row['candidate']}.h5" if ok else None,
                        "h5_sha256": f"sha-{row['task']}-{row['candidate']}" if ok else None,
                        "bytes": 1 if ok else None, "frames": 1 if ok else None})
        if calls is not None:
            calls.append([(r["task"], r["candidate"]) for r in batch])
        return out
    return run


def _continue(specs, out, runner, **kw):
    return _rollout.run_continue(specs, out, src_root=REPO, workers=1, gpu="0", pkg="robomme_hard",
                                 code_baseline="fixture", batch_runner=runner, **kw)


def test_fail_backfill_interrupt_resume(tmp_path):
    specs = _specs(tmp_path)
    before, _ = hard_specs.load_specs(specs, check_fingerprint=False)
    # 中断：第一批跑到一半抛出 → 不回写，锁释放
    with pytest.raises(KeyboardInterrupt):
        _continue(specs, tmp_path / "out1", _fake_runner(set(), crash_after=1))
    assert not Path(str(specs) + ".lock").exists()
    assert hard_specs.load_specs(specs, check_fingerprint=False)[0]["delivery_sha256"] == before["delivery_sha256"]
    # 恢复：BinFill/1 失败 → 递补 BinFill/2；最后每格 2 局交付
    calls: list = []
    summary = _continue(specs, tmp_path / "out2", _fake_runner({("BinFill", 1)}, calls=calls))
    header, rows = hard_specs.load_specs(specs, check_fingerprint=False)
    assert header["identity_sha256"] == before["identity_sha256"]
    delivered = sorted((r["task"], r["candidate"]) for r in rows if hard_specs.delivered(r))
    assert delivered == [("BinFill", 0), ("BinFill", 2), ("PickXtimes", 0), ("PickXtimes", 1)]
    failed = [r for r in rows if (r["rollout"] or {}).get("status") == "failed"]
    assert [(r["task"], r["candidate"], r["selected"], r["tried"]) for r in failed] == [("BinFill", 1, False, True)]
    assert calls[1] == [("BinFill", 2)] and summary["attempted"] == 5
    # 再跑一次：已 ok 的行不重跑
    calls2: list = []
    _continue(specs, tmp_path / "out3", _fake_runner(set(), calls=calls2))
    assert calls2 == []


def test_two_outputs_contend(tmp_path):
    specs = _specs(tmp_path)
    lock = _rollout.SpecsLock(specs)
    lock.acquire()  # 模拟另一个 --output 的进程持锁
    try:
        with pytest.raises(_rollout.RolloutError, match="锁已存在"):
            _continue(specs, tmp_path / "other", _fake_runner(set()))
    finally:
        lock.release()
    assert not (tmp_path / "other").exists(), "取锁失败的进程不得启动任何 worker 或建输出目录"


def test_lock_exists_refused(tmp_path):
    specs = _specs(tmp_path)
    Path(str(specs) + ".lock").write_text(json.dumps({"pid": 1, "host": "stale"}))
    with pytest.raises(_rollout.RolloutError, match="锁已存在"):
        _continue(specs, tmp_path / "out", _fake_runner(set()))
    assert Path(str(specs) + ".lock").exists(), "不自动判陈旧、不删除他人的锁"


def test_file_changed_by_other(tmp_path):
    specs = _specs(tmp_path)

    def runner(batch, header, round_index):
        text = specs.read_text()
        specs.write_text(text + "\n")  # 他人在运行期间改了文件（整份 sha 变化）
        return _fake_runner(set())(batch, header, round_index)

    with pytest.raises(_rollout.RolloutError, match="被他人改过"):
        _continue(specs, tmp_path / "out", runner)
    print("STATE_MACHINE=PASS cases=4")
