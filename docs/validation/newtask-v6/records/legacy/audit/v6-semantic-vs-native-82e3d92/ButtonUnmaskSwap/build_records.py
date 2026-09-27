"""Merge per-check JSONs into records.json (read-only on inputs)."""
import json, os
E=os.path.dirname(os.path.abspath(__file__))
L=lambda n:json.load(open(f'{E}/{n}'))
key=lambda c:(c['tier'],c['episode'])
raw=L('records_raw.json'); sp={key(s):s for s in L('specs_newtier.json')}
ct={key(c):c for c in L('color_track.json')}; idle={key(c):c for c in L('second_button_idle.json')}
dc={key(c):c for c in L('distractor_count.json')}; bp={key(c):c for c in L('button_press.json')}
mp={key(c):c for c in L('mp4_check.json')}; svp=L('spec_vs_pixels.json')
out=[]
for r in raw:
    k=key(r)
    out.append(dict(tier=r['tier'],episode=r['episode'],seed=r['seed_attr'],native=r.get('native',False),h5=r['h5'],mp4_path=r['mp4'],
        task_goal=r['task_goal'],choices=r['choices'],n_steps=r['n_steps'],last_completed=r['last_completed'],
        segments=[{x:s[x] for x in ('t','subgoal','choice','grounded')} for s in r['segments']],
        spec=sp.get(k),color_track=ct[k],second_button_segment=idle[k],distractor_cube_blobs=dc[k],button_press=bp[k],mp4_check=mp[k],
        spec_vs_pixels=[x for x in svp if key(x)==k]))
json.dump(dict(audit_base='82e3d922b78d48ec1e825b168cccc0e1b8c690c1',env='ButtonUnmaskSwap',episodes=out),open(f'{E}/records.json','w'),indent=1)
print(len(out))
