"""读冻结的 V4 specs.jsonl，列出 PatternLock / RouteStick 全部 10 条候选的路径长度与关键取值。"""
import json
P = "scripts/configs/newtask-v4/v4-01/specs.jsonl"
rows = [json.loads(l) for l in open(P)]
hdr, rows = rows[0], rows[1:]
print("header keys:", sorted(hdr.keys()))
for env in ("PatternLock", "RouteStick"):
    print(env, "sampling_config:", json.dumps(hdr["sampling_config"][env], ensure_ascii=False)[:1500])
for r in rows:
    if r["task"] == "PatternLock":
        a = r["spec"]["actions"]
        print("PL", r["episode"], r["seed"], r["selected"], "nodes", len(a["path_nodes"]), "segs", len(a["path_nodes"]) - 1, "attempts", a["path_attempts"], a["path_nodes"])
for r in rows:
    if r["task"] == "RouteStick":
        s = r["spec"]
        print("RS", r["episode"], r["seed"], r["selected"], json.dumps(s.get("objects")), "nodes", s["actions"].get("nodes"), "dirs", len(s["actions"].get("directions", {})) if isinstance(s["actions"].get("directions"), (list, dict)) else None, "rot", s.get("layout", {}).get("rotation_deg"))
