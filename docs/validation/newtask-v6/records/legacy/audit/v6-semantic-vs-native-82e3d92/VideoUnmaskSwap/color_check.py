import h5py, json, cv2, numpy as np, re
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
recs=json.load(open(E+'/raw_extract.json'))
specs={}
for t in ['xhard1','xhard2','xhard3','xhard4']:
    for line in open(f'{ROOT}/artifacts/newtask-v6/v6-01/{t}/specs.jsonl'):
        d=json.loads(line)
        if d.get('task')=='VideoUnmaskSwap' and d.get('record')=='spec': specs[(t,d['seed'])]=d['spec']
def masks(im):
    im=im.astype(int); r,g,b=im[...,0],im[...,1],im[...,2]
    hi=90; lo=60
    return {'red':(r>hi)&(g<lo)&(b<lo),'green':(g>hi)&(r<lo)&(b<lo),'blue':(b>hi)&(r<lo)&(g<lo),
            'yellow':(r>120)&(g>120)&(b<60)&(np.abs(r-g)<40),'cyan':(g>hi)&(b>hi)&(r<lo),'magenta':(r>hi)&(b>hi)&(g<lo)}
def blobs(im,minarea=6):
    out={}
    for k,m in masks(im).items():
        n,lab,st,cen=cv2.connectedComponentsWithStats(m.astype(np.uint8),8)
        out[k]=[[int(cen[i][0]),int(cen[i][1]),int(st[i][4])] for i in range(1,n) if st[i][4]>=minarea]
    return out
def cnt(b): return {k:len(v) for k,v in b.items() if v}
report=[]
for r in recs:
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    fr=lambda t: g[f'timestep_{t}']['obs/front_rgb'][()]
    rep=dict(tier=r['tier'],seed=r['seed'],episode=r['episode'])
    rep['t5']=cnt(blobs(fr(5)))
    rep['t50']=cnt(blobs(fr(50)))
    rep['demo_last']=cnt(blobs(fr(r['demo_last_step'])))
    sp=specs.get((r['tier'],r['seed']))
    if sp:
        from collections import Counter
        exp=Counter({'red':1,'green':1,'blue':1}); exp.update(Counter(sp['objects']['distractors']['cube_colors']))
        rep['t5_expected']=dict(exp)
    else:
        rep['t5_expected']={'red':1,'green':1,'blue':1}
    rep['t5_ok']=rep['t5']==rep['t5_expected']
    picks=[]
    segs=r['segments']
    for i,sg in enumerate(segs):
        if not sg['simple'].startswith('pick up'): continue
        col=re.search(r'hides the (\w+) cube',sg['simple']).group(1)
        s0=blobs(fr(sg['start'])); s1=blobs(fr(sg['end']))
        # lifted frame: use gripper-close + a bit; take end step
        new=[k for k in s1 if len(s1[k])>len(s0.get(k,[]))]
        picks.append(dict(color=col,start=sg['start'],end=sg['end'],start_counts=cnt(s0),end_counts=cnt(s1),newly_visible=new,
                          named_blob_end=s1.get(col),ok=(col in new)))
    rep['picks']=picks
    rep['all_picks_ok']=all(p['ok'] for p in picks)
    report.append(rep)
    print(rep['tier'],rep['seed'],'t5',rep['t5'],'exp',rep['t5_expected'],'OK' if rep['t5_ok'] else 'DIFF','| t50',rep['t50'],'| demo_last',rep['demo_last'])
    for p in picks: print('    pick',p['color'],p['start'],p['end'],'new',p['newly_visible'],'end',p['end_counts'],'OK' if p['ok'] else 'FAIL')
json.dump(report,open(E+'/color_check.json','w'),indent=1)
