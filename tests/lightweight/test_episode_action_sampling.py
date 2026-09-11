"""冻结对象与动作：真实源码片段、历史提取、随机流及比较器反例。"""

import ast
import copy
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from tests.lightweight.test_native_sampling_config import generator, REPO_ROOT, CONFIG_PATH, BASELINE_COMMIT
from tests._shared import parity_observer as observer
from tests._shared import native_sampling_parity as parity


def source_tree(task, baseline=False):
    path = f"src/robomme/robomme_env/{task}.py"
    return generator._module_tree(generator._read_source(REPO_ROOT, path, BASELINE_COMMIT if baseline else None), path)


def resolver(task):
    tree = source_tree(task)
    fn = generator._func_def(tree, "_resolve_sampling_config")
    native = generator._module_literal(tree, "NATIVE_SAMPLING")
    namespace = {"copy": copy, "json": json, "math": math, "NATIVE_SAMPLING": native}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), task, "exec"), namespace)
    return namespace["_resolve_sampling_config"], native


@pytest.mark.parametrize("task", ["VideoUnmaskSwap", "VideoRepick", "RouteStick"])
def test_direct_environment_config_is_validated_without_sampling(task):
    resolve, native = resolver(task)
    cls = SimpleNamespace(configs={})
    state = torch.get_rng_state().clone()
    assert resolve(cls, None) == resolve(cls, native)
    bad = copy.deepcopy(native)
    key = "walk" if task == "RouteStick" else "object_selection"
    bad["parameters"][key]["不存在的策略"] = True
    with pytest.raises(ValueError):
        resolve(cls, bad)
    assert torch.equal(state, torch.get_rng_state())


@pytest.mark.parametrize("value", [True, -0.1, 1.1, float("nan"), float("inf"), "0.5"])
def test_direction_threshold_rejects_invalid_values(value):
    resolve, native = resolver("RouteStick")
    native["parameters"]["walk"]["direction"]["threshold"] = value
    with pytest.raises(ValueError):
        resolve(SimpleNamespace(configs={}), native)


@pytest.mark.parametrize("value", [0, 0.5, 1])
def test_direction_threshold_accepts_boundaries(value):
    resolve, native = resolver("RouteStick")
    candidate = copy.deepcopy(native)
    candidate["parameters"]["walk"]["direction"]["threshold"] = value
    assert resolve(SimpleNamespace(configs={}), candidate)["parameters"]["walk"]["direction"]["threshold"] == value


@pytest.mark.parametrize("ref", [BASELINE_COMMIT, "94a9b5e"])
def test_historical_action_operands_are_recovered_from_both_source_shapes(ref):
    current = generator.extract_native_sampling(REPO_ROOT)
    old = generator.extract_native_sampling(REPO_ROOT, ref)
    assert generator._operand_view(current) == generator._operand_view(old)


def test_unrecognized_historical_rule_fails_instead_of_using_current_defaults():
    tree = source_tree("VideoRepick", baseline=True)
    step = generator._func_def(tree, "step")
    for node in ast.walk(step):
        if isinstance(node, ast.Compare) and ast.unparse(node) == "dist < closest_dist":
            node.ops = [ast.LtE()]
    with pytest.raises(generator.SamplingConfigError, match="未识别历史规则"):
        generator._historical_action_parameters("VideoRepick", tree, source_tree("utils/route", baseline=True))


def test_cross_check_rejects_declared_but_unused_action_configuration(monkeypatch):
    original = generator._read_source
    def changed(root, path, ref=None):
        source = original(root, path, ref)
        if path.endswith("VideoRepick.py"):
            source = source.replace(b'selection_cfg["hard_target_low"]', b'0')
        return source
    monkeypatch.setattr(generator, "_read_source", changed)
    with pytest.raises(generator.SamplingConfigError, match="新字段消费位置"):
        generator.extract_native_sampling(REPO_ROOT)


def walk_function(baseline=False):
    fn = generator._func_def(source_tree("utils/route", baseline), "generate_dynamic_walk")
    namespace = {"torch": torch, "logger": SimpleNamespace(debug=lambda *args: None)}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "route", "exec"), namespace)
    return namespace["generate_dynamic_walk"]


@pytest.mark.parametrize("backtrack,steps", [(False, 2), (False, 5), (True, 7)])
@pytest.mark.parametrize("start", [None, 0, 4])
def test_real_walk_matches_baseline_nodes_and_rng(backtrack, steps, start):
    cfg = resolver("RouteStick")[1]["parameters"]["walk"]
    left = torch.Generator().manual_seed(16000)
    right = torch.Generator().manual_seed(16000)
    old = walk_function(True)(cfg["node_indices"], steps, start, backtrack, left)
    new = walk_function()(cfg["node_indices"], steps, start, backtrack, right, walk_config=cfg)
    assert new == old
    assert len(new) == steps + 1
    assert torch.equal(left.get_state(), right.get_state())
    assert all(abs(a - b) == 2 for a, b in zip(new, new[1:]))


