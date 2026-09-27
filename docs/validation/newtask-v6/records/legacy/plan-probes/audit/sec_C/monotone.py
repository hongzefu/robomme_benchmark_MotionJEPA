"""只读审计：按计划 2.3～2.12 表格手录各档取值，检查（a）均值是否严格介于相邻档（N7/3.2），
（b）区间上下界是否单调不减（口径 5「已加码字段单调不减」的区间解读），（c）新档是否落在 hard 与 xhard 之间。
方向：dir=+1 表示数值越大越难；dir=-1 表示越小越难（如每次交换步数）。"""
TIERS = ["hard", "xhard1", "xhard2", "xhard3", "xhard"]
def R(a, b=None): return (a, a if b is None else b)
F = [
 # (环境, 字段, dir, [hard, x1, x2, x3, xhard])
 ("BinFill","总块",1,[R(10,12),R(12),R(12),R(12),R(12)]),
 ("BinFill","投入",1,[R(3,5),R(4,5),R(4,6),R(5,6),R(5,7)]),
 ("PickXtimes","次数",1,[R(4,5),R(5,7),R(6,9),R(7,12),R(6,15)]),
 ("PickXtimes","干扰块",1,[R(0),R(1),R(2),R(3),R(3)]),
 ("PickXtimes","方块框半宽",1,[R(.2),R(.25),R(.25),R(.25),R(.25)]),
 ("SwingXtimes","轮数",1,[R(3),R(3,4),R(4,6),R(5,8),R(4,10)]),
 ("SwingXtimes","干扰块",1,[R(0),R(1),R(2),R(3),R(3)]),
 ("PickHighlight","pick",1,[R(3),R(4),R(4,5),R(5,6),R(5,7)]),
 ("PickHighlight","spawn",1,[R(6),R(7),R(8),R(8,9),R(8,10)]),
 ("PickHighlight","干扰(spawn-pick,独立抽)",1,[R(3),R(3),R(3,4),R(2,4),R(1,5)]),
 ("VU","pick",1,[R(2),R(2),R(3),R(3),R(3)]),
 ("VU","干扰",1,[R(0),R(8),R(10),R(13),R(15)]),
 ("VU","含cube",1,[R(0),R(4),R(5),R(6,7),R(7,8)]),
 ("VU","内环容器",1,[R(15),R(8),R(8),R(8),R(8)]),
 ("BU","pick",1,[R(2),R(2),R(3),R(3),R(3)]),
 ("BU","干扰",1,[R(0),R(7),R(9),R(12),R(14)]),
 ("BU","含cube",1,[R(0),R(3,4),R(4,5),R(6),R(7,7)]),
 ("VUS","swap",1,[R(2,3),R(4,5),R(5,7),R(7,9),R(8,12)]),
 ("VUS","pick",1,[R(2),R(2),R(3),R(3),R(3)]),
 ("VUS","外环干扰",1,[R(0),R(4),R(6),R(8),R(10)]),
 ("VUS","每次交换步数",-1,[R(50),R(50),R(33),R(33),R(33)]),
 ("BUS","swap",1,[R(2,3),R(3,4),R(4,5),R(5,6),R(6,8)]),
 ("BUS","pick",1,[R(2),R(2),R(3),R(3),R(3)]),
 ("BUS","外环干扰",1,[R(0),R(4),R(6),R(8),R(10)]),
 ("BUS","每次交换步数",-1,[R(50),R(50),R(33),R(33),R(33)]),
 ("VR","块数",1,[R(15),R(4),R(5),R(6),R(6)]),
 ("VR","swap",1,[R(0),R(3,5),R(5,7),R(6,9),R(8,12)]),
 ("VR","repick",1,[R(1,3),R(2,3),R(3,4),R(4,5),R(4,6)]),
 ("PatternLock","节点数",1,[R(4,8),R(9,12),R(13,17),R(18,22),R(25)]),
 ("PatternLock","搜索预算",1,[R(1000),R(20000),R(20000),R(20000),R(20000)]),
 ("RouteStick","L",1,[R(4,7),R(8,10),R(11,12),R(13,14),R(15,21)]),
 ("VPB","k",1,[R(1),R(1),R(2),R(2),R(2)]),
 ("VPB","放回块数(0/1/2)",1,[R(0),R(1),R(0),R(1),R(2)]),
 ("VPB","演示放置次数(计划口径)",1,[R(2),R(3),R(4),R(5),R(6)]),
 ("VPO","k",1,[R(1),R(1),R(2),R(2),R(2)]),
 ("VPO","v",1,[R(2,4),R(2,4),R(2,3),R(2,4),R(2,4)]),
 ("VPO","放回块数",1,[R(0),R(1),R(0),R(0),R(2)]),
 ("VPO","演示放置次数(计划口径)",1,[R(3),R(4),R(5),R(6),R(8)]),
]
def mean(r): return (r[0]+r[1])/2
print("| 环境 | 字段 | 各档（hard→x1→x2→x3→xhard）| 均值 | 均值严格单调 | 下界单调不减 | 上界单调不减 | 新档越过 xhard/低于 hard |")
print("|---|---|---|---|---|---|---|---|")
for env, f, d, v in F:
    m = [mean(x)*d for x in v]
    strict = all(m[i] < m[i+1] for i in range(4))
    nonstrict = [f"{TIERS[i]}={TIERS[i+1]}" for i in range(4) if m[i] == m[i+1]]
    dec = [f"{TIERS[i]}>{TIERS[i+1]}" for i in range(4) if m[i] > m[i+1]]
    lo = [x[0]*d for x in v] if d>0 else [x[1]*d for x in v]
    hi = [x[1]*d for x in v] if d>0 else [x[0]*d for x in v]
    lo_bad = [f"{TIERS[i]}→{TIERS[i+1]}" for i in range(4) if lo[i] > lo[i+1]]
    hi_bad = [f"{TIERS[i]}→{TIERS[i+1]}" for i in range(4) if hi[i] > hi[i+1]]
    out = []
    for i in (1,2,3):
        if m[i] > m[4]: out.append(f"{TIERS[i]}均值>xhard")
        if m[i] < m[0]: out.append(f"{TIERS[i]}均值<hard")
        if lo[i] > lo[4]: out.append(f"{TIERS[i]}下界>xhard下界")
    fmt = lambda r: str(r[0]) if r[0]==r[1] else f"[{r[0]},{r[1]}]"
    s = "是" if strict else ("否：相等 " + ",".join(nonstrict) if nonstrict else "") + ((" 下降 " + ",".join(dec)) if dec else "")
    print(f"| {env} | {f} | {' → '.join(fmt(x) for x in v)} | {' / '.join(f'{mean(x):g}' for x in v)} | {s} | {'是' if not lo_bad else '否 '+','.join(lo_bad)} | {'是' if not hi_bad else '否 '+','.join(hi_bad)} | {'；'.join(out) or '无'} |")
