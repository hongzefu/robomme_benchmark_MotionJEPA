"""robomme_xhard 公共契约与离线工具的纯 CPU 测试（不 gym.make、不起仿真）。

运行（worktree 内，借主检出 venv）::

    UV_PROJECT_ENVIRONMENT=<主检出>/.venv PYTHONPATH=<worktree>/src \
        uv run --no-sync python -m pytest src/robomme_xhard/tests/test_contract.py -q -m 'not gpu'
"""

from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from robomme_xhard.base import XHardMixin
from robomme_xhard.configs import (
    DIFFICULTIES,
    MOTHER_KNOBS,
    SOURCE_DIFFICULTY,
    TASK_ORDER,
    TIER_CONFIGS,
    XHARD_TASKS,
    env_name,
    tier,
    valid_pairs,
)
from robomme_xhard.tools import compare_video, layout, mother_seeds, summarize

TOOLS_DIR = Path(mother_seeds.__file__).resolve().parent


# ------------------------------------------------------------------ 配置表


def test_tier_configs_52_and_only_known_difficulties():
    assert sum(len(v) for v in TIER_CONFIGS.values()) == 52
    assert len(valid_pairs()) == 52
    for task, tiers in TIER_CONFIGS.items():
        assert task in TASK_ORDER
        assert set(tiers) <= set(DIFFICULTIES), task


def test_tier_configs_distinct_within_task():
    for task, tiers in TIER_CONFIGS.items():
        seen = [json.dumps(entry, sort_keys=True) for entry in tiers.values()]
        assert len(seen) == len(set(seen)), f"{task} 有重复配置"


def test_task_order_and_sources():
    assert len(TASK_ORDER) == 16 and len(set(TASK_ORDER)) == 16
    assert set(XHARD_TASKS) == set(TIER_CONFIGS)
    assert "MoveCube" not in TIER_CONFIGS and "InsertPeg" not in TIER_CONFIGS
    assert SOURCE_DIFFICULTY["VideoRepick"] == "medium"
    assert all(SOURCE_DIFFICULTY[t] == "hard" for t in TASK_ORDER if t != "VideoRepick")
    assert set(MOTHER_KNOBS) == set(TASK_ORDER)
    assert env_name("PickXtimes") == "PickXtimesXHard"
    # valid_pairs 按官网任务顺序、再按难度顺序
    keys = [(TASK_ORDER.index(t), DIFFICULTIES.index(d)) for t, d in valid_pairs()]
    assert keys == sorted(keys)


def test_tier_missing_raises():
    with pytest.raises(KeyError):
        tier("StopCube", "xhard12")
    with pytest.raises(KeyError):
        tier("MoveCube", "xhard12")
    with pytest.raises(ValueError):
        tier("PickXtimes", "hard")
    assert tier("PickXtimes", " XHARD12 ")["knobs"]["repeats"] == 6


# ------------------------------------------------------------------ XHardMixin


@dataclasses.dataclass(frozen=True)
class FakeSpec:
    id: str
    max_episode_steps: int = 1000
    kwargs: dict = dataclasses.field(default_factory=dict)


def _make_parent():
    class FakeParent:
        """轻量假父类：有 configs 类属性，__init__ 里 normalize 后给 self.difficulty 赋值。"""

        configs = {
            "easy": {"number_min": 1, "number_max": 1, "keep": "e"},
            "medium": {"number_min": 2, "number_max": 3, "keep": "m", "swap_min": 1, "swap_max": 1},
            "hard": {"number_min": 3, "number_max": 5, "keep": "h", "swap_min": 2, "swap_max": 2},
        }

        def __init__(self, *args, difficulty=None, **kwargs):
            normalized = (difficulty or "easy").strip().lower()
            assert normalized in ("easy", "medium", "hard"), normalized
            self.received = normalized
            self.difficulty = normalized
            self.active = self.configs[self.difficulty]
            self.literal_hard = self.difficulty == "hard"
            self.spec = None

    return FakeParent


