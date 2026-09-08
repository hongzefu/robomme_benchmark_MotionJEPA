"""版本2只冻结分布输入，素材和任务行为不得从配置覆盖。"""

import copy
from collections import defaultdict

import pytest

from robomme_icl.config import load_configs, validate_configs
from robomme_icl.sampling.compiler import candidate_for_slot
from robomme_icl.sampling.tasks import plan_slots
from robomme_icl.specs import EpisodeSpec


def test_default_quota_and_deterministic_candidates():
    configs = load_configs()
    slots = plan_slots(*configs)
    assert len(slots) == 96
    assert len({row["seed"] for row in slots}) == 96
    for task in configs[0]["task_order"]:
        for difficulty in ("easy", "medium", "hard"):
            assert (
                sum(
                    row["task_kind"] == task and row["difficulty"] == difficulty
                    for row in slots
                )
                == 8
            )
    for slot in slots:
        first = candidate_for_slot(slot, 0)
        repeated = candidate_for_slot(slot, 0)
        other = candidate_for_slot(slot, 1)
        assert first == repeated
        assert first.seed == other.seed
        assert first.task_parameters == other.task_parameters
        assert first.spec_hash != other.spec_hash
        assert first.to_dict()["schema_version"] == 2
        assert "geometry" not in first.to_dict()
        assert "schedule" not in first.to_dict()


@pytest.mark.parametrize("forbidden", ["geometry", "schedule"])
def test_geometry_and_timing_cannot_be_configured(forbidden):
    task, position = load_configs()
    position[forbidden] = {}
    with pytest.raises(ValueError, match="覆盖"):
        validate_configs(task, position)


def test_old_spec_and_mutated_hash_are_rejected():
    spec = candidate_for_slot(plan_slots(*load_configs())[0], 0)
    value = spec.to_dict()
    value["schema_version"] = 1
    with pytest.raises(ValueError, match="版本2"):
        EpisodeSpec.from_dict(value)
    value = spec.to_dict()
    value["seed"] += 1
    with pytest.raises(ValueError, match="哈希"):
        EpisodeSpec.from_dict(value)


def test_accessors_do_not_leak_mutable_state():
    spec = candidate_for_slot(plan_slots(*load_configs())[0], 0)
    before = spec.to_dict()
    detached = spec.to_dict()
    detached["placements"].clear()
    assert spec.to_dict() == before


def test_every_position_group_covers_each_layer_exactly_once():
    groups = defaultdict(list)
    for slot in plan_slots(*load_configs()):
        groups[tuple(slot["position_group"])].append(
            candidate_for_slot(slot, 0).to_dict()
        )
    for rows in groups.values():
        fields = set(rows[0]["layout"]["strata"])
        assert all(set(row["layout"]["strata"]) == fields for row in rows)
        for field in fields:
            layers = [row["layout"]["strata"][field] for row in rows]
            assert sorted(layer["index"] for layer in layers) == list(range(len(rows)))
            assert all(layer["count"] == len(rows) for layer in layers)
            assert all(layer["support"] == layers[0]["support"] for layer in layers)


def test_position_seed_does_not_change_task_choices_or_episode_seeds():
    task, position = load_configs()
    original = plan_slots(task, position)
    changed_position = copy.deepcopy(position)
    changed_position["compiler_seed"] += 1
    changed = plan_slots(task, changed_position)
    for before, after in zip(original, changed):
        assert before["parameters"] == after["parameters"]
        assert before["seed"] == after["seed"]
        assert before["position_group"] == after["position_group"]
        assert (
            candidate_for_slot(before, 0).to_dict()["layout"]["strata"] != {}
            or before["task_kind"] == "RouteStick"
        )
