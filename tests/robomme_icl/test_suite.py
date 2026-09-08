"""覆盖配额、位置分层、域隔离、冻结记录及篡改拒绝的轻量验证。"""

from collections import Counter, defaultdict
from dataclasses import FrozenInstanceError
import copy
import json
import math
from pathlib import Path
import subprocess
import tempfile

import pytest

from robomme_icl.suite import (
    EpisodeSpec,
    candidate_for_slot,
    distribution_summary,
    find_spec,
    load_configs,
    load_suite,
    plan_slots,
    save_suite,
    validate_configs,
)


@pytest.fixture
def configs():
    return load_configs()


@pytest.fixture
def local_dir():
    root = Path(__file__).resolve().parents[2]
    cache = root / ".cache" / "robomme_icl_tests"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix="suite-") as directory:
        yield Path(directory)


def test_default_quotas_and_global_seeds(configs):
    slots = plan_slots(*configs)
    assert len(slots) == 96
    assert [slot["seed"] for slot in slots] == list(range(2_000_000_000, 2_000_000_096))
    assert set(
        Counter((slot["task_kind"], slot["difficulty"]) for slot in slots).values()
    ) == {8}
    for difficulty in ("easy", "medium", "hard"):
        group = [
            slot
            for slot in slots
            if slot["task_kind"] == "BinFill" and slot["difficulty"] == difficulty
        ]
        assert Counter(slot["parameters"]["dynamic"] for slot in group) == {
            False: 4,
            True: 4,
        }
    assert Counter(
        slot["topology"]
        for slot in slots
        if slot["task_kind"] == "VideoUnmaskSwap" and slot["difficulty"] == "easy"
    ) == {"triangle": 4, "line": 4}


def test_task_filter_does_not_renumber_seed(configs):
    all_slots = plan_slots(*configs)
    filtered = plan_slots(*configs, tasks=["RouteStick"])
    assert filtered == [slot for slot in all_slots if slot["task_kind"] == "RouteStick"]
    assert len(plan_slots(*configs, tasks=["RouteStick"], episodes_per_task=1)) == 1


def test_spec_is_deeply_immutable_and_hash_is_canonical(configs):
    spec = candidate_for_slot(plan_slots(*configs)[0], 0)
    data = spec.to_dict()
    data["placements"]["cubes"][0]["x_fraction"] = 0.123
    assert spec.to_dict()["placements"]["cubes"][0]["x_fraction"] != 0.123
    with pytest.raises(FrozenInstanceError):
        spec._json = "{}"
    reordered = dict(reversed(list(spec.to_dict().items())))
    assert EpisodeSpec.from_dict(reordered) == spec
    with pytest.raises(ValueError, match="哈希"):
        EpisodeSpec.from_dict(data)


def test_candidates_preserve_counts_seed_and_layers(configs):
    for slot in plan_slots(*configs):
        a = candidate_for_slot(slot, 0)
        b = candidate_for_slot(slot, 1)
        assert a == candidate_for_slot(slot, 0)
        assert a.seed == b.seed
        assert a.task_parameters == b.task_parameters
        assert a.to_dict()["layout"]["strata"] == b.to_dict()["layout"]["strata"]
        assert a.spec_hash != b.spec_hash
        assert "swaps" not in a.to_dict()


def test_position_seed_does_not_change_task_parameters(configs):
    task, position = configs
    other = copy.deepcopy(position)
    other["compiler_seed"] += 1
    first = plan_slots(task, position)
    second = plan_slots(task, other)
    for a, b in zip(first, second):
        left, right = candidate_for_slot(a, 0), candidate_for_slot(b, 0)
        assert left.task_parameters == right.task_parameters
        assert left.seed == right.seed


def test_all_layers_are_covered_per_position_group(configs):
    groups = defaultdict(list)
    for slot in plan_slots(*configs):
        groups[tuple(slot["position_group"])].append(
            candidate_for_slot(slot, 0).to_dict()
        )
    for episodes in groups.values():
        dimensions = episodes[0]["layout"]["strata"]
        for name in dimensions:
            layers = [row["layout"]["strata"][name]["index"] for row in episodes]
            assert sorted(layers) == list(range(len(episodes)))


