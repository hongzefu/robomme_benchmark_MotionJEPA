# 用 trimesh 复刻 get_actor_obb → _trimesh_box_to_obb2d，核对 bin/cube 的 2D OBB 形态
import numpy as np, trimesh
from trimesh.transformations import euler_matrix
def obb2d(mesh, pad=0.0):
    b = mesh.bounding_box_oriented
    T = np.asarray(b.primitive.transform); ex = np.asarray(b.primitive.extents)
    R = T[:3,:3]
    def su(v):
        n=np.linalg.norm(v); return v if n<1e-12 else v/n
    A = np.stack([su(R[:2,0]), su(R[:2,1])],1)
    return T[:2,3], A, 0.5*ex[:2]+pad, R, ex
chs=0.02
def bin_mesh(x,y,yaw_deg):
    inner=chs*2.5; t=0.0025; h=chs*2.5*0.5; tf=0.002; ih=inner/2; off=ih+t; zw=tf+h
    poses=[[0,0,0],[0,0,tf],[-off,0,zw],[off,0,zw],[0,-off,zw],[0,off,zw]]
    hs=[[chs]*3,[ih+t,ih+t,tf],[t,ih+t,h],[t,ih+t,h],[ih+t,t,h],[ih+t,t,h]]
    ms=[]
    for p,s in zip(poses,hs):
        m=trimesh.creation.box(extents=2*np.array(s)); m.apply_translation(p); ms.append(m)
    m=trimesh.util.concatenate(ms)
    T=euler_matrix(np.pi,0,np.deg2rad(yaw_deg),'sxyz')  # XYZ 外旋（与 pytorch3d XYZ 约定近似，仅 yaw 相关）
    T[:3,3]=[x,y,tf+2*h]; m.apply_transform(T); return m
def cube_mesh(x,y,yaw):
    m=trimesh.creation.box(extents=[2*chs]*3); T=euler_matrix(0,0,yaw); T[:3,3]=[x,y,chs]; m.apply_transform(T); return m
rng=np.random.default_rng(0)
print("BIN")
for yaw in rng.uniform(0,90,8):
    c,A,h,R,ex=obb2d(bin_mesh(0.1,-0.05,yaw))
    ang=np.degrees(np.arctan2(A[1,0],A[0,0]))
    print(f"yaw={yaw:6.2f} c={np.round(c,4)} h={np.round(h,4)} axis0ang={ang:7.2f} detA={np.linalg.det(A):.3f} ex={np.round(ex,4)}")
print("CUBE")
for yaw in rng.uniform(0,2*np.pi,8):
    c,A,h,R,ex=obb2d(cube_mesh(0.1,-0.05,yaw))
    ang=np.degrees(np.arctan2(A[1,0],A[0,0]))
    print(f"yaw={np.degrees(yaw):6.2f} h={np.round(h,4)} axis0ang={ang:7.2f} detA={np.linalg.det(A):.3f} colnorms={np.round(np.linalg.norm(A,axis=0),3)}")
