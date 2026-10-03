"""``scripts/eval-official/claim_queue.py``（NFS 认领队列）的纯 CPU 测试。

覆盖：多进程认领竞争（每身份恰好被认领一次）、认领后崩溃、结果已写未确认、半行 JSON、旧进程迟到提交、
无进展回收只一次、重试额度跨实例持续、init 幂等与冲突、``check`` 判定行。
按文件路径加载（目录名带连字符）。
"""
from __future__ import annotations

import importlib.util
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
QPATH = REPO / "scripts" / "eval-official" / "claim_queue.py"


def _load():
    if "claim_queue" in sys.modules:
        return sys.modules["claim_queue"]
    spec = importlib.util.spec_from_file_location("claim_queue", QPATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["claim_queue"] = mod
    spec.loader.exec_module(mod)
    return mod


Q = _load()


def _idents(n=12):
    tasks = ["PickXtimes", "BinFill", "StopCube"]
    return [{"task": tasks[i % 3], "source_episode": 3 + 4 * (i // 3), "seed": 500000 + i,
             "builder_episode": i // 3} for i in range(n)]


def _queue(tmp_path, n=12, budget=8):
    q = Q.ClaimQueue(tmp_path / "q" / "mme")
    q.init(_idents(n), retry_budget=budget)
    return q


def _worker(root, seat, out):
    q = Q.ClaimQueue(root)
    got = []
    while True:
        c = q.claim_next(seat)
        if c is None:
            break
        got.append(c.key)
        assert q.complete(c, {"task": c.key.rsplit("_", 1)[0], "seed": int(c.key.rsplit("_", 1)[1]),
                              "status": "success", "seat": seat})
    Path(out).write_text(json.dumps(got))


def test_多进程认领竞争_每身份恰好一次(tmp_path):
    q = _queue(tmp_path, n=60)
    ctx = mp.get_context("fork")
    outs = [tmp_path / f"w{i}.json" for i in range(6)]
    ps = [ctx.Process(target=_worker, args=(str(q.root), f"s{i}", str(outs[i]))) for i in range(6)]
    for p in ps:
        p.start()
    for p in ps:
        p.join(60)
        assert p.exitcode == 0
    keys = sum((json.loads(o.read_text()) for o in outs), [])
    assert len(keys) == 60 and len(set(keys)) == 60
    st = q.check()
    assert st["dup"] == 0 and st["missing"] == 0 and st["open_claims"] == 0
    assert Q.check_line(st).startswith("QUEUE_CLAIM=PASS dup=0 missing=0 requeued=0")


def test_init幂等_内容不同拒绝(tmp_path):
    q = _queue(tmp_path)
    q.init(_idents())  # 幂等
    with pytest.raises(RuntimeError):
        q.init(_idents()[:5])
    doc = json.loads((q.root / "order.json").read_text())
    assert doc["shuffle_seed"] == 20260930 and sorted(doc["keys"]) == sorted(Q.key_of(r) for r in _idents())
    assert doc["keys"] == Q.ClaimQueue.shuffled_keys(_idents(), 20260930)


def _fake_dead_claim(q, key, seat):
    """伪造一个「认领后进程崩溃」的认领文件（pid 不是本进程）。"""
    doc = {"key": key, "seat": seat, "host": "deadhost", "pid": 1, "time": time.time(), "attempt": 1,
           "token": "dead" + "0" * 28}
    (q.claims / f"{key}.claim").write_text(json.dumps(doc))
    return Q.Claim(doc)


def test_认领后崩溃_重启回收并消耗额度(tmp_path):
    q = _queue(tmp_path, budget=3)
    key = q.order()[0]
    _fake_dead_claim(q, key, "seatA")
    r = q.recover_seat("seatA", tmp_path / "results.jsonl")
    assert r == {"acked": [], "failed": [key]}
    assert not (q.claims / f"{key}.claim").exists() and q.retries_used() == 1
    c = q.claim_next("seatA")
    assert c.key == key and c["attempt"] == 2


def test_结果已写未确认_重启补提交(tmp_path):
    q = _queue(tmp_path)
    key = q.order()[0]
    claim = _fake_dead_claim(q, key, "seatA")
    res = tmp_path / "results.jsonl"
    task, seed = key.rsplit("_", 1)
    Q.append_jsonl(res, {"task": task, "seed": int(seed), "status": "fail", "claim_token": claim.token})
    r = q.recover_seat("seatA", res)
    assert r["acked"] == [key]
    done = json.loads((q.done / f"{key}.json").read_text())
    assert done["status"] == "fail" and q.retries_used() == 0


def test_半行JSON_读时跳过写时补换行(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_text('{"a": 1}\n{"b": 2, "tru')
    Q.append_jsonl(p, {"c": 3})
    rows, bad = Q.read_jsonl_tolerant(p)
    assert rows == [{"a": 1}, {"c": 3}] and bad == 1


def test_旧进程迟到提交被拒(tmp_path):
    q = _queue(tmp_path)
    old = q.claim_next("seatA")
    os.utime(q.claims / f"{old.key}.claim", (time.time() - 5000, time.time() - 5000))
    assert q.reap_stale(1200) == [old.key]
    new = q.claim_next("seatB")
    assert new.key == old.key and new["attempt"] == 2
    task, seed = old.key.rsplit("_", 1)
    rec = {"task": task, "seed": int(seed), "status": "success"}
    assert q.complete(old, rec) is False  # 旧进程迟到
    assert list(q.late.glob(f"{old.key}.*.json"))
    assert q.complete(new, dict(rec, status="fail")) is True
    assert json.loads((q.done / f"{old.key}.json").read_text())["status"] == "fail"
    assert q.complete(new, rec) is False  # 同一身份第二次终态被拒
    st = q.check()
    assert st["dup"] == 0 and st["requeued"] == 1 and st["late"] >= 1


def test_无进展回收只一次_第二次写INFRA_EXHAUSTED(tmp_path):
    q = _queue(tmp_path)
    c = q.claim_next("seatA")
    old = time.time() - 5000
    os.utime(q.claims / f"{c.key}.claim", (old, old))
    assert q.reap_stale(1200) == [c.key]
    c2 = q.claim_next("seatA")
    assert c2.key == c.key
    os.utime(q.claims / f"{c.key}.claim", (old, old))
    assert q.reap_stale(1200) == [c.key]
    done = json.loads((q.done / f"{c.key}.json").read_text())
    assert done["queue_status"] == Q.INFRA_EXHAUSTED
    assert q.check()["infra_exhausted"] == 1


def test_心跳刷新后不回收(tmp_path):
    q = _queue(tmp_path)
    c = q.claim_next("seatA")
    old = time.time() - 5000
    os.utime(q.claims / f"{c.key}.claim", (old, old))
    q.heartbeat(c)
    assert q.reap_stale(1200) == []


def test_重试额度跨实例持续_用完写终态(tmp_path):
    q = _queue(tmp_path, n=3, budget=2)
    outcomes = []
    for _ in range(3):
        c = Q.ClaimQueue(q.root).claim_next("seatA")
        task, seed = c.key.rsplit("_", 1)
        outcomes.append(Q.ClaimQueue(q.root).fail_infra(c, {"task": task, "seed": int(seed), "status": "error",
                                                            "infra": True}))
    assert outcomes == ["requeued", "requeued", "exhausted"]
    assert Q.ClaimQueue(q.root).retries_used() == 2


def test_check_missing与CLI(tmp_path, capsys):
    q = _queue(tmp_path, n=4)
    c = q.claim_next("s")
    task, seed = c.key.rsplit("_", 1)
    q.complete(c, {"task": task, "seed": int(seed), "status": "success"})
    rc = Q.main(["check", "--queue", str(tmp_path / "q"), "--policy", "mme"])
    out = capsys.readouterr().out
    assert rc == 1 and "QUEUE_CLAIM=FAIL dup=0 missing=3" in out
    (q.done / "Bogus_1.json").write_text("{half")
    assert q.check()["dup"] == 1


def test_CLI_init(tmp_path, capsys):
    p = tmp_path / "ids.json"
    p.write_text(json.dumps(_idents(6)))
    assert Q.main(["init", "--queue", str(tmp_path / "q"), "--policy", "smvla", "--identities", str(p)]) == 0
    assert "QUEUE_INIT=PASS policy=smvla n=6" in capsys.readouterr().out


def test_NFS重传幂等_自己的token算成功(tmp_path):
    q = _queue(tmp_path)
    c = q.claim_next("seatA")
    path = q.claims / f"{c.key}.claim"
    assert Q._excl_write(path, "x", token=c.token) is True  # 已存在且是自己的
    assert Q._excl_write(path, "x", token="other") is False
    task, seed = c.key.rsplit("_", 1)
    rec = {"task": task, "seed": int(seed), "status": "success"}
    tmp = q.tmp / "t.json"
    assert q.complete(c, rec)
    tmp.write_text("{}")
    assert Q._link_publish(tmp, q.done / f"{c.key}.json", token=c.token) is True
    tmp.write_text("{}")
    assert Q._link_publish(tmp, q.done / f"{c.key}.json", token="other") is False
    assert q.all_terminal() is False
