import h5py,json,sys
E='/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/MoveCube'
recs={r['tag']:r for r in json.load(open(E+'/records.json'))}
for tag in sys.argv[1:]:
    r=recs[tag]; f=h5py.File(r['h5'],'r'); ep=f[list(f)[0]]; n=r['n_steps']
    for k in list(range(r['demo_end']['step']-6,r['demo_end']['step']+2))+list(range(r['exec_done']['step']-8,n)):
        g=ep[f'timestep_{k}']
        print(tag,k,'gs',[round(x,4) for x in g['obs/gripper_state'][()].tolist()],'close',bool(g['obs/is_gripper_close'][()]),'jointA',[round(x,4) for x in g['action/joint_action'][()].tolist()][-1],'done',bool(g['info/is_completed'][()]),'bd',bool(g['info/is_subgoal_boundary'][()]),g['info/simple_subgoal'][()].decode()[:20])
