"""对任务判定的正例、历史失败与错误转换做独立快照测试。"""

import copy

import pytest

from robomme_icl.tasks import TaskEvaluator, language_goal


def _actor(name, kind, p, half=(.015, .015, .015), **extra):
    return {"id": name, "kind": kind, "position": list(p), "quaternion": [1, 0, 0, 0],
            "half_size": list(half), "color": [1, 0, 0, 1], "role": "object", **extra}


def _snapshot(spec, step=0, **extra):
    return {"step": step, "poses": {a["id"]: {"position": list(a["position"]), "quaternion": list(a["quaternion"])} for a in spec["actors"]},
            "linear_velocities": {a["id"]: [0, 0, 0] for a in spec["actors"]},
            "angular_velocities": {a["id"]: [0, 0, 0] for a in spec["actors"]},
            "grasped_ids": [], "phase": "evaluation", "button_pressed": False,
            "forbidden_collision": False, "tcp_position": [0, 0, .02], **extra}


def _repick():
    return {"task_kind": "VideoRepick", "task_parameters": {"target_ids": ["cube_0"], "repeat_count": 1},
            "actors": [_actor("cube_0", "cube", [0, 0, .015]), _actor("cube_1", "cube", [.15, 0, .015])]}


def test_repick_requires_lift_release_and_three_stable_steps():
    spec = _repick()
    evaluator = TaskEvaluator(spec)
    obs = _snapshot(spec, grasped_ids=["cube_0"])
    obs["poses"]["cube_0"]["position"][2] = .10
    for step in range(5):
        obs["step"] = step
        assert evaluator.update(obs)["repeat_count"] == 0
    obs["grasped_ids"] = []
    obs["step"] = 5
    assert evaluator.update(obs)["repeat_count"] == 0
    obs["poses"]["cube_0"]["position"][2] = .015
    for step in (6, 7):
        obs["step"] = step
        assert evaluator.update(obs)["repeat_count"] == 0
    obs["step"] = 8
    assert evaluator.update(obs)["repeat_count"] == 1
    obs["step"] = 9
    obs["button_pressed"] = True
    assert evaluator.update(obs)["success"]


def test_repick_wrong_cube_early_button_and_reset():
    spec = _repick()
    evaluator = TaskEvaluator(spec)
    assert evaluator.update(_snapshot(spec, grasped_ids=["cube_1"]))["fail"]
    assert evaluator.update(_snapshot(spec, 1, button_pressed=True))["fail"]
    assert not evaluator.update(_snapshot(spec, 2))["success"]
    evaluator.reset()
    result = evaluator.update(_snapshot(spec, button_pressed=True))
    assert result["fail"] and not result["success"]
    assert result["repeat_count"] == 0


def test_demonstration_is_excluded_and_repeated_step_is_idempotent():
    spec = _repick()
    evaluator = TaskEvaluator(spec)
    obs = _snapshot(spec, phase="demonstration", grasped_ids=["cube_1"])
    assert not evaluator.update(obs)["fail"]
    obs["phase"] = "evaluation"
    assert not evaluator.update(obs)["fail"]
    obs["step"] = 1
    assert evaluator.update(obs)["fail"]
    obs["step"] = 0
    with pytest.raises(ValueError, match="倒退"):
        evaluator.update(obs)


def _unmask():
    return {"task_kind": "VideoUnmaskSwap", "task_parameters": {"target_container_ids": ["container_0", "container_1"]},
            "actors": [_actor(f"container_{i}", "container", [i*.15, 0, .036], half=(.03, .03, .036)) for i in range(3)]}


def test_unmask_requires_actual_grasp_and_order():
    spec = _unmask()
    evaluator = TaskEvaluator(spec)
    obs = _snapshot(spec)
    obs["poses"]["container_0"]["position"][2] = .15
    assert evaluator.update(obs)["cursor"] == 0
    obs["step"] = 1
    obs["grasped_ids"] = ["container_0"]
    assert evaluator.update(obs)["cursor"] == 1
    obs["step"] = 2
    obs["grasped_ids"] = ["container_1"]
    obs["poses"]["container_1"]["position"][2] = .15
    assert evaluator.update(obs)["success"]
    obs["step"] = 3
    obs["forbidden_collision"] = True
    result = evaluator.update(obs)
    assert result["fail"] and not result["success"]


def test_unmask_wrong_first_target_latches_failure():
    spec = _unmask()
    evaluator = TaskEvaluator(spec)
    result = evaluator.update(_snapshot(spec, grasped_ids=["container_1"]))
    assert result["fail"] and not result["success"]


def test_unmask_picking_hidden_cube_is_not_a_valid_container_pick():
    spec = _unmask()
    spec["actors"].append(_actor("hidden_cube", "cube", [0, 0, .0167]))
    result = TaskEvaluator(spec).update(_snapshot(spec, grasped_ids=["hidden_cube"]))
    assert result["fail"] and not result["success"]


