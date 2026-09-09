#!/usr/bin/env python3
"""轻量测试：对拍比较器的反例（不加载仿真、不占 GPU）。

方案第四步 4.7 要求比较器必须能**拒绝**这些错误，而不是只证明自己的输出可读回：
关键帧单像素变化、错位或缺帧；对象身份替换、位置跳变、遗漏产生／消失事件；
HDF5 缺字段、dtype／shape 或数值变化；少一次随机调用或状态不同；跨 episode 污染；
证据损坏、来源不匹配。

    uv run --no-sync python -m pytest tests/lightweight/test_native_sampling_evidence.py -q
"""

from __future__ import annotations

import copy
import gzip
import json
import sys
from pathlib import Path
from typing import Any, Callable

import h5py
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared import native_sampling_parity as parity  # noqa: E402

pytestmark = pytest.mark.lightweight


# ── HDF5 比较器的反例 ─────────────────────────────────────────────────────────


def _write_h5(path: Path, mutate: Callable[[h5py.File], None] | None = None) -> Path:
    with h5py.File(path, "w") as handle:
        episode = handle.create_group("episode_0")
        setup = episode.create_group("setup")
        setup.create_dataset("seed", data=np.int64(4000))
        setup.create_dataset("difficulty", data="easy")
        setup.create_dataset("front_camera_intrinsic", data=np.arange(9, dtype=np.float64).reshape(3, 3))
        for index in range(3):
            step = episode.create_group(f"timestep_{index}")
            observation = step.create_group("obs")
            observation.create_dataset(
                "front_rgb", data=np.full((4, 4, 3), index, dtype=np.uint8)
            )
            observation.create_dataset(
                "joint_state", data=np.linspace(0.0, 1.0, 9, dtype=np.float32) + index
            )
            action = step.create_group("action")
            action.create_dataset("joint_action", data=np.full(8, 0.25 * index, dtype=np.float32))
            info = step.create_group("info")
            info.create_dataset("is_completed", data=np.bool_(index == 2))
            info.create_dataset("simple_subgoal", data=f"step-{index}")
        if mutate is not None:
            mutate(handle)
    return path


def _pair(tmp_path: Path, mutate: Callable[[h5py.File], None] | None) -> tuple[Path, Path]:
    return _write_h5(tmp_path / "ref.h5"), _write_h5(tmp_path / "cand.h5", mutate)


def test_identical_h5_files_compare_equal(tmp_path: Path) -> None:
    reference, candidate = _pair(tmp_path, None)
    assert parity.compare_h5(reference, candidate) == []
    assert parity.h5_fingerprint(reference)["entries"] == parity.h5_fingerprint(candidate)["entries"]


def _drop_dataset(handle: h5py.File) -> None:
    del handle["episode_0/timestep_1/obs/joint_state"]


def _add_dataset(handle: h5py.File) -> None:
    handle["episode_0/timestep_1/info"].create_dataset("extra", data=np.int32(1))


def _change_dtype(handle: h5py.File) -> None:
    group = handle["episode_0/timestep_1/obs"]
    values = group["joint_state"][()]
    del group["joint_state"]
    group.create_dataset("joint_state", data=values.astype(np.float64))


def _change_shape(handle: h5py.File) -> None:
    group = handle["episode_0/timestep_1/action"]
    values = group["joint_action"][()]
    del group["joint_action"]
    group.create_dataset("joint_action", data=np.concatenate([values, values[:1]]))


def _change_one_pixel(handle: h5py.File) -> None:
    dataset = handle["episode_0/timestep_1/obs/front_rgb"]
    values = dataset[()]
    values[2, 2, 1] = np.uint8(int(values[2, 2, 1]) + 1)
    dataset[...] = values


def _change_one_float_bit(handle: h5py.File) -> None:
    dataset = handle["episode_0/timestep_1/obs/joint_state"]
    values = dataset[()]
    values[3] = np.nextafter(values[3], np.float32(1e9))
    dataset[...] = values


def _change_string(handle: h5py.File) -> None:
    group = handle["episode_0/timestep_1/info"]
    del group["simple_subgoal"]
    group.create_dataset("simple_subgoal", data="step-X")


def _flip_terminal_bool(handle: h5py.File) -> None:
    handle["episode_0/timestep_2/info/is_completed"][...] = np.bool_(False)


def _add_attribute(handle: h5py.File) -> None:
    handle["episode_0"].attrs["extra"] = 1


