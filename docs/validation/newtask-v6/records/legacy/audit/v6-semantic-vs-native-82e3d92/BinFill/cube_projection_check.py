"""Project every spawned cube (from rng_trace layout.cubes.*) into front camera at t0 and last frame; sample colour.
Also recompute max same-colour component (link 0.09 m) independently."""
import json, h5py, numpy as np
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill'
R=json.load(open(ROOT+'/records.json'))
CH={'red':0,'green':1,'blue':2}
def col(rgb,u,v,r=2):
    p=rgb[max(0,v-r):v+r+1,max(0,u-r):u+r+1].reshape(-1,3).astype(float); best,bn='none',0
    for c,ch in CH.items():
        o=np.max(p[:,[k for k in range(3) if k!=ch]],axis=1); n=int(((p[:,ch]>60)&(p[:,ch]>o*2.5)).sum())
        if n>bn: best,bn=c,n
    return best
def comp(xy,lab,link):
    n=len(xy); d=np.linalg.norm(xy[:,None]-xy[None],axis=-1); seen=[0]*n; best=0
    for s in range(n):
        if seen[s]: continue
        seen[s]=1; st=[s]; sz=0
        while st:
            u=st.pop(); sz+=1
            for v in range(n):
                if not seen[v] and lab[v]==lab[u] and d[u,v]<=link: seen[v]=1; st.append(v)
        best=max(best,sz)
    return best
out=[]
for r in R:
    if r['kind']!='new': continue
    f=h5py.File(r['h5'],'r'); e=f[list(f.keys())[0]]; K=e['setup/front_camera_intrinsic'][()]
    cubes=r['trace']['cubes']; names=list(cubes)
    xy=np.array([cubes[k][:2] for k in names]); lab=[k.split('_')[0] for k in names]
    res=dict(diff=r['difficulty'],ep=r['episode'],n_cubes=len(names),max_component_recomputed=comp(xy,lab,0.09))
    for tag,t in [('t0',0),('last',r['n_steps']-1)]:
        rgb=e[f'timestep_{t}/obs/front_rgb'][()]; ext=e[f'timestep_{t}/obs/front_camera_extrinsic'][()]
        seen={}
        for k in names:
            w=np.array([cubes[k][0],cubes[k][1],0.02]); c=ext[:,:3]@w+ext[:,3]; uv=K@c; u,v=int(round(uv[0]/uv[2])),int(round(uv[1]/uv[2]))
            seen[k]=col(rgb,u,v)
        res[tag+'_colour_at_cube']=seen
        res[tag+'_match']=sum(seen[k]==k.split('_')[0] for k in names)
    # expected remaining per colour at last frame
    tgt=r['trace']['objects.target_numbers']; sp=r['trace']['objects.spawn_numbers']
    res['expected_remaining']=dict(red=sp[0]-tgt[0],blue=sp[1]-tgt[1],green=sp[2]-tgt[2])
    rem={c:0 for c in CH}
    for k,v in res['last_colour_at_cube'].items():
        if v==k.split('_')[0]: rem[v]+=1
    res['observed_remaining_at_original_pos']=rem
    out.append(res)
    print(res['diff'],res['ep'],'n',res['n_cubes'],'comp',res['max_component_recomputed'],'t0 match',res['t0_match'],'exp rem',res['expected_remaining'],'obs rem',rem)
json.dump(out,open(ROOT+'/cube_projection_check.json','w'),indent=1)
