import h5py, json
R=json.load(open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill/records.json'))
out=[]
for r in R:
    f=h5py.File(r['h5'],'r'); e=f[list(f.keys())[0]]
    for s in r['segments']:
        g=[e[f'timestep_{t}/info/grounded_subgoal_online'][()].decode() for t in range(s['start'],s['end']+1)]
        go=[e[f'timestep_{t}/info/grounded_subgoal'][()].decode() for t in range(s['start'],s['end']+1)]
        nc=sum('<' not in x for x in g)
        if nc:
            first=next((i for i,x in enumerate(g) if '<' in x),None)
            item=dict(diff=r['difficulty'],ep=r['episode'],start=s['start'],end=s['end'],simple=s['simple'],steps_without_coord=nc,first_coord_step=None if first is None else s['start']+first,
                      later_text=g[first] if first is not None else None, offline_nocoord=sum('<' not in x for x in go))
            out.append(item); print(item)
print('total',len(out))
json.dump(out,open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill/nocoord_scan.json','w'),indent=1)
