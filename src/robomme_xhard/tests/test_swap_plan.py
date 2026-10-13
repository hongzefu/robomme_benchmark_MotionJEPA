"""纯 CPU 的规划、端点绑定与运行失败留证测试，不创建仿真环境。"""

from types import SimpleNamespace
import json
from pathlib import Path
import subprocess
import numpy as np
import pytest
import torch

from robomme_xhard import swap_plan as sp
from robomme_xhard.collision import bin_collision as bc
from robomme_xhard.collision import SwapCollisionError, SceneGenerationError


def state(i, xy):
    p, q = bc.cube_actor_pose(xy, 0, 0.005)
    return bc.ObjectState(str(i), p, q, bc.cube_shape_specs(0.005))


def rectangle():
    return {i: state(i, xy) for i, xy in enumerate([(-.05, -.1), (-.05, .1), (.1, .1), (.1, -.1)])}


def generator(seed=7):
    return torch.Generator().manual_seed(seed)


def fake_read(actor, name=None):
    return bc.ObjectState(name or actor.name, actor.p.copy(), actor.q.copy(), actor.shapes)


def test_graph_all_pairs_once_and_bystanders(monkeypatch):
    seen = []
    def sweep(a, b, others, **kwargs):
        seen.append((a.name, b.name, [s.name for s in others], kwargs))
        return .01, None
    monkeypatch.setattr(bc, "check_swap_sweep", sweep)
    adj, gaps = sp.slot_graph(rectangle(), [state(9, (2, 2))])
    assert len(seen) == len(gaps) == 6
    assert all("9" in row[2] and len(row[2]) == 3 for row in seen)
    assert all(row[3] == dict(sweep_index=-1, stage="graph") for row in seen)
    assert all(sum(row) == 3 for row in adj)


def test_graph_isolated_rejected():
    with pytest.raises(SwapCollisionError) as exc:
        sp.require_every_slot_covered([[False, True, False], [True, False, False], [False]*3], {"0-2": -.1})
    assert exc.value.stage == "graph"
    assert "孤立槽=[2]" in exc.value.rejection.detail


def test_disconnected_graph_diagonal_prefix_and_reproducibility(monkeypatch):
    adj = [[False]*4 for _ in range(4)]
    for a, b in ((0, 2), (1, 3)):
        adj[a][b] = adj[b][a] = True
    monkeypatch.setattr(sp, "slot_graph", lambda *args: (adj, {}))
    monkeypatch.setattr(bc, "check_swap_sweep", lambda *args, **kwargs: (.01, None))
    full = sp.plan_swaps(rectangle(), [], 11, generator(), s_max=11)
    short = sp.plan_swaps(rectangle(), [], 4, generator(), s_max=11)
    assert short.pairs == full.pairs[:4]
    assert short.slot_pairs == full.slot_pairs[:4]
    assert full.as_dict() == sp.plan_swaps(rectangle(), [], 11, generator(), s_max=11).as_dict()
    assert all(adj[a][b] for a, b in full.slot_pairs)
    assert all(set(a) != set(b) for a, b in zip(full.slot_pairs, full.slot_pairs[1:]))
    assert full.spread_full <= 1
    assert sum(full.initiator_usage) == sum(full.partner_usage) == 11
    assert full.usage == [a+b for a, b in zip(full.initiator_usage, full.partner_usage)]


@pytest.mark.parametrize("key", ["half", "local_p", "local_q", "z", "count"])
def test_static_slots_reject_any_difference(key):
    states = list(rectangle().values())
    if key == "z":
        states[1].p[2] += 1e-12
    elif key == "count":
        states[1].shapes = ()
    else:
        shape = states[1].shapes[0]
        changed = {field: getattr(shape, field).copy() for field in ("half", "local_p", "local_q")}
        changed[key][0] += 1e-12
        states[1].shapes = (bc.ShapeSpec(**changed),)
    with pytest.raises(SceneGenerationError, match="对象 1"):
        sp.require_static_slots(states)


