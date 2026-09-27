import h5py,glob,json
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
files=sorted(glob.glob(R+'/artifacts/newtask-v6/v6-s2-20260926-01/episodes/MoveCube-*/hdf5_files/*.h5'))+sorted(glob.glob(R+'/artifacts/newtask-v6/v1/base/B/MoveCube_episode_*/hdf5_files/*.h5'))+sorted(glob.glob(R+'/artifacts/newtask-v6/v6-01/xhard4/rollout/run1/episodes/MoveCube_*/hdf5_files/*.h5'))
out=[]
for h in files:
    f=h5py.File(h,'r'); ep=f[list(f)[0]]
    ts=sorted([k for k in ep if k.startswith('timestep_')],key=lambda k:int(k.split('_')[1]))
    miss=[]
    for i,k in enumerate(ts):
        info=ep[k]['info']
        if not info['is_subgoal_boundary'][()]: continue
        g=info['grounded_subgoal'][()]; g=g.decode() if isinstance(g,bytes) else g
        s=info['simple_subgoal'][()]; s=s.decode() if isinstance(s,bytes) else s
        if s not in('static','All tasks completed','NO RECORD') and '<' not in g: miss.append(dict(step=i,simple=s,grounded=g,demo=bool(info['is_video_demo'][()])))
    out.append(dict(h5=h.replace(R+'/',''),n_boundary_missing_coords=len(miss),missing=miss)); print(h.split('/')[-1],len(miss),miss)
json.dump(out,open(R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube/grounding_missing_coords_scan.json','w'),indent=1)
