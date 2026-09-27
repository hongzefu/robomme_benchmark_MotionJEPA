import json,re
recs=json.load(open('records_raw.json'))
res=[]
for r in recs:
    diff=r.get('difficulty') or r['setup']['difficulty']
    os_=r['online_segments']
    picks=[s for s in os_ if s['sso'].startswith('pick up the correct cube')]
    puts=[s for s in os_ if s['sso']=='put it down']
    btn=[s for s in os_ if s['sso'].startswith('press the button')]
    if not picks: continue
    t2=picks[0]['start']; t3=puts[0]['start'] if puts else None
    def uncovered(segs,t0):
        u=[]
        for s in segs:
            lo=max(s['start'],t0+501); 
            if s['end']>=lo: u.append([lo,s['end']])
        return u
    up=uncovered(picks,t2); ud=uncovered(puts,t3) if t3 is not None else []
    nrep=len(picks)
    exec_len=(btn[0]['start'] if btn else r['n_steps'])-t2
    rec=dict(kind=r['kind'],difficulty=diff,episode=r['episode'],num_repeats=nrep,first_pick_step=t2,first_put_step=t3,
      pick_guard_window=[t2+50,t2+500],put_guard_window=None if t3 is None else [t3+50,t3+500],
      last_pick_end=picks[-1]['end'],last_put_end=puts[-1]['end'] if puts else None,
      exec_steps_before_button=exec_len,
      pick_steps_unguarded=sum(b-a+1 for a,b in up),put_steps_unguarded=sum(b-a+1 for a,b in ud),
      pick_unguarded_ranges=up,put_unguarded_ranges=ud,
      pick_total_steps=sum(s['end']-s['start']+1 for s in picks),put_total_steps=sum(s['end']-s['start']+1 for s in puts))
    res.append(rec)
    print(r['kind'],diff,r['episode'],'N',nrep,'exec',exec_len,'pick',t2,'->',picks[-1]['end'],'unguarded pick',rec['pick_steps_unguarded'],'/',rec['pick_total_steps'],'put',rec['put_steps_unguarded'],'/',rec['put_total_steps'],up,ud)
json.dump(res,open('timewindow_analysis.json','w'),indent=1)
