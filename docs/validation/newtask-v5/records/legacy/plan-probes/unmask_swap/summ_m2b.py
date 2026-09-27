import sys, json
for l in open(sys.argv[1]):
    if not l.startswith("RESULT_FB "): continue
    try: r = json.loads(l[10:])
    except Exception: continue
    print(f"{r['task'][:3]} {r['ring']:5s} n={r['count']:2d} crit={r['crit']:3s} lane={r['lane']} pf={r['placement_fail']}/{r['layouts']} feasible={r['ep_feasible']}/{r['episodes']}={r['ep_feasible_rate']:.3f} tries={r['tries_hist(feasible eps)']} moved={r['distinct_moved_distractors_mean']} undo={r['outer_immediate_undo_rate']}")
