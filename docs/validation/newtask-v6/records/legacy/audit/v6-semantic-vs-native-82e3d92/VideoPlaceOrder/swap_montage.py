import h5py, json, cv2, numpy as np
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/VideoPlaceOrder'
R=json.load(open(f'{E}/records.json'))
sel=[r for r in R if r['swap'].get('moved_t0_idx_mid') and (r['tier'].startswith('xhard') or r['tier']=='hard')]
rows=[]
for r in sel:
    f=h5py.File(r['h5'],'r'); g=f[[k for k in f.keys() if k.startswith('episode_')][0]]
    s0=r['swap']['swap_start']; tex=r['first_exec_step']; tf=r['n_steps']-1
    ts=[0,s0,s0+15,s0+30,tex,tf]; T0=r['targets_t0']; P=r['answer_target_t0_idx']; X=r['expected_answer_target_post_swap_idx']
    panels=[]
    for i,t in enumerate(ts):
        im=cv2.cvtColor(g[f'timestep_{t}/obs/front_rgb'][()],cv2.COLOR_RGB2BGR).copy()
        for k,tp in enumerate(T0):
            cv2.putText(im,str(k),(int(tp[1])-3,int(tp[0])+18),cv2.FONT_HERSHEY_SIMPLEX,0.35,(0,255,255),1)
        if i<=1 and P is not None: cv2.circle(im,(int(T0[P][1]),int(T0[P][0])),13,(0,255,255),1)
        if i>=4 and X is not None: cv2.circle(im,(int(T0[X][1]),int(T0[X][0])),13,(0,255,0),1)
        cv2.putText(im,f"{r['tier']} ep{r['episode']} t={t}",(3,12),cv2.FONT_HERSHEY_SIMPLEX,0.38,(255,255,255),1)
        if i==0: cv2.putText(im,f"{r['lang_color']} #{r['lang_ordinal']}",(3,26),cv2.FONT_HERSHEY_SIMPLEX,0.38,(255,255,255),1)
        panels.append(im[0:200])
    rows.append(np.concatenate(panels,1))
for j in range(0,len(rows),5):
    cv2.imwrite(f'{E}/frames/swap_montage_{j//5}.png',np.concatenate(rows[j:j+5],0))
print(len(rows))
