"""Read-only semantic-vs-visual analysis of VPO episodes (h5py/numpy/cv2 only)."""
import h5py, json, re, cv2, numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoPlaceOrder'
D=json.load(open(f'{E}/raw_extract.json'))
ORD={'first':1,'second':2,'third':3,'fourth':4,'fifth':5}
CFG={'xhard1':[2,3],'xhard2':[3,3],'xhard3':[3,4],'xhard4':[4,4]}
def rgb(g,t): return g[f'timestep_{t}/obs/front_rgb'][()]
def coord(s):
    m=re.search(r'<(\d+), (\d+)>',s); return (int(m.group(1)),int(m.group(2))) if m else None
def masks(im):
    im=im.astype(int); r,g,b=im[...,0],im[...,1],im[...,2]
    return {'red':(r>150)&(g<60)&(b<60),'green':(g>150)&(r<80)&(b<80),'blue':(b>150)&(r<60)&(g<60),
            'purple':(r>120)&(b>150)&(g<130)&(b-g>60)}
def blobs(m,minarea=15):
    n,l,st,c=cv2.connectedComponentsWithStats(m.astype(np.uint8),8)
    return [(float(c[i][1]),float(c[i][0]),int(st[i][4])) for i in range(1,n) if st[i][4]>=minarea]  # (row,col,area)
def cube_pos(im,color):
    b=blobs(masks(im)[color],8)
    if not b: return None
    b=max(b,key=lambda x:x[2]); return (round(b[0],1),round(b[1],1))
def targets(im):
    m=masks(im)['purple'].astype(np.uint8)
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    return [(round(r,1),round(c,1),a) for r,c,a in blobs(m,30)]
def color_at(im,rc):
    r,c=rc; best=None
    for col in ('red','green','blue'):
        m=masks(im)[col][max(0,r-6):r+7,max(0,c-6):c+7].sum()
        if best is None or m>best[1]: best=(col,int(m))
    return best
