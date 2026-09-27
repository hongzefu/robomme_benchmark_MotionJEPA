import h5py, json, numpy as np, cv2, os, re
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
specs={}
for t in ['xhard1','xhard2','xhard3','xhard4']:
    for line in open(f'{ROOT}/artifacts/newtask-v6/v6-01/{t}/specs.jsonl'):
        d=json.loads(line)
        if d.get('task')=='VideoUnmaskSwap' and d.get('record')=='spec': specs[(t,d['seed'])]=d['spec']
names=['red','green','blue']
def blob(im,col):
    im=im.astype(int); r,g,b=im[...,0],im[...,1],im[...,2]
    m={'red':(r>90)&(g<60)&(b<60),'green':(g>90)&(r<60)&(b<60),'blue':(b>90)&(r<60)&(g<60)}[col]
    n,lab,st,cen=cv2.connectedComponentsWithStats(m.astype(np.uint8),8)
    c=[(st[i][4],cen[i]) for i in range(1,n) if st[i][4]>=6]
    return None if not c else max(c,key=lambda x:x[0])[1]
def proj(g,t,xyz):
    gi=g[f'timestep_{t}']; ext=gi['obs/front_camera_extrinsic'][()]; K=g['setup/front_camera_intrinsic'][()]
    pc=ext[:,:3]@np.array(xyz)+ext[:,3]; uv=K@pc; return uv[:2]/uv[2]
out=[]
for r in json.load(open(E+'/raw_extract.json')):
    sp=specs.get((r['tier'],r['seed']))
    if not sp: continue
    rep_path=os.path.join(os.path.dirname(os.path.dirname(r['h5'])),'spec_replay.json')
    rep=json.load(open(rep_path))
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    o=sp['objects']; bins={int(k):v[:2] for k,v in sp['layout']['bins'].items()}
    cols=[names[j] for j in o['color_order']]
    color_bin={cols[i]:o['selected'][i] for i in range(3)}
    pos=dict(bins)
    z=0.0167
    init_err={c:float(np.linalg.norm(proj(g,5,[*pos[b],z])-blob(g['timestep_5']['obs/front_rgb'][()],c))) for c,b in color_bin.items()}
    sw=sp['actions']['swap_pairs']
    for k in range(o['n_swaps']):
        a=int(sw[str(k)]['initiator'].split('_')[1]); b=int(sw[str(k)]['partner'].split('_')[1])
        pos[a],pos[b]=pos[b],pos[a]
    pick_err={}
    for sg in r['segments']:
        if not sg['simple'].startswith('pick up'): continue
        c=re.search(r'hides the (\w+) cube',sg['simple']).group(1)
        t=sg['end']; bl=blob(g[f'timestep_{t}']['obs/front_rgb'][()],c)
        pick_err[c]=dict(step=t,expected_px=[round(float(x),1) for x in proj(g,t,[*pos[color_bin[c]],z])],observed_px=None if bl is None else [round(float(x),1) for x in bl],
                         err=None if bl is None else round(float(np.linalg.norm(proj(g,t,[*pos[color_bin[c]],z])-bl)),2))
        # also nearest other final slot distance to show discrimination
        others=[float(np.linalg.norm(proj(g,t,[*pos[bb],z])-bl)) for bb in pos if bb!=color_bin[c]] if bl is not None else []
        pick_err[c]['nearest_other_slot_px']=round(min(others),1) if others else None
    res=dict(tier=r['tier'],seed=r['seed'],spec_replay_mismatches=rep.get('mismatches'),init_proj_err_px={k:round(v,2) for k,v in init_err.items()},picks=pick_err)
    out.append(res); print(json.dumps(res))
json.dump(out,open(E+'/track_check.json','w'),indent=1)
