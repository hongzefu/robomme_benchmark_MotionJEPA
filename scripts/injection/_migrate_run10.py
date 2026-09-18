"""运行十的清单驱动迁移：先准备结果和冻结映射，再按日志移动与核验。"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path

from .candidates.io import candidate_key
from .rollout.state import ROOT, RunStore, StateError, file_sha, read_rows, run_root, write_json, atomic_text, assign_roles


def _raw_key(row):
    return row["task"], row["difficulty"], row["episode"]


def _index(rows):
    result = {}
    for row in rows:
        key = _raw_key(row)
        if key in result:
            raise StateError(f"旧输入重复：{key}")
        result[key] = row
    return result


def prepare(root):
    store = RunStore(root)
    logs = store.logs / "migration"
    with store.locked():
        marker = logs / "prepared.json"
        if marker.exists():
            return store.audit()
        baseline = store.logs / "baseline/manifest.json"
        if not baseline.exists():
            raise StateError("阶段三旧基线未冻结，拒绝归并")
        header, candidates, existing = store.load()
        if existing:
            raise StateError("运行十已有新结果，拒绝重新覆盖")
        index = {candidate_key(r): r for r in candidates}
        old_rows = read_rows(root / "feasibility/P01x20/episode_results.jsonl")
        raw = _index(old_rows)
        delivery = json.loads((root / "delivery_manifest.json").read_text())
        selected = {}
        expected_roles = {}
        for name, group in delivery["groups"].items():
            task, difficulty = name.split("/")
            for field, role in (("primary", "primary"), ("spare_rows", "spare"), ("failures", "failed")):
                for original in group[field]:
                    row = {"task": task, "difficulty": difficulty, **original}
                    if row["task"] != task or row["difficulty"] != difficulty:
                        raise StateError("交付组与记录身份不符")
                    key = _raw_key(row)
                    if key in expected_roles:
                        raise StateError("交付清单重复候选")
                    expected_roles[key] = role
                    if role != "failed":
                        selected[key] = row
        if set(raw) != set(expected_roles) or len(raw) != 1842:
            raise StateError("实跑结果与交付清单键集合不一致")
        results, aliases, alias_proofs = [], {}, []
        for key, old in raw.items():
            row = store.normalize(old, "h5", candidate_index=index)
            if row["ok"]:
                reference = selected[key]
                source = ROOT / reference["h5_path"]
                previous = Path(row["h5_path"])
                if not source.is_file() or source.stat().st_size != reference["bytes"]:
                    raise StateError(f"原交付文件缺失或大小漂移：{source}")
                row.update(h5_path=str(source), h5_sha256=reference["sha256"], h5_bytes=reference["bytes"])
                if previous != source:
                    if file_sha(previous) != reference["sha256"] or file_sha(source) != reference["sha256"]:
                        raise StateError("同条双份 HDF5 内容不同，不能建立对拍路径别名")
                    aliases[str(previous)] = str(source)
                    alias_proofs.append({"old": str(previous), "selected": str(source), "sha256": reference["sha256"]})
            results.append(row)
        reset_raw = []
        for path in sorted((root / "env_check").glob("*/*.jsonl")):
            reset_raw.extend(read_rows(path))
        reset_reference = _index(reset_raw)
        if len(reset_raw) != 720:
            raise StateError("旧 reset 范围不是 720 条")
        for old in reset_raw:
            results.append(store.normalize(old, "reset", candidate_index=index))
        groups = [f"{g['task']}/{g['difficulty']}" for g in header["delivery_config_snapshot"]["groups"]]
        test_header, test_candidates = copy.deepcopy(header), copy.deepcopy(candidates)
        checked = assign_roles(test_header, test_candidates, copy.deepcopy(results), groups)
        for row in checked:
            if row["kind"] == "h5" and row["role"] != expected_roles[candidate_key(row)]:
                raise StateError("重算的 h5 正式/备用角色与旧清单不一致")
            if row["kind"] == "reset":
                previous = reset_reference[candidate_key(row)]
                if row["delivered"] != previous["delivered"] or row["counted"] != previous["counted"]:
                    raise StateError("重算的 reset 角色与旧交付标志不一致")
        counts = test_header["roles"]
        expected = {"train/primary": 1600, "train/spare": 196, "train/failed": 46,
                    "test/primary": 700, "test/spare": 20, "test/unused": 838}
        if counts != expected:
            raise StateError(f"迁入角色数错误：{counts}")
        logs.mkdir(parents=True, exist_ok=True)
        selected_paths = {str((ROOT / v["h5_path"]).relative_to(root)): k for k, v in selected.items()}
        entries = []
        for child in sorted(root.iterdir()):
            if child.name in {"candidates", "rollout", "hf_release"}:
                continue
            files = sorted(child.rglob("*")) if child.is_dir() else [child]
            for source in files:
                if source.is_symlink():
                    raise StateError(f"旧产物含符号链接：{source}")
                if not source.is_file():
                    continue
                relative = source.relative_to(root)
                text = str(relative)
                if text in selected_paths:
                    task, difficulty, _ = selected_paths[text]
                    target = Path("rollout") / task / difficulty / "hdf5_files" / source.name
                elif relative.parts[:2] == ("feasibility", "P01x20") and len(relative.parts) >= 5:
                    tail = Path(*relative.parts[2:])
                    if "hdf5_files" in relative.parts:
                        target = Path("rollout/logs/smoke/duplicate-formal") / tail
                    else:
                        target = Path("rollout") / tail
                elif relative.parts[:2] == ("feasibility", "P0x1"):
                    target = Path("rollout/logs/smoke/legacy-P0x1") / Path(*relative.parts[2:])
                elif relative.parts[0] == "specs" or text in {"manifest.json", "plan_stats.json", "check_result.json"}:
                    target = Path("candidates/logs/legacy") / relative
                elif text in {"logs/plan.log", "logs/check.log"}:
                    target = Path("candidates/logs/legacy") / source.name
                else:
                    target = Path("rollout/logs/legacy") / relative
                if (root / target).exists():
                    raise StateError(f"迁移目标已存在：{target}")
                entries.append({"source": text, "target": str(target), "bytes": source.stat().st_size})
        if len({e["target"] for e in entries}) != len(entries):
            raise StateError("迁移目标冲突")
        write_json(logs / "path_map.json", {"entries": entries, "comparison_aliases": aliases,
                                            "comparison_source": {str((root / "feasibility/P01x20").relative_to(ROOT)): str((root / "rollout").relative_to(ROOT))},
                                            "alias_proofs": alias_proofs, "identity_sha256": header["identity_sha256"]})
        atomic_text(logs / "reference_h5.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in checked if r["kind"] == "h5"))
        atomic_text(logs / "reference_reset.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in checked if r["kind"] == "reset"))
        write_json(logs / "l4_scope.json", {"keys": [list(candidate_key(r)) for r in checked if r["kind"] == "reset"],
                                           "stop_episodes": {g: max(r["episode"] for r in checked if r["kind"] == "reset" and f"{r['task']}/{r['difficulty']}" == g) for g in groups}})
        store.publish(results, completed_groups=groups)
        report = store.audit()
        write_json(marker, {"passed": True, "roles": counts, "path_entries": len(entries), **report})
        print("RESULTS_EQUIVALENCE=PASS h5_rows=1842 primary=1600 spare=196 failed=46 reset_rows=720 reset_primary=700")
        print("ROLES_CONSISTENT=PASS rows=3400 mismatch=0 duplicates=0 pending=0 unused=838")
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare",))
    parser.add_argument("--run-id", default="20260912-contract-v3-10")
    args = parser.parse_args()
    prepare(run_root(args.run_id))


if __name__ == "__main__":
    main()
