"""认证所绑定的源码、依赖和设备指纹，不包含时间与运行产物。"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess

from .paths import repository_root


_PACKAGES = (
    "mani-skill", "sapien", "torch", "numpy", "mplib", "h5py", "scipy",
    "gymnasium", "opencv-python", "trimesh", "transforms3d",
)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hash(root: Path) -> str:
    files = []
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError(f"运行源码不能通过符号链接引用其他存储：{path}")
        if path.is_file():
            files.append((path.relative_to(root).as_posix(), _file_hash(path)))
    return hashlib.sha256(json.dumps(files, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def runtime_fingerprint() -> dict:
    """只读取本仓库源码、当前环境包元数据和本机设备，不访问 NFS。"""
    root = repository_root()
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=uuid,name,driver_version", "--format=csv,noheader"],
        check=True, capture_output=True, text=True, timeout=10,
    )
    devices = sorted(line.strip() for line in result.stdout.splitlines() if line.strip())
    if not devices:
        raise RuntimeError("没有可认证的本机 GPU")
    return {
        "fingerprint_version": 1,
        "legacy_source_hash": _tree_hash(root / "src" / "robomme"),
        "icl_source_hash": _tree_hash(root / "src" / "robomme_icl"),
        "uv_lock_hash": _file_hash(root / "uv.lock"),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "machine": platform.machine(),
        "packages": {name: importlib.metadata.version(name) for name in _PACKAGES},
        "gpu_devices": devices,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "thread_environment": {name: os.environ.get(name) for name in (
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
        )},
    }


def source_commit() -> str:
    """Git HEAD 只作来源留档，后续报告提交不导致运行指纹失效。"""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository_root(), check=True,
        capture_output=True, text=True, timeout=5,
    ).stdout.strip()
