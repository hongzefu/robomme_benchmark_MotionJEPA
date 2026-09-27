import json,sys,collections
R=json.load(open('records.json'))
task=sys.argv[1]
order=['easy','medium','hard','xhard1','xhard2','xhard3','xhard4']
rs=sorted([r for r in R if r['task']==task], key=lambda r:(order.index(r['difficulty']),r['episode']))
full = len(sys.argv)>2
for r in rs:
    print('==',r['difficulty'],'ep',r['episode'],'seed',r['setup'].get('seed'),'steps',r['n_steps'],'demo',r['n_demo_steps'],'done',r['last_completed'])
    print('  GOAL:',r['setup']['task_goal'][0])
    if full: 
        for g in r['setup']['task_goal'][1:]: print('  ALT :',g)
    if full: print('  CHOICES:',r['setup'].get('available_multi_choices'))
    for b in r['boundaries']:
        print('   ','D' if b['demo'] else 'E', b['t'], '|', b['grounded'], '|', b.get('choice','') if full else '')
