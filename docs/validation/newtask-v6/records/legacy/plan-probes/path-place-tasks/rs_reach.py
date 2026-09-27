"""V6 规划探针（RouteStick）：加长直线（更多路线节点）时，贝塞尔绕杆轨迹离机器人基座的最大水平距离（几何上界估算，不做 IK）。
布局与 _load_scene 同：节点 y=(col-(n-1)/2)*0.07、x=-0.1，整排绕世界原点转 theta∈[-30°,30°]；路线节点取偶数下标；
每段贝塞尔控制点侧偏 0.2（曲线峰值侧偏 0.1），顺/逆时针两种都算。基座 (-0.615, 0)。"""
import numpy as np
base = np.array([-0.615, 0.0])
for ncol in (9, 11, 13, 15):
    worst = 0; worst_th = None
    for th in np.radians(np.linspace(-30, 30, 61)):
        R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
        pts = [R @ np.array([-0.1, (c - (ncol - 1) / 2) * 0.07]) for c in range(0, ncol, 2)]
        for a, b in zip(pts[:-1], pts[1:]):
            for s0, s1 in ((a, b), (b, a)):
                ch = s1 - s0; u = ch / np.linalg.norm(ch); perp = np.array([-u[1], u[0]])
                for sign in (-1, 1):
                    ctrl = (s0 + s1) / 2 + sign * 0.2 * perp
                    for t in np.linspace(0, 1, 45):
                        p = (1 - t) ** 2 * s0 + 2 * (1 - t) * t * ctrl + t ** 2 * s1
                        d = np.linalg.norm(p - base)
                        if d > worst: worst, worst_th = d, np.degrees(th)
    print(f"1x{ncol}（路线节点 {(ncol+1)//2}）：轨迹最远离基座 {worst:.3f} m（theta={worst_th:.0f}°）")
