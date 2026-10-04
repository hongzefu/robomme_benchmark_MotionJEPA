"""全格 reset 扫描：xhard0 16 任务 × 1 + xhard1~5 43 格 × 1 = 59 次 reset，只 reset 不 step。"""
import json, time, hashlib, subprocess, sys, traceback
import numpy as np
from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder
OUT = sys.argv[1]
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
def d(x):
    if isinstance(x, list): return f"list[{len(x)}]:{d(x[0]) if x else '-'}"
    return f"{type(x).__name__}{tuple(getattr(x,'shape',()))}{getattr(x,'dtype','')}"
cells = []
for task in BenchmarkEnvBuilder.get_task_list():
    cells.append((task, "test", 3, "xhard0"))
    b = BenchmarkEnvBuilder(env_id=task, dataset="test-hard", action_space="joint_angle", max_steps=1600)
    seen = set()
    for ep in range(b.get_episode_num()):
        tier = b.resolve_episode(ep)[1]
        if tier not in seen:
            seen.add(tier); cells.append((task, "test-hard", ep, tier))
print(f"SWEEP_START cells={len(cells)} head={head}", flush=True)
ok = 0
with open(OUT, "w") as f:
    for task, ds, ep, tier in cells:
        rec = {"task": task, "dataset": ds, "episode": ep, "tier": tier, "head": head}
        t = time.time()
        try:
            b = BenchmarkEnvBuilder(env_id=task, dataset=ds, action_space="joint_angle", max_steps=1600)
            rec["seed"], rec["difficulty"] = [str(x) for x in b.resolve_episode(ep)]
            env = b.make_env_for_episode(ep); obs, info = env.reset()
            rec["wall_s"] = round(time.time() - t, 2)
            rec["obs"] = {k: d(v) for k, v in obs.items()}
            rec["info_keys"] = sorted(info.keys()); rec["status"] = info.get("status")
            rec["task_goal"] = info.get("task_goal"); rec["n_frames"] = len(obs["front_rgb_list"])
            rec["frame_sha"] = hashlib.sha256(np.asarray(obs["front_rgb_list"][-1]).tobytes()).hexdigest()[:16]
            rec["joint"] = np.asarray(obs["joint_state_list"][-1]).round(5).tolist()
            chain = []; e = env
            while hasattr(e, "env"): chain.append(type(e).__name__); e = e.env
            rec["chain"] = chain + [type(e).__name__]; rec["ok"] = True; ok += 1
            env.close()
        except Exception as ex:
            rec["ok"] = False; rec["error"] = repr(ex)[:500]; rec["wall_s"] = round(time.time() - t, 2)
            traceback.print_exc()
        f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
        print(f"CELL {task} {tier} ok={rec['ok']} wall={rec['wall_s']}s frames={rec.get('n_frames')}", flush=True)
print(f"RESET_SWEEP={'PASS' if ok == len(cells) else 'FAIL'} cells={len(cells)} ok={ok}", flush=True)
