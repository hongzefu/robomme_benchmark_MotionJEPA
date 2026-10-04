"""1c：清理后 59 格 reset 与清理前快照逐格比（计划第五节 RESET_SNAPSHOT 字段口径）。"""
import json, sys
old = {(r["task"], r["dataset"], r["episode"], r["tier"]): r for r in map(json.loads, open(sys.argv[1]))}
new = {(r["task"], r["dataset"], r["episode"], r["tier"]): r for r in map(json.loads, open(sys.argv[2]))}
FIELDS = ["seed", "difficulty", "joint", "task_goal", "n_frames", "obs", "chain", "info_keys", "status", "ok"]
same = frame_same = 0; bad = []
if set(old) != set(new):
    bad.append(f"格集合不同 old-new={sorted(set(old)-set(new))[:5]} new-old={sorted(set(new)-set(old))[:5]}")
for k in sorted(set(old) & set(new)):
    diffs = [f for f in FIELDS if old[k].get(f) != new[k].get(f)]
    if diffs:
        bad.append(f"{k}: {diffs}")
    else:
        same += 1
    frame_same += old[k].get("frame_sha") == new[k].get("frame_sha")
for b in bad[:20]: print("DIFF", b)
print(f"RESET_SNAPSHOT={'PASS' if not bad and same == len(old) == 59 else 'FAIL'} cells={len(new)} same={same} frame_sha_same={frame_same}")
