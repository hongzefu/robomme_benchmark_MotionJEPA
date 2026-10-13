"""三任务碰撞接线验收；GPU 用例仅由主会话在合并后的主检出执行。

不标 gpu 的用例只检查真实类的 MRO 与对象接口，不创建仿真。
运行期故障送达生成器及产物隔离由独立的 test_fatal_catch 验收，
此处仅检验 reset 拒绝与真实父类 step 的时序、钩子及 fatal 留证。
"""

from types import SimpleNamespace
from pathlib import Path
import json
import os
import subprocess

import numpy as np
import pytest

import robomme.robomme_env  # noqa: F401
import robomme_xhard
from robomme_xhard.base import XHardMixin
from robomme_xhard.collision import SwapCollisionError
from robomme_xhard.collision import bin_collision as bc
from robomme_xhard.envs.button_unmask_swap import ButtonUnmaskSwapXHard
from robomme_xhard.envs.video_repick import VideoRepickXHard
from robomme_xhard.envs.video_unmask_swap import VideoUnmaskSwapXHard
from robomme_xhard.swap_plan import SwapCollisionMixin
from robomme_xhard import swap_plan as sp


# 官网类内顺序：永久性两项，然后参考类 VideoRepick。
CASES = [
    ("VideoUnmaskSwap", VideoUnmaskSwapXHard, 5700, "spawned_bins", "bin_"),
    ("ButtonUnmaskSwap", ButtonUnmaskSwapXHard, 7700, "spawned_bins", "bin_"),
    ("VideoRepick", VideoRepickXHard, 9600, "spawned_cubes", "cube_"),
]
TIERS = ("xhard12", "xhard14", "xhard16", "xhard18", "xhard20")


@pytest.mark.parametrize("task,cls,seed,attr,prefix", CASES)
def test_cpu_mro_and_actor_interfaces(task, cls, seed, attr, prefix):
    assert cls.__mro__[1:3] == (SwapCollisionMixin, XHardMixin)
    assert cls.__mro__[3].__name__ == task
    assert "step" not in SwapCollisionMixin.__dict__
    assert cls.step is cls.__mro__[3].step
    assert cls._before_control_step is SwapCollisionMixin._before_control_step
    assert all("_before_control_step" not in base.__dict__ for base in cls.__mro__[2:-1]
               if base.__name__ != "BaseEnv")
    assert cls._before_simulation_step is SwapCollisionMixin._before_simulation_step
    assert cls._after_simulation_step is SwapCollisionMixin._after_simulation_step
    assert cls.swap_name_prefix == prefix
    actors = [object(), object(), object()]
    buttons = [object(), object()]
    fake = SimpleNamespace(**{attr: actors}, button_left=buttons[0], button_right=buttons[1])
    assert cls._swap_actors(fake) == actors
    assert cls._swap_actors(fake) is not actors
    expected = [] if task == "VideoUnmaskSwap" else (buttons if task == "ButtonUnmaskSwap" else buttons[:1])
    assert cls._bystander_actors(fake) == expected


def _make(task, seed, tier="xhard12"):
    import gymnasium as gym

    return gym.make(
        robomme_xhard.env_name(task), seed=seed, difficulty=tier,
        obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos",
        render_mode="rgb_array", reward_mode="dense",
    )


@pytest.mark.gpu
@pytest.mark.parametrize("task,cls,seed,attr,prefix", CASES)
def test_reset_certifies_all_pairs(task, cls, seed, attr, prefix):
    env = _make(task, seed)
    try:
        env.reset(seed=seed)
        u = env.unwrapped
        actors = u._swap_actors()
        pairs = u._xhard_swap_plan["pairs"]
        assert len(pairs) == u.swap_times == len(u.swap_schedule)
        for k, (a, b, distance, gap) in enumerate(pairs, 1):
            assert getattr(u, f"swap_pair{k}_idx1") is actors[a]
            assert getattr(u, f"swap_pair{k}_idx2") is actors[b]
            assert a != b and np.isfinite(distance) and np.isfinite(gap)
        plan = u._xhard_swap_plan
        assert all(plan["graph"]["adj"][a][b] for a, b in plan["slot_pairs"])
        assert len(u._bystander_actors()) == (0 if task == "VideoUnmaskSwap" else (2 if task == "ButtonUnmaskSwap" else 1))
        assert u._xhard_runtime_checks == []
        assert u._xhard_fatal is None
    finally:
        env.close()


@pytest.mark.gpu
@pytest.mark.parametrize("task,cls,seed,attr,prefix", CASES)
def test_five_tiers_share_pair_prefix(task, cls, seed, attr, prefix):
    previous = []
    previous_slots = previous_graph = None
    for tier in TIERS:
        env = _make(task, seed, tier)
        try:
            env.reset(seed=seed)
            plan = env.unwrapped._xhard_swap_plan
            if previous_slots is not None:
                assert plan["slots"] == previous_slots and plan["graph"] == previous_graph
            previous_slots, previous_graph = plan["slots"], plan["graph"]
            pairs = [tuple(row[:2]) for row in plan["pairs"]]
            assert pairs[:len(previous)] == previous
            previous = pairs
        finally:
            env.close()


