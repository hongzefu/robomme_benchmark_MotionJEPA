"""旧官方录制器的公共小工具：按文件路径加载 recorder.py、传输日志写入、清单读取。

文件名刻意带 ``_v75_`` 前缀：本目录会追加到旧官方客户端的 PYTHONPATH 末尾，不能与官方
``examples/robomme`` 下的 ``utils``、``env_runner`` 等模块重名。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

OBS_DIR = Path(__file__).resolve().parent
RECORDER_PATH = OBS_DIR.parent / "recorder.py"


def load_recorder():
    """按路径加载 scripts/eval-official/recorder.py（模块名 v75_recorder，不改 sys.path）。"""
    name = "v75_recorder"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, RECORDER_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=repr)


def payload_sha(msg: Any) -> tuple[str, int, str]:
    """websocket 消息的 (帧类型, 字节长度, sha256)；文本按 UTF-8 编码后计算。"""
    if isinstance(msg, str):
        b = msg.encode("utf-8")
        kind = "text"
    else:
        b = bytes(msg)
        kind = "binary"
    return kind, len(b), hashlib.sha256(b).hexdigest()


class JsonlLog:
    """线程安全的追加式 jsonl（每行立即 flush）。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, rec: dict) -> None:
        with self._lock:
            self._fh.write(dumps(rec) + "\n")
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            self._fh.close()


def rec_root() -> Path:
    """录制根目录（环境变量 REC_ROOT，必填）。"""
    r = os.environ.get("REC_ROOT")
    if not r:
        raise RuntimeError("未设 REC_ROOT")
    p = Path(r)
    p.mkdir(parents=True, exist_ok=True)
    return p


def episode_dir(root: Path, task: str, source_episode: int, seed: int) -> Path:
    """逐局目录 <task>_<source_episode>_<seed>；同名已存在（续评重跑 error 局）则加 .attemptN。"""
    base = root / f"{task}_{int(source_episode)}_{int(seed)}"
    if not base.exists():
        return base
    k = 2
    while (root / f"{base.name}.attempt{k}").exists():
        k += 1
    return root / f"{base.name}.attempt{k}"


def now() -> float:
    return time.time()


class PostImportHooks:
    """模块首次被导入、执行完毕后立即调用钩子（不提前导入任何模块，保持官方代码的导入顺序不变）。"""

    def __init__(self, hooks: dict):
        self.hooks = dict(hooks)  # 模块名 → fn(module)

    def install(self) -> None:
        for name in list(self.hooks):
            if name in sys.modules:  # 已导入的直接挂
                self.hooks.pop(name)(sys.modules[name])
        if self.hooks:
            sys.meta_path.insert(0, self)

    def find_spec(self, name, path, target=None):
        if name not in self.hooks:
            return None
        spec = None
        for f in sys.meta_path:
            if f is self or not hasattr(f, "find_spec"):
                continue
            spec = f.find_spec(name, path, target)
            if spec is not None:
                break
        if spec is None or spec.loader is None:
            return None
        hook = self.hooks.pop(name)
        orig_exec = spec.loader.exec_module

        def exec_module(module, _orig=orig_exec, _hook=hook):
            _orig(module)
            _hook(module)

        spec.loader.exec_module = exec_module
        return spec


def parse_flag(argv: list[str], names: tuple[str, ...]) -> str | None:
    """从命令行取 ``--x=v`` 或 ``--x v`` 形式的值（tyro 与 argparse 两种写法都认）。"""
    for i, a in enumerate(argv):
        for n in names:
            if a == n and i + 1 < len(argv):
                return argv[i + 1]
            if a.startswith(n + "="):
                return a[len(n) + 1:]
    return None


def manifest_seeds(path: str | None) -> dict:
    """清单 (task, source_episode) → seed。"""
    out = {}
    if path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                out[(r["task"], int(r["source_episode"]))] = int(r["seed"])
    return out
