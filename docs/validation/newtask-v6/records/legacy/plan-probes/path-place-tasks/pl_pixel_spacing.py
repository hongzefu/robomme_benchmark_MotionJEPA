"""前视相机（K、E 取自 V4 h5）下相邻节点的最小像素间距、按钮半径 0.02 m 的像素半径（最远行），比较候选网格的可辨性。"""
import numpy as np
K = np.array([[128.0, 0, 128.0], [0, 128.0, 128.0], [0, 0, 1]])
E = np.array([[0.0, 1.0, 0.0, 0.0], [0.8944271802902222, 0.0, -0.44721364974975586, -0.08944264054298401], [-0.4472137689590454, 0.0, -0.8944271802902222, 0.49193501472473145]])
def proj(p):
    pc = E[:, :3] @ p + E[:, 3]; uv = K @ pc; return uv[:2] / uv[2]
for R, C, sp in [(5, 5, 0.1), (6, 6, 0.08), (6, 6, 0.09), (7, 7, 0.07), (7, 7, 0.065), (8, 8, 0.06), (8, 8, 0.057)]:
    P = {(r, c): np.array([-0.1 + (r - (R - 1) / 2) * sp, (c - (C - 1) / 2) * sp, 0.01]) for r in range(R) for c in range(C)}
    dmin = min(np.linalg.norm(proj(P[a]) - proj(P[b])) for a in P for b in P if a < b and max(abs(a[0]-b[0]), abs(a[1]-b[1])) == 1)
    # 最远离相机的一行（r=0，靠近机器人）按钮半径像素
    rad = min(np.linalg.norm(proj(P[(0, c)] + np.array([0, 0.02, 0])) - proj(P[(0, c)])) for c in range(C))
    print(f"{R}x{C}@{sp}: min adjacent-node pixel distance={dmin:.1f}px, button radius (row nearest robot)={rad:.1f}px")
