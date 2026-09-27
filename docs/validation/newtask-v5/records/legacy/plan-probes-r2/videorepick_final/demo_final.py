# P4 本机演示：进程内 monkeypatch 实现 VideoRepick xhard 最终规则（不落盘改仓库），走正式入口 generate_dataset_newseed._worker
#   ① 摆放：6 块两两中心距 ≥ 0.12 m（哨兵障碍把 _obb2d_intersect 变成圆盘判据，随机流与 spawn_random_cube 一致，每 trial 3 个 rand）；
#      已放方块以精确 OBB 三元组 (c, R(yaw), [hs,hs]) 进 avoid，不再放 actor
#   ② 发起者 seq=[目标]+randperm(5)，第 k 次发起者 seq[k%6]；追加 u=torch.rand(n_swaps)
#   ③ reset 规划搭档（final_rule_sim.plan_final，变体 B：前 3 个可行 + 3 近全不可行退任一可行），无可行 → 真 SceneGenerationError
#   ④ step：xhard 窗口开始时用规划好的搭档；D5 _check_swap_sweep_from_actual 保留（记录拒绝）
#   额外记录：每段窗口内被交换两块的逐控制步位移（峰值速度）、名义路径长度、总控制步数
import sys, os, json, time
from pathlib import Path
WT = Path("/data/hongzefu/robomme_v5_probe_wt"); HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(WT / "scripts")); sys.path.insert(0, str(WT / "src")); sys.path.insert(0, str(HERE))
import generate_dataset_newseed as gen
gen._pool_init("1", None, str(WT / "src"))
import numpy as np, torch
import robomme.robomme_env.utils.object_generation as og
from robomme.robomme_env.utils.xhard import hsv_floor_rgb
from robomme.robomme_env.VideoRepick import VideoRepick
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError as RealSGE
from final_rule_sim import plan_final, place_final, HS
from perturb_check2 import InflCache
DMIN = 0.12
_orig_int = og._obb2d_intersect
def _int(c1, A1, h1, c2, A2, h2):
    if h1[0] < 0:
        return float(np.linalg.norm(np.asarray(c2) - np.asarray(c1))) < h1[1]
    return _orig_int(c1, A1, h1, c2, A2, h2)
og._obb2d_intersect = _int
EP = {}

def final_load(self, avoid):
    xhard_cfg = self._sampling["decision"]["xhard"]; layout = xhard_cfg["layout"]
    region_cfg = self._sampling["positions"]["hard_cubes"]
    u3 = torch.rand(3, generator=self.generator).tolist()
    rgb = self._spec.value("objects.color_rgb", hsv_floor_rgb(u3, xhard_cfg["block_color"]), decision_key="xhard.block_color")
    color = (float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0)
    n = int(layout["cube_count"]); self.spawned_cubes = []; slots = []
    for i in range(n):
        try:
            cube = og.spawn_random_cube(self, avoid=avoid, region_center=list(layout["region_center"]),
                region_half_size=list(layout["region_half_size"]), min_gap=self.cube_half_size, half_size=self.cube_half_size,
                name_prefix=f"bin_{i}", max_trials=256, color=color, random_yaw=region_cfg["random_yaw"],
                include_existing=region_cfg["include_existing"], include_goal=region_cfg["include_goal"],
                generator=self.generator, recorder=self._spec, spec_path=f"layout.cubes.{i}.xy_yaw")
        except RuntimeError as e:
            raise RealSGE(f"final: failed bin_{i}") from e
        self.spawned_cubes.append(cube); setattr(self, f"bin_{i}", cube)
        p = self._get_actor_position(cube)
        q = cube.pose.q; q = q.detach().cpu().numpy().reshape(-1) if hasattr(q, "detach") else np.asarray(q).reshape(-1)
        yaw = float(2 * np.arctan2(q[3], q[0]))
        slots.append((float(p[0]), float(p[1]), yaw))
        c, s = np.cos(yaw), np.sin(yaw)
        avoid.append((np.array([p[0], p[1]], dtype=np.float64), np.array([[c, -s], [s, c]]), np.array([self.cube_half_size] * 2, dtype=np.float64)))
        avoid.append((np.array([p[0], p[1]], dtype=np.float64), np.eye(2), np.array([-1.0, DMIN])))
    self._spec.record("objects.cube_count.requested", n); self._spec.record("objects.cube_count.actual", n)
    target = self._spec.value("objects.target", int(torch.randint(0, n, (1,), generator=self.generator).item()))
    self.target_cube_1 = self.spawned_cubes[target]
    remaining = [i for i in range(n) if i != target]
    perm = self._spec.value("objects.swap_initiators_remaining", torch.randperm(len(remaining), generator=self.generator).tolist())
    seq_all = [target] + [remaining[i] for i in perm]
    u = self._spec.value("objects.swap_partner_u", torch.rand(self.swap_times, generator=self.generator).tolist())
    seq = [seq_all[k % n] for k in range(self.swap_times)]
    pairs, fail_k, fb = plan_final(InflCache(slots, HS + 0.005), seq, u, "B")
    off = place_final(int(self.seed), "exact")
    rec = EP.setdefault(int(self.seed), {"loads": 0})
    rec["loads"] += 1
    rec.update(target=target, seq=seq, n_swaps=self.swap_times, slots=slots,
               offline_match=bool(off["ok"]) and max(abs(a - b) for sc, oc in zip(slots, off["cubes"]) for a, b in zip(sc[:2], oc[:2])) < 1e-5,
               plan=None if pairs is None else [(a, b, sa, sb, L) for a, b, sa, sb, L in pairs], plan_fail_k=fail_k, fallback=fb)
    if pairs is None:
        raise RealSGE(f"final: no feasible partner at swap {fail_k}")
    self._vr_plan = [(a, b) for a, b, *_ in pairs]
    self._spec.record("objects.swap_initiators", [f"bin_{i}" for i in seq_all])
    for k in range(self.swap_times):
        setattr(self, f"swap_pair{k+1}_idx1", self.spawned_cubes[seq[k]]); setattr(self, f"swap_pair{k+1}_idx2", None)
    self._refresh_swap_schedule()
