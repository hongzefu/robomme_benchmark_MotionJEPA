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

from scripts.injection import campaign  # noqa: E402
from scripts.injection.categories import legal_categories, observed_values  # noqa: E402
from scripts.injection.sampling import (  # noqa: E402
    COARSE_BINS,
    GROUP_SIZE,
    derive_rng,
    quota_counts,
    quota_series,
    stratify,
)
from scripts.injection.specs import GROUPS, seal  # noqa: E402

from scripts.injection.contract import load_contract  # noqa: E402

SAMPLING = json.loads((REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "native_sampling.json").read_text())
#: 合法类别表从契约展开；v1 与 native_sampling.json 派生结果一致，这里用 v1。
CONTRACT_V1 = load_contract(REPO_ROOT / "scripts" / "configs" / "newtask-v2" / "injection_contract_v1.json")


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
        {("BinFill", "hard"): _fake_binfill_document(dynamic_values)}, CONTRACT_V1, verdicts
    )
    entry = report["BinFill/hard"]["independent"]["dynamic"]
    return entry["spread"], entry["counts"]


def test_全部为同一个值时配额判据必须失败():
    """⚠ 这就是第 4.1 节的反例：只数「实际出现过的类别」会算出计数差 0 并误判通过。"""
    spread, counts = _dynamic_spread([True] * GROUP_SIZE)
    assert len(counts) == 2, "合法类别只补出一个，说明没按约定表补零"
    assert spread == GROUP_SIZE, "100 条全为 True 却算出计数差 0，补零漏了"

    verdicts = campaign.Verdicts()
    campaign._check_quota({("BinFill", "hard"): _fake_binfill_document([True] * GROUP_SIZE)}, CONTRACT_V1, verdicts)
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
    categories = legal_categories(task, difficulty, CONTRACT_V1)
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


# ── 并发窗口与档位判据（步骤 4）────────────────────────────────────────────
from scripts.injection.run import (  # noqa: E402
    OUTCOME_PASS,
    classify_outcome,
    execution_state,
    overlap_report,
    tier_is_unusable,
    tier_throughput,
)


def _window(pid, gpu, begin, end):
    return {"task": "T", "episode": 0, "pid": pid, "gpu": gpu, "begin": begin, "end": end}


def test_真并发时不同_pid_峰值达到_worker_数():
    windows = [_window(1, "0", 0, 10), _window(2, "0", 1, 11), _window(3, "0", 2, 12)]
    report = overlap_report(windows, ["0"], 3)
    assert report["peak_distinct_pids"] == 3
    assert report["passed"] is True


def test_首尾相接的串行执行不算并发():
    """三条依次执行、互不重叠：峰值只有 1，达不到 3 个 worker。"""
    windows = [_window(1, "0", 0, 10), _window(2, "0", 10, 20), _window(3, "0", 20, 30)]
    report = overlap_report(windows, ["0"], 3)
    assert report["peak_distinct_pids"] == 1
    assert report["passed"] is False


def test_同一个_pid_重叠不算两个并发():
    """同一个 worker 的两条记录即使时间上重叠，也只算一个并发。"""
    windows = [_window(1, "0", 0, 10), _window(1, "0", 1, 11)]
    report = overlap_report(windows, ["0"], 2)
    assert report["peak_distinct_pids"] == 1
    assert report["passed"] is False


def test_双卡要求共同窗口大于零():
    # 两张卡各跑各的且时间错开：每卡峰值够，但没有共同窗口
    apart = [_window(1, "0", 0, 10), _window(2, "1", 20, 30)]
    assert overlap_report(apart, ["0", "1"], 1)["both_busy_seconds"] == 0
    assert overlap_report(apart, ["0", "1"], 1)["passed"] is False
    together = [_window(1, "0", 0, 10), _window(2, "1", 5, 15)]
    report = overlap_report(together, ["0", "1"], 1)
    assert report["both_busy_seconds"] == 5
    assert report["passed"] is True


