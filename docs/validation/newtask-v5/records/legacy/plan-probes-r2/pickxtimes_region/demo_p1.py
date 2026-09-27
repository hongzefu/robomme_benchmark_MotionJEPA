"""P1 本机演示探针：进程内打 patch_p1 补丁后，走 generate_dataset_newseed._worker（与正式生成同一入口）。
用法: demo_p1.py <hw> <out_dir> <seed,seed,...> [num_min,num_max]
每局记录：成败、失败分类、时间步数、墙钟、实际布局（与离线副本逐位对比）、目标/最远方块离基座距离。"""
import json, math, sys, time
from pathlib import Path
WT = Path("/data/hongzefu/robomme_v5_probe_wt")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(WT / "scripts")); sys.path.insert(0, str(WT / "src")); sys.path.insert(0, str(HERE))
import generate_dataset_newseed as gen
gen._pool_init("0", None, str(WT / "src"))
import patch_p1
hw = float(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
seeds = [int(s) for s in sys.argv[3].split(",")]
nr = tuple(int(v) for v in sys.argv[4].split(",")) if len(sys.argv) > 4 else (15, 15)
patch_p1.apply_patch(hw=hw, num_range=nr)
from offline_p1 import v5_layout, BASE
import h5py
for seed in seeds:
    patch_p1.ACCEPTED.clear()
    job = gen.EpisodeJob(task="PickXtimes", episode=9, attempt=0, seed=seed, difficulty="xhard",
                         output_root=str(out), repo_root=str(WT), sampling_config=None)
    t = time.time()
    res = gen._worker(job)
    acc = list(patch_p1.ACCEPTED)
    off = v5_layout(seed, cube_half=hw)
    off_pts = [(x, y, yaw) for (_, x, y, yaw) in off["colored"]] + [(x, y, yaw) for (_, x, y, yaw) in off["distractors"]]
    maxdiff = max(max(abs(a[1] - b[0]), abs(a[2] - b[1]), abs(a[3] - b[2])) for a, b in zip(acc, off_pts)) if len(acc) == 6 else None
    tgt = off_pts[off["target_idx"]]
    steps = None
    try:
        h5s = sorted((out / "hdf5_files").glob(f"*seed{seed}*.h5")) or sorted(out.rglob(f"*{seed}*.h5"))
        if h5s:
            with h5py.File(h5s[-1], "r") as h:
                g = h[f"episode_{job.episode}"]
                steps = sum(1 for k in g.keys() if k.startswith("timestep_"))
    except Exception as e:
        steps = f"err:{e}"
    row = {"hw": hw, "seed": seed, "ok": bool(res.get("ok")), "failure_class": res.get("failure_class"),
           "error_type": res.get("error_type"), "error": (res.get("error") or "")[:400],
           "wall_s": round(time.time() - t, 1), "timestep_count": (res.get("video") or {}).get("timestep_count") if isinstance(res.get("video"), dict) else None,
           "h5_steps": steps, "phases": res.get("phases"),
           "layout_vs_offline_maxabs": maxdiff, "n_cubes_placed": len(acc), "trials": [a[4] for a in acc],
           "target_xy": [round(tgt[0], 4), round(tgt[1], 4)], "target_reach": round(math.dist(tgt[:2], BASE), 4),
           "max_cube_reach": round(max(math.dist(p[:2], BASE) for p in off_pts), 4),
           "goal_xy": [round(v, 4) for v in off["goal"]]}
    with (out / "summary.jsonl").open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"DEMOP1 hw={hw} seed={seed} ok={row['ok']} cls={row['failure_class']} {row['error_type'] or ''} "
          f"steps={row['timestep_count']}/{row['h5_steps']} tgt_reach={row['target_reach']} layout_diff={maxdiff} "
          f"{row['error'][:160]} {row['wall_s']}s", flush=True)
print("DEMOP1_DONE", flush=True)
