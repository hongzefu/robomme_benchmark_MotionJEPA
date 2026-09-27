"""核对计划 2.13「约 1%（256 次 3.5%）」口径：各变体 3000 局 reset 失败率。"""
import sys
from pathlib import Path
from multiprocessing import Pool
sys.path.insert(0, str(Path(__file__).parent))
from offline_p1 import v5_layout, SEED0
V = {"uniform_exact_8cm_256": dict(max_trials=256), "uniform_exact_8cm_1024": dict(),
     "cb0.5_exact_8cm_256": dict(corner_bias=0.5, max_trials=256), "cb0.5_exact_8cm_1024": dict(corner_bias=0.5),
     "uniform_trimesh_8cm_256": dict(obb_mode="trimesh", max_trials=256),
     "hw0.25_uniform_exact_8cm_256": dict(cube_half=0.25, max_trials=256)}
def run(a):
    n, s = a; return n, "fail" in v5_layout(s, **V[n])
if __name__ == "__main__":
    with Pool(24) as p:
        r = p.map(run, [(n, SEED0 + i) for n in V for i in range(3000)], chunksize=25)
    for n in V:
        f = sum(x for (m, x) in r if m == n); print(f"{n}: fail={f}/3000 = {f/3000:.4f}")
