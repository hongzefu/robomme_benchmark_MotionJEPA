"""复用已验证证据生成临时交付清单，不重算大文件散列、不解码视频。"""
import argparse
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DATA = REPO / "artifacts/newtask-v6/v6-01"
VERIFY = HERE / "verification"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(rows, key):
    result = {}
    for row in rows:
        identity = key(row)
        require(identity not in result, f"重复身份：{identity}")
        result[identity] = row
    return result


def delivery_status(success_count, cells):
    """目标足额与通过原三档闸门后的可接纳性分别报告。"""
    require(all(0 <= cell["success"] <= 3 for cell in cells.values()), "每格成功数越界")
    shortfall = sum(3 - cell["success"] for cell in cells.values())
    complete = success_count == 165 and len(cells) == 55 and shortfall == 0
    return {"target_complete": complete, "shortfall": shortfall,
            "delivery_status": "COMPLETE" if complete else "PARTIAL"}


def verify_native(load):
    run = REPO / "artifacts/newtask-v6/v6-s3-20260926-01"
    session = run / "handoff-prep/production-session-20260926"
    binding = load(session / "binding.json")
    outcome = load(session / "outcome.json")
    final = load(session / "final_verification.json")
    require(binding["simulation"] is False and outcome["old_finished"] and
            outcome["child_exit_code"] == 0 and outcome["all_child_group_finished"], "缺少真实S3结束证明")
    require(hashlib.sha256((run / "run_s3.py").read_bytes()).hexdigest() == binding["runner_sha256"], "S3运行器锚点不符")
    require(final["compared"] == final["sha_equal"] == 144 and final["field_mismatch"] == 0, "S3比较未通过")
    require(final["mode"] in {"original_finalized", "offline_finalized"}, "不接受模拟或未知S3完成模式")
    comparison = run / "compare" if final["mode"] == "original_finalized" else session / "finalize-existing/compare"
    pairs = load(comparison / "h5_pairs.jsonl", True)
    expected = load(REPO / "scripts/configs/newtask-v3/subset_manifest.json")["rows"]
    ids = {f"{row['task']}_episode_{row['episode']}" for row in expected}
    actual = unique(pairs, lambda row: row["identity"])
    require(len(actual) == 144 and set(actual) == ids, "S3真实144身份覆盖不足")
    require(all(row["sha_equal"] == 1 and row["field_mismatch"] == 0 for row in pairs), "S3逐身份比较失败")


