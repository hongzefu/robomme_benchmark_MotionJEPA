#!/usr/bin/env python3
"""轻量测试：v7 对照站点目录的选片与终态规则（不读 HDF5、不占 GPU）。

覆盖 scripts/injection-dev/site/v7_site_catalog.py：
- gen1 选片跳过 ``FAILED*``／``success_NO_OBJECT*``，按 seed 取唯一 mp4，多于或少于 1 个即报错；
- 同一身份取最后一个终态行，只有 error 行时返回 error 行；
- 媒体白名单同键同路径幂等、同 ID 不同路径报冲突。

    uv run --no-sync python -m pytest tests/lightweight/test_v7_site_catalog.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
_spec = importlib.util.spec_from_file_location(
    "v7_site_catalog", REPO_ROOT / "scripts" / "injection-dev" / "site" / "v7_site_catalog.py")
cat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cat)


def _episode(tmp_path: Path, names: list[str]) -> Path:
    ep = tmp_path / "BinFill_episode_1"
    (ep / "hdf5_files").mkdir(parents=True)
    (ep / "videos").mkdir()
    for name in names:
        (ep / "videos" / name).write_bytes(b"x")
    h5 = ep / "hdf5_files" / "BinFill_ep1_seed14400100.h5"
    h5.write_bytes(b"x")
    return h5


def test_pick_gen1_video_skips_failed_and_tail(tmp_path):
    h5 = _episode(tmp_path, ["FAILED_BinFill_ep1_seed14400100_a.mp4", "success_NO_OBJECT_BinFill_ep1_seed14400100_a.mp4",
                             "BinFill_ep1_seed14400100_xhard1_put.mp4"])
    assert cat.pick_gen1_video(h5, 14400100).name == "BinFill_ep1_seed14400100_xhard1_put.mp4"


def test_pick_gen1_video_requires_exactly_one(tmp_path):
    h5 = _episode(tmp_path, ["FAILED_BinFill_ep1_seed14400100_a.mp4"])
    with pytest.raises(ValueError):
        cat.pick_gen1_video(h5, 14400100)


def test_last_terminal_and_error_rows():
    final, errors = cat.last_terminal([{"status": "error"}, {"status": "fail", "steps": 1}, {"status": "success", "steps": 2}])
    assert final["status"] == "success" and len(errors) == 1
    final, errors = cat.last_terminal([{"status": "error"}] * 3)
    assert final is None and len(errors) == 3


def test_media_idempotent_and_conflict(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    media = cat.Media()
    assert media.add("k", a) == media.add("k", a)
    media.paths[cat.hashlib.sha256(b"z").hexdigest()[:24]] = str(a)
    with pytest.raises(ValueError):
        media.add("z", b)