def _enter_exchange_window(u, task):
    if task == "VideoRepick":
        # 测试仅选中已存在的交换子任务，不覆写父类 step 或调度。
        # 第一次真实 step 必须自行把占位 400 改成当前步号。
        assert not u.static_flag and u.swap_schedule[0][2] == 400
        u.current_task_specialflag = "swap"
        return int(u.elapsed_steps)
    return int(u.swap_schedule[0][2])


def _write_timing_evidence(u, task, seed, start, hooks):
    # 只消费主会话给出的唯一目录，绝不在工作树或默认路径制造产物。
    root = Path(os.environ["XHARD_TIMING_EVIDENCE_ROOT"]).resolve()
    artifacts = Path(__file__).resolve().parents[3] / "artifacts"
    assert root.is_relative_to(artifacts.resolve()) and root != artifacts.resolve()
    root.mkdir(parents=True, exist_ok=True)
    evidence = dict(task=task, seed=seed, tier="xhard12", start=start,
                    git_commit=subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[3], text=True).strip(),
                    current_step=int(u.elapsed_steps), phase="before_physics", hooks=hooks,
                    fatal=u._xhard_fatal, runtime_checks=u._xhard_runtime_checks,
                    sim_backend=str(u.backend.sim_backend), gpu_sim_enabled=bool(u.gpu_sim_enabled),
                    schedule=[[int(row[2]), int(row[3])] for row in u.swap_schedule])
    path = root / f"{task}-seed{seed}-step{int(u.elapsed_steps)}.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.gpu
@pytest.mark.parametrize("task,cls,seed,attr,prefix", CASES)
def test_real_step_first_start_and_shared_endpoint(monkeypatch, task, cls, seed, attr, prefix):
    env = _make(task, seed)
    try:
        env.reset(seed=seed)
        u = env.unwrapped
        start = _enter_exchange_window(u, task)
        hooks = []
        original = SwapCollisionMixin._before_control_step
        def traced(self):
            hooks.append(dict(control_step=int(self.elapsed_steps), phase="before_physics"))
            return original(self)
        monkeypatch.setattr(SwapCollisionMixin, "_before_control_step", traced)
        # 真正逐步推进，含首次起点与 50 步后的相邻共享端点；不跳改 elapsed_steps。
        while int(u.elapsed_steps) <= start + 50:
            try:
                u.step(None)
            finally:
                _write_timing_evidence(u, task, seed, start, hooks)
            assert u._xhard_fatal is None, u._xhard_fatal
        assert u.swap_schedule[0][2] == start
        assert u.swap_schedule[0][3] == u.swap_schedule[1][2] == start + 50
        sweeps = [r for r in u._xhard_runtime_checks if r["kind"] == "swap_sweep"]
        assert [r["sweep_index"] for r in sweeps] == [0, 1]
        assert [r["control_step"] for r in sweeps] == [start, start + 50]
        assert [r["control_step"] for r in hooks].count(start) == 1
        assert [r["control_step"] for r in hooks].count(start + 50) == 1
        for row in sweeps:
            assert row["phase"] == "before_physics"
            assert row["endpoint_match"] and row["rejection"] is None
            assert row["endpoints"]["mismatches"] == []
            for key in ("a_p", "a_q", "b_p", "b_q"):
                assert np.array_equal(row["endpoints"]["actual"][key], row["endpoints"]["cached"][key])
        kinds = {r["kind"] for r in u._xhard_runtime_checks}
        assert {"substep_before", "substep_after"} <= kinds
    finally:
        env.close()


@pytest.mark.gpu
@pytest.mark.parametrize("task,cls,seed,attr,prefix", CASES)
def test_reset_rejection_propagates_original_evidence(monkeypatch, task, cls, seed, attr, prefix):
    env = _make(task, seed)
    rejection = bc.CollisionRejection("contact", "initial", prefix + "0", prefix + "1", 0, 0, gap_m=-0.01)
    try:
        original = bc.check_bin_layout

        def reject_initial(states, *args, **kwargs):
            if kwargs.get("stage") == "initial":
                return -0.01, rejection
            return original(states, *args, **kwargs)

        monkeypatch.setattr(bc, "check_bin_layout", reject_initial)
        with pytest.raises(SwapCollisionError) as caught:
            env.reset(seed=seed, options={"reconfigure": True})
        assert caught.value.stage == "initial"
        assert caught.value.rejection is rejection
    finally:
        env.close()