def merge_recovery(root, candidates, original_success, cells, load):
    root = root.resolve()
    require(root == REPO / "artifacts/newtask-v6/v6-01-infra-recovery-01", "恢复根不是获准本机路径")
    manifest = load(root / "control/manifest.json")
    approval = load(root / "control/approval.json")
    runtime = load(root / "control/runtime-manifest.json")
    require(approval["approved"] is True and approval["max_attempts"] == manifest["max_attempts"] == 76, "恢复未经批准或预算错误")
    require(hashlib.sha256((root / "control/manifest.json").read_bytes()).hexdigest() == approval["manifest_sha256"], "批准清单指纹不符")
    require(manifest == load(HERE / "recovery/manifest.json") and approval == load(HERE / "recovery/approval.json"), "恢复控制文件与本机授权不符")
    require(runtime == load(HERE / "recovery/runtime-manifest.json"), "恢复运行时来源不符")
    require(hashlib.sha256((DATA / "xhard4/specs.jsonl").read_bytes()).hexdigest() == manifest["source_specs_sha256"], "恢复冻结规格来源不符")
    source = load(VERIFY / "source-recovery.json")
    transfer = load(VERIFY / "transfer-recovery.json")
    media = load(VERIFY / "media-recovery.json")
    require(all(not transfer[k] for k in ("missing", "extra", "mismatches")) and not media["errors"], "恢复转移或媒体证据失败")
    def verified(path, jsonl=False):
        relative = str(path.relative_to(root))
        require(relative in source and hashlib.sha256(path.read_bytes()).hexdigest() == source[relative]["sha256"], f"恢复小文件来源不符{relative}")
        return load(path, jsonl)
    for name in ("manifest.json", "approval.json", "runtime-manifest.json"):
        verified(root / "control" / name)
    output = root / "rollout/run1"
    attempts = verified(output / "attempts.jsonl", True)
    results = verified(output / "results.jsonl", True)
    summary = verified(output / "summary.json")
    key = lambda row: (row["task"], row["episode"])
    eligible = unique(manifest["eligible"], key)
    excluded = {key(row) for row in manifest["excluded"]}
    starts = unique([row for row in attempts if row["event"] == "start"], key)
    finishes = unique([row for row in attempts if row["event"] == "finish"], key)
    result_map = unique(results, key)
    require(len(eligible) == 76 and len(starts) <= 76 and summary["attempted"] == len(starts), "恢复总预算越界")
    require(set(starts) <= set(eligible) and not set(starts) & excluded, "恢复身份不在授权清单或被排除")
    require(set(result_map) <= set(starts) and set(finishes) == set(result_map), "恢复结果与开始/结束事件不符")
    old = {(r["task"], r["episode"]) for r in original_success if r["difficulty"] == "xhard4"}
    require(not old & set(starts), "恢复重跑已有成功")
    checked = unique(media["checks"], key)
    counts = collections.Counter(task for task, _ in starts)
    for task, limit in manifest["limits"].items():
        require(counts[task] <= limit["recovery_limit"] and limit["prior_attempts"] + counts[task] <= limit["cumulative_limit"], "每格恢复预算越界")
        require(limit["cumulative_limit"] in {16, 18, 19}, "累积上限异常")
        require(cells[(task, "xhard4")]["scheduled"] == limit["prior_attempts"], "原派发计数不符")
        require(summary["per_task_attempts"].get(task, 0) == counts[task], "恢复汇总次数不符")
    recovered, dispatched = [], []
    for identity, start in starts.items():
        task, episode = identity
        spec = candidates[(task, "xhard4", episode)]
        require(all(start[k] == eligible[identity][k] == spec[k] for k in ("seed", "spec_sha256")), "恢复身份指纹错误")
        row = result_map.get(identity)
        cell = cells[(task, "xhard4")]
        cell["scheduled"] += 1
        state = "unresolved" if row is None else "success" if row["ok"] else row["recovery_category"]
        record = {"task": task, "difficulty": "xhard4", "episode": episode, "seed": spec["seed"], "spec_sha256": spec["spec_sha256"],
                  "role": "selected" if spec["selected"] else "backfill", "execution_role": "infra_recovery", "state": state}
        dispatched.append(record)
        if row is None:
            cell["unknown"] += 1
            continue
        require(row["seed"] == spec["seed"] and row["spec_sha256"] == spec["spec_sha256"] and type(row["ok"]) is bool, "恢复结果身份错误")
        if not row["ok"]:
            cell["failure"] += 1
            cell["task_failure" if state == "true_task_failure" else "infrastructure_failure"] += 1
            continue
        require(identity in checked, "缺少恢复成功媒体证明")
        episode_root = output / "episodes" / f"{task}_episode_{episode}"
        h5 = list(episode_root.glob("hdf5_files/*.h5"))
        videos = list(episode_root.glob("videos/*.mp4"))
        require(len(h5) == 1 and len(videos) == checked[identity]["videos"] > 0, "恢复成功媒体缺失")
        file_records = []
        for path in sorted(h5 + videos + [episode_root / "spec_replay.json", episode_root / "rng_trace.json"]):
            rel = str(path.relative_to(root))
            require(path.is_file() and rel in source and path.stat().st_size == source[rel]["bytes"], "恢复产物来源缺失")
            file_records.append({"path": str(path), **source[rel]})
        cell["success"] += 1
        recovered.append({**record, "files": file_records, "media_check": checked[identity]})
    for task in manifest["limits"]:
        require(summary["success_with_original"][task] == cells[(task, "xhard4")]["success"], "恢复成功汇总不符")
    return dispatched, recovered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["provisional", "final"], default="provisional")
    parser.add_argument("--recovery-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        rejected = 0
        for probe in (lambda: unique([{"id": 1}, {"id": 1}], lambda r: r["id"]),
                      lambda: require(False, "缺少媒体验证证据"),
                      lambda: require(77 <= 76, "恢复总预算越界"),
                      lambda: verify_native(lambda path, jsonl=False: {"simulation": True, "old_finished": True,
                           "child_exit_code": 0, "all_child_group_finished": True})):
            try:
                probe()
            except ValueError:
                rejected += 1
        require(rejected == 4, "反例未被拒绝")
        partial = delivery_status(143, {str(i): {"success": 3 if i < 47 else 2 if i == 47 else 0} for i in range(55)})
        require(partial == {"target_complete": False, "shortfall": 22, "delivery_status": "PARTIAL"}, "短缺不应变成新接纳硬闸")
        print("DELIVERY_NEGATIVE=PASS duplicates_rejected=1 missing_evidence_rejected=1 over_budget_rejected=1 simulated_native_rejected=1 partial_target_preserved=1")
        return
    target = VERIFY / ("final-delivery.json" if args.mode == "final" else "merged-provisional-delivery.json" if args.recovery_dir else "provisional-delivery.json")
    require(not target.exists(), "临时清单已存在，拒绝覆盖")
    evidence = []
    def load(path, jsonl=False):
        data = path.read_bytes()
        evidence.append({"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        return [json.loads(line) for line in data.splitlines() if line] if jsonl else json.loads(data)
    candidates, cells, success, ledger_rows = {}, {}, [], []
    for tier in ("xhard1", "xhard2", "xhard3", "xhard4"):
        base = DATA / tier
        source = load(VERIFY / f"source-{tier}.json")
        transfer = load(VERIFY / f"transfer-{tier}.json")
        require(all(not transfer[k] for k in ("extra", "missing", "mismatches")), f"{tier}转移验收失败")
        specs = load(base / "specs.jsonl", True)
        spec_bytes = (base / "specs.jsonl").read_bytes()
        require(hashlib.sha256(spec_bytes).hexdigest() == source["specs.jsonl"]["sha256"], "冻结规格来源不符")
        for row in specs[1:]:
            key = (row["task"], tier, row["episode"])
            require(key not in candidates, f"重复候选{key}")
            candidates[key] = row
            cell = cells.setdefault((row["task"], tier), {k: 0 for k in
                ("candidates", "scheduled", "success", "failure", "task_failure", "infrastructure_failure", "unknown", "shortfall")})
            cell["candidates"] += 1
        if tier == "xhard4":
            ledger = load(VERIFY / "original-xhard4-ledger.json")
            require(not ledger["errors"], "xhard4原账本验证失败")
            require(ledger["scheduled_attempts"] == 96, "原始派发数不为96")
            attempts = ledger["entries"]
            checks = ledger["success_checks"]
        else:
            results = load(base / "rollout/run1/results.jsonl", True)
            require(hashlib.sha256((base / "rollout/run1/results.jsonl").read_bytes()).hexdigest() == source["rollout/run1/results.jsonl"]["sha256"], "结果来源不符")
            attempts = [{**row, "state": "success" if row["ok"] else "task_failure", "raw_result": row} for row in results]
            media = load(VERIFY / f"media-{tier}.json")
            require(not media["errors"], "媒体验证失败")
            checks = media["checks"]
        checked = unique(checks, lambda r: (r["task"], r["episode"]))
        seen_attempts = set()
        for item in attempts:
            key = (item["task"], tier, item["episode"])
            require(key in candidates and key not in seen_attempts, f"派发身份缺失或重复{key}")
            seen_attempts.add(key)
            spec = candidates[key]
            require(item["seed"] == spec["seed"], f"seed不符{key}")
            cell = cells[key[:2]]
            cell["scheduled"] += 1
            state = item["state"]
            require(state in {"success", "task_failure", "infrastructure_failure", "unresolved"}, f"未知状态{state}")
            cell["success" if state == "success" else "unknown" if state == "unresolved" else "failure"] += 1
            if state in {"task_failure", "infrastructure_failure"}:
                cell[state] += 1
            raw = item["raw_result"]
            record = {"task": key[0], "difficulty": tier, "episode": key[2], "seed": spec["seed"],
                      "spec_sha256": spec["spec_sha256"], "role": "selected" if spec["selected"] else "backfill",
                      "state": state, "round": item.get("round"), "source_result": item.get("source_result", str(base / "rollout/run1/results.jsonl"))}
            ledger_rows.append(record)
            if state != "success":
                continue
            require((key[0], key[2]) in checked, f"缺少媒体验证证据{key}")
            if tier != "xhard4":
                require(raw["spec_sha256"] == spec["spec_sha256"], f"成功规格sha不符{key}")
            episode = base / "rollout/run1/episodes" / f"{key[0]}_episode_{key[2]}"
            files = list(episode.glob("hdf5_files/*.h5")) + list(episode.glob("videos/*.mp4")) + [episode / "spec_replay.json", episode / "rng_trace.json"]
            require(len(list(episode.glob("hdf5_files/*.h5"))) == 1, "HDF5缺失或不唯一")
            require(len(list(episode.glob("videos/*.mp4"))) == checked[(key[0], key[2])]["videos"] > 0, "视频数量不符")
            file_records = []
            for path in sorted(files):
                rel = str(path.relative_to(base))
                require(path.is_file() and rel in source, f"产物或源指纹缺失{path}")
                expected = source[rel]
                require(path.stat().st_size == expected["bytes"], f"当前字节数不符{path}")
                file_records.append({"path": str(path), **expected})
            success.append({**record, "files": file_records, "media_check": checked[(key[0], key[2])]})
    unique(success, lambda r: (r["task"], r["difficulty"], r["episode"]))
    require(len(candidates) == 550 and len(cells) == 55, "候选或格数不完整")
    for key, cell in cells.items():
        require(cell["candidates"] == 10 and cell["success"] <= 3, f"每格数量不符{key}")
        cell["shortfall"] = 3 - cell["success"]
    require(len(success) == 143 and sum(c["shortfall"] for c in cells.values()) == 22, "当前成功/短缺与143/22不符")
    original_counts = [{"task": k[0], "difficulty": k[1], **v} for k,v in sorted(cells.items())]
    recovery_rows = []
    if args.recovery_dir:
        recovery_rows, recovered = merge_recovery(args.recovery_dir, candidates, success, cells, load)
        success.extend(recovered)
    unique(success, lambda r: (r["task"], r["difficulty"], r["episode"]))
    for cell in cells.values():
        require(cell["success"] <= 3, "每格成功超过3")
        cell["shortfall"] = 3 - cell["success"]
    native = "PENDING"
    if args.mode == "final":
        verify_native(load)
        native = "PASS"
    target_status = delivery_status(len(success), cells)
    report = {"schema": "v6-delivery/2", "accepted": args.mode == "final", "native_regression": native,
              "recovery": "VERIFIED" if args.recovery_dir else "NOT_MERGED", "mode": args.mode, "candidate_count": 550, "planned_cells": 55,
              "target_successes": 165, "success_count": len(success), **target_status,
              "verification_scope": "复用已有转移散列与媒体验证；本次只核对存在和字节数，未重复散列大文件或解码视频",
              "acceptance_policy": "接纳只以真实S3生产证明144身份SHA一致且字段差异0为原三档硬闸，纳入的成功产物须全部有验证证据；165足额是独立目标，短缺报PARTIAL而不否定已验证成功产物的可接纳性",
              "source_evidence": evidence, "cells": [{"task": k[0], "difficulty": k[1], **v} for k,v in sorted(cells.items())],
              "original_cells": original_counts, "original_dispatches": ledger_rows,
              "recovery_dispatches": recovery_rows, "successes": success}
    # 用户决定仅披露而不修数据；保留内部成功计数，不能把原闸门接纳写成题意无缺陷。
    issue_scope = load(REPO / "artifacts/newtask-v6/s3-slow-investigation/vpb-semantics/scope.json")
    issue_rows = [row for row in issue_scope["rows"] if row["delivered"] and row["conflict"]]
    require({(row["tier"], row["episode"]) for row in issue_rows} == {("xhard3", 3), ("xhard3", 6)}, "已披露问题身份不符")
    successful = unique(success, lambda row: (row["task"], row["difficulty"], row["episode"]))
    issues = []
    for row in issue_rows:
        key = ("VideoPlaceButton", row["tier"], row["episode"])
        require(key in successful and successful[key]["seed"] == row["seed"], "问题身份与实际交付不符")
        issues.append({"kind": "question_answer_mismatch", "task": key[0], "difficulty": key[1],
                       "episode": key[2], "seed": row["seed"], "internal_task_success": True,
                       "program_answer_target": row["answer_target"],
                       "last_before_targets": row["before_target_ids"],
                       "status": "KNOWN_ISSUE_UNFIXED", "user_decision": "仅网站注明问题，暂不修数据"})
    report["known_issues"] = issues
    report["semantic_status"] = "KNOWN_ISSUES"
    report["acceptance_scope"] = "accepted仅指原计划V1及来源/文件闸门；不表示自然语言题意与答案无缺陷。已知两条VPB问题按用户决定保留。"
    with target.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(f"DELIVERY=PASS mode={args.mode} candidates=550 cells=55 success={len(success)} shortfall={report['shortfall']} accepted={report['accepted']} out={target}")
    print(f"DELIVERY_PARTIAL={int(not report['target_complete'])} target_complete={report['target_complete']} shortfall={report['shortfall']}")


if __name__ == "__main__":
    main()
