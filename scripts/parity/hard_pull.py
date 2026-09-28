#!/usr/bin/env python3
"""阶段 4 逐局拉取（sled-vail 上跑，0927 计划第一部分 §5.4「流转」）：NFS 暂存 → ``/data`` → 核 sha → 删 NFS 副本。

GL 节点上的 ``hard_parity.py generate`` 每局搬到 ``<stage>/<段>/episodes/…`` 后写 ``SHIPPED``（大文件 sha 清单）；
本脚本只拉带 ``SHIPPED`` 的局，拉回后逐文件重算 sha 与 ``SHIPPED`` 比对，一致才删 NFS 上该局的 h5／mp4
（小文件留着随段末 rsync）。段目录出现 ``SEGMENT_DONE`` 后拉回小文件（identities.jsonl 等），并核 identities 里
每局 h5 都在 ``/data`` 且 sha 相等，打 ``PULL_SEGMENT=PASS|FAIL``；全部段完成后退出并打 ``PULL_DONE``。
NFS 上只存在途的局；段结束确认目录下无大文件后 ``rmdir`` 空目录由 runbook 手工执行（显式逐目录）。

    uv run --no-sync python scripts/parity/hard_pull.py --stage <NFS>/hs-stage --dest artifacts/newtask-v6/hard-split/h5 \
        --segments smoke-O-native,O-native,H-xhard,smoke-P-native,P-native,smoke-H-native,H-native
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pull_episode(src: Path, dst: Path) -> tuple[bool, str]:
    shipped = json.loads((src / "SHIPPED").read_text())
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        target = dst / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for rel, sha in shipped.items():
        if sha256_file(dst / rel) != sha:
            return False, f"sha 不符：{dst / rel}"
    for rel in shipped:
        (src / rel).unlink()
    (src / "PULLED").write_text(time.strftime("%Y-%m-%dT%H:%M:%S") + "\n")
    return True, "ok"


def finish_segment(stage: Path, dest: Path) -> bool:
    for path in sorted(p for p in stage.iterdir() if p.is_file()):
        shutil.copy2(path, dest / path.name)
    for sub in ("_runner", "_rounds"):
        if (stage / sub).is_dir():
            shutil.copytree(stage / sub, dest / sub, dirs_exist_ok=True)
    lines = [json.loads(t) for t in (dest / "identities.jsonl").read_text().splitlines() if t.strip()] \
        if (dest / "identities.jsonl").exists() else []
    bad = 0
    for line in lines:
        if line.get("path"):
            local = dest / line["path"]
            bad += int(not local.is_file() or sha256_file(local) != line["sha256"])
    leftovers = [p for p in stage.rglob("*") if p.is_file() and p.suffix in (".h5", ".mp4")]
    ok = bad == 0 and not leftovers and bool(lines)
    print(f"PULL_SEGMENT={'PASS' if ok else 'FAIL'} segment={stage.name} identities={len(lines)} "
          f"h5={sum(1 for l in lines if l.get('path'))} sha_bad={bad} nfs_leftover_media={len(leftovers)}", flush=True)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--segments", required=True)
    parser.add_argument("--interval", type=float, default=20)
    args = parser.parse_args()
    segments = [s for s in args.segments.split(",") if s]
    done: dict[str, bool] = {}
    while len(done) < len(segments):
        for seg in segments:
            if seg in done:
                continue
            stage, dest = args.stage / seg, args.dest / seg
            if not stage.is_dir():
                continue
            dest.mkdir(parents=True, exist_ok=True)
            for marker in sorted(stage.glob("episodes/**/SHIPPED")):
                src = marker.parent
                if (src / "PULLED").exists():
                    continue
                ok, note = pull_episode(src, dest / src.relative_to(stage))
                print(f"PULLED {seg}/{src.relative_to(stage)} ok={int(ok)} {'' if ok else note}", flush=True)
            if (stage / "SEGMENT_DONE").exists() and not list(p for p in stage.glob("episodes/**/SHIPPED")
                                                            if not (p.parent / "PULLED").exists()):
                done[seg] = finish_segment(stage, dest)
        time.sleep(args.interval)
    ok = all(done.values())
    print(f"PULL_DONE={'PASS' if ok else 'FAIL'} segments={len(done)} failed={[s for s, v in done.items() if not v]}",
          flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
