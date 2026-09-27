"""S2 结束后的纯离线汇总；不导入环境、不生成、不修改已有产物。"""
import collections
import json
from pathlib import Path
import subprocess

import h5py

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]


def read(path):
    return json.loads(path.read_text())


def inspect_h5(path, identity):
    result = {"path": str(path.relative_to(REPO)), "bytes": path.stat().st_size, "ok": False}
    try:
        with h5py.File(path, "r") as handle:
            group = handle[f"episode_{identity['episode']}"]
            steps = sorted(int(key.split("_")[-1]) for key in group if key.startswith("timestep_"))
            seed = int(group["setup/seed"][()])
            difficulty = group["setup/difficulty"][()]
            if isinstance(difficulty, bytes):
                difficulty = difficulty.decode()
            completed = bool(group[f"timestep_{steps[-1]}/info/is_completed"][()]) if steps else False
            result.update(timesteps=len(steps), seed=seed, difficulty=difficulty, terminal_completed=completed,
                          ok=bool(steps and steps == list(range(steps[0], steps[-1] + 1)) and
                                  seed == identity["seed"] and difficulty == identity["difficulty"] and completed))
            # 只接受本轮 HDF5 中显式方法字段，绝不由历史 seed 或任务文字推断。
            fields = {}
            def visit(name, obj):
                if isinstance(obj, h5py.Dataset) and name.rsplit("/", 1)[-1] in {"way", "way_idx", "method"}:
                    value = obj[()]
                    fields[name] = value.decode() if isinstance(value, bytes) else str(value)
            if identity["task"] == "MoveCube":
                group.visititems(visit)
                result["explicit_method_fields"] = fields
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def inspect_video(path):
    result = {"path": str(path.relative_to(REPO)), "bytes": path.stat().st_size, "first_frame_decodable": False}
    try:
        process = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path),
                                  "-map", "0:v:0", "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                                 capture_output=True, timeout=30)
        result.update(exit_code=process.returncode, first_frame_decodable=process.returncode == 0 and bool(process.stdout),
                      error=process.stderr.decode(errors="replace")[-1000:])
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def main():
    # 防止重复调用覆盖已审查的报告；需重做时由主代理决定新的报告位置。
    assert not (ROOT / "report.json").exists() and not (ROOT / "report.md").exists(), "报告已存在，拒绝覆盖"
    manifest = read(ROOT / "manifest.json")
    identities = manifest["identities"]
    assert len(identities) == len({row["id"] for row in identities}) == 144
    actual_dirs = {p.name for p in (ROOT / "episodes").iterdir() if p.is_dir()}
    unexpected = sorted(actual_dirs - {row["id"] for row in identities})
    rows, counts = [], collections.defaultdict(collections.Counter)
    for identity in identities:
        out = ROOT / "episodes" / identity["id"]
        result_file, summary_file = out / "result.json", out / "summary.jsonl"
        result = read(result_file) if result_file.exists() else None
        summaries = []
        summary_error = None
        if summary_file.exists():
            try:
                summaries = [json.loads(line) for line in summary_file.read_text().splitlines() if line]
            except Exception as exc:
                summary_error = str(exc)
        match = lambda item: all(item.get(key) == identity[key] for key in ("task", "difficulty", "seed"))
        valid = result is not None and match(result) and len(summaries) == 1 and match(summaries[0])
        started = (out / "started.json").exists()
        success = bool(valid and result.get("ok") and summaries[0].get("ok"))
        h5s = [inspect_h5(p, identity) for p in sorted(out.rglob("*.h5"))] if out.exists() else []
        videos = [inspect_video(p) for p in sorted(out.rglob("*.mp4"))] if out.exists() else []
        media_ok = len(h5s) == 1 and all(p["ok"] for p in h5s) and bool(videos) and all(p["first_frame_decodable"] for p in videos)
        row = {**identity, "started": started, "result_present": result is not None, "identity_summary_valid": valid,
               "success": success, "timeout": bool(result and result.get("timeout")), "result": result,
               "summary_error": summary_error, "hdf5": h5s, "videos": videos, "success_media_ok": bool(media_ok),
               "reset_calls": "未观测：运行器未记录底层初始化与reset调用计数"}
        if identity["task"] == "MoveCube":
            fields = {p["path"]: p.get("explicit_method_fields", {}) for p in h5s if p.get("explicit_method_fields")}
            row["actual_method"] = fields if fields else "不可核验：本轮HDF5无显式方法字段；历史映射不作实际覆盖证据"
        rows.append(row)
        count = counts[(identity["task"], identity["difficulty"])]
        count.update(expected=1, attempted=int(started), success=int(success),
                     failed=int(started and result is not None and not success), timeout=int(row["timeout"]),
                     missing=int(result is None), invalid_summary=int(result is not None and not valid),
                     successful_media_fail=int(success and not media_ok))
    totals = sum(counts.values(), collections.Counter())
    complete = totals["attempted"] == 144 and totals["missing"] == 0 and not unexpected
    report = {"run_name": manifest["run_name"], "totals": dict(totals), "attempt_coverage_complete": complete,
              "unexpected_episode_dirs": unexpected,
              "video_check_scope": "仅实际首帧解码；不证明全视频可解码、完整帧数或内容正确",
              "reset_calls": "未观测，未将逻辑尝试数换算为实际reset调用数",
              "cells": [{"task": key[0], "difficulty": key[1], **dict(value)} for key, value in sorted(counts.items())],
              "identities": rows}
    with (ROOT / "report.json").open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    lines = ["# S2 固定144次演示汇总", "", f"S2_ATTEMPT_COVERAGE={'PASS' if complete else 'FAIL'} expected=144 attempted={totals['attempted']} missing={totals['missing']}",
             f"S2_TASK_SUCCESS={totals['success']}/144 failed={totals['failed']} timeout={totals['timeout']}",
             f"S2_SUCCESS_MEDIA={'PASS' if totals['successful_media_fail'] == 0 and totals['success'] else 'FAIL'} successful={totals['success']} failed_checks={totals['successful_media_fail']}",
             "", "失败保留在固定144分母；成功率与尝试完成、媒体核验分别报告。视频只核验首帧真实解码，不证明全帧完整。",
             "实际初始化／reset调用数未观测；不由逻辑尝试数推算。MoveCube只认本轮HDF5显式方法字段；缺失时不可核验，历史seed映射不代替实际覆盖。", "",
             "|任务|档位|计划|已尝试|成功|失败|超时|缺失结果|成功媒体异常|", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for (task, tier), c in sorted(counts.items()):
        lines.append(f"|{task}|{tier}|{c['expected']}|{c['attempted']}|{c['success']}|{c['failed']}|{c['timeout']}|{c['missing']}|{c['successful_media_fail']}|")
    lines += ["", "每个身份的错误、退出码、HDF5结构／终态核验及视频首帧结果见同目录 report.json。"]
    with (ROOT / "report.md").open("x") as stream:
        stream.write("\n".join(lines) + "\n")
    print("\n".join(lines[:7]))


if __name__ == "__main__":
    main()
