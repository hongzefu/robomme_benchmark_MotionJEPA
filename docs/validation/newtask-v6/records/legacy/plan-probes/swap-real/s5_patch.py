"""V6 S5 真实演示探针：只在探针子进程内 monkeypatch，不改任何被 git 跟踪的文件。

patch 清单（arm="s5" 时安装；arm="v5" 为对照组，只装只读记录钩子）：
  P1 utils.unmask_swap_xhard.predict_inner_windows（VUS/BUS reset 里 spawn_swap_distractors_v5 调用）：
     改为 S5——读 4 个内环容器实际位姿，对 6 个槽对各跑一次仓库 check_swap_sweep_prefiltered 得可行槽对图 G；
     G 不连通抛 SceneGenerationError("S5_G_DISCONNECTED")；按 S5（可行候选=G 的边，键 (max 计数, sum 计数) 最小，
     平局均匀抽，禁止立即撤销（别无选择才允许），整条极差>1 重排 ≤20 次）预规划整段内环序列，
     写入 swap_pair{k}_idx1/idx2（idx2 预填后 step 的最近邻分支不再执行），返回对应 InnerWindow 列表，
     供原有 prejudge_inner_windows（L20 预判）、InnerSweepGuard（H1）与外环规划照常消费。
  P2 utils.unmask_swap_xhard.plan_distractor_swaps：改为 O4 均衡贪心——每窗把全部 C(count,2) 对按
     (max 计数, sum 计数, 随机数) 排序（不含上一对），逐个调仓库 evaluate_outer_candidate 取第一个可行者；
     全不可行再试上一对；仍无则 ok=False（原逻辑整段重抽布局）。
  P3 VUS/BUS 的 step 包装：因 idx2 已预填、原最近邻分支里的运行时复核不会触发，这里在每窗首步（原分支同一时刻、
     swap 动作之前）调用环境自己的 _check_swap_sweep_from_actual(k, a, b)（→ joint_sweep_from_actual 两对联合
     连续复核，拒绝即抛 BinCollisionError，与原行为相同）。
  P4 VideoRepick._plan_swaps_xhard：改为 VR 版 S5——同一 _XhardSlotSweepFeasibility（5 mm 余量 + 按钮障碍）
     算满可行矩阵 M，有孤立槽抛 SceneGenerationError("S5_ISOLATED")；键 (sum 计数, max 计数)、严格禁止立即换回、
     整条极差>1 重试 ≤20 次；原地改写调用方的 initiator_seq（调用方随后据此写 swap_pair{k}_idx1）并设
     _xhard_swap_partners，step 的 xhard 分支照旧取规划搭档 + 跑 _check_swap_sweep_from_actual。
  R  只读记录（两组都装）：每个控制步若在交换窗口内，step 后调环境自己的 _check_state_readonly 读真实碰撞盒，
     记最小间隙与拒绝次数（只记不抛）；另记实际执行的交换对。
"""
import numpy as np

S5_BUDGET = 20
PAIRS4 = [(a, b) for a in range(4) for b in range(a + 1, 4)]


def _connected(n, edges):
    seen = {0}; st = [0]
    while st:
        u = st.pop()
        for a, b in edges:
            for x, y in ((a, b), (b, a)):
                if x == u and y not in seen:
                    seen.add(y); st.append(y)
    return len(seen) == n


def s5_unmask(G, n_swaps, rng, n=4):
    """p2c/p2d 口径的 S5；G: {(slot_a,slot_b): bool}。返回 (对象对序列, 重排次数, 撤销数)。"""
    best = None
    for t in range(1, S5_BUDGET + 1):
        occ = list(range(n)); cnt = [0] * n; last = None; seq = []; undo = 0
        for k in range(n_swaps):
            allf = [(a, b) for a, b in PAIRS4 if G[(min(occ[a], occ[b]), max(occ[a], occ[b]))]]
            c = [p for p in allf if p != last] or allf
            key = [(max(cnt[a], cnt[b]), cnt[a] + cnt[b]) for a, b in c]; m = min(key)
            c = [p for p, kk in zip(c, key) if kk == m]
            a, b = c[int(rng.integers(len(c)))]
            if (a, b) == last:
                undo += 1
            cnt[a] += 1; cnt[b] += 1; occ[a], occ[b] = occ[b], occ[a]; last = (a, b); seq.append((a, b))
        best = (seq, t, undo)
        if max(cnt) - min(cnt) <= 1:
            return best
    return best


