import json, sys, h5py, collections
rows=json.load(open(sys.argv[1]))["rows"]
def dec(x): return x.decode() if isinstance(x,bytes) else str(x)
acc=collections.defaultdict(lambda:[0,0,0,0]); texts=collections.Counter()
for r in rows:
    if not r.get("ok") or r["task"] not in ("VideoRepick","VideoUnmaskSwap","VideoPlaceButton","VideoUnmask","VideoPlaceOrder"): continue
    f=h5py.File(r["h5"],"r"); g=f[[k for k in f if k.startswith("episode_")][0]]
    m = r["level"]=="mother"
    for k in g:
        if not k.startswith("timestep_"): continue
        d=bool(g[k]["info/is_video_demo"][()]); c=dec(g[k]["action/choice_action"][()]); s=dec(g[k]["info/simple_subgoal"][()])
        e = '"choice"' not in c or '"choice": ""' in c or '"choice": null' in c
        a=acc[(r["task"],m)]
        if d: a[0]+=e; a[1]+=1
        else:
            a[2]+=e; a[3]+=1
            if e and not m: texts[(r["task"],s)]+=1
for (t,m),a in sorted(acc.items()):
    print(f"{t} {'mother' if m else 'xhard '}: demo empty {a[0]}/{a[1]}  exec empty {a[2]}/{a[3]}")
print("派生档执行段空值的 subgoal：", texts.most_common(10))
