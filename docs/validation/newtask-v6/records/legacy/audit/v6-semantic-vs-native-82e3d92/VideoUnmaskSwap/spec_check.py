import json,glob
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
E=ROOT+'/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoUnmaskSwap'
raw={ (r['tier'],r['seed']):r for r in json.load(open(E+'/raw_extract.json'))}
specs={}
for t in ['xhard1','xhard2','xhard3','xhard4']:
    for line in open(f'{ROOT}/artifacts/newtask-v6/v6-01/{t}/specs.jsonl'):
        d=json.loads(line)
        if d.get('task')=='VideoUnmaskSwap' and d.get('record')=='spec': specs[(t,d['seed'])]=d
cfg={'xhard1':((4,5),2,4,50),'xhard2':((6,7),3,6,33),'xhard3':((8,9),3,8,33),'xhard4':((10,12),3,10,33)}
names=['red','green','blue']
out=[]
print('all candidates:')
for (t,seed),d in sorted(specs.items()):
    sp=d['spec']; o=sp['objects']; a=sp['actions']
    ns,npk=o['n_swaps'],o['n_picks']; nd=o['distractors']['placed']; cc=o['distractors']['cube_count']
    L=a['swap_window']['duration_steps']
    c=cfg[t]; ok= c[0][0]<=ns<=c[0][1] and npk==c[1] and nd==c[2] and cc==nd//2 and L==c[3] and len(a['swap_pairs'])==ns and len(a['distractor_swap_pairs'])==ns
    colors=[names[i] for i in o['color_order']]
    print(t,seed,'swaps',ns,'picks',npk,'outer',nd,'outer_cubes',cc,o['distractors']['cube_colors'],'L',L,'selected',o['selected'],'colors',colors,'OK' if ok else 'VIOLATION')
print()
for (t,seed),r in sorted(raw.items()):
    if not t.startswith('xhard'): continue
    d=specs.get((t,seed))
    if d is None:
        # recovery run: xhard4 in infra-recovery
        print('no spec in specs.jsonl for',t,seed); continue
    sp=d['spec']; o=sp['objects']; a=sp['actions']
    colors=[names[i] for i in o['color_order']]
    npk=o['n_picks']
    exp_goal_cols=colors[:npk]
    goal=r['task_goal'][0]
    got=[seg['simple'].split('hides the ')[1].split(' cube')[0] for seg in r['segments'] if seg['simple'].startswith('pick up')]
    import re
    gcols=re.findall(r'hiding the (\w+) cube',goal)
    last_end=64+o['n_swaps']*a['swap_window']['duration_steps']
    print(t,seed,'n_swaps',o['n_swaps'],'last_end',last_end,'demo_last',r['demo_last_step'],'exp',exp_goal_cols,'goal',gcols,'subgoals',got,'MATCH' if exp_goal_cols==gcols==got else 'MISMATCH')
