#!/usr/bin/env python3
"""V7 派生入口：xhard4 母布局 → xhard1～3 派生规格（只 reset、不 step、不录像；0928 方案第二部分 §1.4、§7.3.2）。

    # 阶段 3／4：派生（每候选每档 1 次 reset，失败不重抽，四档同步作废由 _rollout 的候选池表达）
    uv run --no-sync python scripts/injection-dev/derive_specs.py \
        --parent <v7>/xhard4/specs.jsonl --tiers xhard1,xhard2,xhard3 --out-root <v7> --workers 16 --gpus 0
    # 阶段 1：白名单完整性动态核对（16 任务 × 1 局 xhard4 导出 + 13 任务 × 3 档 × 1 局派生 = 55 次 reset）
    uv run --no-sync python scripts/injection-dev/derive_specs.py --whitelist-check --workers 1 --gpus 0 \
        --out artifacts/newtask-v7/whitelist-check

- 派生：``gym.make(task, sampling_config=母 header 的配置, native_episode_spec={"envelope":"derive","parent":母规格,
  "layout":白名单[task]}, seed=母 seed, difficulty=目标档)`` → ``reset`` → 导出 ``native-layered/3``；
  逐档封签写 ``<out-root>/xhard{1..3}/specs.jsonl``（``hard-specs/3``，行带 ``layout_parent``）与 ``derive-report.json``。
- 启动前断言不开 fail recover（``robomme_failure_recovery`` 不进 gym.make 参数）；``--dry-run`` 只打印 reset 预算。
- ``--whitelist-check``：每条 ``value()`` 路径恰好命中 L／G／N 一个模式（xhard4 导出局按白名单分类、派生局在
  SpecRecorder 里闭世界分类），每个模式至少命中一次 → ``LAYOUT_WHITELIST_COMPLETE``。
"""

from __future__ import annotations

import argparse
import copy
import datetime
import functools
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import _common  # noqa: F401  路径设置
import _draw  # noqa: E402
import _extract  # noqa: E402
import _freeze  # noqa: E402

from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402

DERIVED_TIERS = ("xhard1", "xhard2", "xhard3")
WHITELIST = hard_specs.PACKAGED_SPECS_ROOT / "layout_whitelist.json"


def load_whitelist(path: Path) -> dict[str, dict[str, list[str]]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks = payload["tasks"]
    for task, table in tasks.items():
        if set(table) != {"L", "G", "N"}:
            raise SystemExit(f"白名单 {task} 必须恰好有 L／G／N 三表")
    return tasks


def _gym_kwargs(seed: int, difficulty: str, sampling: dict, spec: dict | None) -> dict[str, Any]:
    kwargs = {**hard_specs.RUNTIME, "seed": int(seed), "difficulty": difficulty, "sampling_config": sampling}
    if spec is not None:
        kwargs["native_episode_spec"] = spec
    if "robomme_failure_recovery" in kwargs:
        raise SystemExit("派生不得开 fail recover")
    return kwargs


def run_one(job: dict[str, Any]) -> dict[str, Any]:
    """一次 reset：``job["kind"]`` 为 ``export``（xhard4 导出，白名单核对用）或 ``derive``。"""
    import gymnasium as gym

    env = None
    started = time.time()
    out = {"task": job["task"], "tier": job["tier"], "candidate": job.get("candidate"), "seed": job["seed"],
           "kind": job["kind"]}
    try:
        spec = None
        if job["kind"] == "derive":
            spec = {"envelope": "derive", "parent": job["parent_spec"], "layout": job["layout"]}
        env = gym.make(job["task"], **_gym_kwargs(job["seed"], job["tier"], job["sampling"], spec))
        env.reset()
        recorder = env.unwrapped._spec
        recorder.identity.update({"task": job["task"], "seed": int(job["seed"]), "difficulty": job["tier"],
                                  "episode": job.get("candidate"), "recovery_mode": None})
        document = recorder.to_dict()
        paths = [{"path": item["path"], "source": item["source"], "layout": item.get("layout")}
                 for item in recorder.trace if item["source"] in ("draw", "spec")]
        out.update(ok=True, spec=document, value_paths=paths, error_type=None, error=None,
                   layout_overridden=getattr(recorder, "layout_overridden", 0))
    except Exception as exc:  # noqa: BLE001 失败本身要归类记录
        out.update(ok=False, spec=None, value_paths=[], error_type=type(exc).__name__,
                   error=f"{exc}\n{traceback.format_exc(limit=4)}"[:2000])
    finally:
        if env is not None:
            env.close()
    out["wall_s"] = round(time.time() - started, 2)
    print(f"DERIVE {out['kind']} {out['task']}@{out['tier']} cand={out['candidate']} seed={out['seed']} ok={out['ok']} "
          f"{out['error_type'] or ''}", flush=True)
    return out


def run_jobs(jobs: list[dict[str, Any]], workers: int, gpus: list[str] | None, pkg: str) -> list[dict[str, Any]]:
    if workers <= 1:
        if gpus:
            os.environ["CUDA_VISIBLE_DEVICES"] = gpus[0]
        _draw.assert_registry_owner(pkg)
        return [run_one(job) for job in jobs]
    from concurrent.futures import ProcessPoolExecutor, as_completed

    ctx = mp.get_context("spawn")
    gpu_queue = None
    if gpus:
        gpu_queue = ctx.Queue()
        for index in range(workers):
            gpu_queue.put(gpus[index % len(gpus)])
    results = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx, initializer=_draw._draw_worker_init,
                             initargs=(gpu_queue, str(_common.REPO_ROOT / "src"), pkg)) as pool:
        futures = [pool.submit(run_one, job) for job in jobs]
        for future in as_completed(futures):
            results.append(future.result())
    # 结果按身份排序，与完成顺序无关
    return sorted(results, key=lambda r: (hard_specs.ALL_TASKS.index(r["task"]), r["tier"], r["candidate"] or 0))


