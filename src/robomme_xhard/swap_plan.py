"""可行槽对图、独立均衡规划与保持父类时序的运行期证明。"""

from dataclasses import dataclass, asdict, replace
import numpy as np
import torch

from .collision import SwapCollisionError, SceneGenerationError
from .collision import bin_collision as bc
from .collision import swap_uniform as su
from .configs import TIER_CONFIGS

SWAP_PLAN_SEED_OFFSET = 0x53574150
PLAN_SCORE = "max_sum"
PLAN_BUDGET = 20
PLAN_ACCEPT_RANGE = 1


@dataclass
class SwapPlan:
    """旧字段保持同形，槽中心与槽对用于独立运行绑定。"""

    pairs: list
    usage: list[int]
    initial_gap: float
    initiator_usage: list[int]
    partner_usage: list[int]
    slot_pairs: list
    graph: dict
    s_max: int
    spread_full: int
    spread_prefix: int
    tries: int
    slots: list

    def as_dict(self):
        return asdict(self)


def max_swap_count(task):
    """读取唯一配置表，不把当前档的段数误当整条规划长度。"""
    return max(int(cfg["knobs"]["swap_count"]) for cfg in TIER_CONFIGS[task].values())


def require_static_slots(states):
    """逐盒逐位检查同形及等高；任何差异立即拒绝。"""
    states = list(states.values()) if isinstance(states, dict) else list(states)
    if len(states) < 2:
        raise SceneGenerationError("交换规划至少需要两个对象")
    first = states[0]
    for i, state in enumerate(states[1:], 1):
        if not np.array_equal(state.p[2], first.p[2]):
            raise SceneGenerationError(f"对象 {i} 初始 z 不同")
        if len(state.shapes) != len(first.shapes):
            raise SceneGenerationError(f"对象 {i} 盒体数量不同")
        for j, (left, right) in enumerate(zip(first.shapes, state.shapes)):
            for key in ("half", "local_p", "local_q"):
                if not np.array_equal(getattr(left, key), getattr(right, key)):
                    raise SceneGenerationError(f"对象 {i} 盒体 {j} 的 {key} 不同")


def button_envelope_state(articulation, name):
    """真实底座与圆柱的世界包络，恢复未按下顶面而不写死尺寸。"""
    try:
        links = {link.get_name(): link for link in articulation.get_links()}
        if set(links) != {"button_base", "button_cap"}:
            raise ValueError("按钮连杆集合不符")
        components = [links[key]._objs for key in ("button_base", "button_cap")]
        if any(len(items) != 1 for items in components):
            raise ValueError("按钮必须是单场景关节体")
        base_component, cap_component = (items[0] for items in components)
        bases, caps = base_component.get_collision_shapes(), cap_component.get_collision_shapes()
        if len(bases) != 1 or len(caps) != 1:
            raise ValueError("按钮必须各有一个底座盒体和按帽圆柱")
        base, cap = bases[0], caps[0]
        if type(base).__name__ != "PhysxCollisionShapeBox" or type(cap).__name__ != "PhysxCollisionShapeCylinder":
            raise ValueError("按钮碰撞形状类型不符")
        base_pose = base_component.entity.pose * base.local_pose
        cap_pose = cap_component.entity.pose * cap.local_pose
        bp, cp = bc._to_numpy(base_pose.p), bc._to_numpy(cap_pose.p)
        br, cr = bc.quat_to_matrix(base_pose.q), bc.quat_to_matrix(cap_pose.q)
        half = bc._to_numpy(base.half_size)
        axis = cr[:, 0]
        if not np.allclose(np.abs(axis), [0, 0, 1], atol=1e-6):
            raise ValueError("按帽圆柱轴不是竖直方向")
        radius, length = float(cap.radius), float(cap.half_length)
        qpos = bc._to_numpy(articulation.get_qpos())
        if qpos.size != 1 or not np.all(np.isfinite(qpos)) or qpos[0] > 1e-7:
            raise ValueError("按钮关节必须只有非正的竖直按压位移")
        # 官方按钮棱柱关节的正向为世界 +z，运行期 qpos 为负；补回按压位移。
        cp = cp.copy()
        cp[2] -= float(qpos[0])
        be = np.abs(br) @ half
        ce = np.abs(axis) * length + radius * np.sqrt(np.maximum(0, 1 - axis * axis))
        blo, bhi, clo, chi = bp - be, bp + be, cp - ce, cp + ce
        if (not np.all(np.isfinite(np.r_[blo, bhi, clo, chi])) or
                np.any(half <= 0) or radius <= 0 or length <= 0):
            raise ValueError("按钮几何不是有限正尺寸")
        if not (np.all(clo[:2] >= blo[:2] - 1e-8) and np.all(chi[:2] <= bhi[:2] + 1e-8)):
            raise ValueError("按帽水平投影超出底座")
        if abs(float(blo[2])) > 1e-7:
            raise ValueError("按钮底面没有位于桌面")
        low, high = np.minimum(blo, clo), np.maximum(bhi, chi)
        low[2] = blo[2]
        identity = np.array([1., 0, 0, 0])
        return bc.ObjectState(name, (low + high) / 2, identity,
                              (bc.ShapeSpec(np.zeros(3), identity, (high - low) / 2),))
    except Exception as exc:
        raise SceneGenerationError(f"按钮包络读取失败 {name}：{type(exc).__name__}: {exc}") from exc


