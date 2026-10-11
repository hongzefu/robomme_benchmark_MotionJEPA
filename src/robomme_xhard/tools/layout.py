"""输出根的产物发现与 HDF5 读取（summarize 与 compare_video 共用，只读）。

输出根布局::

    <root>/mother/...      母档（按 R9 用当前代码同 seed 重新生成）
    <root>/xhard12/...     各派生档；其下沿用生成器布局 hdf5_files/ 与 videos/

H5 文件名沿用生成器 ``_h5_path`` 与 RecordWrapper 约定：``<Task>_ep<E>_seed<S>.h5``。
RecordWrapper 只在 episode 成功时写 ``episode_<E>`` 组，失败时删组、只留
``videos/FAILED_<Task>_ep<E>_seed<S>[_FailRecover…]_<后缀>.mp4``。

HDF5 字段路径（2026-10-11 只读核对官方 data_0226 与 RecordWrapper.close）：
- ``episode_<E>/setup/difficulty``（utf-8 字符串）、``episode_<E>/setup/seed``（int64）
- ``episode_<E>/timestep_<i>/info/is_video_demo``（bool）
- ``episode_<E>/timestep_<i>/info/is_completed``（bool，末帧应为真）
- ``episode_<E>/timestep_<i>/obs/front_rgb``（256×256×3 uint8）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..configs import DIFFICULTIES, SOURCE_DIFFICULTY, TASK_ORDER

MOTHER = "mother"
LEVELS: tuple[str, ...] = (MOTHER,) + DIFFICULTIES

# stride-16 motion 窗口：每窗 33 帧
WINDOW_FRAMES = 33
WINDOW_STRIDE = 16

H5_NAME_RE = re.compile(r"^(?P<task>[A-Za-z]+?)(?:XHard)?_ep(?P<episode>\d+)_seed(?P<seed>\d+)\.h5$")
VIDEO_NAME_RE = re.compile(
    r"^(?P<failed>FAILED_)?(?P<task>[A-Za-z]+?)(?:XHard)?_ep(?P<episode>\d+)_seed(?P<seed>\d+)"
    r"(?P<recover>_FailRecover(?:XY|Z)?)?_(?P<suffix>.+)\.mp4$"
)


def windows(length: int) -> int:
    """w(L) = max(0, floor((L - 33) / 16) + 1)。"""
    if length < WINDOW_FRAMES:
        return 0
    return (length - WINDOW_FRAMES) // WINDOW_STRIDE + 1


def task_rank(task: str) -> int:
    try:
        return TASK_ORDER.index(task)
    except ValueError:
        return len(TASK_ORDER)


def level_rank(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else len(LEVELS)


def expected_difficulty(task: str, level: str) -> str:
    """该档 H5 里 setup/difficulty 应等于的值：母档为来源难度，派生档为目录名。"""
    return SOURCE_DIFFICULTY.get(task, "hard") if level == MOTHER else level


@dataclass
class Artifact:
    task: str
    seed: int
    level: str
    episode: int | None = None
    h5: Path | None = None
    video: Path | None = None
    failed_video: Path | None = None
    extra: dict = field(default_factory=dict)


def _ignored(name: str) -> bool:
    # 无物体视频只是录像器附带的副产物，不参与比较
    return name.startswith("success_NO_OBJECT_") or name.startswith("FAILED_NO_OBJECT_")


def scan(root: Path) -> dict[tuple[str, int, str], Artifact]:
    """扫描输出根，返回 {(task, seed, level): Artifact}；只认 LEVELS 里的一级子目录。"""
    root = Path(root)
    found: dict[tuple[str, int, str], Artifact] = {}
    for level in LEVELS:
        level_dir = root / level
        if not level_dir.is_dir():
            continue
        for path in sorted(level_dir.rglob("*.h5")):
            m = H5_NAME_RE.match(path.name)
            if not m:
                continue
            key = (m["task"], int(m["seed"]), level)
            art = found.setdefault(key, Artifact(task=key[0], seed=key[1], level=level))
            art.episode = int(m["episode"])
            art.h5 = path
        for path in sorted(level_dir.rglob("*.mp4")):
            if _ignored(path.name):
                continue
            m = VIDEO_NAME_RE.match(path.name)
            if not m:
                continue
            key = (m["task"], int(m["seed"]), level)
            art = found.setdefault(key, Artifact(task=key[0], seed=key[1], level=level))
            if art.episode is None:
                art.episode = int(m["episode"])
            if m["failed"]:
                art.failed_video = path
            else:
                art.video = path
    return found


def _decode(value):
    if hasattr(value, "item") and not isinstance(value, (bytes, str)):
        value = value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _timestep_keys(group) -> list[str]:
    keys = [k for k in group.keys() if k.startswith("timestep_")]
    return sorted(keys, key=lambda k: int(k.split("_", 1)[1]))


def episode_group(handle, episode: int | None = None):
    """取 H5 里的 episode 组；优先 episode_<E>，否则唯一的 episode_* 组。"""
    if episode is not None and f"episode_{episode}" in handle:
        return handle[f"episode_{episode}"]
    groups = [k for k in handle.keys() if k.startswith("episode_")]
    if len(groups) == 1:
        return handle[groups[0]]
    return None


def read_h5_summary(path: Path, episode: int | None = None) -> dict:
    """读一个 H5 的难度标签、seed 与分段 timestep 数（不读图像）。"""
    import h5py

    out = {
        "has_episode": False,
        "difficulty": None,
        "h5_seed": None,
        "demo_timesteps": 0,
        "exec_timesteps": 0,
        "timesteps": 0,
        "last_completed": None,
    }
    with h5py.File(path, "r") as handle:
        group = episode_group(handle, episode)
        if group is None:
            return out
        out["has_episode"] = True
        setup = group.get("setup")
        if setup is not None:
            if "difficulty" in setup:
                out["difficulty"] = _decode(setup["difficulty"][()])
            if "seed" in setup:
                out["h5_seed"] = int(_decode(setup["seed"][()]))
        keys = _timestep_keys(group)
        demo = 0
        for key in keys:
            info = group[key].get("info")
            if info is not None and "is_video_demo" in info and bool(info["is_video_demo"][()]):
                demo += 1
        out["demo_timesteps"] = demo
        out["exec_timesteps"] = len(keys) - demo
        out["timesteps"] = len(keys)
        if keys:
            info = group[keys[-1]].get("info")
            if info is not None and "is_completed" in info:
                out["last_completed"] = bool(info["is_completed"][()])
    return out
