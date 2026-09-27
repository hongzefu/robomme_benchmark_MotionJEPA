import h5py,json,numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/InsertPeg'
recs=json.load(open(E+'/records.json'))
out={}
for r in recs:
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    red=[]
    for t in range(r['n_steps']):
        im=g[f'timestep_{t}/obs/front_rgb'][()].astype(int)
        m=(im[...,0]>180)&(im[...,1]<60)&(im[...,2]<60)
        red.append(int(m.sum()))
    red=np.array(red); on=np.where(red>=4)[0]
    runs=[]
    for t in on:
        if runs and t==runs[-1][1]+1: runs[-1][1]=int(t)
        else: runs.append([int(t),int(t)])
    out[f"{r['difficulty']}_ep{r['episode']}"]=dict(runs=runs,last_demo=r['last_demo_step'],n=r['n_steps'],insert_seg_demo=[s for s in r['segments'] if s['demo']][-1]['start'],exec_done=[s for s in r['segments'] if s['simple']=='All tasks completed'][0]['start'])
    print(r['difficulty'],r['episode'],out[f"{r['difficulty']}_ep{r['episode']}"])
json.dump(out,open(E+'/red_highlight_runs.json','w'),indent=1)