def test_单卡不要求共同窗口():
    report = overlap_report([_window(1, "0", 0, 10), _window(2, "0", 1, 9)], ["0"], 2)
    assert report["both_busy_seconds"] == 0
    assert report["passed"] is True


# ── 档位可用性与吞吐 ────────────────────────────────────────────────────────
def _tier_result(rows, wall_s=60.0, timed_out=False):
    return {"rows": rows, "wall_s": wall_s, "timed_out": timed_out}


def _row(outcome=OUTCOME_PASS, video="complete", state="completed", error=None):
    return {"outcome": outcome, "video_status": video, "execution_state": state, "error_type": error}


def test_任务性失败不让该档判为不可用():
    """⚠ 规划失败、碰撞拒绝是样本本身的问题，与并发规模无关，不能误伤档位。"""
    rows = [_row(), _row("规划失败"), _row("碰撞拒绝")]
    unusable, _ = tier_is_unusable(_tier_result(rows))
    assert unusable is False


def test_基础设施失败让该档判为不可用():
    rows = [_row(), _row("未运行", state="infra_error", error="BrokenProcessPool")]
    unusable, reason = tier_is_unusable(_tier_result(rows))
    assert unusable is True and "OOM" in reason


def test_内存错误也算该档不可用():
    rows = [_row("未运行", state="infra_error", error="MemoryError")]
    assert tier_is_unusable(_tier_result(rows))[0] is True


def test_超时算该档不可用():
    assert tier_is_unusable(_tier_result([_row()], timed_out=True))[0] is True


def test_吞吐分子只数成功且视频完整的条数():
    """⚠ 否则一档跑得快只是因为大量样本快速失败，会被误当成加速。"""
    rows = [_row(), _row(), _row(video="missing"), _row("规划失败")]
    throughput, delivered, failed = tier_throughput(_tier_result(rows, wall_s=60.0))
    assert delivered == 2  # 第三条视频缺失、第四条任务失败，都不算交付
    assert failed == 1
    assert throughput == pytest.approx(2.0)


def test_快速失败不会拿到高吞吐():
    fast_fail = _tier_result([_row("规划失败") for _ in range(100)], wall_s=10.0)
    slow_good = _tier_result([_row() for _ in range(10)], wall_s=60.0)
    assert tier_throughput(fast_fail)[0] == 0.0
    assert tier_throughput(slow_good)[0] > 0


# ── 七类结果分类 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"ok": True}, "通过"),
        ({"ok": False, "error_type": "EpisodeSpecError", "failure_class": "task"}, "规格拒绝"),
        ({"ok": False, "error_type": "BinCollisionError", "failure_class": "task"}, "碰撞拒绝"),
        ({"ok": False, "error_type": "SpecBindingError", "failure_class": "task"}, "实际对象/动作不符"),
        ({"ok": False, "error_type": "FailsafeTimeout", "failure_class": "task"}, "超时"),
        ({"ok": False, "error_type": "ScrewPlanFailure", "failure_class": "task"}, "规划失败"),
        ({"ok": False, "error_type": "SceneGenerationError", "failure_class": "task"}, "规划失败"),
        ({"ok": False, "error_type": "TypeError", "failure_class": "code"}, "未运行"),
        ({"ok": False, "error_type": "BrokenProcessPool", "failure_class": "infra"}, "未运行"),
    ],
)
def test_七类结果互斥且系统错误不冒充物理不可行(record, expected):
    assert classify_outcome(record) == expected


def test_执行状态与任务结果分开记():
    """系统错误计入执行状态，不能冒充物理不可行——两个字段互不覆盖。"""
    record = {"ok": False, "error_type": "BrokenProcessPool", "failure_class": "infra"}
    assert execution_state(record) == "infra_error"
    assert classify_outcome(record) == "未运行"
    # 任务性失败：确实跑完了，执行状态是 completed，只是任务没成功
    record = {"ok": False, "error_type": "ScrewPlanFailure", "failure_class": "task"}
    assert execution_state(record) == "completed"
    assert classify_outcome(record) == "规划失败"


