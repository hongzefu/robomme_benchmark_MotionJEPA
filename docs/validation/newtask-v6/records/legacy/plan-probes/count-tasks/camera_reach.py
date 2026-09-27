"""只读：front_rgb 相机视野与机械臂可达性对「采样框可放大范围」的约束。

相机：h5 的 front_camera_extrinsic（cv 约定，四个环境相同）+ 内参 fx=fy=128、cx=cy=128（fov=π/2，256×256）。
判据：方块（半边 0.02，高 0.04）8 个角点全部投进 [margin, 256-margin] 像素才算「完整可见」；
可达：到机器人基座 (-0.615, 0) 的水平距离；引用 V5 InsertPeg 探针：抓取点 ≥0.81 m 的两局都失败于可达极限、
>0.78 m 视为风险区（artifacts/newtask-v5/plan-probes/out/insertpeg.txt）。
"""
import numpy as np
E = np.array([[0.0, 1.0, 0.0, 0.0], [0.8944, 0.0, -0.4472, -0.0894], [-0.4472, 0.0, -0.8944, 0.4919]])
K = np.array([[128, 0, 128], [0, 128, 128], [0, 0, 1.0]])
C = -E[:, :3].T @ E[:, 3]
print("相机中心（世界系）", C.round(3))

def proj(p):
    pc = E @ np.append(p, 1.0); uv = K @ pc
    return uv[:2] / uv[2], pc[2]

def cube_visible(x, y, margin=2):
    for dx in (-0.02, 0.02):
        for dy in (-0.02, 0.02):
            for z in (0.0, 0.04):
                (u, v), zc = proj(np.array([x + dx, y + dy, z]))
                if zc <= 0 or not (margin <= u <= 256 - margin and margin <= v <= 256 - margin):
                    return False
    return True

BASE = np.array([-0.615, 0.0])
xs = np.round(np.arange(-0.45, 0.36, 0.01), 3)
ys = np.round(np.arange(0.0, 0.61, 0.01), 3)
print("\n每个 x 处方块完整可见的最大 |y|、该点到基座距离：")
for x in xs[::5]:
    vis = [y for y in ys if cube_visible(x, y)]
    ymax = max(vis) if vis else None
    r = np.hypot(x - BASE[0], ymax) if ymax is not None else None
    print(f"  x={x:+.2f}  |y|max={ymax}  到基座={None if r is None else round(r,3)}  x 到基座={x-BASE[0]:.3f}")
vis_x = [x for x in xs if cube_visible(x, 0.0)]
print(f"\ny=0 上方块完整可见的 x 范围：[{min(vis_x)}, {max(vis_x)}]")
# 各环境现有 xhard 框（方块中心可达范围）的四角检查
boxes = {
    "BinFill 现值 中心 x∈[-0.28,0.08] y∈±0.23": (-0.28, 0.08, 0.23),
    "PickXtimes/SwingXtimes 现值 中心 x∈[-0.33,0.13] y∈±0.23": (-0.33, 0.13, 0.23),
    "PickHighlight 现值 中心 x∈[-0.28,0.08] y∈±0.18": (-0.28, 0.08, 0.18),
    "候选：y 半宽 0.30（中心 ±0.28）x 同 BinFill": (-0.28, 0.08, 0.28),
    "候选：Pick/Swing 半宽 0.30（中心 x∈[-0.38,0.18] y±0.28）": (-0.38, 0.18, 0.28),
    "候选：PickHighlight 半宽 0.25（中心 x∈[-0.33,0.13] y±0.23）": (-0.33, 0.13, 0.23),
}
print("\n框四角：是否完整可见 / 到基座距离")
for name, (xl, xh, yh) in boxes.items():
    out = []
    for x in (xl, xh):
        for y in (-yh, yh):
            out.append(f"({x:+.2f},{y:+.2f}) 可见={cube_visible(x, y)} r={np.hypot(x-BASE[0], y):.3f}")
    print("  " + name + "\n    " + "\n    ".join(out))
