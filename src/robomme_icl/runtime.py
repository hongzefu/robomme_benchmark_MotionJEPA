"""在导入仿真库前配置仓库内缓存与固定计算线程。"""

import os
from pathlib import Path


def repo_root():
    """项目源码安装时解析根目录，不借用其他工作副本。"""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "src" / "robomme"
        ).is_dir():
            return candidate
    raise RuntimeError("无法定位同时包含 robomme 与 robomme_icl 的仓库根目录")


def configure_runtime():
    """对本进程固定线程；所有运行缓存均落在当前仓库。"""
    if os.environ.get("CUDA_VISIBLE_DEVICES") is not None:
        raise ValueError(
            "固定 GPU 绑定使用物理序号；请清除 CUDA_VISIBLE_DEVICES，并通过 prepare --gpus 选择设备"
        )
    root = repo_root()
    paths = {
        "UV_CACHE_DIR": "uv",
        "XDG_CACHE_HOME": "xdg",
        "HF_HOME": "huggingface",
        "MS_ASSET_DIR": "maniskill",
        "MPLCONFIGDIR": "matplotlib",
    }
    for key, folder in paths.items():
        path = root / ".cache" / folder
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[key] = "1"
    os.environ["PYTHONUNBUFFERED"] = "1"
