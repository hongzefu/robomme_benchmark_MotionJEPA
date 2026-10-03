#!/usr/bin/env python3
"""v7 对照站点的逐段 subgoal 帧数（只读 h5）：每局每个 subgoal 各占多少帧，以及 xhard1～4 与 xhard0 是否一致。

- **段**：逐帧读 ``timestep_<k>/info/simple_subgoal``，文字连续相同的帧算一段；结尾的 ``All tasks completed`` 也算一段。
- **h5 来源**（与 ``v7_site_catalog.py`` 同一套 ``(tier, task, seed)`` 键）：xhard0 取
  ``parity/h5/{H-xhard0,O-xhard0-bucket}``（新入口 / 官方旧入口），xhard1～4 取 ``gen1/episodes/<tier>``。
- **模板**：把 subgoal 文字里的序数词、颜色、数字抹成占位符，再按「该模板在本局第几次出现」分成
  「首次」与「后续」两类（如 PickXtimes 第一次抓取要先移过去，比后续抓取长）。
- **一致判据**：同任务同模板，某档中位数与 xhard0 中位数之差超过 25% 且超过 15 帧，记为「不一致」；
  xhard0 里没有的模板记为「新增」。

另出三项（schema 2）：
- **oracle 成功步数**：生成 h5 都是 oracle planner 跑成功的演示，执行步 = 帧数 − ``info/is_video_demo`` 帧数；
  逐格给均值／最小～最大／局数，并与 ``artifacts/newtask-v7/v7-lengths.json`` 的 ``exec`` 逐格对拍（差 ≤1）。
- **逐局 task goal**：``setup/task_goal`` 全部措辞与 ``setup/difficulty``。
- **难度配置**：逐字取 ``0928-newtask-v7-xhard0-shared-layout-plan.md`` §3.2.2 定值表与 §3.2.3 逐任务表、两个要点；
  逐局实际配置取 ``src/robomme_hard/env_metadata/test-hard/<tier>/specs.jsonl`` 中 selected 行的 ``spec.objects``。

输出 ``<site-dir>/subgoals.json``（schema ``v7-subgoals/2``，以 ``open("x")`` 写入、拒绝覆盖），
由 ``site_server.py`` 的 ``/api/subgoals`` 路由提供给页面。末行打印 ``V7_SUBGOALS=PASS|FAIL …``。

    uv run --no-sync python scripts/injection-dev/site/v7_subgoal_lengths.py --site-dir artifacts/newtask-v7/site-r11
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import statistics
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import h5py

REPO_ROOT = Path(__file__).resolve().parents[3]
ART = REPO_ROOT / "artifacts/newtask-v7"
PLAN = REPO_ROOT / "docs" / "plans" / "0928-newtask-v7-xhard0-shared-layout-plan.md"
XHARD0_SIDES = (("new", "H-xhard0"), ("old", "O-xhard0-bucket"))
ORDINALS = ("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth "
            "fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth last").split()
COLORS = "red green blue yellow purple orange pink white black brown gray grey cyan".split()
WORD = re.compile(r"\b(" + "|".join(ORDINALS + COLORS) + r")\b")
NUM = re.compile(r"\d+")
RATIO, FRAMES = 0.25, 15
# 逐任务结论（据本脚本 2026-09-29 的输出人工核读写成；数字以页面表格为准）
EXPLAIN = {
    "BinFill": "一致。每段帧数与 xhard0 同量级（抓取约 100～120、放入约 70、按钮约 70），xhard1～4 只是多投几块，逐段长度不变。",
    "PickXtimes": "一致。首次抓取约 120、首次放置约 90，后续每次抓取约 74、放置约 62，与 xhard0 相同；xhard1～4 只是重复次数从 4～5 次加到 7／10／12／15 次。",
    "SwingXtimes": "一致。每次左右摆动约 41 帧，与 xhard0 相同；xhard1～4 只是摆动次数增加。",
    "PickHighlight": "有区别，出在文字与结尾，不在动作长度：①抓取 subgoal 文字改了，xhard0 为「pick up the N-th highlighted cube, which is 〈颜色〉」，xhard1～4 去掉了「which is 〈颜色〉」，所以表中分成两行，帧数本身相近（约 100）；②xhard0 最后一块拿起后直接结束（结尾段约 14 帧），xhard1～4 每块都放回桌面，且在两轮之间和结尾多一次「press the button」（约 67 帧），结尾段因此变成约 38 帧。",
    "VideoUnmask": "一致。开头视频段 static 固定 66 帧，与 xhard0 相同；xhard2～4 多一次「put down the container」和一次再抓取，逐段长度不变。",
    "ButtonUnmask": "一致。逐段长度与 xhard0 相同；xhard2～4 多一次「put down the container」和一次再抓取。",
    "VideoUnmaskSwap": "有区别：开头视频段 static 变长，xhard0 为 168～216 帧，xhard1／2／3／4 分别是 318／300／366／432 帧（视频里交换次数更多）；其余每段与 xhard0 一致。",
    "ButtonUnmaskSwap": "有区别：xhard1～4 在按完按钮后新增一段「wait for the containers to finish swapping」，xhard0 没有这一段；它的长度随档位增长（中位 6／18／84／150 帧）。其余每段与 xhard0 一致。",
    "VideoRepick": "有区别：xhard1～4 在放下方块后新增一段 static 视频段，xhard0 没有；它的长度随档位增长（中位约 248／353／448／548 帧）。抓放每段与 xhard0 一致，只是重复次数增加。",
    "PatternLock": "基本一致。每步移动约 25～40 帧，与 xhard0 相同；表中「后续 move forward」判为不一致，是因为 xhard0 这一格样本少、且混有长步（中位 61），逐段范围（29～86）与 xhard1～4 重叠，不是单步变长。xhard1～4 的段数更多是因为路径更长。",
    "RouteStick": "一致。每次绕行约 50 帧（43～200），与 xhard0 相同；xhard1～4 只是绕行次数更多。",
    "VideoPlaceButton": "有区别，出在子任务结构：xhard0 视频里最后一块是「drop the cube onto table」，xhard1～4 改为「put the cube back to its original position」（约 86 帧，xhard3～4 出现两次）。其余每段与 xhard0 一致。",
    "VideoPlaceOrder": "有区别，出在子任务结构：同 VideoPlaceButton，xhard0 的「drop the cube onto table」在 xhard1～4 变成「put the cube back to its original position」（约 85 帧，可出现多次）。其余每段与 xhard0 一致。xhard0 有 2 局官方原版就生成失败（段数 0）。",
    "MoveCube": "一致（只有 xhard4）。每段与 xhard0 同量级。",
    "InsertPeg": "一致（只有 xhard4）。每段与 xhard0 同量级。",
    "StopCube": "有区别（只有 xhard4）：「remain static」等待段变长，xhard0 中位 120 帧（6～276），xhard4 中位 519 帧（240～786）；其余三段与 xhard0 一致。",
}


def template(text: str) -> str:
    return NUM.sub("N", WORD.sub(lambda m: "〈序数〉" if m.group(1) in ORDINALS else "〈颜色〉", text))


def _text(v) -> str:
    return v.decode() if isinstance(v, bytes) else str(v)


def read_episode(path: str) -> dict:
    """一局的逐段 subgoal、总帧数、视频演示帧数（``info/is_video_demo``）、task goal 全部措辞与 difficulty。"""
    with h5py.File(path, "r") as f:
        if not list(f):  # 官方原版就生成失败的空 h5
            return {"segs": [], "frames": 0, "demo": 0, "goal": [], "difficulty": None}
        g = f[list(f)[0]]
        steps = sorted((k for k in g if k.startswith("timestep_")), key=lambda k: int(k[9:]))
        segs: list[list] = []
        demo = 0
        for k in steps:
            info = g[k]["info"]
            s = _text(info["simple_subgoal"][()])
            demo += bool(info["is_video_demo"][()]) if "is_video_demo" in info else 0
            if segs and segs[-1][0] == s:
                segs[-1][1] += 1
            else:
                segs.append([s, 1])
        setup = g["setup"]
        goal = [_text(x) for x in setup["task_goal"][()]] if "task_goal" in setup else []
        diff = _text(setup["difficulty"][()]) if "difficulty" in setup else None
    return {"segs": segs, "frames": len(steps), "demo": demo, "goal": goal, "difficulty": diff}


def load_plan_tables(path: Path) -> dict:
    """从 0928 计划逐字取 §3.2.2 定值表（含「表的读法」）、§3.2.3 逐任务表与「两个要点」，不改写原文。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    def section(head, stop):
        i = next(n for n, l in enumerate(lines) if l.startswith(head))
        j = next(n for n in range(i + 1, len(lines)) if lines[n].startswith(stop))
        return lines[i:j]
    def rows(block):
        out = [[c.strip() for c in l.strip().strip("|").split("|")] for l in block if l.startswith("|")]
        return out[0], [r for r in out[2:]]
    s322 = section("#### 3.2.2", "#### 3.2.3")
    t_head, t_rows = rows(s322)
    task = ""
    tier_rows = []
    for r in t_rows:
        task = r[0] or task
        tier_rows.append([task] + r[1:])
    k = next(n for n, l in enumerate(s322) if l.startswith("**表的读法"))
    read_notes = [l for l in s322[k:] if l.strip()][:4]
    s323 = section("#### 3.2.3", "### 3.3")
    l_head, l_rows = rows(s323)
    k = next(n for n, l in enumerate(s323) if l.startswith("两个要点"))
    points = [l[2:] for l in s323[k + 1:] if l.startswith("- ")]
    assert len(tier_rows) >= 20 and len(l_rows) == 14 and len(points) == 2, (len(tier_rows), len(l_rows), len(points))
    return {"source": path.name, "tier_head": t_head, "tier_rows": tier_rows, "tier_rule": s322[2],
            "tier_notes": read_notes, "layout_head": l_head, "layout_rows": l_rows, "key_points": points}


