import json, glob, sys
D = __file__.rsplit('/', 1)[0]
rows = []
for f in sorted(glob.glob(D + "/mc_?.log")):
    for l in open(f):
        l = l.strip()
        if l.startswith("{"):
            rows.append(json.loads(l))
seen = set()
print("label | n | fail(direct) | fail_est | p_acc_mean[0..3] | p_acc_min[0..3] | att_mean | att_max | anyVisOvl | tgtVisOvl | anyCollOvl | tgtCollOvl | I2(tgt axis<0.02) | minGap_p05 | tgtGap_med | tgtNNroot_med | finger_full_rand | finger_full_either | finger_tip_rand | tgtBoxOvl | anyBoxOvl")
for r in rows:
    if r["label"] in seen: continue
    seen.add(r["label"])
    print(f"{r['label']} | {r['n']} | {r['fail_direct']} | {r['fail_est']:.2e} | {r['p_accept_mean']} | {r['p_accept_min']} | {r['attempts_mean']} | {r['attempts_max']} | "
          f"{r['any_visual_overlap']:.4f} | {r['target_visual_overlap']:.4f} | {r['any_collision_overlap']:.4f} | {r['target_collision_overlap']:.4f} | {r['target_axisdist_lt_0p02']:.4f} | "
          f"{r['min_pair_gap_p05']:.4f} | {r['target_gap_median']:.4f} | {r['target_nn_root_median']:.4f} | {r['finger_full_random_end']:.4f} | {r['finger_full_either_end']:.4f} | {r['finger_tip_random_end']:.4f} | {r['target_box_overlap']:.4f} | {r['any_box_overlap']:.4f}")
