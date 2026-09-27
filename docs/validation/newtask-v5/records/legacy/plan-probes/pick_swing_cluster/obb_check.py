"""检查 trimesh bounding_box_oriented 对立方体给出的 2D OBB 是否退化（轴竖直 → 投影为 0）。"""
import numpy as np, trimesh, math, time
from robomme.robomme_env.utils.object_generation import _trimesh_box_to_obb2d, _obb2d_intersect, _build_new_cube_obb2d
rng=np.random.default_rng(0)
def cube_obb2d(x,y,yaw,hs=0.02):
    m=trimesh.creation.box(extents=[2*hs]*3)
    T=np.eye(4); c,s=math.cos(yaw),math.sin(yaw)
    T[:3,:3]=[[c,-s,0],[s,c,0],[0,0,1]]; T[:3,3]=[x,y,hs]
    m.apply_transform(T)
    return _trimesh_box_to_obb2d(m.bounding_box_oriented)
N=2000; degen=0; stats=[]
t0=time.time()
for i in range(N):
    yaw=rng.uniform(0,2*math.pi)
    c,A,h=cube_obb2d(0,0,yaw)
    n0,n1=np.linalg.norm(A[:,0]),np.linalg.norm(A[:,1])
    # 2D 有效半边长：沿 A 两列的投影
    ok = abs(n0-1)<1e-6 and abs(n1-1)<1e-6 and abs(abs(A[:,0]@A[:,1]))<1e-6
    if not ok: degen+=1
    stats.append((n0,n1,abs(A[:,0]@A[:,1])))
print("time/obb ms", (time.time()-t0)/N*1e3)
stats=np.array(stats)
print("N",N,"degenerate(non-orthonormal 2D axes)",degen, "frac", degen/N)
print("col norms quantiles", np.quantile(stats[:,0],[0,0.1,0.5,0.9,1]), np.quantile(stats[:,1],[0,0.1,0.5,0.9,1]))
print("|dot| quantiles", np.quantile(stats[:,2],[0,0.5,0.9,1]))
# 实际最小中心距：对一个退化/不退化的既有方块，扫描新方块（pad 0.02）能贴多近
def min_center_dist(yaw_e, trials=4000):
    c,A,h=cube_obb2d(0,0,yaw_e)
    best=9
    for _ in range(trials):
        r=rng.uniform(0.02,0.08); th=rng.uniform(0,2*math.pi); yn=rng.uniform(0,2*math.pi)
        cn,An,hn=_build_new_cube_obb2d(r*math.cos(th),r*math.sin(th),0.02,yn,pad_xy=0.02)
        if not _obb2d_intersect(c,A,h,cn,An,hn): best=min(best,r)
    return best
md=[min_center_dist(rng.uniform(0,2*math.pi),3000) for _ in range(30)]
print("min accepted center distance over 30 existing yaws:", np.round(sorted(md),4))