@pytest.mark.gpu
@pytest.mark.parametrize("task,cls,seed,attr,prefix", CASES)
def test_runtime_failure_keeps_progress_and_first_evidence(monkeypatch, task, cls, seed, attr, prefix):
    env = _make(task, seed)
    try:
        env.reset(seed=seed)
        u = env.unwrapped
        start = _enter_exchange_window(u, task)
        visited = []

        def reject(self, k):
            visited.append(k)
            self._record_fatal("SwapCollisionError", "segment_start", k,
                              detail={"test_injection": True}, check="sweep_actual")

        monkeypatch.setattr(SwapCollisionMixin, "_check_segment_start", reject)
        while int(u.elapsed_steps) <= start:
            u.step(None)
        fatal = dict(u._xhard_fatal)
        assert visited == [0]
        assert fatal["error_type"] == "SwapCollisionError"
        assert fatal["stage"] == "segment_start" and fatal["k"] == 0
        before = int(u.elapsed_steps)
        u.step(None)
        assert int(u.elapsed_steps) == before + 1
        assert u._xhard_fatal == fatal and visited == [0]
    finally:
        env.close()


@pytest.mark.gpu
def test_isolated_slot_seed_rejected_at_graph():
    # gym.make 内部也可能首次建场；两条路径都必须带原始 graph 证据。
    env = None
    try:
        with pytest.raises(SwapCollisionError) as caught:
            env = _make("ButtonUnmaskSwap", 10500, "xhard20")
            env.reset(seed=10500)
        assert caught.value.stage == "graph"
        assert "孤立槽" in caught.value.rejection.detail
    finally:
        if env is not None:
            env.close()


@pytest.mark.gpu
def test_two_edge_seed_rejected_at_graph():
    # 首次建场可能在 _make 内拒绝，条件清理不得掩盖原始 graph 证据。
    env = None
    try:
        with pytest.raises(SwapCollisionError) as caught:
            env = _make("VideoUnmaskSwap", 6500, "xhard20")
            env.reset(seed=6500)
        assert caught.value.stage == "graph"
        assert caught.value.rejection.detail.startswith("可行槽对不足=2/3")
        evidence = json.loads(caught.value.rejection.detail.split("原始边证据=", 1)[1])
        assert len(evidence["feasible_edges"]) == 2
    finally:
        if env is not None:
            env.close()


@pytest.mark.gpu
def test_button_pose_loadtime_matches_initialized_geometry(monkeypatch):
    """首次建场认证时保留推导值，初始化后以真实子连杆世界位姿独立对照三个按钮。"""
    captured = {}
    original = sp.button_shape_poses
    def capture(articulation):
        base_pose, cap_pose = original(articulation)
        captured[id(articulation)] = (np.asarray(cap_pose.p, dtype=np.float64).copy(),
                                      np.asarray(cap_pose.q, dtype=np.float64).copy())
        return base_pose, cap_pose
    monkeypatch.setattr(sp, "button_shape_poses", capture)
    buttons, max_dp, max_angle = 0, 0., 0.
    for task, seed, expected_count in (("ButtonUnmaskSwap", 7700, 2), ("VideoRepick", 9600, 1)):
        captured.clear()
        env = _make(task, seed)
        try:
            env.reset(seed=seed)
            bystanders = env.unwrapped._bystander_actors()
            assert len(bystanders) == expected_count
            assert set(captured) == {id(button) for button in bystanders}
            for button in bystanders:
                qpos = bc._to_numpy(button.get_qpos())
                assert np.array_equal(qpos, np.zeros(1))
                links = {link.get_name(): link for link in button.get_links()}
                component = links["button_cap"]._objs[0]
                shapes = component.get_collision_shapes()
                assert len(shapes) == 1
                actual = component.entity.pose * shapes[0].local_pose
                derived_p, derived_q = captured[id(button)]
                actual_p, actual_q = np.asarray(actual.p, dtype=np.float64), np.asarray(actual.q, dtype=np.float64)
                dp = float(np.linalg.norm(derived_p-actual_p))
                relative = bc.quat_to_matrix(bc._normalize_quat(derived_q)).T @ bc.quat_to_matrix(bc._normalize_quat(actual_q))
                qrelative = bc.matrix_to_quat(relative)
                angle = float(2*np.arctan2(np.linalg.norm(qrelative[1:]), abs(qrelative[0])))
                assert np.allclose(derived_p, actual_p, atol=1e-6, rtol=0)
                assert dp <= 1e-6 and angle <= 1e-6
                buttons += 1
                max_dp, max_angle = max(max_dp, dp), max(max_angle, angle)
        finally:
            env.close()
    assert buttons == 3
    print(f"BUTTON_POSE_LOADTIME=PASS buttons={buttons} max_dp_m={max_dp:.12g} max_angle_rad={max_angle:.12g}")
