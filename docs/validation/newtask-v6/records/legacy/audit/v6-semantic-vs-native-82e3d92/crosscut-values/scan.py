"""只读扫描165新档+144原档HDF5：setup、子目标边界序列、步数。"""
import h5py, json, glob, os, re, sys
from concurrent.futures import ProcessPoolExecutor
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts'
def dec(v):
    v=v[()] if hasattr(v,'shape') else v
    if isinstance(v,bytes): return v.decode()
    if hasattr(v,'tolist'): return [x.decode() if isinstance(x,bytes) else x for x in v.tolist()] if v.ndim else v.item()
    return v
def scan(args):
    task,tier_hint,ep,h5,mp4=args
    out=dict(task=task,tier_hint=tier_hint,episode=ep,h5=h5,mp4=mp4)
    with h5py.File(h5,'r') as f:
        g=f[list(f.keys())[0]]
        s=g['setup']
        out['setup']={k:dec(s[k]) for k in s.keys() if 'intrinsic' not in k}
        ts=sorted((int(k.split('_')[1]) for k in g if k.startswith('timestep_')))
        out['n_steps']=len(ts)
        b=[];demo=0;choices=[]
        for t in ts:
            info=g[f'timestep_{t}']['info']
            d=bool(info['is_video_demo'][()]); demo+=d
            if bool(info['is_subgoal_boundary'][()]):
                b.append(dict(t=t,demo=d,s=dec(info['simple_subgoal']),so=dec(info['simple_subgoal_online']),g=dec(info['grounded_subgoal']),go=dec(info['grounded_subgoal_online'])))
                try: choices.append(dict(t=t,c=dec(g[f'timestep_{t}']['action']['choice_action'])))
                except Exception: pass
        out['n_demo']=demo; out['boundaries']=b; out['choices']=choices
        last=g[f'timestep_{ts[-1]}']['info']
        out['last_completed']=bool(last['is_completed'][()])
    return out
def main():
    jobs=[]
    idx=json.load(open(f'{ROOT}/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))
    for t,rows in idx.items():
        for r in rows: jobs.append((t,r['difficulty'],r['episode'],r['h5'],r['mp4'][0]))
    for d in sorted(glob.glob(f'{ROOT}/newtask-v6/v1/base/B/*_episode_*')):
        name=os.path.basename(d); task,ep=re.match(r'(\w+)_episode_(\d+)',name).groups()
        for h5 in sorted(glob.glob(d+'/hdf5_files/*.h5')):
            mp4s=sorted(glob.glob(d+'/videos/*.mp4'))
            m=re.search(r'_(easy|medium|hard)_', os.path.basename(mp4s[0])) if mp4s else None
            jobs.append((task,m.group(1) if m else None,int(ep),h5,mp4s[0] if mp4s else None))
    with ProcessPoolExecutor(16) as ex: res=list(ex.map(scan,jobs))
    json.dump(res,open(sys.argv[1],'w'),indent=0)
    print(len(res))
main()
