"""候选规格「每组 k 个 100 条 block」扩容的定向测试（2026-09-12 每 env 400 条交付）。

扩容的全部价值都压在两条不变量上，这里逐条钉死：

* **向后兼容**：``blocks=1`` 的文档必须与 09 冻结逐字节相同；``blocks>1`` 时前 100 条
  必须与 09 逐条散列相同——block 0 的随机流标签没变，追加 block 不动已冻结的部分。
* **每个 block 自成一份均衡样本**：粗箱／批次覆盖、独立离散量的配额都按 block 切片判，
  而不是把 200 条并起来判（两个各自 spread≤1 的 block 合并后可能 spread=2，整组判会假阳）。

    uv run --no-sync python -m pytest tests/lightweight/test_injection_blocks.py -q
"""

from __future__ import annotations

import functools
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "src", REPO_ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import generate_dataset_newseed as generator  # noqa: E402

from scripts.injection import campaign, specs  # noqa: E402
from scripts.injection.categories import legal_categories, observed_values  # noqa: E402
from scripts.injection.contract import load_contract  # noqa: E402
from scripts.injection.sampling import COARSE_BINS, GROUP_SIZE  # noqa: E402

pytestmark = pytest.mark.lightweight

CONFIG_DIR = REPO_ROOT / "scripts" / "configs" / "newtask-v2"
SAMPLING = json.loads((CONFIG_DIR / "native_sampling.json").read_text(encoding="utf-8"))
CONTRACT = load_contract(CONFIG_DIR / "injection_contract_v3.json")
SEED = specs.DEFAULT_SEED
#: 09 运行的冻结规格：每组 100 条、14 组，是「扩容不动旧条目」的比对基准。
RUN_09 = REPO_ROOT / "artifacts" / "injection" / "20260912-contract-v3-09"

needs_09 = pytest.mark.skipif(not RUN_09.is_dir(), reason="09 运行的冻结规格不在工作区")


@functools.lru_cache(maxsize=None)
def build(task: str, difficulty: str, blocks: int = 1):
    """按组缓存一次生成结果——同一组在多条用例里复用，整份文件只付一次生成开销。"""
    return specs.build_group(task, difficulty, SAMPLING, CONTRACT, SEED, blocks=blocks)


def frozen_doc(task: str, difficulty: str) -> dict:
    return json.loads((RUN_09 / "specs" / task / f"{difficulty}.json").read_text(encoding="utf-8"))


# ── 一、与 09 冻结的向后兼容 ────────────────────────────────────────────────
@needs_09
@pytest.mark.parametrize(("task", "difficulty"), [("RouteStick", "easy"), ("BinFill", "easy")])
def test_blocks等于一时文档与09冻结逐字节相同(task, difficulty):
    """默认 ``blocks=1`` 不得有任何行为漂移：整份文档（含不写 ``blocks`` 键）逐字节相同。"""
    frozen = frozen_doc(task, difficulty)
    rebuilt = build(task, difficulty, 1).as_document(frozen["sampling_config_sha256"])
    assert json.dumps(rebuilt, sort_keys=True) == json.dumps(frozen, sort_keys=True)


@needs_09
@pytest.mark.parametrize(("task", "difficulty"), [("RouteStick", "easy"), ("VideoRepick", "easy")])
def test_扩块后前一百条逐条散列与09冻结相同(task, difficulty):
    """block 0 的随机流标签原样保留，所以扩到 200 条后前 100 条一条不动。"""
    result = build(task, difficulty, 2)
    frozen = frozen_doc(task, difficulty)["episodes"]
    assert len(result.episodes) == 2 * GROUP_SIZE
    for left, right in zip(frozen, result.episodes[:GROUP_SIZE]):
        assert left["spec_sha256"] == right["spec_sha256"], left["episode"]
    # episode 号在全局连续：第二个 block 从 100 起
    assert result.episodes[GROUP_SIZE]["episode"] == GROUP_SIZE


def test_block可用自身标签单独复现():
    """blocks=2 的第 2 个 block 与 blocks=3 时的第 2 个 block 必须逐条相同——
    追加第 3 个 block 不会改动已经冻结的前两个。"""
    two = build("RouteStick", "easy", 2)
    three = build("RouteStick", "easy", 3)
    assert len(three.episodes) == 3 * GROUP_SIZE
    left = [item["spec_sha256"] for item in two.episodes[GROUP_SIZE : 2 * GROUP_SIZE]]
    right = [item["spec_sha256"] for item in three.episodes[GROUP_SIZE : 2 * GROUP_SIZE]]
    assert left == right
    # 两个 block 各自独立：block 1 不是 block 0 的复制
    assert left != [item["spec_sha256"] for item in two.episodes[:GROUP_SIZE]]


