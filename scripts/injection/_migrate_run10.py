"""运行十的清单驱动迁移：先准备结果和冻结映射，再按日志移动与核验。"""
from __future__ import annotations

import argparse
import copy
import json
import os
import fcntl
import re
import shutil
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def translate(value, paths, sources, key=None):
    """仅改登记的活动路径字段；错误文字、discarded 与历史日志保持原文。"""
    if key in {"discarded", "traceback", "error"}:
        return value
    if isinstance(value, dict):
        return {k: translate(v, paths, sources, k) for k, v in value.items()}
    if isinstance(value, list):
        return [translate(v, paths, sources, "path" if key == "no_object_paths" else key) for v in value]
    if isinstance(value, str):
        if key == "source":
            return sources.get(value, paths.get(value, value))
        if key in {"h5_path", "path", "video_path", "output_dir", "output_root", "spec_path", "candidates"}:
            return paths.get(value, value)
    return value


def _signature(path):
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def _checked_path(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise StateError(f"迁移路径越界或含符号链接：{relative}")
    return path


def hash_entries(root, entries, field):
    def one(entry):
        path = _checked_path(root, entry[field])
        before = _signature(path)
        sha = file_sha(path)
        if _signature(path) != before:
            raise StateError(f"散列期间文件变化：{path}")
        return entry[field], {"sha256": sha, "bytes": before[2], "signature": before}
    result = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(one, entry) for entry in entries]
        for future in as_completed(futures):
            key, data = future.result()
            result[key] = data
            if len(result) % 200 == 0:
                print(f"迁移散列 {field} {len(result)}/{len(entries)}", flush=True)
    return result


def move_entries(root, entries, journal, *, stop_after=None):
    """可独立演练的移动协议：两边都在或都不在即拒绝，绝不覆盖。"""
    journal.parent.mkdir(parents=True, exist_ok=True)
    moved = 0
    with journal.open("a", encoding="utf-8") as sink:
        for entry in entries:
            source = _checked_path(root, entry["source"])
            target = _checked_path(root, entry["target"])
            source_exists, target_exists = source.exists(), target.exists()
            if source_exists == target_exists:
                raise StateError(f"迁移状态冲突：source={source_exists} target={target_exists} {entry['source']}")
            if source_exists:
                if not source.is_file() or source.stat().st_size != entry["bytes"]:
                    raise StateError("源文件类型或大小改变")
                signature = entry.get("signature")
                if signature is not None:
                    if _signature(source) != signature:
                        raise StateError("源文件指纹改变，拒绝移动")
                elif file_sha(source) != entry["sha256"]:
                    raise StateError("源文件散列不一致")
                target.parent.mkdir(parents=True, exist_ok=True)
                # 同一文件系统内 rename，目标存在已在上面拒绝；运行级锁防本工具并发写者。
                os.rename(source, target)
                action = "moved"
                moved += 1
            else:
                if not target.is_file() or target.stat().st_size != entry["bytes"] or file_sha(target) != entry["sha256"]:
                    raise StateError("恢复目标与冻结散列不符")
                action = "already_moved"
            sink.write(json.dumps({"source": entry["source"], "target": entry["target"], "action": action}, ensure_ascii=False) + "\n")
            sink.flush()
            os.fsync(sink.fileno())
            if stop_after is not None and moved >= stop_after:
                raise InterruptedError("测试中断：部分文件已移动")
    return moved


