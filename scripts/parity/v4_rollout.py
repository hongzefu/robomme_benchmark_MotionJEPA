#!/usr/bin/env python3
"""V4 实跑段：读冻结的 ``specs.jsonl`` 回注规格跑演示，落 ``results.jsonl``；并做 V2 两遍对拍（步 5 / 步 7）。

调用链与 V3 的 C／D 路完全相同：本文件只负责**组织身份与输入**，真正起环境、录 h5、跑规划的是
``train_split_runner.py``（``--identity-source formula`` 分叉，seed 按 V4 公式硬校验）→
``train_split_worker.run_one``（``gym.make(..., sampling_config=, native_episode_spec=)``，往下一行都不改）。

子命令：

* ``run``：先跑每环境 ``selected=true`` 的正式局；演示失败的环境按 H4 在**本环境剩余候选**里按 index 顺序
  （``1,2,4,5,7,8,9``）逐条递补，直到凑满正式局数或候选耗尽；**不追加抽签**，失败局保留在分母里。
  ``--identities-from <另一轮 results.jsonl>`` 时不做递补，严格重放那一轮跑过的全部身份（V2 第二遍用）。
* ``compare``：两轮结果做 V2——**V2a** 全部身份的终态与失败类别逐条一致；**V2b** 两轮都成功的局
  HDF5 全字段零容差比较（复用 ``train_split_parity.compare_h5_pair``），比较前先查文件有效非空、
  并补比根属性（``compare_h5_pair`` 用 ``visititems`` 不访问根节点，两个空 HDF5 会被误判相同）。

⚠ 用户 2026-09-23 定（K4/K5）：全量在本机跑、实跑用多 worker（``--workers``），允许两遍之间有少量不同——
多 worker 下 mplib RRT 的墙钟预算随负载变化，部分局轨迹会分叉；因此 ``compare`` 的 V2 结论只作报告
（``--report-only``），不作硬闸门。

    uv run --no-sync python -m scripts.parity.v4_rollout run --specs <specs.jsonl> --label run1 \
        --official-root artifacts/train-parity/local-smoke-01/official-src --output artifacts/newtask-v4/<id>/rollout
    uv run --no-sync python -m scripts.parity.v4_rollout run --specs <specs.jsonl> --label run2 \
        --identities-from artifacts/newtask-v4/<id>/rollout/run1/results.jsonl ...
    uv run --no-sync python -m scripts.parity.v4_rollout compare artifacts/newtask-v4/<id>/rollout/run1 artifacts/newtask-v4/<id>/rollout/run2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.parity.v4_specs import DIFFICULTY, _read_jsonl, validate_specs  # noqa: E402

BACKFILL_ORDER = (1, 2, 4, 5, 7, 8, 9)
RUNNER = REPO_ROOT / "scripts" / "parity" / "train_split_runner.py"


def _load_all(specs_path: Path):
    """读全部 160 行（含落选候选），递补要用；校验与 load_specs 相同。"""
    records = _read_jsonl(specs_path)
    header, rows = records[0], records[1:]
    validate_specs(header, rows, check_disk=True)
    return header, {(r["task"], r["episode"]): r for r in rows}


def _run_batch(batch: list[dict], header: dict, out_dir: Path, args, round_index: int) -> list[dict]:
    """一批身份交给 runner（单 worker），返回逐条结果（含 spec_replay 的绑定核验）。"""
    work = out_dir / "_rounds" / f"round_{round_index:02d}"
    work.mkdir(parents=True, exist_ok=False)
    jobs, specs = [], {}
    for row in batch:
        worker_dir = out_dir / "episodes" / f"{row['task']}_episode_{row['episode']}"
        jobs.append({"task": row["task"], "episode": row["episode"], "seed": row["seed"],
                     "attempt": row["attempt"], "difficulty": DIFFICULTY, "worker_dir": str(worker_dir)})
        specs[f"{row['task']}/{row['episode']}"] = row["spec"]
    tasks = sorted({row["task"] for row in batch})
    (work / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    (work / "sampling.json").write_text(json.dumps({"tasks": {t: header["sampling_config"][t] for t in tasks}},
                                                   ensure_ascii=False), encoding="utf-8")
    (work / "specs.json").write_text(json.dumps({"specs": specs}, ensure_ascii=False), encoding="utf-8")
    command = [
        sys.executable, str(RUNNER), "--official-root", str(Path(args.official_root).resolve()),
        "--src-root", str(REPO_ROOT), "--jobs-json", str(work / "jobs.json"),
        "--results-json", str(work / "results.json"), "--workers", str(args.workers), "--gpu", "0",
        "--sampling-config", str(work / "sampling.json"), "--episode-specs", str(work / "specs.json"),
        "--identity-source", "formula", "--no-recovery",  # V4 全部不开 recover（与抽签同口径）
    ]
    started = time.time()
    proc = subprocess.run(command, text=True, capture_output=True)
    (work / "runner.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
    if not (work / "results.json").exists():
        raise SystemExit(f"runner 未产出结果（exit={proc.returncode}），见 {work / 'runner.log'}")
    raw = {(r["task"], int(r["episode"])): r for r in json.loads((work / "results.json").read_text())["results"]}
    out = []
    for row in batch:
        result = raw.get((row["task"], row["episode"]), {})
        worker_dir = out_dir / "episodes" / f"{row['task']}_episode_{row['episode']}"
        binding = None
        replay = worker_dir / "spec_replay.json"
        if replay.exists():
            payload = json.loads(replay.read_text(encoding="utf-8"))
            mismatches = payload.get("mismatches", [])
            binding = {"mismatch": len(mismatches),
                       "unattributed_mismatch": sum(1 for m in mismatches if not m.get("decision_key")),
                       "unused": len(payload.get("unused", [])), "value_points": payload.get("value_points")}
        h5 = sorted((worker_dir / "hdf5_files").glob("*.h5"))
        out.append({
            "task": row["task"], "difficulty": DIFFICULTY, "episode": row["episode"], "seed": row["seed"],
            "attempt": row["attempt"], "spec_sha256": row["spec_sha256"], "run_label": args.label,
            "role": row["_role"], "ok": bool(result.get("ok")), "error_type": result.get("error_type"),
            "error": (result.get("error") or "")[:500] or None, "spec_binding": binding,
            "h5": str(h5[0]) if h5 else None, "round": round_index,
        })
    print(f"ROUND {round_index} jobs={len(batch)} ok={sum(r['ok'] for r in out)} "
          f"wall_s={time.time() - started:.0f}", flush=True)
    return out


def cmd_run(args: argparse.Namespace) -> int:
    header, rows = _load_all(Path(args.specs))
    out_dir = Path(args.output) / args.label
    if out_dir.exists():
        raise SystemExit(f"{out_dir} 已存在，禁止覆盖")
    out_dir.mkdir(parents=True)
    tasks = header["tasks"] if args.tasks == "all" else args.tasks.split(",")
    results: list[dict] = []
    round_index = 0
    if args.identities_from:
        # V2 第二遍：严格重放上一轮跑过的全部身份（含递补与失败局），不做递补决策
        previous = [json.loads(line) for line in Path(args.identities_from).read_text().splitlines() if line.strip()]
        batch = [{**rows[(p["task"], p["episode"])], "_role": p["role"]} for p in previous if p["task"] in tasks]
        results = _run_batch(batch, header, out_dir, args, round_index)
    else:
        need = {t: len([r for r in rows.values() if r["task"] == t and r["selected"]]) for t in tasks}
        batch = [{**r, "_role": "selected"} for (t, _), r in sorted(rows.items()) if t in tasks and r["selected"]]
        results = _run_batch(batch, header, out_dir, args, round_index)
        tried = {(r["task"], r["episode"]) for r in results}
        while True:
            ok_count = {t: sum(1 for r in results if r["task"] == t and r["ok"]) for t in tasks}
            batch = []
            for task in tasks:
                if ok_count[task] >= need[task]:
                    continue
                for episode in BACKFILL_ORDER:
                    if (task, episode) in rows and (task, episode) not in tried:
                        batch.append({**rows[(task, episode)], "_role": "backfill"})
                        tried.add((task, episode))
                        break
            if not batch:
                break
            round_index += 1
            results.extend(_run_batch(batch, header, out_dir, args, round_index))
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for row in sorted(results, key=lambda r: (r["task"], r["episode"])):
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    per_env = {}
    for task in tasks:
        mine = [r for r in results if r["task"] == task]
        target = len([r for r in rows.values() if r["task"] == task and r["selected"]])
        ok = sum(r["ok"] for r in mine)
        per_env[task] = {"attempted": len(mine), "ok": ok,
                         "backfilled": sum(1 for r in mine if r["role"] == "backfill" and r["ok"]),
                         "selected_shortfall": max(0, target - ok)}
    summary = {"specs": str(args.specs), "identity_sha256": header["identity_sha256"], "label": args.label,
               "per_env": per_env}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    attempted = sum(v["attempted"] for v in per_env.values())
    print(f"ROLLOUT_DONE label={args.label} rollout_attempted={attempted} "
          f"rollout_ok={sum(v['ok'] for v in per_env.values())} "
          f"backfilled={sum(v['backfilled'] for v in per_env.values())} "
          f"selected_shortfall={sum(v['selected_shortfall'] for v in per_env.values())}")
    return 0


# ── V2 对拍 ────────────────────────────────────────────────────────────────


def _h5_precheck(path: str | None) -> tuple[bool, dict]:
    """有效、非空、含至少一个 episode/timestep；返回根属性供比较。"""
    import h5py

    if not path or not Path(path).is_file() or Path(path).stat().st_size == 0:
        return False, {}
    try:
        with h5py.File(path, "r") as handle:
            names: list[str] = []
            handle.visit(names.append)
            attrs = {key: repr(handle.attrs[key]) for key in sorted(handle.attrs)}
            return bool(names), attrs
    except OSError:
        return False, {}


def cmd_compare(args: argparse.Namespace) -> int:
    from scripts.parity.train_split_parity import compare_h5_pair

    def load(run: str):
        rows = [json.loads(line) for line in (Path(run) / "results.jsonl").read_text().splitlines() if line.strip()]
        return {(r["task"], r["episode"]): r for r in rows}

    left, right = load(args.left), load(args.right)
    identities = sorted(set(left) | set(right))
    terminal_mismatch = compared = sha_equal = field_mismatch = empty_or_invalid = 0
    notes = []
    for ident in identities:
        a, b = left.get(ident), right.get(ident)
        if a is None or b is None or (a["ok"], a["error_type"]) != (b["ok"], b["error_type"]) \
                or a["spec_sha256"] != b["spec_sha256"]:
            terminal_mismatch += 1
            notes.append(f"终态不一致 {ident}")
            continue
        if not (a["ok"] and b["ok"]):
            continue
        valid_a, attrs_a = _h5_precheck(a["h5"])
        valid_b, attrs_b = _h5_precheck(b["h5"])
        if not (valid_a and valid_b):
            empty_or_invalid += 1
            notes.append(f"HDF5 无效或为空 {ident}")
            continue
        compared += 1
        if attrs_a != attrs_b:
            field_mismatch += 1
            notes.append(f"根属性不同 {ident}")
            continue
        result = compare_h5_pair(Path(a["h5"]), Path(b["h5"]))
        sha_equal += int(result["sha_equal"])
        if int(result["field_mismatch"]):
            field_mismatch += 1
            notes.append(f"字段不同 {ident}：{result['field_mismatch']}")
    ok = terminal_mismatch == 0 and field_mismatch == 0 and empty_or_invalid == 0
    verdict = ("REPORT" if args.report_only else ("PASS" if ok else "FAIL"))
    print(f"NEWVALUE_REPLAY={verdict} identities={len(identities)} "
          f"terminal_mismatch={terminal_mismatch} compared_success={compared} sha_equal={sha_equal} "
          f"field_mismatch={field_mismatch} empty_or_invalid={empty_or_invalid}")
    for note in notes[:30]:
        print(f"# {note}")
    return 0 if (ok or args.report_only) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="回注规格跑演示，落 results.jsonl（含 H4 递补）")
    run.add_argument("--specs", required=True)
    run.add_argument("--label", required=True, help="本轮标签，如 run1 / run2")
    run.add_argument("--tasks", default="all")
    run.add_argument("--official-root", required=True, help="官方隔离源码树（提供编排代码）")
    run.add_argument("--identities-from", default=None, help="严格重放另一轮 results.jsonl 的全部身份")
    run.add_argument("--workers", type=int, default=1, help="runner 并行 worker 数（K5：本机多 worker）")
    run.add_argument("--output", required=True)
    run.set_defaults(func=cmd_run)
    cmp_ = sub.add_parser("compare", help="V2：两轮终态一致 + 成功局 HDF5 逐位")
    cmp_.add_argument("left")
    cmp_.add_argument("right")
    cmp_.add_argument("--report-only", action="store_true",
                      help="K5：多 worker 实跑允许少量不同，只报告差异、不作硬闸门")
    cmp_.set_defaults(func=cmd_compare)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
