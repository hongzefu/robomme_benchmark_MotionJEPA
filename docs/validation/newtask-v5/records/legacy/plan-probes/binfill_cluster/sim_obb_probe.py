# 在仿真器里 reset 一次 BinFill xhard，猴补丁记录每个已放方块的真实 2D OBB（只在本进程内存，不写仓库）
import sys, json, pickle, numpy as np
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
sys.path.insert(0, ROOT); sys.path.insert(0, ROOT+'/src')
OUT='/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster'
import gymnasium as gym
import robomme.robomme_env  # noqa
from robomme.robomme_env.utils import object_generation as og
from scripts.parity.v4_specs import env_kwargs, task_sampling
log=[]
orig=og._trimesh_box_to_obb2d
def patched(obb_box, extra_pad=0.0):
    r=orig(obb_box, extra_pad)
    b=getattr(obb_box,'primitive',obb_box)
    log.append(dict(T=np.asarray(b.transform).tolist(), ext=np.asarray(b.extents).tolist(), c=r[0].tolist(), A=r[1].tolist(), h=r[2].tolist()))
    return r
og._trimesh_box_to_obb2d=patched
doc=json.load(open(ROOT+'/scripts/configs/newtask-v4/sampling_config.json'))
seeds=[int(s) for s in sys.argv[1:]] or [4400100]
res={}
for seed in seeds:
    log.clear()
    env=gym.make('BinFill', sampling_config=task_sampling(doc,'BinFill'), **env_kwargs(seed, 0))
    env.reset()
    base=env.unwrapped
    cubes=[(c.name, np.asarray(c.pose.p.cpu()).tolist(), np.asarray(c.pose.q.cpu()).tolist()) for c in base.all_cubes]
    res[seed]=dict(log=list(log), cubes=cubes, spec=base._spec.to_dict())
    env.close()
    print('seed',seed,'obb calls',len(log))
    # 打印去重后的 OBB（按中心）
    seen={}
    for e in log:
        k=tuple(np.round(e['c'],5))
        if k not in seen: seen[k]=e
    for k,e in list(seen.items())[:14]:
        print('  c',k,'A',np.round(e['A'],3).tolist(),'h',np.round(e['h'],4).tolist(),'ext',np.round(e['ext'],4).tolist())
pickle.dump(res, open(OUT+'/sim_obb_probe.pkl','wb'))
print('SIM_PROBE_DONE')
