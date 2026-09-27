"""Read-only visual check: initial R/G/B cube centroids (t=5) vs where each named color is revealed
during its pick segment; also flags any *other* primary color revealed during a pick segment."""
import h5py, json, os, numpy as np
OUT=os.path.dirname(os.path.abspath(__file__))
recs=json.load(open(f'{OUT}/records_raw.json'))
def masks(im):
    r,g,b=[im[:,:,i].astype(int) for i in range(3)]
    return {'red':(r>150)&(g<70)&(b<70),'green':(g>140)&(r<90)&(b<90),'blue':(b>150)&(r<70)&(g<70)}
def cent(m):
    ys,xs=np.nonzero(m)
    return None if len(ys)<6 else [float(ys.mean()),float(xs.mean()),int(len(ys))]
out=[]
for r in recs:
    f=h5py.File(r['h5'],'r'); ep=f[list(f.keys())[0]]
    def img(t): return ep[f'timestep_{t}/obs/front_rgb'][()]
    init={c:cent(m) for c,m in masks(img(5)).items()}
    segs=r['segments']; picks=[]
    for i,s in enumerate(segs):
        if not s['subgoal'].startswith('pick up the container'): continue
        color=s['subgoal'].split('hides the ')[1].split(' cube')[0]
        t0=s['t']; t1=segs[i+1]['t'] if i+1<len(segs) else r['n_steps']-1
        # colors visible at segment start (already revealed, e.g. previous put-down target)
        base={c:cent(m) for c,m in masks(img(t0)).items()}
        revealed={}
        for t in range(t0,t1+1):
            for c,m in masks(img(t)).items():
                ce=cent(m)
                if ce and ce[2]>=15 and c not in revealed:
                    # new appearance: not visible at start, or visible at a different place
                    if base[c] is None or np.hypot(ce[0]-base[c][0],ce[1]-base[c][1])>12:
                        revealed[c]=dict(t=t,centroid=ce)
        tgt=revealed.get(color)
        d_init=None
        if tgt and init[color]:
            d_init=float(np.hypot(tgt['centroid'][0]-init[color][0],tgt['centroid'][1]-init[color][1]))
        others=[c for c in revealed if c!=color]
        picks.append(dict(t0=t0,t1=t1,named=color,revealed=revealed,named_revealed=tgt is not None,
                          other_primary_revealed=others,dist_reveal_vs_initial_px=d_init,
                          same_slot_as_initial=(d_init is not None and d_init<10)))
    last={c:cent(m) for c,m in masks(img(r['n_steps']-1)).items()}
    out.append(dict(tier=r['tier'],episode=r['episode'],seed=r['seed_attr'],initial_centroids=init,picks=picks,final_visible=last))
    print(r['tier'],r['episode'],'init',{c:(None if v is None else [round(v[0]),round(v[1])]) for c,v in init.items()})
    for p in picks: print('   pick',p['named'],'t',p['t0'],'rev' ,{c:(v['t'],[round(v['centroid'][0]),round(v['centroid'][1])]) for c,v in p['revealed'].items()},'d_init',None if p['dist_reveal_vs_initial_px'] is None else round(p['dist_reveal_vs_initial_px'],1),'others',p['other_primary_revealed'])
json.dump(out,open(f'{OUT}/color_track.json','w'),indent=1)