def bystander_states_of(bystanders):
    """规划和运行期唯一旁观物转换入口。"""
    return [button_envelope_state(actor, f"bystander_{i}") if hasattr(actor, "get_links")
            else bc.object_state_from_actor(actor, f"bystander_{i}")
            for i, actor in enumerate(bystanders)]


def slot_graph(states, bystander_states):
    """每个无序槽对只证一次，始终带上其余槽与全部旁观物。"""
    states = list(states.values()) if isinstance(states, dict) else list(states)
    gaps = {}
    def feasible(a, b):
        others = [s for i, s in enumerate(states) if i not in (a, b)] + list(bystander_states)
        gap, rejection = bc.check_swap_sweep(states[a], states[b], others,
                                              sweep_index=-1, stage="graph")
        gaps[f"{a}-{b}"] = float(gap) if rejection is None else rejection.gap_m
        return rejection is None
    return su.slot_pair_graph(len(states), feasible), gaps


def require_every_slot_covered(adj, gaps):
    """口径 B 允许不连通，但不允许任何孤立槽。"""
    isolated = su.isolated_slots(adj)
    if isolated:
        rejection = bc.CollisionRejection(
            reason="contact", stage="graph", object_a="slots", object_b="slots",
            shape_a=-1, shape_b=-1, detail=f"孤立槽={isolated}; 各槽对 gap={gaps}")
        raise SwapCollisionError(rejection, "graph")


def plan_swaps(states, bystanders, swap_times, generator, s_max=None):
    """最长档只规划一次，取当前前缀后逐段按真实占用者再证。"""
    states = list(states.values()) if isinstance(states, dict) else list(states)
    require_static_slots(states)
    initial_gap, rejection = bc.check_bin_layout(states + list(bystanders), stage="initial")
    if rejection is not None:
        raise SwapCollisionError(rejection, "initial")
    adj, gaps = slot_graph(states, bystanders)
    require_every_slot_covered(adj, gaps)
    s_max = int(swap_times if s_max is None else s_max)
    if not 0 <= int(swap_times) <= s_max:
        raise SceneGenerationError("当前交换段数超出最长档")
    full = su.plan_balanced_swaps(adj, s_max, generator, score=PLAN_SCORE,
                                  budget=PLAN_BUDGET, accept_range=PLAN_ACCEPT_RANGE, forbid_undo=True)
    if full is None:
        raise SceneGenerationError("口径 B 通过但均衡规划无解")
    cur = list(states)
    pairs, usage, initiated, partnered = [], [0]*len(cur), [0]*len(cur), [0]*len(cur)
    for k, (a, b) in enumerate(full.pairs[:int(swap_times)]):
        gap, rejection = bc.check_swap_sweep(cur[a], cur[b],
            [s for i, s in enumerate(cur) if i not in (a, b)] + list(bystanders), sweep_index=k)
        if rejection is not None:
            rejection = replace(rejection, detail="G 与逐段不符；" + rejection.detail)
            raise SwapCollisionError(rejection, "sweep")
        pairs.append((a, b, float(np.linalg.norm(cur[a].p[:2] - cur[b].p[:2])), float(gap)))
        usage[a] += 1
        usage[b] += 1
        initiated[a] += 1
        partnered[b] += 1
        old_a, old_b = cur[a], cur[b]
        cur[a] = bc.ObjectState(old_a.name, np.r_[old_b.p[:2], old_a.p[2]], old_b.q.copy(), old_a.shapes)
        cur[b] = bc.ObjectState(old_b.name, np.r_[old_a.p[:2], old_b.p[2]], old_a.q.copy(), old_b.shapes)
    return SwapPlan(pairs, usage, initial_gap, initiated, partnered,
                    full.slot_pairs[:int(swap_times)], {"adj": adj, "gaps": gaps},
                    s_max, full.spread, max(usage)-min(usage), full.tries,
                    [s.p[:2].tolist() for s in states])


