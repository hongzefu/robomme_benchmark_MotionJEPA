"""规格采样与静态检查的定向测试（NEW_VALUE_INJECTION_TEST_PLAN 第四节、第 5.7 节）。

最要紧的一条是计划第 4.1 节点名的陷阱：``check`` 必须按**完整合法类别补零**再算计数差，
否则「100 条全为同一个值」也会算出计数差 0 而被误判通过（在途实现曾有此反例）。
这里直接用一份全 True 的假规格把它钉死。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from tests._shared import injection_campaign as campaign  # noqa: E402
from tests._shared.injection_categories import legal_categories, observed_values  # noqa: E402
from tests._shared.injection_sampling import (  # noqa: E402
    COARSE_BINS,
    GROUP_SIZE,
    derive_rng,
    quota_counts,
    quota_series,
    stratify,
)
from tests._shared.injection_specs import GROUPS, seal  # noqa: E402

SAMPLING = json.loads((REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json").read_text())


# ── 配额 ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("classes", "expected"),
    [(2, [50, 50]), (3, [34, 33, 33]), (5, [20] * 5), (6, [17, 17, 17, 17, 16, 16]), (4, [25] * 4)],
)
def test_配额按类数平分且计数差不超过一(classes, expected):
    counts = quota_counts(classes)
    assert counts == expected
    assert sum(counts) == GROUP_SIZE
    assert max(counts) - min(counts) <= 1


def test_每一批十条也按同一比例分配():
    """实跑只取前 3 批 30 条，所以批内也必须均衡，不能只保证全局。"""
    series = quota_series([True, False], derive_rng(1, "a"))
    assert Counter(series) == {True: 50, False: 50}
    for batch in range(COARSE_BINS):
        chunk = Counter(series[batch * 10 : (batch + 1) * 10])
        assert chunk[True] == 5 and chunk[False] == 5


def test_三类值的前三十条也接近比例():
    series = quota_series([1, 2, 3], derive_rng(2, "b"))
    assert Counter(series) == {1: 34, 2: 33, 3: 33}
    head = Counter(series[:30])
    assert max(head.values()) - min(head.values()) <= 2


# ── 分层 ────────────────────────────────────────────────────────────────────
def test_分层每箱恰十条且每批覆盖全部十箱():
    stratum = stratify(-0.25, -0.15, derive_rng(3, "c"))
    assert Counter(stratum.bin_of) == {b: 10 for b in range(COARSE_BINS)}
    for batch in range(COARSE_BINS):
        assert len(set(stratum.bin_of[batch * 10 : (batch + 1) * 10])) == COARSE_BINS


def test_分层取值落在自己的细分层格里():
    stratum = stratify(0.0, 1.0, derive_rng(4, "d"))
    for episode in range(GROUP_SIZE):
        low, high = stratum.cell_bounds(episode)
        assert low <= stratum.values[episode] < high


def test_重采样留在同一个粗分箱内():
    """几何拒绝后的重采样粒度是粗箱——配额判据验的正是粗箱，所以判据不受影响。"""
    rng = derive_rng(5, "e")
    stratum = stratify(-0.05, 0.05, derive_rng(5, "f"))
    for episode in (0, 37, 99):
        low, high = stratum.coarse_bounds(episode)
        for _ in range(50):
            value = stratum.resample(episode, rng)
            assert low <= value < high


def test_不同变量用各自的排列不落在一条对角线上():
    a = stratify(0.0, 1.0, derive_rng(6, "x"))
    b = stratify(0.0, 1.0, derive_rng(6, "y"))
    assert a.bin_of != b.bin_of


def test_同一标识派生的随机流可复现():
    assert stratify(0.0, 1.0, derive_rng(7, "同")).values == stratify(0.0, 1.0, derive_rng(7, "同")).values


# ── 补零陷阱 ────────────────────────────────────────────────────────────────
def _fake_binfill_document(dynamic_values: list[bool]) -> dict:
    episodes = []
    for episode, dynamic in enumerate(dynamic_values):
        episodes.append(
            seal(
                {
                    "episode": episode,
                    "task": "BinFill",
                    "difficulty": "hard",
                    "layout": {"dynamic": dynamic},
                    "objects": {
                        "colors_present": ["red", "blue", "green"],
                        "initialize_color_order": ["blue", "red", "green"],
                        "target_pool": ["red", "blue"],
                        "spawn_total": 10,
                        "put_in_total": 3,
                        "spawn_count": {},
                        "target_count": {},
                    },
                    "actions": [],
                    "sampling_cells": {},
                }
            )
        )
    return {"episodes": episodes}


def _dynamic_spread(dynamic_values: list[bool]) -> tuple[int, dict]:
    """跑一遍配额检查，只取 dynamic 这一项的计数表与计数差。

    ⚠ 假文档里别的字段都是固定值，它们的计数差自然是 100，所以这里不能拿整体
    ``COVERAGE_QUOTA`` 的 PASS/FAIL 做断言——只看 dynamic 这一项。
    """
    verdicts = campaign.Verdicts()
    report = campaign._check_quota(
        {("BinFill", "hard"): _fake_binfill_document(dynamic_values)}, SAMPLING, verdicts
    )
    entry = report["BinFill/hard"]["independent"]["dynamic"]
    return entry["spread"], entry["counts"]


def test_全部为同一个值时配额判据必须失败():
    """⚠ 这就是第 4.1 节的反例：只数「实际出现过的类别」会算出计数差 0 并误判通过。"""
    spread, counts = _dynamic_spread([True] * GROUP_SIZE)
    assert len(counts) == 2, "合法类别只补出一个，说明没按约定表补零"
    assert spread == GROUP_SIZE, "100 条全为 True 却算出计数差 0，补零漏了"

    verdicts = campaign.Verdicts()
    campaign._check_quota({("BinFill", "hard"): _fake_binfill_document([True] * GROUP_SIZE)}, SAMPLING, verdicts)
    record = verdicts.records[-1]
    assert record["name"] == "COVERAGE_QUOTA" and record["status"] == "FAIL"
    assert any("dynamic" in item for item in record["detail"])


def test_五十比五十的_dynamic_计数差为零():
    spread, counts = _dynamic_spread([True] * 50 + [False] * 50)
    assert spread == 0
    assert sorted(counts.values()) == [50, 50]


def test_计数差按最大减最小算():
    """⚠ 「计数差不超过 1」是 max−min：两类值只有 50/50 才合格，51/49 的差已经是 2。

    三类值的达标形态才是 34/33/33（差 1）。这条把口径钉死，免得日后误以为
    「一条之差」指的是每个类别偏离均值一条。
    """
    assert _dynamic_spread([True] * 50 + [False] * 50)[0] == 0
    assert _dynamic_spread([True] * 51 + [False] * 49)[0] == 2
    assert _dynamic_spread([True] * 52 + [False] * 48)[0] == 4


# ── 合法类别表与观测字段对齐 ────────────────────────────────────────────────
@pytest.mark.parametrize(("task", "difficulty"), GROUPS)
def test_每组的合法类别表非空且独立类别都至少一个值(task, difficulty):
    categories = legal_categories(task, difficulty, SAMPLING)
    assert categories["independent"]
    for field, legal in categories["independent"].items():
        assert legal, f"{task}/{difficulty} 的 {field} 没有合法类别"


def test_排除组不在本轮的十一组里():
    assert ("VideoRepick", "hard") not in GROUPS
    assert len(GROUPS) == 11


# ── 判定行 ──────────────────────────────────────────────────────────────────
def test_判定行渲染成可解析的键值形式():
    verdicts = campaign.Verdicts()
    verdicts.add("DEMO", True, a=1, b="x")
    verdicts.add("DEMO2", False)
    verdicts.add("DEMO3", None)
    assert verdicts.lines[0] == "DEMO=PASS a=1 b=x"
    assert verdicts.lines[1] == "DEMO2=FAIL"
    assert verdicts.lines[2] == "DEMO3=NOT_RUN"
    assert verdicts.passed is False


def test_任一项非_pass_则整体不通过():
    verdicts = campaign.Verdicts()
    verdicts.add("A", True)
    assert verdicts.passed is True
    verdicts.add("B", None)
    assert verdicts.passed is False


def test_运行编号不合法直接拒绝():
    for bad in ("", "../逃逸", "a/b", ".hidden"):
        with pytest.raises(campaign.CampaignError):
            campaign.run_root(bad)
