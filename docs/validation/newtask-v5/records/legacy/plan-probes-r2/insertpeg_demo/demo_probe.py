"""P6：InsertPeg V5 规则（4 根一个循环 + 轮廓间隔 0.03 / 孔板 0.01）的本机演示探针。

做法（全部进程内补丁，不改任何被跟踪文件）：
  1. 取 InsertPeg._initialize_episode 的源码，做 4 处文本替换后在原模块命名空间里重新 exec：
     - xhard 分支 uniform_pegs = self.pegs（4 根一个循环，排在 obj/dir 之前）
     - 循环内通过两条原生判据后才抽 yaw（lazy），再判 杆-孔板轮廓净距 > 0.01、杆-已放杆轮廓净距 > 0.03（严格）
     - 接受后的 yaw 直接用循环里抽的那个，不再额外抽
     - 删除 _xhard_place_near_target_peg 调用
  2. 包一层：记录布局、给 task_list 每个 solve 包日志（阶段 / 起止步数 / 异常）。
  3. 包 step：逐步记录 4 根杆 head/tail 链接位置，统计非目标杆最大抬升、最大横移。
  4. 每个 seed：先起一个裸 env 做静置 20 步（与 settle_test 同口径），再调主入口 _worker 跑完整演示。
"""
import sys, json, time, inspect, textwrap, argparse, os
from pathlib import Path
import numpy as np

WT = "/data/hongzefu/robomme_v5_probe_wt"
OUT = Path(__file__).resolve().parent
sys.path.insert(0, WT + "/scripts"); sys.path.insert(0, WT + "/src"); sys.path.insert(0, str(OUT))
import peggeom as G  # noqa: E402

PAIR_GAP = 0.03
BOX_GAP = 0.01
BASE = np.array([-0.615, 0.0])
TRACE = {}


def gap_ok(xy, yaw, box_xy, box_yaw, placed):
    """V5 规则：杆轮廓与孔板 > BOX_GAP，与每根已放杆 > PAIR_GAP（严格不等号）。"""
    r = G.peg_rect(np.asarray(xy, float), np.float64(yaw))
    if G.rect_dist(r, G.box_rect(np.asarray(box_xy, float), np.float64(box_yaw))) <= BOX_GAP:
        return False
    for pxy, pyaw in placed:
        if G.rect_dist(r, G.peg_rect(np.asarray(pxy, float), np.float64(pyaw))) <= PAIR_GAP:
            return False
    return True


def install_patch():
    import importlib
    M = importlib.import_module("robomme.robomme_env.InsertPeg")
    M = sys.modules["robomme.robomme_env.InsertPeg"]
    cls = M.InsertPeg
    src = inspect.getsource(cls._initialize_episode)  # 先按文件原缩进替换，再 dedent
    reps = [
        ("uniform_pegs = self.pegs[:-1]", "uniform_pegs = self.pegs"),
        ("sampled_xy_positions = []\n",
         "sampled_xy_positions = []\n            _v5_placed = []\n            _yaw_try = None\n"),
        ("                    candidate_xy = sampled_xy\n                    break",
         "                    if xhard:\n"
         "                        _yaw_try = (torch.rand(1, generator=self._hb_generator).item() * 2 - 1) * np.radians(yaw_half_span_deg)\n"
         "                        if not _V5_GAP_OK(sampled_xy, _yaw_try, box_xy, box_yaw, _v5_placed):\n"
         "                            continue\n"
         "                    candidate_xy = sampled_xy\n                    break"),
        ("                yaw_value = (torch.rand(1, generator=self._hb_generator).item() * 2 - 1) * np.radians(yaw_half_span_deg)\n",
         "                yaw_value = _yaw_try if xhard else (torch.rand(1, generator=self._hb_generator).item() * 2 - 1) * np.radians(yaw_half_span_deg)\n"),
        ("                sampled_xy_positions.append(candidate_xy)\n",
         "                sampled_xy_positions.append(candidate_xy)\n                _v5_placed.append((candidate_xy, yaw_value))\n"),
        ("self._xhard_place_near_target_peg(box_xy, sampled_xy_positions, xhard_cfg)", "pass  # V5：删除近目标干扰杆"),
    ]
    for a, b in reps:
        assert src.count(a) == 1, f"替换锚点不唯一或缺失：{a!r} 出现 {src.count(a)} 次"
        src = src.replace(a, b)
    src = textwrap.dedent(src)
    M.__dict__["_V5_GAP_OK"] = gap_ok
    ns = {}
    exec(compile(src, "<v5_patched_initialize_episode>", "exec"), M.__dict__, ns)
    patched = ns["_initialize_episode"]

    def init_wrapper(self, env_idx, options):
        patched(self, env_idx, options)
        if not hasattr(self, "pegs") or getattr(self, "difficulty", None) != "xhard":
            return
        lay = snapshot(self)
        TRACE.setdefault("layouts", []).append(lay)
        TRACE["env"] = self
        TRACE["stages"] = []
        TRACE["track"] = {"nt_max_lift_mm": [0.0] * 4, "max_dxy_mm": [0.0] * 4, "init": [p["center"] for p in lay["pegs"]]}
        for k, entry in enumerate(self.task_list):
            entry["solve"] = wrap_solve(self, k, entry)

    cls._initialize_episode = init_wrapper
    orig_step = cls.step

    def step_wrapper(self, action):
        out = orig_step(self, action)
        tr = TRACE.get("track")
        if tr is not None and TRACE.get("env") is self:
            for i in range(4):
                h = np.asarray(self.peg_heads[i].pose.p).reshape(-1); t = np.asarray(self.peg_tails[i].pose.p).reshape(-1)
                c = (h + t) / 2
                tr["max_dxy_mm"][i] = max(tr["max_dxy_mm"][i], float(np.linalg.norm(c[:2] - np.asarray(tr["init"][i])) * 1000))
                tr["nt_max_lift_mm"][i] = max(tr["nt_max_lift_mm"][i], float((min(h[2], t[2]) - 0.01) * 1000))
        return out

    cls.step = step_wrapper
    orig_eval = cls.evaluate

    def eval_wrapper(self, *args, **kw):
        out = orig_eval(self, *args, **kw)
        try:
            TRACE["last_eval"] = {k: (bool(np.asarray(v.cpu() if hasattr(v, "cpu") else v).reshape(-1)[0])
                                      if np.asarray(v.cpu() if hasattr(v, "cpu") else v).size == 1 else None)
                                  for k, v in dict(out).items()}
        except Exception as ex:  # noqa: BLE001
            TRACE["last_eval"] = f"unparsed {type(ex).__name__}"
        return out

    cls.evaluate = eval_wrapper


