"""只读：mp4 文件名里编码的档名与语言目标 vs HDF5 setup/difficulty 与 setup/task_goal。"""
import json, re
R = json.load(open("/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/crosscut-language/records.json"))
slug = lambda s: re.sub(r"[^a-z0-9-]+", "_", s.lower()).strip("_")
bad = []; n = 0
for r in R:
    for m in r["mp4"]:
        n += 1
        mm = re.match(r".*?_(easy|medium|hard|xhard[1-4])_(.*)$", m[:-4])
        tier, body = mm.groups()
        if tier != r["difficulty"]:
            bad.append(("tier", r["task"], r["difficulty"], m))
        goals = [slug(g) for g in r["setup"]["task_goal"]]
        for i, p in enumerate(body.split("__HASH__")[0].split("__ALT__")):
            p = p.strip("_")
            if i >= len(goals) or not goals[i].startswith(p):
                bad.append(("goal", r["task"], r["difficulty"], r["episode"], i, p, goals[i] if i < len(goals) else None))
for b in bad: print(b)
print(f"MP4_GOAL_MATCH={'PASS' if not bad else 'FAIL'} mp4={n} mismatches={len(bad)}")
