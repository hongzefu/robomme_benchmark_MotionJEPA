"""只读：语言目标 / 子目标 / 规格参数三方一致性检查（165 新档 + 144 原三档）。输出 checks.json。"""
import json, glob, re, collections, os
A = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts"
HERE = os.path.join(A, "audit/v6-semantic-vs-native-82e3d92/crosscut-language")
R = json.load(open(os.path.join(HERE, "records.json")))
specs = {}
for f in glob.glob(A + "/newtask-v6/v6-01/*/specs.jsonl"):
    for l in open(f):
        r = json.loads(l)
        if r.get("record") == "spec":
            specs[(r["task"], r["difficulty"], r["episode"], r["seed"])] = r["spec"]
W = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
O = "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth".split()
w2n = {w: i + 1 for i, w in enumerate(W)}; w2n["twice"] = 2
o2n = {w: i + 1 for i, w in enumerate(O)}
PLAN = {  # 计划第三节：各档取值（区间闭）
    "BinFill": {"xhard1": (6, 6), "xhard2": (7, 7), "xhard3": (8, 8), "xhard4": (9, 9), "hard": (3, 5)},
    "PickXtimes": {"xhard1": (6, 7), "xhard2": (8, 9), "xhard3": (10, 12), "xhard4": (13, 15), "hard": (4, 5)},
    "SwingXtimes": {"xhard1": (4, 5), "xhard2": (6, 7), "xhard3": (8, 9), "xhard4": (10, 11), "hard": (3, 3)},
    "PickHighlight": {"xhard1": (4, 4), "xhard2": (5, 5), "xhard3": (6, 6), "xhard4": (7, 7), "hard": (3, 3)},
    "VideoUnmask": {"xhard1": (2, 2), "xhard2": (3, 3), "xhard3": (3, 3), "xhard4": (3, 3), "hard": (2, 2)},
    "ButtonUnmask": {"xhard1": (2, 2), "xhard2": (3, 3), "xhard3": (3, 3), "xhard4": (3, 3), "hard": (2, 2)},
    "VideoUnmaskSwap": {"xhard1": (2, 2), "xhard2": (3, 3), "xhard3": (3, 3), "xhard4": (3, 3), "hard": (2, 2)},
    "ButtonUnmaskSwap": {"xhard1": (2, 2), "xhard2": (3, 3), "xhard3": (3, 3), "xhard4": (3, 3), "hard": (2, 2)},
    "VideoRepick": {"xhard1": (2, 2), "xhard2": (3, 3), "xhard3": (4, 4), "xhard4": (5, 6)},
    "StopCube": {"xhard4": (6, 15)},
}
SWAPS = {"VideoUnmaskSwap": {"xhard1": (4, 5), "xhard2": (6, 7), "xhard3": (8, 9), "xhard4": (10, 12), "hard": (2, 3)},
         "ButtonUnmaskSwap": {"xhard1": (4, 4), "xhard2": (5, 5), "xhard3": (6, 7), "xhard4": (8, 9), "hard": (2, 3)},
         "VideoRepick": {"xhard1": (3, 4), "xhard2": (5, 6), "xhard3": (7, 8), "xhard4": (9, 12)}}
out = []
def add(r, name, ok, **kv):
    out.append(dict(task=r["task"], difficulty=r["difficulty"], episode=r["episode"], kind=r["kind"], check=name, ok=bool(ok), **kv))
def exe(r):
    return [b for b in r["boundaries"] if not b["demo"]]
def dedup_tail(bs):
    # 末尾终止帧常重复最后一个子目标（原三档同样），去掉紧邻重复
    res = []
    for b in bs:
        if res and res[-1]["simple"] == b["simple"]:
            continue
        res.append(b)
    return res
