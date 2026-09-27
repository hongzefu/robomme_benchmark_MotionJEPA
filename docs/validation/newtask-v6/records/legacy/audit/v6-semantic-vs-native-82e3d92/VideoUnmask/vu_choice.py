import h5py,json,numpy as np
OUT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmask'
recs=json.load(open(f'{OUT}/raw_extract.json')); cc={(c['tier'],c['episode']):c for c in json.load(open(f'{OUT}/color_checks.json'))}
res=[]
for e in recs:
    f=h5py.File(e['h5'],'r'); g=f[[k for k in f if k.startswith('episode_')][0]]
    c=cc[(e['tier'],e['episode'])]; pk=0; bad=[]
    for sg in e['segments']:
        if sg['simple'] in ('static','All tasks completed'): continue
        ch=json.loads(g[f"timestep_{sg['start']}"]['action']['choice_action'][()].decode())
        exp='A' if sg['simple'].startswith('pick') else 'B'
        info=dict(seg=sg['simple'],start=sg['start'],choice=ch)
        if ch['choice']!=exp: bad.append(('letter',info))
        if exp=='A':
            p=c['picks'][pk]; pk+=1
            if p['rgb_visible_start'][p['text_color']]!=0: bad.append(('target_visible_at_pick_start',p))
            if ch['point'] and p['reveal_cube_pos']:
                d=float(np.hypot(ch['point'][0]-p['reveal_cube_pos'][0],ch['point'][1]-p['reveal_cube_pos'][1])); info['point_to_cube_px']=round(d,1)
                # nearest other rgb cube distance
                others=[v[0] for k,v in c['reveal_positions'].items() if k!=p['text_color'] and v]
                info['nearest_other_rgb_px']=round(min(float(np.hypot(ch['point'][0]-o[0],ch['point'][1]-o[1])) for o in others),1)
                if d>12: bad.append(('point_far',info))
            if len(p['newly_uncovered'])!=1 or p['newly_uncovered'][0]!=p['text_color']: bad.append(('uncover',p))
        res.append(dict(tier=e['tier'],ep=e['episode'],**info))
    print(e['tier'],e['episode'],'BAD' if bad else 'ok',bad)
json.dump(res,open(f'{OUT}/choice_checks.json','w'),indent=1)
