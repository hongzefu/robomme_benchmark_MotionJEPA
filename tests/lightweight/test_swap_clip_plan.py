# -*- coding: utf-8 -*-
"""轻量测试：单事件 swap clip 的源筛选/枚举/槽位换算/编号，与 env 源码及各 split metadata 对账。

不跑任何 rollout，纯函数层面校验，秒级完成。目的是在花掉小时级 rollout 之前就排除
swap_times 复算、难度→bin 数映射、region4 模板、槽位换算、编号公式写错。

源范围（2026-08-19 扩源）：train ep90-99 + test ep0-49 + val ep0-49 三个 split，源键为
``(split, task, episode)``。metadata 文件（``src/robomme/env_metadata/{split}/``）是被 git
跟踪的仓库源码、不是数据集产物，lightweight 读它不违反 AGENTS.md 规则 3。

本轮宗旨是「除了 bin 的初始位置和第一次 swap 的排列组合，其他全部保持一致」，且第一次
swap 的可选对受**最近邻约束**（idx2 恒为 idx1 的严格最近邻，见 clip_plan 模块 docstring）。
所以最要紧的三条断言是：

* ``test_variant_specs_enumerates_only_nearest_neighbor_pairs``：只枚举最近邻可达对；
* ``test_tail_slot_pairs_invariant_across_variants``：窗口 ≥2 的**槽位**对跨全部同源
  变体逐条相同 —— 后 30 帧不是第二个变化因子；
* ``test_is_original_reproduces_original_bin_pairs``：is_original 变体的注入序列退化为
  原始 bin 对序列 —— 仍逐位复现官方 episode。

实测几何常量（``MEASURED_SLOT_XY_TRAIN`` / ``MEASURED_ORIGINAL_BIN_PAIRS_TRAIN``）内嵌在
本文件里且**只覆盖 train 的 8 个历史已验证源** —— 它们是回归锚点，不是数据集规模的真值来源。
33 源全量覆盖由 ``test_phase0_index_covers_all_selected_sources`` 做（有 Phase 0 产物才跑、
不硬编码总数）；本文件**不读 outputs/** 之外的例外仅此一条 artifact-gated 用例（无产物即 skip）。

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
    CANDIDATE_EPISODES_BY_SPLIT,
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
    SPLIT_BLOCK,
    SPLIT_CODE,
    SPLITS,
    TOPO_CROSS_ALIGNED,
    TOPO_CROSS_DIAGONAL,
    TOPO_SAME_COLUMN,
    VARIANT_BLOCK,
    bin_pairs,
    bin_pairs_from_slot_pairs,
    clip_visible_windows,
    decode_staging_episode,
    decode_variant_seed,
    load_slot_xy_index,
    nearest_neighbor,
    nearest_neighbor_margin,
    nearest_neighbor_pairs,
    native_window_slots,
    net_permutation,
    nominal_distance_video,
    pair_index,
    plan_table,
    select_sources,
    select_sources_by_split,
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


def _native_region4(task: str) -> list:
    """newtask-v2 10.0 之后，两个 Video 任务的 region4 原值移到模块级 NATIVE_SAMPLING。

    该字典同时是不传 sampling_config 时的运行默认值，``_load_scene`` 从实例副本读它，
    所以取值来源仍然唯一；这里跟着改读原值字典，判据（必须逐字是那个固定模板）不变。
    """
    path = REPO_ROOT / "src" / "robomme" / "robomme_env" / f"{task}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "NATIVE_SAMPLING":
                    native = ast.literal_eval(node.value)
                    return native["positions"]["containers"]["region4"]
    raise AssertionError(f"{task}: 模块级没有 NATIVE_SAMPLING")


def test_region4_video_is_the_fixed_template() -> None:
    """Video 的 region4 是固定字面量，REGION4_VIDEO 必须逐字一致。"""
    assert [list(point) for point in _native_region4("VideoUnmaskSwap")] == [
        [-0.05, -0.1],
        [-0.05, 0.1],
        [0.1, 0.1],
        [0.1, -0.1],
    ]
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


# ── 与各 split metadata 对账：入选源的 seed 与难度 ────────────────────────────

# 三重筛选（4-bin → k≥2 → split 内两 env 共同源号）后的最终源号；顺序即
# (SPLIT_CODE, episode) 排序。33 源 × 2 env = 66 个源单元。
EXPECTED_SOURCES_BY_SPLIT = {
    "train": [91, 95, 98, 99],
    "test": [3, 6, 7, 11, 15, 19, 23, 27, 30, 31, 35, 39, 43, 46, 47],
    "val": [3, 6, 7, 11, 14, 15, 19, 23, 27, 31, 35, 39, 43, 47],
}

# seed/难度/bin/k 锚点：train 全 8 行（ButtonUnmaskSwap/ep98 的 seed 是 16801 而非规则值
# 16800，历史 attempt 探针 —— 这正是必须读表的原因），另钉 3 行 test/val 证明 split 路径
# 段真的在被使用（val Button ep39/ep43 也是 attempt 尾号 seed：1073901/1074301）。
# 66 行全钉等于抄一遍 metadata 文件、什么都测不到，不做。
EXPECTED_SOURCE = {
    ("train", "VideoUnmaskSwap", 91): (14100, "hard", 4, 2),
    ("train", "VideoUnmaskSwap", 95): (14500, "hard", 4, 2),
    ("train", "VideoUnmaskSwap", 98): (14800, "medium", 4, 2),
    ("train", "VideoUnmaskSwap", 99): (14900, "hard", 4, 2),
    ("train", "ButtonUnmaskSwap", 91): (16100, "hard", 4, 3),
    ("train", "ButtonUnmaskSwap", 95): (16500, "hard", 4, 2),
    ("train", "ButtonUnmaskSwap", 98): (16801, "medium", 4, 2),
    ("train", "ButtonUnmaskSwap", 99): (16900, "hard", 4, 3),
    ("test", "VideoUnmaskSwap", 3): (550300, "hard", 4, 3),
    ("val", "ButtonUnmaskSwap", 39): (1073901, "hard", 4, 3),
    ("val", "ButtonUnmaskSwap", 43): (1074301, "hard", 4, 2),
}


@pytest.mark.parametrize("key", sorted(EXPECTED_SOURCE))
def test_source_episode_facts(key: tuple[str, str, int]) -> None:
    split, task, episode = key
    env_seed, difficulty, num_bins, swap_times = EXPECTED_SOURCE[key]
    src = source_episode(task, episode, split)
    assert src.split == split
    assert src.env_seed == env_seed
    assert src.difficulty == difficulty
    assert src.num_bins == num_bins
    assert src.swap_times == swap_times


def test_load_metadata_record_requires_valid_split() -> None:
    """split 必填且必须合法 —— 防「漏传即静默读错 split」。"""
    with pytest.raises(TypeError):
        source_episode("VideoUnmaskSwap", 91)  # 不给 split 直接 TypeError
    with pytest.raises(ValueError, match="未知 split"):
        source_episode("VideoUnmaskSwap", 91, "heldout")


# ── 源三重筛选与规模 ─────────────────────────────────────────────────────────


def test_select_sources_matches_expected_per_split() -> None:
    nested = select_sources_by_split()
    for split, expected in EXPECTED_SOURCES_BY_SPLIT.items():
        for task in EVAL_TASKS:
            got = [src.episode for src in nested[split][task]]
            assert got == expected, f"{task}/{split}: 筛选结果 {got} ≠ {expected}"
    assert sum(len(v) for v in EXPECTED_SOURCES_BY_SPLIT.values()) == 33


def test_select_sources_flat_order_is_split_then_episode() -> None:
    """扁平结果按 (SPLIT_CODE, episode) 升序 —— 与 merge 的密集重编号排序一致。"""
    selected = select_sources()
    for task in EVAL_TASKS:
        keys = [(SPLIT_CODE[src.split], src.episode) for src in selected[task]]
        assert keys == sorted(keys)
        assert len(selected[task]) == 33


def test_filters_actually_bite() -> None:
    """逐条验证三重筛选各自剔掉了谁 —— 防止筛选条件写反还恰好凑对总数。

    train 侧保留历史精确断言；test/val 侧用计算式断言（非空剔除、交集真变小），
    不硬编码 50 条的逐条清单。
    """
    unfiltered = {
        split: {
            task: [
                source_episode(task, ep, split)
                for ep in CANDIDATE_EPISODES_BY_SPLIT[split]
            ]
            for task in EVAL_TASKS
        }
        for split in SPLITS
    }
    for split in SPLITS:
        # 4-bin 门槛剔掉全部 easy（easy 恒 3-bin）
        for task in EVAL_TASKS:
            assert all(
                src.num_bins == 3
                for src in unfiltered[split][task]
                if src.difficulty == "easy"
            )
        # k≥2 门槛在每个 split 都真的剔掉了 4-bin 源（medium 才可能 k=1）
        dropped = [
            src.episode
            for src in unfiltered[split]["VideoUnmaskSwap"]
            if src.num_bins == REQUIRED_BINS and src.swap_times < MIN_SWAP_TIMES
        ]
        assert dropped, f"{split}: k≥2 门槛没剔掉任何源，筛选条件可疑"
    # train 精确回归：k≥2 剔掉 Video 的 ep90/94，共同源号剔掉 Button 独有的 ep90
    assert sorted(
        src.episode
        for src in unfiltered["train"]["VideoUnmaskSwap"]
        if src.num_bins == REQUIRED_BINS and src.swap_times < MIN_SWAP_TIMES
    ) == [90, 94]
    nested_loose = select_sources_by_split(require_common=False)
    assert [src.episode for src in nested_loose["train"]["ButtonUnmaskSwap"]] == [90, 91, 95, 98, 99]
    assert [src.episode for src in nested_loose["train"]["VideoUnmaskSwap"]] == [91, 95, 98, 99]
    # test/val：共同源号门槛真的在起作用（并集严格大于交集）
    nested_strict = select_sources_by_split()
    for split in ("test", "val"):
        loose_union = set(
            src.episode for task in EVAL_TASKS for src in nested_loose[split][task]
        )
        strict_common = set(
            src.episode for src in nested_strict[split]["VideoUnmaskSwap"]
        )
        assert strict_common < loose_union, f"{split}: 共同源号门槛没剔掉任何源"


# ── Phase 0 实测几何（内嵌常量，不读 outputs/；**train-only 回归锚点**）────────
#
# train 8 个历史已验证源 reset 后的槽位 xy，取自 Phase 0 控制跑的 geometry.slot_xy。
# 布局只由 env_seed 决定、逐位可复现，所以可以安全地当常量钉在这里；与实际 Phase 0
# 产物的对拍见 test_measured_layouts_match_phase0_index（有产物才跑）。
# ⚠ 刻意**不**扩到 test/val 的 25 个新源：那些值只在 Phase 0 之后才存在，抄进来就成了
# 产物的转录而非独立校验，且每次重跑 Phase 0 都要重贴 —— 33 源全量覆盖由
# test_phase0_index_covers_all_selected_sources 现算（不硬编码总数）。
MEASURED_SLOT_XY_TRAIN = {
    ("train", "ButtonUnmaskSwap", 91): ((0.018860617652535439, -0.032360583543777466), (0.037674009799957275, 0.14158430695533752), (0.13856323063373566, 0.16328300535678864), (0.1379207968711853, -0.045993141829967499)),
    ("train", "ButtonUnmaskSwap", 95): ((0.0028231116011738777, -0.014349059201776981), (-0.026936819776892662, 0.15235261619091034), (0.1182674914598465, 0.19348432123661041), (0.1070883646607399, -0.009289667010307312)),
    ("train", "ButtonUnmaskSwap", 98): ((0.038808993995189667, -0.016091369092464447), (0.0010299879359081388, 0.22210311889648438), (0.12315738946199417, 0.13342700898647308), (0.069320403039455414, -0.13129152357578278)),
    ("train", "ButtonUnmaskSwap", 99): ((-0.028430763632059097, -0.074804984033107758), (0.033607639372348785, 0.18174615502357483), (0.11400412768125534, 0.1101541668176651), (0.096989408135414124, -0.11219239234924316)),
    ("train", "VideoUnmaskSwap", 91): ((0.081310369074344635, 0.065327830612659454), (-0.053857926279306412, -0.076493784785270691), (-0.15639244019985199, -0.022627763450145721), (-0.026895113289356232, 0.11353651434183121)),
    ("train", "VideoUnmaskSwap", 95): ((-0.037683755159378052, 0.13056036829948425), (0.069486118853092194, 0.019286032766103745), (0.0034428178332746029, -0.13628381490707397), (-0.16626280546188354, -0.0019962657243013382)),
    ("train", "VideoUnmaskSwap", 98): ((0.034369964152574539, 0.1008264422416687), (0.085645034909248352, -0.12671147286891937), (-0.13782745599746704, -0.10730509459972382), (-0.13243746757507324, 0.097971305251121521)),
    ("train", "VideoUnmaskSwap", 99): ((-0.054652493447065353, 0.059143904596567154), (0.10435368120670319, 0.061266347765922546), (0.06396271288394928, -0.12674188613891602), (-0.092229895293712616, -0.037124276161193848)),
}

# 各源 Phase 0 实测的原始 bin 对序列（窗口 ≥2 的 idx2 只能实跑读回，静态算不出）
MEASURED_ORIGINAL_BIN_PAIRS_TRAIN = {
    ("train", "ButtonUnmaskSwap", 91): ((1, 2), (1, 2), (0, 3)),
    ("train", "ButtonUnmaskSwap", 95): ((0, 3), (1, 2)),
    ("train", "ButtonUnmaskSwap", 98): ((1, 2), (1, 2)),
    ("train", "ButtonUnmaskSwap", 99): ((0, 3), (1, 2), (0, 3)),
    ("train", "VideoUnmaskSwap", 91): ((0, 3), (1, 2)),
    ("train", "VideoUnmaskSwap", 95): ((0, 1), (0, 2)),
    ("train", "VideoUnmaskSwap", 98): ((0, 3), (1, 2)),
    ("train", "VideoUnmaskSwap", 99): ((0, 1), (0, 1)),
}

# 由上面几何按严格 argmin 推出的合法对集合 —— 本轮数据集的变体空间真值
EXPECTED_LEGAL_PAIRS_TRAIN = {
    ("train", "ButtonUnmaskSwap", 91): [(0, 3), (1, 2)],
    ("train", "ButtonUnmaskSwap", 95): [(0, 3), (1, 2)],
    ("train", "ButtonUnmaskSwap", 98): [(0, 3), (1, 2)],
    ("train", "ButtonUnmaskSwap", 99): [(0, 3), (1, 2)],
    ("train", "VideoUnmaskSwap", 91): [(0, 3), (1, 2)],
    ("train", "VideoUnmaskSwap", 95): [(0, 1), (0, 3), (1, 2)],
    ("train", "VideoUnmaskSwap", 98): [(0, 3), (1, 2), (2, 3)],
    ("train", "VideoUnmaskSwap", 99): [(0, 1), (0, 3), (2, 3)],
}

# train 子集的历史真值（回归锚点）：Video 11 + Button 8 = 19 条
EXPECTED_TRAIN_CLIPS = 19


def test_plan_table_train_subset_still_totals_19() -> None:
    """train 子集（历史 8 源）的规模回归：扩源不得改变 train 侧的枚举结果。"""
    table = plan_table(splits=("train",), geometry=MEASURED_SLOT_XY_TRAIN)
    assert table["geometry_available"] is True
    per_task: dict[str, int] = {task: 0 for task in EVAL_TASKS}
    for row in table["rows"]:
        assert row["split"] == "train"
        per_task[row["task"]] += row["variant_count"]
    assert per_task["VideoUnmaskSwap"] == 11
    assert per_task["ButtonUnmaskSwap"] == 8
    assert table["total"] == EXPECTED_TRAIN_CLIPS
    # 每源 2~3 条，由该源布局的最近邻结构决定（不再是恒 6）
    assert [row["variant_count"] for row in table["rows"]] == [2, 3, 3, 3, 2, 2, 2, 2]
    assert all(row["variant_count_upper_bound"] == 6 for row in table["rows"])


def test_plan_table_without_geometry_reports_upper_bound_only() -> None:
    """没有实测几何时算不出真实变体数 —— 必须给 None，不能给一个像真值的全枚举总数。"""
    table = plan_table()
    assert table["geometry_available"] is False
    assert table["total"] is None
    # 33 源 × 2 env × C(4,2)=6 —— 上界随源集合计算，不是真值
    assert table["total_upper_bound"] == 33 * 2 * 6
    assert all(row["variant_count"] is None for row in table["rows"])
    assert all(row["legal_pairs"] is None for row in table["rows"])
    # train-only 调用给出历史上界 48
    assert plan_table(splits=("train",))["total_upper_bound"] == 48


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
ORIGINAL_EP91 = MEASURED_ORIGINAL_BIN_PAIRS_TRAIN[("train", "ButtonUnmaskSwap", 91)]
SLOT_XY_EP91 = MEASURED_SLOT_XY_TRAIN[("train", "ButtonUnmaskSwap", 91)]


def _spec_fixture():
    src = source_episode("ButtonUnmaskSwap", 91, "train")
    return src, variant_specs(src, ORIGINAL_EP91, SLOT_XY_EP91)


def test_variant_specs_enumerates_only_nearest_neighbor_pairs() -> None:
    """★ 本轮核心判据：只枚举最近邻可达对，且 variant_idx 是槽位对的字典序下标。"""
    src, specs = _spec_fixture()
    legal = EXPECTED_LEGAL_PAIRS_TRAIN[("train", "ButtonUnmaskSwap", 91)]
    assert len(specs) == len(legal)
    assert sorted(spec.event_slots for spec in specs) == legal
    assert [spec.variant_idx for spec in specs] == [pair_index(pair) for pair in legal]
    assert all(spec.swap_times == src.swap_times for spec in specs)
    # 对角对结构上进不来（它们从来不是任何 bin 的最近邻）
    assert not any(spec.event_slots in ((0, 2), (1, 3)) for spec in specs)


@pytest.mark.parametrize("key", sorted(MEASURED_SLOT_XY_TRAIN))
def test_measured_layouts_yield_expected_legal_pairs(key: tuple[str, int]) -> None:
    """逐源钉死合法对集合与条数 —— 数据集规模的真值来源。"""
    legal = nearest_neighbor_pairs(MEASURED_SLOT_XY_TRAIN[key])
    assert legal == EXPECTED_LEGAL_PAIRS_TRAIN[key]
    assert 2 <= len(legal) <= 3


def test_measured_train_layouts_total_19_clips() -> None:
    total = sum(len(pairs) for pairs in EXPECTED_LEGAL_PAIRS_TRAIN.values())
    assert total == EXPECTED_TRAIN_CLIPS
    video = sum(len(v) for k, v in EXPECTED_LEGAL_PAIRS_TRAIN.items() if k[1] == "VideoUnmaskSwap")
    assert video == 11


@pytest.mark.parametrize("key", sorted(MEASURED_ORIGINAL_BIN_PAIRS_TRAIN))
def test_original_first_pair_is_always_legal(key: tuple[str, int]) -> None:
    """原版 idx2 本就是最近邻回填 ⇒ 原始首对必落在合法集合内（8/8）。

    这条不成立就说明本模块的最近邻复刻与 env 实际行为脱节。
    """
    first_slots = slot_pairs_from_bin_pairs(MEASURED_ORIGINAL_BIN_PAIRS_TRAIN[key], 4)[0]
    assert first_slots in EXPECTED_LEGAL_PAIRS_TRAIN[key]


def test_measured_layouts_match_phase0_index() -> None:
    """有 Phase 0 产物时，与内嵌常量逐位对拍；没有则跳过（lightweight 不依赖数据集）。"""
    path = (
        REPO_ROOT
        / "scripts"
        / "data-generation-MotionJEPALabel"
        / "outputs"
        / "phase0"
        / "original_index.json"
    )
    if not path.exists():
        pytest.skip("没有 Phase 0 产物")
    measured = load_slot_xy_index(path)
    if not measured:
        pytest.skip("Phase 0 索引是旧版（记录无 split 字段），等重跑后再对拍")
    for key, expected in MEASURED_SLOT_XY_TRAIN.items():
        assert key in measured, f"Phase 0 索引里缺 {key}"
        for actual_row, expected_row in zip(measured[key], expected):
            assert tuple(actual_row[:2]) == tuple(expected_row)


def test_tail_slot_pairs_invariant_across_variants() -> None:
    """★ 宗旨判据：窗口 ≥2 的槽位对跨同源全部变体逐条相同。

    这保证后 30 帧里第二次 swap 的 teleport 起止位置、被锁定旁观 bin 的位置集合
    完全一致 —— 后段不是第二个变化因子。
    """
    _, specs = _spec_fixture()
    tails = {spec.slot_pairs[1:] for spec in specs}
    assert len(tails) == 1, f"窗口 ≥2 的槽位对出现了 {len(tails)} 种，应恒为 1 种"
    assert tails.pop() == slot_pairs_from_bin_pairs(ORIGINAL_EP91, 4)[1:]


def test_tail_bin_pairs_follow_first_swap() -> None:
    """窗口 ≥2 的**注入 bin 对**本来就该跟着第一次 swap 变 —— 那是槽位换算的结果。

    这条原先挂在上面那个用例末尾（断言同源变体的 tail bin 对不止一种），但最近邻约束
    下每源只剩 2~3 条，完全可能全部撞成同一种（实测 Button ep91 的两条变体 tail 都是
    ((1,2),(0,3))）。所以改成对换算函数本身举手算样例，不依赖合法集合的大小。
    """
    tail = ((1, 2), (0, 3))
    assert bin_pairs_from_slot_pairs(((0, 1),) + tail, 4) != bin_pairs_from_slot_pairs(
        ((0, 2),) + tail, 4
    )


def test_is_original_reproduces_original_bin_pairs() -> None:
    """★ 宗旨判据：恰有 1 条 is_original，且其注入序列退化为原始 bin 对序列。"""
    _, specs = _spec_fixture()
    originals = [spec for spec in specs if spec.is_original]
    assert len(originals) == 1
    assert originals[0].bin_pairs == ORIGINAL_EP91
    assert originals[0].event_slots == ORIGINAL_EP91[0]


def test_variant_specs_rejects_length_mismatch() -> None:
    src = source_episode("ButtonUnmaskSwap", 91, "train")  # k=3
    with pytest.raises(ValueError):
        variant_specs(src, ((0, 1), (2, 3)), SLOT_XY_EP91)  # 只给了 2 段


def test_variant_specs_rejects_illegal_original_first_pair() -> None:
    """原始首对不在合法集合内 ⇒ fail-loud，绝不静默产出一个没有 is_original 的源。"""
    src = source_episode("ButtonUnmaskSwap", 91, "train")  # k=3
    with pytest.raises(ValueError, match="不在最近邻合法集合"):
        variant_specs(src, ((0, 2), (1, 2), (0, 3)), SLOT_XY_EP91)  # (0,2) 是对角对


def test_variant_specs_requires_matching_slot_count() -> None:
    src = source_episode("ButtonUnmaskSwap", 91, "train")
    with pytest.raises(ValueError):
        variant_specs(src, ORIGINAL_EP91, SLOT_XY_EP91[:3])


# ── 最近邻：与 env 运行时回填逐字同构 ────────────────────────────────────────


def test_nearest_neighbor_breaks_ties_toward_lowest_index() -> None:
    """env 的扫描是严格 ``dist < closest_dist`` + 按下标升序 ⇒ 平局取下标最小。

    写成 ``<=`` 就变成取下标最大。实测布局的 argmin 余量都在 0.0089 以上、不会触发平局，
    所以这条写反了**数据发现不了**，只能靠本用例钉住。
    """
    layout = ((0.0, 0.0), (1.0, 0.0), (-1.0, 0.0), (5.0, 5.0))
    assert nearest_neighbor(layout, 0) == 1  # slot1 与 slot2 等距，取下标小的


def test_nearest_neighbor_pairs_size_bounds() -> None:
    """4 槽位下合法对数恒落在 [2,3]：全局最近的一对必互为最近邻并去重成 1 对。"""
    import random

    rng = random.Random(0)
    for _ in range(500):
        layout = tuple((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3)) for _ in range(4))
        assert 2 <= len(nearest_neighbor_pairs(layout)) <= 3


def test_diagonal_can_be_nearest_neighbor_in_principle() -> None:
    """★ 反例存在性：cross_diagonal 在本 8 源上恒为空是**实测事实、不是几何必然**。

    有了这条，后人就不会把「只有两个拓扑类」硬编码成不变量。
    """
    # 把 slot0 与 slot2（对角）摆得比任何同列/同侧对都近
    layout = ((0.0, 0.0), (0.0, 0.5), (0.01, 0.0), (0.5, 0.5))
    legal = nearest_neighbor_pairs(layout)
    assert (0, 2) in legal
    assert topo_class((0, 2)) == TOPO_CROSS_DIAGONAL


def test_nearest_neighbor_margin_matches_manual() -> None:
    layout = ((0.0, 0.0), (1.0, 0.0), (3.0, 0.0), (7.0, 0.0))
    margins = nearest_neighbor_margin(layout)
    assert margins[0] == pytest.approx(2.0)  # slot0：最近 1.0、次近 3.0
    assert margins[1] == pytest.approx(1.0)  # slot1：最近 1.0、次近 2.0


def test_native_window_slots_tracks_the_moved_bin() -> None:
    """原版后续窗口的 idx1 是一个固定的 **bin**，窗口 1 可能已把它挪到别的槽位。

    手算样例：NN 图为 0↔3、1↔2（Button 型完美配对）时，无论窗口 1 换 (0,3) 还是 (1,2)，
    bin 1 的最近邻槽位对恒为 (1,2)；而 NN 图非配对时（Video ep99 型 NN=[3,0,3,0]），
    bin 0 被挪到 slot3 后会给出 (0,3) 而不是原始的 (0,1)。
    """
    paired = ((0.0, 0.0), (0.0, 0.5), (0.02, 0.5), (0.02, 0.0))  # NN: 0↔3, 1↔2
    assert native_window_slots(paired, 1, [(0, 3)]) == (1, 2)
    assert native_window_slots(paired, 1, [(1, 2)]) == (1, 2)

    xy99 = MEASURED_SLOT_XY_TRAIN[("train", "VideoUnmaskSwap", 99)]
    assert nearest_neighbor(xy99, 0) == 3 and nearest_neighbor(xy99, 1) == 0
    assert native_window_slots(xy99, 0, [(0, 1)]) == (0, 1)   # 与原始一致
    assert native_window_slots(xy99, 0, [(0, 3)]) == (0, 3)   # 偏离原始的 (0,1)
    assert native_window_slots(xy99, 0, [(2, 3)]) == (0, 3)   # 同上


def test_later_windows_deviation_count_is_four_on_train_sources() -> None:
    """★ 已知取舍的量化（**train-only 回归锚点**）：窗口 ≥2 按槽位固定，与原版最近邻
    规则在 train 19 条中的 4 条上不重合。

    这不是缺陷 —— 用户拍板「约束只作用于第一次 swap」，窗口 ≥2 的固定是后 30 帧跨变体
    一致（判据 5）的前提，两者不可兼得。事件本身仍严格落在原版可达空间内。
    全源集合（含 test/val）的偏离计数由 make_clip_labels 逐条量化、verify_clips 报告，
    不在这里钉死。
    """
    idx1_w2 = {  # Phase 0 实测的 original_idx1[1]
        ("train", "ButtonUnmaskSwap", 91): 1, ("train", "ButtonUnmaskSwap", 95): 1,
        ("train", "ButtonUnmaskSwap", 98): 1, ("train", "ButtonUnmaskSwap", 99): 2,
        ("train", "VideoUnmaskSwap", 91): 1, ("train", "VideoUnmaskSwap", 95): 2,
        ("train", "VideoUnmaskSwap", 98): 1, ("train", "VideoUnmaskSwap", 99): 0,
    }
    deviating = []
    for key, slot_xy in sorted(MEASURED_SLOT_XY_TRAIN.items()):
        fixed = slot_pairs_from_bin_pairs(MEASURED_ORIGINAL_BIN_PAIRS_TRAIN[key], 4)[1]
        for first in EXPECTED_LEGAL_PAIRS_TRAIN[key]:
            if native_window_slots(slot_xy, idx1_w2[key], [first]) != fixed:
                deviating.append((key, first))
    assert len(deviating) == 4
    assert all(key[1] == "VideoUnmaskSwap" for key, _ in deviating)


def test_pair_index_is_inverse_of_bin_pairs() -> None:
    for idx, pair in enumerate(bin_pairs(4)):
        assert pair_index(pair) == idx
        assert pair_index((pair[1], pair[0])) == idx  # 无序对，顺序无关


def test_bin_pairs_still_returns_all_six() -> None:
    """★ 回归守卫：bin_pairs 必须保持「全部对」语义。

    swap_inject.slot_geometry 靠它枚举全部 6 对的几何协变量；一旦有人把它改成「只返回
    合法对」，merge_clip_h5 取 pairs[f"{i}{j}"] 会缺项、pair_distance 静默变 None，
    要等到出图阶段才炸。
    """
    assert bin_pairs(4) == [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    assert len(bin_pairs(4)) == 6


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
    """staging 三段编码（split 位 + episode 位 + 变体位）往返与守卫。"""
    assert staging_episode("train", 91, 5) == 91005
    assert staging_episode("test", 3, 2) == 1_003_002
    assert staging_episode("val", 3, 2) == 2_003_002
    assert variant_seed(14100, 5) == 14100005
    assert decode_staging_episode(91005) == ("train", 91, 5)
    assert decode_staging_episode(1_003_002) == ("test", 3, 2)
    assert decode_staging_episode(2_003_002) == ("val", 3, 2)
    assert decode_variant_seed(14100005) == (14100, 5)
    for split in SPLITS:
        for src_ep in (0, 3, 91, 99):
            for idx in (0, 5, VARIANT_BLOCK - 1):
                assert decode_staging_episode(staging_episode(split, src_ep, idx)) == (
                    split,
                    src_ep,
                    idx,
                )
    with pytest.raises(ValueError):
        staging_episode("train", 91, VARIANT_BLOCK)
    with pytest.raises(ValueError):
        staging_episode("train", SPLIT_BLOCK // VARIANT_BLOCK, 0)  # episode 位越界
    with pytest.raises(ValueError):
        staging_episode("heldout", 91, 0)  # 未知 split
    # SPLIT_CODE 与 SPLITS 自洽（编码连续且从 0 起，是 decode 穷举的前提）
    assert sorted(SPLIT_CODE.values()) == list(range(len(SPLITS)))
    assert set(SPLIT_CODE) == set(SPLITS)


def test_variant_seed_unique_and_disjoint_from_env_seeds() -> None:
    """跨三个 split 的全部 33 源 × 2 env × 全部 6 个 variant_idx（几何无关的最坏情况），
    variant_seed 互异且不与任何源 env_seed 撞号。

    这就是「variant_seed 不编码 split」决定的守卫之一：唯一性靠三个 split 的 env_seed
    数值域互不相交，一旦 metadata 变化打破该前提，这条会先炸。
    staging_episode 的唯一性由编码本身保证（split 位），顺带全组合断言一遍。
    """
    selected = select_sources()
    env_seeds = {src.env_seed for task in EVAL_TASKS for src in selected[task]}
    assert len(env_seeds) == 33 * 2  # 66 个源单元的 env_seed 本身互异
    seeds: set[int] = set()
    stagings: set[int] = set()
    count = 0
    for task in EVAL_TASKS:
        for src in selected[task]:
            for idx in range(len(bin_pairs(REQUIRED_BINS))):
                seed = variant_seed(src.env_seed, idx)
                assert seed not in seeds
                seeds.add(seed)
                stagings.add(staging_episode(src.split, src.episode, idx))
                count += 1
    assert count == 33 * 2 * 6
    assert not seeds & env_seeds
    # staging 在 (split, episode, idx) 维度去重后 = 33 源去掉「两 env 同 split 同源号」
    # 的重复 —— 每源两 env 的 staging 相同（同 split 同 ep 同 idx），所以是 33 * 6
    assert len(stagings) == 33 * 6


def test_phase0_index_covers_all_selected_sources() -> None:
    """artifact-gated 全量覆盖：有（新版）Phase 0 索引时，66 个源单元逐一在场且几何合法。

    不硬编码任何总数之外的实测值 —— 合法对大小 ∈ [2,3]、原始首对落在合法集合内、
    variant_idx 编号往返自洽，全部现算。没有产物（或产物是旧版无 split 字段）则 skip。
    """
    import json

    path = (
        REPO_ROOT
        / "scripts"
        / "data-generation-MotionJEPALabel"
        / "outputs"
        / "phase0"
        / "original_index.json"
    )
    if not path.exists():
        pytest.skip("没有 Phase 0 产物")
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = {
        (str(r["split"]), str(r["task"]), int(r["episode"])): r
        for r in payload.get("records", [])
        if r.get("split")
    }
    if not records:
        pytest.skip("Phase 0 索引是旧版（记录无 split 字段），等重跑后再对拍")
    selected = select_sources()
    expected_keys = {
        (src.split, task, src.episode) for task in EVAL_TASKS for src in selected[task]
    }
    assert set(records) == expected_keys, (
        f"Phase 0 覆盖与筛选结果不一致：缺 {sorted(expected_keys - set(records))[:5]}…，"
        f"多 {sorted(set(records) - expected_keys)[:5]}…"
    )
    for key, record in sorted(records.items()):
        slot_xy = record["geometry"]["slot_xy"]
        legal = nearest_neighbor_pairs(slot_xy)
        assert 2 <= len(legal) <= 3, f"{key}: 合法对数 {len(legal)} 越界"
        original_first = slot_pairs_from_bin_pairs(
            [tuple(p) for p in record["original_bin_pairs"]], len(slot_xy)
        )[0]
        assert original_first in legal, f"{key}: 原始首对 {original_first} 不在 {legal}"
        for pair in legal:
            assert bin_pairs(len(slot_xy))[pair_index(pair, len(slot_xy))] == pair


def test_signature_format() -> None:
    assert signature_of(((0, 1), (2, 3))) == "01|23"


def test_clip_job_paths_distinct_across_splits() -> None:
    """test/val 同号源（如双方都有 ep3）的三条产物路径与 h5 组名必须互异。

    control 模式的 wrapper_episode = src_episode 跨 split 同号，路径唯一性只能来自
    文件名里的 seed（variant_seed = env_seed，全局唯一）；clip 模式则由 staging 编码
    的 split 位保证。两条腿分别断言。
    """
    from clip_worker import ClipJob, clip_h5_path, raw_h5_path, trace_path

    def control_job(split: str, env_seed: int) -> ClipJob:
        return ClipJob(
            task="VideoUnmaskSwap", split=split, src_episode=3, variant_idx=-1,
            env_seed=env_seed, variant_seed=env_seed, wrapper_episode=3,
            difficulty="hard", num_bins=4, mode="control", bin_pairs=None,
            slot_pairs=None, is_original=True, attempt=0,
            output_root="/tmp/x", repo_root="/tmp/x",
        )

    test_job = control_job("test", 550300)
    val_job = control_job("val", 1050300)
    root = Path("/tmp/x")
    for helper in (raw_h5_path, clip_h5_path, trace_path):
        assert helper(root, test_job) != helper(root, val_job), helper.__name__
    assert test_job.label != val_job.label
    # clip 模式：同 variant_idx 的 staging_episode 因 split 位互异
    assert staging_episode("test", 3, 2) != staging_episode("val", 3, 2)