for r in R:
    t, g = r["task"], r["setup"]["task_goal"]
    g0 = g[0]
    sp = specs.get((t, r["difficulty"], r["episode"], r["setup"].get("seed"))) if r["kind"] == "new" else None
    eb = dedup_tail(exe(r))
    simples = [b["simple"] for b in eb]
    if t == "BinFill":
        goal = {c: w2n[w] for w, c in re.findall(r"\b(" + "|".join(W) + r") (red|blue|green) cubes?\b", g0)}
        picks = collections.Counter(); ords = collections.defaultdict(list)
        for s in simples:
            m = re.match(r"pick up the (\w+) (red|blue|green) cube", s)
            if m: picks[m.group(2)] += 1; ords[m.group(2)].append(o2n.get(m.group(1)))
        tot = sum(goal.values())
        add(r, "goal_vs_subgoal_counts", dict(picks) == goal, goal=goal, picks=dict(picks))
        add(r, "ordinals_sequential", all(v == list(range(1, len(v) + 1)) for v in ords.values()), ords=dict(ords))
        # 复数形式
        bad = [m for m in re.findall(r"\b(one \w+ cubes|(?:two|three|four|five|six|seven|eight|nine) \w+ cube\b)", g0)]
        add(r, "plural_forms", not bad, bad=bad)
        if sp:
            tn = sp["objects"]["target_numbers"]
            add(r, "spec_target_numbers", dict(zip(["red", "blue", "green"], tn)) == {**{c: 0 for c in ["red", "blue", "green"]}, **goal}, spec=tn)
        if r["difficulty"] in PLAN[t]:
            lo, hi = PLAN[t][r["difficulty"]]; add(r, "plan_range_total", lo <= tot <= hi, value=tot, plan=[lo, hi])
    elif t in ("PickXtimes", "SwingXtimes", "VideoRepick"):
        m = re.search(r"\b(" + "|".join(W) + r"|twice) times\b|\b(twice)\b", g0)
        n = w2n[m.group(1) or m.group(2)] if m else 1
        if t == "PickXtimes":
            cnt = sum(s.startswith("pick up the") for s in simples)
            ordl = [o2n.get(re.search(r"for the (\w+) time", s).group(1)) for s in simples if s.startswith("pick up the")]
        elif t == "SwingXtimes":
            cnt = sum("right-side target" in s for s in simples)
            ordl = [o2n.get(re.search(r"for the (\w+) time", s).group(1)) for s in simples if "right-side" in s]
        else:
            cnt = sum(s.startswith("pick up the correct cube") for s in simples)
            ordl = [o2n.get(re.search(r"for the (\w+) time", s).group(1)) for s in simples if s.startswith("pick up the correct")]
            nstatic = sum(b["simple"] == "static" for b in r["boundaries"] if b["demo"])
            if sp:
                add(r, "vr_static_eq_swaps_plus1", nstatic == sp["objects"]["n_swaps"] + 1, static=nstatic, n_swaps=sp["objects"]["n_swaps"])
                lo, hi = SWAPS[t][r["difficulty"]]; add(r, "plan_range_swaps", lo <= sp["objects"]["n_swaps"] <= hi, value=sp["objects"]["n_swaps"], plan=[lo, hi])
        add(r, "goal_vs_subgoal_counts", cnt == n, goal_n=n, subgoal_n=cnt)
        add(r, "ordinals_sequential", ordl == list(range(1, len(ordl) + 1)), ords=ordl)
        # 所有备选语言数字一致
        nums = set()
        for gg in g:
            mm = re.search(r"\b(" + "|".join(W) + r") times\b|\b(twice)\b", gg)
            if mm: nums.add(w2n[mm.group(1) or mm.group(2)])
        add(r, "alt_goal_numbers_agree", len(nums) <= 1, nums=sorted(nums))
        if sp:
            add(r, "spec_num_repeats", sp["objects"]["num_repeats"] == n, spec=sp["objects"]["num_repeats"], goal=n)
        if r["difficulty"] in PLAN.get(t, {}):
            lo, hi = PLAN[t][r["difficulty"]]; add(r, "plan_range", lo <= n <= hi, value=n, plan=[lo, hi])
        # 目标颜色一致
        if t != "VideoRepick":
            cg = re.search(r"pick up the (\w+) cube", g0).group(1)
            cs = {re.search(r"(?:pick up|put) the (\w+) cube", s).group(1) for s in simples if re.search(r"(?:pick up|put|place) the (\w+) cube", s) and re.search(r"(?:pick up|put) the (\w+) cube", s)}
            add(r, "goal_color_vs_subgoal_color", cs <= {cg}, goal=cg, subgoal=sorted(cs))
    elif t == "PickHighlight":
        picks = [s for s in simples if s.startswith("pick up the")]
        ordl = [o2n.get((re.search(r"pick up the (\w+) highlighted", s) or [None, None])[1]) for s in picks]
        add(r, "ordinals_sequential", ordl == list(range(1, len(ordl) + 1)) or ordl == [None], ords=ordl)
        suffix = ["which is" in s for s in picks]
        add(r, "color_suffix_present", all(suffix), n=len(picks), with_suffix=sum(suffix))
        if sp:
            add(r, "spec_highlight_count", sp["objects"]["highlight_count"] == len(picks), spec=sp["objects"]["highlight_count"], picks=len(picks))
            lo, hi = PLAN[t][r["difficulty"]]; add(r, "plan_range", lo <= len(picks) <= hi, value=len(picks), plan=[lo, hi], n_cubes=sp["objects"]["n_cubes"])
    elif t in ("VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap"):
        gc = re.findall(r"container hiding the (\w+) cube", g0)
        sc = [re.search(r"hides the (\w+) cube", s).group(1) for s in simples if "hides the" in s]
        add(r, "goal_colors_vs_subgoal_colors", gc == sc, goal=gc, subgoal=sc)
        add(r, "goal_colors_distinct", len(set(gc)) == len(gc), goal=gc)
        if sp:
            add(r, "spec_n_picks", sp["objects"]["n_picks"] == len(gc), spec=sp["objects"]["n_picks"], goal=len(gc))
            if t.endswith("Swap"):
                lo, hi = SWAPS[t][r["difficulty"]]; add(r, "plan_range_swaps", lo <= sp["objects"]["n_swaps"] <= hi, value=sp["objects"]["n_swaps"], plan=[lo, hi])
        if r["difficulty"] in PLAN[t]:
            lo, hi = PLAN[t][r["difficulty"]]; add(r, "plan_range_picks", lo <= len(gc) <= hi, value=len(gc), plan=[lo, hi])
    elif t == "StopCube":
        o = re.search(r"for the (\w+) time", g0).group(1); n = o2n[o]
        o2 = re.search(r"on its (\w+) visit", g[1]).group(1)
        add(r, "alt_ordinals_agree", o == o2, a=o, b=o2)
        if sp:
            add(r, "spec_stop_time", sp["actions"]["stop_time"] == n, spec=sp["actions"]["stop_time"], goal=n)
            lo, hi = PLAN[t][r["difficulty"]]; add(r, "plan_range", lo <= n <= hi, value=n, plan=[lo, hi])
    elif t == "VideoPlaceOrder":
        o = re.search(r"on the (\w+) target", g0).group(1); n = o2n[o]
        if sp:
            ob = sp["objects"]
            add(r, "spec_which_in_subset", ob["which_in_subset"] == n, spec=ob["which_in_subset"], goal=n)
            ai = ob["answer_demo_index"]; visits = ob["visit_ids_by_object"][str(ai)]
            add(r, "answer_target_is_nth_visit", n <= len(visits) and visits[n - 1] == sp["actions"]["target_target_id"],
                visits=visits, which=n, target_target_id=sp["actions"]["target_target_id"])
            add(r, "nth_visit_target_unique_in_cube_history", visits.count(visits[n - 1]) == 1, visits=visits, which=n)
            add(r, "total_placements_plan", sum(ob["visit_counts_by_object"]) == {"xhard1": 5, "xhard2": 6, "xhard3": 7, "xhard4": 8}[r["difficulty"]],
                counts=ob["visit_counts_by_object"])
    elif t == "VideoPlaceButton":
        m = re.search(r"right (before|after) the button", g0).group(1)
        if sp:
            add(r, "spec_placements_plan", sp["actions"]["target_placement_count"] == {"xhard1": 3, "xhard2": 4, "xhard3": 5, "xhard4": 6}[r["difficulty"]],
                spec=sp["actions"]["target_placement_count"])
    elif t in ("PatternLock", "RouteStick"):
        if sp and t == "RouteStick":
            L = sp["objects"]["L"]; lo, hi = {"xhard1": (8, 10), "xhard2": (11, 13), "xhard3": (14, 16), "xhard4": (17, 21)}[r["difficulty"]]
            add(r, "plan_range_L", lo <= L <= hi, value=L, plan=[lo, hi], n_exec_subgoals=len(simples))
        if sp and t == "PatternLock":
            n = len(sp["actions"]["path_nodes"]); lo, hi = {"xhard1": (9, 12), "xhard2": (13, 16), "xhard3": (17, 20), "xhard4": (21, 25)}[r["difficulty"]]
            add(r, "plan_range_nodes", lo <= n <= hi, value=n, plan=[lo, hi], n_exec_subgoals=len(simples))
json.dump(out, open(os.path.join(HERE, "checks.json"), "w"), indent=1, ensure_ascii=False)
bad = [c for c in out if not c["ok"]]
summ = collections.Counter((c["task"], c["check"], c["kind"], c["ok"]) for c in out)
for k in sorted(summ): print(k, summ[k])
print("FAILS:")
for c in bad: print(json.dumps(c, ensure_ascii=False))
