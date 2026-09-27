"""只读审计：比对各环境 native_blocks(cls) 与 newtask-v5 快照的 decision/native 是否逐字相同。"""
import importlib, json, sys
sys.path.insert(0, "src")
sc = json.load(open("scripts/configs/newtask-v5/sampling_config.json"))["tasks"]
norm = lambda o: json.loads(json.dumps(o))
for t in sc:
    m = importlib.import_module(f"robomme.robomme_env.{t}")
    cls = getattr(m, t)
    fn = getattr(m, "native_blocks", None)
    if fn is None: print(t, "无 native_blocks"); continue
    dec, nat = fn(cls)
    print(t, "decision相同" if norm(dec)==sc[t].get("decision") else "decision不同", "native相同" if norm(nat)==sc[t].get("native") else "native不同")