def _binfill():
    return {"task_kind": "BinFill", "task_parameters": {"target_counts": {"red": 1, "blue": 1}},
            "actors": [_actor("board", "board", [0, 0, .025], half=(.05, .05, .025), hole_half_size=.04),
                       _actor("red", "cube", [-.15, 0, .015], color_name="red"),
                       _actor("blue", "cube", [.15, 0, .015], color_name="blue")]}


def test_binfill_order_free_unique_counts_and_button():
    spec = _binfill()
    evaluator = TaskEvaluator(spec)
    obs = _snapshot(spec)
    step = 0
    for actor_id in ("blue", "red"):
        obs["poses"][actor_id]["position"] = [0, 0, .015]
        for _ in range(3):
            obs["step"] = step
            step += 1
            evaluator.update(obs)
        # 模拟已投入的方块留在孔内，禁止每帧重复计数。
    obs["step"] = step
    obs["button_pressed"] = True
    result = evaluator.update(obs)
    assert result["success"]
    assert result["color_counts"] == {"red": 1, "blue": 1}


def test_binfill_full_shape_must_fit_and_early_button_fails():
    spec = _binfill()
    evaluator = TaskEvaluator(spec)
    obs = _snapshot(spec)
    obs["poses"]["red"]["position"] = [.035, 0, .015]
    for step in range(5):
        obs["step"] = step
        assert evaluator.update(obs)["inserted_ids"] == []
    obs["step"] = 5
    obs["button_pressed"] = True
    assert evaluator.update(obs)["fail"]


def _route():
    actors = [_actor(f"target_{i}", "target", [i*.14, 0, .02], half=(.02, .02, .002)) for i in range(5)]
    actors += [_actor(f"obstacle_{i}", "obstacle", [.07+i*.14, 0, .02], half=(.015, .015, .02)) for i in range(4)]
    return {"task_kind": "RouteStick", "task_parameters": {"path_indices": [0, 1], "directions": [1]}, "actors": actors}


def test_route_correct_side_and_wrong_side_or_shortcut():
    spec = _route()
    evaluator = TaskEvaluator(spec)
    path = [(0, 0, .02), (0, .06, .02), (.07, .06, .02), (.14, .06, .02), (.14, 0, .02)]
    for step, tcp in enumerate(path):
        result = evaluator.update(_snapshot(spec, step, tcp_position=tcp))
    assert result["success"], result
    evaluator.reset()
    for step, tcp in enumerate([(0, 0, .02), (.07, -.06, .02), (.14, 0, .02)]):
        result = evaluator.update(_snapshot(spec, step, tcp_position=tcp))
    assert result["fail"] and not result["success"]
    evaluator.reset()
    evaluator.update(_snapshot(spec, tcp_position=(0, 0, .02)))
    result = evaluator.update(_snapshot(spec, 1, tcp_position=(.14, 0, .02)))
    assert result["fail"] and any("穿越" in reason for reason in result["failure_reasons"])


def test_task_spec_is_not_mutated_by_evaluation():
    spec = _repick()
    original = copy.deepcopy(spec)
    TaskEvaluator(spec).update(_snapshot(spec))
    assert spec == original


def test_binfill_parked_inserted_cube_keeps_its_count():
    spec = _binfill()
    evaluator = TaskEvaluator(spec)
    obs = _snapshot(spec)
    obs["poses"]["red"]["position"] = [0, 0, .015]
    for step in range(3):
        obs["step"] = step
        evaluator.update(obs)
    obs["poses"]["red"]["position"] = [10, 10, 10]
    for step in range(3, 7):
        obs["step"] = step
        result = evaluator.update(obs)
        assert result["color_counts"] == {"red": 1}
        assert result["inserted_ids"] == ["red"]
    assert not result["success"]
    evaluator.reset()
    assert evaluator.update(_snapshot(spec))["inserted_ids"] == []


def test_unmask_demonstration_pick_does_not_advance_evaluation():
    spec = _unmask()
    evaluator = TaskEvaluator(spec)
    obs = _snapshot(spec, phase="demonstration", grasped_ids=["container_0"])
    obs["poses"]["container_0"]["position"][2] = .15
    for step in range(5):
        obs["step"] = step
        assert evaluator.update(obs)["cursor"] == 0
    obs["step"] = 5
    obs["phase"] = "evaluation"
    obs["grasped_ids"] = []
    assert evaluator.update(obs)["cursor"] == 0


def test_repick_reset_drops_lift_and_stability_cache():
    spec = _repick()
    evaluator = TaskEvaluator(spec)
    obs = _snapshot(spec, grasped_ids=["cube_0"])
    obs["poses"]["cube_0"]["position"][2] = .10
    assert evaluator.update(obs)["holding_phase"] == "lifted"
    evaluator.reset()
    for step in range(5):
        result = evaluator.update(_snapshot(spec, step))
    assert result["repeat_count"] == 0
    assert result["holding_phase"] == "ready"


