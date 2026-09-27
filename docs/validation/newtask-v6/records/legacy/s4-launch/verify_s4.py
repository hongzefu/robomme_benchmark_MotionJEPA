"""S4 回传清单与离线完整性验收；不创建仿真环境。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.parity.v6_tier_monotone import GRADIENT_ENVS, NEWVALUE_TIERS, XHARD4_EXTRA_TASKS


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest(root):
    return {str(p.relative_to(root)): {"bytes": p.stat().st_size, "sha256": sha(p)}
            for p in sorted(root.rglob("*")) if p.is_file()}


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify_success(rollout, row):
    import h5py
    import numpy as np
    import cv2
    episode = rollout / "episodes" / f"{row['task']}_episode_{row['episode']}"
    paths = list((episode / "hdf5_files").glob("*.h5"))
    if len(paths) != 1:
        raise ValueError(f"成功局H5数量={len(paths)}")
    h5 = paths[0]
    if h5.name != f"{row['task']}_ep{row['episode']}_seed{row['seed']}.h5":
        raise ValueError("H5文件身份不符")
    with h5py.File(h5) as handle:
        if list(handle) != [f"episode_{row['episode']}"]:
            raise ValueError("H5 episode身份不符")
        group = handle[f"episode_{row['episode']}"]
        names = sorted((n for n in group if n.startswith("timestep_")), key=lambda n: int(n.split("_")[1]))
        if not names:
            raise ValueError("空H5")
        completed = group[names[-1]]["info/is_completed"][()]
        if not isinstance(completed, (bool, np.bool_)) or not bool(completed):
            raise ValueError("H5终端非严格布尔True")
        difficulty = group["setup/difficulty"][()]
        if isinstance(difficulty, bytes):
            difficulty = difficulty.decode()
        if int(group["setup/seed"][()]) != row["seed"] or difficulty != row["difficulty"]:
            raise ValueError("H5 setup身份不符")
    videos = list((episode / "videos").glob("*.mp4"))
    if not videos:
        raise ValueError("成功局没有视频")
    for video in videos:
        capture = cv2.VideoCapture(str(video))
        try:
            ok, frame = capture.read()
            if not ok or frame is None or not frame.size:
                raise ValueError(f"视频首帧不可解码 {video.name}")
        finally:
            capture.release()
    replay = json.loads((episode / "spec_replay.json").read_text())
    mismatch, unused = replay["mismatches"], replay["unused"]
    if not isinstance(mismatch, list) or not isinstance(unused, list):
        raise ValueError("spec_replay计数类型错误")
    binding = row["spec_binding"]
    if binding["mismatch"] != len(mismatch) or binding["unused"] != len(unused):
        raise ValueError("spec_replay与结果绑定计数不一致")
    if mismatch or unused:
        raise ValueError(f"spec_replay mismatch={len(mismatch)} unused={len(unused)}")
    return {"frames": len(names), "videos": len(videos)}


def verify(root):
    cells, errors, successes = {}, [], []
    for tier in NEWVALUE_TIERS:
        tasks = set(GRADIENT_ENVS) | (set(XHARD4_EXTRA_TASKS) if tier == "xhard4" else set())
        base = root / tier
        try:
            drafts = read_rows(base / "draft/drafts.jsonl")
            specs = read_rows(base / "specs.jsonl")
            results = read_rows(base / "rollout/run1/results.jsonl")
            if set(drafts[0]["tasks"]) != tasks or drafts[0]["difficulty"] != tier:
                raise ValueError("档位或任务集合不符")
            draft_rows = drafts[1:]
            if any(r["task"] not in tasks or r["difficulty"] != tier or type(r.get("reset_ok")) is not bool
                   for r in draft_rows):
                raise ValueError("抽签任务、档位或reset_ok非法")
            candidates = {(r["task"], r["episode"]): r for r in draft_rows if r.get("reset_ok") is True}
            frozen = {(r["task"], r["episode"]): r for r in specs[1:]}
            if len(frozen) != len(specs) - 1 or set(frozen) != set(candidates):
                raise ValueError("冻结候选重复或候选集合不符")
            if len(candidates) != sum(r.get("reset_ok") is True for r in draft_rows):
                raise ValueError("成功候选身份重复")
            for key, row in candidates.items():
                if any(row["spec"]["identity"].get(k) != row[k] for k in ("task", "episode", "seed", "difficulty")):
                    raise ValueError(f"候选规格身份不符 {key}")
                digest = hashlib.sha256(json.dumps(row["spec"], ensure_ascii=False, sort_keys=True,
                                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()
                if row["spec_sha256"] != digest or frozen[key]["spec_sha256"] != digest or frozen[key]["spec"] != row["spec"]:
                    raise ValueError(f"候选冻结SHA不符 {key}")
            draw_ids = [(r["task"], r["episode"], r["attempt"]) for r in draft_rows]
            if len(draw_ids) != len(set(draw_ids)):
                raise ValueError("抽签尝试身份重复")
            result_ids = [(r["task"], r["episode"]) for r in results]
            if len(result_ids) != len(set(result_ids)):
                raise ValueError("轨迹身份重复")
            for row in results:
                key = (row["task"], row["episode"])
                if key not in candidates or any(row[k] != candidates[key][k] for k in ("seed", "difficulty", "attempt", "spec_sha256")):
                    raise ValueError(f"轨迹跨候选或身份不符 {key}")
                if type(row.get("ok")) is not bool:
                    raise ValueError("轨迹ok必须为bool")
                if row["ok"]:
                    try:
                        detail = verify_success(base / "rollout/run1", row)
                        successes.append(dict(task=row["task"], tier=tier, episode=row["episode"], **detail))
                    except Exception as exc:
                        errors.append({"cell": f"{row['task']}/{tier}", "episode": row["episode"], "error": str(exc)})
            for task in sorted(tasks):
                attempts = [r for r in draft_rows if r["task"] == task]
                generated = [r for r in results if r["task"] == task]
                count = sum(r.get("reset_ok") is True for r in attempts)
                success = sum(r["ok"] for r in generated)
                cells[f"{task}/{tier}"] = {"draw_attempts": len(attempts), "draw_failures": len(attempts)-count,
                    "candidates": count, "candidate_shortfall": max(0,10-count), "rollout_attempts":len(generated),
                    "rollout_failures":len(generated)-success,"successes":success,"success_shortfall":max(0,3-success)}
                if len(attempts)>60 or count>10 or len(generated)>10 or success>3:
                    errors.append({"cell": f"{task}/{tier}", "error":"超出批准预算或目标"})
        except Exception as exc:
            errors.append({"tier": tier, "error": f"{type(exc).__name__}: {exc}"})
    return {"integrity":"PASS" if not errors and len(cells)==55 else "FAIL", "cells":cells,"errors":errors,
            "successful_media":successes,"expected_cells":55,"candidate_target":550,"success_target":165,
            "candidates":sum(c["candidates"] for c in cells.values()),"successes":sum(c["successes"] for c in cells.values())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("manifest","compare","verify"))
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--source-manifest",type=Path)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if args.mode=="manifest":
        report=manifest(args.root)
        ok=True
    elif args.mode=="compare":
        expected=json.loads(args.source_manifest.read_text())
        actual=manifest(args.root)
        report={"missing":sorted(set(expected)-set(actual)),"extra":sorted(set(actual)-set(expected)),
                "mismatches":[p for p in expected.keys() & actual.keys() if expected[p]!=actual[p]]}
        ok=not any(report.values())
        print(f"TRANSFER_SHA={'PASS' if ok else 'FAIL'} files={len(actual)}")
    else:
        report=verify(args.root)
        ok=report["integrity"]=="PASS"
        print(f"S4_REPORT=REPORT cells={len(report['cells'])}/55 candidates={report['candidates']}/550 successes={report['successes']}/165")
        print(f"S4_INTEGRITY={report['integrity']} errors={len(report['errors'])}")
    with args.out.open("x",encoding="utf-8") as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
        stream.write("\n")
    return 0 if ok else 1


if __name__=="__main__":
    raise SystemExit(main())
