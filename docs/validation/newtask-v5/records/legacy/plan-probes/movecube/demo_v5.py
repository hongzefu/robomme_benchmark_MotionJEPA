"""本机演示探针（V5-b 猴补丁）：与 scripts/parity/v4_demo_probe.py 同一入口 generate_dataset_newseed._worker，
只是先在进程内打补丁；产物落 scratch。用法：demo_v5.py <out_dir> <seed,seed,...>"""
import json, sys, time
from pathlib import Path
REPO = Path("/data/hongzefu/robomme_benchmark_MotionJEPANewTask")
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/movecube")
import generate_dataset_newseed as gen
gen._pool_init("1", None, str(REPO / "src"))
from patch_v5 import apply_patch
mc = apply_patch()
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
seeds = [int(s) for s in sys.argv[2].split(",")]
names = ["peg_push", "gripper_push", "grasp_putdown"]
for seed in seeds:
    job = gen.EpisodeJob(task="MoveCube", episode=9, attempt=0, seed=seed, difficulty="xhard",
                         output_root=str(out), repo_root=str(REPO), sampling_config=None)
    t = time.time()
    res = gen._worker(job)
    row = {"seed": seed, "ok": bool(res.get("ok")), "failure_class": res.get("failure_class"),
           "error_type": res.get("error_type"), "error": (res.get("error") or "")[:300], "wall_s": round(time.time() - t, 1)}
    with (out / "summary.jsonl").open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"DEMOV5 seed={seed} ok={row['ok']} {row['failure_class'] or ''} {row['error_type'] or ''} {row['error'][:160]} {row['wall_s']}s", flush=True)
