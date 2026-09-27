import sys, json
for l in open(sys.argv[1]):
    if not l.startswith("RESULT "): continue
    r = json.loads(l[7:])
    t = r["task"][:3]
    print(f"{t} {r['ring']:5s} n={r['count']:2d} {r['rule']:4s} lane={r['lane_outer']} pf={r['placement_fail']} eps={r['episodes']} "
          f"exact={r['ep_exact_rate']:.3f} ex+vis={r['ep_exact_visible_rate']:.3f} full={r['ep_full_rate']:.3f} btn_full={r['ep_full_btn_ok']} | "
          f"win_fail={r['win_exact_fail']}/{r['windows']} kinds={r['win_fail_kinds']} notvis={r['win_not_visible']} intrude={r['win_intrude']} "
          f"inner<0={r['win_inner_circle_clear_lt0']} inner<.04={r['win_inner_circle_clear_lt0.04']} chord_med={r['chord_m']['median']:.3f} p95={r['chord_m']['p95']:.3f} "
          f"nn<1mm={r['win_nn_margin_lt_1mm']} undo={r['outer_immediate_undo']} distinct={r['distinct_outer_pairs_per_ep']} "
          + (f"btn_lt_avoid={r.get('win_btn_lt_avoid(0.122)')} btn_lt_contact={r.get('win_btn_lt_contact(0.0955)')} btnmin={r.get('btn_min_center_dist')}" if t=='But' else ""))