def test_new_seeds_do_not_overlap_legacy_metadata(configs):
    root = Path(__file__).resolve().parents[2]
    seeds = set()
    for path in (root / "src" / "robomme" / "env_metadata").rglob("*_metadata.json"):
        for record in json.loads(path.read_text(encoding="utf-8")).get("records", []):
            seeds.add(record["seed"])
    assert seeds
    assert not seeds.intersection(slot["seed"] for slot in plan_slots(*configs))


def test_suite_requires_certification_and_detects_tampering(configs, local_dir):
    spec = candidate_for_slot(plan_slots(*configs)[0], 0)
    with pytest.raises(ValueError, match="认证"):
        save_suite(local_dir / "bad", [spec], configs, {})
    with pytest.raises(ValueError, match="认证"):
        save_suite(
            local_dir / "bad",
            [spec],
            configs,
            {spec.spec_hash: {"passed": True, "repeat_equal": False}},
        )
    reports = {spec.spec_hash: {"passed": True, "repeat_equal": True}}
    path = save_suite(local_dir / "good", [spec], configs, reports)
    loaded = load_suite(path)
    assert find_spec(loaded, spec.task_kind, spec.seed) == spec
    with pytest.raises(FileExistsError):
        save_suite(path, [spec], configs, reports)
    loaded["episodes"][0]["seed"] += 1
    path.write_text(json.dumps(loaded), encoding="utf-8")
    with pytest.raises(ValueError, match="哈希"):
        load_suite(path)


def test_compilation_is_lightweight_in_fresh_process():
    result = subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "python",
            "-c",
            "import sys; from robomme_icl.suite import load_configs, plan_slots, candidate_for_slot; "
            "s=candidate_for_slot(plan_slots(*load_configs())[0],0); "
            "assert not any(x in sys.modules for x in ('torch','numpy','sapien','mani_skill','robomme.robomme_env')); "
            "print(s.spec_hash)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert len(result.stdout.strip()) == 64


def test_dense_field_strata_do_not_assign_duplicate_cells(configs):
    for slot in plan_slots(*configs):
        if slot["topology"] != "field" or slot["position_count"] < 4:
            continue
        spec = candidate_for_slot(slot, 0).to_dict()
        strata = spec["layout"]["strata"]
        count = slot["parameters"]["spawn_count"]
        cells = [
            (strata[f"cube_{index}.x"]["index"], strata[f"cube_{index}.y"]["index"])
            for index in range(min(count, slot["position_count"] ** 2))
        ]
        assert len(cells) == len(set(cells))


def test_inputs_do_not_redefine_native_targets_geometry_or_events(configs):
    for slot in plan_slots(*configs):
        value = candidate_for_slot(slot, 0).to_dict()
        assert not {"actors", "swaps", "geometry", "schedule"} & value.keys()
        assert (
            not {
                "target_ids",
                "target_counts",
                "directions",
                "path_indices",
                "reveal_steps_by_id",
            }
            & value["task_parameters"].keys()
        )
        assert value["layout"]["coordinate_mode"] == "native_support_fraction"
        for group in value["placements"].values():
            for point in group:
                assert 0 <= point["x_fraction"] <= 1
                assert 0 <= point["y_fraction"] <= 1


@pytest.mark.parametrize(
    "mutation",
    [
        lambda t, p: t.pop("compiler_seed"),
        lambda t, p: t["tasks"]["BinFill"]["easy"].update(pick_count=[0]),
        lambda t, p: p["BinFill"]["board"].update(x=[1, -1]),
        lambda t, p: p.update(max_candidates=1025),
        lambda t, p: p.update(safety_clearance=0.0),
        lambda t, p: p.update(geometry={"central_box_thickness": 0.04}),
    ],
)
def test_invalid_config_fails_closed(configs, mutation):
    task, position = copy.deepcopy(configs)
    mutation(task, position)
    with pytest.raises(ValueError):
        validate_configs(task, position)
