"""Read-only PickHighlight audit extractor (h5py/numpy/cv2/json only)."""
import h5py, json, numpy as np, cv2, glob, os, re
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
OUT=os.path.dirname(os.path.abspath(__file__))
idx=json.load(open(f'{ROOT}/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['PickHighlight']

def dec(x):
    x=x[()] if hasattr(x,'shape') else x
    if isinstance(x,bytes): return x.decode()
    if isinstance(x,np.ndarray): return [dec(i) for i in x]
    return x

def load_spec(tier,seed):
    for line in open(f'{ROOT}/artifacts/newtask-v6/v6-01/{tier}/specs.jsonl'):
        d=json.loads(line)
        if d.get('task')=='PickHighlight' and d.get('seed')==seed and d.get('record')=='spec': return d['spec']

def proj(K,Ex,p):
    c=Ex@np.array([p[0],p[1],p[2],1.0]); uv=K@c; return uv[0]/uv[2],uv[1]/uv[2]

def backproj(K,Ex,u,v,z=0.02):
    R=Ex[:,:3]; t=Ex[:,3]; C=-R.T@t; d=R.T@np.linalg.inv(K)@np.array([u,v,1.0])
    s=(z-C[2])/d[2]; return C+s*d

def is_white(px): return (px.min(-1)>195)&((px.max(-1).astype(int)-px.min(-1))<35)

def ring_white(img,K,Ex,xy,r,n=48):
    pts=[proj(K,Ex,(xy[0]+r*np.cos(a),xy[1]+r*np.sin(a),0.011)) for a in np.linspace(0,2*np.pi,n,endpoint=False)]
    vals=[]
    for u,v in pts:
        ui,vi=int(round(u)),int(round(v))
        if 0<=ui<256 and 0<=vi<256: vals.append(bool(is_white(img[vi,ui])))
    return float(np.mean(vals)) if vals else None

def read_ep(h5):
    f=h5py.File(h5,'r'); ep=f[list(f.keys())[0]]
    T=len([k for k in ep.keys() if k.startswith('timestep_')])
    setup={k:dec(ep['setup'][k]) for k in ['difficulty','seed','task_goal','available_multi_choices']}
    K=ep['setup/front_camera_intrinsic'][()]
    segs=[]; prev=None; closes=[]; pg=False; demo=[]
    for t in range(T):
        g=ep[f'timestep_{t}']
        s=dec(g['info/simple_subgoal']); gs=dec(g['info/grounded_subgoal']); b=bool(g['info/is_subgoal_boundary'][()])
        ca=dec(g['action/choice_action']); gc=bool(g['obs/is_gripper_close'][()])
        demo.append(bool(g['info/is_video_demo'][()]))
        if s!=prev or b:
            segs.append({'t':t,'simple':s,'grounded':gs,'boundary':b,'choice_action':ca})
            prev=s
        if gc and not pg:
            closes.append({'t':t,'eef':[float(x) for x in g['obs/eef_state'][()][:3]],'subgoal':s})
        pg=gc
    return f,ep,T,setup,K,segs,closes,demo

def best_highlight_frames(ep):
    return [ep[f'timestep_{t}/obs/front_rgb'][()] for t in range(10,101,5)], ep['timestep_50/obs/front_camera_extrinsic'][()]

def white_components(img,K,Ex,button_xy):
    m=is_white(img).astype(np.uint8)
    # mask out button region and top rows (robot base)
    bu,bv=proj(K,Ex,(button_xy[0],button_xy[1],0.0)) if button_xy is not None else (-99,-99)
    m[:40,:]=0
    if button_xy is not None: cv2.circle(m,(int(bu),int(bv)),14,0,-1)
    n,lab,stats,_=cv2.connectedComponentsWithStats(m,8)
    return [int(stats[i,cv2.CC_STAT_AREA]) for i in range(1,n) if stats[i,cv2.CC_STAT_AREA]>=15]

records=[]
# ---- new tiers
for e in idx:
    f,ep,T,setup,K,segs,closes,demo=read_ep(e['h5'])
    spec=load_spec(e['difficulty'],e['seed'])
    cubes={int(k):v for k,v in spec['layout']['cubes'].items()}
    hid=spec['objects']['highlight_ids']; bxy=spec['layout']['button_xy']
    frames,Ex=best_highlight_frames(ep)
    tgt=[]
    for i in hid:
        fr=[ring_white(im,K,Ex,cubes[i],0.042) for im in frames]
        tgt.append({'cube':i,'xy':cubes[i][:2],'uv':[round(x,1) for x in proj(K,Ex,(*cubes[i][:2],0.02))],'max_white_ring_frac_10_100':max(fr)})
    non=[]
    for i,c in cubes.items():
        if i in hid: continue
        d=min(np.hypot(c[0]-cubes[j][0],c[1]-cubes[j][1]) for j in hid)
        jn=min(hid,key=lambda j:np.hypot(c[0]-cubes[j][0],c[1]-cubes[j][1]))
        non.append({'cube':i,'xy':c[:2],'uv':[round(x,1) for x in proj(K,Ex,(*c[:2],0.02))],'nearest_target':jn,'center_dist_to_nearest_target_m':round(float(d),4)})
    # grasps
    gr=[]
    for c in closes:
        dists={i:np.hypot(c['eef'][0]-v[0],c['eef'][1]-v[1]) for i,v in cubes.items()}
        i=min(dists,key=dists.get); gr.append({**c,'nearest_initial_cube':i,'dist':round(float(dists[i]),4),'is_target':i in hid})
    comps=white_components(ep['timestep_30/obs/front_rgb'][()],K,Ex,bxy)
    records.append({'kind':'new','difficulty':e['difficulty'],'episode':e['episode'],'seed':e['seed'],'h5':e['h5'],'mp4':e['mp4'],
        'frames':T,'setup':setup,'n_cubes':len(cubes),'highlight_ids':hid,'highlight_count':spec['objects']['highlight_count'],
        'segments':segs,'grasps':gr,'targets':tgt,'non_targets':non,'white_components_t30_areas':comps,'demo_frames':int(sum(demo))})
    f.close()
# ---- native
for d in sorted(glob.glob(f'{ROOT}/artifacts/newtask-v6/v1/base/B/PickHighlight_episode_*')):
    h5=glob.glob(d+'/hdf5_files/*.h5')[0]; mp4=glob.glob(d+'/videos/*.mp4')
    f,ep,T,setup,K,segs,closes,demo=read_ep(h5)
    Ex=ep['timestep_5/obs/front_camera_extrinsic'][()]
    im=ep['timestep_5/obs/front_rgb'][()].astype(int)
    r,g,b=im[...,0],im[...,1],im[...,2]
    masks={'red':(r>110)&(g<70)&(b<70),'green':(g>110)&(r<90)&(b<90),'blue':(b>110)&(r<70)&(g<90)}
    cubes=[]
    for col,m in masks.items():
        n,lab,st,cen=cv2.connectedComponentsWithStats(m.astype(np.uint8),8)
        for i in range(1,n):
            if st[i,cv2.CC_STAT_AREA]>=12:
                u,v=cen[i]; w=backproj(K,Ex,u,v)
                cubes.append({'color':col,'uv':[round(u,1),round(v,1)],'xy':[round(float(w[0]),4),round(float(w[1]),4)],'area':int(st[i,cv2.CC_STAT_AREA])})
    frames,Ex2=best_highlight_frames(ep)
    for c in cubes:
        c['max_white_ring_frac_10_100']=max(ring_white(im2,K,Ex2,c['xy'],0.042) or 0 for im2 in frames)
    gr=[]
    for c in closes:
        if not cubes: break
        ds=[np.hypot(c['eef'][0]-q['xy'][0],c['eef'][1]-q['xy'][1]) for q in cubes]; i=int(np.argmin(ds))
        gr.append({**c,'nearest_initial_cube':i,'color':cubes[i]['color'],'dist':round(float(ds[i]),4)})
    comps=white_components(ep['timestep_30/obs/front_rgb'][()],K,Ex2,None)
    records.append({'kind':'native','difficulty':setup['difficulty'],'episode':int(re.search(r'episode_(\d+)',d).group(1)),'seed':setup['seed'],'h5':h5,'mp4':mp4,
        'frames':T,'setup':setup,'detected_cubes':cubes,'segments':segs,'grasps':gr,'white_components_t30_areas':comps,'demo_frames':int(sum(demo))})
    f.close()
def conv(o):
    if isinstance(o,(np.integer,)): return int(o)
    if isinstance(o,(np.floating,)): return float(o)
    if isinstance(o,np.bool_): return bool(o)
    raise TypeError(type(o))
json.dump(records,open(OUT+'/records_raw.json','w'),indent=1,default=conv,ensure_ascii=False)
print('ok',len(records))
