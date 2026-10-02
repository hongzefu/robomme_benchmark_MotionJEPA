#!/usr/bin/env python3
"""v9 子集派生、InsertPeg 迁移、整合、hardlink 交付树与逐字节核对（v9 方案第二部分 §2.1 S1-D 行、§2.4.2 第 3～5 步）。

五个子命令（都不起仿真；只有 ``extend`` 的抽签步会 reset 环境，``--dry-run`` 跳过它）：

    # ① 子集派生：14 个子集任务按格表每格取 V8 交付行候选号最小的 N 个，加 InsertPeg xhard4 的 V8 交付 20 局
    uv run --no-sync python scripts/injection-dev/v9_subset_specs.py derive \\
        --v8-root artifacts/newtask-v8/specs-root --v8-gen artifacts/newtask-v8/gen1 \\
        --out artifacts/newtask-v9/subset-root
    # ② InsertPeg 20 → 50 迁移：导入 V8 该格 40 行与 29 条已试终态，配额改 50，追加候选 40～74，写出片根
    uv run --no-sync python scripts/injection-dev/v9_subset_specs.py extend --task InsertPeg --tier xhard4 \\
        --v8-frozen artifacts/newtask-v8/specs-root --v8-shard artifacts/newtask-v8/gen1/shard3 \\
        --quota 50 --append 35 --max-reset-attempts 55 --gpus 0 --out <片根> [--dry-run]
    #    之后生成（片根自带账本，必须 --resume）：
    #    generate_h5.py --mode continue --cells <片根>/cells.json --specs <片根>/specs --output <片根> --resume ...
    # ③ 整合：子集根 + MoveCube 片根 + InsertPeg 片根 → V9 五档规格 + 800 行交付清单
    uv run --no-sync python scripts/injection-dev/v9_subset_specs.py assemble \\
        --subset artifacts/newtask-v9/subset-root --movecube <MoveCube 片根> --insertpeg <InsertPeg 片根> \\
        --v8-delivery artifacts/newtask-v8/gen1/delivery.local.json \\
        --out-specs artifacts/newtask-v9/specs-root --out-delivery artifacts/newtask-v9/delivery/delivery.local.json
    # ④ hardlink 交付树（只 os.link，不复制、不覆盖；幂等）
    uv run --no-sync python scripts/injection-dev/v9_subset_specs.py link \\
        --delivery artifacts/newtask-v9/delivery/delivery.local.json --out artifacts/newtask-v9/delivery
    # ⑤ 复用局逐字节核对
    uv run --no-sync python scripts/injection-dev/v9_subset_specs.py verify \\
        --v8-root artifacts/newtask-v8/specs-root --v8-delivery artifacts/newtask-v8/gen1/delivery.local.json \\
        --v9-root artifacts/newtask-v9/specs-root --v9-delivery artifacts/newtask-v9/delivery/delivery.local.json \\
        --v9-tree artifacts/newtask-v9/delivery

取行规则（v9 方案第一部分 §3「子集怎么取」）：在该格**交付行**（``selected=True`` 且 rollout ``ok``，并与 gen1
``delivery.local.json`` 逐行核对 seed／spec_sha256／h5_sha256）里按候选号升序取前 N 个——不是 header ``select_rule``
的前 N 个（``select_rule`` 是抽签初选，含生成失败、后来被递补掉的候选）。改写 ``delivery_per_cell[task]=N``、
``select_rule[task]`` 为这 N 个候选号、被丢弃交付行 ``selected=False``，重签 ``identity_sha256``／``delivery_sha256``
（与 ``_rollout.split_v8`` 同一重签写法）；``per_env`` 与规格行其余字段逐字节不动。

所有判定行的数值都从数据统计；任一核对不符打印证据、判定行 ``=FAIL`` 并以退出码 1 结束。不 import 任何 ``tests/``。
"""

from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import _common  # noqa: F401  路径设置
import _rollout  # noqa: E402
from _freeze import write_jsonl_exclusive  # noqa: E402

from robomme_hard.env_record_wrapper import hard_specs as H  # noqa: E402

#: 不走子集的任务：MoveCube 整任务重抽（不进 derive）；InsertPeg 在 derive 里只取 V8 交付的全部局，另由 extend 补
NEW_TASKS = ("MoveCube",)
EXTEND_TASKS = ("InsertPeg",)
DERIVE_META = "v9-derive.json"
CELLS_JSON = "cells.json"
SOURCE_REUSE = "v8-reuse"
SOURCE_NEW = "v9-new"


class SubsetError(RuntimeError):
    """v9 子集派生／迁移／整合的前置条件或核对不满足。"""


# ── 通用小工具 ──────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cell_key(task: str, tier: str) -> str:
    return f"{task}@{tier}"


def specs_dir(root: Path) -> Path:
    """片根（含 ``specs/<tier>/specs.jsonl``）或规格根（含 ``<tier>/specs.jsonl``）→ 规格根。"""
    root = Path(root)
    nested = root / "specs"
    if any((nested / tier / "specs.jsonl").is_file() for tier in H.V8_TIERS):
        return nested
    return root


def load_tier(root: Path, tier: str, table: dict[tuple[str, str], int] | None = None):
    """单档 /4 文件读取（``load_specs`` 校验）；``table`` 缺省按 header 自带配额推出（``_rollout.load_specs_any``）。"""
    path = Path(root) / tier / "specs.jsonl"
    if not path.is_file():
        raise SubsetError(f"缺少规格文件 {path}")
    if table is None:
        header, rows = _rollout.load_specs_any(path, check_fingerprint=False)
    else:
        header, rows = H.load_specs(path, expected_cells=table, check_fingerprint=False)
    if header["schema"] != H.SCHEMA_V8 or header["difficulty"] != tier:
        raise SubsetError(f"{path} 须为 {H.SCHEMA_V8} 且档位 {tier}（实为 {header['schema']}／{header['difficulty']}）")
    return header, rows


def delivered_rows(rows: list[dict[str, Any]], task: str) -> list[dict[str, Any]]:
    return sorted((r for r in rows if r["task"] == task and H.delivered(r)), key=lambda r: int(r["candidate"]))


def resign(header: dict[str, Any], rows: list[dict[str, Any]], table: dict[tuple[str, str], int]) -> dict[str, Any]:
    """与 ``_rollout.split_v8`` 同一重签写法：重算 sampling 散列、两个身份散列，再走 /4 单文件校验。"""
    header = copy.deepcopy(header)
    header["sampling_config_sha256"] = H.digest(header["sampling_config"])
    header["identity_sha256"] = H.identity_sha256(header, rows)
    header["delivery_sha256"] = H.delivery_sha256(rows)
    H.validate_specs(header, rows, expected_cells=table)
    return header


def restrict_header(header: dict[str, Any], tasks: list[str]) -> dict[str, Any]:
    """header 只留 ``tasks``（逐任务四个字典同步收窄）。"""
    sub = copy.deepcopy(header)
    sub["tasks"] = list(tasks)
    for key in ("per_env", "select_rule", "delivery_per_cell", "sampling_config"):
        sub[key] = {task: copy.deepcopy(header[key][task]) for task in tasks}
    return sub