def load_specs() -> dict:
    """(tier, task, seed) → spec.objects（另并入 spec.actions 与 layout.rotation_deg），只取 selected 的规格行。"""
    out = {}
    for p in sorted((REPO_ROOT / "src/robomme_hard/env_metadata/test-hard").glob("xhard*/specs.jsonl")):
        tier = p.parent.name
        for line in p.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("record") == "spec" and r.get("selected"):
                cfg = dict(r["spec"].get("objects", {}))
                if "actions" in r["spec"]:  # PatternLock／RouteStick 的路径与方向在 actions 里
                    cfg["actions"] = r["spec"]["actions"]
                rot = r["spec"].get("layout", {}).get("rotation_deg")
                if rot is not None:
                    cfg["rotation_deg"] = rot
                out[(tier, r["spec"]["task"], r["seed"])] = cfg
    return out


def find_h5(tier: str, task: str, seed: int, side: str | None) -> str | None:
    base = ART / (f"parity/h5/{side}" if side else f"gen1/episodes/{tier}")
    hits = glob.glob(str(base / f"episodes/{task}_episode_*/hdf5_files/*_seed{seed}.h5")) if side else \
        glob.glob(str(base / f"{task}_episode_*/hdf5_files/*_seed{seed}.h5"))
    return hits[0] if len(hits) == 1 else None


