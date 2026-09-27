"""只读：VPB 新档，按规格判定答案方块在「题目所问的一侧（before/after）」放到 target 上几次；
>1 次时第 3 句 ALT「where it was previously placed {before|after} the button」指向不唯一。"""
import json, glob, re
A = "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts"
HERE = A + "/audit/v6-semantic-vs-native-82e3d92/crosscut-language"
idx = json.load(open(A + "/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json"))
keys = {(e["difficulty"], e["episode"], e["seed"]) for e in idx["VideoPlaceButton"]}
R = {(r["difficulty"], r["episode"]): r for r in json.load(open(HERE + "/records.json")) if r["task"] == "VideoPlaceButton"}
cfg = {"xhard1": (1, 0, 1), "xhard2": (1, 1, 1), "xhard3": (2, 1, 0), "xhard4": (2, 1, 1)}  # demo_count, extra_before, extra_after（VideoPlaceButton.py 顶部 V6 表）
out = []
for f in sorted(glob.glob(A + "/newtask-v6/v6-01/*/specs.jsonl")):
    for l in open(f):
        r = json.loads(l)
        if r.get("record") != "spec" or r["task"] != "VideoPlaceButton" or (r["difficulty"], r["episode"], r["seed"]) not in keys:
            continue
        o = r["spec"]["objects"]; d = r["difficulty"]
        _, nb, na = cfg[d]
        sides = ["before"] * nb + ["after"] * na
        owners = dict(zip(sides, o["extra_place_owner_ids"])) if sides else {}
        rec = R[(d, r["episode"])]
        side = re.search(r"right (before|after) the button", rec["setup"]["task_goal"][0]).group(1)
        ans = o["answer_demo_index"]
        n_side = 1 + (1 if owners.get(side) == ans else 0)
        out.append(dict(difficulty=d, episode=r["episode"], seed=r["seed"], question_side=side, answer_demo_index=ans,
                        extra_owner_by_side=owners, answer_cube_placements_on_question_side=n_side,
                        alt3=rec["setup"]["task_goal"][2], ambiguous=n_side > 1,
                        note="before 侧属已排除的 VPB last-placed-before 绑定问题" if (n_side > 1 and side == "before") else ""))
json.dump(out, open(HERE + "/vpb_alt_ambiguity.json", "w"), indent=1, ensure_ascii=False)
for x in out: print(x["difficulty"], x["episode"], x["question_side"], x["extra_owner_by_side"], "ans", x["answer_demo_index"], "n", x["answer_cube_placements_on_question_side"], x["note"])
print("VPB_ALT3_AMBIGUOUS after=%d before=%d total=%d" % (sum(x["ambiguous"] and x["question_side"] == "after" for x in out), sum(x["ambiguous"] and x["question_side"] == "before" for x in out), len(out)))
