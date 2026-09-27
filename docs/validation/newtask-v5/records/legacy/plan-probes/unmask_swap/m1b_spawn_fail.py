"""M1b：内部 4 容器 spawn_random_bin 放不满（env 里 except RuntimeError: break 静默少一个）的频率（复刻，近似 OBB）。"""
import sys, collections
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap")
from replica import vus_layout, bus_layout
N = 2000
for name, fn, base in (("VideoUnmaskSwap", vus_layout, 9_100_000), ("ButtonUnmaskSwap", bus_layout, 9_300_000)):
    c = collections.Counter(len(fn(base + i)["bins"]) for i in range(N))
    print(f"{name} N={N} placed_bins={dict(sorted(c.items()))}", flush=True)