def parent_start_q(q_self, q_other):
    """重放父类在交换段起点真实写入的四元数，作为端点比较的期望值。

    锚点 ``src/robomme/robomme_env/utils/statechange.py::swap_flat_two_lane``：父类在
    ``cur_step == start_step`` 时先把当前 q 以 ``np.asarray(..., dtype=np.float32).flatten()``
    存进 ``_two_lane_swaps[key]["qa"/"qb"]``，随后同一调用按 ``alpha = 0.0`` 走插值分支
    ``q_self * (1 - alpha) + q_other * alpha``，范数大于 ``1e-6`` 时再除以范数，最后
    ``set_pose``；SAPIEN 不再二次归一化。缓存 q 的 float32 范数不恰为 1 时，真实写入与缓存
    相差一个 float32 刻度，所以这里逐字照抄父类的 alpha 计算、混合、范数守卫与除法，
    期望值仍只来自缓存，不读取实际位姿。A 传 ``(qa, qb)``，B 传 ``(qb, qa)``。
    """
    q_self = np.asarray(q_self, dtype=np.float32).flatten()
    q_other = np.asarray(q_other, dtype=np.float32).flatten()
    # 段起点 cur_step == start_step，父类 alpha 经 clip 与 smoothstep 后仍是 Python 的 0.0。
    alpha = float(np.clip(0.0, 0.0, 1.0))
    alpha = alpha * alpha * (3.0 - 2.0 * alpha)
    q = q_self * (1 - alpha) + q_other * alpha
    norm = np.linalg.norm(q)
    if norm > 1e-6:
        q = q / norm
    return q


