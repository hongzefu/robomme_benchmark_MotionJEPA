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
    EpisodeSpec, candidate_for_slot, distribution_summary, find_spec, load_configs,
    load_suite, plan_slots, save_suite, validate_configs,
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
    assert set(Counter((slot["task_kind"], slot["difficulty"]) for slot in slots).values()) == {8}
    for group in distribution_summary(slots).values():
        counts = [row["count"] for row in group["combinations"]]
        assert max(counts) - min(counts) <= 1
    for difficulty in ("easy", "medium", "hard"):
        group = [slot for slot in slots if slot["task_kind"] == "BinFill" and slot["difficulty"] == difficulty]
        assert Counter(slot["parameters"]["dynamic"] for slot in group) == {False: 4, True: 4}
    assert Counter(slot["topology"] for slot in slots if slot["task_kind"] == "VideoUnmaskSwap" and slot["difficulty"] == "easy") == {"triangle": 4, "line": 4}


def test_task_filter_does_not_renumber_seed(configs):
    all_slots = plan_slots(*configs)
    filtered = plan_slots(*configs, tasks=["RouteStick"])
    assert filtered == [slot for slot in all_slots if slot["task_kind"] == "RouteStick"]
    assert len(plan_slots(*configs, tasks=["RouteStick"], episodes_per_task=1)) == 1


def test_spec_is_deeply_immutable_and_hash_is_canonical(configs):
    spec = candidate_for_slot(plan_slots(*configs)[0], 0)
    data = spec.to_dict()
    data["actors"][0]["position"][0] = 123
    assert spec.to_dict()["actors"][0]["position"][0] != 123
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
        assert len(a.to_dict()["swaps"]) == a.task_parameters.get("swap_count", 0)


def test_position_seed_does_not_change_task_parameters(configs):
    task, position = configs
    other = copy.deepcopy(position)
    other["compiler_seed"] += 1
    first = plan_slots(task, position)
    second = plan_slots(task, other)
    for a, b in zip(first, second):
        left, right = candidate_for_slot(a, 0), candidate_for_slot(b, 0)
        assert left.task_parameters == right.task_parameters
        assert left.to_dict()["swaps"] == right.to_dict()["swaps"]


def test_all_layers_are_covered_per_position_group(configs):
    groups = defaultdict(list)
    for slot in plan_slots(*configs):
        groups[tuple(slot["position_group"])].append(candidate_for_slot(slot, 0).to_dict())
    for episodes in groups.values():
        dimensions = episodes[0]["layout"]["strata"]
        for name in dimensions:
            layers = [row["layout"]["strata"][name]["index"] for row in episodes]
            assert sorted(layers) == list(range(len(episodes)))


def test_dense_field_strata_never_assign_duplicate_cells(configs):
    for slot in plan_slots(*configs, tasks=["VideoRepick"]):
        if slot["difficulty"] != "hard":
            continue
        layers = slot["field_layers"]
        cells = [(layers[f"cube_{index}.x"], layers[f"cube_{index}.y"]) for index in range(15)]
        assert len(set(cells)) == 15


def _assert_initial_corners_inside(data):
    from robomme_icl.geometry.collision import actor_boxes

    for actor in data["actors"]:
        if "initial_xy_bounds" not in actor:
            continue
        assert "initial_support_rejection" not in actor
        for box in actor_boxes(actor, data["geometry"]):
            for coordinate, axis in enumerate(("x", "y")):
                unit = tuple(float(index == coordinate) for index in range(3))
                radius = box.radius_on(unit)
                low, high = actor["initial_xy_bounds"][axis]
                assert box.center[coordinate] - radius >= low - 1e-10
                assert box.center[coordinate] + radius <= high + 1e-10


def test_all_rotated_initial_actor_corners_obey_support(configs):
    for slot in plan_slots(*configs):
        _assert_initial_corners_inside(candidate_for_slot(slot, 0).to_dict())


