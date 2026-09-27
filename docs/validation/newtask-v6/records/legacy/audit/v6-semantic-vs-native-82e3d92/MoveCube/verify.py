import json,re,numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube'
raw=json.load(open(E+'/raw_extract.json')); tr=json.load(open(E+'/pixel_tracks.json'))
proj=json.load(open(E+'/xhard4_spec_projection.json'))
WAY={'Pick up the peg':'peg_push','Close the gripper and push the cube to the target':'gripper_push','Pick up the cube':'grasp_putdown'}
recs=[]
for r in raw:
    tag=('xhard4' if r['kind']=='new' else r['setup']['difficulty'])+f"_ep{r['episode']}"
    t=tr[tag]; segs=r['segments']; bs=[s for s in segs if s['boundary']]
    way=WAY[bs[0]['simple']]; dm=[s['simple'] for s in bs if s['demo']]; ex=[s['simple'] for s in bs if not s['demo']]
    ex_chain=[x for x in ex if x!='All tasks completed']; dm_chain=[x for x in dm if x!='static']
    checks=[]
    def dist(a,b): return None if a is None or b is None else round(float(np.hypot(a[0]-b[0],a[1]-b[1])),1)
    for s in bs:
        co=[(int(a),int(b)) for a,b in re.findall(r'<(\d+), (\d+)>',s['grounded'] or '')]
        k=s['step']; x=t[k]
        if s['simple'].startswith(('Close the gripper','Hook')) and len(co)==2:
            checks.append(dict(step=k,what='cube@start',grounded=co[0],detected=x['red'],err_px=dist(co[0],x['red'])))
            checks.append(dict(step=k,what='target',grounded=co[1],detected=x['pur'],err_px=dist(co[1],x['pur'])))
        elif s['simple'].startswith('Pick up the cube') and co:
            checks.append(dict(step=k,what='cube@start',grounded=co[0],detected=x['red'],err_px=dist(co[0],x['red'])))
        elif s['simple'].startswith('place the cube') and co:
            checks.append(dict(step=k,what='target',grounded=co[0],detected=x['pur'],err_px=dist(co[0],x['pur'])))
    st=[s['step'] for s in bs if s['simple']=='static'][0]
    ex0=[s['step'] for s in bs if not s['demo']][0]
    done=[s['step'] for s in bs if s['simple']=='All tasks completed'][0]; n=r['n_steps']
    rec=dict(tag=tag,kind=r['kind'],difficulty=r['setup']['difficulty'],seed=r['setup']['seed'],episode=r['episode'],h5=r['h5'],mp4=r['mp4'],
        language_goal=r['setup']['task_goal'],choices=[c['action'] for c in json.loads(r['setup']['available_multi_choices'])] if isinstance(r['setup']['available_multi_choices'],str) else r['setup']['available_multi_choices'],
        way=way,demo_chain=dm_chain,exec_chain=ex_chain,same_manner=dm_chain==ex_chain,n_steps=n,n_demo=r['n_demo'],
        boundaries=[dict(step=s['step'],demo=s['demo'],simple=s['simple'],grounded=s['grounded']) for s in bs],
        grounding_checks=checks,max_grounding_err_px=max([c['err_px'] for c in checks if c['err_px'] is not None],default=None),
        demo_end=dict(step=st,cube_px=t[st]['red'],cube_visible_px=t[st]['red_n'],target_px=t[st]['pur'],cube_target_px=dist(t[st]['red'],t[st]['pur'])),
        exec_start=dict(step=ex0,cube_px=t[ex0]['red'],target_px=t[ex0]['pur'],target_ring_px=t[ex0]['pur_n']),
        exec_done=dict(step=done,cube_px=t[done]['red'],target_px=t[done]['pur'],cube_target_px=dist(t[done]['red'],t[done]['pur'])),
        last=dict(step=n-1,cube_px=t[n-1]['red'],target_px=t[n-1]['pur'],cube_target_px=dist(t[n-1]['red'],t[n-1]['pur']),cube_drift_done_to_last_px=dist(t[done]['red'],t[n-1]['red'])),
        final_completed=r['last_completed'],choice_letters=sorted(set(json.loads(c['v'])['choice'] for c in r['choice_actions'] if c['v'].startswith('{'))))
    if r['kind']=='new': rec['spec_world']=proj[str(r['episode'])]
    recs.append(rec)
    print(tag,way,'same',rec['same_manner'],'maxErr',rec['max_grounding_err_px'],'demoEnd',rec['demo_end']['cube_target_px'],rec['demo_end']['cube_visible_px'],'done',rec['exec_done']['cube_target_px'],'drift',rec['last']['cube_drift_done_to_last_px'],'choices',rec['choice_letters'],'nd/n',r['n_demo'],n)
json.dump(recs,open(E+'/records.json','w'),indent=1,ensure_ascii=False)
