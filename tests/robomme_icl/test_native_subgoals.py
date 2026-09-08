"""使用原版实际谓词和任务列表检查边界，禁止新版另设更严格判据。"""

from types import SimpleNamespace

import numpy as np
import pytest
import torch

from robomme.robomme_env.BinFill import BinFill
from robomme.robomme_env.utils import subgoal_evaluate_func as predicates
from robomme.robomme_env.utils import statechange


class Actor:
    def __init__(self, name, position):
        self.name = name
        self.pose = SimpleNamespace(
            p=torch.tensor([position], dtype=torch.float32),
            q=torch.tensor([[1.0, 0.0, 0.0, 0.0]]),
        )

    def set_pose(self, pose):
        self.pose.p = torch.tensor(np.asarray(pose.p)[None], dtype=torch.float32)
        self.pose.q = torch.tensor(np.asarray(pose.q)[None], dtype=torch.float32)

    def set_linear_velocity(self, value):
        pass

    def set_angular_velocity(self, value):
        pass


def environment():
    held = set()
    qpos = torch.tensor([[0.0] * 7 + [0.04, 0.04]])
    agent = SimpleNamespace(
        tcp=Actor("tcp", [0.3, 0.3, 0.2]),
        robot=SimpleNamespace(get_qpos=lambda: qpos, qpos=qpos),
        is_grasping=lambda actor: torch.tensor([actor.name in held]),
        reset=lambda _: None,
    )
    return SimpleNamespace(agent=agent, held=held, use_demonstrationwrapper=True)


@pytest.mark.parametrize(
    "height,held,expected",
    [(0.05, True, False), (0.051, True, True), (0.2, False, False)],
)
def test_native_cube_pickup_requires_height_and_real_grasp(height, held, expected):
    env = environment()
    actor = Actor("cube", [0.0, 0.0, height])
    if held:
        env.held.add("cube")
    assert bool(predicates.is_obj_pickup(env, actor)) is expected


def test_native_container_pickup_uses_original_height_rule():
    env = environment()
    assert not bool(predicates.is_bin_pickup(env, Actor("bin", [0.0, 0.0, 0.15])))
    # 原版此谓词不检查夹爪；保持其真实口径，不能偷偷换成新版抓持判据。
    assert bool(predicates.is_bin_pickup(env, Actor("bin", [0.0, 0.0, 0.151])))


def test_native_drop_threshold_keeps_wrapper_context():
    env = environment()
    actor = Actor("cube", [0.0, 0.0, 0.15])
    assert not predicates.is_obj_dropped(env, actor)
    env.use_demonstrationwrapper = False
    assert predicates.is_obj_dropped(env, actor)
    env.held.add("cube")
    assert not predicates.is_obj_dropped(env, actor)


def test_binfill_uses_original_deletion_count_and_final_button_check():
    env = environment()
    red = Actor("red", [0.2, 0.0, 0.02])
    blue = Actor("blue", [0.0, 0.0, 0.02])
    button = SimpleNamespace(get_qpos=lambda: torch.tensor([[0.0]]))
    env.__dict__.update(
        device="cpu",
        generator=torch.Generator().manual_seed(0),
        table_scene=SimpleNamespace(initialize=lambda _: None),
        all_cubes=[red, blue],
        red_cubes=[red],
        blue_cubes=[blue],
        green_cubes=[],
        red_cubes_target_number=1,
        blue_cubes_target_number=0,
        green_cubes_target_number=0,
        board_with_hole=Actor("board", [0.0, 0.0, 0.025]),
        button=button,
        cap_link=button,
        robomme_failure_recovery=False,
    )
    BinFill._initialize_episode(env, torch.tensor([0]), {})
    assert [entry["name"] for entry in env.task_list][-2:] == [
        "put it into the bin",
        "press the button",
    ]
    assert env.task_list[1]["func"]()
    assert env.blue_cubes_in_bin == 1 and env.red_cubes_in_bin == 0
    assert np.array_equal(
        blue.pose.p.numpy()[0], np.array([10.0, 10.0, 0.0], dtype=np.float32)
    )
    assert not env.task_list[1]["func"]()
    assert env.blue_cubes_in_bin == 1
    assert bool(env.task_list[-1]["failure_func"]()[0])


@pytest.mark.parametrize("depth,expected", [(0.005, False), (0.0051, True)])
def test_native_button_depth_boundary(depth, expected):
    button = SimpleNamespace(get_qpos=lambda: torch.tensor([[-depth]]))
    env = SimpleNamespace(button=button)
    assert bool(predicates.is_button_pressed(env, button)) is expected


def test_native_container_reveal_is_at_window_midpoint():
    env = SimpleNamespace()
    actor = Actor("container", [0.1, -0.1, 0.052])
    original = actor.pose.p.clone()
    for step in (0, 31):
        statechange.lift_and_drop_objects_back_to_original(env, actor, 0, 64, step)
        assert actor.pose.p[0, 0] == 10
    statechange.lift_and_drop_objects_back_to_original(env, actor, 0, 64, 32)
    assert torch.equal(actor.pose.p, original)


def test_native_hidden_cube_returns_to_its_container_at_swap_end():
    env = SimpleNamespace()
    cube = Actor("cube", [0.1, 0.2, 0.02])
    container = Actor("container", [-0.1, -0.2, 0.052])
    statechange.lift_and_drop_objectA_onto_objectB(env, cube, container, 64, 114, 63)
    assert cube.pose.p[0, 0] != 10
    for step in (64, 113):
        statechange.lift_and_drop_objectA_onto_objectB(
            env, cube, container, 64, 114, step
        )
        assert cube.pose.p[0, 0] == 10
    statechange.lift_and_drop_objectA_onto_objectB(env, cube, container, 64, 114, 114)
    assert np.array_equal(
        cube.pose.p.numpy()[0], np.array([-0.1, -0.2, 0.02], dtype=np.float32)
    )


def test_native_planner_exhaustion_preserves_three_screw_three_rrt_attempts():
    from robomme.env_record_wrapper.OraclePlannerDemonstrationWrapper import (
        OraclePlannerDemonstrationWrapper,
    )

    calls = []
    planner = SimpleNamespace(
        move_to_pose_with_screw=lambda *a, **k: calls.append("screw") or -1,
        move_to_pose_with_RRTStar=lambda *a, **k: calls.append("rrt") or -1,
    )
    policy = SimpleNamespace(_oracle_screw_max_attempts=3, _oracle_rrt_max_attempts=3)
    OraclePlannerDemonstrationWrapper._wrap_planner_with_screw_then_rrt_retry(
        policy, planner, RuntimeError
    )
    with pytest.raises(RuntimeError, match="exhausted"):
        planner.move_to_pose_with_screw(None)
    assert calls == ["screw"] * 3 + ["rrt"] * 3
