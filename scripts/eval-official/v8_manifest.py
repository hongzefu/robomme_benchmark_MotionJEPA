#!/usr/bin/env python3
"""V8 双模型评估执行清单（1001-v8-post-evaluation-gl-plan.md 第一部分 §3、第二部分 §2；接口契约 C1）。

    python scripts/eval-official/v8_manifest.py --identities <eval-identities-1262.jsonl> \\
        --delivery <gen1/delivery.local.json> --shards 10 --out-dir <dir>

四步，任何一步不过即打印 ``V8_EVAL_SHARDS=FAIL ...`` 并以非零退出（不写任何产物）：

1. 核源集：``export_eval_identities.py`` 的 1262 行（xhard0 16×12=192 + 新值 43 格 1070），逐格对
   ``hard_specs.EXPECTED_CELLS``；xhard0 行 candidate=null、source_episode 为整数，新值行 candidate 为整数、
   source_episode=null；(task, episode) 唯一。
2. 筛五档新值 1070 行，xhard0 在这一步丢弃并计数。
3. 按 ``(task, tier, seed, candidate)`` 连 gen1 交付行补 ``spec_sha256``——**不用交付行的 episode**
   （那是格内序号，不是 builder episode）；连不上（missing）或一对多（duplicate）即停；交付行未被用到记 extra。
4. 核执行清单：43 格、1070 行、xhard0=0、指纹齐全、``key`` 唯一。

然后按任务历史耗时（``TASK_SECONDS``，档位无关）做最长处理时间优先的贪心均衡切片，两模型用同一分片；
核对分片两两不交、并集等于执行清单后写：

- ``<out-dir>/manifest.json``：``{schema, source_sha256, delivery_sha256, xhard0_dropped, total, cells, shards, rows}``；
- ``<out-dir>/shard-NN.json``：执行身份行数组，每行
  ``{task, tier, seed, candidate, builder_episode, source_episode, spec_sha256, effective_max_steps, key}``，
  ``key = f"{task}_{tier}_{seed}"``。

末行 ``V8_EVAL_SHARDS=PASS shards=10 missing=0 extra=0 duplicate=0 total=1070 cells=43 xhard0=0``。
只用标准库，``hard_specs`` 按文件路径加载（不 import robomme_hard 包，不触发 sapien）。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
HARD_SPECS_PATH = REPO / "src" / "robomme_hard" / "env_record_wrapper" / "hard_specs.py"

SCHEMA = "v8-eval-manifest/1"
DELIVERY_SCHEMA = "v8-delivery/1"
SOURCE_KEYS = ("task", "episode", "tier", "seed", "candidate", "source_episode", "round", "shard")
SHARD_ROW_KEYS = ("task", "tier", "seed", "candidate", "builder_episode", "source_episode", "spec_sha256",
                  "effective_max_steps", "key")
DEFAULT_SHARDS = 10

#: 每任务平均单局用时（秒），复制自 ``scripts/injection-dev/export_eval_identities.py::TASK_SECONDS``
#: （该脚本 import ``_common`` 改 sys.path，不便跨目录 import；数值逐字相同，测试核对两者一致）。
TASK_SECONDS = {
    "BinFill": 224.0, "ButtonUnmask": 116.5, "ButtonUnmaskSwap": 73.4, "InsertPeg": 152.2, "MoveCube": 180.3,
    "PatternLock": 79.8, "PickHighlight": 246.7, "PickXtimes": 114.2, "RouteStick": 74.1, "StopCube": 64.9,
    "SwingXtimes": 90.8, "VideoPlaceButton": 58.0, "VideoPlaceOrder": 61.7, "VideoRepick": 51.9, "VideoUnmask": 97.4,
    "VideoUnmaskSwap": 50.5,
}


class ManifestError(RuntimeError):
    """四步转换中的任何不符：带计数，main 据此打印 FAIL 行。"""

    def __init__(self, stage: str, detail: str, **counts):
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail
        self.counts = counts


def load_hard_specs():
    """按文件路径加载 ``hard_specs``（只依赖标准库）。"""
    name = "_v8_manifest_hard_specs"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, HARD_SPECS_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def v8_key(row: dict) -> str:
    return f"{row['task']}_{row['tier']}_{int(row['seed'])}"


def cell_name(task: str, tier: str) -> str:
    return f"{task}@{tier}"


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ManifestError("source", f"第 {i} 行不是 JSON：{e}") from e
    return rows


# ── 第 1 步：核源集 ──────────────────────────────────────────────────────────


def check_source(rows: list[dict], hs) -> dict:
    cells = hs.EXPECTED_CELLS
    xhard0_expected = len(hs.ALL_TASKS) * hs.XHARD0_PER_TASK
    total_expected = xhard0_expected + sum(cells.values())
    bad = []
    seen = set()
    per_cell: dict[tuple[str, str], int] = defaultdict(int)
    xhard0 = 0
    for i, r in enumerate(rows):
        if set(r) != set(SOURCE_KEYS):
            bad.append(f"row{i} keys={sorted(r)}")
            continue
        tk = (r["task"], r["episode"])
        if tk in seen:
            bad.append(f"row{i} duplicate (task,episode)={tk}")
        seen.add(tk)
        if not _is_int(r["episode"]) or not _is_int(r["seed"]):
            bad.append(f"row{i} episode/seed 非整数")
        if r["tier"] == hs.XHARD0:
            xhard0 += 1
            if r["candidate"] is not None or not _is_int(r["source_episode"]):
                bad.append(f"row{i} xhard0 行 candidate 须为 null、source_episode 须为整数")
        else:
            if not _is_int(r["candidate"]) or r["source_episode"] is not None:
                bad.append(f"row{i} 新值行 candidate 须为整数、source_episode 须为 null")
            per_cell[(r["task"], r["tier"])] += 1
    cell_mismatch = sum(per_cell.get(k, 0) != n for k, n in cells.items()) + sum(k not in cells for k in per_cell)
    if bad or len(rows) != total_expected or xhard0 != xhard0_expected or cell_mismatch:
        raise ManifestError("source", f"源集不符 rows={len(rows)} expected={total_expected} xhard0={xhard0} "
                                      f"expected_xhard0={xhard0_expected} cell_mismatch={cell_mismatch} "
                                      f"bad={bad[:5]}", total=len(rows), xhard0=xhard0, cells=len(per_cell))
    return {"rows": len(rows), "xhard0": xhard0, "cells": len(per_cell)}


# ── 第 2、3 步：筛新值、连交付补指纹 ─────────────────────────────────────────


def filter_new(rows: list[dict], hs) -> tuple[list[dict], int]:
    new = [r for r in rows if r["tier"] != hs.XHARD0]
    return new, len(rows) - len(new)


def join_delivery(new_rows: list[dict], delivery: dict, hs) -> list[dict]:
    if delivery.get("schema") != DELIVERY_SCHEMA:
        raise ManifestError("delivery", f"交付 schema={delivery.get('schema')!r}，期望 {DELIVERY_SCHEMA}")
    index: dict[tuple, list[dict]] = defaultdict(list)
    for d in delivery.get("rows") or []:
        index[(d["task"], d["tier"], int(d["seed"]), d["candidate"])].append(d)
    out, missing, duplicate = [], [], []
    used: set[tuple] = set()
    for r in new_rows:
        jk = (r["task"], r["tier"], int(r["seed"]), r["candidate"])
        hits = index.get(jk, [])
        if not hits:
            missing.append(jk)
            continue
        if len(hits) > 1:
            duplicate.append(jk)
            continue
        if jk in used:  # 两条身份行连到同一交付行，也是一对多
            duplicate.append(jk)
            continue
        used.add(jk)
        sha = hits[0].get("spec_sha256")
        tier = r["tier"]
        out.append({"task": r["task"], "tier": tier, "seed": int(r["seed"]), "candidate": int(r["candidate"]),
                    "builder_episode": int(r["episode"]), "source_episode": r["source_episode"], "spec_sha256": sha,
                    "effective_max_steps": int(hs.TIER_MAX_STEPS[tier]), "key": v8_key(r)})
    extra = [k for k in index if k not in used]
    if missing or duplicate or extra:
        raise ManifestError("join", f"连接交付行失败 missing={missing[:5]} duplicate={duplicate[:5]} extra={extra[:5]}",
                            missing=len(missing), duplicate=len(duplicate), extra=len(extra))
    return out


# ── 第 4 步：核执行清单 ──────────────────────────────────────────────────────


def check_exec(rows: list[dict], hs) -> dict:
    cells = hs.EXPECTED_CELLS
    per_cell: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        per_cell[(r["task"], r["tier"])] += 1
    xhard0 = sum(r["tier"] == hs.XHARD0 for r in rows)
    no_sha = sum(not (isinstance(r["spec_sha256"], str) and len(r["spec_sha256"]) == 64
                      and all(c in "0123456789abcdef" for c in r["spec_sha256"])) for r in rows)
    keys = [r["key"] for r in rows]
    dup = len(keys) - len(set(keys))
    cap_bad = sum(r["effective_max_steps"] != hs.V8_EXEC_CAP for r in rows)
    cell_mismatch = sum(per_cell.get(k, 0) != n for k, n in cells.items()) + sum(k not in cells for k in per_cell)
    total = sum(cells.values())
    if len(rows) != total or xhard0 or no_sha or dup or cap_bad or cell_mismatch or len(per_cell) != len(cells):
        raise ManifestError("exec", f"执行清单不符 rows={len(rows)} expected={total} xhard0={xhard0} no_sha={no_sha} "
                                    f"dup_key={dup} cap_bad={cap_bad} cell_mismatch={cell_mismatch}",
                            total=len(rows), xhard0=xhard0, duplicate=dup, cells=len(per_cell))
    return {"total": len(rows), "cells": len(per_cell), "xhard0": xhard0}


# ── 分片 ─────────────────────────────────────────────────────────────────────


def balance(rows: list[dict], shards: int) -> list[list[dict]]:
    """最长处理时间优先：按估计用时降序（同用时按 task、tier、builder_episode），逐局分给当前总用时最小的片。"""
    load = [0.0] * shards
    out: list[list[dict]] = [[] for _ in range(shards)]
    for r in sorted(rows, key=lambda r: (-TASK_SECONDS[r["task"]], r["task"], r["tier"], r["builder_episode"])):
        k = min(range(shards), key=lambda i: (load[i], i))
        out[k].append(r)
        load[k] += TASK_SECONDS[r["task"]]
    for part in out:
        part.sort(key=lambda r: (r["task"], r["tier"], r["builder_episode"]))
    return out


def check_shards(parts: list[list[dict]], rows: list[dict]) -> dict:
    want = {r["key"] for r in rows}
    seen: dict[str, int] = defaultdict(int)
    for p in parts:
        for r in p:
            seen[r["key"]] += 1
    return {"missing": len(want - set(seen)), "extra": len(set(seen) - want),
            "duplicate": sum(n - 1 for n in seen.values() if n > 1)}


def build(identities: Path, delivery_path: Path, shards: int) -> tuple[dict, list[list[dict]]]:
    hs = load_hard_specs()
    src = read_jsonl(identities)
    check_source(src, hs)
    new, dropped = filter_new(src, hs)
    delivery = json.loads(Path(delivery_path).read_text(encoding="utf-8"))
    rows = join_delivery(new, delivery, hs)
    facts = check_exec(rows, hs)
    if shards < 1:
        raise ManifestError("shards", f"shards={shards}")
    parts = balance(rows, shards)
    chk = check_shards(parts, rows)
    if any(chk.values()):
        raise ManifestError("shards", f"分片不符 {chk}", **chk)
    cells: dict[str, int] = defaultdict(int)
    for r in rows:
        cells[cell_name(r["task"], r["tier"])] += 1
    order = {k: i for i, k in enumerate(hs.EXPECTED_CELLS)}
    manifest_rows = []
    for i, p in enumerate(parts):
        for r in p:
            manifest_rows.append(dict(r, shard=f"{i:02d}"))
    manifest_rows.sort(key=lambda r: (order[(r["task"], r["tier"])], r["builder_episode"]))
    manifest = {
        "schema": SCHEMA,
        "source_sha256": file_sha256(identities),
        "delivery_sha256": file_sha256(delivery_path),
        "xhard0_dropped": dropped,
        "total": facts["total"],
        "cells": {cell_name(*k): cells[cell_name(*k)] for k in hs.EXPECTED_CELLS},
        "shards": {f"{i:02d}": len(p) for i, p in enumerate(parts)},
        "rows": manifest_rows,
    }
    return manifest, parts


def write_outputs(out_dir: Path, manifest: dict, parts: list[list[dict]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(parts):
        doc = [{k: r[k] for k in SHARD_ROW_KEYS} for r in p]
        (out_dir / f"shard-{i:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                                     encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8")


def verify_outputs(out_dir: Path, manifest: dict, shards: int) -> dict:
    """从磁盘读回（JSON 往返）再核一次：分片两两不交、并集等于 manifest.rows。"""
    back = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    parts = [json.loads((out_dir / f"shard-{i:02d}.json").read_text(encoding="utf-8")) for i in range(shards)]
    chk = check_shards(parts, back["rows"])
    chk["roundtrip_mismatch"] = int(back != manifest) + sum(
        set(r) != set(SHARD_ROW_KEYS) for p in parts for r in p)
    return chk


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--identities", required=True, help="export_eval_identities.py 的 1262 行 JSONL")
    ap.add_argument("--delivery", required=True, help="gen1 delivery.local.json（schema v8-delivery/1）")
    ap.add_argument("--shards", type=int, default=DEFAULT_SHARDS)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)
    try:
        manifest, parts = build(Path(args.identities), Path(args.delivery), args.shards)
        write_outputs(out_dir, manifest, parts)
        chk = verify_outputs(out_dir, manifest, args.shards)
        if any(chk.values()):
            raise ManifestError("verify", f"读回核对不符 {chk}", **chk)
    except ManifestError as e:
        c = e.counts
        print(f"V8_EVAL_SHARDS=FAIL shards={args.shards} missing={c.get('missing', 0)} extra={c.get('extra', 0)} "
              f"duplicate={c.get('duplicate', 0)} total={c.get('total', 'NA')} cells={c.get('cells', 'NA')} "
              f"xhard0={c.get('xhard0', 'NA')} stage={e.stage} detail={e.detail}", flush=True)
        return 1
    for name, n in manifest["shards"].items():
        est = sum(TASK_SECONDS[r["task"]] for r in parts[int(name)])
        print(f"SHARD {name} rows={n} est_s={est:.0f}", flush=True)
    print(f"V8_EVAL_SHARDS=PASS shards={args.shards} missing=0 extra=0 duplicate=0 total={manifest['total']} "
          f"cells={len(manifest['cells'])} xhard0=0", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
