import json,re
recs=json.load(open('records_raw.json'))
out=[]
for r in recs:
    diff=r.get('difficulty') or r['setup']['difficulty']
    segs=[s for s in r['segments'] if s['ss'].startswith('pick up')]
    pts=[tuple(map(int,re.search(r'<(\d+), (\d+)>',s['gs']).groups())) for s in segs]
    d=((pts[1][0]-pts[0][0])**2+(pts[1][1]-pts[0][1])**2)**.5 if len(pts)>1 else None
    rec=dict(kind=r['kind'],difficulty=diff,episode=r['episode'],demo_pick_rc=pts[0],first_exec_pick_rc=pts[1] if len(pts)>1 else None,dist_px=d)
    if r.get('spec'):
        sp=r['spec']; t=sp['objects']['target']; n=sp['objects']['cube_count']['actual']
        slot=list(range(n)); part=0; moves=[]
        for k,v in sorted(sp['actions']['swap_pairs'].items(),key=lambda x:int(x[0])):
            a=int(v['initiator'][4:]); b=int(v['partner'][4:])
            slot[a],slot[b]=slot[b],slot[a]
            if t in (a,b): part+=1; moves.append(int(k))
        rec.update(target=t,n_swaps=sp['objects']['n_swaps'],target_participation=part,target_swap_indices=moves,target_final_slot=slot[t],target_initial_slot=t,returns_to_origin=slot[t]==t)
    out.append(rec); print(rec)
json.dump(out,open('target_return.json','w'),indent=1)