def test_route_start_is_only_first_event_and_wrong_target_fails():
    spec = _route()
    evaluator = TaskEvaluator(spec)
    result = evaluator.update(_snapshot(spec, tcp_position=(0, 0, .02)))
    assert result["cursor"] == 1
    assert result["next_target"] == "target_1"
    assert not result["success"]
    result = evaluator.update(_snapshot(spec, 1, tcp_position=(.28, 0, .02)))
    assert result["fail"] and not result["success"]
    evaluator.reset()
    result = evaluator.update(_snapshot(spec, tcp_position=(.14, 0, .02)))
    assert result["fail"] and result["cursor"] == 0


def test_nonfinite_physics_pose_cannot_succeed():
    spec = _unmask()
    obs = _snapshot(spec, grasped_ids=["container_0"])
    obs["poses"]["container_0"]["position"][2] = float("inf")
    result = TaskEvaluator(spec).update(obs)
    assert result["fail"] and not result["success"]


def test_binfill_language_uses_exact_counts_without_color_order_constraint():
    spec = _binfill()
    spec["task_parameters"]["target_counts"] = {"blue": 2, "green": 0, "red": 1}
    goal = language_goal(spec)
    assert goal == "put exactly one red cube and two blue cubes into the bin in any order, then press the button to stop"
    assert "green" not in goal
    spec["task_parameters"]["target_counts"] = {"red": 1, "green": 0, "blue": 2}
    assert language_goal(spec) == goal


def test_unmask_language_follows_parent_mapping_and_requested_order():
    spec = _unmask()
    spec["task_parameters"]["target_container_ids"] = ["container_1", "container_0"]
    spec["actors"] += [
        _actor("hidden_0", "cube", [0, 0, .0167], parent_id="container_0", color_name="red"),
        _actor("hidden_1", "cube", [.15, 0, .0167], parent_id="container_1", color_name="blue"),
    ]
    original = copy.deepcopy(spec)
    goal = language_goal(spec)
    assert goal == "watch the video carefully, then pick up the container hiding the blue cube, then pick up the container hiding the red cube"
    assert "container_" not in goal and "hidden_" not in goal
    assert spec == original
    for actor in spec["actors"]:
        actor["position"] = [10, 20, 30]
    assert language_goal(spec) == goal


def test_unmask_language_refuses_missing_color_mapping():
    with pytest.raises(ValueError, match="缺少藏块颜色"):
        language_goal(_unmask())


def test_repick_language_does_not_reveal_target_identity_or_color():
    spec = _repick()
    spec["task_parameters"]["repeat_count"] = 3
    goal = language_goal(spec)
    assert "exactly three times" in goal and "press the button" in goal
    assert "cube_0" not in goal and "red" not in goal
    spec["task_parameters"]["target_ids"] = ["cube_1"]
    assert language_goal(spec) == goal


def test_route_language_preserves_demonstration_dependency():
    spec = _route()
    spec["task_parameters"]["walk_steps"] = 1
    goal = language_goal(spec)
    assert "same target sequence" in goal and "same side as shown" in goal
    assert "exactly one segment" in goal and "target_0" not in goal
    spec["task_parameters"]["directions"] = [-1]
    assert language_goal(spec) == goal


def test_route_planar_markers_support_real_marker_and_stick_heights():
    spec = _route()
    for actor in spec["actors"]:
        if actor["kind"] == "target":
            actor["position"][2] = .01
        else:
            actor["position"][2] = .05
            actor["half_size"][2] = .05
    evaluator = TaskEvaluator(spec)
    path = [(0, 0, .07), (0, .06, .07), (.07, .06, .07), (.14, .06, .07), (.14, 0, .07)]
    for step, tcp in enumerate(path):
        result = evaluator.update(_snapshot(spec, step, tcp_position=tcp))
        if step == 0:
            assert result["cursor"] == 1 and not result["success"]
    assert result["success"] and not result["fail"]
    evaluator.reset()
    result = evaluator.update(_snapshot(spec, tcp_position=(.14, 0, .07)))
    assert result["fail"] and not result["success"]


@pytest.mark.parametrize("height", [-.001, .151])
def test_route_target_height_window_applies_to_correct_and_wrong_targets(height):
    spec = _route()
    evaluator = TaskEvaluator(spec)
    result = evaluator.update(_snapshot(spec, tcp_position=(0, 0, height)))
    assert result["cursor"] == 0 and not result["success"]
    result = evaluator.update(_snapshot(spec, 1, tcp_position=(.14, .10, height)))
    assert result["cursor"] == 0
    evaluator.reset()
    result = evaluator.update(_snapshot(spec, tcp_position=(.14, 0, height)))
    assert result["cursor"] == 0 and not result["fail"]
