# -*- coding: utf-8 -*-
"""轻量测试：单事件 swap clip 的源筛选/枚举/槽位换算/编号，与 env 源码及 train metadata 对账。

不跑任何 rollout，纯函数层面校验，秒级完成。目的是在花掉小时级 rollout 之前就排除
swap_times 复算、难度→bin 数映射、region4 模板、槽位换算、编号公式写错。

本轮宗旨是「除了 bin 的初始位置和第一次 swap 的排列组合，其他全部保持一致」，
所以最要紧的两条断言是：

* ``test_tail_slot_pairs_invariant_across_variants``：窗口 ≥2 的**槽位**对跨全部 6 条
  变体逐条相同 —— 后 30 帧不是第二个变化因子；
* ``test_is_original_reproduces_original_bin_pairs``：is_original 变体的注入序列退化为
  原始 bin 对序列 —— 仍逐位复现官方 episode。

运行（使用 uv）：
    uv run python -m pytest tests/lightweight/test_swap_clip_plan.py -q
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root

pytestmark = [pytest.mark.lightweight]

REPO_ROOT = find_repo_root(__file__)
sys.path.insert(0, str(REPO_ROOT / "scripts" / "data-generation-MotionJEPALabel"))

from clip_plan import (  # noqa: E402
    CANDIDATE_EPISODES,
    CLIP_END,
    CLIP_LEN,
    CLIP_MARGIN,
    CLIP_START,
    ENV_CONFIGS,
    EVAL_TASKS,
    MIN_SWAP_TIMES,
    REGION4_VIDEO,
    REGION_ROTATED,
    REQUIRED_BINS,
    SLOT_ROLE,
    TOPO_CROSS_ALIGNED,
    TOPO_CROSS_DIAGONAL,
    TOPO_SAME_COLUMN,
    VARIANT_BLOCK,
    bin_pairs,
    bin_pairs_from_slot_pairs,
    clip_visible_windows,
    decode_staging_episode,
    decode_variant_seed,
    net_permutation,
    nominal_distance_video,
    plan_table,
    select_sources,
    signature_of,
    slot_pairs_from_bin_pairs,
    source_episode,
    staging_episode,
    swap_windows_clip,
    swap_windows_env,
    topo_class,
    topo_table,
    variant_seed,
    variant_specs,
)


# ── 与 env 源码对账 ──────────────────────────────────────────────────────────


def _env_configs_from_source(task: str) -> dict:
    """AST 解析 env 源码里的 config_easy/medium/hard 类属性（不 import 重型模块）。"""
    path = REPO_ROOT / "src" / "robomme" / "robomme_env" / f"{task}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in (
                "config_easy",
                "config_medium",
                "config_hard",
            ):
                found[target.id.removeprefix("config_")] = ast.literal_eval(node.value)
    assert set(found) == {"easy", "medium", "hard"}, f"{task}: 未解析到全部三档 config"
    return found


@pytest.mark.parametrize("task", EVAL_TASKS)
def test_env_configs_match_source(task: str) -> None:
    source_configs = _env_configs_from_source(task)
    for difficulty, expected in ENV_CONFIGS.items():
        actual = source_configs[difficulty]
        for key, value in expected.items():
            assert actual[key] == value, (
                f"{task}/{difficulty}: ENV_CONFIGS[{key!r}]={value} 与源码 {actual[key]} 不符"
            )


def _region4_expr(task: str) -> str:
    """AST 归一化 _load_scene 里 region4 的右值表达式（Button 的不是纯字面量）。"""
    path = REPO_ROOT / "src" / "robomme" / "robomme_env" / f"{task}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "region4":
                    found = ast.unparse(node.value)
    assert found is not None, f"{task}: 源码里没找到 region4"
    return found


def test_region4_video_is_the_fixed_template() -> None:
    """Video 的 region4 是固定字面量，REGION4_VIDEO 必须逐字一致。"""
    assert _region4_expr("VideoUnmaskSwap") == "[[-0.05, -0.1], [-0.05, 0.1], [0.1, 0.1], [0.1, -0.1]]"
    assert [list(point) for point in REGION4_VIDEO] == [
        [-0.05, -0.1],
        [-0.05, 0.1],
        [0.1, 0.1],
        [0.1, -0.1],
    ]


def test_region4_button_has_per_column_random_y_offsets() -> None:
    """Button 的 region4 带 seed 随机 y 偏移（每列一个）—— 所以类别不能按距离分。

    结构上仍与 Video 同构：左列 x=0 的 (下,上)、右列 x=0.1 的 (上,下)，
    同列 y 相差恒 0.2；偏移 y_offset_1/y_offset_2 是**列内共享**的，不破坏槽位角色。
    """
    assert _region4_expr("ButtonUnmaskSwap") == (
        "[[0, -0.1 + y_offset_1], [0, 0.1 + y_offset_1], "
        "[0.1, 0.1 + y_offset_2], [0.1, -0.1 + y_offset_2]]"
    )


def test_region_rotation_switch_matches_source() -> None:
    """Video 启用整体随机旋转，Button 的那行被注释掉了 —— REGION_ROTATED 必须对上。"""
    for task, rotated in REGION_ROTATED.items():
        text = (REPO_ROOT / "src" / "robomme" / "robomme_env" / f"{task}.py").read_text(
            encoding="utf-8"
        )
        active = any(
            line.strip().startswith("angle, region = rotate_points_random")
            for line in text.splitlines()
        )
        assert active == rotated, f"{task}: 源码里 rotate_points_random 启用={active}，表里={rotated}"


@pytest.mark.parametrize("task", EVAL_TASKS)
def test_swap_window_constants_match_source(task: str) -> None:
    """窗口常量 64 / 50 在 _refresh_swap_schedule 里是硬编码，改了必须同步。"""
    text = (REPO_ROOT / "src" / "robomme" / "robomme_env" / f"{task}.py").read_text(
        encoding="utf-8"
    )
    squeezed = "".join(text.split())  # 两 env 的空格写法不同（Button 是 "64+ 50 * 3"）
    assert "64,64+50)" in squeezed
    assert "64+50,64+50*2)" in squeezed
    assert "64+50*2,64+50*3)" in squeezed


# ── 与 train metadata 对账：入选源的 seed 与难度 ──────────────────────────────

# 三重筛选（4-bin → k≥2 → 两 env 共同源号）后的最终源；ButtonUnmaskSwap/ep98 的
# seed 是 16801 而非规则值 16800（历史 attempt 探针）——这正是必须读表的原因。
EXPECTED_SOURCE = {
    ("VideoUnmaskSwap", 91): (14100, "hard", 4, 2),
    ("VideoUnmaskSwap", 95): (14500, "hard", 4, 2),
    ("VideoUnmaskSwap", 98): (14800, "medium", 4, 2),
    ("VideoUnmaskSwap", 99): (14900, "hard", 4, 2),
    ("ButtonUnmaskSwap", 91): (16100, "hard", 4, 3),
    ("ButtonUnmaskSwap", 95): (16500, "hard", 4, 2),
    ("ButtonUnmaskSwap", 98): (16801, "medium", 4, 2),
    ("ButtonUnmaskSwap", 99): (16900, "hard", 4, 3),
}


@pytest.mark.parametrize("key", sorted(EXPECTED_SOURCE))
def test_source_episode_facts(key: tuple[str, int]) -> None:
    task, episode = key
    env_seed, difficulty, num_bins, swap_times = EXPECTED_SOURCE[key]
    src = source_episode(task, episode)
    assert src.env_seed == env_seed
    assert src.difficulty == difficulty
    assert src.num_bins == num_bins
    assert src.swap_times == swap_times


# ── 源三重筛选与规模 ─────────────────────────────────────────────────────────


def test_select_sources_is_exactly_91_95_98_99() -> None:
    selected = select_sources()
    for task in EVAL_TASKS:
        assert [src.episode for src in selected[task]] == [91, 95, 98, 99], (
            f"{task}: 筛选结果 {[s.episode for s in selected[task]]} ≠ [91,95,98,99]"
        )


def test_filters_actually_bite() -> None:
    """逐条验证三重筛选各自剔掉了谁 —— 防止筛选条件写反还恰好凑对总数。"""
    unfiltered = {
        task: [source_episode(task, ep) for ep in CANDIDATE_EPISODES] for task in EVAL_TASKS
    }
    # 4-bin 门槛剔掉全部 easy
    assert all(
        src.num_bins == 3 for src in unfiltered["VideoUnmaskSwap"] if src.difficulty == "easy"
    )
    # k≥2 门槛剔掉 Video 的 ep90/92/94/96
    dropped_video = sorted(
        src.episode
        for src in unfiltered["VideoUnmaskSwap"]
        if src.num_bins == REQUIRED_BINS and src.swap_times < MIN_SWAP_TIMES
    )
    assert dropped_video == [90, 94]
    # 共同源号门槛剔掉 Button 独有的 ep90
    per_task = select_sources(require_common=False)
    assert [src.episode for src in per_task["ButtonUnmaskSwap"]] == [90, 91, 95, 98, 99]
    assert [src.episode for src in per_task["VideoUnmaskSwap"]] == [91, 95, 98, 99]


def test_plan_total_48() -> None:
    table = plan_table()
    per_task: dict[str, int] = {task: 0 for task in EVAL_TASKS}
    for row in table["rows"]:
        per_task[row["task"]] += row["variant_count"]
    assert per_task["VideoUnmaskSwap"] == 24
    assert per_task["ButtonUnmaskSwap"] == 24
    assert table["total"] == 48
    # 每源恒 6 条 —— 这是剔掉 3-bin 源换来的一致性
    assert [row["variant_count"] for row in table["rows"]] == [6] * 8


# ── 槽位换算：本轮「后续窗口固定」的实现核心 ─────────────────────────────────


def test_bin_pairs_lexicographic() -> None:
    assert bin_pairs(4) == [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]


def test_slot_and_bin_pair_conversions_are_inverse() -> None:
    """两个换算互为逆运算 —— 对全部长度 ≤3 的 bin 对序列穷举验证。"""
    import itertools

    pairs = bin_pairs(4)
    for k in (1, 2, 3):
        for seq in itertools.product(pairs, repeat=k):
            slots = slot_pairs_from_bin_pairs(seq, 4)
            assert bin_pairs_from_slot_pairs(slots, 4) == tuple(
                (min(u, v), max(u, v)) for u, v in seq
            )


def test_first_window_slot_equals_bin_pair() -> None:
    """窗口 1 之前 slot 是 identity，所以首个槽位对 == 首个 bin 对。"""
    for pair in bin_pairs(4):
        assert slot_pairs_from_bin_pairs([pair], 4)[0] == pair
        assert bin_pairs_from_slot_pairs([pair], 4)[0] == pair


def test_slot_tracking_worked_example() -> None:
    """手算样例：先换 bin(0,1)，再要动槽位(0,2) —— 此刻槽位 0 上是 bin 1。"""
    assert bin_pairs_from_slot_pairs([(0, 1), (0, 2)], 4) == ((0, 1), (1, 2))
    assert slot_pairs_from_bin_pairs([(0, 1), (1, 2)], 4) == ((0, 1), (0, 2))


# ── 变体构造：宗旨的两条机器判据 ─────────────────────────────────────────────

# ButtonUnmaskSwap/ep91 的原始序列（Phase 0 实测，bin 口径）；k=3、4 bin。
ORIGINAL_EP91 = ((1, 2), (1, 2), (0, 3))


def _spec_fixture():
    src = source_episode("ButtonUnmaskSwap", 91)
    return src, variant_specs(src, ORIGINAL_EP91)


def test_variant_specs_shape() -> None:
    src, specs = _spec_fixture()
    assert len(specs) == 6
    assert [spec.variant_idx for spec in specs] == list(range(6))
    assert all(spec.swap_times == src.swap_times for spec in specs)
    # 窗口 1 的槽位对恰好枚举完 C(4,2)
    assert sorted(spec.event_slots for spec in specs) == bin_pairs(4)


def test_tail_slot_pairs_invariant_across_variants() -> None:
    """★ 宗旨判据：窗口 ≥2 的槽位对跨全部 6 条变体逐条相同。

    这保证后 30 帧里第二次 swap 的 teleport 起止位置、被锁定旁观 bin 的位置集合
    完全一致 —— 后段不是第二个变化因子。
    """
    _, specs = _spec_fixture()
    tails = {spec.slot_pairs[1:] for spec in specs}
    assert len(tails) == 1, f"窗口 ≥2 的槽位对出现了 {len(tails)} 种，应恒为 1 种"
    assert tails.pop() == slot_pairs_from_bin_pairs(ORIGINAL_EP91, 4)[1:]
    # 而注入用的 bin 对在窗口 ≥2 上**本来就该跟着第一次 swap 变** —— 那是换算的结果
    assert len({spec.bin_pairs[1:] for spec in specs}) > 1


def test_is_original_reproduces_original_bin_pairs() -> None:
    """★ 宗旨判据：恰有 1 条 is_original，且其注入序列退化为原始 bin 对序列。"""
    _, specs = _spec_fixture()
    originals = [spec for spec in specs if spec.is_original]
    assert len(originals) == 1
    assert originals[0].bin_pairs == ORIGINAL_EP91
    assert originals[0].event_slots == ORIGINAL_EP91[0]


def test_variant_specs_rejects_length_mismatch() -> None:
    src = source_episode("ButtonUnmaskSwap", 91)  # k=3
    with pytest.raises(ValueError):
        variant_specs(src, ((0, 1), (2, 3)))  # 只给了 2 段


def test_net_permutation() -> None:
    assert net_permutation([(0, 1)], 4) == (1, 0, 2, 3)
    # 同一对槽位连换两次 = 恒等
    assert net_permutation([(0, 1), (0, 1)], 4) == (0, 1, 2, 3)


# ── 拓扑类别 ─────────────────────────────────────────────────────────────────


def test_topo_table_three_classes_two_pairs_each() -> None:
    table = topo_table()
    assert table == {
        (0, 1): TOPO_SAME_COLUMN,
        (2, 3): TOPO_SAME_COLUMN,
        (1, 2): TOPO_CROSS_ALIGNED,
        (0, 3): TOPO_CROSS_ALIGNED,
        (0, 2): TOPO_CROSS_DIAGONAL,
        (1, 3): TOPO_CROSS_DIAGONAL,
    }
    counts: dict[str, int] = {}
    for name in table.values():
        counts[name] = counts.get(name, 0) + 1
    assert counts == {TOPO_SAME_COLUMN: 2, TOPO_CROSS_ALIGNED: 2, TOPO_CROSS_DIAGONAL: 2}


def test_slot_roles_form_two_columns_of_low_and_high() -> None:
    """槽位角色表本身自洽：两列各一个 low 一个 high。"""
    assert sorted(SLOT_ROLE) == [0, 1, 2, 3]
    by_column: dict[int, list[str]] = {}
    for column, side in SLOT_ROLE.values():
        by_column.setdefault(column, []).append(side)
    assert {column: sorted(sides) for column, sides in by_column.items()} == {
        0: ["high", "low"],
        1: ["high", "low"],
    }


def test_topo_class_matches_video_distance_tiers() -> None:
    """交叉验证：在 Video 的固定模板下，拓扑类别恰好与 0.15/0.20/0.25 三档一一对应。

    （Button 没有这样的常量模板，所以只能在 Video 上做这条交叉验证 ——
    这正是类别必须按角色定义、而不是按距离定义的原因。）
    """
    tiers = {
        TOPO_CROSS_ALIGNED: 0.15,
        TOPO_SAME_COLUMN: 0.20,
        TOPO_CROSS_DIAGONAL: 0.25,
    }
    for pair in bin_pairs(4):
        assert nominal_distance_video(pair) == pytest.approx(tiers[topo_class(pair)])


def test_button_diagonal_can_be_shorter_than_same_column() -> None:
    """反例存在性：Button 的对角距离可以小于同列的 0.20 —— 距离分档会判错。

    同列恒 0.2；跨列对角 = hypot(0.1, 0.2 + (y2 - y1))，y2-y1 ∈ [-0.1, 0.1]。
    取 y2 - y1 = -0.1 得 hypot(0.1, 0.1) ≈ 0.1414 < 0.2。
    """
    import math

    same_column = 0.2
    diagonal_min = math.hypot(0.1, 0.2 - 0.1)
    assert diagonal_min < same_column


def test_topo_class_is_order_insensitive() -> None:
    assert topo_class((3, 0)) == topo_class((0, 3)) == TOPO_CROSS_ALIGNED


# ── clip 帧号与窗口 ──────────────────────────────────────────────────────────


def test_clip_geometry() -> None:
    assert (CLIP_START, CLIP_END, CLIP_LEN, CLIP_MARGIN) == (34, 144, 110, 30)


def test_swap_windows_env_and_clip() -> None:
    assert swap_windows_env(3) == ((64, 114), (114, 164), (164, 214))
    # clip 帧 = env step − 34；返回完整窗口（进度必须按完整窗口算）
    assert swap_windows_clip(3) == ((30, 80), (80, 130), (130, 180))


def test_clip_visible_windows() -> None:
    # 窗口 1 全可见、窗口 2 露出前 30 帧、窗口 3 完全在 clip 外
    assert clip_visible_windows(2) == [0, 1]
    assert clip_visible_windows(3) == [0, 1]
    assert swap_windows_clip(3)[2][0] >= CLIP_LEN


def test_event_window_sits_inside_clip_with_margins() -> None:
    """事件窗口前后各留满 30 帧 —— 这是「前后 30 frame」的机器判据。"""
    start, end = swap_windows_clip(1)[0]
    assert start == CLIP_MARGIN
    assert CLIP_LEN - end == CLIP_MARGIN


# ── 编号公式往返 ─────────────────────────────────────────────────────────────


def test_staging_and_seed_roundtrip() -> None:
    assert staging_episode(91, 5) == 91005
    assert variant_seed(14100, 5) == 14100005
    assert decode_staging_episode(91005) == (91, 5)
    assert decode_variant_seed(14100005) == (14100, 5)
    for src_ep in (91, 95, 98, 99):
        for idx in (0, 5, VARIANT_BLOCK - 1):
            assert decode_staging_episode(staging_episode(src_ep, idx)) == (src_ep, idx)
    with pytest.raises(ValueError):
        staging_episode(91, VARIANT_BLOCK)


def test_variant_seed_unique_and_disjoint_from_env_seeds() -> None:
    """全部 48 条的 variant_seed 互异，且不与任何源 env_seed 撞号。"""
    seen: set[int] = set()
    selected = select_sources()
    for task in EVAL_TASKS:
        for src in selected[task]:
            for idx in range(src.num_pairs):
                seed = variant_seed(src.env_seed, idx)
                assert seed not in seen
                seen.add(seed)
    assert len(seen) == 48
    assert not seen & {value[0] for value in EXPECTED_SOURCE.values()}


def test_signature_format() -> None:
    assert signature_of(((0, 1), (2, 3))) == "01|23"