def test_cuda_显存_oom_也算该档不可用():
    """⚠ CUDA OOM 在 worker 里不在 retryable 名单，会被记成 code_error 而不是 infra_error；
    只看 infra_error 会漏掉它，而档位阶梯恰恰是靠显存 OOM 封顶的。"""
    rows = [{"outcome": "未运行", "video_status": "missing", "execution_state": "code_error",
             "error_type": "OutOfMemoryError", "error": "CUDA out of memory. Tried to allocate 2.00 GiB"}]
    unusable, reason = tier_is_unusable(_tier_result(rows))
    assert unusable is True and "OOM" in reason


def test_仅靠错误文本也能认出显存不足():
    rows = [{"outcome": "未运行", "video_status": "missing", "execution_state": "code_error",
             "error_type": "RuntimeError", "error": "CUDA error: out of memory"}]
    assert tier_is_unusable(_tier_result(rows))[0] is True


def test_普通运行时错误不算资源失败():
    rows = [{"outcome": "规划失败", "video_status": "complete", "execution_state": "completed",
             "error_type": "RuntimeError", "error": "planner gave up after 3 tries"}]
    assert tier_is_unusable(_tier_result(rows))[0] is False


# ── 同任务不同难度不得互相覆盖 ──────────────────────────────────────────────
from scripts.injection.run import read_result_rows  # noqa: E402


def _jsonl(tmp_path, records):
    path = tmp_path / "episode_results.jsonl"
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records), encoding="utf-8")
    return tmp_path


def test_同任务不同难度的结果行不互相覆盖(tmp_path):
    """⚠ seed 只由任务与 episode 决定，所以 BinFill/easy/ep0 与 BinFill/hard/ep0 的
    (task, episode) 完全相同。只用两元组做 key，330 行会塌成 4 任务 × 30 = 120 行。"""
    root = _jsonl(tmp_path, [
        {"task": "BinFill", "difficulty": d, "episode": 0, "seed": 4000, "attempt": 0, "ok": True}
        for d in ("easy", "medium", "hard")
    ])
    rows = read_result_rows(root)
    assert len(rows) == 3
    assert sorted(row["difficulty"] for row in rows) == ["easy", "hard", "medium"]


def test_同一条的重试只保留最后一次(tmp_path):
    root = _jsonl(tmp_path, [
        {"task": "BinFill", "difficulty": "hard", "episode": 0, "seed": 4000, "attempt": 0, "ok": False,
         "failure_class": "task", "error_type": "ScrewPlanFailure"},
        {"task": "BinFill", "difficulty": "hard", "episode": 0, "seed": 4001, "attempt": 1, "ok": True},
    ])
    rows = read_result_rows(root)
    assert len(rows) == 1
    assert rows[0]["attempt"] == 1 and rows[0]["outcome"] == "通过"


def test_十一组三十条各自独立共三百三十行(tmp_path):
    groups = [("BinFill", d) for d in ("easy", "medium", "hard")]
    groups += [("RouteStick", d) for d in ("easy", "medium", "hard")]
    groups += [("VideoUnmaskSwap", d) for d in ("easy", "medium", "hard")]
    groups += [("VideoRepick", d) for d in ("easy", "medium")]
    records = [
        {"task": task, "difficulty": diff, "episode": ep, "seed": 1, "attempt": 0, "ok": True}
        for task, diff in groups for ep in range(30)
    ]
    rows = read_result_rows(_jsonl(tmp_path, records))
    assert len(rows) == 330


def test_h5_索引按任务难度_episode_三元组(tmp_path):
    """同名 HDF5 分处不同难度目录，索引必须分得开。"""
    for diff in ("easy", "hard"):
        target = tmp_path / "BinFill" / diff / "hdf5_files"
        target.mkdir(parents=True)
        (target / "BinFill_ep0_seed4000.h5").write_bytes(b"x")
    index = campaign._index_h5(tmp_path)
    assert len(index) == 2
    assert ("BinFill", "easy", 0) in index and ("BinFill", "hard", 0) in index
