"""M0：复刻精度核对——用 specs.jsonl 的 20 行（VUS/BUS 各 10）逐值比对复刻的布局、取值与干扰容器。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from replica import (bus_layout, distractors_from_repo, inner_sequence, layout_from_spec, load_spec_rows,  # noqa: E402
                     vus_layout)

tot = ok = 0
for task, fn in (("VideoUnmaskSwap", vus_layout), ("ButtonUnmaskSwap", bus_layout)):
    for row in load_spec_rows(task):
        spec = row["spec"]
        rep = fn(row["seed"])
        o = spec["objects"]
        bins_spec = np.array([spec["layout"]["bins"][str(i)] for i in range(4)])
        bins_rep = np.array(rep["bins"])
        bin_err = float(np.max(np.abs(bins_spec - bins_rep))) if bins_rep.shape == bins_spec.shape else float("inf")
        fields_ok = all([
            rep["n_swaps"] == o["n_swaps"], rep["color_order"] == o["color_order"], rep["selected"] == o["selected"],
            rep["target_choice"] == o["target_choice"], rep["swap_initiator_indices"] == o["swap_initiator_indices"],
            rep["swap_initiator_third"] == o["swap_initiator_third"], rep["type_choice"] == spec["layout"]["type_choice"],
        ])
        dis_rep, colors = distractors_from_repo(rep)
        dis_spec = np.array([spec["layout"]["distractors"][str(i)] for i in range(3)])
        dis_err = float(np.max(np.abs(np.array(dis_rep) - dis_spec)))
        good = bin_err < 1e-5 and fields_ok and dis_err < 1e-5 and colors == o["distractors"]["cube_colors"]
        tot += 1
        ok += good
        seq = inner_sequence(layout_from_spec(row))
        pairs = [(a, b) for a, b, *_ in seq]
        print(f"{task} ep{row['episode']} seed={row['seed']} n_swaps={o['n_swaps']} bin_err={bin_err:.2e} "
              f"fields_ok={fields_ok} dis_err={dis_err:.2e} colors_ok={colors == o['distractors']['cube_colors']} "
              f"pairs={pairs}")
print(f"REPLICA_MATCH ok={ok}/{tot}")
