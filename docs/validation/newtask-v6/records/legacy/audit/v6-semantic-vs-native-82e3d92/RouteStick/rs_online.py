import json,h5py,collections
R=json.load(open('artifacts/audit/v6-semantic-vs-native-82e3d92/RouteStick/records_raw.json'))
out={}
for r in R:
    f=h5py.File(r['h5'],'r'); ep=f[next(iter(f))]; n=r['frames']
    runs=[]; prev=None
    for i in range(n):
        t=ep[f'timestep_{i}']
        key=tuple(t[k][()].decode() for k in ['info/simple_subgoal','info/grounded_subgoal','info/simple_subgoal_online','info/grounded_subgoal_online'])
        key=(bool(t['info/is_video_demo'][()]),)+key
        if key!=prev: runs.append([i]+list(key)); prev=key
    out[f"{r['tier']}_{r['episode']}"]=runs
    print(r['tier'],r['episode'],len(runs))
    for x in runs[:4]+runs[-3:]: print('   ',x[0],x[1],'|',x[2][:45],'|',x[3][:45],'|',x[4][:45],'|',x[5][:45])
json.dump(out,open('artifacts/audit/v6-semantic-vs-native-82e3d92/RouteStick/subgoal_runs.json','w'),indent=0)