def _drop_timestep(handle: h5py.File) -> None:
    del handle["episode_0/timestep_2"]


@pytest.mark.parametrize(
    "mutate, marker",
    [
        (_drop_dataset, "候选缺少该对象"),
        (_add_dataset, "候选多出该对象"),
        (_change_dtype, "签名不同"),
        (_change_shape, "签名不同"),
        (_change_one_pixel, "首个不同元素"),
        (_change_one_float_bit, "首个不同元素"),
        (_change_string, "首个不同元素"),
        (_flip_terminal_bool, "首个不同元素"),
        (_add_attribute, "候选多出该对象"),
        (_drop_timestep, "候选缺少该对象"),
    ],
)
def test_h5_comparator_rejects_each_mutation(tmp_path: Path, mutate, marker: str) -> None:
    """逐类改动都必须被抓出来，且能定位到具体对象。"""
    reference, candidate = _pair(tmp_path, mutate)
    differences = parity.compare_h5(reference, candidate)
    assert differences, "比较器漏掉了这处改动"
    assert any(marker in item for item in differences), differences[:3]


def test_h5_float_comparison_has_no_tolerance(tmp_path: Path) -> None:
    """浮点按位模式比较，一个 ULP 的差也算差异，不设容差。"""
    reference, candidate = _pair(tmp_path, _change_one_float_bit)
    differences = parity.compare_h5(reference, candidate)
    assert len(differences) == 1
    assert "最大绝对差" in differences[0]


def test_compare_runs_needs_both_sides(tmp_path: Path) -> None:
    (tmp_path / "ref" / "hdf5_files").mkdir(parents=True)
    with pytest.raises(parity.ParityError):
        parity.compare_runs(tmp_path / "ref", tmp_path / "missing")


def test_compare_runs_rejects_empty_run(tmp_path: Path) -> None:
    """两侧都没有 episode 时不能算通过。"""
    for name in ("ref", "cand"):
        (tmp_path / name / "hdf5_files").mkdir(parents=True)
    assert parity.compare_runs(tmp_path / "ref", tmp_path / "cand")["passed"] is False


# ── 观察器证据比较器的反例 ────────────────────────────────────────────────────


def _evidence() -> dict[str, Any]:
    return {
        "evidence_version": 1,
        "label": "A1",
        "pid": 1,
        "task": "BinFill",
        "seed": 4000,
        "difficulty": "easy",
        "rrt_fallback_count": 0,
        "rng_total": 3,
        "rng": [
            {
                "i": 1,
                "fn": "torch.randint",
                "args": [0, 2, [1]],
                "kwargs": {},
                "rng": {"source": "generator", "ordinal": 0, "initial_seed": 4000, "state_sha256": "aa"},
                "result": {"dtype": "int64", "shape": [1], "values": [1]},
            },
            {
                "i": 2,
                "fn": "torch.rand",
                "args": [2],
                "kwargs": {},
                "rng": {"source": "generator", "ordinal": 0, "initial_seed": 4000, "state_sha256": "bb"},
                "result": {"dtype": "float32", "shape": [2], "values": [0.25, 0.5]},
            },
            {
                "i": 3,
                "fn": "torch.randperm",
                "args": [3],
                "kwargs": {},
                "rng": {"source": "generator", "ordinal": 0, "initial_seed": 4000, "state_sha256": "cc"},
                "result": {"dtype": "int64", "shape": [3], "values": [0, 2, 1]},
            },
        ],
        "events": [
            {"i": 4, "kind": "event_enter", "name": "swap_flat_two_lane", "args": [{"repr": "<cube_red_0>"}]},
            {"i": 5, "kind": "event_exit", "name": "swap_flat_two_lane", "result": None},
            {"i": 6, "kind": "event_enter", "name": "highlight_obj", "args": [{"repr": "<target_3>"}]},
        ],
        "boundaries": [
            {"i": 7, "stage": "after_load_scene", "task_state": {"dynamic": True}, "actors": {"cube_red_0": {"p": [0.1, 0.2, 0.02]}}},
            {"i": 8, "stage": "after_initialize_episode", "task_state": {"dynamic": True}, "actors": {"cube_red_0": {"p": [0.1, 0.2, 0.02]}}},
        ],
        "steps": [
            {"i": 9, "phase": "before_step", "task_state": {"current_task_index": 0}, "actors": {"cube_red_0": {"p": [0.1, 0.2, 0.02]}}},
            {"i": 10, "phase": "after_step", "task_state": {"current_task_index": 0}, "actors": {"cube_red_0": {"p": [0.1, 0.2, 0.03]}}},
        ],
        "initial_obs": {"i": 11, "value": {"front_rgb": {"sha256": "abcd"}}},
        "_path": "<synthetic>",
    }


