"""P5 问题 2：进程内原型（monkeypatch，不改任何被跟踪文件）。

替换三处（只对 xhard 生效，与 V5 计划 2.5～2.7 的改法同构）：
* ``_spawn_xhard_distractors``：内环对内环预判 → 最多 16 次（统一采样器放 10 个 + 外环规划）→ 建容器与带序号 cube；
  障碍 OBB 用真实 ``get_actor_obb``（与 spawn_ring_distractor_bins 同一收集口径），按钮用 build_button 返回的 OBB；
* ``step``：包一层，在原 step 之前按规划对外环 ``swap_flat_two_lane``（lane 0.07、smoothstep、同窗口），
  外环 cube 用 ``lift_and_drop_objectA_onto_objectB`` 跟随（与内环 cube 同一机制、同一 [64, last_end]）；
* ``_check_swap_sweep_from_actual``：两对联合连续证明（实际位姿，认证预筛随 SWAP10_PREFILTER）。

用法：
  proto_sim.py reset <Task> <seed,seed,...>       只 make+reset，记墙钟与规划、对拍副本与离线结果
  proto_sim.py demo  <Task> <seed,seed,...>       走 generate_dataset_newseed._worker 跑完整演示
环境变量 SWAP10_PREFILTER=0/1（默认 1）。每局一行 ROW/DEMO JSON。
"""
import importlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
WT = Path("/data/hongzefu/robomme_v5_probe_wt")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(WT / "scripts"))
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import generate_dataset_newseed as gen  # noqa: E402

gen._pool_init(os.environ["CUDA_VISIBLE_DEVICES"], None, str(WT / "src"))

import gymnasium as gym  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402

import robomme.robomme_env  # noqa: E402,F401
import swap10lib as L  # noqa: E402
from multi_sweep import check_multi_swap_sweep  # noqa: E402
from replica import bus_layout, initiators, vus_layout  # noqa: E402
from robomme.robomme_env.utils.bin_collision import BinCollisionError, object_state_from_actor  # noqa: E402
from robomme.robomme_env.utils.object_generation import build_bin, spawn_fixed_cube  # noqa: E402
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # noqa: E402
from robomme.robomme_env.utils.statechange import lift_and_drop_objectA_onto_objectB, swap_flat_two_lane  # noqa: E402
from robomme.robomme_env.utils.unmask_distractors import _obstacle_obbs  # noqa: E402
from robomme.robomme_env.utils.unmask_swap_xhard import distractor_generator  # noqa: E402
from robomme.robomme_env.utils.xhard import DISTRACTOR_COLORS  # noqa: E402

RGBA = {c["name"]: c["rgba"] for c in DISTRACTOR_COLORS}
LOG = []  # 每次 _load_scene 一条记录（含 step 统计），供 demo 模式在 _worker 关环境后读取
SNAP_DIR = HERE / "frames"
SNAP_DIR.mkdir(exist_ok=True)


def _xy(actor):
    p = actor.pose.p
    if isinstance(p, torch.Tensor):
        p = p[0].detach().cpu().numpy()
    return np.asarray(p, dtype=np.float64)[:2]


