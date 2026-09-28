#!/usr/bin/env python3
"""一次性迁移：把上次 SimpleMemVLA 评估用的 smvla-0927／smvla-0927-fill 快照迁成包内 test-hard 四档规格。

0927 计划第一部分 §5.3「迁移」、第二部分 §1.2；用户 U-5「20局走迁移」、U-13 方案甲、U-16。

* 身份真源：SimpleMemVLA ``aab093f`` 的 ``docs/eval-doc/v6xhard-0927/records/<run>/results-shard*.jsonl``
  六个目录共 1100 行 → ``docs/validation/newtask-v6/hard-split/records/eval-identities-1100.jsonl``；
* 规格来源：benchmark ``1fe2d185`` 的 ``scripts/configs/newtask-v6/smvla-0927{,-fill}/<tier>/specs.reselected.jsonl`` 六份；
* h5 结果：``artifacts/newtask-v6/smvla-0927{,-fill}/<tier>/rollout/run1/results.jsonl``，逐局重算 sha256／字节数／帧数，
  并读 h5 ``setup`` 核 seed 与档位；
* 输出：``src/robomme_hard/env_metadata/test-hard/xhard{1..4}/specs.jsonl``（``schema=hard-specs/2``，排他发布，已存在拒绝覆盖）。

子命令（路径直跑，不用 ``-m``）::

    uv run --no-sync python scripts/injection-dev/migrate_smvla_specs.py build
    uv run --no-sync python scripts/injection-dev/migrate_smvla_specs.py check
    uv run --no-sync python scripts/injection-dev/migrate_smvla_specs.py export-s4-setup

判定行：``SOURCE_POOL``、``SPECS_IDENTITY``、``DELIVERY_SET``、``H5_BINDING``（build 与 check 都打），
``TIER_MAX_STEPS_SOURCE`` 与 S4 setup 清单（export-s4-setup）。不起仿真。
"""

from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for extra in (REPO / "src", REPO):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402

SMVLA_REPO = Path("/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA")
SMVLA_EVAL_COMMIT = "aab093f"
SPEC_COMMIT = "1fe2d185"
LEGACY_V4_COMMIT = "55f1b027"
CODE_BASELINE = "57fe9727a21ed7cb6910a451b8eeaa704e05192f"  # 12.191，smvla-0927 快照生成时的代码
EVAL_RUNS = {  # 评估 run 目录 → (规格快照, 档位)
    "xhard1-main-0927": ("smvla-0927", "xhard1"),
    "xhard1-fill-0927": ("smvla-0927-fill", "xhard1"),
    "xhard2-0927": ("smvla-0927", "xhard2"),
    "xhard3-0927": ("smvla-0927", "xhard3"),
    "xhard4-0927": ("smvla-0927", "xhard4"),
    "xhard4-fill-0927": ("smvla-0927-fill", "xhard4"),
}
TIER_SOURCES = {
    "xhard1": ("smvla-0927", "smvla-0927-fill"),
    "xhard2": ("smvla-0927",),
    "xhard3": ("smvla-0927",),
    "xhard4": ("smvla-0927", "smvla-0927-fill"),
}
DELIVERY_PER_CELL = 20
DEMO_BAND = {"xhard1": (750, 1050)}  # 上次生成报告的演示帧数带（U-16：带外照收，只记清单）
DEMO_BAND_TASKS = ("PatternLock", "RouteStick")  # 与 v5_generation 报告同口径：只统计这两个任务的 is_video_demo 帧数
OUT_ROOT = REPO / "src" / "robomme_hard" / "env_metadata" / "test-hard"
IDENTITIES_OUT = REPO / "docs" / "validation" / "newtask-v6" / "hard-split" / "records" / "eval-identities-1100.jsonl"
S4_DELIVERY = REPO / "artifacts" / "newtask-v6" / "s4-relaunch-02" / "verification" / "final-delivery.json"
S4_SPECS = REPO / "scripts" / "configs" / "newtask-v6" / "v6-02"
S4_SETUP_OUT = OUT_ROOT / "s4-setup-manifest.json"
STATS_CACHE = REPO / "artifacts" / "hard-split" / "migrate-h5-stats.json"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def jsonl(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# ── h5 统计（并行）──────────────────────────────────────────────────────


def h5_stats(path: str) -> dict[str, Any]:
    import h5py

    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 24), b""):
            digest.update(chunk)
            size += len(chunk)
    with h5py.File(path, "r") as handle:
        keys = list(handle.keys())
        episode = handle[keys[0]]
        setup = episode["setup"]
        timesteps = [k for k in episode.keys() if k.startswith("timestep_")]
        demo = sum(bool(episode[k]["info"]["is_video_demo"][()]) for k in timesteps)
        goal = setup["task_goal"][()]
        goal = [g.decode() if isinstance(g, bytes) else str(g) for g in (goal if hasattr(goal, "__len__") and not isinstance(goal, bytes) else [goal])]
        choices = setup["available_multi_choices"][()] if "available_multi_choices" in setup else b""
        return {
            "path": path, "sha256": digest.hexdigest(), "bytes": size, "episodes": len(keys),
            "frames": len(timesteps), "demo_frames": int(demo),
            "setup": {
                "seed": int(setup["seed"][()]),
                "difficulty": (setup["difficulty"][()].decode() if isinstance(setup["difficulty"][()], bytes)
                               else str(setup["difficulty"][()])),
                "task_goal": goal,
                "available_multi_choices": choices.decode() if isinstance(choices, bytes) else str(choices),
                "front_camera_intrinsic": setup["front_camera_intrinsic"][()].tolist() if "front_camera_intrinsic" in setup else None,
                "wrist_camera_intrinsic": setup["wrist_camera_intrinsic"][()].tolist() if "wrist_camera_intrinsic" in setup else None,
            },
        }