def label(segs: list[list]) -> list[dict]:
    seen: dict[str, int] = defaultdict(int)
    out = []
    for text, n in segs:
        t = template(text)
        seen[t] += 1
        out.append({"text": text, "frames": n, "tpl": t, "kind": "首次" if seen[t] == 1 else "后续"})
    return out


def med(xs):
    return statistics.median(xs) if xs else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-dir", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args(argv)
    cat = json.loads((args.site_dir / "catalog.json").read_text(encoding="utf-8"))

    jobs, problems = [], []
    for t in cat["tasks"]:
        for tier, cell in t["tiers"].items():
            for ep in cell["episodes"]:
                sides = XHARD0_SIDES if tier == "xhard0" else (("new", None),)
                for entry, side in sides:
                    p = find_h5(tier, t["id"], ep["seed"], side)
                    if p is None:
                        problems.append(f"找不到 h5：{tier}/{t['id']}/{ep['seed']}/{entry}")
                    else:
                        jobs.append((t["id"], tier, ep["idx"], ep["seed"], entry, p))
    with ProcessPoolExecutor(args.workers) as ex:
        reads = list(ex.map(read_episode, [j[-1] for j in jobs]))
    specs = load_specs()

    episodes: dict = defaultdict(lambda: defaultdict(dict))
    steps: dict = defaultdict(lambda: defaultdict(list))  # 任务 → 档 → [(执行步, 演示帧)]
    goals = spec_hit = spec_need = 0
    for (task, tier, idx, seed, entry, _), r in zip(jobs, reads):
        rec = episodes[task][tier].setdefault(str(idx), {"seed": seed})
        rec[entry] = label(r["segs"])
        if entry == "new":
            rec.update(frames=r["frames"], demo=r["demo"], goal=r["goal"], difficulty=r["difficulty"])
            goals += bool(r["goal"])
            if r["frames"]:
                steps[task][tier].append((r["frames"] - r["demo"], r["demo"]))
            if tier != "xhard0":
                spec_need += 1
                cfg = specs.get((tier, task, seed))
                spec_hit += cfg is not None
                rec["config"] = cfg
                if cfg is None:
                    problems.append(f"specs 缺行：{tier}/{task}/{seed}")

    # oracle 成功步数（执行段 = 帧数 − 视频演示帧）
    max_steps = {(t["id"], tier): cell["episodes"][0]["eval"]["new"]["simplememvla"]["max_steps"]
                 for t in cat["tasks"] for tier, cell in t["tiers"].items()}
    oracle: dict = defaultdict(dict)
    for task, tiers in steps.items():
        for tier, xs in tiers.items():
            ex_ = [a for a, _ in xs]
            oracle[task][tier] = {"n": len(xs), "mean": round(statistics.mean(ex_), 1), "min": min(ex_),
                                  "max": max(ex_), "demo_mean": round(statistics.mean(b for _, b in xs), 1),
                                  "demo_min": min(b for _, b in xs), "demo_max": max(b for _, b in xs),
                                  "total_mean": round(statistics.mean(a + b for a, b in xs), 1),
                                  "total_min": min(a + b for a, b in xs), "total_max": max(a + b for a, b in xs),
                                  "max_steps": max_steps.get((task, tier))}
    lengths = json.loads((ART / "v7-lengths.json").read_text(encoding="utf-8"))
    diffs = [abs(oracle[k.split("/")[0]][k.split("/")[1]]["mean"] - v["exec"]) for k, v in lengths.items()]
    oracle_ok = len(diffs) == sum(len(v) for v in oracle.values()) and max(diffs) <= 1
    if not oracle_ok:
        problems.append(f"与 v7-lengths.json 对不上：cells={len(diffs)} max_diff={max(diffs)}")

    # xhard0 新旧入口逐段比对
    x0_same = x0_total = 0
    for task, tiers in episodes.items():
        for rec in tiers.get("xhard0", {}).values():
            x0_total += 1
            x0_same += rec.get("new") == rec.get("old")

    summary = {}
    for task, tiers in episodes.items():
        pool: dict = defaultdict(lambda: defaultdict(list))  # (tpl, kind) -> tier -> [frames]
        order: list = []
        for tier in cat["tiers"]:
            for rec in tiers.get(tier, {}).values():
                for s in rec["new"]:
                    key = (s["tpl"], s["kind"])
                    if key not in order:
                        order.append(key)
                    pool[key][tier].append(s["frames"])
        rows = []
        for key in order:
            base = med(pool[key].get("xhard0", []))
            cells = {}
            for tier, xs in pool[key].items():
                m = med(xs)
                verdict = "基准" if tier == "xhard0" else (
                    "新增" if base is None else
                    ("不一致" if abs(m - base) > max(RATIO * base, FRAMES) else "一致"))
                cells[tier] = {"n": len(xs), "median": m, "min": min(xs), "max": max(xs), "verdict": verdict}
            rows.append({"tpl": key[0], "kind": key[1], "tiers": cells})
        summary[task] = rows

    ndiff = sum(c["verdict"] == "不一致" for rows in summary.values() for r in rows for c in r["tiers"].values())
    news = sum(c["verdict"] == "新增" for rows in summary.values() for r in rows for c in r["tiers"].values())
    if x0_same != x0_total:
        problems.append(f"xhard0 新旧入口逐段不同 {x0_total - x0_same} 局")
    # 计划表与冻结规格不一致处：以规格实数为准，页面加「实测更正」（每条都用规格逐局核对，不符即 FAIL）
    pl = {t: sorted({len(e["config"]["actions"]["path_nodes"]) for e in episodes["PatternLock"][t].values()})
          for t in ("xhard1", "xhard2", "xhard3", "xhard4")}
    if pl != {"xhard1": [12], "xhard2": [15], "xhard3": [18], "xhard4": [21]}:
        problems.append(f"PatternLock 节点数与更正口径不符：{pl}")
    corrections = {"PatternLock": "实测更正：0928 计划表写节点数 12 → 16 → 20 → 24，但冻结规格里实际是 12 → 15 → 18 → 21"
                                  "（四档各 20 局全部如此）；src/robomme_hard/robomme_env/PatternLock.py 注释记为用户 2026-09-29"
                                  "「直接改 12/15/18/21」（定长 24 在 v6 实测里几乎搜不出）。其余任务的计数字段与计划表逐局一致。"}
    tables = load_plan_tables(PLAN)
    tables["corrections"] = corrections
    out = {"schema": "v7-subgoals/2", "oracle": oracle, "config": tables,
           "rule": f"同任务同模板，某档中位数与 xhard0 中位数相差超过 {int(RATIO * 100)}% 且超过 {FRAMES} 帧记为不一致；"
                   "xhard0 没有的模板记为新增。段 = simple_subgoal 文字连续相同的帧；模板 = 抹去序数词、颜色、数字，"
                   "并按本局首次 / 后续出现分开。",
           "xhard0_new_old_same": [x0_same, x0_total],
           "explain": EXPLAIN, "summary": summary, "episodes": episodes}
    with open(args.site_dir / "subgoals.json", "x", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    status = "PASS" if not problems else "FAIL"
    for p in problems[:20]:
        print(p)
    print(f"V7_SUBGOALS={status} h5={len(jobs)} xhard0_same={x0_same}/{x0_total} "
          f"cells_diff={ndiff} cells_new={news} goals={goals} specs={spec_hit}/{spec_need}")
    print(f"ORACLE_MEAN={'PASS' if oracle_ok else 'FAIL'} cells={len(diffs)} max_diff={max(diffs):.2f}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