def new_spawn(self, button_obbs=None):
    t0 = time.perf_counter()
    for k in L.STATS:
        L.STATS[k] = 0 if isinstance(L.STATS[k], int) else 0.0
    bins = list(self.spawned_bins)
    states = [object_state_from_actor(a, f"bin_{i}") for i, a in enumerate(bins)]
    positions = [np.asarray(self._get_actor_position(a), dtype=np.float32)[:2] for a in bins]
    inits = [next(i for i, a in enumerate(bins) if a is getattr(self, f"swap_pair{k + 1}_idx1")) for k in range(int(self.swap_times))]
    seq = L.predict_inner(states, positions, inits)
    real_obbs = _obstacle_obbs(bins, L.CFG["min_gap"])          # 真实 get_actor_obb 外扩 0.015
    ana_obbs = [L.bin_obb(s.p[0], s.p[1], s.q, L.CFG["min_gap"]) for s in states]
    obb_diff = max(float(np.max(np.abs(r[0] - a[0]))) + float(np.max(np.abs(r[2] - a[2]))) for r, a in zip(real_obbs, ana_obbs))
    btn_obbs = list(button_obbs or [])
    buttons = [np.asarray(c, float)[:2] for c, _A, _h in btn_obbs]
    rec = dict(task=type(self).__name__, seed=int(self.seed), n_swaps=len(seq), inner_pairs=[(a, b) for a, b, _ in seq],
               inner_xy=[p.tolist() for p in positions], initiators=inits, obb_center_half_maxdiff=obb_diff,
               button_obbs=[(np.asarray(c).tolist()[:2], np.asarray(h).tolist()) for c, _A, h in btn_obbs],
               prefilter=L.PREFILTER, steps=[], vis_miss=[], end_err=[], cube_err=None, joint_checks=[], partner_mismatch=0)
    LOG.append(rec)
    try:
        res = L.plan_episode(distractor_generator(self.seed), btn_obbs + real_obbs, seq, buttons)
    except L.SceneReject as exc:
        rec.update(status=exc.kind, t_plan=time.perf_counter() - t0, **dict(L.STATS))
        raise SceneGenerationError(f"P5 原型候选级拒绝[{exc.kind}]：{exc}") from None
    lay, plan = res["layout"], res["plan"]
    rec.update(status="ok", n_attempts=res["n_attempts"], pairs=plan["pairs"], tries=plan["tries"],
               placements=lay["placements"], cube_bins=lay["cube_bins"], cube_colors=lay["cube_colors"],
               t_plan=time.perf_counter() - t0, t_prejudge=res["t_prejudge"], **dict(L.STATS))
    divisor = 1.2
    if type(self).__name__ == "ButtonUnmaskSwap":
        divisor = self._sampling["positions"]["hidden_cube"]["half_size_divisor"]
    self.distractor_bins = [build_bin(self, callsign=f"distractor_bin_{i}", position=[x, y, 0.002], z_rotation_deg=yaw)
                            for i, (x, y, yaw) in enumerate(lay["placements"])]
    self.distractor_cubes, pairs = [], []
    for j, (bi, color) in enumerate(zip(lay["cube_bins"], lay["cube_colors"])):
        x, y, _ = lay["placements"][bi]
        cube = spawn_fixed_cube(self, position=[x, y], half_size=self.cube_half_size / divisor, color=RGBA[color],
                                name_prefix=f"distractor_cube_{j}_{color}", yaw=0.0, dynamic=True)
        self.distractor_cubes.append(cube)
        pairs.append((cube, self.distractor_bins[bi]))
    self.distractor_cube_colors = list(lay["cube_colors"])
    # 名义轨迹：每窗结束后外环各容器的 XY
    pos = [np.array(p[:2]) for p in lay["placements"]]
    nominal = []
    for o, p in plan["pairs"]:
        pos[o], pos[p] = pos[p].copy(), pos[o].copy()
        nominal.append([q.copy() for q in pos])
    self._p5 = dict(rec=rec, pairs=plan["pairs"], cube_pairs=pairs, nominal=nominal, seq=seq)


def make_step(orig):
    def step(self, action):
        p5 = getattr(self, "_p5", None)
        ts = int(self.elapsed_steps)
        t0 = time.perf_counter()
        sched = getattr(self, "swap_schedule", [])
        if p5 is not None and sched:
            D = self.distractor_bins
            for k, (o, p) in enumerate(p5["pairs"]):
                start, end = sched[k][2], sched[k][3]
                swap_flat_two_lane(self, cube_a=D[o], cube_b=D[p], start_step=start, end_step=end, cur_step=ts,
                                   lane_offset=L.CFG["lane"], smooth=True, keep_upright=True,
                                   other_cube=[D[j] for j in range(len(D)) if j not in (o, p)])
            for cube, b in (p5["cube_pairs"] if os.environ.get("SWAP10_OUTER_CUBE_PARK", "1") != "0" else []):
                lift_and_drop_objectA_onto_objectB(self, obj_a=cube, obj_b=b, start_step=self.swap_window_start,
                                                   end_step=sched[-1][3], cur_step=ts)
        out = orig(self, action)
        if p5 is not None and sched:
            rec = p5["rec"]
            rec["steps"].append((ts, time.perf_counter() - t0))
            last_end = sched[-1][3]
            if self.swap_window_start <= ts <= last_end:
                xy = np.array([_xy(a) for a in self.distractor_bins])
                vis = L.visible_xy_many(xy)
                if not vis.all():
                    rec["vis_miss"].append((ts, np.where(~vis)[0].tolist()))
                for k, (o, p) in enumerate(p5["pairs"]):
                    if ts == sched[k][3]:
                        nom = p5["nominal"][k]
                        err = max(float(np.linalg.norm(xy[j] - nom[j])) for j in range(len(nom)))
                        rec["end_err"].append((k, err))
                if ts == sched[0][2] + 16 and not rec.get("snap"):
                    rgb = out[0]["sensor_data"]["base_camera"]["rgb"][0].cpu().numpy()
                    f = SNAP_DIR / f"{rec['task']}_{rec['seed']}_t{ts}.png"
                    Image.fromarray(rgb).save(f)
                    rec["snap"] = str(f)
                if ts == last_end:
                    rec["cube_err"] = max(float(np.linalg.norm(_xy(c) - _xy(b))) for c, b in p5["cube_pairs"])
                    rgb = out[0]["sensor_data"]["base_camera"]["rgb"][0].cpu().numpy()
                    Image.fromarray(rgb).save(SNAP_DIR / f"{rec['task']}_{rec['seed']}_t{ts}_end.png")
        return out
    return step