def all_h5_stats(paths: list[str], workers: int) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    if STATS_CACHE.is_file():
        cache = json.loads(STATS_CACHE.read_text())
    todo = []
    for path in sorted(set(paths)):
        stat = os.stat(path)
        entry = cache.get(path)
        if entry and entry.get("_mtime_ns") == stat.st_mtime_ns and entry.get("bytes") == stat.st_size:
            continue
        todo.append(path)
    print(f"H5_STATS todo={len(todo)} cached={len(set(paths)) - len(todo)} workers={workers}", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for index, result in enumerate(pool.map(h5_stats, todo, chunksize=1), 1):
            result["_mtime_ns"] = os.stat(result["path"]).st_mtime_ns
            cache[result["path"]] = result
            if index % 100 == 0:
                print(f"H5_STATS done={index}/{len(todo)}", flush=True)
    STATS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    STATS_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    return cache


# ── 来源读取 ───────────────────────────────────────────────────────────


def eval_identities() -> list[dict[str, Any]]:
    files = git(SMVLA_REPO, "ls-tree", "-r", "--name-only", SMVLA_EVAL_COMMIT,
                "docs/eval-doc/v6xhard-0927/records/").split()
    out = []
    for run, (source, tier) in EVAL_RUNS.items():
        shards = sorted(f for f in files if f"/records/{run}/results-shard" in f)
        for shard in shards:
            for row in jsonl(git(SMVLA_REPO, "show", f"{SMVLA_EVAL_COMMIT}:{shard}")):
                if row["difficulty"] != tier:
                    raise SystemExit(f"评估行档位 {row['difficulty']} 与 run 目录 {run} 不符")
                out.append({"source_run": run, "snapshot": source, "task": row["task"], "tier": tier,
                            "episode": int(row["episode"]), "seed": int(row["seed"]),
                            "spec_sha256": row["spec_sha256"], "eval_status": row["status"],
                            "eval_demo_frames": row.get("demo_frames"), "shard_file": shard})
    return sorted(out, key=lambda r: (hard_specs.TIERS.index(r["tier"]), r["task"], r["seed"]))


def spec_source(snapshot: str, tier: str) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    rel = f"scripts/configs/newtask-v6/{snapshot}/{tier}/specs.reselected.jsonl"
    text = git(REPO, "show", f"{SPEC_COMMIT}:{rel}")
    records = jsonl(text)
    return sha256_text(text), records[0], records[1:]


def results_rows(snapshot: str, tier: str) -> list[dict[str, Any]]:
    path = REPO / "artifacts" / "newtask-v6" / snapshot / tier / "rollout" / "run1" / "results.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def drafts_stats(snapshot: str, tier: str) -> tuple[str, dict[str, Any]]:
    path = REPO / "artifacts" / "newtask-v6" / snapshot / tier / "draft" / "drafts.jsonl"
    data = path.read_bytes()
    per_task: dict[str, dict[str, Any]] = {}
    for line in data.decode().splitlines()[1:]:
        if not line.strip():
            continue
        row = json.loads(line)
        entry = per_task.setdefault(row["task"], {"attempted": 0, "ok": 0, "fail_class": {}})
        entry["attempted"] += 1
        if row["reset_ok"]:
            entry["ok"] += 1
        else:
            key = row.get("fail_class") or "unknown"
            entry["fail_class"][key] = entry["fail_class"].get(key, 0) + 1
    return hashlib.sha256(data).hexdigest(), per_task


def legacy_validate(header: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    """用 55f1b027 的 v4_specs 原算法重算旧 identity_sha256（SPECS_IDENTITY 的 legacy 部分）。"""
    source = git(REPO, "show", f"{LEGACY_V4_COMMIT}:scripts/parity/v4_specs.py")
    if str(REPO / "scripts") not in sys.path:  # 旧 v4_specs 从 scripts/seed_layout.py 取 SeedLayout
        sys.path.insert(0, str(REPO / "scripts"))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "legacy_v4_specs.py"
        path.write_text(source)
        spec = importlib.util.spec_from_file_location("legacy_v4_specs", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.validate_specs(header, rows, check_disk=False)
        return module.identity_sha256(header, rows) == header["identity_sha256"]


# ── 构建 ───────────────────────────────────────────────────────────────


def build_tier(tier: str, identities: list[dict[str, Any]], stats: dict[str, dict[str, Any]] | None,
               counters: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sources = TIER_SOURCES[tier]
    wanted = {(i["task"], i["seed"], i["spec_sha256"]): i for i in identities if i["tier"] == tier}
    headers, pool, source_files, legacy_ids, drafts_sha, draw_stats = {}, [], {}, [], {}, {}
    for snapshot in sources:
        text_sha, header, rows = spec_source(snapshot, tier)
        headers[snapshot] = header
        source_files[f"{SPEC_COMMIT}:scripts/configs/newtask-v6/{snapshot}/{tier}/specs.reselected.jsonl"] = text_sha
        legacy_ids.append(header["identity_sha256"])
        counters["legacy_total"] += 1
        counters["legacy_equal"] += int(legacy_validate(header, rows))
        drafts_sha[snapshot], draw_stats[snapshot] = drafts_stats(snapshot, tier)
        results = {(r["task"], int(r["episode"]), int(r["seed"]), r["spec_sha256"]): r
                   for r in results_rows(snapshot, tier)}
        for row in rows:
            counters["raw"] += 1
            pool.append((snapshot, row, results.get((row["task"], int(row["episode"]), int(row["seed"]),
                                                     row["spec_sha256"]))))
    main = headers[sources[0]]
    for snapshot, header in headers.items():
        for task in header["tasks"]:
            if task in header["sampling_config"] and header["sampling_config"][task] != main["sampling_config"].get(task):
                raise SystemExit(f"{snapshot}/{tier} 的 sampling_config[{task}] 与主集不同")
        for key in ("runtime", "seed_rule", "recovery_rule"):
            if header[key] != main[key]:
                raise SystemExit(f"{snapshot}/{tier} 的 {key} 与主集不同")
    # 同一完整身份 (task, seed, spec_sha256) 去重：正式交付局保留评估实际所用的快照，其余保留主集
    by_identity: dict[tuple, list] = collections.defaultdict(list)
    for item in pool:
        by_identity[(item[1]["task"], int(item[1]["seed"]), item[1]["spec_sha256"])].append(item)
    chosen = []
    for key, items in by_identity.items():
        counters["dedup"] += len(items) - 1
        counters[f"dedup_{tier}"] = counters.get(f"dedup_{tier}", 0) + len(items) - 1
        if key in wanted:
            items = [it for it in items if it[0] == wanted[key]["snapshot"]] or items
        chosen.append(items[0])
    rows_out, seen = [], set()
    out_of_band = []
    for snapshot, row, result in sorted(chosen, key=lambda it: (hard_specs.ALL_TASKS.index(it[1]["task"]), int(it[1]["episode"]))):
        key = (row["task"], int(row["episode"]))
        if key in seen:
            raise SystemExit(f"{tier} 候选编号冲突：{key}（不同 seed 或规格占同一 episode）")
        seen.add(key)
        identity = (row["task"], int(row["seed"]), row["spec_sha256"])
        selected = identity in wanted
        if selected and wanted[identity]["episode"] != int(row["episode"]):
            raise SystemExit(f"评估行 episode 与规格行不符：{identity}")
        rollout = None
        if result is not None:
            rollout = {
                "status": "ok" if result["ok"] else "failed",
                "round": int(result.get("round", 0)),
                "role": result.get("role"),
                "env_package": "robomme",
                "code_baseline": CODE_BASELINE,
                "source": f"artifacts/newtask-v6/{snapshot}/{tier}/rollout/run1/results.jsonl",
                "source_run": wanted[identity]["source_run"] if selected else snapshot,
            }
            if result["ok"]:
                path = str(REPO / result["h5"]) if not str(result["h5"]).startswith("/") else result["h5"]
                rollout["h5_path"] = str(Path(path).relative_to(REPO))
                stat = (stats or {}).get(path)
                if stat is None or not Path(path).is_file():
                    rollout.update({"h5_sha256": None, "bytes": None, "frames": None, "demo_frames": None,
                                    "h5_missing": True})
                else:
                    rollout.update({"h5_sha256": stat["sha256"], "bytes": stat["bytes"], "frames": stat["frames"],
                                    "demo_frames": stat["demo_frames"]})
                    band = DEMO_BAND.get(tier)
                    if (selected and band and row["task"] in DEMO_BAND_TASKS
                            and not band[0] <= stat["demo_frames"] <= band[1]):
                        out_of_band.append(f"{row['task']}/{row['episode']}:{stat['demo_frames']}")
            else:
                rollout["error_type"] = result.get("error_type")
        if selected and (rollout is None or rollout["status"] != "ok"):
            raise SystemExit(f"正式交付身份没有成功的生成结果：{identity}")
        rows_out.append({
            "record": "spec", "task": row["task"], "tier": tier, "candidate": int(row["episode"]),
            "episode": int(row["episode"]), "seed": int(row["seed"]), "attempt": int(row["attempt"]),
            "spec": row["spec"], "spec_sha256": row["spec_sha256"],
            "selected": selected, "tried": result is not None,
            "initial_selected": int(row["episode"]) in set(headers[snapshot]["select_indices"]),
            "rollout": rollout,
        })
    tasks = [t for t in hard_specs.ALL_TASKS if any(t in h["tasks"] for h in headers.values())]
    per_env = {}
    for task in tasks:
        task_rows = [r for r in rows_out if r["task"] == task]
        per_env[task] = {
            "attempted": sum(draw_stats[s].get(task, {}).get("attempted", 0) for s in sources),
            "candidates": len(task_rows),
            "initial_selected": sorted(r["candidate"] for r in task_rows if r["initial_selected"]),
        }
    header = {
        "record": "header",
        "schema": hard_specs.SCHEMA,
        "difficulty": tier,
        "tasks": tasks,
        "per_env": per_env,
        "runtime": main["runtime"],
        "seed_rule": main["seed_rule"],
        "select_rule": {"rule": "以上次 SimpleMemVLA 评估的 1100 个身份为准（eval-identities-1100.jsonl）",
                        "delivery_per_cell": DELIVERY_PER_CELL},
        "sampling_config": main["sampling_config"],
        "sampling_config_sha256": hard_specs.digest(main["sampling_config"]),
        "recovery_rule": main["recovery_rule"],
        "identity_source": "smvla-0927+fill",
        "run_id": f"test-hard-{tier}",
        "draw_stats": draw_stats,
        "drafts_sha256": drafts_sha,
        "legacy_identity_sha256": legacy_ids,
        "provenance": {"base_fingerprint": hard_specs.base_fingerprint(),
                       "hard_fingerprint": hard_specs.hard_fingerprint(), "env_package": "robomme_hard",
                       "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
        "delivery_per_cell": DELIVERY_PER_CELL,
        "source_files": source_files,
        "eval_identities_sha256": counters["eval_identities_sha256"],
        "dedup_dropped": counters.get(f"dedup_{tier}", 0),
        "demo_frames_out_of_band": {"band": list(DEMO_BAND[tier]), "tasks": list(DEMO_BAND_TASKS),
                                    "scope": "正式交付局", "count": len(out_of_band), "episodes": out_of_band}
        if tier in DEMO_BAND else None,
    }
    if header["demo_frames_out_of_band"] is None:
        del header["demo_frames_out_of_band"]
    header["identity_sha256"] = hard_specs.identity_sha256(header, rows_out)
    header["delivery_sha256"] = hard_specs.delivery_sha256(rows_out)
    hard_specs.validate_specs(header, rows_out)
    return header, rows_out


def write_exclusive(path: Path, records: list[dict[str, Any]]) -> None:
    if path.exists():
        raise SystemExit(f"{path} 已存在，禁止覆盖")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".hardspecs-", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        for record in records:
            stream.write(hard_specs.canonical_json(record) + "\n")
    os.chmod(name, 0o644)
    os.link(name, path)
    os.unlink(name)


def collect_h5_paths() -> list[str]:
    paths = []
    for tier, snapshots in TIER_SOURCES.items():
        for snapshot in snapshots:
            for row in results_rows(snapshot, tier):
                if row["ok"]:
                    path = row["h5"] if str(row["h5"]).startswith("/") else str(REPO / row["h5"])
                    if Path(path).is_file():
                        paths.append(path)
    return paths


def gates(identities: list[dict[str, Any]], built: dict[str, tuple], stats, counters) -> bool:
    merged = sum(len(rows) for _, rows in built.values())
    delivered = [r for _, rows in built.values() for r in rows if hard_specs.delivered(r)]
    ok_pool = counters["raw"] - counters["dedup"] == merged and len(delivered) == 1100
    print(f"SOURCE_POOL={'PASS' if ok_pool else 'FAIL'} raw={counters['raw']} dedup={counters['dedup']} "
          f"merged={merged} delivery={len(delivered)} nondelivery={merged - len(delivered)}")
    legacy_ok = counters["legacy_equal"] == counters["legacy_total"] == 6
    print(f"SPECS_IDENTITY={'PASS' if legacy_ok else 'FAIL'} files={counters['legacy_total']} tiers=4 "
          f"legacy_equal={counters['legacy_equal']}")
    want = {(i["task"], i["tier"], i["seed"], i["spec_sha256"]) for i in identities}
    have = {(r["task"], r["tier"], r["seed"], r["spec_sha256"]) for r in delivered}
    cells = collections.Counter((r["task"], r["tier"]) for r in delivered)
    cells_ok = set(cells) == set(hard_specs.EXPECTED_CELLS) and set(cells.values()) == {DELIVERY_PER_CELL}
    ds_ok = want == have and len(want) == 1100 and cells_ok
    print(f"DELIVERY_SET={'PASS' if ds_ok else 'FAIL'} compared={len(want)} equal={len(want & have)} "
          f"cells={len(cells)} shape=13x3x20+16x20")
    mismatch = missing = 0
    details = []
    for row in delivered:
        rollout = row["rollout"]
        path = str(REPO / rollout["h5_path"])
        stat = stats.get(path)
        if stat is None or rollout.get("h5_missing"):
            missing += 1
            details.append(f"missing:{row['task']}/{row['tier']}/{row['candidate']}")
            continue
        setup = stat["setup"]
        bad = (setup["seed"] != row["seed"] or setup["difficulty"] != row["tier"] or not any(setup["task_goal"])
               or stat["sha256"] != rollout["h5_sha256"] or stat["bytes"] != rollout["bytes"]
               or stat["frames"] != rollout["frames"] or stat["episodes"] != 1)
        if bad:
            mismatch += 1
            details.append(f"mismatch:{row['task']}/{row['tier']}/{row['candidate']}")
    hb_ok = mismatch == 0 and missing == 0 and len(delivered) == 1100
    print(f"H5_BINDING={'PASS' if hb_ok else 'FAIL'} compared={len(delivered)} mismatch={mismatch} ambiguous=0 "
          f"missing={missing}" + (f" detail={details[:10]}" if details else ""))
    return ok_pool and legacy_ok and ds_ok and hb_ok


def cmd_build(args) -> int:
    identities = eval_identities()
    if len(identities) != 1100:
        raise SystemExit(f"评估身份应为 1100 行，实为 {len(identities)}")
    id_lines = [{k: r[k] for k in ("source_run", "task", "tier", "episode", "seed", "spec_sha256")} for r in identities]
    id_text = "".join(hard_specs.canonical_json(r) + "\n" for r in id_lines)
    counters: dict[str, Any] = collections.Counter()
    counters["eval_identities_sha256"] = sha256_text(id_text)
    stats = all_h5_stats(collect_h5_paths(), args.workers)
    built = {tier: build_tier(tier, identities, stats, counters) for tier in hard_specs.TIERS}
    ok = gates(identities, built, stats, counters)
    if not ok:
        print("MIGRATE=FAIL 未写出任何文件")
        return 1
    if args.dry_run:
        print("MIGRATE=DRY_RUN")
        return 0
    if not IDENTITIES_OUT.exists():
        IDENTITIES_OUT.parent.mkdir(parents=True, exist_ok=True)
        IDENTITIES_OUT.write_text(id_text)
    elif hashlib.sha256(IDENTITIES_OUT.read_bytes()).hexdigest() != counters["eval_identities_sha256"]:
        raise SystemExit(f"{IDENTITIES_OUT} 已存在且内容不同")
    for tier, (header, rows) in built.items():
        write_exclusive(OUT_ROOT / tier / "specs.jsonl", [header, *rows])
        print(f"WROTE {tier} rows={len(rows)} delivered={sum(hard_specs.delivered(r) for r in rows)} "
              f"identity={header['identity_sha256'][:12]} delivery={header['delivery_sha256'][:12]}")
    print(f"EVAL_IDENTITIES sha256={counters['eval_identities_sha256']} rows=1100 out={IDENTITIES_OUT.relative_to(REPO)}")
    return 0


def cmd_check(args) -> int:
    """重读包内 jsonl（完整封套校验）并与来源重比；h5 统计走缓存（mtime+字节数不变才复用）。"""
    identities = eval_identities()
    counters: dict[str, Any] = collections.Counter()
    id_text = "".join(hard_specs.canonical_json({k: r[k] for k in ("source_run", "task", "tier", "episode", "seed",
                                                                  "spec_sha256")}) + "\n" for r in identities)
    counters["eval_identities_sha256"] = sha256_text(id_text)
    stats = all_h5_stats(collect_h5_paths(), args.workers)
    built = {}
    for tier in hard_specs.TIERS:
        header, rows = hard_specs.load_specs(hard_specs.packaged_specs_path(tier))
        fresh_header, fresh_rows = build_tier(tier, identities, stats, counters)
        same = (header["identity_sha256"] == fresh_header["identity_sha256"]
                and header["delivery_sha256"] == fresh_header["delivery_sha256"])
        print(f"PACKAGED_{tier.upper()}={'PASS' if same else 'FAIL'} rows={len(rows)} "
              f"identity={header['identity_sha256'][:12]} delivery={header['delivery_sha256'][:12]}")
        built[tier] = (header, rows)
    return 0 if gates(identities, built, stats, counters) else 1


# ── S4 setup 清单与 TIER_MAX_STEPS_SOURCE ────────────────────────────────────


def cmd_export_s4_setup(args) -> int:
    delivery = json.loads(S4_DELIVERY.read_text())
    items = []
    for s in delivery["successes"]:
        h5 = [f for f in s["files"] if f["path"].endswith(".h5")]
        if len(h5) != 1:
            raise SystemExit(f"S4 交付 {s['task']}/{s['difficulty']}/{s['episode']} 的 h5 不唯一")
        items.append((s, h5[0]))
    stats = all_h5_stats([f["path"] for _, f in items], args.workers)
    entries, max_exec = [], collections.defaultdict(int)
    sha_bad = 0
    for s, f in items:
        stat = stats[f["path"]]
        sha_bad += int(stat["sha256"] != f["sha256"] or stat["bytes"] != f["bytes"])
        max_exec[s["difficulty"]] = max(max_exec[s["difficulty"]], stat["frames"] - stat["demo_frames"])
        entries.append({"task": s["task"], "tier": s["difficulty"], "episode": int(s["episode"]),
                        "seed": int(s["seed"]), "spec_sha256": s["spec_sha256"], "h5_sha256": stat["sha256"],
                        "h5_bytes": stat["bytes"], "frames": stat["frames"], "demo_frames": stat["demo_frames"],
                        "setup": stat["setup"]})
    entries.sort(key=lambda e: (hard_specs.TIERS.index(e["tier"]), e["task"], e["episode"]))
    manifest = {"schema": "s4-setup/1", "source": str(S4_DELIVERY.relative_to(REPO)),
                "source_sha256": hashlib.sha256(S4_DELIVERY.read_bytes()).hexdigest(),
                "code_baseline": delivery["code_baseline"], "count": len(entries), "entries": entries}
    manifest["manifest_sha256"] = hard_specs.digest(manifest)
    print(f"S4_SETUP count={len(entries)} sha_mismatch_vs_final_delivery={sha_bad}")
    if sha_bad:
        print("S4_SETUP=FAIL")
        return 1
    if S4_SETUP_OUT.exists():
        old = json.loads(S4_SETUP_OUT.read_text())
        if old.get("manifest_sha256") != manifest["manifest_sha256"]:
            raise SystemExit(f"{S4_SETUP_OUT} 已存在且内容不同")
    else:
        S4_SETUP_OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    values = "/".join(str(hard_specs.TIER_MAX_STEPS[t]) for t in hard_specs.TIERS)
    execs = "/".join(str(max_exec[t]) for t in hard_specs.TIERS)
    legacy = subprocess.run(["git", "-C", str(REPO), "show", "HEAD:scripts/eval/v4_eval.py"],
                            capture_output=True, text=True).stdout
    same = 'NEWVALUE_MAX_STEPS = {"xhard1": 1500, "xhard2": 1700, "xhard3": 2000, "xhard4": 2600}' in legacy
    below = all(max_exec[t] < hard_specs.TIER_MAX_STEPS[t] for t in hard_specs.TIERS)
    print(f"TIER_MAX_STEPS_SOURCE={'PASS' if same and below else 'FAIL'} tiers=4 values={values} "
          f"same_as=v4_eval.NEWVALUE_MAX_STEPS:{int(same)} max_exec={execs}")
    return 0 if same and below else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("build", "check", "export-s4-setup"))
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return {"build": cmd_build, "check": cmd_check, "export-s4-setup": cmd_export_s4_setup}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
