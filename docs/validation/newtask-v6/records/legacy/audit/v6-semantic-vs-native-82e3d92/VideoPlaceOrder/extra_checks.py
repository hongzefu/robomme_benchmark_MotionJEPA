import h5py, json, numpy as np, re, sys
sys.path.insert(0,'/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoPlaceOrder')
from analyze_lib import cube_pos, dist
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoPlaceOrder'
R=json.load(open(f'{E}/records.json'))
for r in R:
    f=h5py.File(r['h5'],'r'); g=f[[k for k in f.keys() if k.startswith('episode_')][0]]
    im=lambda t: g[f'timestep_{t}/obs/front_rgb'][()]
    visits=[[v['target_idx_t0'] for v in b['visits']] for b in r['demo_blocks']]
    c2t=[[v['cube_to_target_px'] for v in b['visits']] for b in r['demo_blocks']]
    s0=r['swap'].get('swap_start'); tex=r['first_exec_step']
    shift={}
    if s0:
        for c in ('red','green','blue'):
            a=cube_pos(im(s0-2),c); b=cube_pos(im(tex),c)
            if a and b: shift[c]=round(dist(a,b),1)
    # ambiguity: does the other demo cube share the answer target
    r['extra']=dict(visit_target_idx=visits,cube_to_target_px=c2t,unique_per_cube=[len(set(v))==len(v) for v in visits],cube_shift_across_swap_px=shift)
    print(r['tier'],r['episode'],'visits',visits,'c2t',c2t,'uniq',r['extra']['unique_per_cube'],'swapshift',shift)
json.dump(R,open(f'{E}/records.json','w'),indent=1,default=str)
