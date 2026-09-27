"""本机演示探针：先进程内打 V5 补丁（R=0.05，计划口径杆段），再走 generate_dataset_newseed._worker 同一入口。
用法：demo_r2.py <out_dir> <seed,seed,...> [R]；R=0 为对照组（去掉 corner_bias、执行段不避让，但不设禁区）"""
import json, sys, time
from pathlib import Path
WT = Path("/data/hongzefu/robomme_v5_probe_wt")
D = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v5/plan-probes-r2/movecube_circle"
sys.path.insert(0, str(WT / "scripts")); sys.path.insert(0, str(WT / "src")); sys.path.insert(0, D)
import generate_dataset_newseed as gen
gen._pool_init("1", None, str(WT / "src"))
from patch_r2 import apply_patch
RR = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
apply_patch(R=RR)
from mc_v5 import simulate
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
seeds = [int(s) for s in sys.argv[2].split(",")]
names = ["peg_push", "gripper_push", "grasp_putdown"]
for i, seed in enumerate(seeds):
    m = simulate(seed, bias=0.0, R=RR)
    job = gen.EpisodeJob(task="MoveCube", episode=i, attempt=0, seed=seed, difficulty="xhard",
                         output_root=str(out), repo_root=str(WT), sampling_config=None)
    t = time.time()
    res = gen._worker(job)
    row = {"R": RR, "seed": seed, "way": names[m.way_idx_run], "way_init0": names[m.way_idx], "model_redraw": sum(m.rej.values()), "ok": bool(res.get("ok")),
           "failure_class": res.get("failure_class"), "error_type": res.get("error_type"),
           "error": (res.get("error") or "")[:300], "timestep_count": res.get("timestep_count"), "wall_s": round(time.time() - t, 1)}
    with (out / "summary.jsonl").open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"DEMOR2 seed={seed} way={row['way']} ok={row['ok']} steps={row['timestep_count']} {row['failure_class'] or ''} {row['error_type'] or ''} {row['error'][:160]} {row['wall_s']}s", flush=True)
print("DEMOR2_DONE")
