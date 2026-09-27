import sys, time
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap")
from replica import *
from robomme.robomme_env.utils.bin_collision import check_swap_sweep
lay = layout_from_spec(load_spec_rows("VideoUnmaskSwap")[0])
for k,(a,b,d,pos,yaw) in enumerate(inner_sequence(lay)[:3]):
    sa=bin_state(f"bin_{a}",*pos[a],yaw[a]); sb=bin_state(f"bin_{b}",*pos[b],yaw[b])
    by=[bin_state(f"bin_{j}",*pos[j],yaw[j]) for j in range(4) if j not in (a,b)]
    by+=[bin_state(f"d{j}",x,y,w) for j,(x,y,w) in enumerate(lay["distractors"])]
    t=time.perf_counter(); g,r=check_swap_sweep(sa,sb,by); dt=time.perf_counter()-t
    print(k,a,b,round(d,4),g,r is None, f"{dt:.2f}s", flush=True)
