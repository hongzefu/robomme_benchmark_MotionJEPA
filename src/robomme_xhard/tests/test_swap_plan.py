"""纯 CPU 的规划、端点绑定与运行失败留证测试，不创建仿真环境。"""

from types import SimpleNamespace
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


def test_select_initiator_excludes_last_pair():
    assert sp.select_initiator([0, 0, 5, 7], {0, 1}, generator()) == 2


def test_select_initiator_fallback_when_pool_empty():
    assert sp.select_initiator([4, 1], {0, 1}, generator()) == 1


def test_select_initiator_tie_random_reproducible():
    def draws(seed):
        g = generator(seed)
        return [sp.select_initiator([0]*4, set(), g) for _ in range(20)]
    assert draws(4) == draws(4)
    assert draws(4) != draws(5)


def test_plan_usage_uniform_s11_n4():
    plan = sp.plan_swaps(rectangle(), [], 11, generator())
    assert max(plan.usage) - min(plan.usage) <= 1
    assert all(set(a[:2]).isdisjoint(b[:2]) for a, b in zip(plan.pairs, plan.pairs[1:]))


def test_plan_rectangle_pairs_short_edge():
    assert all(set(p[:2]) in ({0, 3}, {1, 2}) for p in sp.plan_swaps(rectangle(), [], 11, generator()).pairs)


def test_plan_prefix_across_tiers():
    plans = [sp.plan_swaps(rectangle(), [], s, generator()) for s in (4, 5, 7, 9, 11)]
    assert all(p.pairs == plans[-1].pairs[:len(p.pairs)] for p in plans)


def test_usage_counts_split():
    plan = sp.plan_swaps(rectangle(), [], 11, generator())
    assert sum(plan.initiator_usage) == sum(plan.partner_usage) == 11
    assert plan.usage == [a+b for a, b in zip(plan.initiator_usage, plan.partner_usage)]


def test_plan_n3_rotation():
    states = {0: state(0, (-.2, 0)), 1: state(1, (0, 0)), 2: state(2, (.2, 0))}
    plan = sp.plan_swaps(states, [], 9, generator())
    assert all(set(a[:2]) != set(b[:2]) for a, b in zip(plan.pairs, plan.pairs[1:]))


def test_plan_rejects_sweep_collision_raises_scene_error(monkeypatch):
    # 发起者选左端，另一交换对象在左弯道顶点，最近邻仍是右端。
    states = {0: state(0, (-.02, 0)), 1: state(1, (.02, 0)), 2: state(2, (0, .07))}
    monkeypatch.setattr(sp, "select_initiator", lambda *args: 0)
    with pytest.raises(SwapCollisionError) as exc:
        sp.plan_swaps(states, [], 1, generator())
    assert isinstance(exc.value, SceneGenerationError)
    assert exc.value.stage == "sweep"
    assert exc.value.rejection.object_b == "2"


def fake_read(actor, name=None):
    return bc.ObjectState(name or actor.name, actor.p.copy(), actor.q.copy(), actor.shapes)


def test_certify_prefills_all_pairs_and_schedule(monkeypatch):
    actors = list(rectangle().values())
    env = SimpleNamespace(seed=9, swap_times=11, refreshes=0)
    def refresh():
        env.refreshes += 1
    env._refresh_swap_schedule = refresh
    monkeypatch.setattr(bc, "object_state_from_actor", fake_read)
    before = torch.get_rng_state().clone()
    plan = sp.certify_swap_plan(env, actors, [], "bin_")
    assert torch.equal(before, torch.get_rng_state())
    for k, (a, b, _, _) in enumerate(plan.pairs, 1):
        assert getattr(env, f"swap_pair{k}_idx1") is actors[a]
        assert getattr(env, f"swap_pair{k}_idx2") is actors[b]
    assert env.refreshes == 1
    assert env._xhard_runtime_checks == [] and env._xhard_fatal is None
    assert len(env._xhard_swap_plan["pairs"]) == 11
    sp.certify_swap_plan(env, actors, [], "bin_")
    assert env._xhard_swap_plan == plan.as_dict()


def test_certify_rejects_initial_and_too_few(monkeypatch):
    monkeypatch.setattr(bc, "object_state_from_actor", fake_read)
    env = SimpleNamespace(seed=0, swap_times=1)
    with pytest.raises(SceneGenerationError):
        sp.certify_swap_plan(env, [], [], "bin_")
    with pytest.raises(SwapCollisionError) as exc:
        sp.certify_swap_plan(env, [state(0, (0, 0)), state(1, (0, 0))], [], "bin_")
    assert exc.value.stage == "initial"


class Parent:
    def step(self, action):
        self.elapsed_steps += 1
        return action
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
    env.elapsed_steps = 11
    env.swap_pair1_idx1, env.swap_pair1_idx2 = env.actors[0], env.actors[1]
    env.swap_schedule = [(env.actors[0], env.actors[1], 10, 20)]
    env._xhard_swap_plan = {}
    env._xhard_runtime_checks = []
    env._xhard_fatal = None
    return env


def cache_endpoints(env):
    a, b, start, end = env.swap_schedule[0]
    env._two_lane_swaps = {(id(a), id(b), start, end): dict(ax=a.p[0], ay=a.p[1], az=a.p[2], qa=a.q.copy(),
                                                          bx=b.p[0], by=b.p[1], bz=b.p[2], qb=b.q.copy())}


def test_segment_start_binding_mismatch_records_fatal(monkeypatch):
    env = runtime_env(monkeypatch)
    env._check_segment_start(0)
    assert env._xhard_fatal["error_type"] == "SwapBindingError"
    assert env._xhard_fatal["stage"] == "segment_start"
    assert len(env._xhard_fatal["detail"]["distances"]) == 3


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


def test_segment_start_uses_refreshed_schedule_and_completed_step(monkeypatch):
    env = runtime_env(monkeypatch)
    env.elapsed_steps = 30
    seen = []
    def step(parent_self, action):
        parent_self.swap_schedule = [(env.actors[0], env.actors[1], 30, 40)]
        parent_self.elapsed_steps += 1
        return action
    monkeypatch.setattr(Parent, "step", step)
    env._check_segment_start = lambda k: seen.append((k, env.elapsed_steps-1))
    env.step(1)
    assert seen == [(0, 30)]


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


def test_parent_exception_is_not_swallowed(monkeypatch):
    env = runtime_env(monkeypatch)
    def broken(*args):
        raise ValueError("父类自身错误")
    monkeypatch.setattr(Parent, "step", broken)
    with pytest.raises(ValueError, match="父类自身错误"):
        env.step(1)
    assert env._xhard_fatal is None