# ── 派生 ───────────────────────────────────────────────────────────────


def derive(args) -> int:
    parent_header, parent_rows = hard_specs.load_specs(args.parent, check_fingerprint=False)
    if parent_header["schema"] != hard_specs.SCHEMA_V7 or parent_header["difficulty"] != "xhard4":
        raise SystemExit("--parent 必须是 v7 的 xhard4 母布局文件（hard-specs/3）")
    whitelist_sha = hashlib.sha256(Path(args.whitelist).read_bytes()).hexdigest()
    if parent_header["layout_rule"]["whitelist_sha256"] != whitelist_sha:
        raise SystemExit("白名单 sha256 与母布局 header.layout_rule 不符")
    whitelist = load_whitelist(args.whitelist)
    tiers = [t for t in args.tiers.split(",") if t]
    tasks = [t for t in parent_header["tasks"] if t in whitelist]
    jobs = []
    for tier in tiers:
        for row in parent_rows:
            if row["task"] not in tasks:
                continue
            jobs.append({"kind": "derive", "task": row["task"], "tier": tier, "candidate": int(row["candidate"]),
                         "seed": int(row["seed"]), "parent_spec": row["spec"], "layout": whitelist[row["task"]],
                         "sampling": parent_header["sampling_config"][row["task"]]})
    print(f"DERIVE_PLAN tasks={len(tasks)} tiers={tiers} candidates={len(parent_rows)} reset_budget={len(jobs)} "
          f"workers={args.workers} out_root={args.out_root}", flush=True)
    if args.dry_run:
        return 0
    out_root = Path(args.out_root)
    for tier in tiers:
        if (out_root / tier / "specs.jsonl").exists():
            raise SystemExit(f"{out_root / tier / 'specs.jsonl'} 已存在，禁止覆盖")
    results = run_jobs(jobs, args.workers, _draw.parse_gpus(args.gpus), args.pkg)
    by_parent = {(r["task"], int(r["candidate"])): r for r in parent_rows}
    report = {"schema": "v7-derive-report/1", "parent": str(args.parent), "parent_identity_sha256": parent_header["identity_sha256"],
              "whitelist_sha256": whitelist_sha, "tiers": tiers, "reset_attempted": len(results),
              "derive_fail": [], "derive_ok": {}}
    for tier in tiers:
        rows = []
        for res in (r for r in results if r["tier"] == tier):
            mother = by_parent[(res["task"], res["candidate"])]
            if not res["ok"]:
                report["derive_fail"].append({"task": res["task"], "tier": tier, "candidate": res["candidate"],
                                              "error_type": res["error_type"], "error": res["error"][:500]})
                continue
            spec = res["spec"]
            rows.append({"record": "spec", "task": res["task"], "tier": tier, "candidate": res["candidate"],
                         "episode": int(mother["episode"]), "seed": int(mother["seed"]), "attempt": int(mother["attempt"]),
                         "spec": spec, "spec_sha256": hard_specs.spec_sha256(spec),
                         "selected": bool(mother["initial_selected"]), "tried": False,
                         "initial_selected": bool(mother["initial_selected"]), "rollout": None,
                         "layout_parent": {"tier": "xhard4", "candidate": res["candidate"], "spec_sha256": mother["spec_sha256"]}})
            report["derive_ok"].setdefault(res["task"], {}).setdefault(tier, []).append(res["candidate"])
        rows.sort(key=lambda r: (r["task"], r["candidate"]))
        header = {key: copy.deepcopy(parent_header[key]) for key in (
            "record", "schema", "tasks", "runtime", "seed_rule", "select_rule", "sampling_config",
            "sampling_config_sha256", "recovery_rule", "identity_source", "layout_rule", "delivery_per_cell")}
        header.update(difficulty=tier, tasks=tasks, run_id=f"{parent_header['run_id']}-derive-{tier}",
                      per_env={t: {"candidates": sum(r["task"] == t for r in rows)} for t in tasks},
                      draw_stats={"derive": {"attempted": sum(r["tier"] == tier for r in results),
                                             "ok": len(rows)}},
                      provenance={"base_fingerprint": hard_specs.base_fingerprint(),
                                  "hard_fingerprint": hard_specs.hard_fingerprint(), "env_package": args.pkg,
                                  "derived_from": str(args.parent),
                                  "derived_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")})
        header["identity_sha256"] = hard_specs.identity_sha256(header, rows)
        header["delivery_sha256"] = hard_specs.delivery_sha256(rows)
        hard_specs.validate_specs(header, rows)
        _freeze.write_jsonl_exclusive(out_root / tier / "specs.jsonl", [header, *rows])
        print(f"DERIVE_TIER {tier} rows={len(rows)} fail={sum(f['tier'] == tier for f in report['derive_fail'])}", flush=True)
    (out_root / "derive-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    fails = len(report["derive_fail"])
    by_tier = {t: sum(f["tier"] == t for f in report["derive_fail"]) for t in tiers}
    print(f"DERIVE_DONE reset_attempted={len(results)} ok={len(results) - fails} derive_fail={fails} by_tier={by_tier}",
          flush=True)
    return 0


# ── 白名单完整性动态核对（阶段 1）───────────────────────────────────────


def whitelist_check(args) -> int:
    from robomme_hard.robomme_env.utils.episode_spec import EpisodeSpecError, classify_path

    whitelist = load_whitelist(args.whitelist)
    tasks = list(hard_specs.ALL_TASKS) if args.tasks == "all" else args.tasks.split(",")
    sampling = _extract.build_sampling(tasks, pkg=args.pkg, release="newtask-v7")["tasks"]
    rule = hard_specs.seed_rule_for("xhard4", "v7")
    first, last = (int(x) for x in args.mother_attempts.split(".."))
    budget = len(tasks) * (last - first + 1) + sum(t in whitelist for t in tasks) * len(DERIVED_TIERS)
    print(f"WHITELIST_CHECK_PLAN tasks={len(tasks)} mother_attempts={first}..{last} reset_budget<={budget} "
          f"workers={args.workers}", flush=True)
    if args.dry_run:
        return 0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    gpus = _draw.parse_gpus(args.gpus)
    exported, mother_failures = [], []
    for task in tasks:
        # 母局候选 0：按 attempt 依次抽（与阶段 4 抽签同一 seed 公式），成功即停
        for attempt in range(first, last + 1):
            job = {"kind": "export", "task": task, "tier": "xhard4", "candidate": 0,
                   "seed": hard_specs.seed_for(task, 0, attempt, rule), "sampling": sampling[task]}
            res = run_jobs([job], 1, gpus, args.pkg)[0]
            if res["ok"]:
                exported.append(res)
                break
            mother_failures.append(res)
        else:
            exported.append(res)
    jobs = []
    for res in exported:
        if res["task"] in whitelist and res["ok"]:
            for tier in DERIVED_TIERS:
                jobs.append({"kind": "derive", "task": res["task"], "tier": tier, "candidate": 0, "seed": res["seed"],
                             "parent_spec": res["spec"], "layout": whitelist[res["task"]], "sampling": sampling[res["task"]]})
    derived = run_jobs(jobs, args.workers, gpus, args.pkg)
    reset_total = len(exported) + len(mother_failures) - sum(not r["ok"] for r in exported) + len(derived)
    hits: dict[str, dict[str, int]] = {t: {p: 0 for cls in "LGN" for p in whitelist[t][cls]} for t in whitelist}
    unclassified: list[dict[str, Any]] = []
    for res in [*exported, *derived]:
        if res["task"] not in whitelist:
            continue
        for item in res["value_paths"]:
            try:
                _cls, pattern = classify_path(whitelist[res["task"]], item["path"])
                hits[res["task"]][pattern] += 1
            except EpisodeSpecError as exc:
                unclassified.append({"task": res["task"], "tier": res["tier"], "path": item["path"], "error": str(exc)[:200]})
    failed = [{k: r[k] for k in ("kind", "task", "tier", "error_type", "error")} for r in [*exported, *derived] if not r["ok"]]
    traces = sum(r["ok"] for r in [*exported, *derived])
    paths_by_task = {r["task"] + "@" + r["tier"]: sorted({i["path"] for i in r["value_paths"]})
                     for r in [*exported, *derived] if r["ok"]}
    if args.merge_with:
        # 与上一轮合并：本轮重跑的任务整段替换，其余任务沿用上一轮的命中、失败与未分类记录
        prev = json.loads(Path(args.merge_with).read_text())
        for task, table in prev["hits"].items():
            if task not in tasks:
                hits[task] = table
        failed += [f for f in prev["failed"] if f["task"] not in tasks]
        unclassified += [u for u in prev["unclassified"] if u["task"] not in tasks]
        traces += sum(1 for key in prev["paths_by_task"] if key.split("@")[0] not in tasks)
        paths_by_task = {**{k: v for k, v in prev["paths_by_task"].items() if k.split("@")[0] not in tasks}, **paths_by_task}
    unmatched = [{"task": t, "pattern": p} for t, table in hits.items() for p, n in table.items() if n == 0]
    report = {"traces": traces, "reset_attempted_this_run": reset_total,
              "mother_retries": [{k: r[k] for k in ("task", "seed", "error_type")} for r in mother_failures],
              "failed": failed, "unclassified": unclassified, "unmatched_patterns": unmatched, "hits": hits,
              "paths_by_task": paths_by_task, "merged_with": args.merge_with}
    (out / args.report_name).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    return whitelist_verdict(report, len(whitelist))


def whitelist_verdict(report: dict[str, Any], envs: int) -> int:
    """白名单缺陷（未分类路径、未命中模式、EpisodeSpecError）才判 FAIL；场景生成类的派生可行性失败
    （如 Swap 外环在低档不可行）是方案预料的 derive_fail，只报告（0928 方案第二部分 §1.8、§4）。"""
    defects = [f for f in report["failed"] if f["error_type"] == "EpisodeSpecError"]
    feasibility = [f for f in report["failed"] if f["error_type"] != "EpisodeSpecError"]
    ok = not defects and not report["unclassified"] and not report["unmatched_patterns"]
    print(f"LAYOUT_WHITELIST_COMPLETE={'PASS' if ok else 'FAIL'} envs={envs} traces={report['traces']} "
          f"unclassified={len(report['unclassified'])} unmatched_patterns={len(report['unmatched_patterns'])} "
          f"spec_errors={len(defects)} derive_fail={len(feasibility)}", flush=True)
    for item in (defects + feasibility + report["unclassified"] + report["unmatched_patterns"])[:20]:
        print(f"# {({k: (str(v)[:160]) for k, v in item.items()})}", flush=True)
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--parent", default=None, help="v7 xhard4 母布局 specs.jsonl")
    parser.add_argument("--tiers", default=",".join(DERIVED_TIERS))
    parser.add_argument("--whitelist", default=str(WHITELIST))
    parser.add_argument("--out-root", default=None, help="派生规格根（写 xhard{1..3}/specs.jsonl 与 derive-report.json）")
    parser.add_argument("--whitelist-check", action="store_true")
    parser.add_argument("--out", default=None, help="--whitelist-check 的报告目录")
    parser.add_argument("--tasks", default="all", help="--whitelist-check：只核这些任务（逗号分隔）")
    parser.add_argument("--mother-attempts", default="0..0",
                        help="--whitelist-check：母局候选 0 依次试的 attempt 区间（成功即停），如 1..5")
    parser.add_argument("--merge-with", default=None, help="--whitelist-check：与上一轮 whitelist-check.json 合并判定")
    parser.add_argument("--report-name", default="whitelist-check.json")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--gpus", default=None)
    parser.add_argument("--pkg", default="robomme_hard")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verdict-only", default=None, help="只读已有 whitelist-check 报告出判定行（不 reset）")
    args = parser.parse_args()
    if args.verdict_only:
        return whitelist_verdict(json.loads(Path(args.verdict_only).read_text()), len(load_whitelist(args.whitelist)))
    if args.whitelist_check:
        if not args.out:
            raise SystemExit("--whitelist-check 须给 --out")
        return whitelist_check(args)
    if not args.parent or not args.out_root:
        raise SystemExit("派生须给 --parent 与 --out-root")
    return derive(args)


if __name__ == "__main__":
    sys.exit(main())