@pytest.mark.parametrize("task", ["VideoUnmaskSwap", "VideoRepick"])
@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
def test_real_object_selection_expressions_match_baseline(task, difficulty):
    def run(baseline):
        scene = generator._func_def(source_tree(task, baseline), "_load_scene")
        count = (3 if difficulty == "easy" else 4) if task == "VideoUnmaskSwap" else (15 if difficulty == "hard" else 3)
        actors = [object() for _ in range(count)]
        native = resolver(task)[1]
        rng = torch.Generator().manual_seed(1234)
        env = SimpleNamespace(spawned_bins=actors, spawned_cubes=actors, generator=rng)
        ns = {"self": env, "torch": torch, "generator": rng,
              "selection_cfg": native["parameters"]["object_selection"]}
        if task == "VideoUnmaskSwap":
            names = ["num_bins_to_select", "selected_bin_indices", "selected_bins", "target_indices", "remaining_indices", "third_idx", "swap_indices"]
        elif difficulty == "hard":
            names = ["target_idx"]
        else:
            names = ["target_indices", "remaining_indices", "selected_remaining", "selected_indices", "swap_indices"]
        for name in names:
            value = generator._assignment_value(scene, name)
            ns[name] = eval(compile(ast.Expression(value), task, "eval"), ns)
        if task == "VideoUnmaskSwap":
            result = {"pickup": ns["selected_bin_indices"][:2], "initiators": ns["swap_indices"].tolist()}
            if count == 4:
                assert 3 not in ns["selected_bin_indices"]
        elif difficulty == "hard":
            result = {"target": ns["target_idx"], "initiators": []}
        else:
            result = {"target": ns["target_indices"], "initiators": ns["swap_indices"]}
        return result, rng.get_state()
    old, old_state = run(True)
    new, new_state = run(False)
    assert old == new
    assert torch.equal(old_state, new_state)


@pytest.mark.parametrize("task", ["VideoUnmaskSwap", "VideoRepick"])
@pytest.mark.parametrize("points", [[[0, 0], [1, 0], [-1, 0]], [[0, 0], [3, 0], [0.5, 0]]])
def test_real_swap_resolution_matches_baseline_and_preserves_ties(task, points):
    def run(baseline):
        step = generator._func_def(source_tree(task, baseline), "step")
        loops = [node for node in ast.walk(step) if isinstance(node, ast.For) and ast.unparse(node.iter) == "range(len(self.swap_schedule))"]
        assert len(loops) == 1
        actors = [SimpleNamespace(position=np.array(point, dtype=float)) for point in points]
        # _episode_spec=None 表示关闭态（没传 --episode-specs）：新值注入的两个运行时检查点
        # 都不触发，这个循环的最近邻解析语义必须与历史基线逐字相同——本测试验的正是这一点。
        env = SimpleNamespace(_sampling=resolver(task)[1], swap_schedule=[(actors[0], None, 0, 50)],
            swap_pair1_idx1=actors[0], swap_pair1_idx2=None, elapsed_steps=0, start_step=0,
            _episode_spec=None)
        setattr(env, "spawned_bins" if task == "VideoUnmaskSwap" else "spawned_cubes", actors)
        env._get_actor_position = lambda actor: actor.position
        env._refresh_swap_schedule = lambda *args: None
        namespace = {"self": env, "np": np, "timestep": 0}
        exec(compile(ast.Module(body=loops, type_ignores=[]), task, "exec"), namespace)
        index = next(i for i, actor in enumerate(actors) if actor is env.swap_pair1_idx2)
        actors[1].position[:] = [0.001, 0]
        exec(compile(ast.Module(body=loops, type_ignores=[]), task, "exec"), namespace)
        assert env.swap_pair1_idx2 is actors[index]
        return index
    assert run(False) == run(True) == (1 if points[1][0] == 1 else 2)


def sample_env():
    cubes = [SimpleNamespace(name=f"cube_{i}") for i in range(3)]
    def solve(env, planner, t=cubes[1], d="clockwise"):
        pass
    return SimpleNamespace(spawned_cubes=cubes, buttons_grid=cubes, selected_buttons=cubes[:2],
        swing_directions=["clockwise"], swap_schedule=[(cubes[0], cubes[1], 10, 60), (cubes[1], cubes[2], 60, 110)],
        task_list=[{"choice_label": "pick up the cube", "segment": cubes[0], "demonstration": False},
                   {"solve": solve, "expected_dir": "clockwise", "demonstration": True}])


@pytest.mark.parametrize("mutation", ["pickup", "partner", "swap_order", "node", "direction"])
def test_action_binding_changes_are_rejected(mutation):
    env = sample_env()
    original = {"task": "例子", "seed": 1, "difficulty": "easy", "boundaries": [observer._task_state(env)]}
    if mutation == "pickup":
        env.task_list[0]["segment"] = env.spawned_cubes[2]
    elif mutation == "partner":
        env.swap_schedule[0] = (env.spawned_cubes[0], env.spawned_cubes[2], 10, 60)
    elif mutation == "swap_order":
        env.swap_schedule.reverse()
    elif mutation == "node":
        env.selected_buttons.reverse()
    else:
        env.swing_directions[0] = "counterclockwise"
    changed = {**original, "boundaries": [observer._task_state(env)]}
    assert not parity.compare_evidence(original, changed)["passed"]


def test_swap_event_records_both_resolved_object_identities(monkeypatch):
    env = sample_env()
    episode = observer._EpisodeEvidence("VideoRepick", 9000, "easy")
    monkeypatch.setitem(observer._state, "episode", episode)
    module = SimpleNamespace(swap_flat_two_lane=lambda *args, **kwargs: None)
    observer._wrap_event(module, "swap_flat_two_lane")
    module.swap_flat_two_lane(env, cube_a=env.spawned_cubes[0], cube_b=env.spawned_cubes[1], start_step=10, end_step=60, cur_step=10)
    event = observer._current().events[-2]
    assert event["swap_binding"]["a"]["index"] == 0
    assert event["swap_binding"]["b"]["index"] == 1
    assert event["swap_binding"]["swap_index"] == 0
