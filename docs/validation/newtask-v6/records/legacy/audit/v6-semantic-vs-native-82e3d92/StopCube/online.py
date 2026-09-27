import h5py,json
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/StopCube'
out={}
for r in json.load(open(E+'/_raw_extract.json')):
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    segs=[];prev=None
    for t in range(r['n_steps']):
        i=g[f'timestep_{t}/info']
        k=(i['simple_subgoal_online'][()].decode(),i['grounded_subgoal_online'][()].decode())
        if k!=prev: segs.append([t,*k]); prev=k
    out[f"{r['tier']}_ep{r['episode']}"]=segs
    print(r['tier'],r['episode'],[(s[0],s[1][:40]) for s in segs])
json.dump(out,open(E+'/_online_segments.json','w'),indent=1)
