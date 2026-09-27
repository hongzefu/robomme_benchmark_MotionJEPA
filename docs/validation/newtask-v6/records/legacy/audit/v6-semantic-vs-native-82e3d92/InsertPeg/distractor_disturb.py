import h5py,json,numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/InsertPeg'
recs=json.load(open(E+'/records.json')); out={}
for r in recs:
    if 'pegs' not in r: continue
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    im0=g['timestep_0/obs/front_rgb'][()].astype(int)
    res={}
    for p in r['pegs'][1:]:
        cu=(p['head_uv'][0]+p['tail_uv'][0])/2; cv=(p['head_uv'][1]+p['tail_uv'][1])/2
        u0,v0=int(cu)-6,int(cv)-6
        series=[]
        for t in [r['demo_close_step'],r['last_demo_step'],r['exec_start_step'],r['exec_close_step'],r['n_steps']-1]:
            im=g[f'timestep_{t}/obs/front_rgb'][()].astype(int)
            series.append((t,round(float(np.abs(im[v0:v0+13,u0:u0+13]-im0[v0:v0+13,u0:u0+13]).mean()),2)))
        res[f"peg{p['k']}"]=series
    out[f"{r['difficulty']}_ep{r['episode']}"]=res; print(r['episode'],res)
json.dump(out,open(E+'/distractor_patch_diff.json','w'),indent=1)
