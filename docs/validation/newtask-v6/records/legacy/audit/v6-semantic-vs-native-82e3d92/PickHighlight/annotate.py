import h5py,json,numpy as np,cv2,os
D=os.path.dirname(os.path.abspath(__file__)); R=json.load(open(D+'/records_raw.json'))
os.makedirs(D+'/frames',exist_ok=True); summ=[]
for r in R:
    f=h5py.File(r['h5'],'r'); ep=f[list(f.keys())[0]]
    im=cv2.resize(ep['timestep_30/obs/front_rgb'][()],(512,512),interpolation=cv2.INTER_NEAREST).copy()
    pick_segs=[s for s in r['segments'] if s['simple'].startswith('pick up')]
    chk=[]
    if r['kind']=='new':
        tg={t['cube']:t for t in r['targets']}
        for k,cid in enumerate(r['highlight_ids']):
            u,v=tg[cid]['uv']; cv2.circle(im,(int(u*2),int(v*2)),22,(0,255,0),2); cv2.putText(im,f'T{k+1}:c{cid}',(int(u*2)+14,int(v*2)-14),0,0.45,(0,255,0),1)
            pt=json.loads(pick_segs[k]['choice_action'])['point']
            chk.append({'ordinal':k+1,'cube':cid,'target_uv':[u,v],'choice_point_rowcol':pt,'err_px':round(float(np.hypot(pt[1]-u,pt[0]-v)),1),'grasp_cube':r['grasps'][k+1]['nearest_initial_cube']})
        for n in r['non_targets']:
            u,v=n['uv']; cv2.drawMarker(im,(int(u*2),int(v*2)),(255,0,0),cv2.MARKER_TILTED_CROSS,20,2)
        tag=f"new_{r['difficulty']}_ep{r['episode']}"
    else:
        tg=[c for c in r['detected_cubes'] if c['max_white_ring_frac_10_100']>0.5]
        for c in r['detected_cubes']:
            u,v=c['uv']; col=(0,255,0) if c in tg else (255,0,0)
            cv2.circle(im,(int(u*2),int(v*2)),22,col,2)
        for k,s in enumerate(pick_segs):
            pt=json.loads(s['choice_action'])['point']
            ds=[np.hypot(pt[1]-c['uv'][0],pt[0]-c['uv'][1]) for c in tg]
            chk.append({'ordinal':k+1,'subgoal':s['simple'],'choice_point_rowcol':pt,'nearest_white_ringed_cube_color':tg[int(np.argmin(ds))]['color'] if tg else None,'err_px':round(float(min(ds)),1) if ds else None})
        tag=f"native_{r['difficulty']}_ep{r['episode']}"
    cv2.putText(im,tag+' t=30 green=target red=non',(5,20),0,0.5,(255,255,0),1)
    p=D+f'/frames/{tag}_t30_annot.png'; cv2.imwrite(p,cv2.cvtColor(im,cv2.COLOR_RGB2BGR))
    r['choice_point_check']=chk; r['annotated_png']=p; f.close()
    print(tag,[(c['ordinal'],c.get('cube',c.get('nearest_white_ringed_cube_color')),c['err_px'],c.get('grasp_cube')) for c in chk])
json.dump(R,open(D+'/records.json','w'),indent=1,ensure_ascii=False)
