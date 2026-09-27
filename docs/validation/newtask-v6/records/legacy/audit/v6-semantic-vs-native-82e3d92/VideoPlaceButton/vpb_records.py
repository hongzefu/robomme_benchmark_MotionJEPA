import json
R=json.load(open('raw_extract.json')); T={(t['difficulty'],t['episode']):t for t in json.load(open('cube_tracks.json'))}
recs=[]
for r in R:
    tier=r['difficulty']; ep=r['episode']; rng=r['rng']
    segs=[e for e in T[(tier,ep)]['events']]
    rec=dict(tier=tier,episode=ep,seed=r['setup']['seed'],h5=r['h5'],mp4=r['mp4'],n_steps=r['n_steps'],
             task_goal=r['setup']['task_goal'],choices=r['setup']['available_multi_choices'],
             segments=[dict(start=e['start'],end=e['end'],demo=e['demo'],simple=e['simple'],grounded=e['grounded'],cube_moves_px_xy=e['moved']) for e in segs])
    btn=[e for e in segs if e['simple'].startswith('press')]
    rec['button_steps']=[btn[0]['start'],btn[0]['end']] if btn else None
    if rng:
        colors=[['red','blue','green'][i] for i in rng['objects.color_order']]
        demo=[colors[i] for i in rng['objects.demo_ids']]
        n=len(demo); tf=rng['objects.task_flag']; ai=rng['objects.answer_demo_index']
        before=[(demo[k],2*k) for k in range(n)]; after=[(demo[k],2*k+1) for k in range(n)]
        sides=['before']*(1 if 'objects.extra_place_target_ids.before.0' in rng else 0)+['after']*(1 if 'objects.extra_place_target_ids.after.0' in rng else 0)
        owners=rng['objects.extra_place_owner_ids']
        eb=[(demo[o],rng[f'objects.extra_place_target_ids.{s}.0']) for s,o in zip(sides,owners) if s=='before']
        ea=[(demo[o],rng[f'objects.extra_place_target_ids.{s}.0']) for s,o in zip(sides,owners) if s=='after']
        seq=[('before',)+b for b in before]+[('extra-before',)+b for b in eb]+[('BUTTON',None,None)]+[('after',)+a for a in after]+[('extra-after',)+a for a in ea]+[('home',c,None) for c in demo]
        # attach step spans in order of drop segments
        drops=[e for e in segs if e['demo'] and (e['simple'].startswith(('drop','put the','press')))]
        seq2=[]
        for s,d in zip(seq,drops): seq2.append(dict(kind=s[0],cube=s[1],target=s[2],drop_seg=[d['start'],d['end']],subgoal=d['grounded']))
        rec['plan_from_rng']=dict(all_cubes=colors,demo_cubes=demo,answer_cube=demo[ai],language=('before' if tf else 'after'),
            answer_target=rng['actions.target_target_id'],swap_pair=rng['objects.swap_pair_ids'][:2],placement_count=rng['actions.target_placement_count'],sequence=seq2)
        # derived checks
        pos={}; last_before={}; first_after={}; noop=[]; seen_btn=False; order=[]
        for s in seq2:
            if s['kind']=='BUTTON': seen_btn=True; order.append('BUTTON'); continue
            if s['kind']=='home': continue
            c,t=s['cube'],s['target']
            if pos.get(c)==t: noop.append(dict(cube=c,target=t,steps=s['drop_seg']))
            pos[c]=t; order.append((c,t))
            if not seen_btn: last_before[c]=t
            elif c not in first_after: first_after[c]=t
        ac=demo[ai]; lang=rec['plan_from_rng']['language']
        per_cube=last_before[ac] if lang=='before' else first_after[ac]
        bi=order.index('BUTTON')
        glob=order[bi-1] if lang=='before' else order[bi+1]
        rec['checks']=dict(per_cube_expected_target=per_cube,program_answer_target=rng['actions.target_target_id'],
            per_cube_match=(per_cube==rng['actions.target_target_id']),
            placement_adjacent_to_button=glob, adjacent_is_answer_cube=(glob[0]==ac),
            noop_replacements=noop, distinct_target_changes=sum(1 for o in order if o!='BUTTON')-len(noop))
    recs.append(rec)
json.dump(recs,open('records.json','w'),indent=1)
for x in recs:
    if 'checks' in x: print(x['tier'],x['episode'],x['plan_from_rng']['answer_cube'],x['plan_from_rng']['language'],json.dumps(x['checks']))
