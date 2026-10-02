"""v7 评估视频搬运（0928 方案 §3.1，阶段 9～10）：NFS 暂存 → 本机 /data，与评估解耦、天然可续。

只搬「已完成」的局：按 ``--policy`` 认终态记录（SimpleMemVLA ``results-r*-shard*.jsonl``、MME-VLA ``episodes.jsonl``，
路径由 ``--records-glob`` 给出），``status`` ∈ {success, fail, timeout} 才算终态；同一 ``(task, episode)`` 多行时取最后一个
终态行。视频路径取记录里的 ``video`` 字段（两个 v7 分支都写绝对路径，文件名 ``{task}_{tier}_{episode}_{seed}.mp4``）；
``--identities`` 给出时逐局核对 tier／seed 与清单一致，文件名缺 seed 时按清单补进目标文件名。

每个候选视频：大小连续 ``--stable-sec`` 秒不变 → ``rsync`` 到 ``<dest>/<tier>/<task>/`` → 两端 sha256 相同 → 删 NFS 副本 →
往 ``<dest>/moved.jsonl`` 追加一行。已在 ``moved.jsonl`` 里的源路径跳过。每 ``--interval`` 秒打印
``VMOVE moved=<n> pending=<n> bytes=<n> stage_bytes=<n>``；``--once`` 扫一轮即退（评估结束后的全量对账），
常驻模式下 ``--stop-file`` 出现且无待搬时退出；结束打印 ``EXIT_CODE=``。

官方路线（xhard0 旧入口）的记录没有 ``episode``／``tier`` 字段：局号回退到 ``source_episode``，档位由 ``--tier`` 给出。
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

FINAL = ("success", "fail", "timeout")


def episode_of(row: dict) -> int:
    """局号：v7 路线记录写 ``episode``；官方路线（xhard0 旧入口）记录只有 ``source_episode``。"""
    return int(row["episode"] if row.get("episode") is not None else row["source_episode"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_identities(path: str | None) -> dict[tuple[str, int], dict]:
    if not path:
        return {}
    out = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            out[(row["task"], int(row["episode"]))] = row
    return out


def terminal_records(pattern: str) -> dict[tuple[str, int], dict]:
    """同一 (task, episode) 取最后一个终态行（重评只追加 error 行，终态行不会再跑）。"""
    last: dict[tuple[str, int], dict] = {}
    for path in sorted(glob.glob(pattern)):
        for line in Path(path).read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # 评估进程正在追加的半行，下一轮再读
            if row.get("status") in FINAL and row.get("video"):
                last[(row["task"], episode_of(row))] = row
    return last


def target_name(src: Path, row: dict, ident: dict | None) -> tuple[str, str]:
    tier = str(row.get("tier") or (ident or {}).get("tier") or "")
    seed = row.get("seed", (ident or {}).get("seed"))
    name = src.name
    if seed is not None and f"_{seed}" not in src.stem:
        name = f"{src.stem}_{seed}{src.suffix}"
    return tier, name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy", required=True, choices=("simplememvla", "mmevla"))
    ap.add_argument("--records-glob", required=True, help="终态记录 jsonl 的 glob")
    ap.add_argument("--stage", required=True, help="NFS 视频暂存根（只用于统计积压字节数与越界检查）")
    ap.add_argument("--dest", required=True)
    ap.add_argument("--identities", default=None, help="eval-identities-1262.jsonl（逐局核对 tier／seed）")
    ap.add_argument("--stable-sec", type=float, default=10.0)
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--stop-file", default=None)
    ap.add_argument("--tier", default=None, help="记录不带 tier 时使用的档位（官方路线 xhard0 旧入口）")
    args = ap.parse_args()

    stage, dest = Path(args.stage).resolve(), Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    moved_log = dest / "moved.jsonl"
    moved = set()
    if moved_log.exists():
        moved = {json.loads(l)["src"] for l in moved_log.read_text().splitlines() if l.strip()}
    idents = load_identities(args.identities)
    seen: dict[str, tuple[int, float]] = {}
    moved_bytes = 0
    bad = 0
    last_report = 0.0
    while True:
        pending = 0
        for key, row in terminal_records(args.records_glob).items():
            if args.tier and not row.get("tier"):
                row = {**row, "tier": args.tier}
            src = Path(row["video"])
            if str(src) in moved:
                continue
            if not src.exists():
                continue  # 未落盘（或 video_error）；对账时由缺失统计体现
            if stage not in src.resolve().parents:
                print(f"# 越界：视频不在暂存根下，跳过 {src}", flush=True)
                bad += 1
                moved.add(str(src))
                continue
            ident = idents.get(key)
            if idents and (ident is None or str(ident["tier"]) != str(row.get("tier", ident["tier"]))
                           or int(ident["seed"]) != int(row["seed"])):
                print(f"# 身份不符，跳过 {key} record=({row.get('tier')},{row.get('seed')}) "
                      f"ident={None if ident is None else (ident['tier'], ident['seed'])}", flush=True)
                bad += 1
                moved.add(str(src))
                continue
            size, now = src.stat().st_size, time.time()
            prev = seen.get(str(src))
            if prev is None or prev[0] != size:
                seen[str(src)] = (size, now)
                pending += 1
                continue
            if now - prev[1] < args.stable_sec:
                pending += 1
                continue
            tier, name = target_name(src, row, ident)
            out_dir = dest / (tier or "_notier") / row["task"]
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / name
            proc = subprocess.run(["rsync", "-a", str(src), str(out)], capture_output=True, text=True)
            if proc.returncode != 0:
                print(f"# rsync 失败 {src}: {proc.stderr.strip()[:300]}", flush=True)
                pending += 1
                continue
            digest = sha256(src)
            if sha256(out) != digest:
                print(f"# sha256 不一致，保留 NFS 副本 {src}", flush=True)
                out.unlink(missing_ok=True)
                pending += 1
                continue
            src.unlink()
            moved.add(str(src))
            moved_bytes += size
            with moved_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"policy": args.policy, "task": row["task"], "episode": episode_of(row),
                                         "tier": tier, "seed": row.get("seed"), "status": row["status"],
                                         "src": str(src), "dest": str(out), "sha256": digest, "bytes": size,
                                         "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, ensure_ascii=False) + "\n")
        now = time.time()
        stop = bool(args.stop_file and Path(args.stop_file).exists() and pending == 0)
        if args.once or stop or now - last_report >= args.interval:
            stage_bytes = sum(p.stat().st_size for p in stage.rglob("*.mp4")) if stage.exists() else 0
            print(f"VMOVE moved={len(moved) - bad} pending={pending} bytes={moved_bytes} stage_bytes={stage_bytes} "
                  f"skipped={bad}", flush=True)
            last_report = now
        if args.once:
            # 对账轮：还有待稳定的视频时再等一轮，直到清空
            if pending == 0:
                break
        elif stop:
            break
        time.sleep(min(args.stable_sec, args.interval))
    print("EXIT_CODE=0", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
