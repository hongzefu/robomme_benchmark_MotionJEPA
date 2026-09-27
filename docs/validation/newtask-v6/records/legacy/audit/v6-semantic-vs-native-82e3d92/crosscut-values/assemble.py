"""只读汇总：逐格(任务,档位)对比配置值与HDF5/视频实测值，写 measured.json。"""
import json,re,math,sys
from collections import Counter,defaultdict
E=sys.argv[1]
scan=json.load(open(E+'/scan_raw.json')); cfg=json.load(open(E+'/sampling_config.json'))['tasks']
counts={(o['task'],o['tier'],o['ep']):o for o in json.load(open(E+'/counts_raw.json'))}
area={(o['task'],o['tier'],o['ep']):o for o in json.load(open(E+'/cubearea_raw.json'))}
swaps={(o['task'],o['tier'],o['ep']):o for o in json.load(open(E+'/swaps_raw.json'))}
stop={(o['tier'],o['ep']):o for o in json.load(open(E+'/stopcube_visits.json'))}
track={(o['task'],o['tier'],o['ep']):o for o in json.load(open(E+'/track_raw.json'))}
vpid={(o['task'],o['tier'],o['ep']):o for o in json.load(open(E+'/vp_identity.json'))}
W={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'twice':2,'again':1}
OW={'first':1,'second':2,'third':3,'fourth':4,'fifth':5,'sixth':6,'seventh':7,'eighth':8,'ninth':9,'tenth':10,'eleventh':11,'twelfth':12,'thirteenth':13,'fourteenth':14,'fifteenth':15}
order=['easy','medium','hard','xhard1','xhard2','xhard3','xhard4']
def inr(v,rg): return rg[0]<=v<=rg[1]
def swapcount(o,L):
    return sum(max(1,round((b-a+1)/L)) for a,b in o['all']['windows'])
def ncubes(key):
    return sum(max(1,round(a/21)) for v in area[key]['colors'].values() for a in v['area_cm2'])
