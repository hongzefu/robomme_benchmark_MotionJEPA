"""第一阶段 ①定规则：对 16 任务读 ``native_blocks``，合成 ``sampling_config`` dict（不创建环境、不抽随机数）。"""

from __future__ import annotations

import _common  # noqa: F401  路径设置

from train_split_config import extract_task  # noqa: E402

DEFAULT_PKG = "robomme_hard"
DEFAULT_RELEASE = "newtask-v6"


def build_sampling(tasks: list[str], pkg: str = DEFAULT_PKG, release: str = DEFAULT_RELEASE) -> dict:
    """返回 ``{"tasks": {<task>: {"decision": …, "native": …}}}``；未接口化的任务直接报错。"""
    out = {}
    for task in tasks:
        block = extract_task(task, release=release, pkg=pkg)
        if block is None:
            raise ValueError(f"{pkg}.robomme_env.{task} 没有 native_blocks，无法定规则")
        out[task] = block
    return {"tasks": out}
