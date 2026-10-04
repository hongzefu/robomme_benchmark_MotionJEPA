#!/usr/bin/env python3
"""v9 整合与 hardlink 交付树（v9 方案第二部分 §2.1 S1-D 行、§2.4.2 第 3～5 步）。

原有的 ``derive``（V8 子集派生）、``extend``（InsertPeg 20 → 50 迁移）、``verify``（复用局逐字节核对）三个子命令
依赖已删除的 V8 1070 局格表，已于维护计划阶段 1b（W4，主会话裁决）删除，git 历史可取回（4c645af7）。
现存两个子命令（都不起仿真）：

    # ③ 整合：子集根 + MoveCube 片根 + InsertPeg 片根 → V9 五档规格 + 800 行交付清单
    uv run --no-sync python scripts/injection-dev/v9_subset_specs.py assemble \\
        --subset artifacts/newtask-v9/subset-root --movecube <MoveCube 片根> --insertpeg <InsertPeg 片根> \\
        --v8-delivery artifacts/newtask-v8/gen1/delivery.local.json \\
        --out-specs artifacts/newtask-v9/specs-root --out-delivery artifacts/newtask-v9/delivery/delivery.local.json
    # ④ hardlink 交付树（只 os.link，不复制、不覆盖；幂等）
    uv run --no-sync python scripts/injection-dev/v9_subset_specs.py link \\
        --delivery artifacts/newtask-v9/delivery/delivery.local.json --out artifacts/newtask-v9/delivery

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
from typing import Any

import _common  # noqa: F401  路径设置
import _rollout  # noqa: E402
from _freeze import write_jsonl_exclusive  # noqa: E402

from robomme_hard.env_record_wrapper import hard_specs as H  # noqa: E402

#: 不走子集的任务：MoveCube 整任务重抽；InsertPeg 原由已删除的 derive／extend 两步产出片根（assemble 仍按这两项分派）
NEW_TASKS = ("MoveCube",)
EXTEND_TASKS = ("InsertPeg",)
SOURCE_REUSE = "v8-reuse"
SOURCE_NEW = "v9-new"
#: 交付清单行必有的键（与 V8 ``gen1/delivery.local.json`` 行、``_rollout.aggregate_v8`` 的 row_out 同键；``video`` 可选，
#: assemble 一律补齐）。站点目录 ``site_catalog.py``、subgoals、step-headroom 都按这些键读。
DELIVERY_ROW_KEYS = ("task", "tier", "candidate", "seed", "episode", "spec_sha256", "h5_sha256", "frames",
                     "exec_steps", "h5", "path", "env_module", "recovery_mode", "initial_selected", "role")


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
    v8_data, v8_index = load_delivery(v8_delivery)
    mc_data, mc_index = load_delivery(mc_delivery)
    ip_data, ip_index = load_delivery(ip_delivery)
    base = os.path.abspath(out_delivery.parent)
    rows_out: list[dict[str, Any]] = []
    cell_out: dict[str, dict[str, Any]] = {}
    over_rows: list[dict[str, Any]] = []
    totals = {key: 0 for key in _rollout.V8_TOTAL_COUNT_KEYS}
    for (task, t), expected in cells.items():
        mine = [r for r in loaded[t][1] if r["task"] == task]
        roll = lambda r: r["rollout"] or {}  # noqa: E731
        # 逐格计数键与 _rollout.aggregate_v8 同口径（由合成后规格结果段算）；infra_retries 取各来源清单该格的值
        src_cells = mc_data if task == mc_task else ip_data if task == ip_task else v8_data
        c = {"expected": expected, "candidates": len(mine), "tried": sum(r["tried"] for r in mine),
             "delivered": sum(H.delivered(r) for r in mine),
             "failed": sum(roll(r).get("status") == "failed" for r in mine),
             "exec_over_cap": sum(roll(r).get("error_type") == "exec_over_cap" for r in mine),
             "backfills": sum(r["tried"] and not r["initial_selected"] for r in mine),
             "infra_retries": int(((src_cells.get("cells") or {}).get(f"{task}/{t}") or {}).get("infra_retries", 0)),
             "spares_left": sum(not r["tried"] and not r["selected"] for r in mine),
             "pending": sum(r["selected"] and r["rollout"] is None for r in mine), "bad_h5": 0}
        reused_n = new_n = 0
        for r in sorted(mine, key=lambda r: int(r["candidate"])):
            if roll(r).get("error_type") == "exec_over_cap":
                over_rows.append({"task": task, "tier": t, "candidate": int(r["candidate"]), "seed": int(r["seed"]),
                                  "exec_steps": roll(r).get("exec_steps")})
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
                c["bad_h5"] += 1
                continue
            h5 = drow.get("h5")
            if not h5 or not Path(h5).is_file():
                problems.append(f"{label}：{task}@{t}#{cand} 的 h5 不存在：{h5}")
                c["bad_h5"] += 1
                continue
            video = main_video(h5, drow)
            if not video or not Path(video).is_file():
                problems.append(f"{label}：{task}@{t}#{cand} 找不到唯一主视频（{video}）")
                c["bad_h5"] += 1
                continue
            missing = [k for k in DELIVERY_ROW_KEYS if k not in drow]
            if missing:
                problems.append(f"{label}：{task}@{t}#{cand} 清单行缺键 {missing}")
                continue
            # 来源清单原行逐键拷贝（与 V8 delivery.local.json 同键同口径），只改写随清单位置变化的 path、
            # 补齐绝对 h5／video，另加 video_sha256 与 source
            out_row = copy.deepcopy(drow)
            out_row.update(h5=os.path.abspath(h5), path=os.path.relpath(os.path.abspath(h5), base),
                           video=os.path.abspath(video), video_sha256=file_sha256(Path(video)), source=source)
            rows_out.append(out_row)
            if source == SOURCE_REUSE:
                reused_n += 1
            else:
                new_n += 1
        if c["delivered"] == expected and not c["bad_h5"]:
            status, reason = "PASS", None
        elif c["pending"]:
            status, reason = "FAIL", "pending"
            totals["pending_cells"] += 1
        elif c["delivered"] != expected and c["spares_left"] == 0:
            status, reason = "FAIL", "exhausted"
            totals["exhausted_cells"] += 1
        elif c["delivered"] != expected:
            status, reason = "FAIL", "shortfall"
        else:
            status, reason = "FAIL", "bad_h5"
        if status == "FAIL":
            totals["failed_cells"] += 1
            problems.append(f"{task}/{t}:{reason}（交付 {c['delivered']} ≠ {expected} 或清单行有问题）")
        for k in _rollout.V8_CELL_COUNT_KEYS:
            totals[k] += c[k]
        cell_out[f"{task}/{t}"] = {"task": task, "tier": t, "status": status, "reason": reason, **c,
                                   "reused": reused_n, "new": new_n}
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
    n_tasks = len({t for t, _ in cells})
    # 顶层 line 与 V8 聚合同口径（按 V9 格表算），判定行名换 V9_DELIVERY_SET；整合判定另存 assemble_line
    set_line = (f"V9_DELIVERY_SET=PASS tasks={n_tasks} cells={len(cells)} total={totals['delivered']} "
                f"expected={totals['expected']} failed={totals['failed']} exec_over_cap={totals['exec_over_cap']} "
                f"backfills={totals['backfills']} infra_retries={totals['infra_retries']} "
                f"exhausted_cells={totals['exhausted_cells']} pending_cells={totals['pending_cells']} "
                f"bad_h5={totals['bad_h5']} reused={reused} new={new}")
    report = {
        "schema": _rollout.V8_DELIVERY_SCHEMA, "specs_root": str(out_specs), "cells_source": "v9-assemble",
        "cells_table": _rollout.cells_json(cells), "code_baseline": mc_data.get("code_baseline"),
        "exec_cap": H.V8_EXEC_CAP,
        "ledgers": [*v8_data.get("ledgers", []), *mc_data.get("ledgers", []), *ip_data.get("ledgers", [])],
        "rebase": [], "tasks": n_tasks, "cell_count": len(cells),
        "counts": {**totals, "reused": reused, "new": new},
        "cells": cell_out, "rows": rows_out, "bad_rows": [], "exec_over_cap_rows": over_rows, "problems": [],
        "sources": {"v8_delivery": str(v8_delivery), "v8_delivery_sha256": file_sha256(Path(v8_delivery)),
                    "movecube_delivery": str(mc_delivery), "movecube_delivery_sha256": file_sha256(mc_delivery),
                    "insertpeg_delivery": str(ip_delivery), "insertpeg_delivery_sha256": file_sha256(ip_delivery),
                    "subset_root": str(subset_root), "movecube_root": str(mc_root), "insertpeg_root": str(ip_root)},
        "line": set_line, "assemble_line": line,
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


# ── CLI ────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    names = {"assemble": "V9_ASSEMBLE", "link": "V9_LINK"}
    try:
        if args.cmd == "assemble":
            return cmd_assemble(args)
        return cmd_link(args)
    except (SubsetError, ValueError, RuntimeError, OSError) as exc:  # SpecsError 是 ValueError、RolloutError／AppendError 是 RuntimeError
        return fail(names[args.cmd], [f"{type(exc).__name__}: {exc}"], f" reason={type(exc).__name__}")


if __name__ == "__main__":
    sys.exit(main())
