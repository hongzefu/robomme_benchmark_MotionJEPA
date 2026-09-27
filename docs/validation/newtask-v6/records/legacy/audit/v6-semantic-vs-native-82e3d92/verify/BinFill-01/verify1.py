import h5py, json
R=json.load(open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill/records.json'))
want={('xhard3',0):(698,827,'fifth blue'),('xhard3',3):(1344,1478,'button'),('xhard4',0):(498,632,'fourth blue')}
for r in R:
    k=(r['difficulty'],r['episode'])
    if k not in want: continue
    lo,hi,tag = want[k]
    f=h5py.File(r['h5'],'r'); e=f[list(f.keys())[0]]
    online=[e[f'timestep_{t}/info/grounded_subgoal_online'][()].decode() for t in range(lo,hi+1)]
    offline=[e[f'timestep_{t}/info/grounded_subgoal'][()].decode() for t in range(lo,hi+1)]
    n_online_coord = sum('<' in x for x in online)
    n_offline_coord = sum('<' in x for x in offline)
    print(k, 'h5=',r['h5'])
    print('  n_steps_segment=', hi-lo+1)
    print('  online has coord count=', n_online_coord, 'sample online[0..3]=', online[:3])
    print('  offline has coord count=', n_offline_coord, 'sample offline[0..3]=', offline[:3])
    print('  unique online texts:', set(online))
