#!/usr/bin/env python3
"""从 HuggingFace 补齐官方参考 h5，把本机参考目录凑齐到 16 个任务。

数据源是 HuggingFace dataset 仓库 ``Yinpei/robomme_data_h5``，里面是 16 个
``record_dataset_<任务>.h5.tar.xz``，每个任务 100 个 episode。本机参考目录
（默认 ``/data/hongzefu/robomme_data_h5``）在本脚本编写时只有 4 个任务，剩下
12 个需要下载补齐。

单个任务的处理流程是「已存在就跳过 → 下载 → 解压 → 校验」四步：

1. 目标 ``.h5`` 已存在且校验通过，直接跳过，不重复下载；
2. ``.h5.tar.xz`` 不在本地时才调 ``hf download`` 拉取（走 CLI 而非 Python API，
   免得为一个一次性补数据脚本往 ``pyproject.toml`` 里加显式依赖）；
3. 用 ``tar`` 解压，优先让 ``xz`` 开多线程（``-T0``），失败则退回单线程；
4. 用 h5py 打开，逐个确认 ``episode_0`` … ``episode_99`` 都在。

下载与解压都是小时级长任务，实际使用时应当放进 tmux detached session 里跑，
再挂 Monitor 等，不要直接在前台阻塞。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Sequence

import h5py


HF_REPO_ID = "Yinpei/robomme_data_h5"
DEFAULT_ROOT = Path("/data/hongzefu/robomme_data_h5")
EXPECTED_EPISODES = 100

# 与 validate_generated_dataset_contract.ALL_TASKS 保持同一份任务清单
ALL_TASKS = (
    "PickXtimes",
    "StopCube",
    "SwingXtimes",
    "BinFill",
    "VideoUnmaskSwap",
    "VideoUnmask",
    "ButtonUnmaskSwap",
    "ButtonUnmask",
    "VideoRepick",
    "VideoPlaceButton",
    "VideoPlaceOrder",
    "PickHighlight",
    "InsertPeg",
    "MoveCube",
    "PatternLock",
    "RouteStick",
)


class FetchError(RuntimeError):
    """下载、解压或校验任一环节失败。"""


def _log(message: str) -> None:
    """带前缀的即时输出，便于 tee 到日志后被 Monitor 过滤。"""
    print(f"[fetch] {message}", flush=True)


def h5_name(task: str) -> str:
    return f"record_dataset_{task}.h5"


def archive_name(task: str) -> str:
    return f"{h5_name(task)}.tar.xz"


def verify_h5(path: Path, expected_episodes: int = EXPECTED_EPISODES) -> int:
    """打开 h5 并确认 episode 数量符合预期，返回实际 episode 数。"""
    if not path.is_file():
        raise FetchError(f"缺少文件：{path}")
    with h5py.File(path, "r") as handle:
        episodes = [name for name in handle.keys() if name.startswith("episode_")]
        missing = [
            f"episode_{index}"
            for index in range(expected_episodes)
            if f"episode_{index}" not in handle
        ]
    if missing:
        raise FetchError(
            f"{path}：缺少 {len(missing)} 个 episode，首个缺失项为 {missing[0]}"
        )
    return len(episodes)


def download_archive(task: str, root: Path) -> Path:
    """调 hf CLI 把单个 tar.xz 拉到参考目录下，返回落地路径。"""
    target = root / archive_name(task)
    if target.is_file():
        _log(f"{task}：压缩包已存在，跳过下载（{target.stat().st_size / 2**30:.2f} GiB）")
        return target

    executable = shutil.which("hf")
    if executable is None:
        raise FetchError("找不到 hf 命令行工具；确认 uv 环境已同步后再跑本脚本")

    _log(f"{task}：开始下载 {archive_name(task)}")
    command = [
        executable,
        "download",
        HF_REPO_ID,
        archive_name(task),
        "--repo-type",
        "dataset",
        "--local-dir",
        str(root),
    ]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise FetchError(f"{task}：hf download 返回非零退出码 {completed.returncode}")
    if not target.is_file():
        raise FetchError(f"{task}：下载结束但没有见到 {target}")
    _log(f"{task}：下载完成（{target.stat().st_size / 2**30:.2f} GiB）")
    return target


def extract_archive(task: str, root: Path) -> Path:
    """解压 tar.xz，返回解出的 h5 路径。

    优先用外部 ``tar`` 配合多线程 ``xz -T0``（解压 40 GiB 级文件时单线程 xz 是
    主要瓶颈）；外部命令不可用或失败时退回 Python 的 ``tarfile``。
    """
    archive = root / archive_name(task)
    target = root / h5_name(task)
    if not archive.is_file():
        raise FetchError(f"{task}：压缩包不存在，无法解压：{archive}")

    _log(f"{task}：开始解压 {archive.name}")
    tar_executable = shutil.which("tar")
    extracted = False
    if tar_executable is not None:
        command = [
            tar_executable,
            "--use-compress-program",
            "xz -T0 -d",
            "-xf",
            str(archive),
            "-C",
            str(root),
        ]
        completed = subprocess.run(command, check=False)
        extracted = completed.returncode == 0
        if not extracted:
            _log(f"{task}：外部 tar 解压失败（退出码 {completed.returncode}），退回 Python tarfile")

    if not extracted:
        with tarfile.open(archive, "r:xz") as handle:
            handle.extractall(root)

    if not target.is_file():
        raise FetchError(f"{task}：解压结束但没有见到 {target}")
    _log(f"{task}：解压完成（{target.stat().st_size / 2**30:.2f} GiB）")
    return target


def fetch_task(task: str, root: Path, keep_archive: bool) -> dict[str, object]:
    """补齐单个任务，返回该任务的处理结果摘要。"""
    target = root / h5_name(task)
    if target.is_file():
        try:
            count = verify_h5(target)
        except FetchError as exc:
            _log(f"{task}：已存在的 h5 校验不通过（{exc}），将重新下载解压")
        else:
            _log(f"{task}：已存在且校验通过（{count} 个 episode），跳过")
            return {"task": task, "status": "skipped", "episodes": count}

    download_archive(task, root)
    extract_archive(task, root)
    count = verify_h5(target)
    _log(f"{task}：校验通过（{count} 个 episode）")

    if not keep_archive:
        archive = root / archive_name(task)
        archive.unlink(missing_ok=True)
        _log(f"{task}：已删除压缩包以回收磁盘")

    return {"task": task, "status": "fetched", "episodes": count}


def fetch_reference_h5(
    root: Path | str = DEFAULT_ROOT,
    tasks: Sequence[str] = ALL_TASKS,
    keep_archive: bool = True,
) -> list[dict[str, object]]:
    """按任务清单逐个补齐参考 h5，返回逐任务结果。"""
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    unknown = [task for task in tasks if task not in ALL_TASKS]
    if unknown:
        raise FetchError(f"无法识别的任务名：{', '.join(unknown)}")

    results: list[dict[str, object]] = []
    for index, task in enumerate(tasks, start=1):
        _log(f"===== [{index}/{len(tasks)}] {task} =====")
        results.append(fetch_task(task, root, keep_archive))

    fetched = sum(1 for item in results if item["status"] == "fetched")
    skipped = len(results) - fetched
    _log(f"全部完成：新补齐 {fetched} 个任务，跳过 {skipped} 个已有任务")
    return results


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从 HuggingFace 补齐官方参考 h5，凑齐到 16 个任务",
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help="本机参考数据目录（默认 %(default)s）",
    )
    parser.add_argument(
        "--tasks",
        default="all",
        help="要补齐的任务，逗号分隔；all 表示全部 16 个（默认 %(default)s）",
    )
    parser.add_argument(
        "--keep-archive",
        action="store_true",
        default=True,
        help="解压后保留 .tar.xz（默认保留，与已有 4 个任务的现状一致）",
    )
    parser.add_argument(
        "--drop-archive",
        dest="keep_archive",
        action="store_false",
        help="解压并校验通过后删除 .tar.xz 以回收磁盘",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _args(argv)
    tasks = (
        ALL_TASKS
        if namespace.tasks.strip().lower() == "all"
        else tuple(item.strip() for item in namespace.tasks.split(",") if item.strip())
    )
    try:
        fetch_reference_h5(
            root=namespace.root,
            tasks=tasks,
            keep_archive=namespace.keep_archive,
        )
    except FetchError as exc:
        print(f"[fetch] 失败：{exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