def test_k8_inconsistent_rejected(monkeypatch):
    monkeypatch.setattr(sp, "slot_graph", lambda *args: ([[False, True], [True, False]], {}))
    rejection = bc.CollisionRejection("contact", "sweep", "0", "1", 0, 0, -.01)
    monkeypatch.setattr(bc, "check_swap_sweep", lambda *args, **kwargs: (-.01, rejection))
    with pytest.raises(SwapCollisionError) as exc:
        sp.plan_swaps([state(0, (-.1, 0)), state(1, (.1, 0))], [], 1, generator())
    assert exc.value.stage == "sweep"
    assert "G 与逐段不符" in exc.value.rejection.detail


def test_certify_prefills_and_independent_stream(monkeypatch):
    actors = list(rectangle().values())
    env = SimpleNamespace(seed=9, swap_times=4, robomme_base_id="VideoUnmaskSwap")
    env._refresh_swap_schedule = lambda: None
    monkeypatch.setattr(bc, "object_state_from_actor", fake_read)
    before = torch.get_rng_state().clone()
    plan = sp.certify_swap_plan(env, actors, [], "bin_")
    assert torch.equal(before, torch.get_rng_state())
    assert plan.s_max == 11 and len(plan.pairs) == 4
    for k, (a, b, _, _) in enumerate(plan.pairs, 1):
        assert getattr(env, f"swap_pair{k}_idx1") is actors[a]
        assert getattr(env, f"swap_pair{k}_idx2") is actors[b]
    assert env._xhard_swap_plan == plan.as_dict()


def test_max_swap_count():
    assert [sp.max_swap_count(t) for t in ("VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick")] == [11, 12, 15]


class Parent:
    def step(self, action):
        self._before_control_step()
        for _ in range(3):
            self._before_simulation_step()
            self._after_simulation_step()
        self.elapsed_steps += 1
        return action
    def _before_control_step(self):
        pass
    def _before_simulation_step(self):
        self.before_called = True
    def _after_simulation_step(self):
        self.after_called = True


class Env(sp.SwapCollisionMixin, Parent):
    def _swap_actors(self):
        return self.actors


def runtime_env(monkeypatch, actors=None):
    monkeypatch.setattr(bc, "object_state_from_actor", fake_read)
    env = Env()
    env.actors = actors or list(rectangle().values())
    for actor in env.actors:
        actor.pose = SimpleNamespace(q=actor.q)
    env.elapsed_steps = 11
    env.swap_pair1_idx1, env.swap_pair1_idx2 = env.actors[0], env.actors[1]
    env.swap_schedule = [(env.actors[0], env.actors[1], 10, 20)]
    env._xhard_swap_plan = {"slots": [a.p[:2].tolist() for a in env.actors], "slot_pairs": [(0, 1)]}
    env._xhard_runtime_checks = []
    env._xhard_fatal = None
    env.before_called = False
    env.after_called = False
    return env


def cache_endpoints(env):
    a, b, start, end = env.swap_schedule[0]
    env._two_lane_swaps = {(id(a), id(b), start, end): dict(ax=a.p[0], ay=a.p[1], az=a.p[2], qa=a.q.copy(),
                                                          bx=b.p[0], by=b.p[1], bz=b.p[2], qb=b.q.copy())}


def test_segment_start_binding_mismatch_records_fatal(monkeypatch):
    env = runtime_env(monkeypatch)
    env.actors[-1].p[:2] = env.actors[0].p[:2]
    env._check_segment_start(0)
    assert env._xhard_fatal["error_type"] == "SwapBindingError"
    assert env._xhard_fatal["stage"] == "segment_start"
    assert env._xhard_fatal["check"] == "slot_binding"
    assert len(env._xhard_fatal["detail"]["objects"]) == 4


