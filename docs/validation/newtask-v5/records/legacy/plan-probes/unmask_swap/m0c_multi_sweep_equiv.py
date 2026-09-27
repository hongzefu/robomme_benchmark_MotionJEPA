"""M0c：推广版 check_multi_swap_sweep 在「只有一对」时与仓库 check_swap_sweep 逐值一致；两对相距很远时与各自单查一致。"""
import sys
sys.path.insert(0, "/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap")
from replica import *
from multi_sweep import check_multi_swap_sweep
from robomme.robomme_env.utils.bin_collision import check_swap_sweep
same = tot = 0
for row in load_spec_rows("VideoUnmaskSwap")[:4] + load_spec_rows("ButtonUnmaskSwap")[8:9]:
    lay = layout_from_spec(row)
    for k, (a, b, d, pos, yaw) in enumerate(inner_sequence(lay)[:3]):
        sa = bin_state(f"bin_{a}", *pos[a], yaw[a]); sb = bin_state(f"bin_{b}", *pos[b], yaw[b])
        by = [bin_state(f"bin_{j}", *pos[j], yaw[j]) for j in range(4) if j not in (a, b)]
        by += [bin_state(f"distractor_bin_{j}", x, y, w) for j, (x, y, w) in enumerate(lay["distractors"])]
        g1, r1 = check_swap_sweep(sa, sb, by, sweep_index=k)
        g2, r2, _ = check_multi_swap_sweep([(sa, sb)], by, sweep_index=k)
        ok = (r1 is None) == (r2 is None) and (r1 is None or r1.as_dict() == r2.as_dict()) and (g1 == g2 or (g1 != g1 and g2 != g2))
        same += ok; tot += 1
        print(row["task"], row["episode"], k, "repo", round(g1, 6), None if r1 is None else r1.reason, "multi", round(g2, 6), None if r2 is None else r2.reason, "OK" if ok else "DIFF", flush=True)
# 两对相距很远：内部对 + 一对放在 (5,5) 附近的外部对 ⇒ 结果与单查内部对相同
row = load_spec_rows("VideoUnmaskSwap")[0]; lay = layout_from_spec(row)
a, b, d, pos, yaw = inner_sequence(lay)[0]
sa = bin_state("bin_a", *pos[a], yaw[a]); sb = bin_state("bin_b", *pos[b], yaw[b])
far = (bin_state("distractor_bin_0", 5.0, 5.0, 10.0), bin_state("distractor_bin_1", 5.15, 5.0, 30.0))
g1, r1 = check_swap_sweep(sa, sb, [])
g2, r2, _ = check_multi_swap_sweep([(sa, sb), far], [])
print("far-pair", g1, g2, r1, r2)
print(f"MULTI_SWEEP_EQUIV ok={same}/{tot}")
