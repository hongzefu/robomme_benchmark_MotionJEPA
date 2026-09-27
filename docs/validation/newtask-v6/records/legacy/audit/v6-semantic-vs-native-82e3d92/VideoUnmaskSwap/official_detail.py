import h5py
f=h5py.File('/data/hongzefu/robomme_data_h5/record_dataset_VideoUnmaskSwap.h5','r')
def s(x):
    x=x[()]; return x.decode() if isinstance(x,bytes) else x
for k in ['episode_21','episode_81']:
    g=f[k]; ts=sorted(int(t.split('_')[1]) for t in g if t.startswith('timestep_'))
    prev=None
    print(k, g['setup/task_goal'][()])
    for t in ts:
        gs=s(g[f'timestep_{t}']['info/grounded_subgoal'])
        if gs!=prev: print('  ',t,gs); prev=gs
