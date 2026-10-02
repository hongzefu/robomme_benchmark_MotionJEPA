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

``--mode v8``（1001-v8-post-evaluation-gl-plan.md 第一部分 §1 第 7 条、契约 C4 第二段；不带 ``--mode`` 时一切同上）：

    python scripts/injection-dev/eval_video_mover.py --mode v8 --stage <NFS 运行根> \\
        --dest artifacts/v8-evaluation/<R>/videos [--policies smvla,mme] [--once] [--stop-file F] [--interval S]

扫 ``<stage>/sNN/<policy>/results.jsonl`` 的 V8 结果行（``v8: true``，含 error／infra 尝试与迟到终态），按 ``rec_dir`` 的目录名
``<key>.a<n>`` 找 ``<stage>/sNN/<policy>/rec/<目录名>/``；只搬「结果行已写出」的目录（进行中的不碰），且目录内全部文件
``--stable-sec`` 秒无变化、没有 rsync 临时文件（点开头）。整目录 ``rsync -a`` 到 ``<dest>/<policy>/<tier>/<task>/<目录名>/`` →
逐文件两端 sha256 相同 → 才删 NFS 副本 → 往 ``<dest>/moved.jsonl`` 追加一行（``mode: "v8"``，含逐文件 sha256）；已搬的源不再
存在，自然跳过，可续。sha 不符：删本机这份不完整副本、保留 NFS 源，计 sha_mismatch（常驻模式下一轮重试）。常驻模式每
``--interval`` 秒打印 ``VMOVE mode=v8 moved= pending= bytes= stage_bytes= sha_mismatch=``，``--stop-file`` 出现且无待搬时退出。
``--once``：搬到无待稳定目录后做全量对账，打印
``V8_EVAL_VIDEOS=PASS|FAIL policies= expected= videos= missing= decode_fail= sha_mismatch= error_attempt_videos=``：
expected = 每模型账本 accepted 终态数之和（权威终态口径复用 ``scripts/eval-official/v8_report.py``）；videos = 本机已有且
front.mkv、wrist.mkv 都能读出帧数（>0）的终态录像目录数；error_attempt_videos = 本机已有的非权威尝试（错误／重试／迟到）目录数。
帧数优先用 ``ffprobe -count_frames``，没有 ffprobe 时用 ``imageio-ffmpeg`` 自带 ffmpeg 全解码计帧，都没有则判 decode_fail
（``reason=no_decoder``）。读得出的帧数按 (路径, 大小, mtime) 缓存在 ``<dest>/decode-cache.jsonl``。末行 ``EXIT_CODE=``（FAIL 为 1）。
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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


# ------------------------------------------------------------------ V8 模式

V8_MEDIA = ("front.mkv", "wrist.mkv")
_REPORT_MOD = None


def v8_report_mod():
    """复用 scripts/eval-official/v8_report.py 的读入与权威终态口径（accepted_attempt_id），两处不各写一套。"""
    global _REPORT_MOD
    if _REPORT_MOD is None:
        path = Path(__file__).resolve().parents[1] / "eval-official" / "v8_report.py"
        spec = importlib.util.spec_from_file_location("v8_report_for_mover", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _REPORT_MOD = mod
    return _REPORT_MOD


def tree_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() or p.is_symlink())


def dir_snapshot(root: Path) -> tuple | None:
    """目录内全部文件 (相对路径, 大小, mtime_ns)；有 rsync 临时文件（点开头）时返回 None（仍在写）。"""
    snap = []
    for p in tree_files(root):
        if p.name.startswith("."):
            return None
        st = p.stat()
        snap.append((str(p.relative_to(root)), st.st_size, st.st_mtime_ns))
    return tuple(snap)


def v8_attempt_dirs(stage: Path, policies: list[str]) -> list[dict]:
    """结果行已写出的全部 V8 尝试（含 error／infra／迟到），每个录像目录一项。"""
    rm = v8_report_mod()
    out, seen = [], set()
    for pol in policies:
        st = rm.load_policy(stage, pol)
        for row in st["results"]:
            if not row.get("v8"):
                continue
            name = rm.rec_name(row)
            if not name:
                continue
            src = Path(row["_seat_dir"]) / pol / "rec" / name
            if str(src) in seen:
                continue
            seen.add(str(src))
            out.append({"policy": pol, "row": row, "name": name, "src": src})
    return out


def v8_dest_dir(dest: Path, policy: str, row: dict, name: str) -> Path:
    return dest / policy / str(row.get("tier") or "_notier") / str(row.get("task")) / name