def joint_check(self, sweep_index, initiator, partner):
    p5 = self._p5
    rec = p5["rec"]
    ist = [object_state_from_actor(a, f"bin_{i}") for i, a in enumerate(self.spawned_bins)]
    a, b = self.spawned_bins.index(initiator), self.spawned_bins.index(partner)
    exp = p5["seq"][sweep_index]
    if (exp[0], exp[1]) != (a, b):
        rec["partner_mismatch"] += 1
    o, p = p5["pairs"][sweep_index]
    ost = [object_state_from_actor(d, f"distractor_bin_{i}") for i, d in enumerate(self.distractor_bins)]
    by = [s for j, s in enumerate(ist) if j not in (a, b)] + [s for j, s in enumerate(ost) if j not in (o, p)]
    t = time.perf_counter()
    g, rej, n = check_multi_swap_sweep([(ist[a], ist[b]), (ost[o], ost[p])], by, sweep_index=sweep_index, stage="sweep",
                                       circle_r=L.RADIUS if L.PREFILTER else None)
    dt = time.perf_counter() - t
    rec["joint_checks"].append(dict(k=sweep_index, g=None if rej else g, rej=None if rej is None else rej.summary(), dt=dt, proved=n))
    self._runtime_checks.append(dict(kind="swap_sweep_joint", sweep_index=sweep_index, control_step=int(self.elapsed_steps),
                                     min_g_m=None if rej else g, rejection=None if rej is None else rej.as_dict()))
    if rej is not None:
        raise BinCollisionError(rej)


for name in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
    cls = getattr(importlib.import_module(f"robomme.robomme_env.{name}"), name)
    cls._spawn_xhard_distractors = new_spawn
    cls.step = make_step(cls.step)
    cls._check_swap_sweep_from_actual = joint_check


def compare_offline(rec):
    """与离线（replica + 同一库）结果对拍：内环布局、发起者、干扰放置、外环交换对。"""
    lay = (vus_layout if rec["task"] == "VideoUnmaskSwap" else bus_layout)(rec["seed"])
    out = {}
    if not lay.get("spawn_fail"):
        out["inner_xy_maxerr"] = float(np.max(np.abs(np.array([b[:2] for b in lay["bins"]]) - np.array(rec["inner_xy"]))))
        out["initiators_eq"] = initiators(lay) == rec["initiators"]
    f = HERE / f"offline_{rec['task']}_main.jsonl"
    if f.exists():
        for line in f.read_text().splitlines():
            r = json.loads(line)
            if r["seed"] == rec["seed"]:
                out["offline_status"] = r["status"]
                if r["status"] == "ok" and rec.get("status") == "ok":
                    out["placements_maxerr"] = float(np.max(np.abs(np.array(r["placements"]) - np.array(rec["placements"]))))
                    out["pairs_eq"] = [tuple(x) for x in r["pairs"]] == [tuple(x) for x in rec["pairs"]]
                    out["attempts_eq"] = r["n_attempts"] == rec["n_attempts"]
                break
    return out


def summarize_rec(rec):
    dts = np.array([d for _t, d in rec["steps"]]) if rec["steps"] else np.array([np.nan])
    swap_dts = np.array([d for t, d in rec["steps"] if t >= 64]) if rec["steps"] else np.array([np.nan])
    return dict(status=rec.get("status"), n_swaps=rec["n_swaps"], n_attempts=rec.get("n_attempts"), t_plan=round(rec.get("t_plan", 0), 3),
                obb_maxdiff=round(rec["obb_center_half_maxdiff"], 6), steps=len(rec["steps"]),
                step_ms_p50=round(float(np.nanpercentile(dts, 50)) * 1000, 1), step_ms_p95=round(float(np.nanpercentile(dts, 95)) * 1000, 1),
                swap_step_ms_p95=round(float(np.nanpercentile(swap_dts, 95)) * 1000, 1) if len(swap_dts) else None,
                vis_miss_frames=len(rec["vis_miss"]), end_err_max_mm=round(max([e for _k, e in rec["end_err"]] or [np.nan]) * 1000, 3),
                windows_ended=len(rec["end_err"]), cube_err_mm=None if rec["cube_err"] is None else round(rec["cube_err"] * 1000, 3),
                joint_checks=len(rec["joint_checks"]), joint_rej=sum(1 for c in rec["joint_checks"] if c["rej"]),
                joint_ms_max=round(max([c["dt"] for c in rec["joint_checks"]] or [0]) * 1000, 1),
                partner_mismatch=rec["partner_mismatch"], pairs=rec.get("pairs"), snap=rec.get("snap"))


