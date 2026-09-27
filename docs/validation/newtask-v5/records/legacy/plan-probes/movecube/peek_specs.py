import json
rows=[json.loads(l) for l in open('scripts/configs/newtask-v4/v4-01/specs.jsonl')]
hdr=rows[0]
print(json.dumps(hdr['sampling_config']['MoveCube'],indent=1,ensure_ascii=False)[:4000])
mc=[r for r in rows[1:] if r.get('env')=='MoveCube' or r.get('env_id')=='MoveCube']
print(len(mc), list(rows[1].keys()))
