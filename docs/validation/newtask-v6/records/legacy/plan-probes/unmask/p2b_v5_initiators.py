"""P2b：V5 现状内环发起者的对象级分布（replica 复刻主流取值，10000 局/环境）：每个 bin_i 作发起者的次数占比、
「永不发起」的是谁、bin_3（xhard 下恒为空容器，selected=randperm(3) 只覆盖 bin_0..2）的发起率。"""
import sys, numpy as np
sys.path.insert(0, ".")
from mclib import *  # noqa
for task in ("VideoUnmaskSwap", "ButtonUnmaskSwap"):
    base = 9_100_000 if task == "VideoUnmaskSwap" else 9_300_000
    cnt = np.zeros(4); never = np.zeros(4); sel_has3 = 0; L = 0
    for i in range(10000):
        lay = inner_layout(task, base + i)
        if lay.get("spawn_fail"): continue
        L += 1
        ini = initiators(lay)
        for a in ini: cnt[a] += 1
        s = set(lay["swap_initiator_indices"] + [lay["swap_initiator_third"]])
        for b in range(4):
            never[b] += b not in s
        sel_has3 += 3 in lay["selected"]
    print(f"P2B {task} layouts={L} 发起次数占比={np.round(cnt/cnt.sum(),4).tolist()} 永不发起概率={np.round(never/L,4).tolist()} selected含bin_3={sel_has3}")
