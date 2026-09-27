"""M0b：scratch 版 sample_ring（v4 环、count=3、fast 圆判据预筛）与仓库 sample_distractors 逐值一致性核对。"""
import sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from replica import bus_layout, vus_layout, inner_sequence, distractors_from_repo, load_spec_rows
from ring_sampler import V4_RING, sample_ring, state, RADIUS
from robomme.robomme_env.utils import unmask_swap_xhard as ux
BTN = float(np.linalg.norm([0.05625, 0.05625]))
ok = tot = 0; t_fast = t_repo = 0.0
seeds = [(r["task"], r["seed"]) for r in load_spec_rows() if r["task"] in ("VideoUnmaskSwap", "ButtonUnmaskSwap")]
seeds += [("VideoUnmaskSwap", 9_100_000 + i) for i in range(10)] + [("ButtonUnmaskSwap", 9_300_000 + i) for i in range(10)]
for task, seed in seeds:
    lay = (vus_layout if task == "VideoUnmaskSwap" else bus_layout)(seed)
    sweeps = [(state(f"bin_{a}", *pos[a], yaw[a]), state(f"bin_{b}", *pos[b], yaw[b])) for a, b, _d, pos, yaw in inner_sequence(lay)]
    obstacles = [((b[0], b[1]), RADIUS) for b in lay["bins"]] + [((bx, by), BTN) for bx, by in lay["buttons"]]
    t = time.perf_counter(); fast = sample_ring(ux.distractor_generator(seed), ring=V4_RING, count=3, obstacles=obstacles, sweeps=sweeps); t_fast += time.perf_counter() - t
    t = time.perf_counter(); repo, _ = distractors_from_repo(lay); t_repo += time.perf_counter() - t
    same = fast is not None and np.allclose(np.array(fast), np.array(repo), atol=0, rtol=0)
    ok += same; tot += 1
print(f"RING_SAMPLER_MATCH ok={ok}/{tot} t_fast_total={t_fast:.1f}s t_repo_total={t_repo:.1f}s (repo sample_distractors mean {t_repo/tot:.2f}s/reset)")
