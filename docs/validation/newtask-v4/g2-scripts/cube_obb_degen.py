# 核对：方块 actor 经 get_actor_obb(trimesh OBB) → _trimesh_box_to_obb2d 后，2D OBB 是否退化（一根轴投影为零向量）
import numpy as np, trimesh
def quat_to_mat_f32(yaw):
    q=np.array([np.cos(yaw/2),0,0,np.sin(yaw/2)],dtype=np.float32)
    w,x,y,z=[np.float32(v) for v in q]
    R=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]],dtype=np.float32)
    return R.astype(np.float64)
def obb2d_cube(x,y,yaw,hs=0.02):
    m=trimesh.creation.box(extents=[2*hs]*3); T=np.eye(4); T[:3,:3]=quat_to_mat_f32(yaw); T[:3,3]=[x,y,hs]; m.apply_transform(T)
    b=m.bounding_box_oriented; Tb=np.asarray(b.primitive.transform); ex=np.asarray(b.primitive.extents)
    R=Tb[:3,:3]
    cols=[R[:2,0],R[:2,1]]
    cols=[c if np.linalg.norm(c)<1e-12 else c/np.linalg.norm(c) for c in cols]
    return Tb[:2,3],np.stack(cols,1),0.5*ex[:2]
if __name__=="__main__":
    rng=np.random.default_rng(1); n=2000; deg=0; tiny=0
    for _ in range(n):
        c,A,h=obb2d_cube(rng.uniform(-.3,.1),rng.uniform(-.25,.25),rng.uniform(0,2*np.pi))
        nr=np.linalg.norm(A,axis=0)
        if nr.min()<0.5: deg+=1
    print(f"退化比例 {deg}/{n} = {deg/n:.3f}")
