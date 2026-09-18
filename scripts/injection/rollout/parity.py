"""方案 B 的固定键 HDF5/reset 对拍；视频诊断独立于硬闸。"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .state import ROOT, RunStore, StateError, candidate_key, file_sha, read_rows, run_root, write_json


def check_keys(expected, rows, layer):
    counts = Counter(candidate_key(r) for r in rows)
    expected = set(expected)
    actual = set(counts)
    result = {"layer": layer, "expected": len(expected), "actual": len(rows), "missing": len(expected - actual),
              "extra": len(actual - expected), "duplicates": sum(n - 1 for n in counts.values())}
    result["passed"] = not (result["missing"] or result["extra"] or result["duplicates"])
    return result


def compare_video(left, right, output, deadline, decoded_sha=None):
    """先比实际文件散列；不同则完整顺序解码，预算不足如实记录。"""
    left, right, output = Path(left), Path(right), Path(output)
    if not left.is_file() or not right.is_file():
        return {"status": "NOT_RUN", "reason": "视频文件缺失", "left": str(left), "right": str(right)}
    a, b = file_sha(left), file_sha(right)
    result = {"left": str(left), "right": str(right), "left_sha256": a, "right_sha256": b}
    result["bytes_equal"] = a == b
    if a == b and decoded_sha == (a, b):
        return {**result, "status": "PASS", "method": "文件逐字节一致，已与生成器完整解码记录核验"}
    if time.monotonic() >= deadline:
        return {**result, "status": "NOT_RUN", "reason": "解码预算已用完；文件散列已实际核对"}
    import cv2
    import numpy as np
    captures = [cv2.VideoCapture(str(path)) for path in (left, right)]
    first = None
    counts = [0, 0]
    differing = 0
    fps = [capture.get(cv2.CAP_PROP_FPS) for capture in captures]
    expected_frames = [int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) for capture in captures]
    complete = True
    try:
        if not all(cap.isOpened() for cap in captures):
            return {**result, "status": "NOT_RUN", "reason": "无法打开视频解码器"}
        while True:
            if time.monotonic() >= deadline:
                complete = False
                break
            read = [capture.read() for capture in captures]
            for i, (ok, _) in enumerate(read):
                counts[i] += int(ok)
            if not read[0][0] and not read[1][0]:
                break
            unequal = read[0][0] != read[1][0] or (read[0][0] and read[1][0] and not np.array_equal(read[0][1], read[1][1]))
            if unequal:
                differing += 1
                if first is None:
                    first = max(counts) - 1
                    output.mkdir(parents=True, exist_ok=True)
                    for name, (ok, frame) in zip(("left", "right"), read):
                        if ok:
                            cv2.imwrite(str(output / f"{name}_first_difference.png"), frame)
    finally:
        for capture in captures:
            capture.release()
    decode_ok = complete and all(expected <= 0 or got == expected for got, expected in zip(counts, expected_frames))
    different = differing > 0 or fps[0] != fps[1] or (complete and counts[0] != counts[1])
    status = "DIFFERENT" if different else ("PASS" if decode_ok else "NOT_RUN")
    result.update(status=status, frames=counts, fps=fps, different_frames=differing,
                  first_difference=first, complete_decode=complete, decode_ok=decode_ok,
                  method="完整解码逐帧像素" if complete else "预算内部分解码")
    if different:
        output.mkdir(parents=True, exist_ok=True)
        for name, path in (("left", left), ("right", right)):
            target = output / f"{name}.mp4"
            if not target.exists():
                shutil.copy2(path, target)
            result[f"{name}_copy"] = str(target)
    return result


def video_diagnostics(left, right, output, budget=120):
    deadline = time.monotonic() + budget
    details = []
    for key in sorted(left):
        a = left[key].get("video") or {}
        b = right[key].get("video") or {}
        pairs = [("main", a.get("path"), b.get("path"))]
        aa, bb = sorted(a.get("no_object_paths") or []), sorted(b.get("no_object_paths") or [])
        for index in range(max(len(aa), len(bb))):
            pairs.append((f"no_object_{index}", aa[index] if index < len(aa) else None, bb[index] if index < len(bb) else None))
        for kind, first, second in pairs:
            if not first or not second:
                result = {"status": "NOT_RUN", "reason": "一侧或两侧未产生对应视频", "left": first, "right": second}
            else:
                verified = (a.get("sha256"), b.get("sha256")) if kind == "main" and a.get("status") == b.get("status") == "complete" else None
                result = compare_video(first, second, output / f"{key[0]}-{key[1]}-{key[2]}-{kind}", deadline, verified)
            details.append({"key": list(key), "kind": kind, **result})
    counts = Counter(r["status"] for r in details)
    status = "DIFFERENT" if counts["DIFFERENT"] else ("NOT_RUN" if counts["NOT_RUN"] else "PASS")
    return {"status": status, "counts": dict(counts), "details": details, "budget_s": budget}


def compare(left_root, right_root, *, video_budget=120):
    left_store, right_store = RunStore(left_root), RunStore(right_root)
    if (right_store.logs / "archive.json").exists():
        raise StateError("对拍运行已归档，请读取已冻结的比较结果或用新编号复验")
    out = right_store.logs / "parity"
    out.mkdir(parents=True, exist_ok=True)
    left_header, _, left_rows = left_store.load()
    right_header, _, right_rows = right_store.load()
    groups = [(g["task"], g["difficulty"]) for g in left_header["delivery_config_snapshot"]["groups"]]
    expected_h5 = {(t, d, ep) for t, d in groups for ep in range(15)}
    if len(groups) != 14 or len(expected_h5) != 210:
        raise StateError("方案 B 固定为 14 组各前 15 条")
    a_h5 = [r for r in left_rows if r["kind"] == "h5" and candidate_key(r) in expected_h5]
    b_h5 = [r for r in right_rows if r["kind"] == "h5"]
    frozen = json.loads((left_store.logs / "migration/l4_scope.json").read_text())
    expected_reset = {tuple(k) for k in frozen["keys"]}
    a_reset = read_rows(left_store.logs / "migration/reference_reset.jsonl")
    b_reset = [r for r in right_rows if r["kind"] == "reset"]
    checks = [check_keys(expected_h5, a_h5, "L3-left"), check_keys(expected_h5, b_h5, "L3"),
              check_keys(expected_reset, a_reset, "L4-left"), check_keys(expected_reset, b_reset, "L4")]
    for check in checks:
        print(f"PARITY_KEYS={'PASS' if check['passed'] else 'FAIL'} " + " ".join(f"{k}={v}" for k, v in check.items() if k != "passed"), flush=True)
    if not all(c["passed"] for c in checks):
        write_json(out / "result.json", {"passed": False, "keys": checks})
        return False
    left_store.audit()
    right_store.audit()
    if left_header["identity_sha256"] != right_header["identity_sha256"]:
        raise StateError("新旧候选身份不同")
    left = {candidate_key(r): r for r in a_h5}
    right = {candidate_key(r): r for r in b_h5}
    success, failures, sha_mismatch, failure_mismatch = 0, 0, [], []
    paths = set()
    for key in sorted(expected_h5):
        a, b = left[key], right[key]
        fields = ("ok", "failure_class", "error_type") if not a["ok"] else ("ok",)
        if any(a.get(k) != b.get(k) for k in fields) or a["seed"] != b["seed"] or a["spec_sha256"] != b["spec_sha256"]:
            failure_mismatch.append({"key": list(key), "left": {k: a.get(k) for k in fields}, "right": {k: b.get(k) for k in fields}})
        if a["ok"]:
            success += 1
            paths.add(a["h5_path"])
            if b["ok"]:
                paths.add(b["h5_path"])
        else:
            failures += 1
    def hash_one(path):
        file = Path(path)
        return path, {"sha256": file_sha(file), "bytes": file.stat().st_size} if file.is_file() else {"missing": True}
    with ThreadPoolExecutor(max_workers=8) as pool:
        hashes = dict(pool.map(hash_one, sorted(paths)))
    for key in sorted(expected_h5):
        a, b = left[key], right[key]
        if not a["ok"] or not b["ok"]:
            continue
        x, y = hashes[a["h5_path"]], hashes[b["h5_path"]]
        if x != y or x.get("sha256") != a["h5_sha256"] or y.get("sha256") != b["h5_sha256"] or y.get("bytes") != b["h5_bytes"]:
            detail = {"key": list(key), "left": x, "right": y}
            if len(sha_mismatch) < 3 and not x.get("missing") and not y.get("missing"):
                from .h5_compare import compare_h5
                detail["content_differences"] = compare_h5(a["h5_path"], b["h5_path"])[:100]
            sha_mismatch.append(detail)
    reset_left = {candidate_key(r): r for r in a_reset}
    reset_right = {candidate_key(r): r for r in b_reset}
    fields = ("ok", "outcome", "error_type", "injection_bound", "counted", "role", "seed", "spec_sha256")
    reset_diffs = [{"key": list(key), "fields": [f for f in fields if reset_left[key].get(f) != reset_right[key].get(f)]}
                   for key in sorted(expected_reset) if any(reset_left[key].get(f) != reset_right[key].get(f) for f in fields)]
    stop = {f"{t}/{d}": max(r["episode"] for r in b_reset if (r["task"], r["difficulty"]) == (t, d)) for t, d in groups}
    stop_diffs = sum(stop[k] != v for k, v in frozen["stop_episodes"].items())
    integrity = json.loads((right_store.logs / "source_integrity.json").read_text())
    intact = integrity["passed"] and integrity["before"] == integrity["after"] == file_sha(left_store.candidates)
    h5_ok = not sha_mismatch and not failure_mismatch and (success, failures) == (205, 5)
    reset_ok = not reset_diffs and stop_diffs == 0
    print(f"H5_PARITY={'PASS' if h5_ok else 'FAIL'} compared=210 success={success} failures={failures} sha_mismatch={len(sha_mismatch)} failure_mismatch={len(failure_mismatch)}", flush=True)
    print(f"RESET_PARITY={'PASS' if reset_ok else 'FAIL'} compared=720 outcome_mismatch={len(reset_diffs)} stop_episode_mismatch={stop_diffs} role_mismatch={sum('role' in d['fields'] for d in reset_diffs)}", flush=True)
    print(f"PARITY_SOURCE_INTACT={'PASS' if intact else 'FAIL'}", flush=True)
    videos = video_diagnostics(left, right, out / "video_pairs", video_budget)
    print(f"VIDEO_DIAGNOSTIC={videos['status']} counts={videos['counts']}", flush=True)
    payload = {"passed": h5_ok and reset_ok and intact, "keys": checks, "h5": {"passed": h5_ok,
                "compared": 210, "success": success, "failures": failures, "sha_mismatches": sha_mismatch,
                "failure_mismatches": failure_mismatch, "actual_files": hashes},
               "reset": {"passed": reset_ok, "compared": 720, "differences": reset_diffs, "stop_episode_mismatch": stop_diffs},
               "source_intact": intact, "video": videos}
    write_json(out / "result.json", payload)
    return payload["passed"]


def archive(left_root, right_root):
    """先逐文件留档证据，再按经核验的清单清理临时媒体；原运行大文件不动。"""
    import fcntl
    left, right = RunStore(left_root), RunStore(right_root)
    result = json.loads((right.logs / "parity/result.json").read_text())
    if not result["passed"]:
        raise StateError("对拍硬闸未通过，禁止清理")
    target = left.logs / "parity" / right_root.name
    target.mkdir(parents=True, exist_ok=True)
    marker = right.logs / "archive.json"
    with (right.logs / "writer.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # 原始范围、尝试、结果、诊断及反例视频对完整保留；不复制进程锁和自引用归档标志。
        originals = [(right.candidates, target / "candidates.jsonl"), (right.results_path, target / "results.jsonl")]
        originals += [(p, target / "logs" / p.relative_to(right.logs)) for p in right.logs.rglob("*")
                      if p.is_file() and p.name not in {"writer.lock", "archive.json"}]
        archived = []
        for source, destination in originals:
            if source.is_symlink():
                raise StateError("归档输入含符号链接")
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = file_sha(source)
            if destination.exists():
                if file_sha(destination) != digest:
                    raise StateError(f"归档目标与源不一致：{destination}")
            else:
                shutil.copy2(source, destination)
            if file_sha(destination) != digest:
                raise StateError("归档副本散列不符")
            archived.append({"source": str(source), "archive": str(destination), "sha256": digest})
        # 预算不足或差异的视频另留两侧原件，不能因 HDF5 通过而销毁定位材料。
        for item in result["video"]["details"]:
            if item["status"] == "PASS":
                continue
            folder = target / "video_evidence" / ("-".join(map(str, item["key"])) + "-" + item["kind"])
            for side in ("left", "right"):
                value = item.get(side)
                if value and Path(value).is_file():
                    folder.mkdir(parents=True, exist_ok=True)
                    destination = folder / f"{side}.mp4"
                    if not destination.exists():
                        shutil.copy2(value, destination)
                    if file_sha(value) != file_sha(destination):
                        raise StateError("视频诊断留档散列不符")
        cleanup_path = target / "cleanup_manifest.json"
        if cleanup_path.exists():
            cleanup = json.loads(cleanup_path.read_text())
        else:
            rows = read_rows(right.results_path)
            expected = set()
            for row in rows:
                if row["kind"] != "h5":
                    continue
                if row["ok"]:
                    expected.add(Path(row["h5_path"]))
                video = row.get("video") or {}
                if video.get("path"):
                    expected.add(Path(video["path"]))
                expected.update(Path(p) for p in video.get("no_object_paths", []))
            media = {p for p in right.state.rglob("*") if p.suffix in {".h5", ".mp4"} and "logs" not in p.relative_to(right.state).parts}
            if expected != media:
                raise StateError("临时媒体与结果清单不完全一致，拒绝宽泛删除")
            cleanup = []
            hashes = result["h5"]["actual_files"]
            for path in sorted(media):
                if path.is_symlink() or not path.resolve().is_relative_to(right.state.resolve()):
                    raise StateError("清理目标越界或含符号链接")
                digest = file_sha(path)
                if path.suffix == ".h5" and digest != hashes[str(path)]["sha256"]:
                    raise StateError("对拍后 HDF5 发生改变，拒绝清理")
                cleanup.append({"path": str(path), "sha256": digest, "bytes": path.stat().st_size})
            write_json(cleanup_path, cleanup)
        write_json(target / "archive_index.json", archived)
        write_json(marker, {"state": "in_progress", "archive": str(target), "files": len(cleanup)})
        for item in cleanup:
            path = Path(item["path"])
            if path.exists():
                if path.is_symlink() or path.stat().st_size != item["bytes"] or file_sha(path) != item["sha256"]:
                    raise StateError("临时媒体在清理时改变，保留剩余文件")
                path.unlink()
        write_json(marker, {"state": "complete", "archive": str(target), "removed_files": len(cleanup),
                            "removed_bytes": sum(item["bytes"] for item in cleanup), "evidence_files": len(archived)})
        write_json(target / "archive_result.json", json.loads(marker.read_text()))
        print(f"PARITY_ARCHIVE=PASS evidence_files={len(archived)} removed_media={len(cleanup)} source_media_removed=0")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--scheme", choices=("B",), default="B")
    parser.add_argument("--video-budget-s", type=float, default=120)
    parser.add_argument("--archive", action="store_true")
    args = parser.parse_args()
    if args.archive:
        archive(run_root(args.left), run_root(args.right))
        return
    if not compare(run_root(args.left), run_root(args.right), video_budget=args.video_budget_s):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
