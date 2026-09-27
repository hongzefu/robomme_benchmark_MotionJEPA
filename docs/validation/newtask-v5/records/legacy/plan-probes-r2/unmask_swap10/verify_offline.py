"""P5 副本/判据校验（离线部分）：
(a) replica 对 v4-01 冻结规格 20 行（VUS/BUS 各 10）的内环布局与主流取值逐值一致；
(b) 推广的 check_multi_swap_sweep 单对时与仓库 check_swap_sweep 逐值一致（含外接圆预筛开/关）；
(c) 向量化精确可见判据 visible_xy_many 与仓库 visible_in_camera(bin_corners) 逐点一致（20000 点）；
(d) predict_inner 与 replica.inner_sequence 的交换对逐窗一致。
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import swap10lib as L  # noqa: E402
from multi_sweep import check_multi_swap_sweep  # noqa: E402
from offline_joint import inputs_from_replica  # noqa: E402
from replica import bus_layout, inner_sequence, layout_from_spec, load_spec_rows, vus_layout  # noqa: E402
from robomme.robomme_env.utils.bin_collision import check_swap_sweep  # noqa: E402

# (a)
ok = tot = 0
for task, fn in (("VideoUnmaskSwap", vus_layout), ("ButtonUnmaskSwap", bus_layout)):
    for row in load_spec_rows(task):
        spec, o = row["spec"], row["spec"]["objects"]
        rep = fn(row["seed"])
        bs = np.array([spec["layout"]["bins"][str(i)] for i in range(4)])
        br = np.array(rep["bins"])
        err = float(np.max(np.abs(bs - br))) if br.shape == bs.shape else float("inf")
        f = all([rep["n_swaps"] == o["n_swaps"], rep["color_order"] == o["color_order"], rep["selected"] == o["selected"],
                 rep["target_choice"] == o["target_choice"], rep["swap_initiator_indices"] == o["swap_initiator_indices"],
                 rep["swap_initiator_third"] == o["swap_initiator_third"], rep["type_choice"] == spec["layout"]["type_choice"]])
        good = err < 1e-5 and f
        ok += good; tot += 1
print(f"(a) REPLICA_VS_V4SPEC ok={ok}/{tot}", flush=True)

# (b) + (d)
same = n = dpair_ok = dpair_n = 0
for seed_fn, base in ((vus_layout, 9_100_000), (bus_layout, 9_300_000)):
    for i in range(6):
        lay = seed_fn(base + i)
        if lay.get("spawn_fail"):
            continue
        seq, _ = inputs_from_replica(lay)
        ref = inner_sequence(lay)
        dpair_n += 1
        dpair_ok += [(a, b) for a, b, _ in seq] == [(a, b) for a, b, *_ in ref]
        for k, (a, b, st) in enumerate(seq[:4]):
            by = [s for j, s in enumerate(st) if j not in (a, b)]
            g1, r1 = check_swap_sweep(st[a], st[b], by, sweep_index=k)
            g2, r2, _ = check_multi_swap_sweep([(st[a], st[b])], by, sweep_index=k)
            _g3, r3, _ = check_multi_swap_sweep([(st[a], st[b])], by, sweep_index=k, circle_r=L.RADIUS)
            eq = ((r1 is None) == (r2 is None) == (r3 is None)) and (g1 == g2 or (g1 != g1 and g2 != g2))
            same += eq; n += 1
print(f"(b) MULTI_SWEEP_SINGLE_PAIR_EQUIV ok={same}/{n}", flush=True)
print(f"(d) PREDICT_INNER_EQUIV ok={dpair_ok}/{dpair_n}", flush=True)

# (c)
rng = np.random.default_rng(0)
pts = rng.uniform(-0.5, 0.5, size=(20000, 2))
v1 = L.visible_xy_many(pts)
v2 = np.array([L.visible_xy(x, y) for x, y in pts])
print(f"(c) VISIBLE_VECTORIZED_EQUIV mismatch={int(np.sum(v1 != v2))}/20000 visible={int(v2.sum())}", flush=True)
