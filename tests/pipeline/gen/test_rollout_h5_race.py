"""run_batch 回读 h5 与搬运线程的竞态（2026-10-04 GL 对拍首跑实测：Mover 在 run_batch 列出 h5 之后、
打开之前按 match 删掉了文件，h5_facts 抛 FileNotFoundError 使整批生成以 runner_exit=1 退出）。

契约：文件在列目录与打开之间消失，与「列目录时已不在」同等处理——该局 h5 记 None、不回读事实、整批不崩；
文件仍在时照常回读事实。

本文件先钉住 h5_facts 的两种基本行为；经真实 run_batch 驱动竞态的贯通用例，待生成测试块的 FakeRunner（tests/pipeline/gen/gen_world.py）合入后补。"""
from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from tests._support.loaders import load_script


@pytest.fixture
def rollout():
    return load_script("injection-dev/_rollout.py")


def _write_h5(path: Path, steps: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        ep = f.create_group("episode_0")
        for i in range(steps):
            g = ep.create_group(f"timestep_{i}")
            g.create_dataset("info/is_video_demo", data=np.bool_(i == 0))


def test_h5_facts_missing_file_raises(tmp_path, rollout):
    with pytest.raises(FileNotFoundError):
        rollout.h5_facts(tmp_path / "gone.h5")


def test_h5_facts_reads_exec_steps(tmp_path, rollout):
    p = tmp_path / "a.h5"
    _write_h5(p, steps=5)
    facts = rollout.h5_facts(p)
    assert facts["frames"] == 5 and facts["exec_steps"] == 4 and facts["bytes"] == p.stat().st_size
