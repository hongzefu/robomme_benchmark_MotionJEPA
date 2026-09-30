#!/usr/bin/env python3
"""v7 对照站点的逐段 subgoal 帧数（只读 h5）：每局每个 subgoal 各占多少帧，以及 xhard1～4 与 xhard0 是否一致。

- **段**：逐帧读 ``timestep_<k>/info/simple_subgoal``，文字连续相同的帧算一段；结尾的 ``All tasks completed`` 也算一段。
- **h5 来源**（与 ``v7_site_catalog.py`` 同一套 ``(tier, task, seed)`` 键）：xhard0 取
  ``parity/h5/{H-xhard0,O-xhard0-bucket}``（新入口 / 官方旧入口），xhard1～4 取 ``gen1/episodes/<tier>``。
- **模板**：把 subgoal 文字里的序数词、颜色、数字抹成占位符，再按「该模板在本局第几次出现」分成
  「首次」与「后续」两类（如 PickXtimes 第一次抓取要先移过去，比后续抓取长）。
- **一致判据**：同任务同模板，某档中位数与 xhard0 中位数之差超过 25% 且超过 15 帧，记为「不一致」；
  xhard0 里没有的模板记为「新增」。

输出 ``<site-dir>/subgoals.json``（schema ``v7-subgoals/1``，以 ``open("x")`` 写入、拒绝覆盖），
由 ``v6_site.py`` 的 ``/api/subgoals`` 路由提供给页面。末行打印 ``V7_SUBGOALS=PASS|FAIL …``。

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


def read_segments(path: str) -> list[list]:
    with h5py.File(path, "r") as f:
        if not list(f):
            return []  # 官方原版就生成失败的空 h5
        g = f[list(f)[0]]
        steps = sorted((k for k in g if k.startswith("timestep_")), key=lambda k: int(k[9:]))
        segs: list[list] = []
        for k in steps:
            s = g[k]["info"]["simple_subgoal"][()]
            s = s.decode() if isinstance(s, bytes) else str(s)
            if segs and segs[-1][0] == s:
                segs[-1][1] += 1
            else:
                segs.append([s, 1])
    return segs


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
        segs = list(ex.map(read_segments, [j[-1] for j in jobs]))

    episodes: dict = defaultdict(lambda: defaultdict(dict))
    for (task, tier, idx, seed, entry, _), s in zip(jobs, segs):
        episodes[task][tier].setdefault(str(idx), {"seed": seed})[entry] = label(s)

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

    diffs = sum(c["verdict"] == "不一致" for rows in summary.values() for r in rows for c in r["tiers"].values())
    news = sum(c["verdict"] == "新增" for rows in summary.values() for r in rows for c in r["tiers"].values())
    if x0_same != x0_total:
        problems.append(f"xhard0 新旧入口逐段不同 {x0_total - x0_same} 局")
    out = {"schema": "v7-subgoals/1",
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
          f"cells_diff={diffs} cells_new={news}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
