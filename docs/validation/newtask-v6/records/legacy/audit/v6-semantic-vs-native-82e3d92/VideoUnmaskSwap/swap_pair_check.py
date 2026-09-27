import h5py, json, numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
specs={}
for t in ['xhard1','xhard2','xhard3','xhard4']:
    for line in open(f'{ROOT}/artifacts/newtask-v6/v6-01/{t}/specs.jsonl'):
        d=json.loads(line)
        if d.get('task')=='VideoUnmaskSwap' and d.get('record')=='spec': specs[(t,d['seed'])]=d['spec']
def proj(g,t,xyz):
    gi=g[f'timestep_{t}']; ext=gi['obs/front_camera_extrinsic'][()]; K=g['setup/front_camera_intrinsic'][()]
    pc=ext[:,:3]@np.array(xyz)+ext[:,3]; uv=K@pc; return uv[:2]/uv[2]
def whitefrac(im,uv,rad=4):
    u,v=int(round(uv[0])),int(round(uv[1]))
    patch=im[max(0,v-rad):v+rad+1,max(0,u-rad):u+rad+1].astype(int)
    mn=patch.min(-1); mx=patch.max(-1)
    return float(((mn>150)&(mx-mn<35)).mean())
out=[]; bad=0; total=0
for r in json.load(open(E+'/raw_extract.json')):
    sp=specs.get((r['tier'],r['seed']))
    if not sp: continue
    f=h5py.File(r['h5'],'r'); g=f[list(f.keys())[0]]
    L=sp['actions']['swap_window']['duration_steps']; slots={int(k):v[:2] for k,v in sp['layout']['bins'].items()}
    pos=dict(slots); wins=[]
    for k in range(sp['objects']['n_swaps']):
        a=int(sp['actions']['swap_pairs'][str(k)]['initiator'].split('_')[1]); b=int(sp['actions']['swap_pairs'][str(k)]['partner'].split('_')[1])
        tm=64+L*k+L//2; im=g[f'timestep_{tm}']['obs/front_rgb'][()]
        # positions (slots) currently occupied by a and b vs the others
        wa=whitefrac(im,proj(g,tm,[*pos[a],0.02])); wb=whitefrac(im,proj(g,tm,[*pos[b],0.02]))
        others=[whitefrac(im,proj(g,tm,[*pos[c],0.02])) for c in pos if c not in (a,b)]
        allw={c:whitefrac(im,proj(g,tm,[*pos[c],0.035]),5) for c in pos}
        low2=set(sorted(allw,key=lambda c:allw[c])[:2])
        ok = low2=={a,b} and sorted(allw.values())[2]-sorted(allw.values())[1]>0.1
        total+=1; bad+= (not ok)
        wins.append(dict(k=k,pair=[a,b],mid_step=tm,white_at_a=round(wa,2),white_at_b=round(wb,2),white_at_others=[round(x,2) for x in others],white_all_z035={str(c):round(v,2) for c,v in allw.items()},ok=ok))
        pos[a],pos[b]=pos[b],pos[a]
    out.append(dict(tier=r['tier'],seed=r['seed'],windows=wins))
    print(r['tier'],r['seed'],[ (w['pair'],w['ok'],w['white_all_z035']) for w in wins if not w['ok']])
print('SWAP_PAIR_VISUAL windows',total,'not_ok',bad)
json.dump(out,open(E+'/swap_pair_check.json','w'),indent=1)