def test_video_seven_infeasible_old_pairings_are_repaired_before_sampling(configs):
    affected = {"VideoUnmaskSwap/medium/0000", "VideoUnmaskSwap/medium/0002", "VideoUnmaskSwap/medium/0006",
                "VideoUnmaskSwap/hard/0000", "VideoUnmaskSwap/hard/0003", "VideoUnmaskSwap/hard/0004", "VideoUnmaskSwap/hard/0007"}
    for slot in plan_slots(*configs, tasks=["VideoUnmaskSwap"]):
        if slot["slot_id"] not in affected:
            continue
        assert slot["video_yaw_layers"]
        for candidate_index in (0, 1, 50):
            _assert_initial_corners_inside(candidate_for_slot(slot, candidate_index).to_dict())


def test_support_intersection_resamples_without_clamping_or_switching_layers(configs):
    from robomme_icl.suite.compiler import _sample_initial_support

    slot = plan_slots(*configs, tasks=["BinFill"], episodes_per_task=1)[0]
    data = candidate_for_slot(slot, 0).to_dict()
    actor = next(actor for actor in data["actors"] if actor["kind"] == "cube")
    actor["quaternion"] = [math.cos(math.pi / 8), 0.0, 0.0, math.sin(math.pi / 8)]
    bounds = actor["initial_xy_bounds"]
    actor["position"][:2] = [bounds[axis][0] + .02 for axis in ("x", "y")]
    strata = data["layout"]["strata"]
    original_layers = copy.deepcopy(strata)
    first, second = copy.deepcopy(actor), copy.deepcopy(actor)
    assert _sample_initial_support(first, slot, 0, strata, data["geometry"])
    assert _sample_initial_support(second, slot, 1, strata, data["geometry"])
    assert strata == original_layers
    assert first["position"] != second["position"]
    for result in (first, second):
        for coordinate, axis in enumerate(("x", "y")):
            assert bounds[axis][0] + math.sqrt(2) * .02 < result["position"][coordinate] < bounds[axis][1] - math.sqrt(2) * .02
    # 人为制造原层与旋转支持框完全无交集，必须显式拒绝而非裁到边缘。
    impossible = copy.deepcopy(actor)
    narrow = copy.deepcopy(strata)
    narrow[f"{actor['id']}.x"]["bounds"] = [bounds["x"][0] + .02, bounds["x"][0] + .025]
    original_position = list(impossible["position"])
    assert not _sample_initial_support(impossible, slot, 0, narrow, data["geometry"])
    assert impossible["position"] == original_position
    assert "initial_support_rejection" in impossible


def test_new_seeds_do_not_overlap_legacy_metadata(configs):
    root = Path(__file__).resolve().parents[2]
    seeds = set()
    for path in (root / "src" / "robomme" / "env_metadata").rglob("*_metadata.json"):
        for record in json.loads(path.read_text(encoding="utf-8")).get("records", []):
            seeds.add(record["seed"])
    assert seeds
    assert not seeds.intersection(slot["seed"] for slot in plan_slots(*configs))


def test_route_walk_and_target_counts(configs):
    for slot in plan_slots(*configs):
        spec = candidate_for_slot(slot, 0)
        params = spec.task_parameters
        if spec.task_kind == "BinFill":
            assert sum(params["target_counts"].values()) == params["pick_count"]
            assert sum(count > 0 for count in params["target_counts"].values()) == params["target_color_count"]
            assert len(params["target_ids"]) == params["pick_count"]
        if spec.task_kind == "RouteStick":
            path = params["path_indices"]
            assert len(path) == params["walk_steps"] + 1
            assert all(abs(a-b) == 1 for a, b in zip(path, path[1:]))
            if not params["allow_backtracking"]:
                assert all(a != c or b in (0, 4) for a, b, c in zip(path, path[1:], path[2:]))


def test_binfill_default_scene_and_target_color_semantics(configs):
    assert configs[0]["tasks"]["BinFill"]["hard"]["target_color_count"] == [2, 3]
    for slot in plan_slots(*configs, tasks=["BinFill"]):
        data = candidate_for_slot(slot, 0).to_dict()
        params = data["task_parameters"]
        scene_colors = {actor["color_name"] for actor in data["actors"] if actor["kind"] == "cube"}
        expected = {"easy": 1, "medium": 2, "hard": 3}[slot["difficulty"]]
        assert params["scene_color_count"] == expected == len(scene_colors)
        assert {name for name, count in params["target_counts"].items() if count} <= scene_colors
        if slot["difficulty"] == "hard":
            assert params["target_color_count"] in (2, 3)


