"""交换规划、初始化几何证明与不抛异常的运行期复核。"""

from dataclasses import dataclass, asdict

import numpy as np
import torch

from .collision import SwapCollisionError, SceneGenerationError
from .collision import bin_collision as bc

SWAP_PLAN_SEED_OFFSET = 0x53574150


@dataclass
class SwapPlan:
    """序号按对象生成顺序，段号在运行证据中从零开始。"""

    pairs: list
    usage: list[int]
    initial_gap: float
    initiator_usage: list[int]
    partner_usage: list[int]

    def as_dict(self):
        return asdict(self)


def select_initiator(usage, excluded, generator):
    """先避开上一对，再在总参与次数最少者间独立随机抽样。"""
    pool = [i for i in range(len(usage)) if i not in excluded] or list(range(len(usage)))
    least = min(usage[i] for i in pool)
    candidates = [i for i in pool if usage[i] == least]
    return candidates[int(torch.randint(len(candidates), (1,), generator=generator).item())]


def plan_swaps(states, bystanders, swap_times, generator):
    """逐段证明后才交换名义位姿；调用方的状态与随机流不被修改。"""
    if len(states) < 2:
        raise SceneGenerationError("交换规划至少需要两个对象")
    if list(states) != list(range(len(states))):
        raise ValueError("交换对象序号必须按生成顺序连续排列")
    cur = dict(states)
    initial_gap, rejection = bc.check_bin_layout(list(cur.values()) + list(bystanders), stage="initial")
    if rejection is not None:
        raise SwapCollisionError(rejection, "initial")
    usage = [0] * len(cur)
    initiated = [0] * len(cur)
    partnered = [0] * len(cur)
    excluded = set()
    pairs = []
    for k in range(swap_times):
        a = select_initiator(usage, excluded, generator)
        b, table = bc.nearest_partner_index(cur[a].p, [(i, s.p) for i, s in cur.items() if i != a])
        if b < 0:
            raise SceneGenerationError("无法找到有限距离的交换搭档")
        others = [s for i, s in cur.items() if i not in (a, b)] + list(bystanders)
        gap, rejection = bc.check_swap_sweep(cur[a], cur[b], others, sweep_index=k)
        if rejection is not None:
            raise SwapCollisionError(rejection, "sweep")
        pairs.append((a, b, dict(table)[b], gap))
        usage[a] += 1
        usage[b] += 1
        initiated[a] += 1
        partnered[b] += 1
        old_a, old_b = cur[a], cur[b]
        # 收尾接手对方的横向位置与朝向，各对象保留自身高度与碰撞形状。
        cur[a] = bc.ObjectState(old_a.name, np.r_[old_b.p[:2], old_a.p[2]], old_b.q.copy(), old_a.shapes)
        cur[b] = bc.ObjectState(old_b.name, np.r_[old_a.p[:2], old_b.p[2]], old_a.q.copy(), old_b.shapes)
        excluded = {a, b}
    return SwapPlan(pairs, usage, initial_gap, initiated, partnered)


def certify_swap_plan(env, actors, bystanders, name_prefix):
    """在父类建场完成后证明并预写全部配对，独立流不掺入档位。"""
    if len(actors) < 2:
        raise SceneGenerationError("交换规划至少需要两个对象")
    try:
        states = {i: bc.object_state_from_actor(a, f"{name_prefix}{i}") for i, a in enumerate(actors)}
        others = [bc.object_state_from_actor(a, f"bystander_{i}") for i, a in enumerate(bystanders)]
    except bc.BinCollisionError as exc:
        raise SwapCollisionError(exc.rejection, "initial") from exc
    generator = torch.Generator().manual_seed(int(env.seed) + SWAP_PLAN_SEED_OFFSET)
    plan = plan_swaps(states, others, int(env.swap_times), generator)
    for k, (a, b, _, _) in enumerate(plan.pairs, 1):
        setattr(env, f"swap_pair{k}_idx1", actors[a])
        setattr(env, f"swap_pair{k}_idx2", actors[b])
    env._refresh_swap_schedule()
    env._xhard_swap_plan = plan.as_dict()
    env._xhard_runtime_checks = []
    env._xhard_fatal = None
    return plan


