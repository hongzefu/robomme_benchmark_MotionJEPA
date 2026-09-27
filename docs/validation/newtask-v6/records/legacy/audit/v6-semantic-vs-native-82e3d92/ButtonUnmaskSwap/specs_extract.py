"""Read-only: pull delivered new-tier specs for ButtonUnmaskSwap and compute net slot permutation."""
import json, os
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/v6-01'
OUT=os.path.dirname(os.path.abspath(__file__))
def flat(d,p=''):
    o={}
    if isinstance(d,dict):
        for k,v in d.items(): o.update(flat(v,f'{p}.{k}' if p else k))
    else: o[p]=d
    return o
COL=['red','green','blue']
res=[]
for t in ['xhard1','xhard2','xhard3','xhard4']:
    for l in open(f'{ROOT}/{t}/specs.jsonl'):
        d=json.loads(l)
        if d.get('task')!='ButtonUnmaskSwap' or not d.get('selected') or d.get('episode') not in (0,3,6): continue
        f=flat(d['spec'])
        n=f['objects.n_swaps']; picks=f['objects.n_picks']
        names=[COL[i] for i in f['objects.color_order']]
        sel=f['objects.selected']
        # slot[b] = slot index currently occupied by bin b ; start slot b
        slot={b:b for b in range(4)}
        pairs=[]
        for k in range(n):
            a=int(f[f'actions.swap_pairs.{k}.initiator'].split('_')[1]); b=int(f[f'actions.swap_pairs.{k}.partner'].split('_')[1])
            pairs.append((a,b)); slot[a],slot[b]=slot[b],slot[a]
        hidden={names[i]:sel[i] for i in range(3)}
        moved={c:(b,slot[b]) for c,b in hidden.items()}
        picked=names[:picks]
        r=dict(tier=t,episode=d['episode'],seed=d['seed'],n_swaps=n,n_picks=picks,color_names=names,selected_bins=sel,
               swap_pairs=pairs,final_slot_of_bin=slot,identity_perm=all(slot[b]==b for b in range(4)),
               picked_targets_final_slot_changed={c:moved[c][1]!=moved[c][0] for c in picked},
               distractor_requested=f['objects.distractors.requested'],distractor_placed=f['objects.distractors.placed'],
               distractor_cube_count=f['objects.distractors.cube_count'],distractor_cube_colors=f['objects.distractors.cube_colors'],
               distractor_swap_pairs=f['actions.distractor_swap_pairs'],distractor_swap_balance=f['actions.distractor_swap_balance.counts'],
               swap_window=[f['actions.swap_window.start_step'],f['actions.swap_window.duration_steps']],
               swap_end=f['actions.swap_window.start_step']+n*f['actions.swap_window.duration_steps'],
               inner_counts=f['objects.swap_plan.counts'],graph=f['layout.inner_swap_graph'],layout_type=f['layout.type_choice'],
               bins_xy=[f[f'layout.bins.{i}'] for i in range(4)])
        res.append(r)
        print(t,d['episode'],'n',n,'pairs',pairs,'final',slot,'ID' if r['identity_perm'] else '','changed',r['picked_targets_final_slot_changed'],'dcube',r['distractor_cube_count'],r['distractor_placed'],'end',r['swap_end'])
json.dump(res,open(f'{OUT}/specs_newtier.json','w'),indent=1)
