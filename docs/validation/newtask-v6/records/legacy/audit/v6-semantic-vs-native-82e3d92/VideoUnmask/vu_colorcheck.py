import h5py,json,cv2,numpy as np,re
OUT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmask'
recs=json.load(open(f'{OUT}/raw_extract.json'))
HUES={'red':[(0,6),(174,180)],'yellow':[(25,35)],'green':[(55,65)],'cyan':[(85,95)],'blue':[(115,125)],'magenta':[(145,155)]}
def blobs(rgb):
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV); h,s,v=hsv[...,0],hsv[...,1],hsv[...,2]
    res={}
    for c,rs in HUES.items():
        m=np.zeros(h.shape,bool)
        for lo,hi in rs: m|=(h>=lo)&(h<=hi)
        m&=(s>200)&(v>60)
        n,lab,st,cen=cv2.connectedComponentsWithStats(m.astype(np.uint8))
        res[c]=[dict(yx=[round(float(cen[i][1]),1),round(float(cen[i][0]),1)],area=int(st[i][4])) for i in range(1,n) if st[i][4]>=6]
    return res
def white_count(rgb):
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV); m=((hsv[...,1]<40)&(hsv[...,2]>170)).astype(np.uint8)
    m[:40,:]=0  # drop robot base/top strip
    n,lab,st,cen=cv2.connectedComponentsWithStats(m); return int(sum(st[i][4]>=30 for i in range(1,n)))
out=[]
for e in recs:
    f=h5py.File(e['h5'],'r'); g=f[[k for k in f if k.startswith('episode_')][0]]
    G=lambda t: g[f'timestep_{t}']['obs']['front_rgb'][()]
    rev=blobs(G(10)); pre=blobs(G(0)); after=blobs(G(40))
    r=dict(tier=e['tier'],episode=e['episode'],seed=e['seed'],goal=e['setup']['task_goal'][0],
           reveal_t10={c:len(v) for c,v in rev.items()},reveal_t0={c:len(v) for c,v in pre.items()},
           covered_t40={c:len(v) for c,v in after.items()},white_components_t40=white_count(G(40)),
           reveal_positions={c:[b['yx'] for b in v] for c,v in rev.items() if c in('red','green','blue')},picks=[])
    goal_colors=re.findall(r'hiding the (\w+) cube',r['goal'])
    picks=[sg for sg in e['segments'] if sg['simple'].startswith('pick')]
    r['goal_colors']=goal_colors; r['subgoal_colors']=[re.search(r'hides the (\w+) cube',p['simple']).group(1) for p in picks]
    for k,p in enumerate(picks):
        col=r['subgoal_colors'][k]
        b_end=blobs(G(p['end'])); b_start=blobs(G(p['start']))
        gy=re.search(r'<(\d+), (\d+)>',p['grounded'])
        gp=[int(gy.group(1)),int(gy.group(2))] if gy else None
        tgt=rev[col][0]['yx'] if rev[col] else None
        d=None if (gp is None or tgt is None) else round(float(np.hypot(gp[0]-tgt[0],gp[1]-tgt[1])),1)
        # which rgb cubes visible at end vs start
        vis_start={c:len(b_start[c]) for c in ('red','green','blue')}; vis_end={c:len(b_end[c]) for c in ('red','green','blue')}
        newly=[c for c in ('red','green','blue') if vis_end[c]>vis_start[c]]
        r['picks'].append(dict(k=k,text_color=col,seg=[p['start'],p['end']],grounded=gp,reveal_cube_pos=tgt,grounded_to_cube_px=d,
                               rgb_visible_start=vis_start,rgb_visible_end=vis_end,newly_uncovered=newly))
    out.append(r)
    print(r['tier'],r['episode'],'goal',goal_colors,'sub',r['subgoal_colors'],'rev',r['reveal_t10'],'cov40',{c:v for c,v in r['covered_t40'].items() if v},'white',r['white_components_t40'])
    for p in r['picks']: print('   pick',p['k'],p['text_color'],p['seg'],'gp',p['grounded'],'cube',p['reveal_cube_pos'],'d',p['grounded_to_cube_px'],'new',p['newly_uncovered'],p['rgb_visible_end'])
json.dump(out,open(f'{OUT}/color_checks.json','w'),indent=1)
