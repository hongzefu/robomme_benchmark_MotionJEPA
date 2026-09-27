"""只读独立复算：从 records.json 重新推导 native/new-tier 缺坐标计数，
不复用 nocoord.json 结果，验证审计原始计数是否可复现。"""
import json, re, collections

BASE = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/crosscut-language"
R = json.load(open(BASE + "/records.json"))
norm = lambda s: re.sub(
    r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|\d+th|red|blue|green)\b",
    "X", s,
)
has = collections.defaultdict(set)
for r in R:
    for b in r["boundaries"]:
        if "<" in b["grounded"]:
            has[r["task"]].add(norm(re.sub(r" at <[^>]*>", "", b["grounded"])))

tot = collections.Counter()
miss = collections.Counter()
miss_rows = []
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
            miss_rows.append(dict(
                task=r["task"], difficulty=r["difficulty"], episode=r["episode"],
                t=b["t"], seg=key[1], grounded=b["grounded"], choice=b.get("choice"),
            ))

print("=== 独立复算 totals/missing（与 nocoord.json 核对） ===")
for k in sorted(tot):
    print(k, miss[k], "/", tot[k], f"{100*miss[k]/tot[k]:.2f}%")

print()
print("=== 每条 missing exec 行都带 choice_action.point？ ===")
all_have_point = True
for x in miss_rows:
    if x["seg"] != "exec":
        continue
    c = x.get("choice")
    has_point = bool(c) and '"point"' in c
    if not has_point:
        all_have_point = False
    print(x["task"], x["difficulty"], x["episode"], x["t"], "point_present=", has_point)
print("ALL_EXEC_ROWS_HAVE_POINT =", all_have_point)

print()
print("=== Fisher exact: native exec 2/407 vs new exec 11/1011 ===")
try:
    from scipy.stats import fisher_exact
    odds, p = fisher_exact([[2, 405], [11, 1000]])
    print(f"odds={odds:.4f} p={p:.4f}")
except Exception as e:
    print("scipy not available:", e)
