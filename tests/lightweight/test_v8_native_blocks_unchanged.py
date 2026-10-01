#!/usr/bin/env python3
"""v8 轻量回归：16 个环境的 ``native_blocks()`` 相对 BASE（a0d5c1d7，v7 取值）的变化范围（1001 方案 §2.1、R2／R8）。

* 9 个不改环境（BinFill、VideoUnmaskSwap、ButtonUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、
  VideoRepick、MoveCube、InsertPeg）：``(decision, native)`` 规范化 JSON 的 sha256 与 BASE 逐字节相同；
* 7 个改值环境（PickXtimes、SwingXtimes、StopCube、VideoUnmask、ButtonUnmask、RouteStick、PatternLock）：
  剥掉新值键（``_strip_xhard``）后的 ``(decision, native)`` 与 BASE 逐字节相同，新值子树按表 1 取值（逐档值由
  ``test_v7_tier_values.py`` 核对，这里只核「哪些档有新值子树」）；
* 16 个环境全部可导入、``configs`` 可解析、``_resolve_sampling_config(cls, None)`` 通过守卫。
  ⚠ 真正实例化（``gym.make`` + reset）需要 sapien／Vulkan 渲染，不在本 CPU 测试内；此处以「可导入且 configs
  与采样配置可解析」代替，真实实例化由合并后主会话的 GPU 闸门（XHARD0_RESET_PARITY 等）覆盖。

期望摘要是在 BASE（a0d5c1d79c607e6984deb269aa46aaa99af717ae）代码上用本文件同一 ``_digest`` 算出后写死的。

    uv run --no-sync python -m pytest tests/lightweight/test_v8_native_blocks_unchanged.py -q
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme_hard.robomme_env.utils.sampling_config import NEWVALUE_KEYS, _strip_xhard  # noqa: E402

#: BASE 上 9 个不改环境 ``[decision, native]`` 全量的 sha256
BASE_FULL_DIGEST = {
    "BinFill": "b367d532bdeaa94fa19ad5f7452c72fbe3e487706bc07ddf9cde20a2c2347f00",
    "VideoUnmaskSwap": "8f2835ac7a9c3d66bf91bacef422e6a0e0c4dbba3ffaaae9b4d0df69f7a12f24",
    "ButtonUnmaskSwap": "357b5e8cd8064a56d0ed28d839eaee8005a2f1bb1abe79057fcb50cc6c30beb3",
    "VideoPlaceButton": "fce7272f1a90417ae3d580cb4e4b0610a2c314ff4e58554dc55bc4a76831a43d",
    "VideoPlaceOrder": "e970fbd312eb61ee5150c6575bf4702a16a439118bd963e31ed34d465eafa081",
    "PickHighlight": "c771e0a605841d1953563a6aac59a795919bf09ea8ffd52ad913638b2ac8fbff",
    "VideoRepick": "49d60efefdb353a04a4c74503f74bb2eee0ffe459001cb8bd42160df193aa1ef",
    "MoveCube": "0bb52cce5eaf011d32b51512608564f5b004bba7d5e13f5bf9705c52fda2ab51",
    "InsertPeg": "d74d74381b4362d801a89209c84874a9d008bdd94e9ebe3874785ef020db7856",
}

#: BASE 上 7 个改值环境 ``[_strip_xhard(decision), native]`` 的 sha256
BASE_STRIPPED_DIGEST = {
    "PickXtimes": "dd86248d9f502496b37dc6a35e6eed471db1f711dece146a23b43791c5673823",
    "SwingXtimes": "76d41f008b97ee8aa29db6f1ae32de4ab79d47e37573533e0147025fb8643145",
    "StopCube": "f32aa6af25a80e2b08e3eee00955911f6ff19b9bbba9a9d5508e547e50d2228b",
    "VideoUnmask": "5e3493eb56fc4a938aa1adecc687f0a8200cab695b96a03f46d5ac097831f204",
    "ButtonUnmask": "bd23f8f5366d93c5ad8d038393cfeff5a55dfbc2885fdbf0f76fd9ad42d0dcf5",
    "RouteStick": "4cc33fada54b3eb8dc2f04c0bba52ed2ea59c2539a240e26d6522e8e601ec04a",
    "PatternLock": "5ab5d9954b0f7ba717fc96cf79e54a265872bcf7df3e93a1689c3d86980e49e7",
}

#: 改值环境 decision 顶层的新值子树（v8：只有 SwingXtimes、StopCube 多 xhard5）
TOP_LEVEL_TIERS = {
    "PickXtimes": {"xhard1", "xhard2", "xhard3", "xhard4"},
    "SwingXtimes": {"xhard1", "xhard2", "xhard3", "xhard4", "xhard5"},
    "StopCube": {"xhard1", "xhard2", "xhard3", "xhard4", "xhard5"},
    "VideoUnmask": {"xhard1", "xhard2", "xhard3", "xhard4"},
    "ButtonUnmask": {"xhard1", "xhard2", "xhard3", "xhard4"},
    "RouteStick": {"xhard1", "xhard2", "xhard3", "xhard4"},
    "PatternLock": {"xhard1", "xhard2", "xhard3", "xhard4"},
}

ALL_TASKS = (*BASE_FULL_DIGEST, *BASE_STRIPPED_DIGEST)


def _module(task):
    return importlib.import_module(f"robomme_hard.robomme_env.{task}")


def _blocks(task):
    module = _module(task)
    return module.native_blocks(getattr(module, task))


def _digest(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _has_key(node, key) -> bool:
    if isinstance(node, dict):
        return key in node or any(_has_key(value, key) for value in node.values())
    if isinstance(node, list):
        return any(_has_key(item, key) for item in node)
    return False


@pytest.mark.parametrize("task", list(BASE_FULL_DIGEST))
def test_unchanged_env_native_blocks_byte_identical(task) -> None:
    decision, native = _blocks(task)
    assert _digest([decision, native]) == BASE_FULL_DIGEST[task]
    # R8：不改环境完全不感知 xhard5
    assert not _has_key(decision, "xhard5")


@pytest.mark.parametrize("task", list(BASE_STRIPPED_DIGEST))
def test_changed_env_stripped_byte_identical(task) -> None:
    decision, native = _blocks(task)
    assert _digest([_strip_xhard(decision), native]) == BASE_STRIPPED_DIGEST[task]
    assert {key for key in decision if key in NEWVALUE_KEYS} == TOP_LEVEL_TIERS[task]
    if "xhard5" not in TOP_LEVEL_TIERS[task]:
        assert not _has_key(decision, "xhard5"), task


@pytest.mark.parametrize("task", ALL_TASKS)
def test_all_16_envs_importable_and_configs_resolve(task) -> None:
    """可导入、configs 可解析、默认采样配置通过守卫（真实实例化需 GPU，见模块说明）。"""
    module = _module(task)
    cls = getattr(module, task)
    configs = cls.configs
    assert isinstance(configs, dict) and {"easy", "medium", "hard"} <= set(configs)
    json.dumps(configs, sort_keys=True, default=str)
    resolved = module._resolve_sampling_config(cls, None)
    assert isinstance(resolved, dict) and "decision" in resolved


def test_summary_line(capsys) -> None:
    unchanged_bad = [t for t in BASE_FULL_DIGEST if _digest(list(_blocks(t))) != BASE_FULL_DIGEST[t]]
    changed_bad = [t for t in BASE_STRIPPED_DIGEST
                   if _digest([_strip_xhard(_blocks(t)[0]), _blocks(t)[1]]) != BASE_STRIPPED_DIGEST[t]]
    ok = not unchanged_bad and not changed_bad
    with capsys.disabled():
        print(f"\nV8_NATIVE_BLOCKS_UNCHANGED={'PASS' if ok else 'FAIL'} unchanged={len(BASE_FULL_DIGEST)} "
              f"changed_stripped={len(BASE_STRIPPED_DIGEST)} bad={unchanged_bad + changed_bad}")
    assert ok
    assert len(ALL_TASKS) == 16
