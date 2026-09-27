"""只读：汇总 16 环境 × 7 档的语言目标模板变体、分档分支、子目标词表与自动核对结果，写 templates.json。"""
import json, re, collections, os
HERE = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/crosscut-language"
R = json.load(open(HERE + "/records.json")); C = json.load(open(HERE + "/checks.json"))
ORDER = ["easy", "medium", "hard", "xhard1", "xhard2", "xhard3", "xhard4"]
W = "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twice"
O = "first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|\\d+th"
def norm(s):
    s = re.sub(r"<[^>]*>", "<>", s)
    s = re.sub(r"\b(red|green|blue)\b", "{color}", s)
    s = re.sub(r"\b(" + O + r")\b", "{ord}", s)
    s = re.sub(r"\b(" + W + r")\b", "{num}", s)
    s = re.sub(r"\b(before|after)\b", "{before|after}", s)
    return s
BRANCHES = {
 "BinFill": "task_goal.py::get_language_goal BinFill：按颜色计数拼短语（1 用 cube，其余 cubes），0～3 色三分支；无分档分支。子目标 BinFill.py 用 subgoal_language.get_subgoal_with_index（序数表到 twentieth）。",
 "PickXtimes": "repeats>1 两句 / repeats==1 一句；无分档分支。子目标序数走 subgoal_language（到 twentieth）。新档另有 yellow/cyan/magenta 干扰块（NEWVALUE_DECISION 前 k 色）。",
 "SwingXtimes": "repeats>1 两句（第 1 句不提放下）/ repeats==1 两句；无分档分支。子目标序数用 SwingXtimes.py::_load_scene 本地 10 项表，超出写成 f\"{i+1}th\"。",
 "VideoUnmask": "task_goal.py::_unmask_pick_count：新档读 env.xhard_pick_count；pick>2 走 _unmask_multi_pick_clause（next…finally…），pick==2 / 1 原句。",
 "ButtonUnmask": "同 VideoUnmask，前缀 first press the button。",
 "VideoUnmaskSwap": "self.pick_times==2 / >=3（V4 新增 next…finally…）/ 其他。",
 "ButtonUnmaskSwap": "同 VideoUnmaskSwap，前缀 first press both buttons on the table。",
 "VideoPlaceButton": "四句固定；第 4 句按 before/after 分 last placed before / first placed after。无分档分支；新档额外放台（extra_place_before/after）只改任务链，不改语言。",
 "VideoPlaceOrder": "两句，{num} 用 num2words_2[which_in_subset]；无分档分支。",
 "PickHighlight": "两句固定（含拼写 highlighteted）；无分档分支。子目标：新档 subgoal_color_suffix=omit 去掉 ', which is {color}'（PickHighlight.py::_load_scene xhard 分支）。",
 "VideoRepick": "num_repeats>1 三句（two 时用 twice）/ ==1 两句；无分档分支。子目标序数 VideoRepick.py 本地 10 项表。",
 "StopCube": "两句，num2words_2[stop_time]（到 twentieth）；无分档分支。",
 "InsertPeg": "两句固定。", "MoveCube": "两句固定。", "PatternLock": "两句固定。", "RouteStick": "两句固定。",
}
out = {"audit_base": "82e3d922b78d48ec1e825b168cccc0e1b8c690c1", "envs": {}}
for t in sorted({r["task"] for r in R}):
    rs = [r for r in R if r["task"] == t]
    goals = collections.defaultdict(set); subs = collections.defaultdict(set); choices = collections.defaultdict(set)
    for r in rs:
        for i, g in enumerate(r["setup"]["task_goal"]):
            goals[f"variant{i}|" + norm(g)].add(r["difficulty"])
        for b in r["boundaries"]:
            if b["simple"] != "All tasks completed":
                subs[("demo|" if b["demo"] else "exec|") + norm(b["simple"])].add(r["difficulty"])
        choices[r["setup"]["available_multi_choices"]].add(r["difficulty"])
    srt = lambda s: sorted(s, key=ORDER.index)
    def tag(v):
        v = srt(v); nat = [x for x in v if not x.startswith("x")]; new = [x for x in v if x.startswith("x")]
        return {"tiers": v, "scope": "both" if nat and new else ("native_only" if nat else "new_only")}
    cks = [c for c in C if c["task"] == t]
    summ = collections.Counter((c["check"], c["kind"], "ok" if c["ok"] else "FAIL") for c in cks)
    out["envs"][t] = {
        "source_branches": BRANCHES[t],
        "goal_variants": {k: tag(v) for k, v in sorted(goals.items())},
        "subgoal_templates": {k: tag(v) for k, v in sorted(subs.items())},
        "choice_sets": [{"choices": json.loads(k), **tag(v)} for k, v in choices.items()],
        "auto_checks": {"|".join(k): n for k, n in sorted(summ.items())},
        "episodes": {"native": sum(r["kind"] == "native" for r in rs), "new": sum(r["kind"] == "new" for r in rs)},
    }
json.dump(out, open(HERE + "/templates.json", "w"), indent=1, ensure_ascii=False)
print("TEMPLATES_JSON=WRITTEN envs=%d" % len(out["envs"]))
