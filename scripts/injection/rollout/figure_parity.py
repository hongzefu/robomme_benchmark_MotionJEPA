"""同一运行的旧、新图表完整对拍；只对冻结的路径字段做归一化。"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from ..candidates.io import canonical_json
from .parity import check_keys
from .state import ROOT, RunStore, file_sha, run_root, write_json


def path_normalizer(root, mapping):
    paths = {str(root / entry["source"]): str(root / entry["target"]) for entry in mapping["entries"]}
    aliases = mapping.get("comparison_aliases", {})
    sources = mapping.get("comparison_source", {})
    def normalize(value, kind="h5_path"):
        if kind == "source":
            return sources.get(value, value)
        value = aliases.get(value, value)
        return paths.get(value, value)
    return normalize


def normalize_data(value, normalize):
    if isinstance(value, dict):
        return {key: normalize(item, key) if key in {"source", "h5_path"} and isinstance(item, str)
                else normalize_data(item, normalize) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_data(item, normalize) for item in value]
    return value


def timeline_keys(data):
    rows = []
    for name, records in data["groups"].items():
        task, difficulty = name.split("/")
        rows.extend({"task": task, "difficulty": difficulty, "episode": r["episode"]} for r in records)
    rows.extend({"task": r["task"], "difficulty": r["difficulty"], "episode": r["episode"]} for r in data["excluded_slow"])
    return rows


def compare(root):
    store = RunStore(root)
    baseline = store.logs / "baseline"
    manifest = json.loads((baseline / "manifest.json").read_text())
    expected = {key: value for key, value in manifest["outputs"].items() if key.endswith(".png")}
    actual = {}
    for prefix, directory in (("before", root / "candidates/figures"), ("windows", store.state / "figures")):
        for path in directory.rglob("*.png"):
            actual[f"{prefix}/{path.relative_to(directory)}"] = path
    png_diffs = []
    for key in sorted(set(expected) | set(actual)):
        if key not in expected or key not in actual or not (baseline / key).is_file():
            png_diffs.append({"path": key, "reason": "缺失或额外图"})
        elif file_sha(baseline / key) != expected[key] or file_sha(actual[key]) != expected[key]:
            png_diffs.append({"path": key, "reason": "PNG 字节不同"})
    old = json.loads((baseline / "windows_timeline.json").read_text())
    new = json.loads((store.logs / "windows_timeline.json").read_text())
    mapping = json.loads((store.logs / "migration/path_map.json").read_text())
    normalize = path_normalizer(root, mapping)
    timeline_equal = canonical_json(normalize_data(old, normalize)) == canonical_json(normalize_data(new, normalize))
    expected_keys = {(r["task"], r["difficulty"], r["episode"]) for r in store.load()[2] if r["kind"] == "h5" and r["ok"]}
    keys = [check_keys(expected_keys, timeline_keys(data), f"L2-{name}") for name, data in (("old", old), ("new", new))]
    def table_text(path):
        return re.sub(r"/[^\s|]+\.h5", lambda match: normalize(match.group()), path.read_text(encoding="utf-8"))
    tables = {
        "events": table_text(baseline / "event_tables.md") == table_text(root / "candidates/logs/event_tables.md"),
        "windows": table_text(baseline / "window_tables.md") == table_text(store.logs / "window_tables.md"),
    }
    conserved = new["episodes_before_exclusion"] == 1796 and new["episodes"] + len(new["excluded_slow"]) == 1796 and not new["skipped"]
    passed = len(expected) == len(actual) == 113 and not png_diffs and all(tables.values()) and timeline_equal and conserved and all(k["passed"] for k in keys)
    result = {"passed": passed, "png": len(actual), "png_differences": png_diffs, "tables": tables,
              "timeline_equal": timeline_equal, "before": new["episodes_before_exclusion"], "kept": new["episodes"],
              "excluded": len(new["excluded_slow"]), "skipped": len(new["skipped"]), "keys": keys}
    write_json(store.logs / "figure_parity.json", result)
    for key in keys:
        print(f"PARITY_KEYS={'PASS' if key['passed'] else 'FAIL'} layer={key['layer']} missing={key['missing']} extra={key['extra']} duplicates={key['duplicates']}")
    print(f"FIGURES_EQUIVALENCE={'PASS' if len(actual)==113 and not png_diffs else 'FAIL'} png={len(actual)} differences={len(png_diffs)}")
    print(f"TABLES_EQUIVALENCE={'PASS' if all(tables.values()) else 'FAIL'} drift={sum(not x for x in tables.values())}")
    print(f"TIMELINE_EQUIVALENCE={'PASS' if timeline_equal and conserved else 'FAIL'} before={new['episodes_before_exclusion']} kept={new['episodes']} excluded={len(new['excluded_slow'])} skipped={len(new['skipped'])} differences={int(not timeline_equal)}")
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="20260912-contract-v3-10")
    args = parser.parse_args()
    if not compare(run_root(args.run_id)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