if __name__ == "__main__":
    mode, task, seeds = sys.argv[1], sys.argv[2], [int(s) for s in sys.argv[3].split(",") if s]
    kw = dict(obs_mode="rgb+depth+segmentation", control_mode="pd_joint_pos", render_mode="rgb_array", reward_mode="dense", difficulty="xhard")
    for seed in seeds:
        LOG.clear()
        if mode == "reset":
            row = dict(task=task, seed=seed, prefilter=L.PREFILTER)
            env = None
            try:
                t0 = time.perf_counter(); env = gym.make(task, seed=seed, **kw); row["make_s"] = round(time.perf_counter() - t0, 2)
                t0 = time.perf_counter(); env.reset(); row["reset_s"] = round(time.perf_counter() - t0, 2)
                row["ok"] = True
            except Exception as exc:  # noqa: BLE001
                row.update(ok=False, err=f"{type(exc).__name__}: {str(exc)[:200]}")
            finally:
                if env is not None:
                    env.close()
            row["load_scene_calls"] = len(LOG)
            row["t_plan_each"] = [round(r.get("t_plan", 0), 2) for r in LOG]
            if LOG:
                last = LOG[-1]
                row.update(status=last.get("status"), n_attempts=last.get("n_attempts"), pairs=last.get("pairs"),
                           obb_maxdiff=last["obb_center_half_maxdiff"], h1_calls=last.get("h1_calls"), h1_s=round(last.get("h1_s", 0), 2),
                           joint_calls=last.get("joint_calls"), joint_s=round(last.get("joint_s", 0), 2),
                           t_prejudge=round(last.get("t_prejudge", 0), 3), buttons=last["button_obbs"])
                row["vs_offline"] = compare_offline(last)
            print("ROW " + json.dumps(row, ensure_ascii=False), flush=True)
        elif mode == "hold":
            # 诊断：不调规划器，保持关节角步进到 last_end+5，按时段统计每步耗时（看停放点堆叠的代价）
            env = gym.make(task, seed=seed, **kw); env.reset(); b = env.unwrapped
            qpos = b.agent.robot.get_qpos()[0].cpu().numpy(); act = np.concatenate([qpos[:7], [qpos[7]]]).astype(np.float32)
            last_end = b.swap_schedule[-1][3]
            for _ in range(last_end + 6):
                env.step(act)
            rec = LOG[-1]
            seg = {"pre[0,64)": [d for t, d in rec["steps"] if t < 64], "swap[64,end)": [d for t, d in rec["steps"] if 64 <= t < last_end],
                   "post": [d for t, d in rec["steps"] if t >= last_end]}
            env.close()
            print("HOLD " + json.dumps(dict(task=task, seed=seed, park=os.environ.get("SWAP10_OUTER_CUBE_PARK", "1"), last_end=last_end,
                  **{k: dict(n=len(v), p50_ms=round(float(np.percentile(v, 50)) * 1000, 1), p95_ms=round(float(np.percentile(v, 95)) * 1000, 1))
                     for k, v in seg.items() if v}, vis_miss=len(rec["vis_miss"]), end_err_max_mm=round(max(e for _k, e in rec["end_err"]) * 1000, 3))), flush=True)
        else:
            job = gen.EpisodeJob(task=task, episode=0, attempt=0, seed=seed, difficulty="xhard",
                                 output_root=str(HERE / f"demo_out_{task}"), repo_root=str(WT), sampling_config=None)
            t0 = time.perf_counter()
            r = gen._worker(job)
            row = dict(task=task, seed=seed, ok=bool(r.get("ok")), failure_class=r.get("failure_class"), error_type=r.get("error_type"),
                       error=(r.get("error") or "")[:300], wall_s=round(time.perf_counter() - t0, 1), phases=r.get("phases"),
                       load_scene_calls=len(LOG),
                       bin_collision=sum(1 for c in r.get("runtime_checks", []) if c.get("rejection")) + (r.get("error_type") == "BinCollisionError"))
            if LOG:
                row.update(summarize_rec(LOG[-1]))
                row["vs_offline"] = compare_offline(LOG[-1])
            print("DEMO " + json.dumps(row, ensure_ascii=False, default=str), flush=True)
    print("SIM_DONE", flush=True)
