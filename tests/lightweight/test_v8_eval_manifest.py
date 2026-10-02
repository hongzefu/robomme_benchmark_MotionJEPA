"""``scripts/eval-official/v8_manifest.py`` 的纯 CPU 测试（合成 1262 源集 + gen1 交付夹具，不读 artifacts、不起仿真）。

覆盖（1001-v8-post-evaluation-gl-plan.md 第二部分 §2 表、契约 C1）：正常四步与十片输出、连接不上、一对多、
xhard0 混入执行清单、格数不符、源集字段不符、分片两两不交且并集等于全集、JSON 往返、nullable 字段、
TASK_SECONDS 与 export_eval_identities 一致、交付行 episode 不参与连接。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EO = REPO / "scripts" / "eval-official"

pytestmark = pytest.mark.lightweight


def _load(name, alias):
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, EO / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load("v8_manifest", "v8_manifest_under_test")
HS = M.load_hard_specs()


def _source_and_delivery():
    """按 EXPECTED_CELLS 合成：每任务 xhard0 12 局 + 新值逐格局数；builder episode 在任务内连续编号。"""
    src, rows = [], []
    for ti, task in enumerate(HS.ALL_TASKS):
        ep = 0
        for j, se in enumerate(HS.XHARD0_EPISODES):
            src.append({"task": task, "episode": ep, "tier": "xhard0", "seed": 500000 + 1000 * ti + j,
                        "candidate": None, "source_episode": se, "round": None, "shard": None})
            ep += 1
        for (t, tier), n in HS.EXPECTED_CELLS.items():
            if t != task:
                continue
            for c in range(n):
                seed = 16_000_000 + 100_000 * ti + 1000 * int(tier[-1]) + c
                src.append({"task": task, "episode": ep, "tier": tier, "seed": seed, "candidate": c,
                            "source_episode": None, "round": None, "shard": None})
                # 交付行的 episode 是格内序号（≠ builder episode），故意与 builder episode 不同
                rows.append({"task": task, "tier": tier, "candidate": c, "seed": seed, "episode": c,
                             "spec_sha256": hashlib.sha256(f"{task}{tier}{c}".encode()).hexdigest()})
                ep += 1
    return src, {"schema": "v8-delivery/1", "rows": rows}


def _write(tmp_path, src, delivery):
    ip = tmp_path / "ids.jsonl"
    ip.write_text("".join(json.dumps(r) + "\n" for r in src))
    dp = tmp_path / "delivery.json"
    dp.write_text(json.dumps(delivery))
    return ip, dp


def _run(tmp_path, src, delivery, capsys, shards=10):
    ip, dp = _write(tmp_path, src, delivery)
    out = tmp_path / "out"
    rc = M.main(["--identities", str(ip), "--delivery", str(dp), "--shards", str(shards), "--out-dir", str(out)])
    last = capsys.readouterr().out.strip().splitlines()[-1]
    return rc, last, out


def test_夹具规模():
    src, d = _source_and_delivery()
    assert len(src) == 1262 and len(d["rows"]) == 1070 and len(HS.EXPECTED_CELLS) == 43


def test_正常_十片_判定行_往返_nullable(tmp_path, capsys):
    src, d = _source_and_delivery()
    rc, last, out = _run(tmp_path, src, d, capsys)
    assert rc == 0
    assert last == "V8_EVAL_SHARDS=PASS shards=10 missing=0 extra=0 duplicate=0 total=1070 cells=43 xhard0=0"
    man = json.loads((out / "manifest.json").read_text())
    assert man["schema"] == "v8-eval-manifest/1" and man["total"] == 1070 and man["xhard0_dropped"] == 192
    assert len(man["cells"]) == 43 and sum(man["cells"].values()) == 1070
    assert man["cells"]["PickXtimes@xhard1"] == 17 and man["cells"]["SwingXtimes@xhard5"] == 10
    assert man["source_sha256"] == hashlib.sha256((tmp_path / "ids.jsonl").read_bytes()).hexdigest()
    assert man["delivery_sha256"] == hashlib.sha256((tmp_path / "delivery.json").read_bytes()).hexdigest()
    parts = [json.loads((out / f"shard-{i:02d}.json").read_text()) for i in range(10)]
    assert sorted(man["shards"]) == [f"{i:02d}" for i in range(10)]
    assert [man["shards"][f"{i:02d}"] for i in range(10)] == [len(p) for p in parts]
    keys = [r["key"] for p in parts for r in p]
    assert len(keys) == len(set(keys)) == 1070  # 两两不交
    assert set(keys) == {r["key"] for r in man["rows"]}  # 并集等于全集
    by_src = {(r["task"], r["tier"], r["seed"]): r for r in src}
    for p in parts:
        for r in p:
            assert set(r) == set(M.SHARD_ROW_KEYS)
            assert r["source_episode"] is None and isinstance(r["candidate"], int)  # nullable 原样保留为 null
            assert r["effective_max_steps"] == 1600 and r["tier"] != "xhard0"
            assert r["key"] == f"{r['task']}_{r['tier']}_{r['seed']}"
            assert r["builder_episode"] == by_src[(r["task"], r["tier"], r["seed"])]["episode"]
            assert r["spec_sha256"] == hashlib.sha256(f"{r['task']}{r['tier']}{r['candidate']}".encode()).hexdigest()
    # JSON 往返：读回再写出逐字节相同
    again = json.dumps(json.loads((out / "manifest.json").read_text()), ensure_ascii=False, indent=1, sort_keys=True)
    assert again + "\n" == (out / "manifest.json").read_text()
    # 均衡：各片估计用时极差不超过最大单局用时
    est = [sum(M.TASK_SECONDS[r["task"]] for r in p) for p in parts]
    assert max(est) - min(est) <= max(M.TASK_SECONDS.values())


def test_连接不上即停(tmp_path, capsys):
    src, d = _source_and_delivery()
    d["rows"] = d["rows"][1:]
    rc, last, out = _run(tmp_path, src, d, capsys)
    assert rc != 0 and last.startswith("V8_EVAL_SHARDS=FAIL") and "missing=1" in last
    assert not (out / "manifest.json").exists()


def test_一对多即停(tmp_path, capsys):
    src, d = _source_and_delivery()
    d["rows"].append(dict(d["rows"][5], episode=999, spec_sha256="0" * 64))
    rc, last, _ = _run(tmp_path, src, d, capsys)
    assert rc != 0 and "duplicate=1" in last and "stage=join" in last


def test_交付多余行记extra(tmp_path, capsys):
    src, d = _source_and_delivery()
    d["rows"].append(dict(d["rows"][0], seed=99, spec_sha256="1" * 64))
    rc, last, _ = _run(tmp_path, src, d, capsys)
    assert rc != 0 and "extra=1" in last


def test_交付行episode不参与连接(tmp_path, capsys):
    src, d = _source_and_delivery()
    for r in d["rows"]:
        r["episode"] = -1
    rc, last, _ = _run(tmp_path, src, d, capsys)
    assert rc == 0 and last.startswith("V8_EVAL_SHARDS=PASS")


def test_源集格数不符即停(tmp_path, capsys):
    src, d = _source_and_delivery()
    i = next(i for i, r in enumerate(src) if r["tier"] == "xhard3")
    src.pop(i)
    rc, last, _ = _run(tmp_path, src, d, capsys)
    assert rc != 0 and "stage=source" in last


def test_源集字段不符即停(tmp_path, capsys):
    src, d = _source_and_delivery()
    i = next(i for i, r in enumerate(src) if r["tier"] == "xhard1")
    src[i]["source_episode"] = 7  # 新值行 source_episode 必须为 null
    rc, last, _ = _run(tmp_path, src, d, capsys)
    assert rc != 0 and "stage=source" in last


def test_执行清单xhard0混入与格数不符():
    src, d = _source_and_delivery()
    new, dropped = M.filter_new(src, HS)
    assert dropped == 192 and all(r["tier"] != "xhard0" for r in new)
    rows = M.join_delivery(new, d, HS)
    assert M.check_exec(rows, HS)["total"] == 1070
    mixed = rows[:-1] + [dict(rows[-1], tier="xhard0", key="X_xhard0_1")]
    with pytest.raises(M.ManifestError) as ei:
        M.check_exec(mixed, HS)
    assert ei.value.counts["xhard0"] == 1
    with pytest.raises(M.ManifestError):
        M.check_exec(rows[:-1], HS)  # 少一行：格数不符
    with pytest.raises(M.ManifestError):
        M.check_exec(rows[:-1] + [dict(rows[-1], spec_sha256=None)], HS)  # 指纹缺失


def test_分片检查能发现重叠与遗漏():
    src, d = _source_and_delivery()
    rows = M.join_delivery(M.filter_new(src, HS)[0], d, HS)
    parts = M.balance(rows, 10)
    assert M.check_shards(parts, rows) == {"missing": 0, "extra": 0, "duplicate": 0}
    bad = [list(p) for p in parts]
    bad[1].append(bad[0][0])
    bad[2].pop()
    chk = M.check_shards(bad, rows)
    assert chk["duplicate"] == 1 and chk["missing"] == 1


def test_TASK_SECONDS与导出脚本一致():
    tree = ast.parse((REPO / "scripts" / "injection-dev" / "export_eval_identities.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "TASK_SECONDS")
    assert ast.literal_eval(node.value) == M.TASK_SECONDS