def test_segment_start_rejects_third_object_crossing(monkeypatch):
    actors = [state(0, (-.02, 0)), state(1, (.02, 0)), state(2, (0, .07))]
    env = runtime_env(monkeypatch, actors)
    cache_endpoints(env)
    assert bc.check_bin_layout(actors)[1] is None
    env._check_segment_start(0)
    assert env._xhard_fatal["check"] == "sweep_actual"
    assert env._xhard_fatal["rejection"]["object_b"] == "bin_2"
    assert env._xhard_runtime_checks[-1]["endpoint_match"] is True


def test_segment_start_endpoint_evidence_and_mismatch(monkeypatch):
    env = runtime_env(monkeypatch, [state(0, (-.05, 0)), state(1, (.05, 0))])
    cache_endpoints(env)
    env._check_segment_start(0)
    assert env._xhard_fatal is None
    assert env._xhard_runtime_checks[-1]["endpoint_match"] is True
    env._two_lane_swaps[next(iter(env._two_lane_swaps))]["ax"] += .001
    env._check_segment_start(0)
    assert env._xhard_fatal["check"] == "endpoint_binding"


def test_mixin_records_fatal_without_raising(monkeypatch):
    env = runtime_env(monkeypatch)
    env.elapsed_steps = 10
    env.actors[-1].p[:2] = env.actors[0].p[:2]
    assert env.step("结果") == "结果"
    fatal = env._xhard_fatal
    assert fatal["error_type"] == "SwapBindingError"
    env._before_simulation_step()
    env._after_simulation_step()
    assert env.before_called and env.after_called
    assert env._xhard_fatal is fatal
    assert len(env._xhard_runtime_checks) == 1


@pytest.mark.parametrize("stage", ["substep_before", "substep_after"])
def test_substep_failure_never_raises(monkeypatch, stage):
    env = runtime_env(monkeypatch, [state(0, (0, 0)), state(1, (0, 0))])
    getattr(env, "_before_simulation_step" if stage == "substep_before" else "_after_simulation_step")()
    assert env._xhard_fatal["error_type"] == "SwapCollisionError"
    assert env._xhard_fatal["stage"] == stage


def test_runtime_guard_records_unexpected_check_exception(monkeypatch):
    env = runtime_env(monkeypatch)
    env.elapsed_steps = 10
    def broken(k):
        raise RuntimeError("无法读取端点")
    env._check_segment_start = broken
    assert env.step(3) == 3
    assert env._xhard_fatal["check"] == "uncertified"


def test_segment_start_uses_refreshed_schedule_and_current_step(monkeypatch):
    env = runtime_env(monkeypatch)
    env.elapsed_steps = 30
    seen = []
    def step(parent_self, action):
        parent_self.swap_schedule = [(env.actors[0], env.actors[1], 30, 40)]
        parent_self.static_flag = True
        return original_step(parent_self, action)
    original_step = Parent.step
    env.static_flag = False
    monkeypatch.setattr(Parent, "step", step)
    env._check_segment_start = lambda k: seen.append((k, env.elapsed_steps))
    env.step(1)
    assert seen == [(0, 30)]


def test_control_hook_once_before_physics_shared_boundary_and_no_state(monkeypatch):
    env = runtime_env(monkeypatch)
    env.elapsed_steps = 10
    env.swap_schedule = [(env.actors[0], env.actors[1], 10, 11),
                         (env.actors[1], env.actors[0], 11, 12)]
    events = []
    env._check_segment_start = lambda k: events.append(("start", k, env.elapsed_steps))
    env._substep_check = lambda stage: events.append((stage, env.elapsed_steps))
    monkeypatch.setattr(Parent, "_before_control_step", lambda self: events.append(("parent", self.elapsed_steps)))
    keys = set(vars(env))
    env.step(None)
    env.step(None)
    assert [r for r in events if r[0] == "start"] == [("start", 0, 10), ("start", 1, 11)]
    assert events[:3] == [("parent", 10), ("start", 0, 10), ("substep_before", 10)]
    assert events[8:11] == [("parent", 11), ("start", 1, 11), ("substep_before", 11)]
    assert set(vars(env)) - keys == set()
    assert "step" not in sp.SwapCollisionMixin.__dict__
    assert "reset" not in sp.SwapCollisionMixin.__dict__
    assert "_initialize_episode" not in sp.SwapCollisionMixin.__dict__