def test_mixin_difficulty_and_configs():
    parent = _make_parent()

    class FakePick(XHardMixin, parent):
        robomme_base_id = "PickXtimes"

    env = FakePick(difficulty="xhard12")
    assert env.received == "hard"  # 父类收到的是母来源
    assert env.difficulty == "xhard12"  # 赋值被拦截
    assert env.active == {"number_min": 6, "number_max": 6, "keep": "h", "swap_min": 2, "swap_max": 2}
    assert env.literal_hard is False
    assert env.xhard_label == "xhard12"
    assert env.xhard_knobs == {"repeats": 6}
    assert env.source_difficulty == "hard"
    # 父类三档原样保留、五档合成
    assert set(FakePick.configs) == {"easy", "medium", "hard", *DIFFICULTIES}
    assert FakePick.configs["hard"] == parent.configs["hard"]
    assert FakePick.configs["xhard20"]["number_min"] == 10
    # 父类本身的 configs 不被改写
    assert set(parent.configs) == {"easy", "medium", "hard"}


def test_mixin_source_medium_for_videorepick():
    parent = _make_parent()

    class FakeRepick(XHardMixin, parent):
        robomme_base_id = "VideoRepick"

    env = FakeRepick(difficulty="xhard14")
    assert env.received == "medium"
    assert env.difficulty == "xhard14"
    assert env.active["keep"] == "m"
    assert env.active["swap_min"] == env.active["swap_max"] == 7
    assert env.xhard_knobs == {"swap_count": 7, "repick_count": 2}


def test_mixin_rejects_non_xhard_and_missing_tier():
    parent = _make_parent()

    class FakeStop(XHardMixin, parent):
        robomme_base_id = "StopCube"

    for bad in ("hard", "medium", None, "xhard13"):
        with pytest.raises(ValueError):
            FakeStop(difficulty=bad)
    with pytest.raises(KeyError):
        FakeStop(difficulty="xhard12")  # StopCube 缺 xhard12
    with pytest.raises(KeyError):

        class FakeMove(XHardMixin, parent):  # noqa: F841
            robomme_base_id = "MoveCube"


def test_mixin_spec_renamed_other_fields_kept():
    parent = _make_parent()

    class FakePick(XHardMixin, parent):
        robomme_base_id = "PickXtimes"

    env = FakePick(difficulty="xhard16")
    assert env.spec is None
    env.spec = FakeSpec(id="PickXtimesXHard", max_episode_steps=1234, kwargs={"difficulty": "xhard16"})
    assert env.spec.id == "PickXtimes"
    assert env.spec.max_episode_steps == 1234
    assert env.spec.kwargs == {"difficulty": "xhard16"}


# ------------------------------------------------------------------ 母 seed 清单


def _metadata(task):
    return {int(r["episode"]): r for r in mother_seeds.load_records(mother_seeds.DEFAULT_METADATA_DIR, task)}


def test_reference_subsets_match_plan_sizes():
    for task, subset in mother_seeds.REFERENCE_SUBSETS.items():
        if subset is None:
            assert task in ("MoveCube", "InsertPeg")
            continue
        assert len(subset) == mother_seeds.REFERENCE_SUBSET_SIZES[task], task
        assert len(set(subset)) == len(subset)
    assert list(mother_seeds.REFERENCE_SUBSETS) == list(TASK_ORDER)


def test_mother_seeds_manifest(tmp_path):
    manifest = mother_seeds.build_manifest(official_dir=None)
    assert manifest["version"] == 1
    assert list(manifest["tasks"]) == list(TASK_ORDER)
    ok, n, min_ep = mother_seeds.check_manifest(manifest)
    assert ok and n == 32 and min_ep >= 6
    ranks = [e["rank"] for t in TASK_ORDER for e in manifest["tasks"][t]]
    assert ranks.count(0) == 16 and ranks.count(1) == 16
    for task in TASK_ORDER:
        entries = manifest["tasks"][task]
        assert [e["rank"] for e in entries] == [0, 1]
        assert entries[0]["episode"] < entries[1]["episode"]
        meta = _metadata(task)
        subset = mother_seeds.REFERENCE_SUBSETS[task]
        for e in entries:
            assert e["episode"] >= 6
            rec = meta[e["episode"]]
            assert e["seed"] == rec["seed"]
            assert rec["difficulty"] == e["source_difficulty"] == SOURCE_DIFFICULTY[task]
            if subset is not None:
                assert e["episode"] in subset
            assert e["verify"] == "unverified"
    # 命令行入口写出可读 JSON
    out = tmp_path / "m.json"
    assert mother_seeds.main(["--out", str(out), "--no-verify"]) == 0
    assert json.loads(out.read_text())["tasks"] == manifest["tasks"]