VideoRepick._load_cubes_xhard = final_load

_orig_d5 = VideoRepick._check_swap_sweep_from_actual
def d5(self, sweep_index, initiator, partner):
    rec = EP.setdefault(int(self.seed), {}); d = rec.setdefault("d5", [])
    try:
        _orig_d5(self, sweep_index, initiator, partner); d.append({"k": int(sweep_index), "rejected": False, "gap": self._runtime_checks[-1]["min_g_m"]})
    except Exception as e:
        d.append({"k": int(sweep_index), "rejected": True, "err": str(e)[:200]}); raise
VideoRepick._check_swap_sweep_from_actual = d5

_orig_step = VideoRepick.step
def step(self, action):
    rec = EP.setdefault(int(self.seed), {})
    if self.difficulty == "xhard" and hasattr(self, "_vr_plan"):
        if self.current_task_specialflag == "swap" and self.static_flag == False:
            self.static_flag = True; self.start_step = int(self.elapsed_steps.item()); self._refresh_swap_schedule(self.start_step)
        if self.static_flag:
            for i, (_a, _b, start, end) in enumerate(self.swap_schedule):
                if self.elapsed_steps in range(start, end) and getattr(self, f"swap_pair{i+1}_idx2") is None:
                    a_idx, b_idx = self._vr_plan[i]
                    ini = getattr(self, f"swap_pair{i+1}_idx1"); assert self.spawned_cubes.index(ini) == a_idx
                    partner = self.spawned_cubes[b_idx]
                    pa = self._get_actor_position(ini)[:2]; pb = self._get_actor_position(partner)[:2]
                    rec.setdefault("actual_len", []).append(float(np.linalg.norm(pa - pb)))
                    self._check_swap_sweep_from_actual(i, ini, partner)
                    self._spec.record(f"actions.swap_pairs.{i}", {"initiator": f"bin_{a_idx}", "partner": f"bin_{b_idx}"})
                    self._spec.record(f"actions.swap_windows.{i}", [int(start), int(end)])
                    setattr(self, f"swap_pair{i+1}_idx2", partner); self._refresh_swap_schedule(self.start_step)
    before = [self._get_actor_position(c)[:2].copy() for c in self.spawned_cubes] if getattr(self, "static_flag", False) else None
    out = _orig_step(self, action)
    rec["steps"] = int(self.elapsed_steps.item()); rec["control_freq"] = float(self.control_freq)
    if before is not None:
        after = [self._get_actor_position(c)[:2] for c in self.spawned_cubes]
        vmax = max(float(np.linalg.norm(a - b)) for a, b in zip(after, before))
        if vmax > 1e-6 and any(s <= int(self.elapsed_steps.item()) - 1 <= e for _a, _b, s, e in self.swap_schedule):
            rec["step_disp_max"] = max(rec.get("step_disp_max", 0.0), vmax)
    return out
VideoRepick.step = step

out = HERE / "demo_out"; out.mkdir(exist_ok=True)
tag = sys.argv[2]; RES = []
for seed in [int(s) for s in sys.argv[1].split(",")]:
    job = gen.EpisodeJob(task="VideoRepick", episode=9, attempt=0, seed=seed, difficulty="xhard", output_root=str(out), repo_root=str(WT), sampling_config=None)
    t0 = time.time(); res = gen._worker(job)
    r = EP.get(seed, {})
    d5l = r.get("d5", [])
    summ = dict(seed=seed, ok=bool(res.get("ok")), error_type=res.get("error_type"), error=str(res.get("error"))[:160] if not res.get("ok") else None,
                wall_s=round(time.time() - t0, 1), steps=r.get("steps"), n_swaps=r.get("n_swaps"), offline_match=r.get("offline_match"),
                plan_fail_k=r.get("plan_fail_k"), fallback=r.get("fallback"), d5_checked=len(d5l), d5_rejected=sum(x["rejected"] for x in d5l),
                d5_min_gap=min([x["gap"] for x in d5l if not x["rejected"] and x.get("gap") is not None], default=None),
                plan_len_max=max([p[4] for p in (r.get("plan") or [])], default=None), actual_len_max=max(r.get("actual_len", [0])),
                step_disp_max=r.get("step_disp_max"), control_freq=r.get("control_freq"))
    print(json.dumps(summ, ensure_ascii=False), flush=True)
    RES.append({"summary": summ, "detail": r})
    for f in (out / "hdf5_files").glob(f"*seed{seed}*"):
        f.unlink()
    json.dump(RES, open(HERE / f"demo_final_{tag}.json", "w"), default=str)
print("全部完成")