def test_small_quaternion_difference_rejected_and_step_evidence(monkeypatch, tmp_path):
    env = runtime_env(monkeypatch, [state(0, (-.05, 0)), state(1, (.05, 0))])
    env.elapsed_steps = 10
    cache_endpoints(env)
    env.actors[0].q[1] += 1e-12
    env.step(None)
    assert env._xhard_fatal["check"] == "endpoint_binding"
    assert env._xhard_fatal["control_step"] == 10
    assert all(r["control_step"] == 10 and r["phase"] == "before_physics" for r in env._xhard_runtime_checks)
    assert "a_q" in env._xhard_runtime_checks[-1]["endpoints"]["mismatches"]
    path = tmp_path / "tiny-q.json"
    evidence = dict(env._xhard_runtime_checks[-1], git_commit=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[3], text=True).strip())
    path.write_text(json.dumps(evidence), encoding="utf-8")
    restored = json.loads(path.read_text(encoding="utf-8"))
    assert restored["git_commit"] == evidence["git_commit"] and len(restored["git_commit"]) == 40
    endpoints = restored["endpoints"]
    assert endpoints == env._xhard_runtime_checks[-1]["endpoints"]
    assert endpoints["actual_raw_q"]["a"] != endpoints["cached_raw_q"]["a"]
    assert endpoints["delta"]["a_q"][1] != 0
    assert set(endpoints["delta"]) == {"a_p", "a_q", "b_p", "b_q"}


def test_real_check_before_integrating_pose_and_shared_cache(monkeypatch):
    env = runtime_env(monkeypatch, [state(0, (-.05, 0)), state(1, (.05, 0))])
    env.elapsed_steps = 10
    a, b = env.actors
    env.swap_schedule = [(a, b, 10, 11), (b, a, 11, 12)]
    env.swap_pair2_idx1, env.swap_pair2_idx2 = b, a
    events = []
    original_step = Parent.step
    def refresh_and_step(self, action):
        # 模拟父类先落定上一段，再捕获新段端点并应用 alpha=0。
        if self.elapsed_steps == 11:
            a.p[:2], b.p[:2] = b.p[:2].copy(), a.p[:2].copy()
            a.q[1] = b.q[1] = 0
            events.append("落定上一段")
        first, second, start, end = self.swap_schedule[self.elapsed_steps - 10]
        self._two_lane_swaps[(id(first), id(second), start, end)] = dict(
            ax=first.p[0], ay=first.p[1], az=first.p[2], qa=first.q.copy(),
            bx=second.p[0], by=second.p[1], bz=second.p[2], qb=second.q.copy())
        events.append("捕获本段")
        return original_step(self, action)
    def integrate(self):
        # 第一个物理子步修改位姿，若段起点检查后移就会逐位失败。
        a.p[2] += 1e-5
        a.q[1] += 1e-12
        events.append("物理积分")
    env._two_lane_swaps = {}
    monkeypatch.setattr(Parent, "step", refresh_and_step)
    monkeypatch.setattr(Parent, "_after_simulation_step", integrate)
    monkeypatch.setattr(env, "_substep_check", lambda stage: None)
    keys = set(vars(env))
    env.step(None)
    assert env._xhard_fatal is None
    assert env._xhard_runtime_checks[-1]["endpoint_match"] is True
    # 同一份真实检查在积分后必拒，证明它不能移到 step 返回后。
    env._check_segment_start(0)
    assert env._xhard_fatal["check"] == "endpoint_binding"
    env._xhard_fatal = None
    env._xhard_runtime_checks = env._xhard_runtime_checks[:2]
    env.step(None)
    assert env._xhard_fatal is None
    sweeps = [r for r in env._xhard_runtime_checks if r["kind"] == "swap_sweep"]
    assert [(r["sweep_index"], r["control_step"]) for r in sweeps] == [(0, 10), (1, 11)]
    assert all(r["endpoint_match"] and r["phase"] == "before_physics" for r in sweeps)
    assert events[:2] == ["捕获本段", "物理积分"]
    assert events[4:6] == ["落定上一段", "捕获本段"]
    assert set(vars(env)) == keys


