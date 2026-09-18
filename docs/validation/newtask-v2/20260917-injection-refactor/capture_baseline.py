"""阶段三旧算法基线采集；在旧入口仍存在的固定提交上执行，产物只进运行日志目录。"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OLD = ROOT / "scripts/injection-before-2d"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(module, arguments):
    previous = sys.argv
    try:
        sys.argv = [str(module.__file__), *arguments]
        if module.main() != 0:
            raise RuntimeError(f"旧工具检查失败：{module.__name__}")
    finally:
        sys.argv = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="20260912-contract-v3-10")
    args = parser.parse_args()
    run = ROOT / "artifacts/injection" / args.run_id
    out = run / "rollout/logs/baseline"
    out.mkdir(parents=True, exist_ok=True)
    if (out / "manifest.json").exists():
        raise RuntimeError("基线已冻结，禁止覆盖")
    for path in (ROOT, ROOT / "src", OLD):
        sys.path.insert(0, str(path))
    timeline = importlib.import_module("window_timeline")
    before = importlib.import_module("plot_injection_before_2d")
    tables = importlib.import_module("event_tables")
    windows = importlib.import_module("plot_sampling_windows")
    started = time.monotonic()
    input_paths = [Path(module.__file__) for module in (timeline, before, tables, windows)]
    input_paths += [run / "manifest.json", run / "feasibility/P01x20/episode_results.jsonl"]
    input_paths += sorted((run / "specs").glob("*/*.json"))
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in input_paths}
    print("开始冻结旧跑前图", flush=True)
    invoke(before, ["--run-id", args.run_id, "--out-dir", str(out / "before")])
    text, table_rows = tables.render_all(run, tables.load_sampling(run), tables.load_contract_for(run))
    (out / "event_tables.md").write_text(text, encoding="utf-8")
    print(f"旧事件表已冻结 groups=14 rows={table_rows}，开始读取全部 HDF5", flush=True)
    data = timeline.extract(args.run_id, run / "feasibility/P01x20")
    (out / "windows_timeline.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    table_text, _ = timeline.render_tables(data)
    (out / "window_tables.md").write_text(table_text, encoding="utf-8")
    if data["episodes_before_exclusion"] != 1796 or data["skipped"] or data["episodes"] + len(data["excluded_slow"]) != 1796:
        raise RuntimeError("旧数轴范围、读取或剔除守恒失败")
    print(f"旧数轴读取完成 kept={data['episodes']} excluded={len(data['excluded_slow'])}，开始出图", flush=True)
    invoke(windows, ["--json", str(out / "windows_timeline.json"), "--out-dir", str(out / "windows")])
    pictures = sorted(out.rglob("*.png"))
    if len(pictures) != 113:
        raise RuntimeError(f"基线图片数错误：{len(pictures)}")
    if inputs != {str(p.relative_to(ROOT)): sha(p) for p in input_paths}:
        raise RuntimeError("采集期间旧输入或旧代码改变")
    manifest = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "inputs": inputs, "outputs": {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()},
                "png": len(pictures), "tables": 14, "event_rows": table_rows, "before": 1796,
                "kept": data["episodes"], "excluded": len(data["excluded_slow"]), "skipped": len(data["skipped"]),
                "elapsed_s": round(time.monotonic() - started, 2)}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BASELINE_CAPTURED=PASS png=113 tables=14 before=1796 kept={data['episodes']} excluded={len(data['excluded_slow'])} skipped=0 elapsed_s={manifest['elapsed_s']}")


if __name__ == "__main__":
    main()
