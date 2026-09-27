import json,re,math
D='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/SwingXtimes'
R=json.load(open(D+'/raw_extract.json'))
res=[]
for r in R:
    m=re.search(r'<(\d+), (\d+)>',r['segments'][0]['grounded']); gy,gx=int(m.group(1)),int(m.group(2))
    f0=r['frame0_blobs']; last=r['frame_last_blobs']
    dist={c:min(math.hypot(b['cx']-gx,b['cy']-gy) for b in v) for c,v in f0.items()}
    nearest=min(dist,key=dist.get)
    moved={}
    for c,v in f0.items():
        b=max(v,key=lambda x:x['area'])
        # min distance of this f0 blob to any last blob of same color
        moved[c]=round(min(math.hypot(b['cx']-x['cx'],b['cy']-x['cy']) for x in last.get(c,[{'cx':1e9,'cy':1e9}])),1)
    row=dict(tier=r['difficulty'],ep=r['episode'],goal_color=r['goal_color'],grounded_pick=[gy,gx],nearest_blob=nearest,nearest_dist=round(dist[nearest],1),
             f0_colors=sorted(f0),moved_px=moved)
    res.append(row); print(row)
json.dump(res,open(D+'/identity.json','w'),indent=1)
