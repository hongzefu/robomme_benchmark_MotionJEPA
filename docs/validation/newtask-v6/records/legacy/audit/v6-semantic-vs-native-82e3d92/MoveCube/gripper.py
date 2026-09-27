import h5py,json,numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube'
recs=json.load(open(E+'/records.json')); out={}
for r in recs:
    f=h5py.File(r['h5'],'r'); ep=f[list(f)[0]]
    bs=r['boundaries']
    res=[]
    for i,b in enumerate(bs):
        if b['simple'] in ('static','All tasks completed'): continue
        end=bs[i+1]['step'] if i+1<len(bs) else r['n_steps']
        g=[bool(ep[f'timestep_{k}/obs/is_gripper_close'][()]) for k in range(b['step'],end)]
        w=[float(np.mean(ep[f'timestep_{k}/obs/gripper_state'][()])) for k in (end-1,)]
        res.append(dict(seg=b['simple'][:30],demo=b['demo'],start=b['step'],end=end,closed_frac=round(float(np.mean(g)),3),first_closed=b['step']+g.index(True) if True in g else None,closed_at_end=g[-1],gripper_state_end=round(w[0],4)))
    out[r['tag']]=res
    print(r['tag'],r['way'],[(x['seg'][:18],x['demo'],x['closed_frac'],x['closed_at_end'],x['gripper_state_end']) for x in res])
json.dump(out,open(E+'/gripper_state_by_segment.json','w'),indent=1)
