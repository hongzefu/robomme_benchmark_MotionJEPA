#!/usr/bin/env python3
"""V4 步 3b（g9）：MoveCube / InsertPeg xhard 放置失败风险的纯几何蒙特卡洛（不起 sapien）。

逐字复刻两个环境 xhard 分支的拒绝采样几何（取值域、判据、尝试上限），只把 torch 随机流换成
numpy（分布相同、序列不同），用于量化「尝试上限耗尽 ⇒ SceneGenerationError」的概率。

* InsertPeg：孔板 xy 抖动 ±0.1；前 3 根杆在 x∈[-0.2,0.2]、y∈[-0.3,0.3] 均匀拒绝采样
  （离孔板 > 0.06、杆间 > 0.075，上限 512 次）；第 4 根在 peg_0 周围半径 (0.075, d_max]、
  方位均匀的距离带里采样（同样三条判据，上限 512 次）。原三档（3 根均匀）一并算作对照。
* MoveCube：goal 在 ±(half-0.04) 内均匀（演示 half=0.15、执行 half=0.1）；方块候选中心
  xy = corner_push(u)·0.2-0.1，要求离 goal > 0.1（cube_half_size*5），上限 128 次（D3）。

    uv run --no-sync python docs/validation/newtask-v4/step3b-g9-scripts/placement_mc.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "src"))
from robomme.robomme_env.utils.xhard import corner_push  # noqa: E402

RNG = np.random.default_rng(20260922)


def insertpeg_trial(n_uniform, near_dmax=None, max_attempts=512):
    """返回 (是否成功, 失败在哪一根, 近杆尝试次数)。"""
    box = np.array([(RNG.random() - 0.5) * 0.2, (RNG.random() - 0.5) * 0.2])
    placed = []
    for i in range(n_uniform):
        ok = False
        for _ in range(max_attempts):
            xy = np.array([RNG.random() * 0.4 - 0.2, RNG.random() * 0.6 - 0.3])
            if np.linalg.norm(xy - box) <= 0.06:
                continue
            if any(np.linalg.norm(xy - p) <= 0.075 for p in placed):
                continue
            placed.append(xy)
            ok = True
            break
        if not ok:
            return False, i, None
    if near_dmax is None:
        return True, None, None
    anchor = placed[0]
    for attempt in range(1, max_attempts + 1):
        r = 0.075 + RNG.random() * (near_dmax - 0.075)
        th = RNG.random() * 2 * np.pi
        xy = anchor + r * np.array([np.cos(th), np.sin(th)])
        if not (-0.2 <= xy[0] <= 0.2 and -0.3 <= xy[1] <= 0.3):
            continue
        if np.linalg.norm(xy - box) <= 0.06:
            continue
        if any(np.linalg.norm(xy - p) <= 0.075 for p in placed):
            continue
        return True, None, attempt
    return False, n_uniform, max_attempts


def run_insertpeg(trials=20000):
    print("== InsertPeg ==")
    fails = sum(not insertpeg_trial(3)[0] for _ in range(trials))
    print(f"原三档（3 根均匀）: 失败 {fails}/{trials}")
    for dmax in (0.08, 0.085, 0.1):
        res = [insertpeg_trial(3, dmax) for _ in range(trials)]
        fails = [r for r in res if not r[0]]
        att = np.array([r[2] for r in res if r[0]])
        # 单次尝试接受率（近杆），用来外推 512 次耗尽概率
        p_acc = len(att) / max(1, att.sum())
        by = {}
        for r in fails:
            by[r[1]] = by.get(r[1], 0) + 1
        print(f"xhard d_max={dmax}: 失败 {len(fails)}/{trials} 失败位置={by} "
              f"近杆尝试 均值={att.mean():.2f} p95={np.percentile(att, 95):.0f} max={att.max()} "
              f"单次接受率≈{p_acc:.3f}")
    # 单局条件接受率的最坏分位：锚点被挤在角落时的接受率
    worst = []
    for _ in range(4000):
        box = np.array([(RNG.random() - 0.5) * 0.2, (RNG.random() - 0.5) * 0.2])
        ok, _, _ = True, None, None
        placed = []
        while len(placed) < 3:
            xy = np.array([RNG.random() * 0.4 - 0.2, RNG.random() * 0.6 - 0.3])
            if np.linalg.norm(xy - box) > 0.06 and all(np.linalg.norm(xy - p) > 0.075 for p in placed):
                placed.append(xy)
        acc = 0
        m = 2000
        for _ in range(m):
            r = 0.075 + RNG.random() * 0.01
            th = RNG.random() * 2 * np.pi
            xy = placed[0] + r * np.array([np.cos(th), np.sin(th)])
            if (-0.2 <= xy[0] <= 0.2 and -0.3 <= xy[1] <= 0.3 and np.linalg.norm(xy - box) > 0.06
                    and all(np.linalg.norm(xy - p) > 0.075 for p in placed)):
                acc += 1
        worst.append(acc / m)
    worst = np.array(worst)
    print(f"d_max=0.085 单局接受率分布: min={worst.min():.4f} p1={np.percentile(worst, 1):.4f} "
          f"p5={np.percentile(worst, 5):.4f} 中位={np.median(worst):.3f}；接受率=0 的局占 {np.mean(worst == 0):.4%}")


def run_movecube(trials=200000):
    print("== MoveCube（D3：方块中心 128 次拒绝采样）==")
    for half, name in ((0.15, "演示段"), (0.1, "执行段")):
        g = RNG.random((trials, 2)) * 2 * (half - 0.04) - (half - 0.04)
        for b in (0.0, 0.25, 0.5, 0.75, 1.0):
            u = RNG.random((trials, 2))
            push = np.vectorize(lambda v: corner_push(float(v), b))
            c = push(u) * 0.2 - 0.1 if b else u * 0.2 - 0.1
            p_fail_one = float(np.mean(np.linalg.norm(c - g, axis=1) <= 0.1))
            # 最坏 goal 位置：在 goal 可行域上取 21×21 网格，取单次拒绝率最大的那一格
            lim = half - 0.04
            grid = np.linspace(-lim, lim, 21)
            p_worst = max(float(np.mean(np.linalg.norm(c[:20000] - np.array([gx, gy]), axis=1) <= 0.1))
                          for gx in grid for gy in grid)
            print(f"{name} b={b}: 单次拒绝率均值={p_fail_one:.3f} 最坏 goal 位置={p_worst:.3f} "
                  f"⇒ 128 次全失败概率上界≈{p_worst ** 128:.2e}")


def _seg_dist(p1, q1, p2, q2):
    """两条平面线段的最短距离（采样近似，足够判断是否小于 2×radius）。"""
    t = np.linspace(0, 1, 41)
    a = p1[None] + t[:, None] * (q1 - p1)[None]
    b = p2[None] + t[:, None] * (q2 - p2)[None]
    return float(np.min(np.linalg.norm(a[:, None] - b[None], axis=2)))


def _footprint(root, yaw):
    """InsertPeg 杆（length=0.05）的中轴线：head 以根点为中心 ±0.025，tail 在 -0.05 处 ±0.025。"""
    ax = np.array([np.cos(yaw), np.sin(yaw)])
    return root - 0.075 * ax, root + 0.025 * ax


def run_insertpeg_overlap(trials=4000):
    """初始摆放时杆与杆几何重叠（中轴线距离 < 2×radius=0.02）的比例：原三档 vs xhard。

    重叠的杆在第一步物理里被弹开，目标杆可能被撞翻/滚转（诊断中 seed 920101 实见），
    所以这是 xhard 演示失败的一个主要来源。
    """
    print("== InsertPeg 初始几何重叠 ==")
    for label, n_uniform, near, half_deg in (("原三档", 3, None, 45), ("xhard", 3, 0.085, 180)):
        any_overlap = target_overlap = 0
        for _ in range(trials):
            box = np.array([(RNG.random() - 0.5) * 0.2, (RNG.random() - 0.5) * 0.2])
            placed = []
            while len(placed) < n_uniform:
                xy = np.array([RNG.random() * 0.4 - 0.2, RNG.random() * 0.6 - 0.3])
                if np.linalg.norm(xy - box) > 0.06 and all(np.linalg.norm(xy - p) > 0.075 for p in placed):
                    placed.append(xy)
            if near is not None:
                while True:
                    r = 0.075 + RNG.random() * (near - 0.075)
                    th = RNG.random() * 2 * np.pi
                    xy = placed[0] + r * np.array([np.cos(th), np.sin(th)])
                    if (-0.2 <= xy[0] <= 0.2 and -0.3 <= xy[1] <= 0.3 and np.linalg.norm(xy - box) > 0.06
                            and all(np.linalg.norm(xy - p) > 0.075 for p in placed)):
                        placed.append(xy)
                        break
            yaws = [(RNG.random() * 2 - 1) * np.radians(half_deg) for _ in placed]
            segs = [_footprint(p, y) for p, y in zip(placed, yaws)]
            pairs = [(i, j) for i in range(len(segs)) for j in range(i + 1, len(segs))]
            hits = [(i, j) for i, j in pairs if _seg_dist(*segs[i], *segs[j]) < 0.02]
            any_overlap += bool(hits)
            target_overlap += any(0 in h for h in hits)
        print(f"{label}: 任一对杆重叠 {any_overlap / trials:.1%}，目标杆 peg_0 与他杆重叠 {target_overlap / trials:.1%}")


if __name__ == "__main__":
    run_insertpeg()
    run_insertpeg_overlap()
    run_movecube()
