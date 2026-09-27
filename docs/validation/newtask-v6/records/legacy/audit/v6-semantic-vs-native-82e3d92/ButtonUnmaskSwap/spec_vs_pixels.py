"""Read-only: check that the pixel location where each named cube is revealed equals the slot predicted by the
delivered spec swap sequence (slot pixel = initial centroid of the cube originally in that slot)."""
import json, os, numpy as np
OUT=os.path.dirname(os.path.abspath(__file__))
sp={(s['tier'],s['episode']):s for s in json.load(open(f'{OUT}/specs_newtier.json'))}
ct={(c['tier'],c['episode']):c for c in json.load(open(f'{OUT}/color_track.json'))}
res=[];ok=0;n=0;unk=0
for k,s in sp.items():
    c=ct[k]; col_of_bin={s['selected_bins'][i]:s['color_names'][i] for i in range(3)}
    bin_of_col={v:b for b,v in col_of_bin.items()}
    for p in c['picks']:
        b=bin_of_col[p['named']]; fs=s['final_slot_of_bin'][str(b)] if isinstance(list(s['final_slot_of_bin'].keys())[0],str) else s['final_slot_of_bin'][b]
        occupant=col_of_bin.get(fs)  # colour originally in that slot (None => empty bin_3 slot)
        rv=p['revealed'][p['named']]['centroid']
        if occupant is None:
            dmin=min(np.hypot(rv[0]-v[0],rv[1]-v[1]) for v in c['initial_centroids'].values())
            verdict='empty_slot_unverifiable' ; unk+=1; d=None
            verdict += f'(min dist to any init cube {dmin:.1f}px)'
        else:
            iv=c['initial_centroids'][occupant]; d=float(np.hypot(rv[0]-iv[0],rv[1]-iv[1])); n+=1
            verdict='match' if d<12 else 'MISMATCH'; ok+= d<12
        res.append(dict(tier=k[0],episode=k[1],named=p['named'],bin=b,final_slot=fs,slot_original_colour=occupant,reveal=rv,dist_px=d,verdict=verdict))
        print(k,p['named'],'bin',b,'->slot',fs,'orig',occupant,verdict,None if d is None else round(d,1))
print(f'SPEC_PIXEL_SLOT_MATCH matched={ok}/{n} empty_slot_unverifiable={unk}')
json.dump(res,open(f'{OUT}/spec_vs_pixels.json','w'),indent=1)