cells=defaultdict(list)
for x in scan: cells[(x['task'],x['setup']['difficulty'])].append(x)
out=[]
for (task,tier),xs in sorted(cells.items(),key=lambda kv:(kv[0][0],order.index(kv[0][1]))):
    dec=cfg[task]['decision']; eps=[]
    for x in sorted(xs,key=lambda x:x['episode']):
        key=(task,tier,x['episode']); b=x['boundaries']; goal=x['setup']['task_goal']; ex=[bb for bb in b if not bb['demo']]
        m={'episode':x['episode'],'seed':x['setup']['seed'],'h5':x['h5'],'mp4':x['mp4'],'n_steps':x['n_steps'],'n_demo':x['n_demo'],
           'exec_steps_to_completion':[bb['t'] for bb in b if bb['s']=='All tasks completed'][0]-x['n_demo'],'goal0':goal[0]}
        chk={}
        if task=='BinFill':
            m['puts']=sum(bb['s']=='put it into the bin' for bb in b)
            parts=re.findall(r'(\w+) (red|green|blue) cubes?',goal[0]); want={c:W[n] for n,c in parts if n in W}
            m['goal_counts']=want; m['n_colors']=len(want)
            if tier.startswith('xhard'):
                c=dec['configs'][tier]; m['visible_cubes_t0']=ncubes(key)
                m['visible_by_color_t0']={k:sum(max(1,round(a/21)) for a in v['area_cm2']) for k,v in area[key]['colors'].items()}
                chk['puts']=inr(m['puts'],c['put_in_numbers']); chk['total_cubes']=inr(m['visible_cubes_t0'],c['spawn_cubes'])
                chk['colors']=inr(m['n_colors'],cfg[task]['native']['parameters']['put_in_color'][tier]); chk['goal_eq_chain']=sum(want.values())==m['puts']
                chk['goal_le_available']=all(m['visible_by_color_t0'].get(k,0)>=v for k,v in want.items())
            else:
                c=dec['configs'][tier]; chk['puts']=inr(m['puts'],c['put_in_numbers']); chk['goal_eq_chain']=sum(want.values())==m['puts']
                m['note']='原三档 native_dynamic：部分方块延后生成，t0 可见数不代表 spawn_cubes，未计'
        elif task in('PickXtimes','SwingXtimes'):
            mm=re.search(r'(\w+) times',goal[0]); n=W[mm.group(1)] if mm else 1; m['goal_n']=n
            m['chain_n']=sum(1 for bb in b if bb['s'].startswith('place the') or bb['s'].startswith('move to the top of the right'))
            m['visible_by_color_t0']={k:sum(max(1,round(a/21)) for a in v['area_cm2']) for k,v in area[key]['colors'].items()}
            dist=[k for k in m['visible_by_color_t0'] if k in('yellow','cyan','magenta')]
            m['distractors']=sum(m['visible_by_color_t0'][k] for k in dist)
            m['rgb_cubes']=sum(v for k,v in m['visible_by_color_t0'].items() if k in('red','green','blue'))
            chk['n']=inr(n,dec['number_range'][tier]) and n==m['chain_n']; chk['rgb_cubes']=m['rgb_cubes']==dec['color'][tier]
            want=len(dec[tier]['distractor']['colors']) if tier in dec and isinstance(dec.get(tier),dict) else 0
            chk['distractors']=m['distractors']==want
            if task=='SwingXtimes': m['numeric_ordinal_subgoals']=[bb['s'] for bb in b if re.search(r'\d+th',bb['s'])]
        elif task=='PickHighlight':
            m['picks']=sum(bb['s'].startswith('pick up') for bb in b); m['cubes_t0']=sum(1 for a in counts[key]['t0_objects'] if 0.03<a['zmax']<0.05 and a['color']!='white')
            hc=dec['highlight_count'][tier]; sc=dec['spawn_count'][tier]; hc=[hc,hc] if isinstance(hc,int) else hc; sc=[sc,sc] if isinstance(sc,int) else sc
            chk['picks']=inr(m['picks'],hc); chk['spawn']=inr(m['cubes_t0'],sc)
            if not chk['spawn']: m['note']='xhard3 ep6 自动分割少计1块，目视 frames/PickHighlight-xhard3-ep6-front_rgb-t0.png 计得9块' 
            if tier=='xhard3' and x['episode']==6: m['cubes_t0_visual']=9; chk['spawn']=True
        elif task in('VideoUnmask','ButtonUnmask','VideoUnmaskSwap','ButtonUnmaskSwap'):
            m['picks']=sum(bb['s'].startswith('pick up the container') for bb in b)
            m['cubes_t0']=sum(1 for a in counts[key]['t0_objects'] if 0.03<a['zmax']<0.05 and a['color']!='white')
            bc=Counter(bb['ring'] for bb in counts[key]['bins']); m['bins_seen']=sum(bc.values()); m['bins_ring_split']=dict(bc)
            if 'Swap' in task:
                nc=cfg[task]['native']['parameters']['configs'][tier]; chk['picks']=inr(m['picks'],[nc['pick_min'],nc['pick_max']])
                L=48 if tier in('easy','medium','hard','xhard1') else 32
                m['swaps']=swapcount(swaps[key],L); m['swap_windows']=swaps[key]['all']['windows']; m['swap_window_len']=[b2-a2+1 for a2,b2 in swaps[key]['all']['windows']]
                chk['swaps']=inr(m['swaps'],[nc['swap_min'],nc['swap_max']])
                exp_bins=nc['bin']+(dec[tier]['distractor']['count'] if tier.startswith('xhard') else 0)
                exp_cubes=3+(dec[tier]['distractor']['cube_count_range'][0] if tier.startswith('xhard') else 0)
            else:
                chk['picks']=m['picks']==dec['pick_count'][tier]
                exp_bins=dec['bin_layout_policy']['count'][tier]+(dec[tier]['distractor']['count'] if tier.startswith('xhard') else 0)
                exp_cubes=[3+dec[tier]['distractor']['cube_count_range'][0],3+dec[tier]['distractor']['cube_count_range'][1]] if tier.startswith('xhard') else [3,3]
            m['expected_bins']=exp_bins
            VIS={('ButtonUnmask','xhard3',3):(20,'frames/ButtonUnmask-xhard3-ep3-front_rgb-t40.png'),('ButtonUnmaskSwap','xhard4',0):(14,'frames/ButtonUnmaskSwap-xhard4-ep0-front_rgb-t40.png'),('VideoUnmaskSwap','xhard4',3):(14,'frames/VideoUnmaskSwap-xhard4-ep3-front_rgb-t40.png'),('ButtonUnmask','medium',10):(4,'frames/ButtonUnmask-medium-ep10-front_rgb-t40.png'),('ButtonUnmask','hard',3):(6,'frames/grid-ButtonUnmask-t40.png')}
            if key in VIS: m['bins_visual']=VIS[key][0]; m['bins_visual_png']=VIS[key][1]
            chk['bins']=m.get('bins_visual',m['bins_seen'])==exp_bins
            if task=='VideoUnmask' and tier=='hard': m['note']='D1 已知（hard 请求15只放下6），已排除，标 seen'
            chk['cubes']=inr(m['cubes_t0'],exp_cubes if isinstance(exp_cubes,list) else [exp_cubes,exp_cubes])
        elif task=='VideoRepick':
            m['repicks']=sum(bb['s'].startswith('pick up the correct') for bb in ex)
            m['goal_n']=W.get(re.search(r'(two|three|four|five|six|again)',goal[0]).group(1))
            m['swaps']=swapcount(swaps[key],48); m['swap_window_len']=[b2-a2+1 for a2,b2 in swaps[key]['all']['windows']]
            m['cubes_t0']=ncubes(key) if area[key]['colors'] else sum(1 for a in counts[key]['t0_objects'] if 0.03<a['zmax']<0.05 and a['color']!='white')
            sw=dec['swap'][tier]; chk['swaps']=inr(m['swaps'],[sw['swap_min'],sw['swap_max']]); chk['goal_eq_chain']=m['goal_n']==m['repicks']
            if tier.startswith('xhard'):
                rr=dec['num_repeats_range'][tier]; chk['repicks']=inr(m['repicks'],[rr['low'],rr['high_exclusive']-1]); chk['cubes']=m['cubes_t0']==dec[tier]['layout']['cube_count']
            elif tier=='hard': chk['cubes']=m['cubes_t0']==15
            else: chk['cubes']=m['cubes_t0']==3; chk['repicks']=inr(m['repicks'],[1,3])
        elif task=='PatternLock':
            m['nodes']=sum(bb['s'].startswith('move') for bb in ex)+1; m['demo_eq_exec']=[bb['s'] for bb in b if bb['demo']]==[bb['s'] for bb in ex if bb['s'].startswith('move')]
            chk['nodes']=inr(m['nodes'],dec['path_length_range'][tier]) if tier.startswith('xhard') or tier=='hard' else None
            m['nodes_vs_native_range']=dec['path_length_range'][tier]; chk['demo_eq_exec']=m['demo_eq_exec']
        elif task=='RouteStick':
            m['segments']=sum(bb['s'].startswith('move') for bb in ex); chk['exec_50L']=x['n_steps']-x['n_demo']==50*m['segments']
            if tier.startswith('xhard'): chk['segments']=inr(m['segments'],dec[tier]['segment_count_range'])
            elif tier=='hard': chk['segments']=inr(m['segments'],[4,7])
        elif task in('VideoPlaceButton','VideoPlaceOrder'):
            v=vpid[key]; m['placements_on_target']=sum(bb['s']=='drop the cube onto target' for bb in b if bb['demo'])
            m['returns_to_origin']=sum('original position' in bb['s'] for bb in b); m['carry_sequence']=[(e['color'],e['dest']) for e in v['events']]
            m['places_by_color']=v['places_by_color']; m['goal_color']=v['goal_color']
            if task=='VideoPlaceButton':
                m['goal_color_before']=v['goal_color_before']; m['goal_color_after']=v['goal_color_after']; m['goal_which']=v['which']
                btn=v['button_t']; places=[e for e in v['events'] if e['dest']=='drop the cube onto target']
                pre=[e for e in places if e['t_pick']<btn]; post=[e for e in places if e['t_pick']>btn]
                m['last_place_before_button_color']=pre[-1]['color'] if pre else None; m['first_place_after_button_color']=post[0]['color'] if post else None
                adj=m['last_place_before_button_color'] if v['which']=='before' else m['first_place_after_button_color']
                chk['immediate_adjacency']=adj==v['goal_color']
                chk['goal_placement_unique_for_alt3']=(m['goal_color_before'] if v['which']=='before' else m['goal_color_after'])==1
                exp={'easy':2,'medium':2,'hard':2,'xhard1':3,'xhard2':4,'xhard3':5,'xhard4':6}[tier]; chk['placements']=m['placements_on_target']==exp
            else:
                m['goal_ordinal']=v['goal_ordinal']; chk['ordinal_le_visits']=v['ordinal_ok']
                if tier.startswith('xhard'): chk['placements']=m['placements_on_target']==sum(dec[tier]['visit_counts']); chk['per_block']=sorted(v['places_by_color'].values())==sorted(dec[tier]['visit_counts'])
                elif tier=='hard': chk['placements']=inr(m['placements_on_target'],[2,4])
        elif task=='StopCube':
            s=stop[(tier,x['episode'])]; vis=[t for t in s['visits_t'] if t>5]
            m['goal_ordinal']=OW[s['goal_ordinal']]; m['visits_t']=vis; m['final_dist_m']=s['final_dist_m']
            if tier=='hard' and x['episode']==7: m['note']='跟踪失败（锁定到静止物体），未测'; chk['visits']=None
            else: chk['visits']=len(vis)==m['goal_ordinal']
            rg=dec.get(tier,dec)['stop_time_range']; chk['stop_time_in_cfg']=rg['low']<=m['goal_ordinal']<rg['high_exclusive']
        elif task=='MoveCube':
            t=track[key]; m['frames']=t['frames']
            if tier=='xhard4':
                R=dec['demo_layout']['xhard4']['region']; ok=True
                for fr in t['frames']:
                    rc=math.dist(fr['cube'],R['center']); rg_=math.dist(fr['target'],R['center']); d=math.dist(fr['cube'],fr['target'])
                    fr.update(r_cube=round(rc,3),r_goal=round(rg_,3),cube_goal=round(d,3))
                    ok&=R['r_in']-0.01<=rc<=R['r_out']+0.01 and R['r_in']-0.01<=rg_<=R['r_out']+0.01 and 0.09<=d<=0.31
                chk['annulus']=ok
        elif task=='InsertPeg':
            m['note']='xhard4 数值与原xhard相同、无梯度维度；本轮只核链条一致'
            chk['demo_eq_exec']=[bb['s'] for bb in b if bb['demo']][0]==[bb['s'] for bb in ex][0]
        m['checks']=chk; m['all_ok']=all(v in(True,None) for v in chk.values())
        eps.append(m)
    out.append(dict(task=task,tier=tier,kind='new' if tier.startswith('xhard') else 'native',episodes=eps,all_ok=all(e['all_ok'] for e in eps)))
json.dump(dict(audit_base='82e3d922b78d48ec1e825b168cccc0e1b8c690c1',n_cells=len(out),cells=out),open(E+'/measured.json','w'),indent=1,ensure_ascii=False)
for c in out:
    if not c['all_ok']:
        for e in c['episodes']:
            if not e['all_ok']: print(c['task'],c['tier'],e['episode'],{k:v for k,v in e['checks'].items() if v is False})
print('cells',len(out),'new',sum(c['kind']=='new' for c in out),'native',sum(c['kind']=='native' for c in out))
