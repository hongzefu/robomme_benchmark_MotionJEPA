#!/usr/bin/env python3
"""v8 轻量回归：16 个环境的 ``native_blocks()`` 相对 BASE（a0d5c1d7，v7 取值）的变化范围（1001 方案 §2.1、R2／R8）。

* 8 个不改环境（BinFill、VideoUnmaskSwap、ButtonUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、
  VideoRepick、InsertPeg）：``(decision, native)`` 规范化 JSON 的 sha256 与 BASE 逐字节相同；
* MoveCube（V9，1002 计划 R2「只许 xhard4.region 子树变化」）：剥掉所有 ``xhard4`` 下的 ``region`` 子树
  （``_strip_xhard4_region``，两块都剥；实测只出现在 decision 的 demo_layout／execution_layout 两处，native 无）
  后的 sha256 与 V9 改动前（30f36e44，V8 取值）用同一函数算出的值相同，剥出的 region 等于 V9 值；
* 7 个改值环境（PickXtimes、SwingXtimes、StopCube、VideoUnmask、ButtonUnmask、RouteStick、PatternLock）：
  剥掉新值键（``_strip_xhard``）后的 ``(decision, native)`` 与 BASE 逐字节相同，新值子树按表 1 取值（逐档值由
  ``test_v7_tier_values.py`` 核对，这里只核「哪些档有新值子树」）；
* 16 个环境全部可导入、``configs`` 可解析、``_resolve_sampling_config(cls, None)`` 通过守卫。
  ⚠ 真正实例化（``gym.make`` + reset）需要 sapien／Vulkan 渲染，不在本 CPU 测试内；此处以「可导入且 configs
  与采样配置可解析」代替，真实实例化由合并后主会话的 GPU 闸门（XHARD0_RESET_PARITY 等）覆盖。

期望摘要是在 BASE（a0d5c1d79c607e6984deb269aa46aaa99af717ae）代码上用本文件同一 ``_digest`` 算出后写死的；
``MOVECUBE_STRIPPED_DIGEST`` 是在 30f36e449ad1f05146c2006009bdf1520715cacb 的 MoveCube.py 上用同一剥离函数算出的
（该版的全量摘要即原 ``BASE_FULL_DIGEST["MoveCube"]`` 0bb52cce…ab51，算时已核对一致）。

    uv run --no-sync python -m pytest tests/lightweight/test_v8_native_blocks_unchanged.py -q
"""

from __future__ import annotations

import copy
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

#: BASE 上 8 个不改环境 ``[decision, native]`` 全量的 sha256（MoveCube V9 起改走下面的剥离比对）
BASE_FULL_DIGEST = {
    "BinFill": "b367d532bdeaa94fa19ad5f7452c72fbe3e487706bc07ddf9cde20a2c2347f00",
    "VideoUnmaskSwap": "8f2835ac7a9c3d66bf91bacef422e6a0e0c4dbba3ffaaae9b4d0df69f7a12f24",
    "ButtonUnmaskSwap": "357b5e8cd8064a56d0ed28d839eaee8005a2f1bb1abe79057fcb50cc6c30beb3",
    "VideoPlaceButton": "fce7272f1a90417ae3d580cb4e4b0610a2c314ff4e58554dc55bc4a76831a43d",
    "VideoPlaceOrder": "e970fbd312eb61ee5150c6575bf4702a16a439118bd963e31ed34d465eafa081",
    "PickHighlight": "c771e0a605841d1953563a6aac59a795919bf09ea8ffd52ad913638b2ac8fbff",
    "VideoRepick": "49d60efefdb353a04a4c74503f74bb2eee0ffe459001cb8bd42160df193aa1ef",
    "InsertPeg": "d74d74381b4362d801a89209c84874a9d008bdd94e9ebe3874785ef020db7856",
}