class SwapCollisionMixin:
    """只覆盖获准的检查点；父类自身异常仍按原路径传播。"""

    swap_name_prefix = "bin_"

    def _swap_actors(self):
        raise NotImplementedError

    def _bystander_actors(self):
        return []

    def _swap_segment_index_at(self, step):
        if hasattr(self, "static_flag") and not self.static_flag:
            return None
        return next((k for k, row in enumerate(self.swap_schedule) if step == row[2]), None)

    def _in_swap_window(self):
        # VideoRepick 演示尚未结束时，400 只是父类占位起点。
        if hasattr(self, "static_flag") and not self.static_flag:
            return False
        return any(row[2] <= int(self.elapsed_steps) <= row[3] for row in self.swap_schedule)

    def _record_fatal(self, error_type, stage, k, rejection=None, detail=None, check=None):
        if getattr(self, "_xhard_fatal", None) is None:
            self._xhard_fatal = dict(error_type=error_type, stage=stage, check=check, k=k,
                                    rejection=None if rejection is None else rejection.as_dict(),
                                    detail=detail, control_step=int(self.elapsed_steps))

    def _runtime_guard(self, stage, function, *args):
        """形状读取或证据检查的异常也拒绝样本，不能截断仿真进度。"""
        if not hasattr(self, "_xhard_swap_plan") or getattr(self, "_xhard_fatal", None) is not None:
            return
        try:
            function(*args)
        except Exception as exc:
            rejection = getattr(exc, "rejection", None)
            self._record_fatal("SwapCollisionError", stage, args[0] if stage == "segment_start" else None,
                               rejection=rejection, detail={"exception_type": type(exc).__name__, "message": str(exc)},
                               check="uncertified")

    def step(self, action):
        out = super().step(action)
        if hasattr(self, "_xhard_swap_plan") and getattr(self, "_xhard_fatal", None) is None:
            # 父类已落定上一段并缓存本段端点；控制步计数此时已加一。
            k = self._swap_segment_index_at(int(self.elapsed_steps) - 1)
            if k is not None:
                self._runtime_guard("segment_start", self._check_segment_start, k)
        return out

    def _before_simulation_step(self):
        super()._before_simulation_step()
        self._runtime_guard("substep_before", self._substep_check, "substep_before")

    def _after_simulation_step(self):
        super()._after_simulation_step()
        self._runtime_guard("substep_after", self._substep_check, "substep_after")

    def _states(self):
        actors = self._swap_actors()
        states = [bc.object_state_from_actor(a, f"{self.swap_name_prefix}{i}") for i, a in enumerate(actors)]
        others = [bc.object_state_from_actor(a, f"bystander_{i}") for i, a in enumerate(self._bystander_actors())]
        return actors, states, others

    def _endpoint_evidence(self, k, a, b):
        row = self.swap_schedule[k]
        cache = getattr(self, "_two_lane_swaps", {}).get((id(row[0]), id(row[1]), int(row[2]), int(row[3])))
        actual = {"a_p": a.p.tolist(), "a_q": a.q.tolist(), "b_p": b.p.tolist(), "b_q": b.q.tolist()}
        if cache is None:
            return False, {"actual": actual, "cached": None}
        ca = bc.ObjectState(a.name, [cache["ax"], cache["ay"], cache["az"]], cache["qa"], a.shapes)
        cb = bc.ObjectState(b.name, [cache["bx"], cache["by"], cache["bz"]], cache["qb"], b.shapes)
        cached = {"a_p": ca.p.tolist(), "a_q": ca.q.tolist(), "b_p": cb.p.tolist(), "b_q": cb.q.tolist()}
        # 原始四元数均按判据的归一化语义转换后比较，不改变几何容差。
        mismatches = [key for key in actual if not np.array_equal(actual[key], cached[key])]
        return not mismatches, {"actual": actual, "cached": cached, "mismatches": mismatches,
                                "cached_raw_q": {"a": bc._to_numpy(cache["qa"]).tolist(),
                                                 "b": bc._to_numpy(cache["qb"]).tolist()}}

    def _check_segment_start(self, k):
        if getattr(self, "_xhard_fatal", None) is not None:
            return
        actors, states, others = self._states()
        initiator = getattr(self, f"swap_pair{k+1}_idx1")
        expected = getattr(self, f"swap_pair{k+1}_idx2")
        a = next(i for i, actor in enumerate(actors) if actor is initiator)
        b = next(i for i, actor in enumerate(actors) if actor is expected)
        recomputed, table = bc.nearest_partner_index(states[a].p, [(i, s.p) for i, s in enumerate(states) if i != a])
        detail = dict(initiator=a, expected=b, recomputed=recomputed, distances=table)
        self._xhard_runtime_checks.append(dict(kind="swap_binding", control_step=int(self.elapsed_steps)-1,
                                                sweep_index=k, **detail))
        if recomputed != b:
            self._record_fatal("SwapBindingError", "segment_start", k, detail=detail, check="binding")
            return
        match, endpoints = self._endpoint_evidence(k, states[a], states[b])
        if not match:
            self._xhard_runtime_checks.append(dict(kind="swap_sweep", control_step=int(self.elapsed_steps)-1,
                                                    sweep_index=k, endpoint_match=False, endpoints=endpoints))
            self._record_fatal("SwapBindingError", "segment_start", k, detail=endpoints, check="endpoint_binding")
            return
        gap, rejection = bc.check_swap_sweep(states[a], states[b],
                                             [s for i, s in enumerate(states) if i not in (a, b)] + others,
                                             sweep_index=k, stage="segment_start")
        self._xhard_runtime_checks.append(dict(kind="swap_sweep", control_step=int(self.elapsed_steps)-1,
                                                sweep_index=k, gap_lower_bound=gap, endpoint_match=match,
                                                endpoints=endpoints, rejection=None if rejection is None else rejection.as_dict()))
        if rejection is not None:
            self._record_fatal("SwapCollisionError", "segment_start", k, rejection=rejection, check="sweep_actual")

    def _substep_check(self, stage):
        if getattr(self, "_xhard_fatal", None) is not None or not self._in_swap_window():
            return
        _, states, others = self._states()
        gap, rejection = bc.check_bin_layout(states + others, stage=stage)
        k = next(k for k, row in enumerate(self.swap_schedule) if row[2] <= int(self.elapsed_steps) <= row[3])
        self._xhard_runtime_checks.append(dict(kind=stage, control_step=int(self.elapsed_steps), sweep_index=k,
                                                gap_lower_bound=gap, rejection=None if rejection is None else rejection.as_dict()))
        if rejection is not None:
            self._record_fatal("SwapCollisionError", stage, k, rejection=rejection, check="layout")
