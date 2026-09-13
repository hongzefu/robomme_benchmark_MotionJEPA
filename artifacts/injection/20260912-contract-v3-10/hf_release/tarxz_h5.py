#!/usr/bin/env python3
"""RoboMME h5 数据集的批量打包 / 解包脚本（零第三方依赖，只用标准库）。

用法::

    python tarxz_h5.py decompress --input_dir . --jobs 8
    python tarxz_h5.py compress   --input_dir . --jobs 8

``decompress`` 把目录下（含子目录）的每个 ``*.tar.xz`` 解到**归档所在目录**；
``compress`` 把每个 ``record_dataset_*`` 目录打成同名 ``.tar.xz``。
解包前逐成员校验路径，拒绝绝对路径、``..`` 穿越与符号链接。
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
import tarfile
from pathlib import Path


def _safe_members(archive: tarfile.TarFile, dest: Path):
    """逐成员做路径穿越检查，安全的才交给 extract。"""
    dest = dest.resolve()
    for member in archive.getmembers():
        if member.issym() or member.islnk():
            raise ValueError(f"拒绝链接成员：{member.name}")
        name = member.name
        if name.startswith("/") or ".." in Path(name).parts:
            raise ValueError(f"拒绝越界成员：{name}")
        target = (dest / name).resolve()
        if target != dest and dest not in target.parents:
            raise ValueError(f"拒绝越界成员：{name}")
        yield member


def _decompress_one(args) -> str:
    path, remove_archive = args
    path = Path(path)
    dest = path.parent
    with tarfile.open(path, mode="r:xz") as archive:
        for member in _safe_members(archive, dest):
            archive.extract(member, path=dest)
    if remove_archive:
        path.unlink()
    return str(path)


def _compress_one(args) -> str:
    directory, remove_original = args
    directory = Path(directory)
    out = directory.with_name(directory.name + ".h5.tar.xz")
    with tarfile.open(out, mode="w:xz") as archive:
        for item in sorted(directory.rglob("*")):
            if item.is_file():
                archive.add(item, arcname=str(Path(directory.name) / item.relative_to(directory)))
    if remove_original:
        import shutil

        shutil.rmtree(directory)
    return str(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="RoboMME h5 数据集批量打包 / 解包")
    sub = parser.add_subparsers(dest="command", required=True)

    compress = sub.add_parser("compress", help="把 record_dataset_* 目录打成 .h5.tar.xz")
    compress.add_argument("--input_dir", default=".")
    compress.add_argument("--jobs", type=int, default=4)
    compress.add_argument("--remove_original", action="store_true", help="打完删掉原目录")

    decompress = sub.add_parser("decompress", help="把 *.tar.xz 解到归档所在目录")
    decompress.add_argument("--input_dir", default=".")
    decompress.add_argument("--jobs", type=int, default=4)
    decompress.add_argument("--remove_archive", action="store_true", help="解完删掉归档")

    args = parser.parse_args(argv)
    root = Path(args.input_dir).resolve()

    if args.command == "decompress":
        tasks = [(str(p), args.remove_archive) for p in sorted(root.rglob("*.tar.xz"))]
        worker = _decompress_one
    else:
        tasks = [
            (str(p), args.remove_original)
            for p in sorted(root.rglob("record_dataset_*"))
            if p.is_dir()
        ]
        worker = _compress_one

    if not tasks:
        print(f"{root} 下没有可处理的对象", file=sys.stderr)
        return 1
    jobs = max(1, min(args.jobs, len(tasks)))
    if jobs == 1:
        for task in tasks:
            print(worker(task))
    else:
        with multiprocessing.Pool(jobs) as pool:
            for done in pool.imap_unordered(worker, tasks):
                print(done)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