def test_video_unmask_three_original_colors_and_empty_container_semantics(configs):
    for slot in plan_slots(*configs, tasks=["VideoUnmaskSwap"]):
        data = candidate_for_slot(slot, 0).to_dict()
        cubes = [actor for actor in data["actors"] if actor["kind"] == "cube"]
        containers = {actor["id"] for actor in data["actors"] if actor["kind"] == "container"}
        assert len(cubes) == 3
        assert {cube["color_name"] for cube in cubes} == {"red", "green", "blue"}
        parents = {cube["parent_id"] for cube in cubes}
        empty = data["task_parameters"]["empty_container_id"]
        if len(containers) == 3:
            assert parents == containers
            assert empty is None
        else:
            assert containers - parents == {empty}
            assert empty not in data["task_parameters"]["target_container_ids"]


def test_video_repick_preserves_same_color_memory_task(configs):
    for slot in plan_slots(*configs, tasks=["VideoRepick"]):
        data = candidate_for_slot(slot, 0).to_dict()
        colors = Counter(actor["color_name"] for actor in data["actors"] if actor["kind"] == "cube")
        if slot["difficulty"] == "hard":
            assert colors == {"red": 5, "green": 5, "blue": 5}
        else:
            assert len(colors) == 1
            assert list(colors.values()) == [3]


def test_wrong_target_counts_and_reveal_timeline_are_rejected(configs):
    slot = next(slot for slot in plan_slots(*configs) if slot["task_kind"] == "BinFill" and slot["parameters"]["dynamic"])
    data = candidate_for_slot(slot, 0).to_dict()
    data.pop("spec_hash")
    broken = copy.deepcopy(data)
    broken["task_parameters"]["target_counts"]["red"] += 1
    with pytest.raises(ValueError, match="target_counts"):
        EpisodeSpec.from_dict(broken)
    broken = copy.deepcopy(data)
    broken["task_parameters"]["reveal_steps_by_id"]["cube_0"] += 1
    with pytest.raises(ValueError, match="出现时刻"):
        EpisodeSpec.from_dict(broken)


def test_suite_requires_certification_and_detects_tampering(configs, local_dir):
    spec = candidate_for_slot(plan_slots(*configs)[0], 0)
    with pytest.raises(ValueError, match="认证"):
        save_suite(local_dir / "bad", [spec], configs, {})
    with pytest.raises(ValueError, match="认证"):
        save_suite(local_dir / "bad", [spec], configs, {spec.spec_hash: {"passed": True, "repeat_equal": False}})
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


@pytest.mark.parametrize("mutation", [
    lambda t, p: t.pop("compiler_seed"),
    lambda t, p: t["tasks"]["BinFill"]["easy"].update(pick_count=[0]),
    lambda t, p: p["BinFill"]["board"].update(x=[1, -1]),
    lambda t, p: p.update(max_candidates=1025),
    lambda t, p: p.update(safety_clearance=0.0),
    lambda t, p: p["geometry"].update(central_box_thickness=0.04),
])
def test_invalid_config_fails_closed(configs, mutation):
    task, position = copy.deepcopy(configs)
    mutation(task, position)
    with pytest.raises(ValueError):
        validate_configs(task, position)


def test_compilation_is_lightweight_in_fresh_process():
    result = subprocess.run([
        "uv", "run", "--no-sync", "python", "-c",
        "import sys; from robomme_icl.suite import load_configs, plan_slots, candidate_for_slot; "
        "s=candidate_for_slot(plan_slots(*load_configs())[0],0); "
        "assert not any(x in sys.modules for x in ('torch','numpy','sapien','mani_skill','robomme.robomme_env')); "
        "print(s.spec_hash)",
    ], capture_output=True, text=True, check=True)
    assert len(result.stdout.strip()) == 64
