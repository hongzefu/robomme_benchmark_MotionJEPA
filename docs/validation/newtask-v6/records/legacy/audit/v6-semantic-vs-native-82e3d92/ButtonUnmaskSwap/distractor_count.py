"""Read-only: count yellow/cyan/magenta distractor-cube blobs at t=5 and t=30 (front_rgb, connected components)."""
import h5py, json, os, numpy as np, cv2
OUT=os.path.dirname(os.path.abspath(__file__))
recs=json.load(open(f'{OUT}/records_raw.json')); specs={(s['tier'],s['episode']):s for s in json.load(open(f'{OUT}/specs_newtier.json'))}
res=[]
for r in recs:
    f=h5py.File(r['h5'],'r'); ep=f[list(f.keys())[0]]
    row=dict(tier=r['tier'],episode=r['episode'])
    for t in (5,30):
        im=ep[f'timestep_{t}/obs/front_rgb'][()].astype(int); R,G,B=im[:,:,0],im[:,:,1],im[:,:,2]
        ms={'yellow':(R>170)&(G>170)&(B<90),'cyan':(G>150)&(B>150)&(R<90),'magenta':(R>150)&(B>150)&(G<90)}
        cnt={}
        for c,m in ms.items():
            n,lab,st,_=cv2.connectedComponentsWithStats(m.astype(np.uint8),8)
            cnt[c]=int(sum(1 for i in range(1,n) if st[i,4]>=8))
        row[f't{t}']=cnt
    sp=specs.get((r['tier'],r['episode']))
    if sp: row['spec_cube_colors']=sp['distractor_cube_colors']; row['spec_bins_placed']=sp['distractor_placed']
    res.append(row); print(row)
json.dump(res,open(f'{OUT}/distractor_count.json','w'),indent=1)
