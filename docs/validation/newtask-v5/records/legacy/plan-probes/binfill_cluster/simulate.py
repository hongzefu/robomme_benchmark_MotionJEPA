# 用逐位复刻的采样器批量生成 V4 xhard BinFill 布局（纯 CPU，不进仿真器）
# 用法：simulate.py <n> <seed_offset> <exact 1|0> <out.pkl>
import sys, time, pickle, torch
sys.path.insert(0, '/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster')
from binfill_sampler import sample_layout, placed_cube_obb, obb_is_degenerate
torch.set_num_threads(1)
n=int(sys.argv[1]); off=int(sys.argv[2]); exact=bool(int(sys.argv[3])); out=sys.argv[4]
t0=time.time(); res=[]; fails=0; degen=0; tot=0
for i in range(n):
    L=sample_layout(off+i, exact=exact, return_trials=True)
    if L is None:
        fails+=1; res.append(None); continue
    if exact:
        for c in L['cubes']:
            d=obb_is_degenerate(placed_cube_obb(c['x'],c['y'],c['yaw'],exact=True)); c['degenerate']=d; degen+=d; tot+=1
    res.append(L)
    if (i+1)%500==0: print(f'{i+1}/{n} {time.time()-t0:.0f}s fails={fails}', flush=True)
pickle.dump(res, open(out,'wb'))
print(f'SIM_DONE n={n} exact={exact} fails={fails} degenerate_obb={degen}/{tot} wall={time.time()-t0:.0f}s')