# ── 二、每个 block 自成一份均衡样本 ─────────────────────────────────────────
@pytest.mark.parametrize(("task", "difficulty"), [("RouteStick", "easy"), ("VideoRepick", "easy")])
def test_每个block内十个粗箱各十条且每批覆盖十箱(task, difficulty):
    """连续量的分层判据按 block 切片成立：每 100 条里每个粗箱恰 10 条、每批 10 条覆盖 10 箱。"""
    result = build(task, difficulty, 2)
    names = list(result.episodes[0]["sampling_cells"])
    assert names, "该组没有连续量，用例选错了"
    for block in range(2):
        chunk = result.episodes[block * GROUP_SIZE : (block + 1) * GROUP_SIZE]
        for name in names:
            coarse = [int(item["sampling_cells"][name][0]) for item in chunk]
            assert Counter(coarse) == {b: GROUP_SIZE // COARSE_BINS for b in range(COARSE_BINS)}, (name, block)
            for batch in range(COARSE_BINS):
                window = coarse[batch * COARSE_BINS : (batch + 1) * COARSE_BINS]
                assert len(set(window)) == COARSE_BINS, (name, block, batch)


@pytest.mark.parametrize(("task", "difficulty"), [("RouteStick", "easy"), ("VideoRepick", "easy")])
def test_独立离散量按block切片计数差不超过一(task, difficulty):
    """独立类别的配额也按 block 判：按完整合法类别补零后，每个 block 内计数差 ≤1。"""
    result = build(task, difficulty, 2)
    categories = legal_categories(task, difficulty, CONTRACT)
    assert categories["independent"], "该组没有独立离散量，用例选错了"
    for field, legal in categories["independent"].items():
        for block in range(2):
            observed: Counter = Counter()
            for record in result.episodes[block * GROUP_SIZE : (block + 1) * GROUP_SIZE]:
                for value in observed_values(task, record).get(field, []):
                    observed[specs.canonical_json(value)] += 1
            table = {specs.canonical_json(value): observed.get(specs.canonical_json(value), 0) for value in legal}
            assert max(table.values()) - min(table.values()) <= 1, (field, block, table)


def test_合并两个block后三类量的计数差会到二():
    """这正是必须按 block 切片判的理由：三类量每个 block 34/33/33（各自 spread=1），
    合并 200 条成 68/66/66（spread=2）。整组判会把完全合法的扩容判成配额不达标。"""
    task, difficulty = "VideoRepick", "easy"
    result = build(task, difficulty, 2)
    field = "num_repeats"
    legal = legal_categories(task, difficulty, CONTRACT)["independent"][field]
    assert len(legal) == 3
    merged: Counter = Counter()
    for record in result.episodes:
        for value in observed_values(task, record).get(field, []):
            merged[specs.canonical_json(value)] += 1
    table = {specs.canonical_json(value): merged.get(specs.canonical_json(value), 0) for value in legal}
    assert max(table.values()) - min(table.values()) == 2, table


# ── 三、文档与统计的形状 ────────────────────────────────────────────────────
@needs_09
def test_文档在blocks为一时不带blocks字段而大于一时带():
    frozen_sha = frozen_doc("RouteStick", "easy")["sampling_config_sha256"]
    single = build("RouteStick", "easy", 1).as_document(frozen_sha)
    multi = build("RouteStick", "easy", 2).as_document(frozen_sha)
    assert "blocks" not in single
    assert multi["blocks"] == 2
    assert set(multi) - set(single) == {"blocks"}


def test_per_block统计只在多block时存在():
    single = build("RouteStick", "easy", 1)
    multi = build("RouteStick", "easy", 2)
    assert "per_block" not in single.stats
    assert len(multi.stats["per_block"]) == 2
    keys = {"candidates_tried", "rejected_geometry", "rejected_contact",
            "rejected_numerical_boundary", "rejected_uncertified", "max_candidates_used"}
    for entry in multi.stats["per_block"]:
        assert keys <= set(entry)
    # 逐 block 计数是增量，合起来不超过整组累计值
    assert sum(entry["candidates_tried"] for entry in multi.stats["per_block"]) == multi.stats["candidates_tried"]


# ── 四、生产加载器接受可选的 blocks 键 ──────────────────────────────────────
def _minimal_record(episode: int = 0) -> dict:
    """一条形状合法的最小 BinFill 记录（与 test_episode_specs.py 同源），散列由 seal 现算。"""
    return specs.seal(
        {
            "episode": episode,
            "task": "BinFill",
            "difficulty": "hard",
            "layout": {
                "dynamic": True,
                "button_xy": [-0.21, 0.08],
                "board": {"xy": [0.05, -0.12], "yaw_deg": 7.5},
                "cubes": [{"object_id": "cube_red_0", "color": "red", "color_index": 0, "xy": [-0.2, 0.15], "yaw_rad": 1.1}],
            },
            "objects": {
                "colors_present": ["red"],
                "initialize_color_order": ["blue", "red", "green"],
                "target_pool": ["red"],
                "spawn_total": 1,
                "put_in_total": 1,
                "spawn_count": {"red": 1},
                "target_count": {"red": 1},
            },
            "actions": [{"pick": "cube_red_0", "put_in": True}],
            "sampling_cells": {"button_x": [0, 0]},
        }
    )


def _minimal_document(records: list[dict]) -> dict:
    return {
        "spec_schema_version": 1,
        "task": "BinFill",
        "difficulty": "hard",
        "generator_seed": SEED,
        "derived_seed": 1,
        "generator_version": "injection-specs-1",
        "sampling_config_sha256": "0" * 64,
        "episodes": records,
    }


def _write(tmp_path: Path, payload: dict, name: str = "hard.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_规格文档的可选blocks字段被生产加载器接受(tmp_path):
    """扩容后的文档多一个顶层 ``blocks`` 键，生成器必须照读；其余未知键仍要拒。"""
    payload = _minimal_document([_minimal_record(0), _minimal_record(100)])
    payload["blocks"] = 2
    document = generator.load_spec_document(_write(tmp_path, payload))
    assert sorted(document["records"]) == [0, 100]
    payload["foo"] = 1
    with pytest.raises(generator.EpisodeSpecError, match="未知顶层字段"):
        generator.load_spec_document(_write(tmp_path, payload, "hard2.json"))


# ── 五、check 侧的判据按 blocks 放大 ────────────────────────────────────────
def _fake_documents(count: int, blocks: int, *, bad_episode: int | None = None) -> dict:
    """造一组条数／blocks 可控的假文档；每条都过 ``record_sha256 == spec_sha256``。"""
    episodes = []
    for index in range(count):
        number = bad_episode if (bad_episode is not None and index == count - 1) else index
        episodes.append(specs.seal({"episode": number, "task": "RouteStick", "difficulty": "easy"}))
    doc = {"episodes": episodes}
    if blocks != 1:
        doc["blocks"] = blocks
    return {("RouteStick", "easy"): doc}


def test_scope判据按blocks放大episode区间():
    verdicts = campaign.Verdicts()
    campaign._check_scope(_fake_documents(2 * GROUP_SIZE, 2), verdicts)
    record = verdicts.records[-1]
    assert record["status"] == "PASS" and record["specs"] == 200 and record["blocks"] == "2"

    # 越界的 episode 号（200 不在 range(200) 里）
    verdicts = campaign.Verdicts()
    campaign._check_scope(_fake_documents(2 * GROUP_SIZE, 2, bad_episode=2 * GROUP_SIZE), verdicts)
    assert verdicts.records[-1]["status"] == "FAIL"

    # blocks 写 1 而实际 200 条：条数与声明不符，同样必须 FAIL
    verdicts = campaign.Verdicts()
    campaign._check_scope(_fake_documents(2 * GROUP_SIZE, 1), verdicts)
    assert verdicts.records[-1]["status"] == "FAIL"

    # 单 block 的判定行逐字不变：不打 blocks 字段
    verdicts = campaign.Verdicts()
    campaign._check_scope(_fake_documents(GROUP_SIZE, 1), verdicts)
    assert verdicts.records[-1]["status"] == "PASS" and "blocks" not in verdicts.records[-1]


def test_可复现判据在重建条数不一致时必须失败(monkeypatch):
    """``zip`` 会静默截断：重建只有 50 条时若不单独比条数，100 条的文档会被判成 PASS。"""
    documents = _fake_documents(GROUP_SIZE, 1)

    def fake_build_group(task, difficulty, sampling, contract, seed, *, blocks=1):
        return specs.GroupResult(task, difficulty, seed, 0, list(documents[(task, difficulty)]["episodes"][:50]))

    monkeypatch.setattr(campaign, "build_group", fake_build_group)
    verdicts = campaign.Verdicts()
    campaign._check_reproducible(documents, SAMPLING, CONTRACT, SEED, verdicts)
    record = verdicts.records[-1]
    assert record["status"] == "FAIL" and record["differences"] >= 50 and record["compared"] == 50


def test_配额判据按block切片():
    """合法的 blocks=2 结果必须 PASS，且 report 形状换成 ``{"blocks": [...]}``。"""
    result = build("RouteStick", "easy", 2)
    documents = {("RouteStick", "easy"): result.as_document("0" * 64)}
    verdicts = campaign.Verdicts()
    report = campaign._check_quota(documents, CONTRACT, verdicts)
    record = verdicts.records[-1]
    assert record["status"] == "PASS" and record["blocks"] == "2"
    entry = report["RouteStick/easy"]
    assert list(entry) == ["blocks"] and len(entry["blocks"]) == 2
    for block_report in entry["blocks"]:
        assert set(block_report) == {"independent", "coupled", "continuous"}
        assert all(item["ok"] for item in block_report["continuous"].values())

    # blocks=1 时 report 形状与此前逐字相同（直接就是那份组报告，不套 blocks 层）
    single = {("RouteStick", "easy"): build("RouteStick", "easy", 1).as_document("0" * 64)}
    verdicts = campaign.Verdicts()
    report = campaign._check_quota(single, CONTRACT, verdicts)
    assert "blocks" not in verdicts.records[-1]
    assert set(report["RouteStick/easy"]) == {"independent", "coupled", "continuous"}
