"""``hard_parity.py generate --tier xhard0 --identities``（xhard0 子集生成）的纯 CPU 测试。

不起仿真：``subprocess.run`` 被替身拦截（记录运行器命令并读其 ``jobs.json``），GPU 事实与版本信息打桩，
用 ``--dev-smoke`` 放行非 A40。完整 xhard0 清单取仓库内 ``scripts/configs/newtask-v7/xhard0_manifest.json``。
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from scripts.parity import gate_set as G
from scripts.parity import hard_parity as H

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "scripts" / "configs" / "newtask-v7" / "xhard0_manifest.json"
FROZEN_X0 = REPO / "scripts" / "configs" / "gate-set-xhard0-48.json"


@pytest.fixture
def fake_run(monkeypatch):
    calls: list[dict] = []

    def run(command, *args, **kwargs):
        record = {"command": list(command), "jobs": None, "identities": None}
        if "--jobs-json" in command:
            record["jobs"] = json.loads(Path(command[command.index("--jobs-json") + 1]).read_text())
        if "--identities" in command:
            text = Path(command[command.index("--identities") + 1]).read_text()
            record["identities"] = [json.loads(t) for t in text.splitlines() if t.strip()]
        calls.append(record)
        return types.SimpleNamespace(returncode=0, stdout="0" * 40 + "\n", stderr="")

    monkeypatch.setattr(H.subprocess, "run", run)
    monkeypatch.setattr(H, "gpu_facts", lambda: {"gpu_model": "FAKE", "driver": "0"})
    monkeypatch.setattr(H, "versions", lambda: {})
    return calls


def _generate(argv: list[str]) -> int:
    args = H.build_parser().parse_args(argv)
    return args.func(args)


def _runner_call(calls):
    runner = [c for c in calls if str(H.RUNNER) in c["command"] or str(H.GENERATE_H5) in c["command"]]
    assert len(runner) == 1
    return runner[0]


def _write_subset(path: Path, items) -> Path:
    path.write_text("".join(json.dumps(i) + "\n" for i in items))
    return path


def test_xhard0_子集只生成子集_清单仍为完整清单(fake_run, tmp_path):
    x0 = G.load_xhard0_set(FROZEN_X0)
    subset = G.write_generate_identities(x0, tmp_path / "x0.jsonl")
    out = tmp_path / "out"
    rc = _generate(["generate", "--side", "H", "--tier", "xhard0", "--manifest", str(MANIFEST),
                    "--src-root", str(REPO), "--out", str(out), "--dev-smoke", "--identities", str(subset)])
    assert rc == 1  # 替身运行器不产出任何局，recorded=0 ≠ 48 → FAIL；这里只核派发
    call = _runner_call(fake_run)
    cmd = call["command"]
    assert cmd[cmd.index("--xhard0-manifest") + 1] == str(MANIFEST)
    assert {(j["task"], j["seed"], j["episode"]) for j in call["jobs"]} == \
        {(r["task"], r["seed"], r["source_episode"]) for r in x0}
    assert len(call["jobs"]) == 48 and all(j["difficulty"] == "hard" for j in call["jobs"])
    launch = json.loads(next(out.glob("launch-*.json")).read_text())
    assert launch["rows"] == 48 and launch["identities"] == str(subset)
    assert launch["manifest"] == str(MANIFEST)


def test_xhard0_不给子集时仍为完整192(fake_run, tmp_path):
    _generate(["generate", "--side", "O", "--tier", "xhard0", "--manifest", str(MANIFEST),
               "--src-root", str(REPO), "--out", str(tmp_path / "o"), "--dev-smoke"])
    assert len(_runner_call(fake_run)["jobs"]) == 192


def test_xhard0_子集与_smoke_叠加_先筛后截(fake_run, tmp_path):
    x0 = G.load_xhard0_set(FROZEN_X0)
    subset = G.write_generate_identities(x0, tmp_path / "x0.jsonl")
    _generate(["generate", "--side", "H", "--tier", "xhard0", "--manifest", str(MANIFEST), "--src-root", str(REPO),
               "--out", str(tmp_path / "s"), "--dev-smoke", "--identities", str(subset), "--smoke", "2"])
    jobs = _runner_call(fake_run)["jobs"]
    keys = {(r["task"], r["seed"]) for r in x0}
    assert len(jobs) == 2 and all((j["task"], j["seed"]) in keys for j in jobs)


def test_xhard0_清单外身份报错(fake_run, tmp_path):
    subset = _write_subset(tmp_path / "bad.jsonl", [{"task": "PickXtimes", "tier": "xhard0", "seed": 510300},
                                                   {"task": "PickXtimes", "tier": "xhard0", "seed": 1}])
    with pytest.raises(H.ParityError, match="清单之外"):
        _generate(["generate", "--side", "H", "--tier", "xhard0", "--manifest", str(MANIFEST), "--src-root",
                   str(REPO), "--out", str(tmp_path / "b"), "--dev-smoke", "--identities", str(subset)])
    assert fake_run == []


def test_xhard0_子集_tier_不是_xhard0_报错(fake_run, tmp_path):
    subset = _write_subset(tmp_path / "bad.jsonl", [{"task": "PickXtimes", "tier": "hard", "seed": 510300}])
    with pytest.raises(H.ParityError, match="tier 须为 xhard0"):
        _generate(["generate", "--side", "H", "--tier", "xhard0", "--manifest", str(MANIFEST), "--src-root",
                   str(REPO), "--out", str(tmp_path / "b"), "--dev-smoke", "--identities", str(subset)])


def test_xhard0_subset_rows_纯函数():
    rows = H.native_rows(MANIFEST)
    got = H.xhard0_subset_rows(rows, {("PickXtimes", "xhard0", 510300), ("StopCube", "xhard0", 520300)})
    assert [(r["task"], r["episode"]) for r in got] == [("PickXtimes", 3), ("StopCube", 3)]


# ── v8／v9 原行为回归 ─────────────────────────────────────────────────────────


def _delivery(path: Path) -> Path:
    rows = [{"task": "StopCube", "tier": "xhard1", "episode": i, "seed": 100 + i, "candidate": i, "h5_sha256": "x"}
            for i in range(4)]
    path.write_text(json.dumps({"schema": H.V8_DELIVERY_SCHEMA, "rows": rows}))
    return path


def test_v9_子集仍按三元身份筛_清单外报错(fake_run, tmp_path):
    delivery = _delivery(tmp_path / "delivery.json")
    subset = _write_subset(tmp_path / "s.jsonl", [{"task": "StopCube", "tier": "xhard1", "seed": 101},
                                                 {"task": "StopCube", "tier": "xhard1", "seed": 103}])
    _generate(["generate", "--side", "H2", "--tier", "v9", "--manifest", str(delivery), "--src-root", str(REPO),
               "--out", str(tmp_path / "v9"), "--dev-smoke", "--specs-root", str(tmp_path), "--identities", str(subset)])
    call = _runner_call(fake_run)
    assert call["identities"] == [{"task": "StopCube", "tier": "xhard1", "seed": 101},
                                  {"task": "StopCube", "tier": "xhard1", "seed": 103}]
    stray = _write_subset(tmp_path / "x.jsonl", [{"task": "StopCube", "tier": "xhard2", "seed": 101}])
    with pytest.raises(H.ParityError, match="交付清单之外"):
        _generate(["generate", "--side", "H2", "--tier", "v9", "--manifest", str(delivery), "--src-root", str(REPO),
                   "--out", str(tmp_path / "v9b"), "--dev-smoke", "--specs-root", str(tmp_path),
                   "--identities", str(stray)])


def test_其他档给子集仍报错(fake_run, tmp_path):
    subset = _write_subset(tmp_path / "s.jsonl", [{"task": "PickXtimes", "tier": "easy", "seed": 1}])
    with pytest.raises(H.ParityError, match="--identities 只用于"):
        _generate(["generate", "--side", "H", "--tier", "native", "--manifest", str(MANIFEST), "--src-root",
                   str(REPO), "--out", str(tmp_path / "n"), "--dev-smoke", "--identities", str(subset)])
