"""离线逐条核对 V6 正式候选；不创建环境、不执行 reset。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.parity import v6_tier_monotone as tier_check
from scripts.parity.v4_specs import _read_jsonl, _check_sources

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "scripts/configs/newtask-v6/sampling_config.json"


def check_candidates(paths, sampling_config=DEFAULT_CONFIG):
    """固定检查 52 格各 10 条，来源与当前快照、源码逐项绑定。"""
    document = json.loads(Path(sampling_config).read_text(encoding="utf-8"))
    errors, mismatches, sources = [], [], []
    cells = {f"{env}/{tier}": {"episodes": [], "reset_failures": 0}
             for env in tier_check.GRADIENT_ENVS for tier in tier_check.NEWVALUE_TIERS}
    seen_tiers = set()
    for raw in paths:
        path = Path(raw)
        try:
            records = _read_jsonl(path)
            header = records[0]
            _check_sources(header, document, str(path))
            tier, _, _, _, rows, failures, _ = tier_check._read_v4_reset_file(path)
            if tier in seen_tiers:
                raise ValueError(f"重复档位 {tier}")
            seen_tiers.add(tier)
            attempts = set()
            for row in records[1:]:
                key = (row["task"], row["episode"], row["attempt"])
                if key in attempts:
                    raise ValueError(f"重复尝试 {key}")
                attempts.add(key)
            sources.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "tier": tier, "failure_counts_available": header["schema"] == "v4-drafts/1"})
            for env in tier_check.GRADIENT_ENVS:
                cells[f"{env}/{tier}"]["reset_failures"] = failures[env] if header["schema"] == "v4-drafts/1" else None
            for row in rows:
                env = row["task"]
                if env not in tier_check.GRADIENT_ENVS:
                    continue
                cell = cells[f"{env}/{tier}"]
                episode = row["episode"]
                if episode in cell["episodes"] or episode not in range(10):
                    raise ValueError(f"{env}/{tier} 重复或超出正式候选范围 episode={episode}")
                cell["episodes"].append(episode)
                try:
                    spec = row["spec"]
                    if env in {"VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap"}:
                        if type(spec.get("objects", {}).get("distractors", {}).get("placed")) is not int:
                            raise ValueError("干扰物缺少实际 placed 数，不能用 requested 替代")
                    actual = tier_check.dimensions_from_reset_spec(env, spec)
                    decision = dict(document["tasks"][env]["decision"])
                    # V6 不允许退回废弃的 xhard；某些环境档键位于 configs 子树。
                    decision.setdefault(tier, {})
                    expected = tier_check.dims_from_xhard_decision(env, decision, tier)
                    if set(actual) != set(expected):
                        raise ValueError("实际与配置梯度字段集合不同")
                    for dim, value in actual.items():
                        interval = tier_check.value_interval(expected[dim])
                        if interval is None or not interval[0] <= value <= interval[1]:
                            mismatches.append({"task": env, "tier": tier, "episode": episode,
                                               "field": dim, "actual": value, "expected": expected[dim]})
                except (KeyError, TypeError, ValueError) as exc:
                    mismatches.append({"task": env, "tier": tier, "episode": episode, "error": str(exc)})
        except Exception as exc:
            errors.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
    if len(paths) != 4 or seen_tiers != set(tier_check.NEWVALUE_TIERS):
        errors.append({"error": "必须提供四个不同档位的完整候选文件"})
    for cell in cells.values():
        cell["missing_episodes"] = sorted(set(range(10)) - set(cell["episodes"]))
    shortfall = sum(len(cell["missing_episodes"]) for cell in cells.values())
    # 冻结 spec 不保留失败尝试，不能将未知计为零或给完整验收 PASS。
    if any(not source["failure_counts_available"] for source in sources):
        errors.append({"error": "冻结 spec 不含失败尝试，完整验收请使用原始 drafts"})
    return {"schema": "v6-candidate-values/1", "verdict": "FAIL" if errors or mismatches or shortfall else "PASS",
            "cells": cells, "candidates": sum(len(c["episodes"]) for c in cells.values()),
            "shortfall": shortfall, "mismatches": mismatches, "input_errors": errors, "sources": sources,
            "sampling_config_sha256": hashlib.sha256(Path(sampling_config).read_bytes()).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drafts", action="append", required=True)
    parser.add_argument("--sampling-config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    output = Path(args.out).resolve()
    if not output.is_relative_to(ROOT):
        parser.error("报告必须位于仓库内")
    report = check_candidates(args.drafts, args.sampling_config)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"CANDIDATE_VALUES={report['verdict']} cells=52 candidates={report['candidates']} "
          f"mismatches={len(report['mismatches'])} shortfall={report['shortfall']} "
          f"input_errors={len(report['input_errors'])} out={output}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
