import json
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
L=lambda n: json.load(open(f'{E}/{n}'))
raw=L('raw_extract.json'); cc={(x['tier'],x['seed']):x for x in L('color_check.json')}
tr={(x['tier'],x['seed']):x for x in L('track_check.json')}; mo={(x['tier'],x['seed']):x for x in L('motion_check.json')}
sw={(x['tier'],x['seed']):x for x in L('swap_pair_check.json')}; ps={(x['tier'],x['seed']):x for x in L('post_swap_check.json')}
specs={}
for t in ['xhard1','xhard2','xhard3','xhard4']:
    for line in open(f'{ROOT}/artifacts/newtask-v6/v6-01/{t}/specs.jsonl'):
        d=json.loads(line)
        if d.get('task')=='VideoUnmaskSwap' and d.get('record')=='spec': specs[(t,d['seed'])]=d['spec']
names=['red','green','blue']
recs=[]
for r in raw:
    k=(r['tier'],r['seed']); sp=specs.get(k)
    rec=dict(tier=r['tier'],episode=r['episode'],seed=r['seed'],h5=r['h5'],mp4=r['mp4'],hdf5_difficulty=r['difficulty_attr'],
             task_goal=r['task_goal'][0],available_multi_choices=r['choices'],n_steps=r['n_steps'],demo_last_step=r['demo_last_step'],
             completed_last_step=r['completed_last'],subgoal_boundaries=r['boundaries'],
             segments=[dict(start=s['start'],end=s['end'],simple=s['simple'],grounded=s['grounded'],grounded_online=s['grounded_online'],video_demo=s['demo']) for s in r['segments']],
             pick_subgoals_without_coordinates=[dict(start=s['start'],end=s['end'],grounded=s['grounded']) for s in r['segments'] if s['simple'].startswith('pick up') and '<' not in s['grounded']],
             color_check=cc[k], motion_check=mo[k], post_swap_colored_px=ps[k]['colored_px'])
    if sp:
        o=sp['objects']
        rec['spec']=dict(n_swaps=o['n_swaps'],n_picks=o['n_picks'],swap_window=sp['actions']['swap_window'],selected=o['selected'],
                         color_names=[names[i] for i in o['color_order']],inner_swap_pairs=[[sp['actions']['swap_pairs'][str(i)]['initiator'],sp['actions']['swap_pairs'][str(i)]['partner']] for i in range(o['n_swaps'])],
                         outer_distractors=o['distractors']['placed'],outer_cube_colors=o['distractors']['cube_colors'],outer_swap_pairs=sp['actions']['distractor_swap_pairs'])
        rec['track_check']=tr[k]; rec['swap_pair_visual_check']=sw[k]
    recs.append(rec)
json.dump(recs,open(E+'/records.json','w'),indent=1); print(len(recs))
