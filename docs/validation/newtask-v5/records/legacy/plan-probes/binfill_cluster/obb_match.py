# 尝试逐位复刻 get_actor_obb：sapien Pose→float32 变换矩阵 + trimesh box(extents=2*float32 half) + merge_meshes
import pickle, numpy as np, sapien, trimesh, json
from mani_skill.utils.geometry.trimesh_utils import merge_meshes
from robomme.robomme_env.utils.object_generation import _trimesh_box_to_obb2d, _yaw_to_quat_tensor
OUT='/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/binfill_cluster'
res=pickle.load(open(OUT+'/sim_obb_probe.pkl','rb'))
ROOT='/data/hongzefu/robomme_benchmark_MotionJEPANewTask'
rows=[json.loads(l) for l in open(f'{ROOT}/scripts/configs/newtask-v4/v4-01/specs.jsonl')][1:]
b={r['seed']:r for r in rows if r.get('task')=='BinFill'}
def obb_v(x,y,yaw,variant):
    q=_yaw_to_quat_tensor(yaw,device='cpu')[0].numpy()
    p=np.array([x,y,0.02],dtype=np.float32)
    if variant=='sapien':
        T=sapien.Pose(p=p,q=q).to_transformation_matrix()
        half=np.array([0.02,0.02,0.02],dtype=np.float32)
        m=trimesh.creation.box(extents=2*half)
        m=merge_meshes([m])
        m.apply_transform(T)
    return _trimesh_box_to_obb2d(m.bounding_box_oriented,0.0)
for seed,d in res.items():
    L=b[seed]['spec']['layout']['cubes']
    seen={}
    for e in d['log']:
        k=tuple(np.round(e['c'],6))
        seen.setdefault(k,e)
    ok=0;n=0
    for name,v in L.items():
        mine=obb_v(*v,'sapien')
        # 找对应的真实日志
        k=min(seen, key=lambda kk: abs(kk[0]-v[0])+abs(kk[1]-v[1]))
        e=seen[k]
        same=np.allclose(np.array(e['A']),mine[1],atol=1e-6) and np.allclose(np.array(e['c']),mine[0],atol=1e-7)
        n+=1; ok+=same
        if not same: print(seed,name,'real A',np.round(e['A'],3).tolist(),'mine',np.round(mine[1],3).tolist())
    print(seed,'OBB match',ok,'/',n)