def test_identical_evidence_compares_equal() -> None:
    result = parity.compare_evidence(_evidence(), _evidence())
    assert result["passed"] is True
    assert all(item["passed"] for item in result["sections"].values())


def _drop_one_rng_call(evidence: dict[str, Any]) -> None:
    evidence["rng"].pop(1)


def _change_rng_state(evidence: dict[str, Any]) -> None:
    evidence["rng"][1]["rng"]["state_sha256"] = "zz"


def _change_rng_result(evidence: dict[str, Any]) -> None:
    evidence["rng"][2]["result"]["values"] = [0, 1, 2]


def _change_rng_bounds(evidence: dict[str, Any]) -> None:
    evidence["rng"][0]["args"] = [0, 3, [1]]


def _merge_random_sources(evidence: dict[str, Any]) -> None:
    evidence["rng"][1]["rng"]["ordinal"] = 1


def _reorder_events(evidence: dict[str, Any]) -> None:
    evidence["events"][0], evidence["events"][2] = evidence["events"][2], evidence["events"][0]


def _drop_event(evidence: dict[str, Any]) -> None:
    evidence["events"].pop(2)


def _replace_object_identity(evidence: dict[str, Any]) -> None:
    evidence["events"][0]["args"] = [{"repr": "<cube_blue_0>"}]


def _jump_object_position(evidence: dict[str, Any]) -> None:
    evidence["steps"][1]["actors"]["cube_red_0"]["p"] = [0.5, 0.2, 0.03]


def _change_task_state(evidence: dict[str, Any]) -> None:
    evidence["boundaries"][1]["task_state"]["dynamic"] = False


def _change_initial_obs(evidence: dict[str, Any]) -> None:
    evidence["initial_obs"]["value"]["front_rgb"]["sha256"] = "ffff"


def _change_seed(evidence: dict[str, Any]) -> None:
    evidence["seed"] = 4100


@pytest.mark.parametrize(
    "mutate, section",
    [
        (_drop_one_rng_call, "rng"),
        (_change_rng_state, "rng"),
        (_change_rng_result, "rng"),
        (_change_rng_bounds, "rng"),
        (_merge_random_sources, "rng"),
        (_reorder_events, "events"),
        (_drop_event, "events"),
        (_replace_object_identity, "events"),
        (_jump_object_position, "steps"),
        (_change_task_state, "boundaries"),
    ],
)
def test_evidence_comparator_rejects_each_mutation(mutate, section: str) -> None:
    """少一次随机调用、状态不同、事件错序或缺失、对象身份替换、位置跳变都必须被拒绝。"""
    candidate = _evidence()
    mutate(candidate)
    result = parity.compare_evidence(_evidence(), candidate)
    assert result["passed"] is False
    assert result["sections"][section]["passed"] is False
    assert result["sections"][section]["first_divergence"] is not None


def test_evidence_comparator_rejects_initial_obs_change() -> None:
    candidate = _evidence()
    _change_initial_obs(candidate)
    result = parity.compare_evidence(_evidence(), candidate)
    assert result["passed"] is False
    assert result["initial_obs"]["passed"] is False


def test_evidence_comparator_rejects_source_mismatch() -> None:
    """来源不匹配（seed 不同）必须明确报告，不能当成代码差异。"""
    candidate = _evidence()
    _change_seed(candidate)
    result = parity.compare_evidence(_evidence(), candidate)
    assert result["passed"] is False
    assert any("seed" in item for item in result["context_mismatch"])


def test_digest_locates_first_divergence() -> None:
    """轻量指纹保留逐条散列链，能在不带全量的情况下定位首个分歧。"""
    reference = parity.evidence_digest(_evidence())
    candidate_evidence = _evidence()
    _change_rng_result(candidate_evidence)
    candidate = parity.evidence_digest(candidate_evidence)
    assert reference["sections"]["rng"]["sha256"] != candidate["sections"]["rng"]["sha256"]
    chain_reference = reference["sections"]["rng"]["record_sha256"]
    chain_candidate = candidate["sections"]["rng"]["record_sha256"]
    first = next(i for i, _ in enumerate(chain_reference) if chain_reference[i] != chain_candidate[i])
    assert first == 2
    assert reference["sections"]["steps"]["count"] == 2


