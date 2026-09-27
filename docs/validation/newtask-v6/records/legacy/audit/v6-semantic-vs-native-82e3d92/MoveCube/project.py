import h5py,json,numpy as np
R='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
specs={}
for l in open(R+'/artifacts/newtask-v6/v6-01/xhard4/specs.jsonl'):
    d=json.loads(l)
    if d.get('task')=='MoveCube' and d.get('selected'): specs[d['episode']]=d['spec']
idx=json.load(open(R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json'))['MoveCube']
out={}
for it in idx:
    sp=specs[it['episode']]; f=h5py.File(it['h5'],'r'); ep=f[list(f)[0]]
    K=ep['setup/front_camera_intrinsic'][()]; Ex=ep['timestep_0/obs/front_camera_extrinsic'][()]
    def proj(x,y,z):
        p=K@(Ex@np.array([x,y,z,1.0])); return [round(float(p[0]/p[2]),1),round(float(p[1]/p[2]),1)]
    o={}
    for seg in ('demo','execution'):
        L=sp['layout'][seg]; c=L['cube_pose']; g=L['goal_xy']; po=L['peg_offsets']; yaw=L['peg_yaw']
        root=np.array([po[1],po[2]]); u=np.array([np.cos(yaw),np.sin(yaw)])
        grasp=root-0.1*u
        cg=float(np.hypot(c[0]-g[0],c[1]-g[1]))
        o[seg]=dict(cube_world=c,goal_world=g,peg_root=root.tolist(),peg_yaw=yaw,peg_grasp=grasp.tolist(),
                   cube_px=proj(c[0],c[1],0.02),goal_px=proj(g[0],g[1],0.0),peg_grasp_px=proj(*grasp,0.01),peg_root_px=proj(*root,0.01),
                   cube_goal_dist_m=round(cg,4),
                   cube_r_center=round(float(np.hypot(c[0]+0.06,c[1])),4),goal_r_center=round(float(np.hypot(g[0]+0.06,g[1])),4),grasp_r_center=round(float(np.hypot(grasp[0]+0.06,grasp[1])),4),
                   dy_cube_minus_goal=round(c[1]-g[1],4))
    o['way_idx']=sp['initializations']; o['extrinsic_changes']=bool(not np.allclose(Ex, ep['timestep_%d/obs/front_camera_extrinsic'%(len([k for k in ep if k.startswith('timestep_')])-1)][()]))
    out[it['episode']]=o
    print(it['episode'],json.dumps(o,indent=0)[:2500])
json.dump(out,open(R+'/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube/xhard4_spec_projection.json','w'),indent=1)