def v8_move_dir(item: dict, dest: Path, moved_log: Path) -> tuple[str, int]:
    """rsync 整目录 → 逐文件 sha256 → 删源 → 记 moved.jsonl。返回 (结果, 字节数)；结果 ∈ moved / rsync_fail / sha_mismatch。"""
    src, row = item["src"], item["row"]
    out = v8_dest_dir(dest, item["policy"], row, item["name"])
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["rsync", "-a", f"{src}/", f"{out}/"], capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"# rsync 失败 {src}: {proc.stderr.strip()[:300]}", flush=True)
        return "rsync_fail", 0
    files: dict[str, str] = {}
    nbytes = 0
    for f in tree_files(src):
        rel = str(f.relative_to(src))
        digest = sha256(f)
        tgt = out / rel
        if not tgt.is_file() or sha256(tgt) != digest:
            print(f"# sha256 不一致，保留 NFS 副本并删本机不完整副本 {src} 文件 {rel}", flush=True)
            shutil.rmtree(out, ignore_errors=True)
            return "sha_mismatch", 0
        files[rel] = digest
        nbytes += f.stat().st_size
    for f in tree_files(src):
        f.unlink()
    for d in sorted((p for p in src.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        d.rmdir()
    src.rmdir()
    with moved_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"mode": "v8", "policy": item["policy"], "key": row.get("key"),
                                 "task": row.get("task"), "tier": row.get("tier"), "seed": row.get("seed"),
                                 "attempt_id": row.get("attempt_id"), "attempt_no": row.get("attempt_no"),
                                 "status": row.get("status"), "infra": row.get("infra"), "seat": row.get("_seat"),
                                 "src": str(src), "dest": str(out), "files": files, "bytes": nbytes,
                                 "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return "moved", nbytes


def pick_decoder() -> tuple[str, str | None]:
    """ffprobe 优先；没有就用 imageio-ffmpeg 自带的 ffmpeg（再退回 PATH 里的 ffmpeg）；都没有返回 none。"""
    probe = shutil.which("ffprobe")
    if probe:
        return "ffprobe", probe
    try:
        import imageio_ffmpeg  # type: ignore

        return "ffmpeg", imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        pass
    ff = shutil.which("ffmpeg")
    if ff:
        return "ffmpeg", ff
    return "none", None


def count_frames(path: Path, decoder: tuple[str, str | None]) -> int | None:
    """完整解码视频流 0 并返回帧数；读不出返回 None。"""
    kind, exe = decoder
    try:
        if kind == "ffprobe":
            proc = subprocess.run([exe, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                                   "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
                                  capture_output=True, text=True, timeout=1800)
            txt = proc.stdout.strip().split("\n")[0].strip().rstrip(",")
            return int(txt) if proc.returncode == 0 and txt.isdigit() else None
        if kind == "ffmpeg":
            proc = subprocess.run([exe, "-nostdin", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "null", "-",
                                   "-progress", "pipe:1"], capture_output=True, text=True, timeout=1800)
            frames = [l.split("=", 1)[1].strip() for l in proc.stdout.splitlines() if l.startswith("frame=")]
            return int(frames[-1]) if proc.returncode == 0 and frames and frames[-1].isdigit() else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return None


class DecodeCache:
    """读得出的帧数按 (路径, 大小, mtime_ns) 缓存；读不出的不缓存、下次重试。"""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[tuple, int] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                    self.data[(r["path"], r["size"], r["mtime_ns"])] = int(r["frames"])
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue

    def frames(self, f: Path, decoder) -> int | None:
        st = f.stat()
        k = (str(f.resolve()), st.st_size, st.st_mtime_ns)
        if self.data.get(k):
            return self.data[k]
        n = count_frames(f, decoder)
        if n:
            self.data[k] = n
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"path": k[0], "size": k[1], "mtime_ns": k[2], "frames": n}) + "\n")
        return n


def v8_verify(stage: Path, dest: Path, policies: list[str], sha_mismatch: int, workers: int) -> tuple[bool, str, list]:
    rm = v8_report_mod()
    decoder = pick_decoder()
    if decoder[0] != "ffprobe":
        print(f"# 解码器：{decoder[0]} {decoder[1] or ''}（未找到 ffprobe）", flush=True)
    cache = DecodeCache(dest / "decode-cache.jsonl")
    expected = 0
    terminal_dirs: list[tuple[str, dict, Path]] = []
    error_attempt_videos = 0
    for pol in policies:
        an = rm.analyze_attempts(rm.load_policy(stage, pol))
        expected += len(an["accepted"])
        for row in an["accepted"].values():
            terminal_dirs.append((pol, row, v8_dest_dir(dest, pol, row, rm.rec_name(row) or "_norec")))
        acc_ids = {str(r.get("attempt_id")) for r in an["accepted"].values()}
        for aid, lst in an["by_attempt"].items():
            row = lst[-1]
            if aid in acc_ids or not rm.rec_name(row):
                continue
            if v8_dest_dir(dest, pol, row, rm.rec_name(row)).is_dir():
                error_attempt_videos += 1
    missing = decode_fail = 0
    problems: list[dict] = []
    to_decode = []
    for pol, row, d in terminal_dirs:
        if not d.is_dir() or not all((d / m).is_file() for m in V8_MEDIA):
            missing += 1
            problems.append({"policy": pol, "key": row.get("key"), "problem": "missing", "dir": str(d)})
            continue
        to_decode.append((pol, row, d))

    def check(item):
        _, _, d = item
        if decoder[0] == "none":
            return item, {m: None for m in V8_MEDIA}
        return item, {m: cache.frames(d / m, decoder) for m in V8_MEDIA}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        results = list(ex.map(check, to_decode))
    videos = 0
    for (pol, row, d), frames in results:
        if all(frames[m] for m in V8_MEDIA):
            videos += 1
        else:
            decode_fail += 1
            problems.append({"policy": pol, "key": row.get("key"), "problem": "decode_fail", "dir": str(d),
                             "frames": frames, "reason": "no_decoder" if decoder[0] == "none" else None})
    ok = expected > 0 and missing == 0 and decode_fail == 0 and sha_mismatch == 0 and videos == expected
    line = (f"V8_EVAL_VIDEOS={'PASS' if ok else 'FAIL'} policies={len(policies)} expected={expected} videos={videos} "
            f"missing={missing} decode_fail={decode_fail} sha_mismatch={sha_mismatch} "
            f"error_attempt_videos={error_attempt_videos}")
    return ok, line, problems


