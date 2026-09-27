"""Unmask 交换均匀化可视化的公共件：路径、字体、S1/S1n/S5 规则的纯图论模拟、外环逐窗可行槽对图重算。
只读仓库（经 ../mclib.py 调仓库纯函数），不改任何被 git 跟踪的文件。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent
sys.path.insert(0, str(PROBE))
os.chdir(PROBE)  # 探针脚本按相对路径读 JSON

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 110
plt.rcParams["savefig.dpi"] = 130

N = 4
PAIRS = [(a, b) for a in range(N) for b in range(a + 1, N)]
TASK_ZH = {"VideoUnmaskSwap": "VUS（VideoUnmaskSwap）", "ButtonUnmaskSwap": "BUS（ButtonUnmaskSwap）"}
OBJ_COLORS = ["#d62728", "#2ca02c", "#1f77b4", "#7f7f7f"]  # bin_0..2 藏 红/绿/蓝（示意），bin_3 恒空
C_S1, C_S1N, C_S5, C_S5G = "#9aa5b1", "#e0a030", "#2b8a3e", "#1864ab"


def g_dict(glist):
    return {p: bool(g) for p, g in zip(PAIRS, glist)}


def connected(glist):
    e = [p for p, g in zip(PAIRS, glist) if g]
    seen = {0}; st = [0]
    while st:
        u = st.pop()
        for a, b in e:
            for x, y in ((a, b), (b, a)):
                if x == u and y not in seen:
                    seen.add(y); st.append(y)
    return len(seen) == N


def feasible_pairs(G, occ):
    return [(a, b) for a, b in PAIRS if G[(min(occ[a], occ[b]), max(occ[a], occ[b]))]]


def run_s1(G, n, rng, no_undo=False):
    """S1：每窗在当前可行对象对里均匀抽；no_undo=True 即 S1n（禁止立即撤销，别无选择则失败）。返回逐窗日志或 None。"""
    occ = list(range(N)); cnt = [0] * N; last = None; log = []
    for k in range(n):
        allf = feasible_pairs(G, occ)
        cand = [p for p in allf if p != last] if (no_undo and last is not None) else allf
        if not cand:
            return None
        pair = cand[rng.integers(len(cand))]
        a, b = pair
        log.append(dict(k=k, pair=pair, occ=list(occ), feas=allf, cand=cand, undo=(pair == last),
                        cnt_before=list(cnt)))
        cnt[a] += 1; cnt[b] += 1; occ[a], occ[b] = occ[b], occ[a]; last = pair
        log[-1]["cnt_after"] = list(cnt)
    return log


def run_s5_once(G, n, rng):
    """S5 单趟：候选 = 可行对 − 上一对（别无选择才允许撤销）；取「两者参与次数的较大值、再比和」最小者；平局均匀抽。"""
    occ = list(range(N)); cnt = [0] * N; last = None; log = []
    for k in range(n):
        allf = feasible_pairs(G, occ)
        cand = [p for p in allf if p != last] or allf
        if not cand:
            return None
        key = [(max(cnt[a], cnt[b]), cnt[a] + cnt[b]) for a, b in cand]
        m = min(key)
        best = [p for p, kk in zip(cand, key) if kk == m]
        pair = best[rng.integers(len(best))]
        a, b = pair
        log.append(dict(k=k, pair=pair, occ=list(occ), feas=allf, cand=cand, keys=key, best=best,
                        tie=len(best) > 1, undo=(pair == last), cnt_before=list(cnt)))
        cnt[a] += 1; cnt[b] += 1; occ[a], occ[b] = occ[b], occ[a]; last = pair
        log[-1]["cnt_after"] = list(cnt)
    return log


def spread(log):
    c = np.array(log[-1]["cnt_after"]); return int(c.max() - c.min())


def run_s5(G, n, rng, max_reroll=20):
    """S5 完整版（计划 M6(a)）：整条极差 >1 就整条重排，最多 20 次；仍不满足则接受极差 2 的那条（取极差最小者）。
    返回 (log, 用掉的趟数, 历次尝试的极差列表)。"""
    tries = []; best = None
    for t in range(max_reroll):
        log = run_s5_once(G, n, rng)
        if log is None:
            return None, t + 1, tries
        s = spread(log); tries.append(s)
        if best is None or s < spread(best):
            best = log
        if s <= 1:
            return log, t + 1, tries
    return best, max_reroll, tries


def savefig(fig, name):
    out = HERE / name
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("SAVED", out)
    return out