def _activity(root, logs, mapping):
    paths = {str(root / e["source"]): str(root / e["target"]) for e in mapping["entries"]}
    sources = mapping.get("comparison_source", {})
    files = [root / "rollout/results.jsonl", root / "rollout/logs/windows_timeline.json",
             root / "rollout/logs/window_tables.md", root / "rollout/WINDOWS.md", root / "rollout/ROLLOUT.md"]
    files += list((root / "rollout/logs/attempts").glob("*/scope.json"))
    records = []
    for path in files:
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        original = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            changed = "".join(json.dumps(translate(json.loads(line), paths, sources), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n" for line in original.splitlines())
        elif path.suffix == ".json":
            changed = json.dumps(translate(json.loads(original), paths, sources), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        else:
            changed = re.sub(r"/[^\s|)<>]+\.(?:h5|mp4)", lambda m: paths.get(m.group(), m.group()), original)
        backup, version = logs / "backups" / relative, logs / "versions" / relative
        atomic_text(backup, original)
        atomic_text(version, changed)
        records.append({"path": str(relative), "before": file_sha(backup), "after": file_sha(version)})
    write_json(logs / "active_files.json", records)


def verify(root, *, complete=False):
    logs = root / "rollout/logs/migration"
    entries = json.loads((logs / "inventory.json").read_text())
    actual = hash_entries(root, entries, "target")
    mismatches = [e["target"] for e in entries if actual[e["target"]]["sha256"] != e["sha256"] or actual[e["target"]]["bytes"] != e["bytes"]]
    if mismatches:
        raise StateError(f"迁移后字节差异：{mismatches[:5]}")
    allowed = set(json.loads((logs / "allowed_new.json").read_text()))
    targets = {e["target"] for e in entries}
    current = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()
               and not str(p.relative_to(root)).startswith(("hf_release/", "rollout/logs/migration/")) and not p.name.endswith(".lock")}
    if current != allowed | targets:
        raise StateError(f"产物集合不守恒：missing={sorted((allowed|targets)-current)[:5]} extra={sorted(current-(allowed|targets))[:5]}")
    rows = read_rows(root / "rollout/results.jsonl")
    successes = [r for r in rows if r["kind"] == "h5" and r["ok"]]
    if len(successes) != 1796:
        raise StateError("成功 HDF5 数不是 1796")
    for row in successes:
        relative = str(Path(row["h5_path"]).relative_to(root))
        if actual[relative]["sha256"] != row["h5_sha256"] or actual[relative]["bytes"] != row["h5_bytes"]:
            raise StateError("成品与结果散列不符")
    active = json.loads((logs / "active_files.json").read_text())
    for item in active:
        if file_sha(root / item["path"]) != item["after"]:
            raise StateError(f"活动元数据不是预生成版本：{item['path']}")
    stale = []
    def paths(value, key=None):
        if key in {"discarded", "error", "traceback"}:
            return
        if isinstance(value, dict):
            for k, v in value.items():
                paths(v, k)
        elif isinstance(value, list):
            for v in value:
                paths(v, "path" if key == "no_object_paths" else key)
        elif isinstance(value, str) and key in {"h5_path", "path", "video_path", "output_root", "output_dir", "spec_path", "candidates", "source"}:
            if value.startswith(str(root)) or value.startswith(str(root.relative_to(ROOT))):
                path = Path(value) if Path(value).is_absolute() else ROOT / value
                if not path.exists() or str(path).startswith(str(root / "feasibility")):
                    stale.append(value)
    paths(rows)
    paths(json.loads((root / "rollout/logs/windows_timeline.json").read_text()))
    for item in active:
        path = root / item["path"]
        if path.suffix == ".json":
            paths(json.loads(path.read_text()))
    if stale:
        raise StateError(f"活动路径失效或残留旧前缀：{stale[:5]}")
    result = {"passed": True, "h5": 1796, "artifacts": len(entries), "sha_mismatch": 0,
              "missing": 0, "extra": 0, "active_missing": 0, "old_prefix": 0, "unexpected_field_changes": 0}
    write_json(logs / "verification.json", result)
    print(f"H5_INTACT=PASS count=1796 sha_mismatch=0 missing=0\nARTIFACTS_INTACT=PASS count={len(entries)} missing=0 extra=0 sha_mismatch=0\nACTIVE_PATHS=PASS missing=0 old_prefix=0\nMIGRATION_METADATA=PASS unexpected_field_changes=0", flush=True)
    if complete:
        write_json(logs / "state.json", {"state": "complete", "verified": result})
    return result


def move(root):
    logs = root / "rollout/logs/migration"
    with (root / "rollout/logs/writer.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status_path = logs / "state.json"
        if status_path.exists() and json.loads(status_path.read_text())["state"] == "complete":
            return json.loads((logs / "verification.json").read_text())
        mapping = json.loads((logs / "path_map.json").read_text())
        if not status_path.exists():
            audit = RunStore(root).audit()
            if audit["results"] != 3400 or audit["pending"] or audit["unused"]:
                raise StateError("正式候选与结果尚未完整归并")
            for gate in (root / "rollout/logs/figure_parity.json", root / "rollout/logs/unused_result.json",
                         root / "rollout/logs/parity/20260912-contract-v3-10-parity/logs/parity/result.json"):
                if not gate.exists() or not json.loads(gate.read_text())["passed"]:
                    raise StateError(f"迁移前置硬闸未通过：{gate}")
            expected_sources = {e["source"] for e in mapping["entries"]}
            actual_sources = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()
                              and p.relative_to(root).parts[0] not in {"candidates", "rollout", "hf_release"}}
            if actual_sources != expected_sources:
                raise StateError("旧产物集合自映射冻结后改变")
            if len({e["target"] for e in mapping["entries"]}) != len(mapping["entries"]):
                raise StateError("迁移目标重复")
            for entry in mapping["entries"]:
                target = _checked_path(root, entry["target"])
                if Path(entry["target"]).parts[0] not in {"candidates", "rollout"} or target.exists():
                    raise StateError(f"迁移目标已存在或越界：{target}")
            _activity(root, logs, mapping)
            allowed = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()
                       and p.relative_to(root).parts[0] in {"candidates", "rollout"}
                       and not str(p.relative_to(root)).startswith("rollout/logs/migration/") and not p.name.endswith(".lock")]
            write_json(logs / "allowed_new.json", allowed)
            write_json(status_path, {"state": "in_progress", "started_at": time.time()})
        inventory_path = logs / "inventory.json"
        if not inventory_path.exists():
            hashes = hash_entries(root, mapping["entries"], "source")
            results = read_rows(root / "rollout/results.jsonl")
            reference = {r["h5_path"]: r["h5_sha256"] for r in results if r["kind"] == "h5" and r["ok"]}
            aliases = mapping.get("comparison_aliases", {})
            inventory = []
            for entry in mapping["entries"]:
                item = {**entry, **hashes[entry["source"]]}
                if Path(entry["source"]).suffix == ".h5":
                    name = str(root / entry["source"])
                    if item["sha256"] != reference.get(aliases.get(name, name)):
                        raise StateError(f"旧 HDF5 与原交付散列不符：{name}")
                inventory.append(item)
            write_json(inventory_path, inventory)
        inventory = json.loads(inventory_path.read_text())
        move_entries(root, inventory, logs / "journal.jsonl")
        # 所有小文件的新版本已在移动前生成；中断后只接受旧版或新版，拒绝覆盖第三方变化。
        for item in json.loads((logs / "active_files.json").read_text()):
            target = root / item["path"]
            current = file_sha(target)
            if current not in {item["before"], item["after"]}:
                raise StateError(f"活动元数据出现范围外修改：{target}")
            if current != item["after"]:
                atomic_text(target, (logs / "versions" / item["path"]).read_text(encoding="utf-8"))
        # 仅移除已经搬空的旧目录；有任何额外内容时保留并由集合核验报错。
        parents = {parent for e in inventory for parent in (root / e["source"]).parents if parent != root and parent.is_relative_to(root)}
        for directory in sorted(parents, key=lambda p: len(p.parts), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        return verify(root, complete=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "move", "resume", "verify"))
    parser.add_argument("--run-id", default="20260912-contract-v3-10")
    args = parser.parse_args()
    root = run_root(args.run_id)
    if args.command == "prepare":
        prepare(root)
    elif args.command == "verify":
        verify(root)
    else:
        move(root)


if __name__ == "__main__":
    main()
