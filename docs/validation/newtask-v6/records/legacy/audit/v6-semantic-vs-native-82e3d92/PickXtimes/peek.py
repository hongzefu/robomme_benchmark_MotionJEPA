import h5py,sys,numpy as np
f=h5py.File(sys.argv[1],'r')
ep=f[list(f.keys())[0]]
s=ep['setup']
for k in s: 
    v=s[k][()]
    print(k, v if not isinstance(v,np.ndarray) or v.dtype==object else v.shape)
ts=sorted([k for k in ep if k.startswith('timestep_')],key=lambda x:int(x.split('_')[1]))
print(len(ts))
prev=None
for t in ts:
    g=ep[t]
    ss=g['info/simple_subgoal'][()]; gs=g['info/grounded_subgoal'][()]; ca=g['action/choice_action'][()]
    b=g['info/is_subgoal_boundary'][()]; vd=g['info/is_video_demo'][()]
    key=(ss,gs,ca,vd)
    if key!=prev or b:
        print(t,b,vd,ss,'|',gs,'|',ca,'|',g['info/simple_subgoal_online'][()],'|',g['info/grounded_subgoal_online'][()])
    prev=key