def wrap_solve(env, k, entry):
    f = entry["solve"]

    def g(e, planner):
        rec = {"k": k, "name": entry["name"], "demo": bool(entry.get("demonstration")), "t0": int(env.elapsed_steps)}
        TRACE["stages"].append(rec)
        try:
            r = f(e, planner)
            rec["ret"] = "fail(-1)" if (isinstance(r, int) and r == -1) else "ok"
            return r
        except Exception as ex:  # noqa: BLE001
            rec["exc"] = f"{type(ex).__name__}: {str(ex)[:120]}"
            raise
        finally:
            rec["t1"] = int(env.elapsed_steps)
            # 诊断：阶段结束时目标杆两端与孔板的位置、最近一次 evaluate
            rec["tgt_head"] = np.round(np.asarray(env.peg_heads[0].pose.p).reshape(-1), 4).tolist()
            rec["tgt_tail"] = np.round(np.asarray(env.peg_tails[0].pose.p).reshape(-1), 4).tolist()
            rec["box"] = np.round(np.asarray(env.box.pose.p).reshape(-1), 4).tolist()
            rec["eval"] = TRACE.get("last_eval")
            rec["flip_log"] = list(getattr(env, "_peg_grasp_flip_log", []) or [])
    return g


def snapshot(env):
    """从真实链接位姿量几何（与采样器独立的交叉核验）。"""
    pegs = []
    for i in range(4):
        h = np.asarray(env.peg_heads[i].pose.p).reshape(-1)[:2].astype(float)
        t = np.asarray(env.peg_tails[i].pose.p).reshape(-1)[:2].astype(float)
        u = (h - t) / np.linalg.norm(h - t)
        c = (h + t) / 2
        pegs.append({"head": h.tolist(), "tail": t.tolist(), "center": c.tolist(), "yaw": float(np.arctan2(u[1], u[0]))})
    bq = np.asarray(env.box.pose.q).reshape(-1); bp = np.asarray(env.box.pose.p).reshape(-1)
    w, x, y, z = bq
    box_yaw = float(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))
    box_r = G.rect_corners(bp[:2].astype(float), G.axis(np.float64(box_yaw)), G.BOX_HALF)
    rects = [G.rect_corners(np.array(p["center"]), G.axis(np.float64(p["yaw"])), G.PEG_HALF) for p in pegs]
    pair = {f"{i}{j}": float(G.rect_dist(rects[i], rects[j])) for i in range(4) for j in range(i + 1, 4)}
    boxg = [float(G.rect_dist(r, box_r)) for r in rects]
    # 目标恒为 peg_0；抓取端 obj_flag=-1 抓 head，否则抓 tail
    tgt = pegs[0]
    grasp = np.array(tgt["head"] if env.obj_flag == -1 else tgt["tail"])
    base = np.asarray(env.agent.robot.pose.p).reshape(-1)[:2].astype(float)
    # 夹爪区：抓取链接中心处，沿杆向 ±8.75 mm，垂向 0.01~0.04 为闭合区（pinch），0.04~0.0648 为指垫落点（land）
    yaw0 = np.float64(tgt["yaw"])
    u0 = G.axis(yaw0); v0 = np.array([-u0[1], u0[0]])
    def zone(lo, hi):
        mid = (lo + hi) / 2; half = np.array([G.FINGER_ALONG, (hi - lo) / 2])
        zl = G.rect_corners(grasp + mid * v0, u0, half); zr = G.rect_corners(grasp - mid * v0, u0, half)
        return [j for j in range(1, 4) if G.rect_intersect(zl, rects[j]) or G.rect_intersect(zr, rects[j])]
    return {
        "pegs": pegs, "box_xy": bp[:2].tolist(), "box_yaw": box_yaw, "base_xy": base.tolist(),
        "pair_gap": pair, "min_pair_gap": min(pair.values()), "tgt_min_pair_gap": min(v for k, v in pair.items() if k[0] == "0"),
        "box_gap": boxg, "min_box_gap": min(boxg), "obj_flag": int(env.obj_flag), "direction": int(env.direction),
        "grasp_xy": grasp.tolist(), "grasp_dist_base": float(np.linalg.norm(grasp - base)),
        "pinch": zone(0.0101, 0.04), "land": zone(0.04, G.FINGER_PERP_OUT),
    }


