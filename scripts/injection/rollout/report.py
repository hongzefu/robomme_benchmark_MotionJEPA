"""从唯一结果表生成实跑报告，正式交付配额与局部诊断分别判断。"""
from collections import Counter
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from .state import StateError, atomic_text, write_json, file_sha


def report(store, purpose="delivery"):
    audit = store.audit()
    header, candidates, rows = store.load()
    successful = [row for row in rows if row["kind"] == "h5" and row["ok"]]
    def verify(row):
        path = Path(row["h5_path"])
        if not path.is_file() or path.stat().st_size != row["h5_bytes"] or file_sha(path) != row["h5_sha256"]:
            raise StateError(f"成功结果的 HDF5 缺失或散列不符：{path}")
        return {"path": str(path), "sha256": row["h5_sha256"], "bytes": row["h5_bytes"]}
    with ThreadPoolExecutor(max_workers=8) as pool:
        checked = list(pool.map(verify, successful))
    write_json(store.logs / "h5_integrity.json", {"passed": True, "checked": len(checked), "files": checked})
    counts = Counter((r["kind"], r["task"], r["difficulty"], r["role"]) for r in rows)
    lines = ["# 实跑结果", "", f"运行：`{header['run_id']}`；用途：`{purpose}`。", "",
             "结果按唯一键保存；reset 通过只表示能建环境，不表示可以完成任务。", "",
             "| 组 | HDF5 正式 | HDF5 备用 | HDF5 失败 | reset 正式 | reset 备用 | reset 失败 |", "|---|---:|---:|---:|---:|---:|---:|"]
    gaps = []
    for group in header["delivery_config_snapshot"]["groups"]:
        task, difficulty = group["task"], group["difficulty"]
        name = f"{task}/{difficulty}"
        if name not in header["group_provenance"]:
            continue
        numbers = [counts[(kind, task, difficulty, role)] for kind in ("h5", "reset") for role in ("primary", "spare", "failed")]
        lines.append("| " + name + " | " + " | ".join(map(str, numbers)) + " |")
        if numbers[0] != group["target_h5"] or numbers[3] != header["delivery_config_snapshot"]["extra_candidates"]:
            gaps.append(name)
    videos = Counter((r.get("video") or {}).get("status", "unrecorded") for r in rows if r["kind"] == "h5")
    lines += ["", "## 视频状态", "", str(dict(videos)), "", "## 失败记录", "",
              "| 类型 | 组 | episode | seed | 异常 |", "|---|---|---:|---:|---|"]
    for row in rows:
        if not row["ok"]:
            lines.append(f"| {row['kind']} | {row['task']}/{row['difficulty']} | {row['episode']} | {row['seed']} | {row.get('error_type')} |")
    lines += ["", f"候选角色：`{header['roles']}`。", "", f"完整交付缺口组：`{gaps}`。局部运行不冒充完整交付。", ""]
    atomic_text(store.state / "ROLLOUT.md", "\n".join(lines))
    result = {"passed": not gaps if purpose == "delivery" else True, "purpose": purpose, "roles": header["roles"],
              "video_status_counts": dict(videos), "quota_gaps": gaps, "audit": audit}
    write_json(store.logs / "result.json", result)
    if purpose == "delivery" and gaps:
        raise StateError(f"正式交付配额不足：{gaps}")
    print(f"REPORT=PASS purpose={purpose} rows={len(rows)} pending={audit['pending']} unused={audit['unused']}", flush=True)
    return result


def main():
    import argparse
    from .state import RunStore, run_root
    parser = argparse.ArgumentParser(description="核验成品散列并生成实跑报告")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--purpose", choices=("delivery", "parity", "smoke"), default="delivery")
    parser.add_argument("--label")
    args = parser.parse_args()
    store = RunStore(run_root(args.run_id), args.label)
    with store.locked():
        report(store, args.purpose)


if __name__ == "__main__":
    main()
