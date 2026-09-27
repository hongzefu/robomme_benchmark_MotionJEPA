# 仿真验证 V5「最小方案」（进程内 monkeypatch，不落盘改仓库）：
#   ① 摆放加中心距硬下限 DMIN（用哨兵障碍把 _obb2d_intersect 变成圆盘判据，随机流协议与 spawn_random_cube 一致）
#   ② 发起者 = 目标 + 其余 5 块的完整 randperm，第 k 次用 swap_indices[k % 6]（randperm 调用不变，只是不截断）
#   ③ 搭档仍是运行时 XY 最近邻（V4 原逻辑）
import sys, os, json, time
from pathlib import Path
REPO = Path("/data/hongzefu/robomme_benchmark_MotionJEPANewTask"); HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, str(REPO / "src")); sys.path.insert(0, str(HERE))
import generate_dataset_newseed as gen
gen._pool_init("1", None, str(REPO / "src"))
import numpy as np, torch
import robomme.robomme_env.utils.object_generation as og
from robomme.robomme_env.utils.xhard import hsv_floor_rgb
from robomme.robomme_env.VideoRepick import VideoRepick
from robomme.robomme_env.utils.SceneGenerationError import SceneGenerationError  # 真类（VideoRepick 模块里同名符号被 from .utils import * 遮蔽成子模块）
DMIN = float(os.environ.get("DMIN", "0.12"))
_orig_int = og._obb2d_intersect
def _int(c1, A1, h1, c2, A2, h2):
    if h1[0] < 0:  # 哨兵：圆盘判据（中心距 < DMIN 即「相交」）
        return float(np.linalg.norm(np.asarray(c2) - np.asarray(c1))) < h1[1]
    return _orig_int(c1, A1, h1, c2, A2, h2)
og._obb2d_intersect = _int

def v5_load(self, avoid):
    xhard_cfg = self._sampling["decision"]["xhard"]; layout = xhard_cfg["layout"]
    region_cfg = self._sampling["positions"]["hard_cubes"]
    u = torch.rand(3, generator=self.generator).tolist()
    rgb = self._spec.value("objects.color_rgb", hsv_floor_rgb(u, xhard_cfg["block_color"]), decision_key="xhard.block_color")
    color = (float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0)
    n = int(layout["cube_count"]); self.spawned_cubes = []
    for i in range(n):
        try:
            cube = og.spawn_random_cube(self, avoid=avoid, region_center=list(layout["region_center"]),
                region_half_size=list(layout["region_half_size"]), min_gap=self.cube_half_size, half_size=self.cube_half_size,
                name_prefix=f"bin_{i}", max_trials=256, color=color, random_yaw=region_cfg["random_yaw"],
                include_existing=region_cfg["include_existing"], include_goal=region_cfg["include_goal"],
                generator=self.generator, recorder=self._spec, spec_path=f"layout.cubes.{i}.xy_yaw")
        except RuntimeError as e:
            raise SceneGenerationError(f"v5: failed bin_{i}") from e
        self.spawned_cubes.append(cube); setattr(self, f"bin_{i}", cube); avoid.append(cube)
        p = self._get_actor_position(cube)
        avoid.append((np.array([p[0], p[1]], dtype=np.float64), np.eye(2), np.array([-1.0, DMIN])))
    self._spec.record("objects.cube_count.requested", n); self._spec.record("objects.cube_count.actual", len(self.spawned_cubes))
    target = self._spec.value("objects.target", int(torch.randint(0, n, (1,), generator=self.generator).item()))
    self.target_cube_1 = self.spawned_cubes[target]
    remaining = [i for i in range(n) if i != target]
    perm = self._spec.value("objects.swap_initiators_remaining", torch.randperm(len(remaining), generator=self.generator).tolist())
    swap_indices = [target] + [remaining[i] for i in perm]
    self._spec.record("objects.swap_initiators", [f"bin_{i}" for i in swap_indices])
    for k in range(self.swap_times):
        setattr(self, f"swap_pair{k+1}_idx1", self.spawned_cubes[swap_indices[k % n]]); setattr(self, f"swap_pair{k+1}_idx2", None)
    self._refresh_swap_schedule()
VideoRepick._load_cubes_xhard = v5_load

LOG = []
_orig = VideoRepick._check_swap_sweep_from_actual
def patched(self, sweep_index, initiator, partner):
    poses = [[float(v) for v in self._get_actor_position(a)[:2]] for a in self.spawned_cubes]
    rec = {"seed": int(self.seed), "sweep_index": int(sweep_index), "a": self.spawned_cubes.index(initiator),
           "b": self.spawned_cubes.index(partner), "poses": poses, "target": self.spawned_cubes.index(self.target_cube_1)}
    try:
        _orig(self, sweep_index, initiator, partner); rec["rejected"] = False
    except Exception as exc:
        rec["rejected"] = True; LOG.append(rec); raise
    LOG.append(rec)
VideoRepick._check_swap_sweep_from_actual = patched
out = HERE / "demo_out_v5"; out.mkdir(exist_ok=True)
tag = sys.argv[2]
for seed in [int(s) for s in sys.argv[1].split(",")]:
    job = gen.EpisodeJob(task="VideoRepick", episode=9, attempt=0, seed=seed, difficulty="xhard", output_root=str(out), repo_root=str(REPO), sampling_config=None)
    t0 = time.time(); res = gen._worker(job)
    print(f"seed={seed} ok={res.get('ok')} err={res.get('error_type')} {str(res.get('error'))[:120]} wall={time.time()-t0:.0f}s", flush=True)
    LOG.append({"seed": seed, "episode_result": {"ok": bool(res.get("ok")), "error_type": res.get("error_type")}})
    for f in (out / "hdf5_files").glob(f"*seed{seed}*"):
        f.unlink()
    json.dump(LOG, open(HERE / f"demo_v5_log_{tag}.json", "w"))
print("全部完成")
