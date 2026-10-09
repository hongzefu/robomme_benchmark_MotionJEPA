"""生成根计划 HTML 第一部分「三、对齐原则」与「四、分组讨论 + 全任务旋钮总表」两节，并直接写回根计划。

2026-10-08 用户口径（语音转写，原话见生成出的三节）：统一叫法 V2（newtask-v2 交付集）对 V3（本仓库，只有一档）；
主判据是任务长度（中位 timestep，等价于 stride-16 motion 窗数），再验 8 帧是否漏 subgoal；
「拿起 + 放下」合并算一个 subgoal、每次 swap 计入、只看中位条；图改为一图一轴，先画 V2 参照再画配对的 V3 环境。

数据只读：
  * V2：vis/v2/windows_timeline.json（origin/newtask-v2 20260911-contract-v3-07 实跑，剔除 excluded_slow），四个参照组各取中位条；
  * V3：vis/output/reference_<Task>.json（vis/synthesize_reference_timeline.py 的合成参考，非实跑），每任务取合成中位条；
    VideoRepick 的母样本是官方 medium（见该脚本 RULES）。
用法：
  uv run --no-sync python scripts/plan-site/align_section.py            # 只打印统计与判定行
  uv run --no-sync python scripts/plan-site/align_section.py --write    # 替换根计划 <h2 id="p1-_4"> … <h2 id="p1-_6"> 之间的内容
判定行：ALIGN_SECTION=OK groups=4 tasks=14 figures=<n>
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import statistics
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[2]
VIS = REPO / "vis"
if str(VIS) not in sys.path:
    sys.path.insert(0, str(VIS))
import build_site  # noqa: E402
import v2_plot  # noqa: E402

PLAN = REPO / "1006-xhard12-env-plan.html"
TAIL = "All tasks completed"
SEC_BEGIN = '<h2 id="p1-_4">'
SEC_END = '<h2 id="p1-_6">'

# ---------------------------------------------------------------------------
# 严格 subgoal 口径：执行段里相邻的「拿起 → 放下」合并成一个 subgoal；demo 段与尾段不算；每次 swap 算一个事件。
# 键为任务名（V2 参照组用 "V2/<task>"），值为 (拿起正则, 放下正则)；None 表示不合并（每段一个 subgoal）。
MERGE: dict[str, tuple[str, str] | None] = {
    "BinFill": (r"^pick up the", r"^put it into the bin"),
    "PickXtimes": (r"^pick up the", r"^place the"),
    "SwingXtimes": (r"right-side target", r"left-side target"),          # 一次摆动 = 去右侧 + 回左侧
    "StopCube": (r"^move to the top of the button", r"^press the button"),  # 到按钮上方 + 按下 = 一次按钮
    "VideoUnmask": (r"^pick up the container", r"^put down the container"),
    "ButtonUnmask": (r"^pick up the container", r"^put down the container"),
    "VideoUnmaskSwap": (r"^pick up the container", r"^put down the container"),
    "ButtonUnmaskSwap": (r"^pick up the container", r"^put down the container"),
    "PickHighlight": (r"^pick up the", r"^place the cube onto the table"),
    "VideoRepick": (r"^pick up the correct cube", r"^put it down"),
    "VideoPlaceButton": (r"^pick up the cube", r"^place the cube onto the correct target"),
    "VideoPlaceOrder": (r"^pick up the cube", r"^place the cube onto the correct target"),
    "PatternLock": None,
    "RouteStick": None,
}
MERGE_NOTE = {
    "SwingXtimes": "摆动「去右侧 → 回左侧」合并为一次；开头的拿起与结尾的放回桌面不相邻，各算一个",
    "StopCube": "「到按钮上方 → 按下」合并为一次；每段 remain static 各算一个（每段对应方块一次往返）",
}

# 四个配对组（用户 2026-10-08 确认）。ref = V2 组键；tasks 按官网顺序（AGENTS.md P6）。
GROUPS = [
    {"id": "g1", "name": "计数组", "ref": "BinFill/hard", "tasks": ["BinFill", "PickXtimes", "SwingXtimes"],
     "ref_cfg": "V2 BinFill hard：3 色、生成 8–10 块、投入 3–5 块；h5 把成品轨迹重复两遍，前一遍标 is_video_demo=True（假 demo，V3 已弃用，AGENTS.md P4）",
     "ref_note": "V2 这组的中位 1658 含假 demo 那一遍；去掉假 demo 的纯执行中位是 829。下面每个任务给两个倍数：对 1658 与对 829。"},
    {"id": "g2", "name": "序列组", "ref": "RouteStick/xhard", "tasks": ["StopCube", "PatternLock", "RouteStick"],
     "ref_cfg": "V2 RouteStick xhard：length 8–10、可折返；demo 与执行各 50·L 步，T = 100·L", "ref_note": ""},
    {"id": "g3", "name": "容器组", "ref": "VideoUnmaskSwap/xhard", "tasks": ["VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap"],
     "ref_cfg": "V2 VideoUnmaskSwap xhard：4 容器、swap 4–5、pick 2；demo = 6·ceil((64+50n)/6)，n=4/5 → 264/318", "ref_note": ""},
    {"id": "g4", "name": "参考组", "ref": "VideoRepick/xhard", "tasks": ["PickHighlight", "VideoRepick", "VideoPlaceButton", "VideoPlaceOrder"],
     "ref_cfg": "V2 VideoRepick xhard：3 块 cube（easy/medium 分支）、swap 4–5、重抓 1–3 次；demo = 拿起 + 放下 + static(20) + swap×static(54)", "ref_note": ""},
]
WEB_ID = {"BinFill": "1.1", "PickXtimes": "1.2", "SwingXtimes": "1.3", "StopCube": "1.4",
          "VideoUnmask": "2.1", "ButtonUnmask": "2.2", "VideoUnmaskSwap": "2.3", "ButtonUnmaskSwap": "2.4",
          "PickHighlight": "3.1", "VideoRepick": "3.2", "VideoPlaceButton": "3.3", "VideoPlaceOrder": "3.4",
          "MoveCube": "4.1", "InsertPeg": "4.2", "PatternLock": "4.3", "RouteStick": "4.4"}

# 每任务的长度旋钮：key = 配置键；hard = 母样本取值；plan = 现计划（10-07）取值；
# n_hard / n_plan = 两档的「次数」中位（用来从合成结果反推每单位增量）；bind = 与 V2 参照绑定的机制说明；
# width = 建议区间宽度（沿用现计划区间宽度）；unit_name = 一个单位是什么。
KNOB: dict[str, dict[str, Any]] = {
    "BinFill": {"key": 'configs["hard"]["put_in_numbers"]', "hard": "[3,5]", "plan": "[5,6]", "n_hard": 4.0, "n_plan": 5.5, "width": 1,
                "unit_name": "投放目标数", "bind": "与 V2 BinFill 同一个环境、同一个旋钮；V2 hard 投入 3–5 对应 V3 hard 的 [3,5]"},
    "PickXtimes": {"key": 'configs["hard"]["number_min"/"number_max"]', "hard": "[4,5]", "plan": "[6,7]", "n_hard": 4.5, "n_plan": 6.5, "width": 1,
                   "unit_name": "抓放次数", "bind": "一次「拿起 → 放到 target」对应 V2 BinFill 的一次「拿起 → 投进 bin」，段长相近（154 对 179）"},
    "SwingXtimes": {"key": 'configs["hard"]["number_min"/"number_max"]', "hard": "3", "plan": "[7,8]", "n_hard": 3.0, "n_plan": 7.5, "width": 1,
                    "unit_name": "摆动次数", "bind": "一次摆动（去右侧 + 回左侧，约 78）只有 V2 BinFill 一次投放的 44%，同样的长度要翻倍的次数"},
    "StopCube": {"key": "stop_time randint 上下界 + move_interval", "hard": "[2,5]，间隔 60/80/120 随机", "plan": "[8,10]，间隔钉 120", "n_hard": 3.5, "n_plan": 9.0, "width": 2,
                 "unit_name": "停止序号（方块往返次数）", "bind": "方块每往返一次约 120 步对应 V2 RouteStick 一个节点的 demo+exec 100 步；两者都是「等够 k 个周期」"},
    "PatternLock": {"key": 'configs["hard"]["length"]', "hard": "[4,8]", "plan": "[10,14]", "n_hard": 6.0, "n_plan": 12.0, "width": 4,
                    "unit_name": "节点数", "bind": "每个节点 demo+exec 各一段约 31 步，对应 V2 RouteStick 每节点各 50 步；同样的长度要 1.6 倍的节点"},
    "RouteStick": {"key": 'configs["hard"]["length"]', "hard": "[4,7]", "plan": "[8,10]", "n_hard": 5.5, "n_plan": 9.0, "width": 2,
                   "unit_name": "段数", "bind": "与 V2 RouteStick xhard 同一个环境、同一个旋钮、同一个取值"},
    "VideoUnmask": {"key": "task_list 抓容器次数（重写方法）", "hard": "2", "plan": "3", "n_hard": 2.0, "n_plan": 3.0, "width": 0,
                    "unit_name": "抓容器次数", "bind": "每多抓一个容器 +152（放下 49 + 抓 103）；V2 参照的长度主要来自 demo 里的 swap static，这里没有 swap，只能靠多抓"},
    "ButtonUnmask": {"key": "task_list 抓容器次数（重写方法）", "hard": "2", "plan": "3", "n_hard": 2.0, "n_plan": 3.0, "width": 0,
                     "unit_name": "抓容器次数", "bind": "同 VideoUnmask；按钮代替 demo，无 swap"},
    "VideoUnmaskSwap": {"key": 'configs["hard"]["swap_min"/"swap_max"]', "hard": "[2,3]", "plan": "[4,5]", "n_hard": 2.5, "n_plan": 4.5, "width": 1,
                        "unit_name": "swap 次数", "bind": "与 V2 VideoUnmaskSwap 同一个环境、同一个旋钮、同一个取值；每次 swap 让 demo static 多 50 步"},
    "ButtonUnmaskSwap": {"key": 'configs["hard"]["swap_min"/"swap_max"]', "hard": "[2,3]", "plan": "[4,5]", "n_hard": 2.5, "n_plan": 4.5, "width": 1,
                         "unit_name": "swap 次数", "bind": "swap 与按钮并行，不改长度；长度旋钮只能是抓容器次数（同 ButtonUnmask 每多抓 +142）",
                         "length_knob": {"key": "task_list 抓容器次数（重写方法）", "hard": "2", "n_hard": 2.0, "unit": 142.0, "width": 0, "unit_name": "抓容器次数"}},
    "PickHighlight": {"key": 'configs["hard"]["pickup"]', "hard": "3", "plan": "5", "n_hard": 3.0, "n_plan": 5.0, "width": 0,
                      "unit_name": "高亮块数", "bind": "一次「拿起高亮块 → 放回桌面」约 154，对应 V2 VideoRepick 一次「拿起正确块 → 放下」约 160；V2 靠 swap 加长 demo，这里靠多抓"},
    "VideoRepick": {"key": '母样本 medium；configs["medium"]["swap_min"/"swap_max"]', "hard": "[2,3]", "plan": "[4,5]", "n_hard": 2.5, "n_plan": 4.5, "width": 1,
                    "unit_name": "swap 次数", "bind": "与 V2 VideoRepick xhard 同一个分支（3 块 cube）、同一个旋钮、同一个取值；重抓次数 num_repeats 1–3 不动"},
    "VideoPlaceButton": {"key": "不改", "hard": "原 hard", "plan": "原 hard", "n_hard": 1.0, "n_plan": 1.0, "width": 0, "unit_name": "—",
                         "bind": "demo 长度（约 757）已超 V2 VideoRepick 的 demo（468）；只按原 hard 配置重生成"},
    "VideoPlaceOrder": {"key": "不改", "hard": "原 hard", "plan": "原 hard", "n_hard": 1.0, "n_plan": 1.0, "width": 0, "unit_name": "—",
                        "bind": "同 VideoPlaceButton；demo 约 917"},
}

PRINCIPLES = [
    ("叫法", "上一版数据集叫 <b>V2</b>（origin/newtask-v2 交付集，20260912-contract-v3-10），本仓库这版叫 <b>V3</b>。V3 只有一档，不再出现档位名。",
     "你给我定确定一个说法就是说V2和V3 v3只有xhard1不用再提了"),
    ("配对", "V3 每个任务绑定 V2 的一个代表任务，按长度比对：计数三任务（BinFill、PickXtimes、SwingXtimes）对 V2 BinFill hard；StopCube、PatternLock、RouteStick 对 V2 RouteStick xhard；四个容器任务对 V2 VideoUnmaskSwap xhard；四个参考类任务（PickHighlight、VideoRepick、VideoPlaceButton、VideoPlaceOrder）对 V2 VideoRepick xhard。倍数 = V3 中位 ÷ V2 参照中位，只作参考。",
     "这个确认"),
    ("主判据 = 长度", "只按任务长度作主要参考标准：量是<b>每条 episode 的中位 timestep 数</b>，它正好对应 stride-16 motion 窗口数（窗 ≈ (timestep − 32) / 16，demo 与 exec 各铺、不跨段）。V3 的目标是中位长度落到配对的 V2 参照中位附近。",
     "你还是只按照任务长度作为一个主要的参考标准。任务长度正好就对应了这个这个motion的这个窗口数"),
    ("只看中位", "长度、窗数、漏段都只报中位条（按 timestep 排序取下标 n//2 那条），不看最短与最长。",
     "我们现在就只考虑中位数的情况。不考虑这个最短或者最长的情况"),
    ("验 8 帧漏 subgoal（严格口径）", "长度定下后只验证一件事：8 帧等距采样（帧路 floor(i·(T−1)/7 + 0.5)）是否漏掉 subgoal。subgoal 按<b>严格口径</b>数：执行段里相邻的「拿起 → 放下」合并算一个，不算两个；demo 段与尾段不算；<b>每次 swap 算一个事件</b>，采不到也算漏。中位条上漏 ≥ 1 记 PASS，否则记 FAIL 交用户决定，不为此改长度目标。",
     "之前的binfill任务、pic任务等把这个拿起来再放下应该算作为一个subgo不能算作为两个用这个更加严格的机制来评判这个漏subgo……然后SWP你也要考虑进去"),
    ("改法沿用 V2", "只改次数型旋钮、不改任务结构：与 V2 有同名环境的（RouteStick、VideoUnmaskSwap、VideoRepick）取 V2 xhard 的同一组值；VideoRepick 按 V2 的做法从 medium 分支（3 块 cube）改 swap，不用 hard 的 15 块 cluster 分支；MoveCube、InsertPeg 没有次数型的量，不改也不纳入；VideoPlaceButton、VideoPlaceOrder 按原 hard 配置重生成。",
     "MoveCubeInsertPack都不改还是都不改；VdeoRepic这个任务你应该还是按照和上一版本V2一样的都是通过Medium来改"),
]


# ---------------------------------------------------------------------------
def _units(task: str, segs: list[dict[str, Any]]) -> list[tuple[int, int, str]]:
    """严格 subgoal 单元 [(起, 止, 标签)]：按 MERGE 合并相邻拿起→放下，剔除 demo 与尾段。"""
    exec_ = [s for s in segs if not s["demo"] and s["text"] != TAIL]
    rule = MERGE[task.split("/")[-1]]
    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(exec_):
        s = exec_[i]
        if rule and re.search(rule[0], s["text"]) and i + 1 < len(exec_) and re.search(rule[1], exec_[i + 1]["text"]):
            t = exec_[i + 1]
            out.append((s["start"], t["start"] + t["len"], s["text"] + " → " + t["text"]))
            i += 2
        else:
            out.append((s["start"], s["start"] + s["len"], s["text"]))
            i += 1
    return out


def strict_stats(task: str, item: dict[str, Any], swaps: list[list[Any]]) -> dict[str, Any]:
    total, demo = item["total"], item["demo"]
    frames = v2_plot.frame_path(total, 8)
    units = _units(task, item["segments"])
    miss_u = [u for u in units if not any(a <= f < b for f in frames for a, b, _ in [u])]
    miss_s = [s for s in swaps if not any(s[0] <= f < s[1] for f in frames)]
    d, e = v2_plot.window_counts({"demo": demo, "total": total})
    return {"timesteps": total, "demo": demo, "exec": total - demo, "windows": d + e, "windows_demo": d, "windows_exec": e,
            "delta8": round((total - 1) / 7, 1), "units": len(units), "swaps": len(swaps),
            "miss_units": len(miss_u), "miss_swaps": len(miss_s), "miss": len(miss_u) + len(miss_s),
            "missed_labels": [u[2] for u in miss_u], "shortest_unit": min((b - a for a, b, _ in units), default=0)}


def _median_rec(records: list[dict[str, Any]], key) -> dict[str, Any]:
    ordered = sorted(records, key=lambda r: (key(r), r["episode"]))
    return ordered[len(ordered) // 2]


def load_v2() -> dict[str, dict[str, Any]]:
    data = json.loads((VIS / "v2" / "windows_timeline.json").read_text(encoding="utf-8"))
    excluded = {(r["task"], r["difficulty"], r["episode"]) for r in data.get("excluded_slow", [])}
    out = {}
    for g in GROUPS:
        key = g["ref"]
        task, diff = key.split("/")
        recs = [r for r in data["groups"][key] if (task, diff, r["episode"]) not in excluded]
        med = _median_rec(recs, lambda r: r["total"])
        segs = [{"start": s, "len": n, "text": t, "demo": s < med["demo"]} for s, n, t in med["segs"]]
        item = {"total": med["total"], "demo": med["demo"], "segments": segs}
        swaps = med.get("swaps", [])
        st = strict_stats("V2/" + task, item, swaps)
        st["n"] = len(recs)
        st["median_all"] = int(statistics.median(r["total"] for r in recs))
        if med.get("simulated_demo"):
            # 假 demo：前一遍整段不算 subgoal（strict_stats 已按 demo 剔除）；另给纯执行口径
            st["exec_only"] = med["original_total"]
            st["exec_only_median"] = int(statistics.median(r["original_total"] for r in recs))
        out[key] = {"episode": med["episode"], "seed": med["seed"], "item": item, "swaps": swaps, "stats": st, "run": data["rollout_run_id"]}
    return out


def load_v3() -> dict[str, dict[str, Any]]:
    out = {}
    for task in KNOB:
        data = json.loads((VIS / "output" / f"reference_{task}.json").read_text(encoding="utf-8"))
        recs = data["records"]
        med_new = _median_rec(recs, lambda r: r["xhard1"]["stats"]["timesteps"])
        med_hard = _median_rec(recs, lambda r: r["hard"]["stats"]["timesteps"])
        new = strict_stats(task, med_new["xhard1"]["item"], med_new["xhard1"]["swaps"])
        hard = strict_stats(task, med_hard["hard"]["item"], med_hard["hard"]["swaps"])
        new["median_all"] = int(statistics.median(r["xhard1"]["stats"]["timesteps"] for r in recs))
        hard["median_all"] = int(statistics.median(r["hard"]["stats"]["timesteps"] for r in recs))
        new["windows_median_all"] = int(statistics.median(r["xhard1"]["stats"]["windows"] for r in recs))
        hard["windows_median_all"] = int(statistics.median(r["hard"]["stats"]["windows"] for r in recs))
        out[task] = {"n": len(recs), "rule": data["rule"], "new": new, "hard": hard,
                     "new_rec": {"episode": med_new["episode"], "seed": med_new["seed"], "item": med_new["xhard1"]["item"], "swaps": med_new["xhard1"]["swaps"]},
                     "hard_rec": {"episode": med_hard["episode"], "seed": med_hard["seed"], "item": med_hard["hard"]["item"], "swaps": med_hard["hard"]["swaps"]}}
    return out


def _range_text(lo: int, hi: int) -> str:
    return f"{lo}" if lo == hi else f"[{lo},{hi}]"


def propose(task: str, v3: dict[str, Any], target: int) -> dict[str, Any]:
    """按合成结果反推每单位增量，给出把中位长度拉到 target 的建议取值（区间宽度沿用现计划）。"""
    k = KNOB[task]
    hard_med, new_med = v3["hard"]["median_all"], v3["new"]["median_all"]
    lk = k.get("length_knob")
    if k["key"] == "不改":
        return {"unit": 0, "text": "不改", "est": hard_med, "n_mid": None}
    if lk:  # ButtonUnmaskSwap：swap 不改长度，长度旋钮另算
        unit, n_hard, width, key, unit_name = lk["unit"], lk["n_hard"], lk["width"], lk["key"], lk["unit_name"]
    else:
        unit = (new_med - hard_med) / (k["n_plan"] - k["n_hard"]) if k["n_plan"] != k["n_hard"] else 0
        n_hard, width, key, unit_name = k["n_hard"], k["width"], k["key"], k["unit_name"]
    if unit <= 0:
        return {"unit": 0, "text": "无长度旋钮", "est": new_med, "n_mid": None}
    n_mid = n_hard + (target - hard_med) / unit
    lo = max(1, round(n_mid - width / 2))
    hi = lo + width
    est = round(hard_med + ((lo + hi) / 2 - n_hard) * unit)
    return {"unit": round(unit, 1), "n_mid": round(n_mid, 1), "lo": lo, "hi": hi, "text": _range_text(lo, hi), "est": est,
            "key": key, "unit_name": unit_name}


# ---------------------------------------------------------------------------
def _row(rec: dict[str, Any], left: list[str]) -> dict[str, Any]:
    r = build_site.track_row(rec["item"]["segments"], rec["item"]["total"], rec["item"]["demo"], rec["swaps"], rec["episode"], rec["seed"])
    return {"kind": "row", "left": [x for x in left if x], "r": r}


def _fig(key: str, title: str, sub: str) -> str:
    return (f'<figure class="tl"><div class="tl-title">{html.escape(title)}</div><p class="tl-sub">{html.escape(sub)}</p>'
            f'<div class="tl-scroll"><div class="tl-board" data-board="{key}"></div></div><div class="tl-legend"></div></figure>\n')


def _miss_text(st: dict[str, Any]) -> str:
    s = f"{st['miss_units']} 个 subgoal"
    if st["swaps"]:
        s += f" + {st['miss_swaps']} 次 swap"
    s += f"（共 {st['units']} 个严格 subgoal" + (f"、{st['swaps']} 次 swap" if st["swaps"] else "") + f"；Δ8 {st['delta8']}）"
    return s


def _ratio(a: int, b: int) -> str:
    return f"{a / b:.2f}"


def _short(text: str) -> str:
    return v2_plot.short_label(text.split(" → ")[0])[0]


def build(v2: dict[str, Any], v3: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    boards: dict[str, Any] = {}
    summary: dict[str, Any] = {}
    parts: list[str] = []
    E = html.escape
    B = lambda x: f'<span class="big">{x}</span>'  # noqa: E731

    parts.append('<h2 id="p1-_4">三、对齐原则（两条）</h2>\n<ol class="lead">\n'
                 "<li><b>旋钮只调长度</b>：中位 timestep 拉到配对的 V2 参照，同时报对 V2、对本任务 hard 两个倍数。</li>\n"
                 "<li><b>长度定了再验</b>：8 帧采样在中位条上至少漏一个 subgoal（拿起加放下算一个，每次 swap 算一个）。</li>\n</ol>\n")
    parts.append('<h2 id="p1-_5">四、分组讨论</h2>\n')
    for gi, g in enumerate(GROUPS, 1):
        ref = v2[g["ref"]]
        rs = ref["stats"]
        target = rs["median_all"]
        xmax = max([ref["item"]["total"]] + [v3[t]["new_rec"]["item"]["total"] for t in g["tasks"]])
        xmax = (xmax + 99) // 100 * 100
        parts.append(f'<h3 id="p1-g{gi}">四.{gi} {E(g["name"])}：V2 {E(g["ref"])} ← V3 {E("、".join(g["tasks"]))}</h3>\n')
        parts.append(f"<p><b>V2 参照</b>　中位 timestep {B(rs['median_all'])} · 窗 {B(rs['windows'])} · 8 帧漏 {B(rs['miss'])}"
                     + (f" · 纯执行 {B(rs['exec_only_median'])}" if "exec_only_median" in rs else "") + "</p>\n")
        key = f"v2-{g['id']}"
        boards[key] = {"title": f"V2 {g['ref']} 中位条", "sub": "", "xmax": xmax, "items": [_row(ref, [f"V2 {g['ref']}", "中位条", f"ep{ref['episode']} · seed {ref['seed']}"])]}
        parts.append(_fig(key, f"V2 {g['ref']}　{g['ref_cfg'].split('：', 1)[1]}", ""))
        for t in g["tasks"]:
            x = v3[t]
            k = KNOB[t]
            hs, ns = x["hard"], x["new"]
            prop = propose(t, x, target)
            alt = propose(t, x, rs["exec_only_median"]) if "exec_only_median" in rs else None
            summary[t] = {"group": g["name"], "ref": g["ref"], "target": target, "hard": hs, "new": ns, "prop": prop, "alt": alt}
            has = prop.get("n_mid") is not None
            verdict = "PASS" if ns["miss"] >= 1 else "FAIL"
            missed = "、".join(_short(l) for l in ns["missed_labels"]) + ("、swap" if ns["miss_swaps"] else "")
            parts.append(f'<h4 id="p1-t-{t.lower()}">{WEB_ID[t]} {E(t)}</h4>\n<table class="kv"><tbody>\n')
            parts.append(f"<tr><td>旋钮</td><td><code>{E(k['key'])}</code>　hard {E(k['hard'])} → 现计划 {B(E(k['plan']))}" + (f" → 建议 {B(E(prop['text']))}" if has else "") + "</td></tr>\n")
            parts.append(f"<tr><td>中位 timestep / 窗</td><td>hard {hs['median_all']} / {hs['windows_median_all']} → 现计划 {B(ns['median_all'])} / {B(ns['windows_median_all'])}" + (f" → 建议估 {B(prop['est'])}" if has else "") + "</td></tr>\n")
            parts.append(f"<tr><td>对 V2 倍数</td><td>现计划 {B(_ratio(ns['median_all'], target))}" + (f" → 建议 {B(_ratio(prop['est'], target))}" if has else "") +
                         (f"　对纯执行 {B(_ratio(ns['median_all'], rs['exec_only_median']))}" if alt else "") + "</td></tr>\n")
            parts.append(f"<tr><td>对 hard 倍数</td><td>现计划 {B(_ratio(ns['median_all'], hs['median_all']))}" + (f" → 建议 {B(_ratio(prop['est'], hs['median_all']))}" if has else "") + "</td></tr>\n")
            parts.append(f"<tr><td>8 帧漏</td><td>{B(ns['miss'])} / {ns['units'] + ns['swaps']}" + (f"　漏：{E(missed)}" if missed else "") + f"　{B(verdict)}</td></tr>\n")
            parts.append("</tbody></table>\n")
            nr = x["new_rec"]
            key = f"v3-{t}"
            boards[key] = {"title": f"V3 {t} 中位条", "sub": "", "xmax": xmax,
                           "items": [_row(nr, [f"V3 {t}", f"现计划 {k['plan']}", f"ep{nr['episode']} · seed {nr['seed']}", "合成"])]}
            parts.append(_fig(key, f"V3 {t}　现计划 {k['plan']}", ""))
    parts.append('<h3 id="p1-g5">四.5 不纳入：4.1 MoveCube、4.2 InsertPeg</h3>\n')
    parts.append('<h3 id="p1-g6">四.6 全任务总表</h3>\n')
    parts.append("<table><thead><tr><th>编号</th><th>任务</th><th>旋钮 hard → 现计划 → 建议</th><th>中位 timestep hard → 现计划</th><th>窗 hard → 现计划</th><th>对 V2</th><th>对 hard</th><th>8 帧漏</th></tr></thead><tbody>\n")
    for t in WEB_ID:
        if t not in KNOB:
            parts.append(f"<tr><td>{WEB_ID[t]}</td><td>{t}</td><td>不纳入</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>\n")
            continue
        s = summary[t]
        hs, ns, p, alt = s["hard"], s["new"], s["prop"], s["alt"]
        k = KNOB[t]
        has = p.get("n_mid") is not None
        rv = B(_ratio(ns["median_all"], s["target"])) + (f"（纯执行 {_ratio(ns['median_all'], v2[s['ref']]['stats']['exec_only_median'])}）" if alt else "")
        parts.append(f"<tr><td>{WEB_ID[t]}</td><td>{t}</td><td>{E(k['hard'])} → {E(k['plan'])}" + (f" → <b>{E(p['text'])}</b>" if has else "") + "</td>"
                     f"<td>{hs['median_all']} → {B(ns['median_all'])}</td><td>{hs['windows_median_all']} → {ns['windows_median_all']}</td>"
                     f"<td>{rv}</td><td>{B(_ratio(ns['median_all'], hs['median_all']))}</td>"
                     f"<td>{B(ns['miss'])} {'PASS' if ns['miss'] >= 1 else 'FAIL'}</td></tr>\n")
    parts.append("</tbody></table>\n")

    payload = {"boards": boards, "win": v2_plot.WIN, "stride": v2_plot.STRIDE, "budgets": list(v2_plot.BUDGETS),
               "swap_colors": v2_plot.SWAP_COLORS, "color": v2_plot.COLOR}
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    js = (pathlib.Path(__file__).with_name("timeline_board.js")).read_text(encoding="utf-8")
    parts.append(f"<style>{CSS}</style>\n<script>window.TL_DATA = {data};</script>\n<script>\n{js}</script>\n")
    return "".join(parts), boards, summary


CSS = """
figure.tl { margin:14px 0; border:1px solid var(--border); border-radius:8px; padding:10px 14px; }
figure.tl .tl-title { font-weight:700; font-size:1.0em; }
figure.tl .tl-sub { color:var(--muted); font-size:.86em; margin:3px 0 6px; }
figure.tl .tl-scroll { overflow-x:auto; }
figure.tl .tl-legend { display:flex; flex-wrap:wrap; gap:6px 16px; color:var(--muted); font-size:.84em; margin-top:4px; }
figure.tl .tl-legend i { display:inline-block; width:18px; height:10px; vertical-align:middle; margin-right:5px; border-radius:2px; }
.muted { color:var(--muted); font-size:.88em; }
.lead { font-size:1.08em; line-height:1.7; }
.big { font-size:1.3em; font-weight:700; }
table.kv td:first-child { white-space:nowrap; width:11em; }
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="写回根计划 HTML")
    ap.add_argument("--plan", default=str(PLAN))
    a = ap.parse_args()
    v2, v3 = load_v2(), load_v3()
    frag, boards, summary = build(v2, v3)
    for t, s in summary.items():
        print(f"ALIGN_TASK task={t} ref={s['ref']} target={s['target']} hard_med={s['hard']['median_all']} plan_med={s['new']['median_all']} "
              f"plan_ratio={s['new']['median_all'] / s['target']:.2f} propose={s['prop'].get('text')} est={s['prop'].get('est')} "
              f"miss_strict={s['new']['miss_units']}+{s['new']['miss_swaps']}swap units={s['new']['units']}")
    if a.write:
        plan = pathlib.Path(a.plan)
        doc = plan.read_text(encoding="utf-8")
        i, j = doc.index(SEC_BEGIN), doc.index(SEC_END)
        assert 0 < i < j, (i, j)
        plan.write_text(doc[:i] + frag + doc[j:], encoding="utf-8")
        print(f"ALIGN_WRITE=OK plan={plan} replaced_chars={j - i} new_chars={len(frag)}")
    print(f"ALIGN_SECTION=OK groups={len(GROUPS)} tasks={len(KNOB)} figures={len(boards)}")


if __name__ == "__main__":
    main()
