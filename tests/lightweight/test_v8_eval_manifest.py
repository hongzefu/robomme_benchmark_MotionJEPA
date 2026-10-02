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


def test_夹具规模(monkeypatch):
    # V8 夹具（1262 身份／1070 交付）：v9 阶段 3b 起 EXPECTED_CELLS 是 V9_CELLS，本文件 V8 用例钉回 V8 表
    monkeypatch.setattr(HS, "EXPECTED_CELLS", HS.V8_CELLS)
    src, d = _source_and_delivery()
    assert len(src) == 1262 and len(d["rows"]) == 1070 and len(HS.EXPECTED_CELLS) == 43


def test_正常_十片_判定行_往返_nullable(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(HS, "EXPECTED_CELLS", HS.V8_CELLS)  # V8 夹具钉 V8 表（同 test_夹具规模）
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


def test_执行清单xhard0混入与格数不符(monkeypatch):
    monkeypatch.setattr(HS, "EXPECTED_CELLS", HS.V8_CELLS)  # V8 夹具钉 V8 表（同 test_夹具规模）
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


def test_读回核对不过即删本次产物(tmp_path, capsys, monkeypatch):
    src, d = _source_and_delivery()
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("other")  # 目录里其他文件不动
    monkeypatch.setattr(M, "verify_outputs", lambda *a, **k: {"missing": 0, "extra": 0, "duplicate": 1,
                                                                "roundtrip_mismatch": 0})
    rc, last, out = _run(tmp_path, src, d, capsys)
    assert rc != 0 and "stage=verify" in last and "duplicate=1" in last
    assert not (out / "manifest.json").exists() and not list(out.glob("shard-*.json"))
    assert (out / "keep.txt").read_text() == "other"


# ── V9：--exclude-evaluated（1002 方案第二部分 §2.1 S1-F）────────────────────────

#: V8 InsertPeg xhard4 实际交付的 20 个候选号（V8 manifest 真实值，均 < 29）
V8_INSERTPEG_CANDS = [0, 1, 4, 5, 6, 7, 8, 10, 12, 13, 14, 15, 16, 17, 19, 21, 22, 23, 25, 28]


def _seed(ti, tier, c):
    return 16_000_000 + 100_000 * ti + 1000 * int(tier[-1]) + c


def _sha(*parts):
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def _v9_fixture():
    """合成 V8 manifest（V8_CELLS 1070 行）+ V9 992 身份（xhard0 192 + V9_CELLS 800）+ V9 800 行交付。

    子集格取 V8 同格候选号最小的 N 个（四元组与 V8 逐字相同）；MoveCube xhard4 候选号 0～49 与 V8 同 seed、
    spec_sha256 不同（R-3）；InsertPeg xhard4 = V8 的 20 局 + 候选号 29～58 的 30 局新局。"""
    ti_of = {t: i for i, t in enumerate(HS.ALL_TASKS)}
    v8_cands = {k: (V8_INSERTPEG_CANDS if k == ("InsertPeg", "xhard4") else list(range(n)))
                for k, n in HS.V8_CELLS.items()}
    v8_rows = []
    for (task, tier), cands in v8_cands.items():
        assert len(cands) == HS.V8_CELLS[(task, tier)]
        for c in cands:
            seed = _seed(ti_of[task], tier, c)
            v8_rows.append({"task": task, "tier": tier, "seed": seed, "candidate": c, "builder_episode": c,
                            "source_episode": None, "spec_sha256": _sha("v8", task, tier, c),
                            "effective_max_steps": 1600, "key": f"{task}_{tier}_{seed}", "shard": "00"})
    v8_man = {"schema": "v8-eval-manifest/1", "total": len(v8_rows), "rows": v8_rows}
    src, deliv = [], []
    for task in HS.ALL_TASKS:
        ti = ti_of[task]
        ep = 0
        for j, se in enumerate(HS.XHARD0_EPISODES):
            src.append({"task": task, "episode": ep, "tier": "xhard0", "seed": 500000 + 1000 * ti + j,
                        "candidate": None, "source_episode": se, "round": None, "shard": None})
            ep += 1
        for (t, tier), n in HS.V9_CELLS.items():
            if t != task:
                continue
            if task == "MoveCube":
                items = [(c, _sha("v9", task, tier, c)) for c in range(n)]  # 与 V8 同 seed、不同布局
            elif task == "InsertPeg":
                items = [(c, _sha("v8", task, tier, c)) for c in V8_INSERTPEG_CANDS]
                items += [(c, _sha("v9", task, tier, c)) for c in range(29, 29 + n - len(V8_INSERTPEG_CANDS))]
            else:
                items = [(c, _sha("v8", task, tier, c)) for c in v8_cands[(task, tier)][:n]]
            for c, sha in items:
                seed = _seed(ti, tier, c)
                src.append({"task": task, "episode": ep, "tier": tier, "seed": seed, "candidate": c,
                            "source_episode": None, "round": None, "shard": None})
                deliv.append({"task": task, "tier": tier, "candidate": c, "seed": seed, "episode": c,
                              "spec_sha256": sha})
                ep += 1
    return src, {"schema": "v8-delivery/1", "rows": deliv}, v8_man


def _run_v9(tmp_path, src, delivery, v8_man, capsys, shards=10):
    ip, dp = _write(tmp_path, src, delivery)
    vp = tmp_path / "v8-manifest.json"
    vp.write_text(json.dumps(v8_man))
    out = tmp_path / "out"
    rc = M.main(["--identities", str(ip), "--delivery", str(dp), "--shards", str(shards), "--out-dir", str(out),
                 "--exclude-evaluated", str(vp)])
    last = capsys.readouterr().out.strip().splitlines()[-1]
    return rc, last, out, vp


def test_v9剔除已评身份(tmp_path, capsys):
    src, d, v8 = _v9_fixture()
    assert len(src) == 992 and len(d["rows"]) == 800 and len(v8["rows"]) == 1070
    rc, last, out, vp = _run_v9(tmp_path, src, d, v8, capsys)
    assert rc == 0, last
    raw = (out / "reused.json").read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    assert last == (f"V9_EVAL_SHARDS=PASS shards=10 total=80 cells=2 reused=720 reused_sha256={sha[:12]} "
                    "missing=0 extra=0 duplicate=0 xhard0=0")
    # reused.json 契约：schema、计数、行字段、排序、确定性写法、v8_key 取 V8 manifest 的 key 原值
    doc = json.loads(raw)
    assert set(doc) == {"schema", "v8_manifest", "v8_manifest_sha256", "count", "rows"}
    assert doc["schema"] == "v9-eval-reused/1" and doc["count"] == len(doc["rows"]) == 720
    assert doc["v8_manifest"] == str(vp) and doc["v8_manifest_sha256"] == hashlib.sha256(vp.read_bytes()).hexdigest()
    assert raw.decode() == json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    assert [(r["task"], r["tier"], r["seed"]) for r in doc["rows"]] == sorted(
        (r["task"], r["tier"], r["seed"]) for r in doc["rows"])
    v8_by_quad = {(r["task"], r["tier"], r["seed"], r["spec_sha256"]): r["key"] for r in v8["rows"]}
    for r in doc["rows"]:
        assert set(r) == {"task", "tier", "seed", "spec_sha256", "v8_key"}
        assert v8_by_quad[(r["task"], r["tier"], r["seed"], r["spec_sha256"])] == r["v8_key"]
    assert not any(r["task"] == "MoveCube" for r in doc["rows"])
    assert sum(r["task"] == "InsertPeg" for r in doc["rows"]) == 20
    # manifest：字段同 V8，只多 reused 一键；只含新评 80 行、两格
    man = json.loads((out / "manifest.json").read_text())
    assert set(man) == {"schema", "source_sha256", "delivery_sha256", "xhard0_dropped", "total", "cells", "shards",
                        "rows", "reused"}
    assert man["schema"] == "v8-eval-manifest/1" and man["total"] == 80 and man["xhard0_dropped"] == 192
    assert man["cells"] == {"MoveCube@xhard4": 50, "InsertPeg@xhard4": 30}
    assert man["reused"]["sha256"] == sha and man["reused"]["count"] == 720 and man["reused"]["path"] == "reused.json"
    assert all(r["candidate"] >= 29 for r in man["rows"] if r["task"] == "InsertPeg")
    # 同 seed 不同 spec_sha256（MoveCube 候选号 0～19 与 V8 同 seed）一律不剔除
    v8_seeds = {(r["task"], r["tier"], r["seed"]) for r in v8["rows"]}
    same_seed = [r for r in man["rows"] if (r["task"], r["tier"], r["seed"]) in v8_seeds]
    assert len(same_seed) == 20 and all(r["task"] == "MoveCube" for r in same_seed)
    # 十片两两不交、并集 80、均衡（每片 8 局）
    parts = [json.loads((out / f"shard-{i:02d}.json").read_text()) for i in range(10)]
    keys = [r["key"] for p in parts for r in p]
    assert len(keys) == len(set(keys)) == 80 and set(keys) == {r["key"] for r in man["rows"]}
    assert [len(p) for p in parts] == [8] * 10
    assert all(set(r) == set(M.SHARD_ROW_KEYS) for p in parts for r in p)


def test_v9四元组一处不同即不剔除_新评集合不符即停(tmp_path, capsys):
    src, d, v8 = _v9_fixture()
    i = next(i for i, r in enumerate(d["rows"]) if r["task"] == "PickXtimes")
    d["rows"][i]["spec_sha256"] = "f" * 64  # 子集行 spec_sha256 不同：不命中 V8 → 落进新评 → 不符规则
    rc, last, out, _ = _run_v9(tmp_path, src, d, v8, capsys)
    assert rc != 0 and last.startswith("V9_EVAL_SHARDS=FAIL") and "stage=exclude" in last and "extra=1" in last
    assert not (out / "manifest.json").exists() and not (out / "reused.json").exists()


def test_v9规则内命中V8即停(tmp_path, capsys):
    src, d, v8 = _v9_fixture()
    i = next(i for i, r in enumerate(d["rows"]) if r["task"] == "MoveCube" and r["candidate"] == 3)
    d["rows"][i]["spec_sha256"] = _sha("v8", "MoveCube", "xhard4", 3)  # 新局却与 V8 四元组相同
    rc, last, _, _ = _run_v9(tmp_path, src, d, v8, capsys)
    assert rc != 0 and "stage=exclude" in last and "missing=1" in last


def test_v9格表须为登记表(tmp_path, capsys):
    src, d, v8 = _v9_fixture()
    j = next(j for j, r in enumerate(d["rows"]) if r["task"] == "BinFill")
    d["rows"].pop(j)
    rc, last, _, _ = _run_v9(tmp_path, src, d, v8, capsys)
    assert rc != 0 and "stage=cells" in last


def test_v9_V8manifest四元组重复即停(tmp_path, capsys):
    src, d, v8 = _v9_fixture()
    v8["rows"].append(dict(v8["rows"][0], key="X_xhard1_1"))
    rc, last, _, _ = _run_v9(tmp_path, src, d, v8, capsys)
    assert rc != 0 and "stage=exclude" in last and "duplicate=1" in last


def test_v9读回核对不过即删reused(tmp_path, capsys, monkeypatch):
    src, d, v8 = _v9_fixture()
    monkeypatch.setattr(M, "verify_outputs", lambda *a, **k: {"reused_mismatch": 1})
    rc, last, out, _ = _run_v9(tmp_path, src, d, v8, capsys)
    assert rc != 0 and "stage=verify" in last
    assert not (out / "reused.json").exists() and not (out / "manifest.json").exists()