#: MoveCube：30f36e44（V8 取值）上 ``[_strip_xhard4_region(decision), _strip_xhard4_region(native)]`` 的 sha256
MOVECUBE_STRIPPED_DIGEST = "b76f47da866b4e4b725212532364aabb452b5e6cff9f3d291f20650cd58449f9"
#: V9 的 xhard4.region（r_in／r_out／base_dist 改 V9，其余键与 V8 相同）
MOVECUBE_V9_REGION = {"center": [-0.06, 0.0], "r_in": 0.24, "r_out": 0.42, "base_dist": [0.31, 0.80],
                      "push_len_max": 0.30, "peg_gap": 0.04, "goal_peg_gap": 0.02,
                      "peg_max_trials": 128, "goal_max_trials": 256, "cube_max_trials": 4096}
#: MoveCube 中 xhard4.region 出现的全部位置（decision／native 两块逐层核实）
MOVECUBE_REGION_PATHS = {("decision", "demo_layout", "xhard4"), ("decision", "execution_layout", "xhard4")}

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

ALL_TASKS = (*BASE_FULL_DIGEST, "MoveCube", *BASE_STRIPPED_DIGEST)


def _module(task):
    return importlib.import_module(f"robomme_hard.robomme_env.{task}")


def _blocks(task):
    module = _module(task)
    return module.native_blocks(getattr(module, task))


def _digest(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _strip_xhard4_region(node):
    """深拷贝后删掉任意深度上 ``xhard4`` 字典里的 ``region`` 键，其余原样保留。"""
    node = copy.deepcopy(node)

    def rec(x):
        if isinstance(x, dict):
            for key, value in x.items():
                if key == "xhard4" and isinstance(value, dict):
                    value.pop("region", None)
                rec(value)
        elif isinstance(x, list):
            for item in x:
                rec(item)

    rec(node)
    return node


def _xhard4_region_paths(node, path):
    """返回 ``xhard4`` 下带 ``region`` 键的所有位置（元组路径）。"""
    out = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "xhard4" and isinstance(value, dict) and "region" in value:
                out.add((*path, key))
            out |= _xhard4_region_paths(value, (*path, key))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out |= _xhard4_region_paths(item, (*path, i))
    return out


def _movecube_stripped_digest(decision, native) -> str:
    return _digest([_strip_xhard4_region(decision), _strip_xhard4_region(native)])


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


def test_movecube_only_xhard4_region_changed() -> None:
    """V9 R2：MoveCube 只许 xhard4.region 子树变化，且变化后的值就是 V9。"""
    decision, native = _blocks("MoveCube")
    # region 出现位置全部核实：只在 decision 的两段 layout 下，native 里没有
    paths = _xhard4_region_paths(decision, ("decision",)) | _xhard4_region_paths(native, ("native",))
    assert paths == MOVECUBE_REGION_PATHS
    assert _movecube_stripped_digest(decision, native) == MOVECUBE_STRIPPED_DIGEST
    for seg in ("demo_layout", "execution_layout"):
        assert decision[seg]["xhard4"]["region"] == MOVECUBE_V9_REGION
    assert not _has_key(decision, "xhard5")


def test_movecube_strip_is_effective() -> None:
    """负例：剥离确实生效——不剥、或只剥一段时摘要都不等于期望值。"""
    decision, native = _blocks("MoveCube")
    assert _digest([decision, native]) != MOVECUBE_STRIPPED_DIGEST
    half = copy.deepcopy(decision)
    del half["demo_layout"]["xhard4"]["region"]          # 漏剥 execution_layout
    assert _digest([half, native]) != MOVECUBE_STRIPPED_DIGEST
    # 剥后确实不剩 region，且原对象未被就地修改
    assert _xhard4_region_paths(_strip_xhard4_region(decision), ("decision",)) == set()
    assert "region" in decision["demo_layout"]["xhard4"]


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
    movecube_bad = [] if _movecube_stripped_digest(*_blocks("MoveCube")) == MOVECUBE_STRIPPED_DIGEST else ["MoveCube"]
    ok = not unchanged_bad and not changed_bad and not movecube_bad
    with capsys.disabled():
        print(f"\nV8_NATIVE_BLOCKS_UNCHANGED={'PASS' if ok else 'FAIL'} unchanged={len(BASE_FULL_DIGEST)} "
              f"movecube_region_only=1 changed_stripped={len(BASE_STRIPPED_DIGEST)} "
              f"bad={unchanged_bad + movecube_bad + changed_bad}")
    assert ok
    assert len(ALL_TASKS) == 16