def test_outside_window_does_not_read_geometry(monkeypatch):
    env = runtime_env(monkeypatch)
    env.elapsed_steps = 1
    env._states = lambda: pytest.fail("交换窗外不应读取几何")
    env._before_simulation_step()
    env._after_simulation_step()
    assert env._xhard_runtime_checks == []


def test_repick_placeholder_does_not_enter_window(monkeypatch):
    env = runtime_env(monkeypatch)
    env.static_flag = False
    env.elapsed_steps = 400
    env.swap_schedule = [(env.actors[0], env.actors[1], 400, 450)]
    env._states = lambda: pytest.fail("演示结束前不应读取交换几何")
    env._before_simulation_step()
    assert env._swap_segment_index_at(400) is None
    assert env._xhard_runtime_checks == []


@pytest.mark.parametrize("method", ["step", "_before_control_step", "_before_simulation_step", "_after_simulation_step"])
def test_parent_exception_is_not_swallowed(monkeypatch, method):
    env = runtime_env(monkeypatch)
    def broken(*args):
        raise ValueError("父类自身错误")
    env.elapsed_steps = 1
    monkeypatch.setattr(Parent, method, broken)
    with pytest.raises(ValueError, match="父类自身错误"):
        env.step(1)
    assert env._xhard_fatal is None


# ── 方案 X′：段起点期望四元数重放父类 float32 归一化 ─────────────────────────────
class PoseActor:
    """只提供父类 swap_flat_two_lane 用到的 pose 读取与 set_pose，记录真实写入。"""

    def __init__(self, name, p, q, shapes):
        self.name, self.shapes = name, shapes
        self.p = np.asarray(p, dtype=np.float32)
        self.q = np.asarray(q, dtype=np.float32)
        self.written = []

    @property
    def pose(self):
        return SimpleNamespace(p=self.p.copy(), q=self.q.copy())

    def set_pose(self, pose):
        self.written.append(np.asarray(pose.q, np.float32))
        self.p = np.asarray(pose.p, dtype=np.float32)
        self.q = np.asarray(pose.q, dtype=np.float32)


# 非平凡偏航四元数，float32 范数恰为 1；[1,0,0,0] 加一个刻度在 float64 正规化后会被抹平，区分不出。
QA_UNIT = np.array([0.989905059337616, 0.0, 0.0, 0.14173220098018646], dtype=np.float32)
QB_YAW = np.array([np.cos(0.3), 0, 0, np.sin(0.3)], dtype=np.float32)


def parent_q_cases():
    """范数恰为 1、首分量多一个 float32 刻度、少一个刻度三组缓存 qa。"""
    assert np.linalg.norm(QA_UNIT) == np.float32(1)
    up = QA_UNIT.copy()
    up[0] = np.nextafter(up[0], np.float32(2))
    down = QA_UNIT.copy()
    down[0] = np.nextafter(down[0], np.float32(0))
    return {"unit": QA_UNIT.copy(), "up": up, "down": down}


def run_parent_start(qa, qb, env=None):
    """在 cur_step == start_step < end_step 下调用真实父类函数一次。"""
    from robomme.robomme_env.utils.statechange import swap_flat_two_lane
    shapes = bc.cube_shape_specs(0.005)
    a = PoseActor("bin_0", [-.05, 0, .005], qa, shapes)
    b = PoseActor("bin_1", [.05, 0, .005], qb, shapes)
    env = env if env is not None else SimpleNamespace()
    swap_flat_two_lane(env, a, b, start_step=10, end_step=20, cur_step=10)
    return env, a, b


