# -*- coding: utf-8 -*-
"""对若干产物目录流式计算 sha256，写出 SHA256SUMS 与 MANIFEST.tsv。

用途：1017-test-xhard5-12per 计划 3.4 节「上传与读回校验」的第一步——aspen 本机对
artifacts/test-xhard/full/G{1..5}/ 下的全部文件（624 个 h5、视频、清单 json/jsonl）
各算一次 sha256，作为上传 HF bucket 时随附的清单，GL 读回校验 job 以它为准。

bucket 内相对路径 = <目录 basename>/<目录内相对路径>，例如 G5/hdf5_files/BinFill_ep50_seed1.h5。
因此传入的各目录 basename 必须互不相同（G5 与 G5-r2 这种续跑目录可以并存）。

输出（写到 --out-dir）：
  SHA256SUMS   每行 "<sha256>  <bucket 内相对路径>"（两个空格，sha256sum -c 兼容），按路径排序
  MANIFEST.tsv 表头 path\tbytes\tsha256，行序与 SHA256SUMS 相同
末行判定行：SHA256SUMS=PASS|FAIL h5=<n> files=<n> bytes=<n>

只用标准库；分块读文件，不整文件读入内存。

用法（uv 管理的解释器）：
    uv run --no-sync python scripts/hf-upload/make_sha256sums.py \
        --out-dir artifacts/test-xhard/upload --expect-h5 624 \
        artifacts/test-xhard/full/G1 ... artifacts/test-xhard/full/G5
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CHUNK_BYTES = 8 * 1024 * 1024
SUMS_NAME = "SHA256SUMS"
MANIFEST_NAME = "MANIFEST.tsv"
MANIFEST_HEADER = "path\tbytes\tsha256"


def sha256_file(path: Path, chunk_bytes: int = CHUNK_BYTES) -> tuple[str, int]:
    """分块读文件，返回 (sha256 十六进制, 实际读到的字节数)。"""
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk_bytes)
            if not buf:
                break
            h.update(buf)
            n += len(buf)
    return h.hexdigest(), n


def collect_files(dirs: list[Path]) -> list[tuple[str, Path]]:
    """返回按 bucket 内相对路径排序的 (相对路径, 本地路径) 列表。"""
    names = [d.name for d in dirs]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ValueError(f"目录 basename 重复，bucket 内路径会冲突：{dup}")
    out: list[tuple[str, Path]] = []
    for d in dirs:
        if not d.is_dir():
            raise ValueError(f"不是目录：{d}")
        for p in d.rglob("*"):
            if p.is_symlink():
                raise ValueError(f"产物目录里不应有符号链接：{p}")
            if p.is_file():
                out.append((f"{d.name}/{p.relative_to(d).as_posix()}", p))
    out.sort(key=lambda t: t[0])
    return out


def format_sums(rows: list[tuple[str, int, str]]) -> str:
    return "".join(f"{sha}  {rel}\n" for rel, _n, sha in rows)


def format_manifest(rows: list[tuple[str, int, str]]) -> str:
    return MANIFEST_HEADER + "\n" + "".join(f"{rel}\t{n}\t{sha}\n" for rel, n, sha in rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", type=Path, help="产物目录（basename 作为 bucket 内前缀）")
    ap.add_argument("--out-dir", type=Path, required=True, help="SHA256SUMS 与 MANIFEST.tsv 的输出目录")
    ap.add_argument("--expect-h5", type=int, default=None, help="断言 .h5 文件总数，不符即 FAIL")
    ap.add_argument("--workers", type=int, default=4, help="并行算哈希的线程数（hashlib 释放 GIL）")
    args = ap.parse_args(argv)

    out_dir = args.out_dir.resolve()
    dirs = [d.resolve() for d in args.dirs]
    for d in dirs:
        if out_dir == d or d in out_dir.parents:
            print(f"错误: --out-dir {out_dir} 落在产物目录 {d} 内，会把清单自己算进去")
            print("SHA256SUMS=FAIL h5=0 files=0 bytes=0")
            return 2

    try:
        files = collect_files(dirs)
    except ValueError as e:
        print(f"错误: {e}")
        print("SHA256SUMS=FAIL h5=0 files=0 bytes=0")
        return 2

    def work(item: tuple[str, Path]) -> tuple[str, int, str]:
        rel, p = item
        sha, n = sha256_file(p)
        size = p.stat().st_size
        if n != size:
            raise RuntimeError(f"读到的字节数 {n} 与 stat 大小 {size} 不符（文件在被写？）：{p}")
        return rel, n, sha

    rows: list[tuple[str, int, str]] = []
    total = len(files)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for i, row in enumerate(pool.map(work, files), 1):
            rows.append(row)
            if i % 50 == 0 or i == total:
                print(f"已算 {i}/{total}：{row[0]}", flush=True)

    n_h5 = sum(1 for rel, _n, _s in rows if rel.endswith(".h5"))
    n_bytes = sum(n for _r, n, _s in rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / SUMS_NAME).write_text(format_sums(rows), encoding="utf-8")
    (out_dir / MANIFEST_NAME).write_text(format_manifest(rows), encoding="utf-8")
    print(f"已写 {out_dir / SUMS_NAME} 与 {out_dir / MANIFEST_NAME}")

    ok = args.expect_h5 is None or n_h5 == args.expect_h5
    if not ok:
        print(f"错误: h5 数 {n_h5} 与 --expect-h5 {args.expect_h5} 不符")
    print(f"SHA256SUMS={'PASS' if ok else 'FAIL'} h5={n_h5} files={len(rows)} bytes={n_bytes}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
