#!/usr/bin/env python3
"""轻量测试：V9 定稿口径（用户 2026-10-02 定义）——``dataset="test-hard"`` 的交付集严格为 800 局。

钉死四件事（`docs/plans/1002-v9-final-cleanup-plan.md` §三）：

1. 包内五份 ``env_metadata/test-hard/xhard{1..5}/specs.jsonl`` 的正式局（``delivered``：``selected`` 且
   ``rollout.status=="ok"``）恰好 800 行、16 任务各 50 局、逐格等于 ``V9_CELLS``、档内 seed 不重复；
   未入选候选行仍留在文件里（用户决定「不裁，只加校验」），由 builder 过滤。
2. builder 实际发出的 episode：每任务 62 = xhard0 官方 hard 12 局（不算在 800 里）+ V9 50 局，16 任务 992；
   前 12 局档位 xhard0，其后按 xhard1→xhard5 单调不降。
3. 入口 ``scripts/evaluation_hard.py`` 的步数上限是构造时写死的一个数 ``max_steps=1600``（六档含 xhard0 一律
   1600），``make_env_for_episode(episode)`` 与官方一样不传、不按档查表；规格文件 header 与行里都没有 ``max_steps``
   键——不从 episode 读。包内常量表 ``TIER_MAX_STEPS`` 入口不再引用（评估流水线 eval-official 仍用，去留待定 B5）。
4. ``scripts/evaluation_hard.py`` 与官方 ``scripts/evaluation.py`` 只差 3 个单行 hunk：换包 import、
   ``dataset="test-hard"``、``max_steps`` 1300→1600。

只读包内 jsonl 与官方 test 元数据，不 ``gym.make``、不起仿真。判定行：
``V9_PACKAGED=PASS total=800 per_task=50 cells=43 episodes_per_task=62 total_with_xhard0=992``、
``V9_MAX_STEPS=PASS entry=1600``、``HARD_ENTRY_DIFF=PASS hunks=3``。

    uv run --no-sync python -m pytest tests/lightweight/test_v9_packaged_800.py -q -s
"""

from __future__ import annotations

import difflib
import sys
import warnings
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme_hard.env_record_wrapper import TIER_MAX_STEPS, BenchmarkEnvBuilder, hard_specs as H  # noqa: E402

V9_TOTAL = 800
V9_PER_TASK = 50
XHARD0_PER_TASK = 12
EXEC_CAP = 1600
XHARD0_CAP = 1300


@pytest.fixture(scope="module")
def packaged() -> dict[str, tuple[dict, list]]:
    """五份包内规格：tier → (header, rows)。只读，不校验指纹（指纹不符只警告）。"""
    out = {}
    for tier in H.TIERS:
        records = H.read_jsonl(H.PACKAGED_SPECS_ROOT / tier / "specs.jsonl")
        out[tier] = (records[0], records[1:])
    return out


def test_包内正式局恰好800且每任务50(packaged):
    delivered = [(tier, row) for tier, (_, rows) in packaged.items() for row in rows if H.delivered(row)]
    assert len(delivered) == V9_TOTAL, f"包内正式局 {len(delivered)} ≠ {V9_TOTAL}"
    per_task = Counter(row["task"] for _, row in delivered)
    assert set(per_task) == set(H.ALL_TASKS)
    assert all(n == V9_PER_TASK for n in per_task.values()), f"每任务应恰为 {V9_PER_TASK}：{dict(per_task)}"
    per_cell = Counter((row["task"], tier) for tier, row in delivered)
    assert dict(per_cell) == dict(H.V9_CELLS), "逐格局数须等于 V9_CELLS"
    assert H.EXPECTED_CELLS is H.V9_CELLS and sum(H.V9_CELLS.values()) == V9_TOTAL and len(H.V9_CELLS) == 43
    for tier, (_, rows) in packaged.items():
        seeds = [row["seed"] for row in rows if H.delivered(row)]
        assert len(seeds) == len(set(seeds)), f"{tier} 正式局 seed 重复"
    # 未入选候选行允许存在（用户决定不裁），但正式局集合不受影响
    total_rows = sum(len(rows) for _, rows in packaged.values())
    assert total_rows >= V9_TOTAL


