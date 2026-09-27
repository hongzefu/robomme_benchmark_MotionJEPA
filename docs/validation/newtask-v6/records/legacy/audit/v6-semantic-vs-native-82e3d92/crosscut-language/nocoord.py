"""只读：统计 grounded_subgoal 应带坐标（同模板其他边界带 <r, c>）却缺坐标的边界，分原三档 / 新档、演示 / 执行。"""
import json, re, collections
HERE = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/crosscut-language"
R = json.load(open(HERE + "/records.json"))
norm = lambda s: re.sub(r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|\d+th|red|blue|green)\b", "X", s)
has = collections.defaultdict(set)
for r in R:
    for b in r["boundaries"]:
        if "<" in b["grounded"]:
            has[r["task"]].add(norm(re.sub(r" at <[^>]*>", "", b["grounded"])))
tot = collections.Counter(); miss = collections.Counter(); rows = []
for r in R:
    for b in r["boundaries"]:
        if b["simple"] == "All tasks completed":
            continue
        if norm(b["simple"]) not in has[r["task"]]:
            continue
        key = (r["kind"], "demo" if b["demo"] else "exec")
        tot[key] += 1
        if "<" not in b["grounded"]:
            miss[key] += 1
            rows.append(dict(task=r["task"], difficulty=r["difficulty"], episode=r["episode"], t=b["t"], seg=key[1], grounded=b["grounded"], choice=b.get("choice")))
res = {"totals": {f"{k[0]}/{k[1]}": v for k, v in tot.items()}, "missing": {f"{k[0]}/{k[1]}": v for k, v in miss.items()}, "rows": rows}
json.dump(res, open(HERE + "/nocoord.json", "w"), indent=1)
for k in sorted(tot): print(k, miss[k], "/", tot[k], f"{100*miss[k]/tot[k]:.2f}%")
for x in rows:
    if x["seg"] == "exec": print(x["task"], x["difficulty"], x["episode"], x["t"], x["grounded"])