def settle(seed, steps=20):
    import gymnasium as gym
    from robomme.robomme_env.utils import reset_panda
    env = gym.make("InsertPeg", obs_mode="state", control_mode="pd_joint_pos", reward_mode="dense", seed=seed, difficulty="xhard")
    env.reset()
    b = env.unwrapped
    lay = snapshot(b)
    c0 = [np.array(p["center"]) for p in lay["pegs"]]; y0 = [p["yaw"] for p in lay["pegs"]]
    action = reset_panda.get_reset_panda_param("action")
    action = np.asarray(action.cpu() if hasattr(action, "cpu") else action, dtype=np.float32).reshape(-1)
    for _ in range(steps):
        env.step(action)
    lay1 = snapshot(b)
    dxy = [float(np.linalg.norm(np.array(p["center"]) - c0[i]) * 1000) for i, p in enumerate(lay1["pegs"])]
    dyaw = [float(np.degrees((p["yaw"] - y0[i] + np.pi) % (2 * np.pi) - np.pi)) for i, p in enumerate(lay1["pegs"])]
    env.close()
    return lay, dxy, dyaw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", default="0,1,2,3,4,5,6,7,8,9")
    ap.add_argument("--gpu", default="1")
    ap.add_argument("--results", default="results.jsonl")
    ap.add_argument("--out-sub", default="demo")
    a = ap.parse_args()
    import generate_dataset_newseed as gen
    gen._pool_init(a.gpu, None, WT + "/src")  # 先绑卡，再 import torch / robomme
    install_patch()
    out = OUT / a.out_sub; out.mkdir(parents=True, exist_ok=True)
    res_path = OUT / a.results
    for ep in [int(e) for e in a.episodes.split(",")]:
        seed = 5300000 + 100 * ep
        TRACE.clear()
        t0 = time.time()
        slay, dxy, dyaw = settle(seed)
        TRACE.clear()
        job = gen.EpisodeJob(task="InsertPeg", episode=ep, attempt=0, seed=seed, difficulty="xhard",
                             output_root=str(out), repo_root=WT, sampling_config=None)
        r = gen._worker(job)
        lay = TRACE["layouts"][-1] if TRACE.get("layouts") else None
        same = lay is not None and all(np.allclose(lay["pegs"][i]["center"], slay["pegs"][i]["center"], atol=1e-6) for i in range(4))
        row = {"episode": ep, "seed": seed, "recovery_mode": r.get("recovery_mode"), "ok": bool(r.get("ok")),
               "error_type": r.get("error_type"), "error": (r.get("error") or "")[:300],
               "timesteps": r.get("timestep_count"), "wall_s": round(time.time() - t0, 1),
               "layout_same_as_settle_env": bool(same), "n_inits": len(TRACE.get("layouts", [])),
               "layout": lay, "settle_dxy_mm": dxy, "settle_dyaw_deg": dyaw,
               "stages": TRACE.get("stages"), "track": {k: v for k, v in (TRACE.get("track") or {}).items() if k != "init"}}
        with res_path.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        L = lay or {}
        print(f"EP ep={ep} seed={seed} ok={row['ok']} steps={row['timesteps']} err={row['error_type']} "
              f"min_pair={L.get('min_pair_gap', float('nan')):.4f} min_box={L.get('min_box_gap', float('nan')):.4f} "
              f"grasp_d={L.get('grasp_dist_base', float('nan')):.3f} pinch={L.get('pinch')} land={L.get('land')} "
              f"settle_max={max(dxy):.2f}mm same={same} wall={row['wall_s']}s", flush=True)
    print("ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