def v8_main(args) -> int:
    stage, dest = Path(args.stage).resolve(), Path(args.dest)
    policies = [p for p in args.policies.split(",") if p]
    dest.mkdir(parents=True, exist_ok=True)
    moved_log = dest / "moved.jsonl"
    seen: dict[str, tuple[tuple | None, float]] = {}
    failed: set[str] = set()
    moved_bytes = moved_n = sha_mismatch = 0
    last_report = 0.0
    while True:
        pending = 0
        for item in v8_attempt_dirs(stage, policies):
            src = item["src"]
            key = str(src)
            if not src.is_dir():
                continue  # 尚未同步到运行根，或已搬走（moved.jsonl 有记录）
            if args.once and key in failed:
                continue  # 对账轮里同一目录只试一次，sha 不符已计数
            snap = dir_snapshot(src)
            now = time.time()
            prev = seen.get(key)
            if snap is None or prev is None or prev[0] != snap:
                seen[key] = (snap, now)
                pending += 1
                continue
            if now - prev[1] < args.stable_sec:
                pending += 1
                continue
            result, nbytes = v8_move_dir(item, dest, moved_log)
            seen.pop(key, None)
            if result == "moved":
                moved_n += 1
                moved_bytes += nbytes
            else:
                sha_mismatch += result == "sha_mismatch"
                failed.add(key)
                if not args.once:
                    pending += 1
        now = time.time()
        stop = bool(args.stop_file and Path(args.stop_file).exists() and pending == 0)
        if args.once or stop or now - last_report >= args.interval:
            stage_bytes = sum(f.stat().st_size for pol in policies for f in stage.glob(f"s*/{pol}/rec/**/*")
                              if f.is_file()) if stage.exists() else 0
            print(f"VMOVE mode=v8 moved={moved_n} pending={pending} bytes={moved_bytes} stage_bytes={stage_bytes} "
                  f"sha_mismatch={sha_mismatch}", flush=True)
            last_report = now
        if args.once:
            if pending == 0:
                break
        elif stop:
            break
        time.sleep(max(0.05, min(args.stable_sec, args.interval)))
    rc = 0
    if args.once:
        ok, line, problems = v8_verify(stage, dest, policies, sha_mismatch, args.decode_workers)
        for p in problems[:50]:
            print(f"# {json.dumps(p, ensure_ascii=False)}", flush=True)
        print(line, flush=True)
        rc = 0 if ok else 1
    print(f"EXIT_CODE={rc}", flush=True)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="v7", choices=("v7", "v8"),
                    help="v7（默认，原行为）；v8：整目录搬 V8 评估录像，见 v8_main")
    ap.add_argument("--policy", default=None, choices=("simplememvla", "mmevla"), help="v7 模式必填")
    ap.add_argument("--records-glob", default=None, help="终态记录 jsonl 的 glob（v7 模式必填）")
    ap.add_argument("--policies", default="smvla,mme", help="v8 模式：要搬的模型（运行根下 sNN/<policy>/）")
    ap.add_argument("--decode-workers", type=int, default=4, help="v8 --once 解码核对并行数")
    ap.add_argument("--stage", required=True, help="NFS 视频暂存根（只用于统计积压字节数与越界检查）")
    ap.add_argument("--dest", required=True)
    ap.add_argument("--identities", default=None, help="eval-identities-1262.jsonl（逐局核对 tier／seed）")
    ap.add_argument("--stable-sec", type=float, default=10.0)
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--stop-file", default=None)
    ap.add_argument("--tier", default=None, help="记录不带 tier 时使用的档位（官方路线 xhard0 旧入口）")
    args = ap.parse_args()
    if args.mode == "v8":
        return v8_main(args)
    if not args.policy or not args.records_glob:
        ap.error("v7 模式需要 --policy 与 --records-glob")

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
