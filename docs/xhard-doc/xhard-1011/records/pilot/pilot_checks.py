"""小规模实测的 choice 对齐与 8 帧严格遗漏检查（只读 H5）。口径沿用 artifacts/audit-1011/M4/skip8.py。"""
import json, math, re, sys, h5py, collections
rows = json.load(open(sys.argv[1]))["rows"]
TAIL = "All tasks completed"
LONGEST = {"BinFill":"xhard20","PickXtimes":"xhard20","SwingXtimes":"xhard20","StopCube":"xhard20","VideoUnmaskSwap":"xhard20",
 "ButtonUnmaskSwap":"xhard20","VideoRepick":"xhard20","PatternLock":"xhard20","RouteStick":"xhard20",
 "VideoUnmask":"xhard14","ButtonUnmask":"xhard14","VideoPlaceButton":"xhard14","PickHighlight":"xhard18","VideoPlaceOrder":"xhard12"}
def dec(x): return x.decode() if isinstance(x, bytes) else str(x)
def load(path):
    f = h5py.File(path, "r"); g = f[[k for k in f if k.startswith("episode_")][0]]
    ts = sorted([k for k in g if k.startswith("timestep_")], key=lambda s: int(s.split("_")[1]))
    sub=[dec(g[k]["info/simple_subgoal"][()]) for k in ts]; demo=[bool(g[k]["info/is_video_demo"][()]) for k in ts]
    ch=[dec(g[k]["action/choice_action"][()]) for k in ts]
    swap_times = None
    return sub, demo, ch
def segs(sub, demo):
    out=[]; 
    for i,(s,d) in enumerate(zip(sub,demo)):
        if out and out[-1]["text"]==s and out[-1]["demo"]==d: out[-1]["len"]+=1
        else: out.append(dict(text=s,demo=d,start=i,len=1))
    return out
def units(sg):
    ex=[x for x in sg if not x["demo"] and x["text"]!=TAIL]; u=[]; i=0
    while i<len(ex):
        a=ex[i]
        if a["text"].startswith("pick up") and i+1<len(ex) and re.match(r"(place|put|drop)",ex[i+1]["text"]):
            u.append((a["start"],ex[i+1]["start"]+ex[i+1]["len"])); i+=2
        else: u.append((a["start"],a["start"]+a["len"])); i+=1
    return u
SW={"VideoUnmaskSwap":{"xhard12":4,"xhard14":5,"xhard16":7,"xhard18":9,"xhard20":11},
    "ButtonUnmaskSwap":{"xhard12":4,"xhard14":6,"xhard16":8,"xhard18":10,"xhard20":12},
    "VideoRepick":{"xhard12":5,"xhard14":7,"xhard16":10,"xhard18":13,"xhard20":15}}
def swaps(t, lvl, sg):
    if t in ("VideoUnmaskSwap","ButtonUnmaskSwap"): return [(64+50*k,64+50*(k+1)) for k in range(SW[t][lvl])]
    if t=="VideoRepick":
        st=[x for x in sg if x["demo"] and x["text"]=="static"]
        return [(st[1]["start"]+50*k, st[1]["start"]+50*(k+1)) for k in range(SW[t][lvl])] if len(st)>1 else []
    if t in ("VideoPlaceButton","VideoPlaceOrder"):
        st=[x for x in sg if x["demo"] and x["text"]=="static"]
        return [(st[-1]["start"], st[-1]["start"]+50)] if st else []
    return []
ground=collections.defaultdict(lambda:[0,0]); bus_btn=[0,0,0]; e8=[]
for r in rows:
    if not r.get("ok") or not r.get("h5"): continue
    sub,demo,ch=load(r["h5"]); t=r["task"]
    empty=sum(1 for c in ch if not c or c in ("None","{}","") or '"choice": ""' in c or '"choice": null' in c)
    ground[(t,r["level"]=="mother")][0]+=empty; ground[(t,r["level"]=="mother")][1]+=len(ch)
    if t=="ButtonUnmaskSwap" and r["level"]!="mother":
        for s,c in zip(sub,ch):
            if s.startswith("press the"):
                bus_btn[0]+=1; ok = (s=="press the first button" and '"A"' in c) or (s=="press the second button" and '"B"' in c)
                bus_btn[1]+= (not ok)
        bus_btn[2]+=1
    if LONGEST.get(t)==r["level"]:
        sg=segs(sub,demo); T=len(sub); fp=[math.floor(i*(T-1)/7+0.5) for i in range(8)]
        u=units(sg); sw=swaps(t,r["level"],sg)
        um=sum(not any(a<=x<b for x in fp) for a,b in u); sm=sum(not any(a<=x<b for x in fp) for a,b in sw)
        e8.append((t,r["seed"],r["level"],T,len(u),um,len(sw),sm))
print("choice 空值比例（母档 vs 派生档）：")
bad=0
for t in sorted({k[0] for k in ground}):
    m=ground[(t,True)]; x=ground[(t,False)]
    rm=m[0]/m[1] if m[1] else 0; rx=x[0]/x[1] if x[1] else 0
    flag = rx>rm+1e-9 and x[1]>0
    bad+=flag
    print(f"  {t}: mother {rm:.3f} ({m[0]}/{m[1]})  xhard {rx:.3f} ({x[0]}/{x[1]}){'  <-- 高于母档' if flag else ''}")
print(f"XHARD_CHOICE_GROUNDING={'PASS' if bad==0 and bus_btn[1]==0 else 'FAIL'} files={bus_btn[2]} button_steps={bus_btn[0]} empty={bus_btn[1]} tasks_over_mother={bad}")
print("8 帧严格遗漏（最长一档）： task seed level T units unit_miss swaps swap_miss")
fail=0; tasks=set()
for e in e8:
    miss=e[5]+e[7]; tasks.add(e[0]); fail+= miss==0
    print("  ",*e, "miss="+str(miss))
print(f"XHARD_8FRAME_LONGEST={'PASS' if fail==0 else 'FAIL'} tasks={len(tasks)} episodes={len(e8)} zero_miss={fail}")
