"""候选阶段入口；阶段一先实现冻结与筛查，图表在阶段六接入。"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from .contract import audit_overrides, load_contract
from .io import (CandidateError, RUNTIME, canonical_json, identity_sha256,
                 load_candidates, seed_for, write_candidates)
from .screen import ObservationCollector, screen_documents
from .specs import DEFAULT_SEED, GENERATOR_VERSION, build_group, difficulties_of, operand_sha256


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def checked_root(run_id):
    if not run_id or run_id in {".", ".."} or "/" in run_id or "\\" in run_id or run_id.startswith("."):
        raise CandidateError(f"运行编号非法：{run_id!r}")
    parent = REPO_ROOT / "artifacts" / "injection"
    root = parent / run_id
    if root.is_symlink() or root.resolve().parent != parent.resolve():
        raise CandidateError("运行目录不能指向外部位置")
    return root


def execute(args):
    root = checked_root(args.run_id)
    stage = root / "candidates"
    logs = stage / "logs"
    if stage.is_symlink() or logs.is_symlink():
        raise CandidateError("候选目录与日志目录不能是符号链接")
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "writer.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (stage / "candidates.jsonl").exists() or (root / "rollout" / "results.jsonl").exists() or (logs / "plan_meta.json").exists():
            raise CandidateError("候选或运行状态已存在，禁止覆盖；失败重试须换独立运行编号")
        return generate(args, root, stage, logs)


def generate(args, root, stage, logs):
    started = time.monotonic()
    sampling_path = Path(args.sampling_config).resolve()
    contract_path = Path(args.contract).resolve()
    delivery_path = Path(args.delivery_config).resolve()
    sampling = json.loads(sampling_path.read_text())
    contract = load_contract(contract_path)
    delivery = json.loads(delivery_path.read_text())
    from .config import load_delivery_config
    parsed_delivery = load_delivery_config(delivery_path, contract)
    _, problems = audit_overrides(contract, sampling)
    if problems:
        raise CandidateError(f"契约存在未登记差异：{problems}")
    if args.seed != contract.generator_seed:
        raise CandidateError("生成种子与契约不符")
    selected = [(g.task, g.difficulty) for g in contract.groups()]
    if args.groups:
        wanted = {tuple(name.split("/")) for name in args.groups}
        if not wanted.issubset(set(selected)):
            raise CandidateError("请求的组不在契约内")
        selected = [g for g in selected if g in wanted]
    if args.blocks is not None and (args.purpose != "smoke" or args.blocks < 1):
        raise CandidateError("只有 smoke 可显式指定正数 blocks")
    if args.reconstruct_run and (args.groups or args.blocks or args.purpose != "delivery"):
        raise CandidateError("重算补证必须覆盖完整旧运行")
    operand_sha = operand_sha256(sampling, difficulties_of(selected))
    old_docs = {}
    old_stats = {}
    old_files = {}
    if args.reconstruct_run:
        source = checked_root(args.reconstruct_run)
        manifest_path = source / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        for name in ("contract_sha256", "delivery_config_sha256", "generator_seed"):
            actual = {"contract_sha256": contract.sha256, "delivery_config_sha256": sha256(delivery_path), "generator_seed": args.seed}[name]
            if manifest[name] != actual:
                raise CandidateError(f"旧运行 {name} 与当前输入不一致")
        if manifest["sampling_operands_sha256"] != operand_sha or manifest["sampling_config_file_sha256"] != sha256(sampling_path):
            raise CandidateError("旧运行采样配置与当前输入不一致")
        old_files[manifest_path] = sha256(manifest_path)
        old_files[source / "plan_stats.json"] = sha256(source / "plan_stats.json")
        old_stats = json.loads((source / "plan_stats.json").read_text())
        for group in manifest["groups"]:
            key = (group["task"], group["difficulty"])
            path = source / group["path"]
            if key in old_docs or not path.resolve().is_relative_to(source.resolve()) or sha256(path) != group["file_sha256"]:
                raise CandidateError("旧清单重复、路径越界或散列不符")
            old_files[path] = sha256(path)
            old_docs[key] = json.loads(path.read_text())
        if set(old_docs) != set(selected):
            raise CandidateError("旧运行与新运行组集合不一致")
    meta = {"state": "running", "run_id": args.run_id, "source_run": args.reconstruct_run,
            "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip(),
            "started_at": datetime.now(timezone.utc).isoformat(), "sampling_file_sha256": sha256(sampling_path),
            "contract_sha256": contract.sha256, "delivery_config_sha256": sha256(delivery_path),
            "source_files": {str(p.relative_to(REPO_ROOT)): s for p, s in old_files.items()},
            "implementation_sha256": {str(p.relative_to(REPO_ROOT)): sha256(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
            "pyproject_sha256": sha256(REPO_ROOT / "pyproject.toml"), "uv_lock_sha256": sha256(REPO_ROOT / "uv.lock")}
    write_json(logs / "plan_meta.json", meta)
    docs = {}
    rows = []
    stats = {}
    origin = "reconstructed" if old_docs else "generated"
    with (logs / "rejections.jsonl").open("x", encoding="utf-8") as stream:
        observer = ObservationCollector(stream)
        for task, difficulty in selected:
            target = parsed_delivery.group(task, difficulty)
            blocks = args.blocks or target.blocks
            group = build_group(task, difficulty, sampling, contract, args.seed, blocks=blocks, observer=observer)
            doc = group.as_document(operand_sha)
            observer.check_stats(group)
            stats[f"{task}/{difficulty}"] = group.stats
            if old_docs:
                if canonical_json(doc) != canonical_json(old_docs[(task, difficulty)]):
                    raise CandidateError(f"完整旧规格对拍失败：{task}/{difficulty}")
                frozen_stats = {k: v for k, v in group.stats.items() if k != "rejections"}
                frozen_stats["rejection_samples"] = group.stats["rejections"][:8]
                if frozen_stats != old_stats[f"{task}/{difficulty}"]:
                    raise CandidateError(f"旧组统计对拍失败：{task}/{difficulty}")
            docs[(task, difficulty)] = doc
            for spec in group.episodes:
                ep = spec["episode"]
                rows.append({"record": "candidate", "task": task, "difficulty": difficulty,
                             "episode": ep, "block": ep // 100, "seed": seed_for(task, ep),
                             "spec_sha256": spec["spec_sha256"], "spec": spec,
                             "split": "train" if ep < target.run_episodes else "test", "role": "pending", "error_type": None,
                             "screening": observer.screening(spec, origin)})
            stream.flush()
            print(f"候选完成 {task}/{difficulty} rows={len(group.episodes)}", flush=True)
    verdicts, quota = screen_documents(docs, sampling, contract, args.seed)
    verdicts.add("SCREENING_EVIDENCE", True, rows=len(rows), groups=len(docs))
    if old_docs:
        expected = [(t, d, ep["episode"]) for (t, d), doc in old_docs.items() for ep in doc["episodes"]]
        actual = [(r["task"], r["difficulty"], r["episode"]) for r in rows]
        keys_ok = len(actual) == len(set(actual)) and sorted(actual) == sorted(expected)
        verdicts.add("PARITY_KEYS", keys_ok, layer="L1", expected=len(expected), actual=len(actual),
                     missing=len(set(expected) - set(actual)), extra=len(set(actual) - set(expected)), duplicates=len(actual) - len(set(actual)))
        verdicts.add("CANDIDATES_EQUIVALENCE", keys_ok, compared=len(rows), differences=0)
        verdicts.add("SOURCE_INTACT", all(sha256(p) == s for p, s in old_files.items()), files=len(old_files))
    write_json(logs / "quota_report.json", quota)
    write_json(logs / "check_result.json", {"passed": verdicts.passed, "verdicts": verdicts.records})
    write_json(logs / "group_stats.json", stats)
    if not verdicts.passed:
        raise CandidateError("候选筛查失败，未发布候选文件")
    header = {"record": "header", "run_id": args.run_id, "candidate_schema_version": 1,
              "spec_schema_version": 1, "generator_seed": args.seed, "generator_version": GENERATOR_VERSION,
              "contract": str(contract_path.relative_to(REPO_ROOT)), "contract_sha256": contract.sha256,
              "sampling_config_sha256": operand_sha, "sampling_file_sha256": sha256(sampling_path),
              "delivery_config": str(delivery_path.relative_to(REPO_ROOT)), "delivery_config_sha256": sha256(delivery_path),
              "groups": len(docs), "candidates": len(rows), "sampling_config": sampling,
              "delivery_config_snapshot": delivery, "runtime": RUNTIME, "purpose": args.purpose,
              "group_provenance": {f"{t}/{d}": {k: v for k, v in doc.items() if k != "episodes"} for (t, d), doc in docs.items()},
              "evidence_source": meta}
    header["identity_sha256"] = identity_sha256(header, rows)
    # 发布前先核当前源码指纹；失败不得留下可被误用的正式封套。
    from .io import validate_candidates
    validate_candidates(header, rows, repo_root=REPO_ROOT)
    write_candidates(stage / "candidates.jsonl", header, rows)
    load_candidates(stage / "candidates.jsonl", repo_root=REPO_ROOT)
    meta.update(state="complete", elapsed_s=round(time.monotonic() - started, 2), candidates=len(rows))
    write_json(logs / "plan_meta.json", meta)
    print(f"CANDIDATES=PASS rows={len(rows)} elapsed_s={meta['elapsed_s']}", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    defaults = REPO_ROOT / "scripts/configs/newtask-v2"
    parser.add_argument("--sampling-config", default=str(defaults / "native_sampling.json"))
    parser.add_argument("--contract", default=str(defaults / "injection_contract_v3.json"))
    parser.add_argument("--delivery-config", default=str(defaults / "delivery_400.json"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--purpose", choices=("delivery", "smoke"), default="delivery")
    parser.add_argument("--groups", nargs="+")
    parser.add_argument("--blocks", type=int)
    parser.add_argument("--reconstruct-run", help="只读旧运行，完整规格和统计相同后才发布重算证据")
    return execute(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
