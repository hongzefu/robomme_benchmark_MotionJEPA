"""swap-real 结果统计：python analyze.py results.jsonl > summary.txt（同时写 summary.json）"""
import collections
import json
import sys

import numpy as np
from scipy.stats import chisquare

R = [json.loads(l) for l in open(sys.argv[1])]
TASKS = ["VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick"]
ABBR = {"VideoUnmaskSwap": "VUS", "ButtonUnmaskSwap": "BUS", "VideoRepick": "VR"}
out = {}


def fail_class(r):
    if r.get("ok"):
        return "成功"
    tr = r.get("trace") or []
    raises = [t for t in tr if t.get("tag") == "raise"]
    et = r.get("error_type") or "?"
    task = None
    if raises:
        et = raises[-1]["error_type"]; task = raises[-1]["task"]
    elif any(t.get("tag") == "solve_-1" for t in tr):
        task = [t for t in tr if t.get("tag") == "solve_-1"][-1]["task"]; et = "PlannerExhausted"
    else:
        befores = [t for t in tr if t.get("tag") == "before"]
        task = befores[-1]["task"] if befores else None
        if "reported failure" in (r.get("error") or ""):
            et = "环境判失败"
        elif "did not succeed" in (r.get("error") or ""):
            et = "未成功"
    t = (task or "").split(" that ")[0]
    return f"{et}@{t}" if t else et


for task in TASKS:
    for arm in ("s5", "v5"):
        rs = [r for r in R if r["task"] == task and r.get("arm") == arm]
        if not rs:
            continue
        acc = [r for r in rs if r.get("reset_ok")]
        rej = collections.Counter()
        for r in rs:
            if not r.get("reset_ok"):
                e = r.get("error") or ""
                tag = "S5_G_DISCONNECTED" if "S5_G_DISCONNECTED" in e else "S5_ISOLATED" if "S5_ISOLATED" in e else \
                    f"{r.get('error_type')}:{e[:60]}"
                rej[tag] += 1
        succ = [r for r in acc if r.get("ok")]
        fails = collections.Counter(fail_class(r) for r in acc if not r.get("ok"))
        # 参与统计：只用演示成功的局（交换全部执行完毕）
        spreads = []; undos = 0; nsw = 0; marg = None; mismatch = 0; sweep_ok = 0; sweep_n = 0; ctrl_rej = 0
        ctrl_n = 0; min_gaps = []; plan_eq = 0; outer_unvis = []; outer_undo = 0; outer_n = 0; all_part = 0
        for r in succ:
            c = r["capture"]; n_obj = c["n_objs"]
            pairs = [(a, b) for a, b, _s, _e in c["executed_pairs"]]
            cnt = np.zeros(n_obj, int)
            last = None
            for a, b in pairs:
                cnt[a] += 1; cnt[b] += 1
                key = (min(a, b), max(a, b))
                if key == last:
                    undos += 1
                last = key
            nsw += len(pairs)
            marg = cnt.astype(float) if marg is None else marg + cnt
            spreads.append(int(cnt.max() - cnt.min())); all_part += int((cnt > 0).all())
            s5 = c.get("s5") or {}
            if arm == "s5" and s5.get("seq") is not None:
                plan_eq += int([[min(a, b), max(a, b)] for a, b in pairs] == [[min(a, b), max(a, b)] for a, b in s5["seq"]])
            sc = c.get("sweep_checks") or []
            sweep_n += len(sc); sweep_ok += sum(1 for x in sc if x["ok"])
            mismatch += sum(1 for x in sc if x.get("mismatch"))
            pc = c.get("probe_ctrl") or {}
            ctrl_n += pc.get("n", 0); ctrl_rej += pc.get("rej", 0)
            if pc.get("min_gap") is not None:
                min_gaps.append(pc["min_gap"])
            if c.get("outer_pairs"):
                ocnt = np.zeros(c["n_outer"], int); ol = None
                for o, p in c["outer_pairs"]:
                    ocnt[o] += 1; ocnt[p] += 1
                    k = (min(o, p), max(o, p))
                    outer_undo += int(k == ol); ol = k; outer_n += 1
                outer_unvis.append(int((ocnt == 0).sum()))
        d = {"attempts": len(rs), "reset_ok": len(acc), "reset_rate": len(acc) / len(rs), "reject": dict(rej),
             "success": len(succ), "success_rate": (len(succ) / len(acc)) if acc else None, "fails": dict(fails),
             "spread_hist": dict(collections.Counter(spreads)), "spread_le1": (np.mean([s <= 1 for s in spreads]) if spreads else None),
             "spread_mean": float(np.mean(spreads)) if spreads else None, "all_participate": all_part,
             "undo": undos, "n_swaps_total": nsw,
             "marginal": (marg / marg.sum()).round(4).tolist() if marg is not None else None,
             "chi2_p": float(chisquare(marg).pvalue) if marg is not None else None,
             "sweep_checks": [sweep_ok, sweep_n], "inner_mismatch_logs": mismatch,
             "ctrl_state_checks": [ctrl_n - ctrl_rej, ctrl_n], "ctrl_min_gap_m": float(min(min_gaps)) if min_gaps else None,
             "plan_equals_executed": [plan_eq, len(succ)] if arm == "s5" else None,
             "outer_unvisited_mean": float(np.mean(outer_unvis)) if outer_unvis else None,
             "outer_unvisited_hist": dict(collections.Counter(outer_unvis)) if outer_unvis else None,
             "outer_undo": [outer_undo, outer_n] if outer_n else None}
        if arm == "s5":
            tries = [((r.get("capture") or {}).get("s5") or {}).get("tries") for r in acc]
            d["s5_tries_mean"] = float(np.mean([t for t in tries if t])) if any(tries) else None
        out[f"{ABBR[task]}/{arm}"] = d
        print(f"== {ABBR[task]} {arm}: 尝试 {len(rs)}，通过 reset {len(acc)}（{d['reset_rate']:.1%}），拒绝 {dict(rej)}")
        if acc:
            print(f"   演示成功 {len(succ)}/{len(acc)} = {d['success_rate']:.1%}；失败 {dict(fails)}")
        print(f"   成功局：极差分布 {d['spread_hist']} 均值 {d['spread_mean']}，≤1 占 {d['spread_le1']}，全员参与 {all_part}/{len(succ)}，"
              f"撤销 {undos}/{nsw}，参与频率 {d['marginal']} χ² p={d['chi2_p']}")
        print(f"   真实判定：窗首联合扫掠复核通过 {sweep_ok}/{sweep_n}，逐控制步真实碰撞盒复核通过 {ctrl_n - ctrl_rej}/{ctrl_n}"
              f"（最小间隙 {d['ctrl_min_gap_m']}），规划=执行 {d['plan_equals_executed']}，"
              f"外环未参与均值 {d['outer_unvisited_mean']} 分布 {d['outer_unvisited_hist']} 外环撤销 {d['outer_undo']}")
json.dump(out, open(sys.argv[1].rsplit("/", 1)[0] + "/summary.json" if "/" in sys.argv[1] else "summary.json", "w"),
          ensure_ascii=False, indent=1, default=float)