def dist(a,b): return float(np.hypot(a[0]-b[0],a[1]-b[1]))
recs=[]
for ep in D:
    f=h5py.File(ep['h5'],'r'); g=f[[k for k in f.keys() if k.startswith('episode_')][0]]
    goal=ep['setup']['task_goal'][0]
    m=re.search(r'place the (\w+) cube on the (\w+) target',goal); lang_color,lang_ord=m.group(1),ORD[m.group(2)]
    im0=rgb(g,0); T0=targets(im0)
    cubes0={c:cube_pos(im0,c) for c in ('red','green','blue')}
    segs=ep['segments']; demo=[s for s in segs if s['demo']]
    # parse demo blocks
    blocks=[]; cur=None; button_after=None; nvis=0
    for s in demo:
        txt=s['grounded']
        if txt.startswith('pick up the cube'):
            pc=coord(txt); col=None
            if pc: col=color_at(rgb(g,s['start']),pc)
            if cur is None: cur={'pick':pc,'color_pick':col,'visits':[],'end':None}
            cur.setdefault('picks',[]).append((s['start'],pc,col))
        elif txt.startswith('drop the cube onto target'):
            cur['visits'].append({'t_end':s['end'],'coord':coord(txt)}); nvis+=1
        elif txt.startswith('put the cube back') or txt.startswith('drop the cube onto table'):
            cur['end']=txt.split(' at')[0]; cur['t_end']=s['end']; blocks.append(cur); cur=None
        elif txt.startswith('press the button'): button_after=nvis
    # color of each block from picks with coords (majority)
    for b in blocks:
        cols=[p[2][0] for p in b['picks'] if p[2] and p[2][1]>5]
        b['color']=max(set(cols),key=cols.count) if cols else None
        # visual: at each drop end, which purple target is the cube of that color on
        for v in b['visits']:
            cp=cube_pos(rgb(g,v['t_end']),b['color']) if b['color'] else None
            v['cube_px']=cp
            v['target_idx_t0']=min(range(len(T0)),key=lambda i:dist(T0[i],cp)) if cp and T0 else None
            v['cube_to_target_px']=round(dist(T0[v['target_idx_t0']],cp),1) if cp and T0 else None
        cp_end=cube_pos(rgb(g,b['t_end']),b['color']) if b['color'] else None
        b['end_cube_px']=cp_end; b['end_vs_t0_px']=round(dist(cp_end,cubes0[b['color']]),1) if cp_end and cubes0.get(b['color']) else None
    exec_segs=[s for s in segs if not s['demo']]
    ex_pick=coord(exec_segs[0]['grounded']); t_ex=ep['first_nondemo']
    ex_color=color_at(rgb(g,t_ex),ex_pick) if ex_pick else None
    ex_tgt=next((coord(s['grounded']) for s in exec_segs if s['grounded'].startswith('place') and coord(s['grounded'])),None)
    ans=[b for b in blocks if b['color']==lang_color]
    ans_b=ans[0] if ans else None
    P_idx=ans_b['visits'][lang_ord-1]['target_idx_t0'] if ans_b and len(ans_b['visits'])>=lang_ord else None
    # swap detection: second static start = boundary between last demo seg end and exec start
    last_demo_end=demo[-1]['end']
    bnds=[b for b in ep['boundaries'] if demo[-1]['start']<b<t_ex]
    s0=bnds[0] if bnds else None
    swap={}
    if s0:
        pre=targets(rgb(g,s0)); mid=targets(rgb(g,s0+25)); post=targets(rgb(g,t_ex))
        moved=[i for i,tp in enumerate(T0) if min([dist(tp,x) for x in mid]+[99])>6]
        still_pre=[round(min([dist(tp,x) for x in post]+[99]),1) for tp in T0]
        swap={'swap_start':s0,'n_targets_t0':len(T0),'moved_t0_idx_mid':moved,'t0_to_post_min_px':still_pre}
    # expected post-swap location of answer target
    exp=None
    if P_idx is not None:
        mv=swap.get('moved_t0_idx_mid',[])
        if len(mv)==2 and P_idx in mv: exp=[i for i in mv if i!=P_idx][0]
        else: exp=P_idx
    tf=ep['n_steps']-1; imf=rgb(g,tf)
    fin=cube_pos(imf,lang_color)
    fin_idx=min(range(len(T0)),key=lambda i:dist(T0[i],fin)) if fin else None
    third=[c for c in ('red','green','blue') if c not in [b['color'] for b in blocks] and cubes0.get(c)]
    third_move={c:round(dist(cubes0[c],cube_pos(rgb(g,t_ex),c) or (999,999)),1) for c in third}
    r=dict(tier=ep['tier'],episode=ep['episode'],seed=ep['setup']['seed'],h5=ep['h5'],mp4=ep['mp4'],goal=ep['setup']['task_goal'],
        lang_color=lang_color,lang_ordinal=lang_ord,n_steps=ep['n_steps'],first_exec_step=t_ex,
        targets_t0=T0,cubes_t0=cubes0,
        demo_blocks=[dict(color=b['color'],picks=[(p[0],p[1],p[2]) for p in b['picks']],visits=b['visits'],end=b['end'],t_end=b['t_end'],end_vs_t0_px=b['end_vs_t0_px']) for b in blocks],
        visit_counts=[len(b['visits']) for b in blocks],button_after_nth_visit=button_after,
        exec_pick=ex_pick,exec_pick_color=ex_color,exec_target_grounded=ex_tgt,
        answer_target_t0_idx=P_idx,swap=swap,expected_answer_target_post_swap_idx=exp,
        final_cube_px=fin,final_nearest_t0_target_idx=fin_idx,
        final_cube_to_expected_px=round(dist(fin,T0[exp]),1) if fin and exp is not None else None,
        exec_target_grounded_to_expected_px=round(dist(ex_tgt,T0[exp]),1) if ex_tgt and exp is not None else None,
        non_demo_cubes=third,non_demo_cube_shift_px=third_move,
        checks=dict(color_match=(ex_color[0]==lang_color if ex_color else None),
                    answer_cube_demoed=bool(ans_b),
                    visit_counts_ok=(sorted(len(b['visits']) for b in blocks)==sorted(CFG[ep['tier']]) if ep['tier'] in CFG else (len(blocks)==1 and 2<=len(blocks[0]['visits'])<=4)),
                    ordinal_in_range=(ans_b is not None and lang_ord<=len(ans_b['visits'])),
                    final_on_expected=(fin_idx==exp)))
    recs.append(r)
    print(r['tier'],r['episode'],lang_color,lang_ord,'blocks',[(b['color'],len(b['visits']),b['end'][:12] if b['end'] else None,b['end_vs_t0_px']) for b in blocks],
          'btn',button_after,'P',P_idx,'swap',swap.get('moved_t0_idx_mid'),'exp',exp,'fin',fin_idx,r['final_cube_to_expected_px'],'exgr',r['exec_target_grounded_to_expected_px'],
          'nT',len(T0),'3rd',third_move,r['checks'])
json.dump(recs,open(f'{E}/records.json','w'),indent=1,default=str)