@pytest.fixture(scope="module")
def builders():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return {task: BenchmarkEnvBuilder(task, dataset="test-hard") for task in H.ALL_TASKS}


def test_builder每任务62局_前12局xhard0_后50局按档单调(builders):
    order = {tier: i for i, tier in enumerate(("xhard0", *H.TIERS))}
    total = 0
    for task, builder in builders.items():
        n = builder.get_episode_num()
        assert n == XHARD0_PER_TASK + V9_PER_TASK == 62, f"{task} 发出 {n} 局，应为 62"
        tiers = [builder.resolve_episode(i)[1] for i in range(n)]
        assert tiers[:XHARD0_PER_TASK] == ["xhard0"] * XHARD0_PER_TASK, f"{task} 前 12 局不是 xhard0"
        rest = tiers[XHARD0_PER_TASK:]
        assert all(t in H.TIERS for t in rest) and Counter(rest) == {
            t: n for (tk, t), n in H.V9_CELLS.items() if tk == task
        }, f"{task} 后 50 局档位分布与 V9_CELLS 不符"
        assert all(order[a] <= order[b] for a, b in zip(rest, rest[1:])), f"{task} 档位顺序非单调"
        total += n
    assert total == 16 * 62 == 992
    print(f"\nV9_PACKAGED=PASS total={V9_TOTAL} per_task={V9_PER_TASK} cells={len(H.V9_CELLS)} "
          f"episodes_per_task=62 total_with_xhard0={total}")


def test_max_steps入口固定1600不按档查表(packaged):
    src = (REPO_ROOT / "scripts" / "evaluation_hard.py").read_text(encoding="utf-8")
    assert src.count("max_steps=1600") == 1, "入口构造时须写死 max_steps=1600"
    assert "max_steps=1300" not in src
    assert "TIER_MAX_STEPS" not in src and "resolve_episode" not in src, "入口不得按档查表"
    assert "env_builder.make_env_for_episode(episode)" in src, "make_env_for_episode 须与官方一样不传 max_steps"
    # 规格文件里没有 max_steps 键：上限不从 episode 读
    for tier, (header, rows) in packaged.items():
        assert "max_steps" not in header, f"{tier} header 不应含 max_steps"
        assert header.get("exec_cap") == EXEC_CAP
        assert all("max_steps" not in row for row in rows), f"{tier} 规格行不应含 max_steps"
    # 包内常量表只剩评估流水线在用，入口不用；记录其现值（去留待定 B5）
    assert TIER_MAX_STEPS is H.TIER_MAX_STEPS
    assert TIER_MAX_STEPS == {"xhard0": XHARD0_CAP, **{tier: EXEC_CAP for tier in H.TIERS}}
    print(f"\nV9_MAX_STEPS=PASS entry={EXEC_CAP} per_tier_lookup=none source=evaluation_hard.py")


def test_evaluation_hard与官方入口只差3行():
    official = (REPO_ROOT / "scripts" / "evaluation.py").read_text(encoding="utf-8").splitlines()
    hard = (REPO_ROOT / "scripts" / "evaluation_hard.py").read_text(encoding="utf-8").splitlines()
    diff = [line for line in difflib.unified_diff(official, hard, n=0, lineterm="") if line[:3] not in ("---", "+++")]
    hunks = [line for line in diff if line.startswith("@@")]
    removed = [line[1:] for line in diff if line.startswith("-")]
    added = [line[1:] for line in diff if line.startswith("+")]
    assert len(hunks) == 3, f"hunk 数 {len(hunks)} ≠ 3：{diff}"
    assert len(removed) == 3 and len(added) == 3, diff
    assert any("from robomme.env_record_wrapper import BenchmarkEnvBuilder" in line for line in removed)
    assert any(line.strip() == "from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder" for line in added)
    assert any('dataset="test"' in line for line in removed) and any('dataset="test-hard"' in line for line in added)
    assert any("max_steps=1300" in line for line in removed) and any("max_steps=1600" in line for line in added)
    assert not any("TIER_MAX_STEPS" in line or "resolve_episode" in line for line in added)
    print(f"\nHARD_ENTRY_DIFF=PASS hunks={len(hunks)} removed={len(removed)} added={len(added)}")
