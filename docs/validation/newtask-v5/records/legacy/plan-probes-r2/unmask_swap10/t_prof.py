import sys, time; sys.path.insert(0, sys.argv[1])
import offline_joint as O, swap10lib as L
from replica import vus_layout
from robomme.robomme_env.utils.unmask_swap_xhard import distractor_generator
lay = vus_layout(9100000); seq, obbs = O.inputs_from_replica(lay)
t=time.perf_counter(); print("prejudge", L.inner_prejudge(seq), time.perf_counter()-t)
import cProfile, pstats
cProfile.run("L.plan_episode(distractor_generator(9100000), obbs, seq, [])", "/tmp/claude-114466650/p5prof.out")
pstats.Stats("/tmp/claude-114466650/p5prof.out").sort_stats("cumtime").print_stats(14)
print(L.STATS)
