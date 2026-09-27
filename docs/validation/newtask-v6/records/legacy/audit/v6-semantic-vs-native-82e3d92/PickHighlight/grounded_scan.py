import h5py,json,re,glob
R=json.load(open(__file__.rsplit('/',1)[0]+'/records_raw.json'))
out={}
for r in R:
    f=h5py.File(r['h5'],'r'); ep=f[list(f.keys())[0]]
    T=r['frames']; noc=[];noc_on=[]
    for t in range(T):
        g=ep[f'timestep_{t}/info']
        s=g['simple_subgoal'][()].decode(); gs=g['grounded_subgoal'][()].decode(); go=g['grounded_subgoal_online'][()].decode()
        if 'pick up' in s:
            if '<' not in gs: noc.append(t)
            if '<' not in go: noc_on.append(t)
    def runs(xs):
        o=[]
        for x in xs:
            if o and x==o[-1][1]+1: o[-1][1]=x
            else: o.append([x,x])
        return o
    key=f"{r['kind']}/{r['difficulty']}/ep{r['episode']}"
    out[key]={'grounded_no_coord_runs':runs(noc),'online_no_coord_runs':runs(noc_on)}
    print(key,out[key])
json.dump(out,open(__file__.rsplit('/',1)[0]+'/grounded_scan.json','w'),indent=1)
