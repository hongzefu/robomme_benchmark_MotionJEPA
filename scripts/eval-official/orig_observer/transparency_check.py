"""代理透明性对账：客户端逐条 send/recv 的 sha256 与代理入口／出口逐条对照（方案第二部分 §2 ``OBSERVER_TRANSPARENT``）。

对账口径：
- 客户端 ``send`` 第 i 条 ↔ 代理同一连接 ``c2s`` 第 i 条（代理收到并原样转发给 server 的那条）；
- 代理 ``s2c`` 第 i 条（从 server 收到并原样转发）↔ 客户端 ``recv`` 第 i 条；
- 比对帧类型、字节长度、sha256 与顺序。连接按内容配对（客户端第 k 条连接 ↔ 代理里消息序列与之最吻合的连接），
  不依赖进程内连接序号（每遍重评会重起客户端进程，代理常驻）。

用法：python transparency_check.py --rec-root <REC_ROOT> [--out report.json]
输出一行：``OBSERVER_TRANSPARENT=PASS|FAIL messages=<n> mismatch=<m> conns=<k> unmatched_conns=<u>``
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path


def _read(paths):
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


def load_client(rec_root: Path) -> dict:
    """{(pid, conn): {"send": [...], "recv": [...]}}，每条 (idx, type, len, sha256)。"""
    out: dict = collections.defaultdict(lambda: {"send": [], "recv": []})
    for r in _read(sorted(rec_root.glob("client-transport-*.jsonl"))):
        out[(r["pid"], r["conn"])][r["dir"]].append((r["idx"], r["type"], r["len"], r["sha256"]))
    return dict(out)


def load_proxy(rec_root: Path) -> dict:
    """{(proxy_file, conn): {"c2s": [...], "s2c": [...]}}。"""
    out: dict = collections.defaultdict(lambda: {"c2s": [], "s2c": []})
    for p in sorted((rec_root / "proxy").glob("proxy-*.jsonl")):
        for r in _read([p]):
            if r.get("kind") == "msg":
                out[(p.name, r["conn"])][r["dir"]].append((r["idx"], r["type"], r["len"], r["sha256"]))
    return dict(out)


def _cmp(a: list, b: list) -> tuple[int, int]:
    """(对上的条数, 不符条数)；按 idx 排序后逐位比，长度差计入不符。"""
    a = sorted(a)
    b = sorted(b)
    ok = sum(1 for x, y in zip(a, b) if x == y)
    bad = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
    # idx 必须是 0..n-1 连续（顺序不乱、不缺）
    bad += sum(1 for i, x in enumerate(a) if x[0] != i) + sum(1 for i, y in enumerate(b) if y[0] != i)
    return ok, bad


def check(rec_root: Path) -> dict:
    client = load_client(rec_root)
    proxy = load_proxy(rec_root)
    used = set()
    pairs, messages, mismatch, unmatched = [], 0, 0, 0
    for ck in sorted(client):
        c = client[ck]
        best, best_score = None, None
        for pk, p in proxy.items():
            if pk in used:
                continue
            ok1, bad1 = _cmp(c["send"], p["c2s"])
            ok2, bad2 = _cmp(p["s2c"], c["recv"])
            score = (ok1 + ok2, -(bad1 + bad2))
            if best_score is None or score > best_score:
                best, best_score = pk, score
        n = len(c["send"]) + len(c["recv"])
        if best is None or best_score[0] == 0:
            unmatched += 1
            mismatch += n
            pairs.append({"client": list(ck), "proxy": None, "messages": n})
            continue
        used.add(best)
        p = proxy[best]
        ok1, bad1 = _cmp(c["send"], p["c2s"])
        ok2, bad2 = _cmp(p["s2c"], c["recv"])
        messages += ok1 + ok2
        mismatch += bad1 + bad2
        pairs.append({"client": list(ck), "proxy": list(best), "c2s_ok": ok1, "c2s_bad": bad1,
                      "s2c_ok": ok2, "s2c_bad": bad2})
    extra = [list(k) for k in proxy if k not in used]
    ok = mismatch == 0 and unmatched == 0 and messages > 0 and not extra  # 代理多出的连接也算不透明
    return {"OBSERVER_TRANSPARENT": "PASS" if ok else "FAIL", "messages": messages, "mismatch": mismatch,
            "conns": len(client), "unmatched_conns": unmatched, "proxy_only_conns": extra, "pairs": pairs}


def verdict_line(rep: dict) -> str:
    return (f"OBSERVER_TRANSPARENT={rep['OBSERVER_TRANSPARENT']} messages={rep['messages']} "
            f"mismatch={rep['mismatch']} conns={rep['conns']} unmatched_conns={rep['unmatched_conns']} "
            f"proxy_only_conns={len(rep['proxy_only_conns'])}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="代理透明性对账")
    ap.add_argument("--rec-root", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    rep = check(Path(a.rec_root))
    if a.out:
        Path(a.out).write_text(json.dumps(rep, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(verdict_line(rep), flush=True)
    return 0 if rep["OBSERVER_TRANSPARENT"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
