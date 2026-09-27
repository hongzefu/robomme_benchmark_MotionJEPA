"""阶段 0b 的 legacy 保留清单与归档（0926-robomme-hard-split-plan.md 第一部分 §0.3 步骤 4、5）。

`artifacts/` 不进 git，待删目录里被文档引用或属显式验收依赖的小文件，归档进 `docs/` 的那份就是
唯一副本；因此清单由本脚本从文档引用生成，不靠人手。

- `list`（只读）：扫描 `docs/validation/**`、`docs/ledger/**` 与三份 0925/0926 计划里的全部
  `artifacts/…` 路径串，加上显式验收依赖，只保留落在待删目录内、类型白名单内的文件，写 JSON 清单。
  末行 `LEGACY_KEEP=PASS referenced=<n> resolved=<n> missing=0 absent_before=<k> files=<f> bytes=<b>`。
  `missing` 只计显式依赖缺失（非零即 FAIL）；文档引用了但运行前早已不存在的路径计入
  `absent_before` 并逐条列出，它们无物可归档。
- `archive`：按清单复制到 `docs/validation/<版本>/records/legacy/<原二级目录>/…`，每个版本写
  `MANIFEST.md`（原路径、新路径、字节、sha256），复制后逐文件复核 sha256。
  末行 `LEGACY_ARCHIVE=PASS copied=<n> bytes=<b> sha_mismatch=0`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".md", ".json", ".jsonl", ".txt", ".log", ".sh", ".py"}
MEDIA_SUFFIXES = {".h5", ".mp4", ".png", ".jpg", ".npy"}
SMALL_LIMIT = 1 << 20
REFERENCE_SOURCES = ("docs/validation/**/*", "docs/ledger/**/*")
REFERENCE_PLANS = ("0925-newtask-release-v6-plan.md", "0926-v6-audit-fix-plan.md", "0926-robomme-hard-split-plan.md")
PATH_RE = re.compile(r"artifacts/[A-Za-z0-9_.\-/]+")

#: 附录 B 表 A 的未跟踪产物目录 + 表 B 第 4 条，逐目录显式列名（与步骤 8 的删除清单同源）。
DELETE_TARGETS = (
    "artifacts/test-tmp", "artifacts/cache", "artifacts/codex-multiagent", "artifacts/logs",
    "artifacts/newtask-v4", "artifacts/newtask-v5", "artifacts/audit",
    *(f"artifacts/newtask-v6/{name}" for name in (
        "v6-01", "v6-01-infra-recovery-01", "v6-s2-20260926-01", "v6-s3-20260926-01",
        "gl-smoke-61890467-binf-xhard1-20260926T195419Z", "s3-slow-investigation", "s0", "s1-reset",
        "s2-prep", "s4-prep", "s4-launch", "plan-probes", "vpb-order-fix-prep", "site", "site-v2",
        "site-review", "site-v3", "site-v4", "site-v5", "site-v6", "site-v7", "site-v8", "site-v9", "site-v10")),
)

#: 待删目录里整体不归档的子树：两个审查用 git worktree 源码快照（代码可由 git 还原，
#: 其中的 审查汇总.md / verify/ 走显式依赖另收）、uv 下载缓存与测试临时目录。
EXCLUDE = (
    "artifacts/audit/v6-semantic-0a3f989", "artifacts/audit/v6-semantic-0a3f989-01a0e086", "artifacts/cache",
    "artifacts/test-tmp",
)

#: 显式验收依赖（§0.3 步骤 4 第②项），glob 相对仓库根；每条至少命中一个文件，否则计 missing。
EXPLICIT = (
    "artifacts/newtask-v6/s0/lightweight-baseline.log",
    "artifacts/newtask-v6/s0/lightweight-shards/**/*",
    "artifacts/newtask-v6/s0/lightweight-shards/**/v6-final-identities.txt",
    "artifacts/newtask-v6/s4-launch/verification/*.json",
    "artifacts/newtask-v6/s4-launch/recovery/approval.json",
    "artifacts/newtask-v6/s4-launch/incident/**/*",
    "artifacts/newtask-v6/v6-s3-20260926-01/run_s3.py",
    "artifacts/newtask-v6/v6-s3-20260926-01/compare/summary.json",
    "artifacts/newtask-v6/v6-s3-20260926-01/handoff-prep/production-session-*/outcome.json",
    "artifacts/newtask-v6/v6-s3-20260926-01/handoff-prep/production-session-*/final_verification.json",
    "artifacts/audit/*/审查汇总.md",
    "artifacts/audit/*/verify/**/*",
    "artifacts/audit/*/records/**/*",
    "artifacts/newtask-v6/v6-01/**/final-delivery.json",
)
#: 计划列出但盘点时从未存在的显式项：audit 各目录无 records/；v6-01 的交付文件实际落在
#: s4-launch/verification/final-delivery.json（已由上面的 verification/*.json 覆盖）。只报告，不计 missing。
OPTIONAL = {"artifacts/audit/*/records/**/*", "artifacts/newtask-v6/v6-01/**/final-delivery.json"}


def target_of(rel: str) -> str | None:
    for target in DELETE_TARGETS:
        if rel == target or rel.startswith(target + "/"):
            return target
    return None


def version_of(rel: str) -> str:
    """原路径 → 归档版本目录：newtask-v4→v4、newtask-v5→v5，其余（v6、audit、logs 等）→v6。"""
    second = rel.split("/")[1]
    return {"newtask-v4": "newtask-v4", "newtask-v5": "newtask-v5"}.get(second, "newtask-v6")


def archive_path(rel: str) -> str:
    parts = rel.split("/")
    # newtask-v6/<子目录>/… 取子目录为「原二级目录」；其余 artifacts/<目录>/… 保留目录名。
    tail = parts[2:] if parts[1].startswith("newtask-v") else parts[1:]
    return f"docs/validation/{version_of(rel)}/records/legacy/" + "/".join(tail)


def excluded(rel: str) -> bool:
    return any(rel == e or rel.startswith(e + "/") for e in EXCLUDE)


def wanted(path: Path, explicit_file: bool) -> bool:
    if path.is_symlink() or not path.is_file() or path.suffix in MEDIA_SUFFIXES or path.suffix not in TEXT_SUFFIXES:
        return False
    return explicit_file or path.stat().st_size <= SMALL_LIMIT


def collect_references() -> set[str]:
    sources = [p for pattern in REFERENCE_SOURCES for p in ROOT.glob(pattern)]
    sources += [ROOT / name for name in REFERENCE_PLANS]
    refs = set()
    for source in sources:
        if source.is_file() and source.suffix in TEXT_SUFFIXES:
            for match in PATH_RE.findall(source.read_text(errors="ignore")):
                refs.add(match.rstrip(".-/"))
    return refs


def build_list() -> dict:
    refs = sorted(r for r in collect_references() if target_of(r))
    files: dict[str, str] = {}
    absent, resolved = [], 0
    for rel in refs:
        path = ROOT / rel
        if not path.exists():
            absent.append(rel)
            continue
        resolved += 1
        if path.is_dir():
            for child in path.rglob("*"):
                child_rel = child.relative_to(ROOT).as_posix()
                if not excluded(child_rel) and wanted(child, False):
                    files.setdefault(child_rel, "reference")
        elif not excluded(rel) and wanted(path, True):
            files.setdefault(rel, "reference")
    missing, optional_absent = [], []
    for pattern in EXPLICIT:
        hits = [p for p in ROOT.glob(pattern) if p.is_file()]
        if not hits:
            (optional_absent if pattern in OPTIONAL else missing).append(pattern)
        for hit in hits:
            if wanted(hit, True):
                files[hit.relative_to(ROOT).as_posix()] = "explicit"
    entries = []
    for rel in sorted(files):
        size = (ROOT / rel).stat().st_size
        entries.append({"source": rel, "dest": archive_path(rel), "bytes": size, "why": files[rel],
                        "large": size > SMALL_LIMIT})
    return {"schema": "legacy-keep-list/1", "delete_targets": list(DELETE_TARGETS), "referenced": len(refs),
            "resolved": resolved, "absent_before": absent, "missing": missing,
            "optional_absent": optional_absent, "files": entries}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def cmd_list(args) -> int:
    data = build_list()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for rel in data["missing"]:
        print(f"MISSING {rel}")
    for rel in data["optional_absent"]:
        print(f"OPTIONAL_ABSENT {rel}")
    large = [e for e in data["files"] if e["large"]]
    for entry in large:
        print(f"LARGE {entry['bytes']} {entry['source']}")
    total = sum(e["bytes"] for e in data["files"])
    verdict = "PASS" if not data["missing"] else "FAIL"
    print(f"LEGACY_KEEP={verdict} referenced={data['referenced']} resolved={data['resolved']} "
          f"missing={len(data['missing'])} absent_before={len(data['absent_before'])} "
          f"files={len(data['files'])} large={len(large)} bytes={total}")
    return 0 if verdict == "PASS" else 1


def cmd_archive(args) -> int:
    data = json.loads(args.list.read_text(encoding="utf-8"))
    if data["missing"]:
        raise SystemExit("清单 missing 非零，拒绝归档")
    by_version: dict[str, list[tuple]] = {}
    copied = total = mismatch = 0
    for entry in data["files"]:
        src, dst = ROOT / entry["source"], ROOT / entry["dest"]
        if dst.exists():
            raise SystemExit(f"目标已存在，拒绝覆盖：{dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        a, b = sha256(src), sha256(dst)
        mismatch += a != b
        copied += 1
        total += entry["bytes"]
        by_version.setdefault(entry["dest"].split("/")[2], []).append((entry["source"], entry["dest"], entry["bytes"], b))
    for version, rows in by_version.items():
        base = ROOT / f"docs/validation/{version}/records/legacy"
        lines = ["# legacy 归档清单", "",
                 "阶段 0b（`0926-robomme-hard-split-plan.md` 第一部分 §0.3）由 `scripts/parity/legacy_keep_list.py archive` 生成。",
                 "原路径所在的 `artifacts/` 目录随后删除，本目录即唯一副本。", "",
                 "| 原路径 | 新路径 | 字节 | sha256 |", "|---|---|---|---|"]
        lines += [f"| `{s}` | `{d.removeprefix(f'docs/validation/{version}/records/legacy/')}` | {n} | `{h}` |"
                  for s, d, n, h in rows]
        (base / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    verdict = "PASS" if mismatch == 0 else "FAIL"
    print(f"LEGACY_ARCHIVE={verdict} copied={copied} bytes={total} sha_mismatch={mismatch}")
    return 0 if verdict == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--out", type=Path, default=ROOT / "artifacts/newtask-v6/hard-split/legacy-keep-list.json")
    p_arch = sub.add_parser("archive")
    p_arch.add_argument("--list", type=Path, default=ROOT / "artifacts/newtask-v6/hard-split/legacy-keep-list.json")
    args = parser.parse_args(argv)
    return cmd_list(args) if args.command == "list" else cmd_archive(args)


if __name__ == "__main__":
    sys.exit(main())
