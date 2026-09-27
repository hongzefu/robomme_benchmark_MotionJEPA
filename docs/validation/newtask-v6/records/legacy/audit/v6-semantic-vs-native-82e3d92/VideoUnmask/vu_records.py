import json
OUT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmask'
raw=json.load(open(f'{OUT}/raw_extract.json')); cc={(c['tier'],c['episode']):c for c in json.load(open(f'{OUT}/color_checks.json'))}
ch=json.load(open(f'{OUT}/choice_checks.json'))
cfg={'easy':dict(bins=3,pick=1,ring=0,ring_cubes=0),'medium':dict(bins=5,pick=1,ring=0,ring_cubes=0),'hard':dict(bins=15,pick=2,ring=0,ring_cubes=0),
 'xhard1':dict(bins=8,pick=2,ring=8,ring_cubes=[4,4]),'xhard2':dict(bins=8,pick=3,ring=10,ring_cubes=[5,5]),'xhard3':dict(bins=8,pick=3,ring=13,ring_cubes=[6,7]),'xhard4':dict(bins=8,pick=3,ring=15,ring_cubes=[7,8])}
out=[]
for e in raw:
    c=cc[(e['tier'],e['episode'])]
    ring_seen=sum(c['reveal_t10'][k] for k in ('yellow','cyan','magenta'))
    out.append(dict(tier=e['tier'],episode=e['episode'],seed=e['seed'],h5=e['h5'],mp4=e['mp4'],config_at_audit_base=cfg[e['tier']],
      task_goal=e['setup']['task_goal'],available_multi_choices=e['setup']['available_multi_choices'],n_steps=e['n_steps'],
      video_demo_steps=e['demo_steps'],subgoal_boundaries=e['boundaries'],
      segments=[dict(start=s['start'],end=s['end'],simple=s['simple'],grounded=s['grounded']) for s in e['segments']],
      goal_colors=c['goal_colors'],subgoal_colors=c['subgoal_colors'],
      reveal_t10_cube_counts=c['reveal_t10'],ring_cubes_seen=ring_seen,
      ring_cubes_in_range=(e['tier'].startswith('xhard') and cfg[e['tier']]['ring_cubes'][0]<=ring_seen<=cfg[e['tier']]['ring_cubes'][1]) or (not e['tier'].startswith('xhard') and ring_seen==0),
      all_cubes_covered_t40=not any(c['covered_t40'].values()),
      picks=c['picks'],choice_checks=[x for x in ch if x['tier']==e['tier'] and x['ep']==e['episode']],
      grip_close_runs=e['grip_close_runs'],completed_first_step=e['completed_first'],
      sheet=f"{OUT}/frames/sheet_{e['tier']}_ep{e['episode']}_seed{e['seed']}.png"))
json.dump(out,open(f'{OUT}/records.json','w'),indent=1,ensure_ascii=False)
print(len(out),[ (o['tier'],o['ring_cubes_seen'],o['ring_cubes_in_range'],o['all_cubes_covered_t40']) for o in out])
