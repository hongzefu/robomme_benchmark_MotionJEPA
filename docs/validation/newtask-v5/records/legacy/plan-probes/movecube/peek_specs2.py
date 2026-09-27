import json
rows=[json.loads(l) for l in open('scripts/configs/newtask-v4/v4-01/specs.jsonl')]
mc=[r for r in rows[1:] if r.get('task')=='MoveCube']
print(len(mc))
r=mc[0]
print({k:v for k,v in r.items() if k!='spec'})
print(json.dumps(r['spec'],indent=1,ensure_ascii=False)[:5000])