def certify_swap_plan(env, actors, bystanders, name_prefix):
    """在父类建场完成后证明并预写全部配对，独立流不掺入档位。"""
    if len(actors) < 2:
        raise SceneGenerationError("交换规划至少需要两个对象")
    try:
        states = {i: bc.object_state_from_actor(a, f"{name_prefix}{i}") for i, a in enumerate(actors)}
        others = bystander_states_of(bystanders)
    except bc.BinCollisionError as exc:
        raise SwapCollisionError(exc.rejection, "initial") from exc
    generator = torch.Generator().manual_seed(int(env.seed) + SWAP_PLAN_SEED_OFFSET)
    plan = plan_swaps(states, others, int(env.swap_times), generator,
                      s_max=max_swap_count(env.robomme_base_id))
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

    def _before_control_step(self):
        super()._before_control_step()
        # 父类已应用本段起点，首个物理子步尚未发生；此时就是本步步号。
        k = self._swap_segment_index_at(int(self.elapsed_steps))
        if k is not None:
            self._runtime_guard("segment_start", self._check_segment_start, k)

    def _before_simulation_step(self):
        super()._before_simulation_step()
        self._runtime_guard("substep_before", self._substep_check, "substep_before")

    def _after_simulation_step(self):
        super()._after_simulation_step()
        self._runtime_guard("substep_after", self._substep_check, "substep_after")

    def _states(self):
        actors = self._swap_actors()
        states = [bc.object_state_from_actor(a, f"{self.swap_name_prefix}{i}") for i, a in enumerate(actors)]
        others = bystander_states_of(self._bystander_actors())
        return actors, states, others

    def _endpoint_evidence(self, k, a, b):
        row = self.swap_schedule[k]
        cache = getattr(self, "_two_lane_swaps", {}).get((id(row[0]), id(row[1]), int(row[2]), int(row[3])))
        actual = {"a_p": a.p.tolist(), "a_q": a.q.tolist(), "b_p": b.p.tolist(), "b_q": b.q.tolist()}
        def raw_q(actor):
            pose = actor.pose if hasattr(actor, "pose") else actor.get_pose()
            return bc._to_numpy(pose.q)[:4].tolist()
        diagnostics = {"phase": "before_physics", "actual_raw_q": {"a": raw_q(row[0]), "b": raw_q(row[1])}}
        if cache is None:
            return False, {"actual": actual, "cached": None, **diagnostics}
        # 段起点父类写入的是缓存 q 经一次 float32 混合与归一化的结果，位置则就是缓存值。
        qa_start = parent_start_q(cache["qa"], cache["qb"])
        qb_start = parent_start_q(cache["qb"], cache["qa"])
        ca = bc.ObjectState(a.name, [cache["ax"], cache["ay"], cache["az"]], qa_start, a.shapes)
        cb = bc.ObjectState(b.name, [cache["bx"], cache["by"], cache["bz"]], qb_start, b.shapes)
        cached = {"a_p": ca.p.tolist(), "a_q": ca.q.tolist(), "b_p": cb.p.tolist(), "b_q": cb.q.tolist()}
        # 原始四元数均按判据的归一化语义转换后比较，不改变几何容差。
        mismatches = [key for key in actual if not np.array_equal(actual[key], cached[key])]
        delta = {key: (np.asarray(actual[key], dtype=np.float64) -
                       np.asarray(cached[key], dtype=np.float64)).tolist() for key in actual}
        return not mismatches, {"actual": actual, "cached": cached, "mismatches": mismatches, **diagnostics,
                                "delta": delta,
                                "cached_raw_q": {"a": bc._to_numpy(cache["qa"]).tolist(),
                                                 "b": bc._to_numpy(cache["qb"]).tolist()},
                                "expected_start_raw_q": {"a": qa_start.tolist(), "b": qb_start.tolist()}}

    def _slot_binding_evidence(self, k, states=None):
        """仅有另一个槽严格更近才失败，等距仍通过；检查全部对象。"""
        if states is None:
            _, states, _ = self._states()
        slots = np.asarray(self._xhard_swap_plan["slots"], dtype=np.float64)
        occ = list(range(len(slots)))
        for sa, sb in self._xhard_swap_plan["slot_pairs"][:k]:
            occ[sa], occ[sb] = occ[sb], occ[sa]
        slot_of = [occ.index(i) for i in range(len(states))]
        rows = []
        for i, state in enumerate(states):
            distances = np.linalg.norm(slots - state.p[:2], axis=1)
            expected = slot_of[i]
            other_closer = bool(np.any(distances < distances[expected]))
            rows.append(dict(object=i, expected_slot=expected, distances=distances.tolist(),
                             drift_mm=float(distances[expected]*1000), other_closer=other_closer))
        return not any(row["other_closer"] for row in rows), {"objects": rows}

    def _check_segment_start(self, k):
        if getattr(self, "_xhard_fatal", None) is not None:
            return
        actors, states, others = self._states()
        initiator = getattr(self, f"swap_pair{k+1}_idx1")
        expected = getattr(self, f"swap_pair{k+1}_idx2")
        a = next(i for i, actor in enumerate(actors) if actor is initiator)
        b = next(i for i, actor in enumerate(actors) if actor is expected)
        match, detail = self._slot_binding_evidence(k, states)
        self._xhard_runtime_checks.append(dict(kind="swap_binding", control_step=int(self.elapsed_steps),
                                                phase="before_physics", sweep_index=k, **detail))
        if not match:
            self._record_fatal("SwapBindingError", "segment_start", k, detail=detail, check="slot_binding")
            return
        match, endpoints = self._endpoint_evidence(k, states[a], states[b])
        if not match:
            self._xhard_runtime_checks.append(dict(kind="swap_sweep", control_step=int(self.elapsed_steps), phase="before_physics",
                                                    sweep_index=k, endpoint_match=False, endpoints=endpoints))
            self._record_fatal("SwapBindingError", "segment_start", k, detail=endpoints, check="endpoint_binding")
            return
        gap, rejection = bc.check_swap_sweep(states[a], states[b],
                                             [s for i, s in enumerate(states) if i not in (a, b)] + others,
                                             sweep_index=k, stage="segment_start")
        self._xhard_runtime_checks.append(dict(kind="swap_sweep", control_step=int(self.elapsed_steps), phase="before_physics",
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

