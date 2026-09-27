# 在分歧点之后枚举随机流里的候选，找出真实 env 接受的是第几次 trial，列出真实 env 拒绝而复刻接受的候选
import json, sys, numpy as np, torch
sys.path.insert(0, '/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster')
import binfill_sampler as bs
from robomme.robomme_env.utils.object_generation import _obb2d_intersect, _build_new_cube_obb2d
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
rows=[json.loads(l) for l in open(f'{ROOT}/scripts/configs/newtask-v4/v4-01/specs.jsonl')][1:]
b={r['seed']:r for r in rows if r.get('task')=='BinFill'}
for seed in [4400100, 4400500, 4400800, 4400200]:
    L=b[seed]['spec']['layout']; o=b[seed]['spec']['objects']
    # 用 spec 的位置逐块重放随机流：每块枚举 trial 直到命中 spec 值
    g=torch.Generator().manual_seed(seed)
    out=bs.sample_layout(generator=torch.Generator().manual_seed(seed), max_trials=0) # 仅用于 meta（max_trials=0 ⇒ None）
    # 手工重走 meta 抽样
    g=torch.Generator().manual_seed(seed)
    torch.rand(2,generator=g); [torch.rand(1,generator=g) for _ in range(3)]
    cp=torch.randperm(3,generator=g).tolist(); pic=torch.randint(2,4,(1,),generator=g).item()
    active=cp[:pic]
    if pic==1: torch.randint(5,8,(1,),generator=g)
    else:
        tt=torch.randint(5,8,(1,),generator=g).item(); [torch.randint(0,len(active),(1,),generator=g) for _ in range(tt)]
    torch.randint(12,13,(1,),generator=g)
    spawn=[0,0,0]; tgt=o['target_numbers']
    for i in cp: spawn[i]=max(tgt[i],1)
    rem=12-sum(spawn); [torch.randint(0,3,(1,),generator=g) for _ in range(rem)]
    tasks=[(bs.COLORS[c],k) for c in range(3) for k in range(o['spawn_numbers'][c])]
    order=torch.randperm(len(tasks),generator=g).tolist(); assert order==o['spawn_order']
    tasks=[tasks[i] for i in order]
    lo=bs.REGION_C-bs.REGION_H+bs.HS; hi=bs.REGION_C+bs.REGION_H-bs.HS
    bx,by=0.15+L['board']['offsets'][0], L['board']['offsets'][1]
    obst=[bs.create_button_obb(center_xy=tuple(L['button_xy']),half_size=0.05625)]+bs.board_strips(bx,by)
    placed=[]
    for si,(col,k) in enumerate(tasks):
        v=L['cubes'][f'{col}_{k}']
        cands=[]
        for t in range(400):
            u1=torch.rand(1,generator=g).item(); u2=torch.rand(1,generator=g).item()
            x=float(lo[0]+u1*(hi[0]-lo[0])); y=float(lo[1]+u2*(hi[1]-lo[1])); yaw=float(torch.rand(1,generator=g).item()*2*np.pi)
            cands.append((x,y,yaw))
            if x==v[0] and y==v[1] and yaw==v[2]: break
        else:
            print(seed,'no match for',col,k); break
        n=len(cands)
        mine_acc=[]
        for (x,y,yaw) in cands[:-1]:
            cn,An,hn=_build_new_cube_obb2d(x,y,bs.HS,yaw,pad_xy=bs.MIN_GAP)
            hit=[i for i,(c,A,h) in enumerate(obst) if _obb2d_intersect(c,A,h,cn,An,hn)]
            if not hit: mine_acc.append((round(x,4),round(y,4),round(yaw,3)))
        if mine_acc:
            print(seed,'cube',si,col,k,'real trials',n,'mine would accept:',mine_acc[:3])
            print('    placed so far', [(round(p[0],3),round(p[1],3)) for p in placed], 'button',np.round(L['button_xy'],3),'board',round(bx,3),round(by,3))
        placed.append(v)
        obst.append(bs.placed_cube_obb(*v))