@pytest.mark.parametrize("case", ["unit", "up", "down"])
def test_parent_start_q_matches_real_parent_write(case):
    qa = parent_q_cases()[case]
    env, a, b = run_parent_start(qa, QB_YAW)
    cache = env._two_lane_swaps[(id(a), id(b), 10, 20)]
    assert cache["qa"].dtype == np.float32
    assert len(a.written) == len(b.written) == 1
    assert np.array_equal(sp.parent_start_q(cache["qa"], cache["qb"]), a.written[0])
    assert np.array_equal(sp.parent_start_q(cache["qb"], cache["qa"]), b.written[0])
    assert sp.parent_start_q(cache["qa"], cache["qb"]).dtype == np.float32


def test_parent_start_q_distinguishes_one_ulp_from_cache():
    qa = parent_q_cases()["up"]
    env, a, b = run_parent_start(qa, QB_YAW)
    cache = env._two_lane_swaps[(id(a), id(b), 10, 20)]
    assert not np.array_equal(sp.parent_start_q(cache["qa"], cache["qb"]), cache["qa"])
    # 判据 float64 正规化后，旧期望（缓存原值）同样与真实写入不同，即方案 X 的误报来源。
    assert not np.array_equal(bc.ObjectState("a", [0, 0, 0], cache["qa"], ()).q,
                              bc.ObjectState("a", [0, 0, 0], a.written[0], ()).q)


def parent_runtime_env(monkeypatch):
    """端到端：父类在 env 上真实捕获缓存并写入段起点，再交给 mixin 比较。"""
    env = runtime_env(monkeypatch, [state(0, (-.05, 0)), state(1, (.05, 0))])
    env.elapsed_steps = 10
    _, a, b = run_parent_start(parent_q_cases()["up"], QB_YAW, env)
    env.actors = [a, b]
    env.swap_pair1_idx1, env.swap_pair1_idx2 = a, b
    env.swap_schedule = [(a, b, 10, 20)]
    return env, a, b


def test_endpoint_evidence_accepts_parent_replay(monkeypatch):
    env, a, b = parent_runtime_env(monkeypatch)
    actual = [bc.object_state_from_actor(x, f"bin_{i}") for i, x in enumerate((a, b))]
    match, evidence = env._endpoint_evidence(0, *actual)
    assert match is True and evidence["mismatches"] == []
    assert evidence["expected_start_raw_q"]["a"] == a.written[0].tolist()
    assert evidence["expected_start_raw_q"]["b"] == b.written[0].tolist()
    assert evidence["cached_raw_q"]["a"] != evidence["expected_start_raw_q"]["a"]
    assert {"actual", "cached", "mismatches", "delta", "actual_raw_q", "cached_raw_q",
            "phase", "expected_start_raw_q"} <= set(evidence)
    env._check_segment_start(0)
    assert env._xhard_fatal is None
    assert env._xhard_runtime_checks[-1]["endpoint_match"] is True


@pytest.mark.parametrize("kind", ["position", "extra_ulp"])
def test_endpoint_evidence_rejects_real_difference_after_replay(monkeypatch, kind):
    env, a, b = parent_runtime_env(monkeypatch)
    if kind == "position":
        a.p = a.p.astype(np.float64)
        a.p[2] += 1e-6
        key = "a_p"
    else:
        # 归一化解释不了的额外一个 float32 刻度。
        a.q = a.q.copy()
        a.q[3] = np.nextafter(a.q[3], np.float32(1))
        key = "a_q"
    actual = [bc.object_state_from_actor(x, f"bin_{i}") for i, x in enumerate((a, b))]
    match, evidence = env._endpoint_evidence(0, *actual)
    assert match is False and evidence["mismatches"] == [key]
    env._check_segment_start(0)
    assert env._xhard_fatal["check"] == "endpoint_binding"


