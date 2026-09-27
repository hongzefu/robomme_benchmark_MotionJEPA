import h5py, json, collections
R=json.load(open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill/records.json'))
want={('xhard3',0):'fifth blue',('xhard3',3):'press the button',('xhard4',0):'fourth blue'}
for r in R:
    k=(r['difficulty'],r['episode'])
    if k not in want: continue
    f=h5py.File(r['h5'],'r'); e=f[list(f.keys())[0]]
    c=collections.Counter()
    for t in range(r['n_steps']):
        s=e[f'timestep_{t}/info/grounded_subgoal'][()].decode()
        if want[k] in s: c[s]+=1
    print(k,dict(c))
    c2=collections.Counter()
    for t in range(r['n_steps']):
        s=e[f'timestep_{t}/info/grounded_subgoal_online'][()].decode()
        if want[k] in s: c2[s]+=1
    print('  online',dict(c2))
