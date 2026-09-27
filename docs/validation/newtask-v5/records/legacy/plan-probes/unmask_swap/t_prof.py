import sys, time, cProfile, pstats
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap")
import m2_outer_sim as m
from replica import vus_layout, distractors_from_repo
t=time.perf_counter(); lay=vus_layout(9100000); d=distractors_from_repo(lay); print("repo sample_distractors s", time.perf_counter()-t, flush=True)
cProfile.run("m.run_episode(('VideoUnmaskSwap', 9100000, 'v4', 3, 'rot3', 0.07))", "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap/prof.out")
p=pstats.Stats("/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap/prof.out"); p.sort_stats("cumulative").print_stats(18)