def test_parent_start_q_verdict_line(capsys):
    """三组锁定用例汇总成判定行。"""
    passed = 0
    for qa in parent_q_cases().values():
        env, a, b = run_parent_start(qa, QB_YAW)
        cache = env._two_lane_swaps[(id(a), id(b), 10, 20)]
        passed += int(np.array_equal(sp.parent_start_q(cache["qa"], cache["qb"]), a.written[0]) and
                      np.array_equal(sp.parent_start_q(cache["qb"], cache["qa"]), b.written[0]))
    assert passed == 3
    with capsys.disabled():
        print(f"\nXHARD_PARENT_START_Q=PASS cases={passed}")


def test_slot_binding_tie_and_planned_slot_closer(monkeypatch):
    env = runtime_env(monkeypatch, [state(0, (-.1, 0)), state(1, (.1, 0))])
    env.actors[0].p[:2] = (0, 0)
    assert env._slot_binding_evidence(0)[0]
    env.actors[0].p[0] = -.001
    assert env._slot_binding_evidence(0)[0]
    env.actors[0].p[0] = .001
    assert not env._slot_binding_evidence(0)[0]
    env._check_segment_start(0)
    assert env._xhard_fatal["check"] == "slot_binding"


class FakePose:
    def __init__(self, p, q=(1, 0, 0, 0)):
        self.p, self.q = np.asarray(p), np.asarray(q)
    def __mul__(self, other):
        return FakePose(self.p + bc.quat_to_matrix(self.q) @ other.p,
                        bc.matrix_to_quat(bc.quat_to_matrix(self.q) @ bc.quat_to_matrix(other.q)))


def button_fixture(qpos=0.):
    box = type("PhysxCollisionShapeBox", (), {})()
    box.half_size, box.local_pose = np.array([.0375, .0375, .0075]), FakePose([0, 0, 0])
    cap = type("PhysxCollisionShapeCylinder", (), {})()
    cap.radius, cap.half_length = .0225, .009
    cap.local_pose = FakePose([0, 0, .009], bc.euler_xyz_to_quat([0, -np.pi/2, 0]))
    def link(name, shape, p):
        component = SimpleNamespace(entity=SimpleNamespace(pose=FakePose(p)), get_collision_shapes=lambda: [shape])
        return SimpleNamespace(get_name=lambda: name, _objs=[component])
    links = [link("button_base", box, [0, 0, .0075]), link("button_cap", cap, [0, 0, .015+qpos])]
    return SimpleNamespace(get_links=lambda: links, get_qpos=lambda: np.array([qpos]))


def test_button_envelope_covers_unpressed_cap_while_pressed():
    before = sp.button_envelope_state(button_fixture(), "button")
    after = sp.button_envelope_state(button_fixture(-.01), "button")
    assert np.allclose(before.p, after.p)
    assert np.allclose(before.shapes[0].half, after.shapes[0].half)
    assert np.allclose(before.p+before.shapes[0].half, [.0375, .0375, .033])
    assert np.allclose(before.p-before.shapes[0].half, [-.0375, -.0375, 0])


def test_button_geometry_fail_loud():
    button = button_fixture()
    button.get_links()[1]._objs[0].get_collision_shapes()[0].radius = .1
    with pytest.raises(SceneGenerationError, match="水平投影"):
        sp.button_envelope_state(button, "button")


def test_bystander_conversion_shared_by_planning_and_runtime(monkeypatch):
    monkeypatch.setattr(bc, "object_state_from_actor", fake_read)
    button, actor = button_fixture(), state(9, (2, 2))
    direct = sp.bystander_states_of([button, actor])
    env = runtime_env(monkeypatch)
    env._bystander_actors = lambda: [button, actor]
    runtime = env._states()[2]
    assert all(np.array_equal(a.p, b.p) for a, b in zip(direct, runtime))
    assert len(direct[0].shapes) == 1 and direct[1].shapes == actor.shapes


def test_button_bystander_removes_crossing_edge():
    states = [state(0, (-.1, 0)), state(1, (.1, 0))]
    # 双弯道中段正好经过 y=±.07 的按钮，初态不接触。
    blocker = state(9, (0, .07))
    assert sp.slot_graph(states, [])[0][0][1]
    assert not sp.slot_graph(states, [blocker])[0][0][1]

