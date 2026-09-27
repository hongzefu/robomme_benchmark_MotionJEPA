"""Read-only PatternLock HDF5 audit extractor (h5py/numpy/json only)."""
import json, glob, os, re
import h5py, numpy as np
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
E=ROOT+'/artifacts/audit/v6-semantic-vs-native-82e3d92/PatternLock'
idx=json.load(open(ROOT+'/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['PatternLock']
GRID={'easy':3,'medium':4,'hard':5,'xhard1':5,'xhard2':5,'xhard3':5,'xhard4':5}
LEN={'easy':[2,4],'medium':[3,5],'hard':[4,8],'xhard1':[9,12],'xhard2':[13,16],'xhard3':[17,20],'xhard4':[21,25]}
DIRV={"forward":(1,0),"backward":(-1,0),"left":(0,1),"right":(0,-1),"forward-left":(1,1),"forward-right":(1,-1),"backward-left":(-1,1),"backward-right":(-1,-1)}
def node_xy(n,g):
    r,c=divmod(n,g); rc=(g-1)/2
    return np.array([-0.1+(r-rc)*0.1,(c-rc)*0.1])
def dir_of(a,b,g):
    d=node_xy(b,g)-node_xy(a,g); d/=np.linalg.norm(d)
    return max(DIRV,key=lambda k: float(np.dot(d,np.array(DIRV[k],float)/np.linalg.norm(DIRV[k]))))
def s(x):
    x=x[()]; return x.decode() if isinstance(x,bytes) else x
eps=[]
for it in idx: eps.append(dict(tier=it['difficulty'],episode=it['episode'],seed=it['seed'],h5=it['h5'],mp4=it['mp4'][0],kind='new'))
for d in sorted(glob.glob(ROOT+'/artifacts/newtask-v6/v1/base/B/PatternLock_episode_*')):
    h=glob.glob(d+'/hdf5_files/*.h5')[0]; m=glob.glob(d+'/videos/*.mp4')
    tier=re.search(r'_seed\d+_(easy|medium|hard)_',os.path.basename(m[0])).group(1)
    eps.append(dict(tier=tier,episode=int(d.rsplit('_',1)[1]),seed=int(re.search(r'seed(\d+)',h).group(1)),h5=h,mp4=m[0],kind='native',n_mp4=len(m)))
out=[]
for e in eps:
    g=GRID[e['tier']]
    with h5py.File(e['h5'],'r') as f:
        ep=f[next(iter(f))]; su=ep['setup']
        e['setup_difficulty']=s(su['difficulty']); e['setup_seed']=int(su['seed'][()])
        e['task_goal']=[x.decode() for x in su['task_goal'][()]]
        e['choices']=[c['action'] for c in json.loads(s(su['available_multi_choices']))]
        n=sum(k.startswith('timestep_') for k in ep)
        xyz=[];demo=[];bnd=[];simple=[];grounded=[];comp=[];choice=[]
        for i in range(n):
            t=ep[f'timestep_{i}']
            xyz.append(t['obs/eef_state'][()][:3]); demo.append(bool(t['info/is_video_demo'][()]))
            bnd.append(bool(t['info/is_subgoal_boundary'][()])); comp.append(bool(t['info/is_completed'][()]))
            simple.append(s(t['info/simple_subgoal'])); grounded.append(s(t['info/grounded_subgoal']))
            choice.append(s(t['action/choice_action']))
    xyz=np.array(xyz); demo=np.array(demo)
    nodes_xy=np.array([node_xy(k,g) for k in range(g*g)])
    # contact detection mirrors is_obj_swing_onto: horiz<=0.01 and z<0.1 (eef_state used as TCP proxy)
    contacts=[]  # (step,node)
    for i,p in enumerate(xyz):
        dd=np.linalg.norm(nodes_xy-p[:2],axis=1); k=int(dd.argmin())
        if dd[k]<=0.01 and p[2]<0.1: contacts.append((i,k))
    def seq(part):
        sq=[];st=[]
        for i,k in contacts:
            if part(i) and (not sq or sq[-1]!=k): sq.append(k); st.append(i)
        return sq,st
    dn,dst=seq(lambda i: demo[i]); xn,xst=seq(lambda i: not demo[i])
    # subgoal segments
    segs=[]
    starts=[i for i in range(n) if bnd[i]]
    for j,a in enumerate(starts):
        b=starts[j+1] if j+1<len(starts) else n
        segs.append(dict(start=a,end=b,demo=bool(demo[a]),simple=simple[a],grounded=grounded[a],completed=comp[a],choice=choice[a]))
    # label changes (not only boundaries)
    changes=[(i,simple[i],bool(demo[i])) for i in range(n) if i==0 or simple[i]!=simple[i-1] or demo[i]!=demo[i-1]]
    exp_dirs=lambda sq:[dir_of(a,b,g) for a,b in zip(sq,sq[1:])]
    demo_len=int(demo.sum()); exec_len=int(n-demo_len)
    rec=dict(e, frames=n, demo_frames=demo_len, exec_frames=exec_len,
        demo_nodes=dn, demo_node_steps=dst, exec_nodes=xn, exec_node_steps=xst,
        n_nodes=len(dn), len_range=LEN[e['tier']], in_range=LEN[e['tier']][0]<=len(dn)<=LEN[e['tier']][1],
        demo_unique=len(set(dn))==len(dn), exec_equal_demo=dn==xn,
        adjacency_ok=all(max(abs(a//g-b//g),abs(a%g-b%g))==1 for a,b in zip(dn,dn[1:])),
        expected_dirs=exp_dirs(dn), exec_expected_dirs=exp_dirs(xn),
        demo_seg_labels=[x['simple'] for x in segs if x['demo']], exec_seg_labels=[x['simple'] for x in segs if not x['demo']],
        label_changes=changes, segments=segs,
        grounded_eq_simple=all(a==b for a,b in zip(simple,grounded)),
        z_min=float(xyz[:,2].min()), first_eef=xyz[0].tolist())
    rec['demo_labels_match_path']=rec['demo_seg_labels'][:len(rec['expected_dirs'])]==rec['expected_dirs']
    rec['exec_labels_match_path']=rec['exec_seg_labels'][:len(rec['exec_expected_dirs'])]==rec['exec_expected_dirs']
    out.append(rec)
json.dump(out,open(E+'/records_raw.json','w'),indent=1)
for r in out:
    print(r['kind'],r['tier'],r['episode'],r['seed'],'diff',r['setup_difficulty'],'frames',r['frames'],'demo',r['demo_frames'],'exec',r['exec_frames'],
      'N',r['n_nodes'],r['in_range'],'uniq',r['demo_unique'],'eq',r['exec_equal_demo'],'adj',r['adjacency_ok'],
      'dL',r['demo_labels_match_path'],len(r['demo_seg_labels']),'xL',r['exec_labels_match_path'],len(r['exec_seg_labels']),'gs',r['grounded_eq_simple'],'zmin',round(r['z_min'],3))
