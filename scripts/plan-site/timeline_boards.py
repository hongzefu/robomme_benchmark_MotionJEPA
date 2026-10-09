"""计划网页里两张数轴总览的浏览器内渲染：把 PNG 换成「内联数据 + 内联 JS 画 SVG」。

2026-10-08 用户原话：「修改http://sled-aspen.eecs.umich.edu:8092/envs.html能否把这个树轴的渲染能否把这个数轴的渲染改。
改在原生在浏览器内部渲染而不是现在这样」。

两张图与原 PNG 同内容、同取条规则（v2_plot.representatives：按 timestep 排序取最短 / 中位（n//2）/ 最长）：
  * xhard1：vis/output/reference_<Task>.json 的 xhard1 合成，14 任务按官网顺序（SUITE_ORDER，AGENTS.md P6）各三条，全局横轴；
    同 vis/synthesize_reference_timeline.py::plot_overview；
  * v2：vis/v2/windows_timeline.json（20260911-contract-v3-07 实跑）14 组各三条，剔除 excluded_slow 慢条，全局横轴；
    同 origin/newtask-v2 c0e7f046 的 windows_overview.png。
只读 vis/ 下数据，不跑仿真。画法在同目录 timeline_board.js。
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[2]
VIS = REPO / "vis"
if str(VIS) not in sys.path:
    sys.path.insert(0, str(VIS))
import build_site  # noqa: E402
import synthesize_reference_timeline as srt  # noqa: E402
import v2_plot  # noqa: E402

# 根计划里两张 PNG 的仓库相对路径 → 数轴键
BOARD_OF_IMAGE = {"vis/output/overview.png": "xhard1", "vis/v2/windows_overview.png": "v2"}
SUB = (f"窗口 [f, f+{v2_plot.WIN - 1}]（{v2_plot.WIN} 帧）、stride {v2_plot.STRIDE}、不跨 demo／exec 段；"
       f"帧路 round(linspace(0, T-1, N))，Δ = (T-1)/(N-1)；N={v2_plot.BUDGETS[0]} 与 N={v2_plot.BUDGETS[1]} 是帧预算不是切分步长。"
       "悬停 subgoal 块看英文全文与起止 timestep。")


def _row(rec: dict[str, Any], left: list[str]) -> dict[str, Any]:
    return {"kind": "row", "left": [x for x in left if x], "r": rec}


def _three(rows: list[dict[str, Any]], name: str, extra=lambda r: "") -> list[dict[str, Any]]:
    reps = v2_plot.representatives(rows)
    return [_row(reps[b], [name, b, f"ep{reps[b]['episode']} · seed {reps[b]['seed']}", extra(reps[b])]) for b in v2_plot.BANDS]


def xhard1_board() -> dict[str, Any]:
    items, xmax, n = [], 0, 0
    for task in srt.SUITE_ORDER:
        path = VIS / "output" / f"reference_{task}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = [build_site.track_row(r["xhard1"]["item"]["segments"], r["xhard1"]["item"]["total"], r["xhard1"]["item"]["demo"],
                                     r["xhard1"]["swaps"], r["episode"], r["seed"]) for r in data["records"]]
        xmax = max(xmax, *(r["total"] for r in rows))
        items.append({"kind": "head", "text": f"{task} / xhard1 合成（{len(rows)} 条）　{data['rule']}"})
        items += _three(rows, f"{task}/xhard1")
        n += 1
    return {"title": f"xhard1 合成参考数轴总览 · {n} 任务各取最短／中位／最长三条（横轴 0–{xmax} 全局固定，可跨任务横比；非实跑）",
            "sub": SUB, "xmax": xmax, "items": items, "count": n}


def v2_board() -> dict[str, Any]:
    data = json.loads((VIS / "v2" / "windows_timeline.json").read_text(encoding="utf-8"))
    excluded = {(r["task"], r["difficulty"], r["episode"]) for r in data.get("excluded_slow", [])}
    items, xmax = [], 0
    for key, recs in data["groups"].items():
        task, diff = key.split("/")
        rows, demo_note = [], ""
        for r in recs:
            if (task, diff, r["episode"]) in excluded:
                continue
            segs = [{"start": s, "len": n, "text": t} for s, n, t in r["segs"]]
            row = build_site.track_row(segs, r["total"], r["demo"], r.get("swaps", []), r["episode"], r["seed"],
                                       r.get("swap_check", "PASS") == "PASS")
            if r.get("simulated_demo"):
                row["orig"] = r["original_total"]
                demo_note = "demo 由生成器直出（重复两遍）" if r.get("demo_source") == "recorded" else "模拟 demo（重复两遍）"
            rows.append(row)
        xmax = max(xmax, *(r["total"] for r in rows))
        items.append({"kind": "head", "text": f"{task} / {diff}（{len(rows)} 条）" + (f"　{demo_note}" if demo_note else "")})
        items += _three(rows, key, lambda r: demo_note if r.get("orig") else "")
    run = data.get("rollout_run_id", "")
    return {"title": f"V2 采样窗口数轴总览 · {len(data['groups'])} 组各取最短／中位／最长三条（实跑 {run}；横轴 0–{xmax} 全局固定，可跨任务横比）",
            "sub": SUB + " 已剔除慢条（excluded_slow）。", "xmax": xmax, "items": items, "count": len(data["groups"])}


def figure_html(key: str, alt: str) -> str:
    return (f'<figure class="tl"><div class="tl-title">{alt}</div><p class="tl-sub"></p>'
            f'<div class="tl-scroll"><div class="tl-board" data-board="{key}"></div></div>'
            f'<div class="tl-legend"></div></figure>')


CSS = """
figure.tl { margin:18px 0; border:1px solid var(--border); border-radius:8px; padding:12px 14px; }
figure.tl .tl-title { font-weight:700; font-size:1.02em; }
figure.tl .tl-sub { color:var(--muted); font-size:.88em; margin:4px 0 8px; }
figure.tl .tl-scroll { overflow-x:auto; }
figure.tl .tl-legend { display:flex; flex-wrap:wrap; gap:6px 16px; color:var(--muted); font-size:.85em; margin-top:6px; }
figure.tl .tl-legend i { display:inline-block; width:18px; height:10px; vertical-align:middle; margin-right:5px; border-radius:2px; }
"""


def script_html() -> tuple[str, dict[str, int]]:
    boards = {"xhard1": xhard1_board(), "v2": v2_board()}
    payload = {"boards": boards, "win": v2_plot.WIN, "stride": v2_plot.STRIDE, "budgets": list(v2_plot.BUDGETS),
               "swap_colors": v2_plot.SWAP_COLORS, "color": v2_plot.COLOR}
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    js = (pathlib.Path(__file__).with_name("timeline_board.js")).read_text(encoding="utf-8")
    rows = {k: sum(1 for x in b["items"] if x["kind"] == "row") for k, b in boards.items()}
    return f"<script>window.TL_DATA = {data};</script>\n<script>\n{js}</script>\n", rows