def test_digest_is_stable_under_volatile_fields() -> None:
    """pid、label 这类逐次不同的字段不参与判定。"""
    other = _evidence()
    other["pid"] = 99999
    other["label"] = "C"
    assert parity.evidence_digest(_evidence()) == parity.evidence_digest(other)


def test_load_evidence_rejects_corrupt_package(tmp_path: Path) -> None:
    """证据损坏必须报错，不能静默当成空证据通过。"""
    directory = tmp_path / "BinFill_seed4000"
    directory.mkdir()
    (directory / "pid1.json.gz").write_bytes(b"not gzip")
    with pytest.raises(Exception):
        parity.load_evidence(directory)


def test_load_evidence_requires_exactly_one_file(tmp_path: Path) -> None:
    directory = tmp_path / "BinFill_seed4000"
    directory.mkdir()
    for name in ("pid1.json.gz", "pid2.json.gz"):
        with gzip.open(directory / name, "wt", encoding="utf-8") as handle:
            json.dump(_evidence(), handle)
    with pytest.raises(parity.ParityError):
        parity.load_evidence(directory)


def test_compare_evidence_dirs_rejects_missing_episode(tmp_path: Path) -> None:
    """一侧少一局不能算通过。"""
    for label, cells in (("A", ("BinFill_seed4000", "RouteStick_seed16000")), ("B", ("BinFill_seed4000",))):
        for cell in cells:
            directory = tmp_path / label / cell
            directory.mkdir(parents=True)
            payload = copy.deepcopy(_evidence())
            payload.pop("_path")
            with gzip.open(directory / "pid1.json.gz", "wt", encoding="utf-8") as handle:
                json.dump(payload, handle)
    result = parity.compare_evidence_dirs(tmp_path / "A", tmp_path / "B")
    assert result["passed"] is False
    assert result["missing_in_candidate"] == ["RouteStick_seed16000"]


def test_large_sections_fall_back_to_block_chain() -> None:
    """大段按块散列：能把首个分歧缩到一个块内，精确到条要回 artifacts/ 的全量证据。"""
    evidence = _evidence()
    evidence["steps"] = [
        {"i": index, "phase": "after_step", "task_state": {"n": index}} for index in range(2000)
    ]
    digest = parity.evidence_digest(evidence)
    section = digest["sections"]["steps"]
    assert section["granularity"] == "block"
    assert section["block_size"] == parity.CHAIN_BLOCK
    assert section["count"] == 2000
    assert len(section["record_sha256"]) == (2000 + parity.CHAIN_BLOCK - 1) // parity.CHAIN_BLOCK

    changed = copy.deepcopy(evidence)
    changed["steps"][777]["task_state"]["n"] = -1
    other = parity.evidence_digest(changed)["sections"]["steps"]
    differing = [i for i, value in enumerate(section["record_sha256"]) if value != other["record_sha256"][i]]
    assert differing == [777 // parity.CHAIN_BLOCK]
    # 块级只定位到区间，精确到条必须回全量证据
    assert parity.compare_evidence(evidence, changed)["sections"]["steps"]["first_divergence"]["index"] == 777


def test_h5_digest_locates_the_differing_timestep(tmp_path: Path) -> None:
    """入库形态能判断整份是否相同并定位到哪一帧；不能还原画面或算像素差幅度。"""
    reference, candidate = _pair(tmp_path, _change_one_pixel)
    left = parity.h5_digest(parity.h5_fingerprint(reference))
    right = parity.h5_digest(parity.h5_fingerprint(candidate))
    assert left["sha256"] != right["sha256"]
    assert left["object_count"] == right["object_count"]
    differing = [key for key, value in left["group_sha256"].items() if right["group_sha256"][key] != value]
    assert differing == ["episode_0/timestep_1"]
    assert "front_rgb" not in json.dumps(left)


def test_h5_digest_is_stable_for_identical_files(tmp_path: Path) -> None:
    reference, candidate = _pair(tmp_path, None)
    assert parity.h5_digest(parity.h5_fingerprint(reference)) == {
        **parity.h5_digest(parity.h5_fingerprint(candidate)),
        "file": "ref.h5",
    }


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