def load_delivery(path: Path) -> tuple[dict[str, Any], dict[tuple[str, str, int], dict[str, Any]]]:
    """``v8-delivery/1`` 清单 → (原文, {(task, tier, candidate): 行})；身份重复即拒绝。"""
    path = Path(path)
    if not path.is_file():
        raise SubsetError(f"缺少交付清单 {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != _rollout.V8_DELIVERY_SCHEMA:
        raise SubsetError(f"{path} 不是 {_rollout.V8_DELIVERY_SCHEMA}：{data.get('schema')!r}")
    index: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in data["rows"]:
        key = (row["task"], row["tier"], int(row["candidate"]))
        if key in index:
            raise SubsetError(f"{path} 有重复身份 {key}")
        index[key] = row
    return data, index


def main_video(h5: str | None, row: dict[str, Any]) -> str | None:
    """该局显式目录 ``videos/`` 下的主视频 ``<Task>_ep<e>_seed<s>_*.mp4``（不含 ``success_NO_OBJECT_`` 等前缀副本）；
    清单行自带 ``video`` 时优先用它。找不到或不唯一返回 None。"""
    if row.get("video"):
        return str(row["video"])
    if not h5:
        return None
    videos = sorted((Path(h5).parents[1] / "videos").glob(f"{row['task']}_ep{int(row['episode'])}_seed{int(row['seed'])}_*.mp4"))
    return str(videos[0]) if len(videos) == 1 else None


def check_against_delivery(row: dict[str, Any], drow: dict[str, Any] | None, label: str) -> list[str]:
    """规格交付行与清单行逐字段核对：seed、spec_sha256、h5_sha256（= rollout 段记录值）。"""
    key = f"{row['task']}@{row['tier']}#{row['candidate']}"
    if drow is None:
        return [f"{label}：交付行 {key} 不在清单里"]
    problems = []
    rollout = row.get("rollout") or {}
    for name, want, got in (("seed", int(row["seed"]), int(drow["seed"])),
                            ("spec_sha256", row["spec_sha256"], drow.get("spec_sha256")),
                            ("h5_sha256", rollout.get("h5_sha256"), drow.get("h5_sha256"))):
        if want != got:
            problems.append(f"{label}：{key} 的 {name} 规格={want} 清单={got}")
    return problems


def write_text_exclusive(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as stream:
        stream.write(text)


def fail(prefix: str, problems: list[str], extra: str = "") -> int:
    for item in problems[:40]:
        print(f"# 证据：{item}", flush=True)
    if len(problems) > 40:
        print(f"# 证据：……另有 {len(problems) - 40} 条", flush=True)
    print(f"{prefix}=FAIL problems={len(problems)}{extra}", flush=True)
    return 1


# ── derive ─────────────────────────────────────────────────────────────


def subset_cells(target: dict[tuple[str, str], int] | None = None,
                 source: dict[tuple[str, str], int] | None = None) -> dict[tuple[str, str], int]:
    """derive 的目标格表：V9 表去掉整任务重抽的 MoveCube；InsertPeg 取 V8 交付局数（20）。"""
    target = dict(H.V9_CELLS if target is None else target)
    source = dict(H.V8_CELLS if source is None else source)
    out = {k: n for k, n in target.items() if k[0] not in NEW_TASKS}
    for key in list(out):
        if key[0] in EXTEND_TASKS:
            out[key] = source[key]
    return _rollout.order_cells(out)


def derive(v8_root: Path, v8_delivery: Path, out: Path, *, source_cells: dict[tuple[str, str], int] | None = None,
           target_cells: dict[tuple[str, str], int] | None = None,
           cell_table: dict[tuple[str, str], int] | None = None) -> dict[str, Any]:
    """V8 规格根 + gen1 交付清单 → 子集规格根（只写 ``out``）。返回 {line, picks, problems, ...}。"""
    source_cells = _rollout.order_cells(dict(H.V8_CELLS if source_cells is None else source_cells))
    target_cells = subset_cells(target_cells, source_cells) if target_cells is None else _rollout.order_cells(target_cells)
    table = H.V9_CELLS if cell_table is None else cell_table
    stray = sorted(k for k in target_cells if k not in source_cells)
    if stray:
        raise SubsetError(f"目标格不在 V8 格表里：{stray}")
    out = Path(out)
    targets = [out / tier / "specs.jsonl" for tier in _rollout.cell_tiers(target_cells)] + [out / DERIVE_META]
    existing = [str(p) for p in targets if p.exists()]
    if existing:
        raise SubsetError(f"输出已存在，拒绝覆盖：{existing[:3]}")
    loaded = H.load_specs_v8(v8_root, source_cells, cell_table=H.resolve_cell_table(source_cells),
                             check_fingerprint=False)
    _, dindex = load_delivery(v8_delivery)
    problems: list[str] = []
    # gen1 清单与规格交付行逐格核对（以 delivery.local.json 为准：两边交付集合必须相等）
    for (task, tier) in source_cells:
        rows = loaded[tier][1]
        spec_set = {int(r["candidate"]) for r in delivered_rows(rows, task)}
        list_set = {c for (t, ti, c) in dindex if t == task and ti == tier}
        if spec_set != list_set:
            problems.append(f"{task}@{tier} 规格交付行 {sorted(spec_set - list_set)} 不在清单、清单多出 "
                            f"{sorted(list_set - spec_set)}")
        for row in delivered_rows(rows, task):
            problems += check_against_delivery(row, dindex.get((task, tier, int(row["candidate"]))), "V8 gen1")
        bad = [int(r["candidate"]) for r in rows if r["task"] == task and r["selected"] and not H.delivered(r)]
        if bad:
            problems.append(f"{task}@{tier} 有 selected 却未交付的行 {bad}")
    picks: dict[str, list[int]] = {}
    dropped: dict[str, list[int]] = {}
    for (task, tier), n in target_cells.items():
        pool = [int(r["candidate"]) for r in delivered_rows(loaded[tier][1], task)]
        if len(pool) < n:
            problems.append(f"{task}@{tier} V8 交付行只有 {len(pool)} 个，不够取 {n}")
            continue
        picks[cell_key(task, tier)] = pool[:n]
        dropped[cell_key(task, tier)] = pool[n:]
    if problems:
        return {"line": None, "problems": problems}
    written: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    for tier in _rollout.cell_tiers(target_cells):
        header, rows = loaded[tier]
        tasks = [task for task in header["tasks"] if (task, tier) in target_cells]
        new_header = restrict_header(header, tasks)
        new_rows = []
        for row in rows:
            if row["task"] not in tasks:
                continue
            new = copy.deepcopy(row)
            if H.delivered(row):
                new["selected"] = int(row["candidate"]) in picks[cell_key(row["task"], tier)]
            new_rows.append(new)
        for task in tasks:
            new_header["select_rule"][task] = list(picks[cell_key(task, tier)])
            new_header["delivery_per_cell"][task] = int(target_cells[(task, tier)])
        new_header["run_id"] = f"{header['run_id']}-v9subset"
        stats = copy.deepcopy(header.get("draw_stats") or {})
        stats["v9_subset"] = {"tool": "v9_subset_specs.py derive", "at": now_iso(),
                              "source_identity_sha256": header["identity_sha256"],
                              "source_file_sha256": file_sha256(Path(v8_root) / tier / "specs.jsonl"),
                              "dropped_tasks": [t for t in header["tasks"] if t not in tasks],
                              "rule": "交付行候选号升序前 N 个"}
        new_header["draw_stats"] = stats
        new_header = resign(new_header, new_rows, table)
        written[tier] = (new_header, new_rows)
    for tier, (header, rows) in written.items():
        write_jsonl_exclusive(out / tier / "specs.jsonl", [header, *rows])
    H.load_specs_v8(out, dict(target_cells), cell_table=table, check_fingerprint=False)
    subset = sum(n for (t, _), n in target_cells.items() if t not in EXTEND_TASKS)
    extend = sum(n for (t, _), n in target_cells.items() if t in EXTEND_TASKS)
    line = (f"V9_DERIVE=PASS cells={len(target_cells)} subset={subset} insertpeg={extend} "
            f"total={subset + extend} tiers={len(written)}")
    meta = {"schema": "v9-derive/1", "at": now_iso(), "v8_root": str(v8_root), "v8_delivery": str(v8_delivery),
            "v8_delivery_sha256": file_sha256(Path(v8_delivery)), "cells": _rollout.cells_json(target_cells),
            "picks": picks, "dropped": dropped,
            "tiers": {tier: {"identity_sha256": h["identity_sha256"], "delivery_sha256": h["delivery_sha256"]}
                      for tier, (h, _) in written.items()}, "line": line}
    write_text_exclusive(out / DERIVE_META, json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    return {"line": line, "problems": [], "picks": picks, "dropped": dropped, "cells": target_cells}


def cmd_derive(args) -> int:
    delivery = Path(args.v8_delivery) if args.v8_delivery else Path(args.v8_gen) / "delivery.local.json"
    result = derive(Path(args.v8_root), delivery, Path(args.out))
    if result["problems"]:
        return fail("V9_DERIVE", result["problems"])
    for key, cands in result["picks"].items():
        print(f"DERIVE {key} N={len(cands)} picked={_rollout.compact_range(cands)} "
              f"dropped={_rollout.compact_range(result['dropped'][key]) or '-'}", flush=True)
    print(result["line"], flush=True)
    return 0


# ── extend ─────────────────────────────────────────────────────────────


def _ledger_lines(path: Path) -> list[tuple[str, dict[str, Any]]]:
    if not Path(path).is_file():
        raise SubsetError(f"缺少尝试账本 {path}")
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append((line, json.loads(line)))
    return out


def plan_extend(task: str, tier: str, v8_frozen: Path, v8_shard: Path, quota: int, append: int) -> dict[str, Any]:
    """extend 的只读核对与计划（``allow_spares=True`` 跳过的核对在这里补齐）：

    * 片 ``shard.json`` 含该格、来源 identity 等于冻结根当前 identity；两份规格都未上锁；
    * 冻结根与片的该任务行：身份键与 ``spec`` 逐字相等；冻结根若已带结果段（V8 合并根）则结果段也须与片逐字相等；
      候选号恰为 ``0..per_env-1``；片无「selected 未跑」行；
    * 账本：该格每条终态的 task／tier／candidate／seed／spec_sha256 与片行一致、终态 ok↔``rollout.status``、ok 局
      ``h5_sha256`` 相等；有终态的候选 == 片里 ``tried`` 的行；
    * 同任务别档 seed（冻结根其他档文件）收集给追加核对。"""
    if (task, tier) not in H.V9_CELLS:
        raise SubsetError(f"{task}@{tier} 不在 V9 格表里")
    if not 0 < quota <= H.V9_CELLS[(task, tier)]:
        raise SubsetError(f"--quota 须为 1..{H.V9_CELLS[(task, tier)]}：{quota}")
    if append < 0:
        raise SubsetError(f"--append 须为非负整数：{append}")
    v8_frozen, v8_shard = Path(v8_frozen), Path(v8_shard)
    frozen_path = v8_frozen / tier / "specs.jsonl"
    shard_path = v8_shard / "specs" / tier / "specs.jsonl"
    for path in (frozen_path, shard_path):
        if Path(str(path) + ".lock").exists():
            raise SubsetError(f"{path} 上锁中（{path}.lock），可能有 continue 在跑，拒绝")
    meta_path = v8_shard / _rollout.SHARD_META
    if not meta_path.is_file():
        raise SubsetError(f"缺少 {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("schema") != _rollout.V8_SHARD_SCHEMA or cell_key(task, tier) not in (meta.get("cells") or {}):
        raise SubsetError(f"{meta_path} 不是含 {cell_key(task, tier)} 的 {_rollout.V8_SHARD_SCHEMA}")
    f_header, f_rows = load_tier(v8_frozen, tier)
    s_header, s_rows = load_tier(v8_shard / "specs", tier)
    if (meta.get("sources") or {}).get(tier, {}).get("identity_sha256") != f_header["identity_sha256"]:
        raise SubsetError(f"{meta_path} 记录的 {tier} 来源 identity 与冻结根 {frozen_path} 不符")
    for header, label in ((f_header, "冻结根"), (s_header, "片")):
        if task not in header["tasks"]:
            raise SubsetError(f"{label} {tier} 不含任务 {task}")
    if f_header["sampling_config"][task] != s_header["sampling_config"][task]:
        raise SubsetError(f"{task}/{tier} 片与冻结根的 sampling_config 不符")
    for key in ("per_env", "select_rule", "delivery_per_cell"):
        if f_header[key][task] != s_header[key][task]:
            raise SubsetError(f"{task}/{tier} 片与冻结根的 {key} 不符：{s_header[key][task]} ≠ {f_header[key][task]}")
    _, row_keys, _, _ = H._schema_keys(H.SCHEMA_V8)
    fmine = sorted((r for r in f_rows if r["task"] == task), key=lambda r: int(r["candidate"]))
    smine = sorted((r for r in s_rows if r["task"] == task), key=lambda r: int(r["candidate"]))
    per_env = int(s_header["per_env"][task])
    if [int(r["candidate"]) for r in smine] != list(range(per_env)) or len(fmine) != len(smine):
        raise SubsetError(f"{task}/{tier} 候选号须恰为 0..{per_env - 1}，冻结根 {len(fmine)} 行、片 {len(smine)} 行")
    frozen_has_results = any(r["tried"] for r in fmine)
    for f, s in zip(fmine, smine):
        if any(f[k] != s[k] for k in row_keys) or f["spec"] != s["spec"]:
            raise SubsetError(f"{task}/{tier} 候选 {s['candidate']} 冻结根与片身份不符")
        if frozen_has_results and f != s:
            raise SubsetError(f"{task}/{tier} 候选 {s['candidate']} 冻结根（已带结果段）与片逐字段不等")
    pending = [int(r["candidate"]) for r in smine if r["selected"] and r["rollout"] is None]
    if pending:
        raise SubsetError(f"{task}/{tier} 片里还有 selected 未跑的行 {pending}，先跑完再迁移")
    # 账本
    ledger_path = v8_shard / _rollout.LEDGER_NAME
    entries = [(line, e) for line, e in _ledger_lines(ledger_path) if e.get("task") == task and e.get("tier") == tier]
    by_cand = {int(r["candidate"]): r for r in smine}
    results: dict[int, dict[str, Any]] = {}
    infra = 0
    for _, entry in entries:
        cand = int(entry["candidate"])
        if entry["kind"] == "infra_retry":
            infra += 1
            continue
        if entry["kind"] != "result":
            raise SubsetError(f"账本有未知 kind：{entry['kind']!r}")
        if cand in results:
            raise SubsetError(f"账本里 {task}/{tier} 候选 {cand} 有两条终态")
        rec = entry["record"]
        row = by_cand.get(cand)
        if row is None:
            raise SubsetError(f"账本终态 {task}/{tier}#{cand} 不在片规格里")
        for name, want, got in (("task", row["task"], rec.get("task")), ("tier", row["tier"], rec.get("tier")),
                                ("candidate", int(row["candidate"]), int(rec.get("candidate", -1))),
                                ("seed", int(row["seed"]), int(rec.get("seed", -1))),
                                ("spec_sha256", row["spec_sha256"], rec.get("spec_sha256"))):
            if want != got:
                raise SubsetError(f"账本终态 {task}/{tier}#{cand} 的 {name} 与规格行不符：规格={want} 账本={got}")
        status = (row.get("rollout") or {}).get("status")
        if status != ("ok" if rec.get("ok") else "failed"):
            raise SubsetError(f"账本终态 {task}/{tier}#{cand} ok={rec.get('ok')} 与规格 rollout.status={status} 不符")
        if rec.get("ok") and rec.get("h5_sha256") != row["rollout"].get("h5_sha256"):
            raise SubsetError(f"账本终态 {task}/{tier}#{cand} 的 h5_sha256 与规格 rollout 段不符")
        results[cand] = rec
    tried = {int(r["candidate"]) for r in smine if r["tried"]}
    if set(results) != tried:
        raise SubsetError(f"账本终态候选 {sorted(set(results) - tried)} 未在规格里 tried，规格 tried 却无终态 "
                          f"{sorted(tried - set(results))}")
    other_seeds: set[int] = set()
    for other in H.V8_TIERS:
        if other == tier or not (v8_frozen / other / "specs.jsonl").is_file():
            continue
        _, orows = load_tier(v8_frozen, other)
        other_seeds |= {int(r["seed"]) for r in orows if r["task"] == task}
    ok_n = sum(1 for rec in results.values() if rec.get("ok"))
    selected_now = sum(1 for r in smine if r["selected"])
    spares = [int(r["candidate"]) for r in smine if not r["tried"] and not r["selected"]]
    deficit = quota - selected_now
    if deficit < 0:
        raise SubsetError(f"{task}/{tier} 已选 {selected_now} 局，超过新配额 {quota}")
    return {"task": task, "tier": tier, "quota": quota, "append": append, "frozen_path": frozen_path,
            "shard_path": shard_path, "meta": meta, "f_header": f_header, "s_header": s_header, "rows": smine,
            "entries": entries, "imported_ok": ok_n, "imported_fail": len(results) - ok_n, "infra_retries": infra,
            "spares": spares, "per_env": per_env, "selected_now": selected_now, "deficit": deficit,
            "other_seeds": other_seeds, "ledger_path": ledger_path, "frozen_identity": f_header["identity_sha256"],
            "shard_identity": s_header["identity_sha256"]}


def build_extend(plan: dict[str, Any], new_rows: list[dict[str, Any]], draw_info: dict[str, Any] | None
                 ) -> tuple[dict[str, Any], list[dict[str, Any]], list[int]]:
    """组装 V9 片规格：V8 该任务全部行（只把缺额个候选号最小的未试行标 selected）+ 追加行；配额改新值、重签。"""
    task, tier, quota = plan["task"], plan["tier"], plan["quota"]
    episodes = [int(r["episode"]) for r in new_rows]
    if episodes != list(range(plan["per_env"], plan["per_env"] + len(new_rows))):
        raise SubsetError(f"追加候选须从 {plan['per_env']} 起连续：{episodes}")
    clash = sorted({int(r["seed"]) for r in new_rows} & plan["other_seeds"])
    if clash:
        raise SubsetError(f"追加候选 seed 与同任务别档相交：{clash[:5]}")
    rows = [copy.deepcopy(r) for r in plan["rows"]] + [copy.deepcopy(r) for r in new_rows]
    untried = sorted(int(r["candidate"]) for r in rows if not r["tried"] and not r["selected"])
    if len(untried) < plan["deficit"]:
        raise SubsetError(f"{task}/{tier} 未试候选只有 {len(untried)} 个，补不满缺额 {plan['deficit']}")
    chosen = untried[:plan["deficit"]]
    for row in rows:
        if int(row["candidate"]) in chosen:
            row["selected"] = True
    header = restrict_header(plan["s_header"], [task])
    header["per_env"][task] = len(rows)
    header["delivery_per_cell"][task] = quota
    header["select_rule"][task] = sorted(set(plan["s_header"]["select_rule"][task]) | set(chosen))
    if len(header["select_rule"][task]) != quota:
        raise SubsetError(f"select_rule 长度 {len(header['select_rule'][task])} ≠ 配额 {quota}（V8 初选与新选重叠？）")
    header["run_id"] = f"{plan['f_header']['run_id']}-v9extend-{task}"
    header["draw_stats"] = {"v9_extend": {
        "tool": "v9_subset_specs.py extend", "at": now_iso(), "task": task, "tier": tier,
        "v8_frozen": str(plan["frozen_path"]), "v8_frozen_identity_sha256": plan["frozen_identity"],
        "v8_shard": str(plan["shard_path"]), "v8_shard_identity_sha256": plan["shard_identity"],
        "quota_old": int(plan["s_header"]["delivery_per_cell"][task]), "quota_new": quota,
        "imported_ok": plan["imported_ok"], "imported_fail": plan["imported_fail"],
        "imported_infra_retries": plan["infra_retries"], "spares": plan["spares"],
        "appended": len(new_rows), "append_requested": plan["append"], "selected_new": chosen,
        "draw": draw_info}}
    header = resign(header, rows, H.V9_CELLS)
    return header, rows, chosen


def extend(task: str, tier: str, v8_frozen: Path, v8_shard: Path, quota: int, append: int, out: Path, *,
           max_reset_attempts: int, dry_run: bool = False, draw_one: Callable | None = None,
           sampling_check: Callable | None = None, pkg: str = "robomme_hard", release: str | None = None,
           gpus: str | None = None) -> dict[str, Any]:
    out = Path(out)
    busy = [str(out / name) for name in ("specs", _rollout.SHARD_META, _rollout.LEDGER_NAME, CELLS_JSON, "episodes",
                                         "_rounds") if (out / name).exists()]
    if busy:
        raise SubsetError(f"输出片根已有内容，拒绝覆盖：{busy}")
    plan = plan_extend(task, tier, v8_frozen, v8_shard, quota, append)
    spares = plan["spares"]
    print(f"EXTEND_IMPORT {task}@{tier} rows={plan['per_env']} imported_ok={plan['imported_ok']} "
          f"imported_fail={plan['imported_fail']} infra_retries={plan['infra_retries']} "
          f"spares={_rollout.compact_range(spares) or '-'} frozen_identity={plan['frozen_identity'][:12]} "
          f"shard_identity={plan['shard_identity'][:12]}", flush=True)
    print(f"EXTEND_QUOTA {task}@{tier} {plan['s_header']['delivery_per_cell'][task]}→{quota} "
          f"selected_now={plan['selected_now']} deficit={plan['deficit']}", flush=True)
    start, stop = plan["per_env"], plan["per_env"] + append
    planned_untried = spares + list(range(start, stop))
    first = planned_untried[:plan["deficit"]]
    print(f"EXTEND_PLAN append={append} candidates={start}..{stop - 1} first_pending={_rollout.compact_range(first)} "
          f"untried_after={_rollout.compact_range(planned_untried)} max_reset_attempts={max_reset_attempts}", flush=True)
    if len(planned_untried) < plan["deficit"]:
        raise SubsetError(f"未试 {len(spares)} + 追加 {append} < 缺额 {plan['deficit']}")
    if dry_run:
        line = (f"V9_{task.upper()}_EXTEND_DRY_RUN imported_ok={plan['imported_ok']} "
                f"imported_fail={plan['imported_fail']} spares={len(spares)} append={append} quota={quota} "
                f"deficit={plan['deficit']}（未抽签、未写盘）")
        return {"line": line, "plan": plan, "dry_run": True}
    new_rows: list[dict[str, Any]] = []
    draw_info = None
    if append:
        import append_candidates as AC  # noqa: PLC0415

        pre = restrict_header(plan["f_header"], [task])
        new_rows, draw_info = AC.draw_extra(pre, task, tier, start, append, allow_spares=True,
                                            max_reset_attempts=max_reset_attempts, draw_one=draw_one,
                                            sampling_check=sampling_check, pkg=pkg, release=release, gpus=gpus)
    header, rows, chosen = build_extend(plan, new_rows, draw_info)
    # 写出：规格（排他）、账本（V8 原文本行原样）、格表 JSON、shard.json
    spec_path = out / "specs" / tier / "specs.jsonl"
    write_jsonl_exclusive(spec_path, [header, *rows])
    write_text_exclusive(out / _rollout.LEDGER_NAME, "".join(line + "\n" for line, _ in plan["entries"]))
    cells = {(task, tier): quota}
    write_text_exclusive(out / CELLS_JSON, json.dumps(_rollout.cells_json(cells), ensure_ascii=False, indent=1) + "\n")
    meta = {"schema": _rollout.V8_SHARD_SCHEMA, "label": f"v9-extend-{task}", "frozen_root": str(v8_frozen),
            "cells": _rollout.cells_json(cells),
            "sources": {tier: {"identity_sha256": plan["frozen_identity"],
                               "file_sha256": file_sha256(plan["frozen_path"])}},
            "v9_extend": {"v8_shard": str(v8_shard), "v8_shard_identity_sha256": plan["shard_identity"],
                          "identity_sha256": header["identity_sha256"], "file_sha256": file_sha256(spec_path),
                          "imported_ok": plan["imported_ok"], "imported_fail": plan["imported_fail"],
                          "spares": spares, "appended": len(new_rows), "selected_new": chosen,
                          "generate": "generate_h5.py --mode continue --cells <本目录>/cells.json "
                                      "--specs <本目录>/specs --output <本目录> --resume"}}
    write_text_exclusive(out / _rollout.SHARD_META, json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    # 写后复核：片根按格表可读、V8 行身份逐字未变、账本逐行原样
    loaded = _rollout.load_v8_root(out / "specs", cells)
    _, back = loaded[tier]
    _, row_keys, _, _ = H._schema_keys(H.SCHEMA_V8)
    old = {int(r["candidate"]): r for r in plan["rows"]}
    for row in back:
        cand = int(row["candidate"])
        if cand in old and ({k: row[k] for k in row if k != "selected"} != {k: old[cand][k] for k in old[cand]
                                                                          if k != "selected"}):
            raise SubsetError(f"写后复核：V8 候选 {cand} 除 selected 外有字段变了")
    if [line for line, _ in _ledger_lines(out / _rollout.LEDGER_NAME)] != [line for line, _ in plan["entries"]]:
        raise SubsetError("写后复核：导入账本与 V8 原文本行不符")
    untried_after = sorted(int(r["candidate"]) for r in back if not r["tried"])
    pending = sorted(int(r["candidate"]) for r in back if r["selected"] and r["rollout"] is None)
    print(f"EXTEND_WRITE out={out} per_env={len(back)} identity={header['identity_sha256'][:12]} "
          f"pending={_rollout.compact_range(pending)} untried={_rollout.compact_range(untried_after)}", flush=True)
    line = (f"V9_{task.upper()}_EXTEND=PASS imported_ok={plan['imported_ok']} imported_fail={plan['imported_fail']} "
            f"spares={len(spares)} appended={len(new_rows)} quota={header['delivery_per_cell'][task]}")
    return {"line": line, "plan": plan, "header": header, "rows": back, "chosen": chosen, "pending": pending,
            "untried": untried_after, "dry_run": False}


def cmd_extend(args, *, draw_one: Callable | None = None, sampling_check: Callable | None = None) -> int:
    result = extend(args.task, args.tier, Path(args.v8_frozen), Path(args.v8_shard), args.quota, args.append,
                    Path(args.out), max_reset_attempts=args.max_reset_attempts, dry_run=args.dry_run,
                    draw_one=draw_one, sampling_check=sampling_check, pkg=args.pkg, release=args.release,
                    gpus=args.gpus)
    if not result["dry_run"] and len(result["rows"]) - result["plan"]["per_env"] < args.append:
        # 抽签预算内没凑够追加数：规格已写（够补缺额），但如实报告短缺
        print(f"# 注意：追加 {len(result['rows']) - result['plan']['per_env']} < 请求 {args.append}", flush=True)
    print(result["line"], flush=True)
    return 0


# ── assemble ───────────────────────────────────────────────────────────


#: 合并 xhard4 header 时各来源必须逐字相等的 header 键
SAME_HEADER_KEYS = ("schema", "difficulty", "runtime", "seed_rule", "recovery_rule", "identity_source", "exec_cap",
                    "layout_rule")


def _tier_file_rows(root: Path, tier: str):
    header, rows = load_tier(root, tier, H.V9_CELLS)
    return header, rows


def assemble(subset: Path, movecube: Path, insertpeg: Path, v8_delivery: Path, out_specs: Path, out_delivery: Path, *,
             movecube_delivery: Path | None = None, insertpeg_delivery: Path | None = None,
             cells: dict[tuple[str, str], int] | None = None, tier: str = "xhard4") -> dict[str, Any]:
    cells = _rollout.order_cells(dict(H.V9_CELLS if cells is None else cells))
    out_specs, out_delivery = Path(out_specs), Path(out_delivery)
    subset_root, mc_root, ip_root = specs_dir(subset), specs_dir(movecube), specs_dir(insertpeg)
    if out_specs.resolve() == subset_root.resolve():
        raise SubsetError("--out-specs 不能与 --subset 相同（子集根留作 derive 产物；整合写到新根）")
    targets = [out_specs / t / "specs.jsonl" for t in _rollout.cell_tiers(cells)] + [out_delivery]
    existing = [str(p) for p in targets if p.exists()]
    if existing:
        raise SubsetError(f"输出已存在，拒绝覆盖：{existing[:3]}")
    mc_delivery = Path(movecube_delivery) if movecube_delivery else Path(movecube) / "delivery.json"
    ip_delivery = Path(insertpeg_delivery) if insertpeg_delivery else Path(insertpeg) / "delivery.json"
    problems: list[str] = []
    (mc_task,), (ip_task,) = NEW_TASKS, EXTEND_TASKS
    s_header, s_rows = _tier_file_rows(subset_root, tier)
    m_header, m_rows = _tier_file_rows(mc_root, tier)
    i_header, i_rows = _tier_file_rows(ip_root, tier)
    if m_header["tasks"] != [mc_task]:
        raise SubsetError(f"MoveCube 根的 {tier} 任务须恰为 [{mc_task}]：{m_header['tasks']}")
    if i_header["tasks"] != [ip_task]:
        raise SubsetError(f"InsertPeg 根的 {tier} 任务须恰为 [{ip_task}]：{i_header['tasks']}")
    if mc_task in s_header["tasks"] or ip_task not in s_header["tasks"]:
        raise SubsetError(f"子集根 {tier} 须不含 {mc_task}、含 {ip_task}（V8 交付局）：{s_header['tasks']}")
    for key in SAME_HEADER_KEYS:
        for header, label in ((m_header, "MoveCube"), (i_header, "InsertPeg")):
            if header[key] != s_header[key]:
                problems.append(f"{label} 根 header.{key} 与子集根不符")
    # 逐任务 sampling_config：同一任务出现在多个来源时必须逐字相同；每个来源自身散列自洽（load 已核）
    sampling_sources = {task: [("subset", s_header["sampling_config"][task])] for task in s_header["tasks"]}
    sampling_sources.setdefault(mc_task, []).append(("movecube", m_header["sampling_config"][mc_task]))
    sampling_sources.setdefault(ip_task, []).append(("insertpeg", i_header["sampling_config"][ip_task]))
    for task, items in sampling_sources.items():
        digests = {label: H.digest(value) for label, value in items}
        if len(set(digests.values())) != 1:
            problems.append(f"{task}/{tier} sampling_config 来源不一致：{ {k: v[:12] for k, v in digests.items()} }")
    # InsertPeg：V8 行（子集根里的全部行）与 extend 片逐字一致（除 selected）；V8 交付局在片里仍交付且结果段相同
    _, row_keys, _, _ = H._schema_keys(H.SCHEMA_V8)
    i_by = {int(r["candidate"]): r for r in i_rows}
    s_ip = [r for r in s_rows if r["task"] == ip_task]
    v8_reuse_ip = {int(r["candidate"]) for r in s_ip if H.delivered(r)}
    for row in s_ip:
        got = i_by.get(int(row["candidate"]))
        if got is None:
            problems.append(f"{ip_task} 候选 {row['candidate']} 在 extend 片里缺失")
            continue
        if {k: v for k, v in got.items() if k != "selected"} != {k: v for k, v in row.items() if k != "selected"}:
            if any(got[k] != row[k] for k in row_keys) or got["spec"] != row["spec"]:
                problems.append(f"{ip_task} 候选 {row['candidate']} 身份与 V8 不符")
            elif row["tried"]:
                problems.append(f"{ip_task} 候选 {row['candidate']} V8 已试，extend 片里结果段被改")
        if int(row["candidate"]) in v8_reuse_ip and not H.delivered(got):
            problems.append(f"{ip_task} 候选 {row['candidate']} 是 V8 交付局，extend 片里却未交付")
    v8_tried_ip = {int(r["candidate"]) for r in s_ip if r["tried"]}
    ip_new = [r for r in i_rows if H.delivered(r) and int(r["candidate"]) not in v8_reuse_ip]
    stale = [int(r["candidate"]) for r in ip_new if int(r["candidate"]) in v8_tried_ip]
    if stale:
        problems.append(f"{ip_task} 新交付局 {stale} 在 V8 已试过（新局只能来自 V8 未试备用或追加候选）")
    for task, rows_ in ((mc_task, m_rows), (ip_task, i_rows)):
        pend = [int(r["candidate"]) for r in rows_ if r["selected"] and r["rollout"] is None]
        if pend:
            problems.append(f"{task}/{tier} 还有 selected 未跑的行 {pend[:5]}")
        got = len(delivered_rows(rows_, task))
        if got != cells[(task, tier)]:
            problems.append(f"{task}/{tier} 交付 {got} ≠ 格表 {cells[(task, tier)]}")
    if problems:
        return {"line": None, "problems": problems}
    # 合成 xhard4
    tasks = list(s_header["tasks"]) + [mc_task]
    header = copy.deepcopy(s_header)
    header["tasks"] = tasks
    for key in ("per_env", "select_rule", "delivery_per_cell", "sampling_config"):
        header[key] = {}
        for task in tasks:
            src = m_header if task == mc_task else i_header if task == ip_task else s_header
            header[key][task] = copy.deepcopy(src[key][task])
    header["run_id"] = f"v9-specs-{tier}"
    header["provenance"] = copy.deepcopy(m_header["provenance"])
    header["draw_stats"] = {"v9_assemble": {
        "tool": "v9_subset_specs.py assemble", "at": now_iso(),
        "subset": {"path": str(subset_root / tier / "specs.jsonl"), "identity_sha256": s_header["identity_sha256"]},
        "movecube": {"path": str(mc_root / tier / "specs.jsonl"), "identity_sha256": m_header["identity_sha256"]},
        "insertpeg": {"path": str(ip_root / tier / "specs.jsonl"), "identity_sha256": i_header["identity_sha256"]}}}
    rows = []
    for task in tasks:
        src_rows = m_rows if task == mc_task else i_rows if task == ip_task else s_rows
        rows += sorted((copy.deepcopy(r) for r in src_rows if r["task"] == task), key=lambda r: int(r["candidate"]))
    header = resign(header, rows, H.V9_CELLS)
    write_jsonl_exclusive(out_specs / tier / "specs.jsonl", [header, *rows])
    for other in _rollout.cell_tiers(cells):
        if other == tier:
            continue
        src = subset_root / other / "specs.jsonl"
        dst = out_specs / other / "specs.jsonl"
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(src, "rb") as a, open(dst, "xb") as b:
            b.write(a.read())
    loaded = H.load_specs_v8(out_specs, dict(cells), cell_table=H.V9_CELLS, check_fingerprint=False)
    # 交付清单
    _, v8_index = load_delivery(v8_delivery)
    _, mc_index = load_delivery(mc_delivery)
    _, ip_index = load_delivery(ip_delivery)
    base = os.path.abspath(out_delivery.parent)
    rows_out: list[dict[str, Any]] = []
    cell_out: dict[str, dict[str, Any]] = {}
    for (task, t), expected in cells.items():
        mine = [r for r in loaded[t][1] if r["task"] == task]
        c = {"task": task, "tier": t, "expected": expected, "candidates": len(mine),
             "tried": sum(r["tried"] for r in mine), "delivered": 0, "reused": 0, "new": 0,
             "failed": sum((r["rollout"] or {}).get("status") == "failed" for r in mine),
             "spares_left": sum(not r["tried"] and not r["selected"] for r in mine)}
        for row in delivered_rows(mine, task):
            cand = int(row["candidate"])
            key = (task, t, cand)
            if task == mc_task:
                source, drow, label = SOURCE_NEW, mc_index.get(key), "MoveCube delivery.json"
            elif task == ip_task and cand not in v8_reuse_ip:
                source, drow, label = SOURCE_NEW, ip_index.get(key), "InsertPeg delivery.json"
            else:
                source, drow, label = SOURCE_REUSE, v8_index.get(key), "V8 delivery.local.json"
            errs = check_against_delivery(row, drow, label)
            if errs:
                problems += errs
                continue
            h5 = drow.get("h5")
            if not h5 or not Path(h5).is_file():
                problems.append(f"{label}：{task}@{t}#{cand} 的 h5 不存在：{h5}")
                continue
            video = main_video(h5, drow)
            if not video or not Path(video).is_file():
                problems.append(f"{label}：{task}@{t}#{cand} 找不到唯一主视频（{video}）")
                continue
            out_row = {"task": task, "tier": t, "candidate": cand, "seed": int(row["seed"]),
                       "episode": int(row["episode"]), "spec_sha256": row["spec_sha256"],
                       "h5_sha256": drow["h5_sha256"], "frames": drow.get("frames"),
                       "exec_steps": drow.get("exec_steps"), "h5": os.path.abspath(h5),
                       "path": os.path.relpath(os.path.abspath(h5), base), "env_module": drow.get("env_module"),
                       "recovery_mode": drow.get("recovery_mode"), "initial_selected": drow.get("initial_selected"),
                       "role": drow.get("role"), "video": os.path.abspath(video), "video_sha256": file_sha256(Path(video)),
                       "source": source}
            rows_out.append(out_row)
            c["delivered"] += 1
            c["reused" if source == SOURCE_REUSE else "new"] += 1
        c["status"] = "PASS" if c["delivered"] == expected else "FAIL"
        if c["status"] == "FAIL":
            problems.append(f"{task}/{t} 交付 {c['delivered']} ≠ {expected}")
        cell_out[f"{task}/{t}"] = c
    reused = sum(r["source"] == SOURCE_REUSE for r in rows_out)
    new = len(rows_out) - reused
    expect_new = cells[(mc_task, tier)] + cells[(ip_task, tier)] - len(v8_reuse_ip)
    if new != expect_new:
        problems.append(f"新局数 {new} ≠ MoveCube {cells[(mc_task, tier)]} + InsertPeg 新 "
                        f"{cells[(ip_task, tier)] - len(v8_reuse_ip)}")
    if len(rows_out) != sum(cells.values()):
        problems.append(f"清单行数 {len(rows_out)} ≠ 格表合计 {sum(cells.values())}")
    ok = not problems
    line = (f"V9_ASSEMBLE={'PASS' if ok else 'FAIL'} rows={len(rows_out)} reused={reused} new={new} "
            f"cells={len(cells)}")
    if not ok:
        return {"line": line, "problems": problems}
    report = {
        "schema": _rollout.V8_DELIVERY_SCHEMA, "specs_root": str(out_specs), "cells_source": "v9-assemble",
        "cells_table": _rollout.cells_json(cells), "code_baseline": None, "exec_cap": H.V8_EXEC_CAP,
        "ledgers": [], "rebase": [], "tasks": len({t for t, _ in cells}), "cell_count": len(cells),
        "counts": {"expected": sum(cells.values()), "delivered": len(rows_out), "reused": reused, "new": new},
        "cells": cell_out, "rows": rows_out, "bad_rows": [], "exec_over_cap_rows": [], "problems": [],
        "sources": {"v8_delivery": str(v8_delivery), "v8_delivery_sha256": file_sha256(Path(v8_delivery)),
                    "movecube_delivery": str(mc_delivery), "movecube_delivery_sha256": file_sha256(mc_delivery),
                    "insertpeg_delivery": str(ip_delivery), "insertpeg_delivery_sha256": file_sha256(ip_delivery),
                    "subset_root": str(subset_root), "movecube_root": str(mc_root), "insertpeg_root": str(ip_root)},
        "line": line,
    }
    write_text_exclusive(out_delivery, json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    return {"line": line, "problems": [], "report": report}


def cmd_assemble(args) -> int:
    result = assemble(Path(args.subset), Path(args.movecube), Path(args.insertpeg), Path(args.v8_delivery),
                      Path(args.out_specs), Path(args.out_delivery),
                      movecube_delivery=Path(args.movecube_delivery) if args.movecube_delivery else None,
                      insertpeg_delivery=Path(args.insertpeg_delivery) if args.insertpeg_delivery else None)
    if result["problems"]:
        return fail("V9_ASSEMBLE", result["problems"])
    print(result["line"], flush=True)
    return 0


# ── link ───────────────────────────────────────────────────────────────


def link_tree(delivery: Path, out: Path) -> dict[str, Any]:
    """按身份建 ``<out>/episodes/<tier>/<Task>_episode_<c>/{hdf5_files,videos}/`` 的 hardlink（``os.link``）。
    目标已存在：同 inode 跳过（幂等）；否则记 problem、不覆盖。``out`` 不得落在任何来源片目录里。"""
    data, _ = load_delivery(delivery)
    out = Path(out).resolve()
    problems: list[str] = []
    linked = skipped = 0
    plan = []
    for row in data["rows"]:
        wdir = out / "episodes" / row["tier"] / f"{row['task']}_episode_{int(row['candidate'])}"
        for kind, src in (("hdf5_files", row.get("h5")), ("videos", row.get("video"))):
            if not src or not Path(src).is_file():
                problems.append(f"{row['task']}@{row['tier']}#{row['candidate']} 的 {kind} 源文件不存在：{src}")
                continue
            shard_root = Path(src).resolve().parents[4]
            if out == shard_root or shard_root in out.parents or out in shard_root.parents:
                problems.append(f"--out {out} 与来源片目录 {shard_root} 重叠（不得在来源目录下建文件）")
                continue
            plan.append((Path(src), wdir / kind / Path(src).name))
    if problems:
        return {"line": None, "problems": problems}
    for src, dst in plan:
        if dst.exists() or dst.is_symlink():
            if dst.is_file() and os.path.samefile(src, dst):
                skipped += 1
                continue
            problems.append(f"目标已存在且不是同一 inode：{dst}（源 {src}），不覆盖")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src, dst)
        except OSError as exc:
            problems.append(f"os.link 失败 {src} → {dst}：{exc}")
            continue
        linked += 1
    ok = not problems
    line = (f"V9_LINK={'PASS' if ok else 'FAIL'} rows={len(data['rows'])} files={len(plan)} linked={linked} "
            f"skipped={skipped}")
    return {"line": line, "problems": problems, "linked": linked, "skipped": skipped}


def cmd_link(args) -> int:
    result = link_tree(Path(args.delivery), Path(args.out))
    if result["problems"]:
        return fail("V9_LINK", result["problems"])
    print(result["line"], flush=True)
    return 0


# ── verify ─────────────────────────────────────────────────────────────


def verify(v8_root: Path, v8_delivery: Path, v9_root: Path, v9_delivery: Path, v9_tree: Path, *,
           v8_cells: dict[tuple[str, str], int] | None = None, v9_cells: dict[tuple[str, str], int] | None = None,
           rehash_h5: bool = False) -> dict[str, Any]:
    """复用局逐字节核对：规格行（除 selected 外逐字段）、h5（清单 sha 相等 + 交付树文件与 V8 文件同 inode；
    ``rehash_h5`` 另重算）、mp4（交付树文件与 V8 主视频同 inode 且重算 sha 等于清单 ``video_sha256``）；
    每格复用局 = V8 交付行候选号最小的 min(N_v9, N_v8) 个。"""
    v8_cells = _rollout.order_cells(dict(H.V8_CELLS if v8_cells is None else v8_cells))
    v9_cells = _rollout.order_cells(dict(H.V9_CELLS if v9_cells is None else v9_cells))
    v8 = H.load_specs_v8(v8_root, v8_cells, cell_table=H.resolve_cell_table(v8_cells), check_fingerprint=False)
    v9 = H.load_specs_v8(v9_root, v9_cells, cell_table=H.V9_CELLS, check_fingerprint=False)
    _, v8_index = load_delivery(v8_delivery)
    v9_data, _ = load_delivery(v9_delivery)
    tree = Path(v9_tree)
    problems: list[str] = []
    reuse_rows = [r for r in v9_data["rows"] if r.get("source") == SOURCE_REUSE]
    bad_source = [r for r in v9_data["rows"] if r.get("source") not in (SOURCE_REUSE, SOURCE_NEW)]
    if bad_source:
        problems.append(f"清单有 {len(bad_source)} 行 source 不是 {SOURCE_REUSE}／{SOURCE_NEW}")
    # 取行规则：逐格复用集合 = V8 交付行候选号升序前 min(N_v9, N_v8) 个
    picks_ok = picks_total = 0
    for (task, tier), n9 in v9_cells.items():
        if task in NEW_TASKS:
            continue
        if (task, tier) not in v8_cells:
            problems.append(f"{task}@{tier} 不在 V8 格表里")
            continue
        picks_total += 1
        pool = [int(r["candidate"]) for r in delivered_rows(v8[tier][1], task)]
        want = pool[:min(n9, len(pool))]
        got = sorted(int(r["candidate"]) for r in reuse_rows if r["task"] == task and r["tier"] == tier)
        nine = [int(r["candidate"]) for r in delivered_rows(v9[tier][1], task)]
        ok = got == want and set(want) <= set(nine) and (task in EXTEND_TASKS or nine == want)
        picks_ok += ok
        if not ok:
            problems.append(f"{task}@{tier} 复用 {_rollout.compact_range(got)} ≠ V8 交付行前 {len(want)} 个 "
                            f"{_rollout.compact_range(want)}（V9 交付 {_rollout.compact_range(nine)}）")
    print(f"V9_SUBSET_PICKS cells={picks_total} ok={picks_ok}", flush=True)
    spec_equal = h5_equal = video_equal = 0
    for row in reuse_rows:
        task, tier, cand = row["task"], row["tier"], int(row["candidate"])
        tag = f"{task}@{tier}#{cand}"
        r8 = next((r for r in v8.get(tier, ({}, []))[1] if r["task"] == task and int(r["candidate"]) == cand), None)
        r9 = next((r for r in v9.get(tier, ({}, []))[1] if r["task"] == task and int(r["candidate"]) == cand), None)
        d8 = v8_index.get((task, tier, cand))
        if r8 is None or r9 is None or d8 is None:
            problems.append(f"{tag} 在 V8 规格／V9 规格／V8 清单里缺失")
            continue
        if {k: v for k, v in r8.items() if k != "selected"} == {k: v for k, v in r9.items() if k != "selected"} \
                and r8["spec_sha256"] == row["spec_sha256"] == d8["spec_sha256"] and H.delivered(r9):
            spec_equal += 1
        else:
            problems.append(f"{tag} 规格行与 V8 不等（或 V9 未交付）")
        v8_h5 = Path(d8["h5"])
        tree_h5 = tree / "episodes" / tier / f"{task}_episode_{cand}" / "hdf5_files" / Path(row["h5"]).name
        h5_ok = (row["h5_sha256"] == d8["h5_sha256"] and v8_h5.is_file() and tree_h5.is_file()
                 and os.path.samefile(v8_h5, tree_h5) and os.path.samefile(row["h5"], v8_h5))
        if h5_ok and rehash_h5:
            h5_ok = file_sha256(tree_h5) == d8["h5_sha256"]
        if h5_ok:
            h5_equal += 1
        else:
            problems.append(f"{tag} h5 与 V8 不同（sha 或 inode）：{tree_h5}")
        v8_video = main_video(d8["h5"], d8)
        tree_video = tree / "episodes" / tier / f"{task}_episode_{cand}" / "videos" / Path(row.get("video") or "x").name
        video_ok = (bool(v8_video) and Path(v8_video).is_file() and tree_video.is_file()
                    and os.path.samefile(v8_video, tree_video)
                    and file_sha256(tree_video) == row.get("video_sha256"))
        if video_ok:
            video_equal += 1
        else:
            problems.append(f"{tag} mp4 与 V8 不同（sha 或 inode）：{tree_video}")
    expected_reuse = sum(min(n9, len(delivered_rows(v8[tier][1], task)))
                         for (task, tier), n9 in v9_cells.items() if task not in NEW_TASKS and (task, tier) in v8_cells)
    if len(reuse_rows) != expected_reuse:
        problems.append(f"复用行 {len(reuse_rows)} ≠ 按格表推出的 {expected_reuse}")
    ok = not problems and spec_equal == h5_equal == video_equal == len(reuse_rows)
    line = (f"V9_SUBSET={'PASS' if ok else 'FAIL'} reused={len(reuse_rows)} spec_equal={spec_equal} "
            f"h5_equal={h5_equal} video_equal={video_equal}")
    return {"line": line, "problems": problems, "ok": ok}


def cmd_verify(args) -> int:
    result = verify(Path(args.v8_root), Path(args.v8_delivery), Path(args.v9_root), Path(args.v9_delivery),
                    Path(args.v9_tree), rehash_h5=args.rehash_h5)
    for item in result["problems"][:40]:
        print(f"# 证据：{item}", flush=True)
    print(result["line"], flush=True)
    return 0 if result["ok"] else 1


# ── CLI ────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("derive", help="V8 规格根 + gen1 清单 → 子集规格根（14 任务前 N + InsertPeg V8 交付 20）")
    p.add_argument("--v8-root", required=True, help="V8 规格根（合并后、带结果段，如 artifacts/newtask-v8/specs-root）")
    p.add_argument("--v8-gen", required=True, help="V8 gen1 根（读 <根>/delivery.local.json）")
    p.add_argument("--v8-delivery", default=None, help="显式指定 V8 交付清单（缺省 <--v8-gen>/delivery.local.json）")
    p.add_argument("--out", required=True, help="子集规格根（新目录；已有同名档文件即拒绝）")
    p = sub.add_parser("extend", help="InsertPeg 20→50 迁移：导入 V8 该格行与终态、改配额、追加候选、写片根")
    p.add_argument("--task", default="InsertPeg", choices=EXTEND_TASKS)
    p.add_argument("--tier", default="xhard4")
    p.add_argument("--v8-frozen", required=True, help="V8 冻结根或合并后规格根（<根>/<tier>/specs.jsonl）")
    p.add_argument("--v8-shard", required=True, help="V8 该格所在片根（含 specs/、shard.json、results.jsonl；InsertPeg 在 shard3）")
    p.add_argument("--quota", type=int, required=True, help="新配额（V9 InsertPeg 为 50）")
    p.add_argument("--append", type=int, required=True, help="追加候选数（V9 InsertPeg 为 35，候选号 40～74）")
    p.add_argument("--out", required=True, help="V9 片根（新目录）")
    p.add_argument("--max-reset-attempts", type=int, default=55, help="追加抽签的 reset 总预算（缺省 55，见 §2.4.3）")
    p.add_argument("--gpus", default=None, help="抽签用的 GPU（取第一张）")
    p.add_argument("--pkg", default="robomme_hard")
    p.add_argument("--release", default=None, help="重建 sampling 的 release（缺省 _extract.DEFAULT_RELEASE）")
    p.add_argument("--dry-run", action="store_true", help="只做导入核对、配额与计划打印；不抽签、不写盘")
    p = sub.add_parser("assemble", help="子集根 + MoveCube 片根 + InsertPeg 片根 → V9 五档规格 + 800 行交付清单")
    p.add_argument("--subset", required=True, help="derive 输出根")
    p.add_argument("--movecube", required=True, help="MoveCube 片根（跑完 continue；含 specs/xhard4/specs.jsonl）")
    p.add_argument("--insertpeg", required=True, help="extend 片根（跑完 continue）")
    p.add_argument("--v8-delivery", required=True, help="V8 gen1/delivery.local.json（复用局的 h5／mp4 路径与 sha 来源）")
    p.add_argument("--movecube-delivery", default=None,
                   help="MoveCube 片聚合清单（本机路径，aggregate --rebase 之后；缺省 <--movecube>/delivery.json）")
    p.add_argument("--insertpeg-delivery", default=None,
                   help="InsertPeg 片聚合清单（本机路径，aggregate --rebase 之后；缺省 <--insertpeg>/delivery.json）")
    p.add_argument("--out-specs", required=True, help="V9 五档规格根（新目录，不能与 --subset 相同）")
    p.add_argument("--out-delivery", required=True, help="800 行交付清单路径（已存在即拒绝）")
    p = sub.add_parser("link", help="按身份建 hardlink 交付树（不复制、不覆盖、幂等）")
    p.add_argument("--delivery", required=True, help="assemble 写出的交付清单")
    p.add_argument("--out", required=True, help="交付树根（如 artifacts/newtask-v9/delivery）")
    p = sub.add_parser("verify", help="复用局规格／h5／mp4 与 V8 逐字节相同，且每格取的是交付行最小的 N 个")
    p.add_argument("--v8-root", required=True)
    p.add_argument("--v8-delivery", required=True)
    p.add_argument("--v9-root", required=True)
    p.add_argument("--v9-delivery", required=True)
    p.add_argument("--v9-tree", required=True, help="link 的 --out")
    p.add_argument("--rehash-h5", action="store_true", help="另对交付树里每个复用 h5 重算 sha256（慢：每局数百 MB）")
    return parser


def main(argv: list[str] | None = None, *, draw_one: Callable | None = None,
         sampling_check: Callable | None = None) -> int:
    """``draw_one``／``sampling_check`` 只供单测注入（extend 不起仿真）。"""
    args = build_parser().parse_args(argv)
    names = {"derive": "V9_DERIVE", "extend": "V9_INSERTPEG_EXTEND", "assemble": "V9_ASSEMBLE", "link": "V9_LINK",
             "verify": "V9_SUBSET"}
    try:
        if args.cmd == "derive":
            return cmd_derive(args)
        if args.cmd == "extend":
            return cmd_extend(args, draw_one=draw_one, sampling_check=sampling_check)
        if args.cmd == "assemble":
            return cmd_assemble(args)
        if args.cmd == "link":
            return cmd_link(args)
        return cmd_verify(args)
    except (SubsetError, ValueError, RuntimeError, OSError) as exc:  # SpecsError 是 ValueError、RolloutError／AppendError 是 RuntimeError
        return fail(names[args.cmd], [f"{type(exc).__name__}: {exc}"], f" reason={type(exc).__name__}")


if __name__ == "__main__":
    sys.exit(main())