def test_mother_seeds_insufficient_raises():
    records = [{"episode": e, "seed": 100 + e, "difficulty": "hard"} for e in range(100)]
    saved = mother_seeds.REFERENCE_SUBSETS["StopCube"]
    try:
        mother_seeds.REFERENCE_SUBSETS["StopCube"] = (3, 5, 59)
        with pytest.raises(mother_seeds.MotherSeedError):
            mother_seeds.select_task("StopCube", records)
    finally:
        mother_seeds.REFERENCE_SUBSETS["StopCube"] = saved


# ------------------------------------------------------------------ summarize


def test_window_formula():
    w = layout.windows
    assert [w(0), w(17), w(32), w(33), w(48), w(49), w(65), w(900)] == [0, 0, 0, 1, 1, 2, 3, 55]


def _write_h5(path: Path, episode: int, seed: int, difficulty: str, demo: int, exe: int, color: int = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        g = f.create_group(f"episode_{episode}")
        s = g.create_group("setup")
        s.create_dataset("seed", data=seed)
        s.create_dataset("difficulty", data=difficulty, dtype=h5py.string_dtype(encoding="utf-8"))
        total = demo + exe
        for i in range(total):
            ts = g.create_group(f"timestep_{i}")
            info = ts.create_group("info")
            info.create_dataset("is_video_demo", data=i < demo)
            info.create_dataset("is_completed", data=i == total - 1)
            obs = ts.create_group("obs")
            obs.create_dataset("front_rgb", data=np.full((8, 8, 3), (color + i) % 256, dtype=np.uint8))


def _fake_root(tmp_path: Path) -> Path:
    root = tmp_path / "run"
    # PickXtimes seed 1700：母档 + 两档
    _write_h5(root / "mother/hdf5_files/PickXtimes_ep7_seed1700.h5", 7, 1700, "hard", 40, 60)
    _write_h5(root / "xhard12/hdf5_files/PickXtimes_ep7_seed1700.h5", 7, 1700, "xhard12", 49, 81)
    _write_h5(root / "xhard14/hdf5_files/PickXtimes_ep7_seed1700.h5", 7, 1700, "xhard14", 33, 107)
    # BinFill seed 4701：只有母档（排序时应在 PickXtimes 之前）
    _write_h5(root / "mother/hdf5_files/BinFill_ep7_seed4701.h5", 7, 4701, "hard", 0, 50)
    # 失败：只有 FAILED_ 视频
    vids = root / "xhard16/videos"
    vids.mkdir(parents=True)
    (vids / "FAILED_PickXtimes_ep7_seed1700_xhard16_pick_up.mp4").write_bytes(b"")
    return root


def test_summarize_rows_windows_ratio_and_order(tmp_path):
    root = _fake_root(tmp_path)
    rows = summarize.collect(root)
    order = [(r["task"], r["seed"], r["level"]) for r in rows]
    assert order == [
        ("BinFill", 4701, "mother"),
        ("PickXtimes", 1700, "mother"),
        ("PickXtimes", 1700, "xhard12"),
        ("PickXtimes", 1700, "xhard14"),
        ("PickXtimes", 1700, "xhard16"),
    ]
    by = {(r["task"], r["level"]): r for r in rows}
    m = by[("PickXtimes", "mother")]
    assert (m["demo_timesteps"], m["exec_timesteps"], m["timesteps"]) == (40, 60, 100)
    assert (m["demo_windows"], m["exec_windows"], m["windows"]) == (1, 2, 3)
    x12 = by[("PickXtimes", "xhard12")]
    assert (x12["demo_windows"], x12["exec_windows"], x12["windows"]) == (2, 4, 6)
    assert x12["ratio_timesteps"] == 1.3 and x12["ratio_windows"] == 2.0
    assert x12["task_success"] == 1 and x12["difficulty"] == "xhard12"
    failed = by[("PickXtimes", "xhard16")]
    assert failed["task_success"] == 0 and failed["timesteps"] is None
    verdicts = summarize.judge(rows)
    assert verdicts["DIFFICULTY_LABEL"] == "DIFFICULTY_LABEL=PASS files=4"
    assert verdicts["XHARD_RECORD_NONEMPTY"] == "XHARD_RECORD_NONEMPTY=PASS files=4"
    assert verdicts["GRADIENT_REVIEW"].startswith("GRADIENT_REVIEW=INFO groups=2")
    assert "failed=1" in verdicts["GRADIENT_REVIEW"]
    md = summarize.to_markdown(rows, verdicts)
    assert md.count("\n| ") >= 6


def test_summarize_seed_order_from_manifest_and_label_fail(tmp_path):
    root = tmp_path / "run"
    _write_h5(root / "mother/hdf5_files/PickXtimes_ep11_seed2100.h5", 11, 2100, "hard", 0, 40)
    _write_h5(root / "mother/hdf5_files/PickXtimes_ep7_seed1700.h5", 7, 1700, "hard", 0, 40)
    _write_h5(root / "xhard12/hdf5_files/PickXtimes_ep7_seed1700.h5", 7, 1700, "hard", 0, 40)  # 标签错
    manifest = {"tasks": {"PickXtimes": [{"episode": 11, "seed": 2100, "rank": 0}, {"episode": 7, "seed": 1700, "rank": 1}]}}
    rows = summarize.collect(root, manifest)
    assert [(r["seed"], r["level"]) for r in rows] == [(2100, "mother"), (1700, "mother"), (1700, "xhard12")]
    verdicts = summarize.judge(rows)
    assert verdicts["DIFFICULTY_LABEL"].startswith("DIFFICULTY_LABEL=FAIL files=3")


# ------------------------------------------------------------------ compare_video


def _solid(values, size=8):
    return [np.full((size, size, 3), v, dtype=np.uint8) for v in values]


def test_column_state_and_end_hold():
    short = compare_video.Column("a", compare_video.OK, compare_video.ArraySource(_solid([10, 50, 90])))
    long = compare_video.Column("b", compare_video.OK, compare_video.ArraySource(_solid([20, 60, 100, 140, 180])))
    missing = compare_video.Column("c", compare_video.MISSING)
    assert compare_video.column_state(short, 1) == ("play", 1)
    assert compare_video.column_state(short, 4) == ("end", 2)
    assert compare_video.column_state(missing, 0) == ("blank", None)
    cols = [short, long, missing]
    assert compare_video.segment_length(cols) == 5
    assert compare_video.segment_length([missing]) == 1

    panel = 64
    frames = list(compare_video.iter_segment_frames(cols, "t", panel=panel))
    assert len(frames) == 5
    top = compare_video.TITLE_H + compare_video.LABEL_H
    for f in frames:
        assert f.shape == (top + panel, panel * 3, 3)
    last = frames[-1]
    # 取栏底部右下角（远离叠字）：短栏停在末帧 90，长栏在第 5 帧 180，缺档栏为灰底 90 且不补位
    assert tuple(last[-2, panel - 2]) == (90, 90, 90)
    assert tuple(last[-2, 2 * panel - 2]) == (180, 180, 180)
    assert tuple(last[-2, 2 * panel + 2]) == (90, 90, 90)
    assert tuple(frames[0][-2, panel - 2]) == (10, 10, 10)
    # t=0 时短栏未结束，末帧时有“结束”标注（标注区像素被改动）
    region = (slice(top + 2, top + 26), slice(2, panel - 2))
    assert np.all(frames[0][region] == 10)
    assert not np.all(last[region] == 90)


def test_build_columns_missing_absent_and_failed(tmp_path):
    root = tmp_path / "run"
    _write_h5(root / "mother/hdf5_files/VideoPlaceOrder_ep7_seed11705.h5", 7, 11705, "hard", 2, 3)
    arts = layout.scan(root)
    cols = compare_video.build_columns("VideoPlaceOrder", 11705, arts)
    try:
        assert [c.status for c in cols] == ["ok", "absent", "missing", "missing", "missing", "missing"]
        assert cols[0].length == 5 and cols[0].label.startswith("母档")
    finally:
        for c in cols:
            if c.source is not None:
                c.source.close()
    # 有效档只有失败记录且无视频 → 失败栏
    arts[("VideoPlaceOrder", 11705, "xhard12")] = layout.Artifact("VideoPlaceOrder", 11705, "xhard12", h5=root / "nope.h5")
    cols = compare_video.build_columns("VideoPlaceOrder", 11705, arts)
    try:
        assert cols[1].status == compare_video.FAILED and cols[1].length == 0
    finally:
        for c in cols:
            if c.source is not None:
                c.source.close()


def test_render_small_mp4(tmp_path):
    root = tmp_path / "run"
    _write_h5(root / "mother/hdf5_files/PickXtimes_ep7_seed1700.h5", 7, 1700, "hard", 2, 3)
    _write_h5(root / "xhard12/hdf5_files/PickXtimes_ep7_seed1700.h5", 7, 1700, "xhard12", 3, 4)
    out = tmp_path / "cmp.mp4"
    stats = compare_video.render(root, out, None, fps=10, panel=32)
    assert stats == {"segments": 1, "frames": 7, "cjk_font": stats["cjk_font"]}
    assert out.stat().st_size > 0


# ------------------------------------------------------------------ S3 真实布局：根下 run_summary.json


def _card(task, seed, difficulty, role, ok, failure_class=None, episode=7):
    return {
        "task": task,
        "role": role,
        "make_name": f"{task}XHard" if role == "xhard" else task,
        "difficulty": difficulty,
        "source_difficulty": "hard",
        "mother_episode": episode,
        "seed": seed,
        "attempt": 0,
        "ok": ok,
        "task_success": ok,
        "timesteps": None,
        "h5": None,
        "failure_class": None if ok else failure_class,
        "error": None if ok else "planner 失败",
    }


def _s3_root(tmp_path: Path, with_summary: bool = True) -> Path:
    """按 S3 生成器布局造最小产物：结果记录在根下，H5 在 <root>/<档>/hdf5_files/。"""
    root = tmp_path / "s3run"
    _write_h5(root / "mother/hdf5_files/PickXtimes_ep7_seed1700.h5", 7, 1700, "hard", 2, 3)
    _write_h5(root / "xhard12/hdf5_files/PickXtimes_ep7_seed1700.h5", 7, 1700, "xhard12", 3, 4)
    # xhard16 失败且留下 FAILED_ 视频（空文件，视频工具应容错）；xhard14 失败且无任何产物
    vids = root / "xhard16/videos"
    vids.mkdir(parents=True)
    (vids / "FAILED_PickXtimes_ep7_seed1700_xhard16_pick_up.mp4").write_bytes(b"")
    cards = [
        _card("PickXtimes", 1700, "hard", "mother", True),
        _card("PickXtimes", 1700, "xhard12", "xhard", True),
        _card("PickXtimes", 1700, "xhard14", "xhard", False, "task"),
        _card("PickXtimes", 1700, "xhard16", "xhard", False, "code"),
    ]
    # 根下 jsonl 与 run_summary 矛盾（xhard14 记 ok=true），用来证明 run_summary 优先
    jsonl = [
        {"task": "PickXtimes", "episode": 7, "seed": 1700, "difficulty": "xhard14", "card_role": "xhard", "ok": True},
        {"task": "PickXtimes", "episode": 7, "seed": 1700, "difficulty": "xhard18", "card_role": "xhard", "ok": False, "failure_class": "task"},
    ]
    root.mkdir(parents=True, exist_ok=True)
    (root / "episode_results.jsonl").write_text("\n".join(json.dumps(r) for r in jsonl) + "\n")
    if with_summary:
        (root / "run_summary.json").write_text(json.dumps({"requested_count": 4, "cards": cards}))
    return root


def test_s3_layout_run_summary_is_authoritative(tmp_path):
    root = _s3_root(tmp_path)
    results, source = layout.read_run_results(root)
    assert source == "run_summary"
    assert set(results) == {("PickXtimes", 1700, lvl) for lvl in ("mother", "xhard12", "xhard14", "xhard16")}
    rows = summarize.collect(root)
    by = {r["level"]: r for r in rows}
    assert [r["level"] for r in rows] == ["mother", "xhard12", "xhard14", "xhard16"]
    assert by["mother"]["task_success"] == 1 and by["mother"]["ok"] is True
    assert by["xhard12"]["timesteps"] == 7 and by["xhard12"]["ratio_timesteps"] == 1.4
    # 失败卡即使既无 H5 也无视频也出现在表里，且以 run_summary 为准（不采纳 jsonl 的 ok=true）
    x14 = by["xhard14"]
    assert x14["h5"] is None and x14["failed_video"] is None
    assert (x14["ok"], x14["task_success"], x14["failure_class"], x14["result_source"]) == (False, 0, "task", "run_summary")
    assert by["xhard16"]["failure_class"] == "code" and by["xhard16"]["task_success"] == 0
    # jsonl 里多出的 xhard18 不进表（run_summary 存在时不读 jsonl）
    assert "xhard18" not in by
    verdicts = summarize.judge(rows)
    assert verdicts["DIFFICULTY_LABEL"] == "DIFFICULTY_LABEL=PASS files=2"
    assert "failed=2" in verdicts["GRADIENT_REVIEW"]


def test_s3_layout_fallback_to_root_jsonl(tmp_path):
    root = _s3_root(tmp_path, with_summary=False)
    results, source = layout.read_run_results(root)
    assert source == "episode_results"
    rows = summarize.collect(root)
    by = {r["level"]: r for r in rows}
    # 根下 jsonl 定档：card_role=xhard → difficulty 档
    assert by["xhard14"]["ok"] is True and by["xhard14"]["result_source"] == "episode_results"
    assert by["xhard18"]["task_success"] == 0 and by["xhard18"]["failure_class"] == "task"
    # 两种记录都没有的档退回 H5 / FAILED_ 视频推断
    assert by["mother"]["task_success"] == 1 and by["mother"]["result_source"] == "h5"
    assert by["xhard16"]["task_success"] == 0 and by["xhard16"]["result_source"] == "failed_video"


def test_s3_layout_compare_video_marks_failed_cards(tmp_path):
    root = _s3_root(tmp_path)
    arts = layout.scan(root)
    results, _ = layout.read_run_results(root)
    cols = compare_video.build_columns("PickXtimes", 1700, arts, results)
    try:
        # 母档、xhard12 成功；xhard14 失败无产物 → 失败（不是无产物）；xhard16 失败视频打不开 → 失败；
        # xhard18、xhard20 有效档但无卡无产物 → 无产物
        assert [c.status for c in cols] == ["ok", "ok", "failed", "failed", "absent", "absent"]
        assert cols[2].length == 0 and cols[3].length == 0
    finally:
        for c in cols:
            if c.source is not None:
                c.source.close()
    # 没有 results 时 xhard14 只能标“无产物”
    cols = compare_video.build_columns("PickXtimes", 1700, arts)
    try:
        assert cols[2].status == compare_video.ABSENT
    finally:
        for c in cols:
            if c.source is not None:
                c.source.close()
    out = tmp_path / "s3.mp4"
    stats = compare_video.render(root, out, None, fps=10, panel=32)
    assert stats["segments"] == 1 and stats["frames"] == 7 and out.stat().st_size > 0


# ------------------------------------------------------------------ 生产代码不依赖测试目录


def test_tools_do_not_import_tests():
    for path in TOOLS_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            assert not any("tests" in n.split(".") for n in names), f"{path.name} 导入了测试目录"
