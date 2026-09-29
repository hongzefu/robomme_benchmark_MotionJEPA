#!/usr/bin/env python3
"""轻量测试：V7 共用布局白名单（0928 方案第二部分 §1.3、R10）。

* ``episode_spec.classify_path`` 的匹配语义：按段匹配，``*`` 恰好匹配一段；``[:n]`` 后缀＝去掉后缀精确匹配
  （列表取前缀的语义在 SpecRecorder 派生时体现）；恰好命中一个模式才合法，零个或多个都抛 ``EpisodeSpecError``；
* 包内 ``env_metadata/test-hard/layout_whitelist.json``：13 个梯度任务、每任务恰有 L／G／N 三表，
  不同类的模式之间不存在能同时命中的路径（互斥），只有 xhard4 的三个任务不在表内。

    uv run --no-sync python -m pytest tests/lightweight/test_v7_whitelist_semantics.py -q
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme_hard.env_record_wrapper import hard_specs as V  # noqa: E402
from robomme_hard.robomme_env.utils import episode_spec as es  # noqa: E402

WHITELIST = V.PACKAGED_SPECS_ROOT / "layout_whitelist.json"

LAYOUT = {
    "L": ["layout.button_xy", "layout.cubes.*", "actions.path_nodes[:n]"],
    "G": ["objects.num_repeats", "actions.swap_pairs.*"],
    "N": ["objects.target_numbers"],
}


# ── classify_path 语义 ──────────────────────────────────────────────────────
def test_精确匹配与星号恰好一段():
    assert es.classify_path(LAYOUT, "layout.button_xy") == ("L", "layout.button_xy")
    assert es.classify_path(LAYOUT, "layout.cubes.red_0") == ("L", "layout.cubes.*")
    assert es.classify_path(LAYOUT, "actions.swap_pairs.3") == ("G", "actions.swap_pairs.*")
    assert es.classify_path(LAYOUT, "objects.target_numbers") == ("N", "objects.target_numbers")
    # * 不跨段、也不匹配零段
    for path in ("layout.cubes.red_0.xy", "layout.cubes", "actions.swap_pairs"):
        with pytest.raises(es.EpisodeSpecError):
            es.classify_path(LAYOUT, path)


def test_前缀后缀只按去掉后缀后的路径精确匹配():
    assert es.classify_path(LAYOUT, "actions.path_nodes") == ("L", "actions.path_nodes[:n]")
    for path in ("actions.path_nodes.0", "actions.path_nodes[:n]", "actions.path"):
        with pytest.raises(es.EpisodeSpecError):
            es.classify_path(LAYOUT, path)


def test_未分类路径抛错():
    with pytest.raises(es.EpisodeSpecError, match="命中 0 个模式"):
        es.classify_path(LAYOUT, "objects.never_listed")
    with pytest.raises(es.EpisodeSpecError):
        es.classify_path({}, "layout.button_xy")


def test_多类同时命中抛错():
    clash = {"L": ["layout.cubes.*"], "G": ["layout.cubes.red_0"], "N": []}
    with pytest.raises(es.EpisodeSpecError, match="命中 2 个模式"):
        es.classify_path(clash, "layout.cubes.red_0")
    assert es.classify_path(clash, "layout.cubes.blue_0") == ("L", "layout.cubes.*")
    same_class = {"L": ["layout.a.*", "layout.*.b"], "G": [], "N": []}
    with pytest.raises(es.EpisodeSpecError):
        es.classify_path(same_class, "layout.a.b")  # 同类两个模式同时命中也算不唯一


# ── 包内白名单 ──────────────────────────────────────────────────────────────
def _can_overlap(p: str, q: str) -> bool:
    """两个模式是否存在同时命中的路径（按 classify_path 的语义判定）。"""
    suffix = es.PREFIX_SUFFIX
    if p.endswith(suffix) or q.endswith(suffix):
        exact_p = p[: -len(suffix)] if p.endswith(suffix) else None
        exact_q = q[: -len(suffix)] if q.endswith(suffix) else None
        if exact_p is not None and exact_q is not None:
            return exact_p == exact_q
        exact, other = (exact_p, q) if exact_p is not None else (exact_q, p)
        return es._segments_match(other, exact)
    a, b = p.split("."), q.split(".")
    return len(a) == len(b) and all(x == "*" or y == "*" or x == y for x, y in zip(a, b))


@pytest.fixture(scope="module")
def whitelist():
    return json.loads(WHITELIST.read_text(encoding="utf-8"))


def test_包内白名单覆盖13个梯度任务且三表齐全(whitelist):
    assert whitelist["schema"] == "layout-whitelist/1"
    tasks = whitelist["tasks"]
    expected = {t for t in V.ALL_TASKS if t not in V.XHARD4_ONLY}
    assert set(tasks) == expected and len(tasks) == 13
    for task, layout in tasks.items():
        assert set(layout) == {"L", "G", "N"}, task
        for cls in ("L", "G", "N"):
            assert isinstance(layout[cls], list), (task, cls)
            assert all(isinstance(p, str) and p for p in layout[cls]), (task, cls)
        assert layout["L"], f"{task} 没有 L 表：母布局无从共用"


def test_包内白名单不同类的模式互斥(whitelist):
    clashes = []
    for task, layout in whitelist["tasks"].items():
        for c1, c2 in itertools.combinations(("L", "G", "N"), 2):
            for p in layout[c1]:
                for q in layout[c2]:
                    if p == q or _can_overlap(p, q):
                        clashes.append((task, c1, p, c2, q))
        # 同类内也不许重复写同一模式
        for cls in ("L", "G", "N"):
            assert len(layout[cls]) == len(set(layout[cls])), (task, cls)
    assert clashes == []


def test_包内白名单的N表都有嵌套规则或属于外环段(whitelist):
    """N 表路径要么在 ``NEST_RULES`` 里有派生函数，要么是 Swap 两任务的外环容器（D-19，由派生脚本取母布局弧段）。"""
    for task, layout in whitelist["tasks"].items():
        for pattern in layout["N"]:
            if pattern in es.NEST_RULES:
                continue
            assert task in ("VideoUnmaskSwap", "ButtonUnmaskSwap") and pattern.startswith("objects.distractors.bins"), \
                (task, pattern)


def test_重叠判定自检():
    assert _can_overlap("layout.cubes.*", "layout.cubes.red_0")
    assert _can_overlap("layout.*.xy", "layout.cubes.*")
    assert not _can_overlap("layout.cubes.*", "layout.cubes.*.xy")
    assert _can_overlap("actions.path_nodes[:n]", "actions.*")
    assert not _can_overlap("actions.path_nodes[:n]", "actions.path_nodes.*")
