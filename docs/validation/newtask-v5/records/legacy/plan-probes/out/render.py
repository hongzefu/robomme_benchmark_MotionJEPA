import json,sys
def render(o,ind=0):
    p="  "*ind
    out=[]
    if isinstance(o,dict):
        for k,v in o.items():
            if isinstance(v,(dict,list)):
                out.append(f"{p}## {k}"); out+=render(v,ind+1)
            else:
                out.append(f"{p}- {k}: {v}")
    elif isinstance(o,list):
        for i,v in enumerate(o):
            if isinstance(v,(dict,list)):
                out.append(f"{p}[{i}]"); out+=render(v,ind+1)
            else: out.append(f"{p}* {v}")
    return out
for fn in sys.argv[1:]:
    d=json.load(open(fn))
    d.pop("scratch_files",None) if False else None
    open(fn.replace(".json",".txt"),"w").write("\n".join(render(d)))