def install(arm):
    import torch  # noqa: F401
    from robomme.robomme_env.utils import unmask_swap_xhard as ux
    from robomme.robomme_env.utils.bin_collision import check_swap_sweep_prefiltered, object_state_from_actor
    from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError
    import importlib
    import robomme.robomme_env  # noqa: F401
    VUSm = importlib.import_module("robomme.robomme_env.VideoUnmaskSwap")
    BUSm = importlib.import_module("robomme.robomme_env.ButtonUnmaskSwap")
    VRm = importlib.import_module("robomme.robomme_env.VideoRepick")
    from robomme.robomme_env.utils.bin_collision import ObjectState

    def rec_step_wrapper(cls, do_inner_check):
        orig = cls.step

        def step(self, action):
            t = int(self.elapsed_steps)
            if do_inner_check and getattr(self, "_s5_info", None) is not None:
                done = self._s5_info.setdefault("_checked", [])
                for k, (a, b, s, _e) in enumerate(getattr(self, "swap_schedule", [])):
                    if t == int(s) and k not in done and a is not None and b is not None:
                        done.append(k)
                        self._check_swap_sweep_from_actual(k, a, b)
            out = orig(self, action)
            try:
                tt = int(self.elapsed_steps)
                if hasattr(self, "_in_swap_window"):
                    inwin = self._in_swap_window()
                else:
                    inwin = any(int(s) <= tt <= int(e) for _a, _b, s, e in getattr(self, "swap_schedule", []))
                if inwin and getattr(self, "static_flag", True):
                    if hasattr(self, "_check_state_readonly"):
                        gap, rej = self._check_state_readonly("probe_ctrl")
                    else:
                        gap, rej = VUSm.check_bin_state(self._object_states_for_collision(), stage="probe_ctrl")
                    r = self.__dict__.setdefault("_probe_ctrl", {"n": 0, "rej": 0, "min_gap": None, "first_rej": None})
                    r["n"] += 1
                    if rej is not None:
                        r["rej"] += 1
                        if r["first_rej"] is None:
                            r["first_rej"] = {"t": t, "rej": rej.as_dict()}
                    elif gap is not None:
                        r["min_gap"] = gap if r["min_gap"] is None else min(r["min_gap"], gap)
            except Exception as exc:  # noqa: BLE001
                self.__dict__.setdefault("_probe_ctrl_err", repr(exc))
            return out
        cls.step = step

    for cls in (VUSm.VideoUnmaskSwap, BUSm.ButtonUnmaskSwap):
        rec_step_wrapper(cls, do_inner_check=(arm == "s5"))
    rec_step_wrapper(VRm.VideoRepick, do_inner_check=False)
    if arm != "s5":
        return

    # ── P1 内环 S5 ──
    def s5_predict_inner_windows(env, partner_axes):
        bins = list(env.spawned_bins)
        n = len(bins)
        states = [object_state_from_actor(a, f"bin_{i}") for i, a in enumerate(bins)]
        G = {}
        for a, b in PAIRS4:
            others = [s for j, s in enumerate(states) if j not in (a, b)]
            _g, rej = check_swap_sweep_prefiltered(states[a], states[b], others, sweep_index=0, stage="s5_graph")
            G[(a, b)] = rej is None
        edges = [p for p, ok in G.items() if ok]
        info = {"G": [int(G[p]) for p in PAIRS4], "n_swaps": int(env.swap_times), "connected": _connected(n, edges)}
        env._s5_info = info
        if not info["connected"]:
            raise SceneGenerationError(f"S5_G_DISCONNECTED G={info['G']}")
        rng = np.random.default_rng(int(env.seed) * 7919 + 17)
        seq, tries, undo = s5_unmask(G, int(env.swap_times), rng, n)
        info.update(seq=[[int(a), int(b)] for a, b in seq], tries=tries, undo=undo)
        for k, (a, b) in enumerate(seq):
            setattr(env, f"swap_pair{k + 1}_idx1", bins[a])
            setattr(env, f"swap_pair{k + 1}_idx2", bins[b])
        env._refresh_swap_schedule()
        ws = []; s = list(states)
        for a, b in seq:
            ws.append(ux.InnerWindow(a=int(a), b=int(b), states=tuple(s)))
            sa, sb = s[a], s[b]
            s[a] = ObjectState(name=sa.name, p=sb.p.copy(), q=sb.q.copy(), shapes=sa.shapes)
            s[b] = ObjectState(name=sb.name, p=sa.p.copy(), q=sa.q.copy(), shapes=sb.shapes)
        return ws

    ux.predict_inner_windows = s5_predict_inner_windows

    # ── P2 外环 O4 ──
    def o4_plan(layout, perm, windows, *, cfg, cube_half_size, buttons_xy=(), stats=None):
        count = layout.count
        perm = [int(v) for v in perm]
        rng = np.random.default_rng(int(sum(p * 31 ** i for i, p in enumerate(perm)) % (2 ** 32)) + 101)
        shapes = ux.padded_bin_shapes(cube_half_size, cfg.plan_pad_m)
        outer = [ux.distractor_bin_state(i, x, y, yaw, cube_half_size, shapes) for i, (x, y, yaw) in enumerate(layout.bins)]
        plan = ux.OuterSwapPlan(ok=False, perm=perm)
        cnt = [0] * count; last = None
        allp = [(a, b) for a in range(count) for b in range(a + 1, count)]
        for k, window in enumerate(windows):
            u = rng.random(len(allp))
            order = sorted(range(len(allp)), key=lambda i: (max(cnt[allp[i][0]], cnt[allp[i][1]]),
                                                            cnt[allp[i][0]] + cnt[allp[i][1]], u[i]))
            cands = [allp[i] for i in order if allp[i] != last] + ([last] if last is not None else [])
            chosen = None
            for o, p in cands:
                ok, reason, _r = ux.evaluate_outer_candidate(k, window, o, p, outer, cfg=cfg, cube_half_size=cube_half_size,
                                                             buttons_xy=buttons_xy, stats=stats)
                if ok:
                    chosen = (o, p); break
                plan.reasons[reason] = plan.reasons.get(reason, 0) + 1
            if chosen is None:
                plan.fail_window = k
                return plan
            o, p = chosen
            plan.pairs.append((o, p)); plan.fallbacks.append(0)
            cnt[o] += 1; cnt[p] += 1; last = (o, p)
            so, sp = outer[o], outer[p]
            outer[o] = ObjectState(name=so.name, p=sp.p.copy(), q=sp.q.copy(), shapes=so.shapes)
            outer[p] = ObjectState(name=sp.name, p=so.p.copy(), q=so.q.copy(), shapes=sp.shapes)
        plan.ok = True
        plan.final_xy = [[float(v) for v in st.p[:2]] for st in outer]
        return plan

    ux.plan_distractor_swaps = o4_plan

    # ── P4 VR S5 ──
    def vr_s5_plan(self, initiator_seq, partner_u, button_obb):
        swap_cfg = self._sampling["decision"]["xhard"]["swap_plan"]
        margin = float(swap_cfg["sweep_margin_m"])
        half = float(self.cube_half_size)
        slots = []
        for cube in self.spawned_cubes:
            c, axes, _h = VRm.cube_obb2d_exact(cube, half)
            slots.append((float(c[0]), float(c[1]), float(np.arctan2(axes[1, 0], axes[0, 0]))))
        statics = []
        if swap_cfg["button_obstacle"]:
            statics.append(VRm.button_base_state("button_base", button_obb[0],
                                                 scale=float(self._sampling["positions"]["button"]["scale"])))
        feas = VRm._XhardSlotSweepFeasibility(VRm._xhard_slot_states(slots, half, margin), statics)
        N = len(slots)
        M = np.zeros((N, N), bool)
        for a in range(N):
            for b in range(a + 1, N):
                M[a, b] = M[b, a] = feas.feasible(a, b)
        info = {"M": M.astype(int).tolist(), "n_swaps": int(self.swap_times), "isolated": bool((M.sum(1) == 0).any())}
        self._s5_info = info
        if info["isolated"]:
            raise VRm._RealSceneGenerationError(f"S5_ISOLATED deg={M.sum(1).tolist()}")
        rng = np.random.default_rng(int(self.seed) * 7919 + 23)
        pairs = [(a, b) for a in range(N) for b in range(a + 1, N) if M[a, b]]
        chosen = None
        for t in range(1, S5_BUDGET + 1):
            occ = list(range(N)); slot_of = list(range(N)); cnt = np.zeros(N, int); last = None; plan = []
            dead = False
            for k in range(int(self.swap_times)):
                cands = [p for p in pairs if p != last]
                if not cands:
                    dead = True; break
                score = [(cnt[occ[a]] + cnt[occ[b]], max(cnt[occ[a]], cnt[occ[b]])) for a, b in cands]
                m = min(score)
                pool = [p for p, s in zip(cands, score) if s == m]
                sa, sb = pool[int(rng.integers(len(pool)))]
                if rng.random() < 0.5:
                    sa, sb = sb, sa
                ia, ib = occ[sa], occ[sb]
                occ[sa], occ[sb] = ib, ia; slot_of[ia], slot_of[ib] = sb, sa
                cnt[ia] += 1; cnt[ib] += 1
                plan.append((int(ia), int(ib), int(sa), int(sb)))
                last = (min(sa, sb), max(sa, sb))
            if dead:
                raise VRm._RealSceneGenerationError("S5_NO_CANDIDATE")
            chosen = (plan, t)
            if cnt.max() - cnt.min() <= 1:
                break
        plan, tries = chosen
        for k, (ia, ib, _sa, _sb) in enumerate(plan):
            initiator_seq[k] = ia   # 原地改写：调用方随后按它写 swap_pair{k}_idx1
        self._xhard_swap_partners = [ib for _ia, ib, _sa, _sb in plan]
        self._xhard_swap_plan_info = {"slots": slots, "plan": plan}
        info.update(seq=[[ia, ib] for ia, ib, _a, _b in plan], slot_seq=[[sa, sb] for _a, _b, sa, sb in plan], tries=tries)
        return plan

    VRm.VideoRepick._plan_swaps_xhard = vr_s5_plan
