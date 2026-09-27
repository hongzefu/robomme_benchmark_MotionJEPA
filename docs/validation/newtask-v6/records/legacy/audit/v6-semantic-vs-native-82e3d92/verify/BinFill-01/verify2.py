import h5py, json
R=json.load(open('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill/records.json'))
for r in R:
    if r['difficulty']=='xhard3' and r['episode']==0:
        segs=[s for s in r['segments'] if s['start']<=827 and s['end']>=698]
        for s in segs:
            print(s)
        f=h5py.File(r['h5'],'r'); e=f[list(f.keys())[0]]
        for t in [696,697,698,699,700,750,800,825,826,827,828,829]:
            og=e[f'timestep_{t}/info/grounded_subgoal'][()].decode()
            ol=e[f'timestep_{t}/info/grounded_subgoal_online'][()].decode()
            simple=e[f'timestep_{t}/info/simple_subgoal'][()].decode() if 'timestep_%d/info/simple_subgoal'%t in e else 'NA'
            print(t, 'offline=',og,'| online=',ol)
        break
