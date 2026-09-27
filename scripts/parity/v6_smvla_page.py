"""把 SimpleMemVLA 在 V6 xhard1–4 上的评估结果生成成站点静态页 ``v6_smvla.html``。

数据只读 SimpleMemVLA 仓库 ``docs/eval-doc/v6xhard-0927/records`` 下的逐条结果 jsonl；
页面由 ``v6_site.py`` 的 ``/smvla`` 路由提供。每格同时标「成功/总数」与成功率。

用法：uv run --no-sync python -m scripts.parity.v6_smvla_page --records <records 目录>
"""
from __future__ import annotations

import argparse
import collections
import glob
import html
import json
from pathlib import Path

TIERS = ("xhard1", "xhard2", "xhard3", "xhard4")
NORMAL = ("success", "fail", "timeout")
BASE = {"xhard1": ["xhard1-main-0927", "xhard1-fill-0927"], "xhard2": ["xhard2-0927"],
        "xhard3": ["xhard3-0927"], "xhard4": ["xhard4-0927", "xhard4-fill-0927"]}
LONG_STEPS = {"xhard1": 3000, "xhard2": 3400, "xhard3": 4000, "xhard4": 5200}
BASE_STEPS = {"xhard1": 1500, "xhard2": 1700, "xhard3": 2000, "xhard4": 2600}


def _load(records: Path, dirs):
    fin = {}
    for d in dirs:
        for f in sorted(glob.glob(str(records / d / "results-*.jsonl"))):
            for line in open(f, encoding="utf-8"):
                r = json.loads(line)
                k = (r["difficulty"], r["task"], r["seed"])
                if k not in fin or fin[k]["status"] not in NORMAL:
                    fin[k] = r
    return fin


def _count(rows):
    t = collections.defaultdict(collections.Counter)
    for r in rows:
        t[(r["difficulty"], r["task"])][r["status"]] += 1
    return t


def _cell(c):
    if c is None:
        return '<td class="na">—</td>'
    n = sum(c.values())
    s = c["success"]
    rate = s / n if n else 0.0
    alpha = 0.08 + 0.72 * rate
    extra = f' · {c["error"]} error' if c["error"] else ""
    title = f'success {s} · fail {c["fail"]} · timeout {c["timeout"]}{extra}'
    return (f'<td style="--a:{alpha:.2f}" title="{title}"><span class="frac">{s}/{n}</span>'
            f'<span class="rate">{rate:.0%}</span></td>')


def _table(counts, tiers, caption, note=""):
    tasks = sorted({task for (_, task) in counts})
    head = "".join(f"<th>{t}</th>" for t in tiers)
    body = []
    for task in tasks:
        body.append(f"<tr><th scope=\"row\">{html.escape(task)}</th>"
                    + "".join(_cell(counts.get((t, task))) for t in tiers) + "</tr>")
    tot = []
    for t in tiers:
        c = sum((v for (tt, _), v in counts.items() if tt == t), collections.Counter())
        tot.append(_cell(c if c else None).replace("<td", '<td class="total"', 1))
    body.append('<tr class="sum"><th scope="row">合计</th>' + "".join(tot) + "</tr>")
    note_html = f'<p class="note">{note}</p>' if note else ""
    return (f'<section class="block"><h2>{caption}</h2>{note_html}<div class="scroll"><table>'
            f'<thead><tr><th>task</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div></section>')


def build(records: Path) -> str:
    base = {t: _load(records, BASE[t]) for t in TIERS}
    more = {t: _load(records, [f"more-{t}-0927"]) for t in TIERS}
    long = _load(records, [Path(p).name for p in glob.glob(str(records / "long-*"))])
    base_c = _count(r for t in TIERS for r in base[t].values())
    more_c = _count(r for t in TIERS for r in more[t].values())
    merged = _count([r for t in TIERS for r in more[t].values()]
                    + [r for t in TIERS for r in base[t].values()
                       if any(k[1] == r["task"] for k in more[t])])
    long_c = _count(long.values())
    long_base = {k: v for k, v in base_c.items() if k in long_c}
    errors = sum(1 for d in (base, more) for t in TIERS for r in d[t].values() if r["status"] not in NORMAL)
    steps = " / ".join(f"{t} {BASE_STEPS[t]}" for t in TIERS)
    longsteps = " / ".join(f"{t} {LONG_STEPS[t]}" for t in TIERS)
    blocks = [
        _table(base_c, TIERS, "本体：每格 20 条",
               f"55 格共 1100 条，每条均有生成侧 h5；步数上限 {steps}；未解决 error {errors} 条。"
               "单元格为 成功/总数 与成功率，悬停可看 fail / timeout 分布。"),
        _table(merged, TIERS, "低成功率格：本体 + 新 seed 补测合并（40 条）",
               "本体成功率 ≤20% 的格子另评 20 条新 seed（与本体 seed 无重叠），与本体 20 条合并。"),
        _table(more_c, TIERS, "低成功率格：仅新 seed 补测（20 条）"),
        _table(long_base, TIERS, "加长步数重测前（本体，对照）", f"本体 timeout ≥5/20 的格子。"),
        _table(long_c, TIERS, "加长步数重测：同 20 条，步数上限翻倍", f"步数上限 {longsteps}。"),
    ]
    return PAGE.replace("__BLOCKS__", "\n".join(blocks))


PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SimpleMemVLA 成功率</title>
<style>
:root{--paper:#f6f7f2;--card:#fff;--ink:#172a26;--muted:#6e7a72;--line:#e1e6dc;--green:#246847;--soft:#eaf0e5;--radius:20px}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--paper:#121a17;--card:#18231f;--ink:#e3ece6;--muted:#93a39a;--line:#2a3833;--green:#6fc295;--soft:#1f2d27}}
:root[data-theme="dark"]{--paper:#121a17;--card:#18231f;--ink:#e3ece6;--muted:#93a39a;--line:#2a3833;--green:#6fc295;--soft:#1f2d27}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:1080px;margin:0 auto;padding:28px 16px 60px}
.crumb{font-size:12px;color:var(--muted)}.crumb a{color:var(--green);text-decoration:none}
h1{font-size:28px;letter-spacing:-.8px;margin:14px 0 8px;font-weight:620}
.lead{color:var(--muted);font-size:13px;line-height:1.9;margin:0 0 26px;max-width:820px}
.block{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:22px 22px 18px;margin-bottom:22px}
h2{font-size:17px;margin:0 0 6px;font-weight:600}
.note{color:var(--muted);font-size:12px;line-height:1.8;margin:0 0 14px}
.scroll{overflow-x:auto}
table{border-collapse:separate;border-spacing:4px;width:100%;min-width:520px}
th{font-size:12px;font-weight:550;text-align:left;color:var(--muted);padding:6px 8px;white-space:nowrap}
thead th{text-align:center}
td{text-align:center;border-radius:9px;padding:8px 6px;background:color-mix(in srgb,var(--green) calc(var(--a,0)*100%),transparent);border:1px solid var(--line);font-variant-numeric:tabular-nums;min-width:92px}
td .frac{display:block;font-size:14px;font-weight:600}
td .rate{display:block;font-size:11px;color:var(--muted)}
td.na{background:transparent;color:var(--muted);border-style:dashed}
tr.sum th{color:var(--ink)}
td.total{outline:2px solid var(--green);outline-offset:-2px}
</style>
</head>
<body>
<main>
<div class="crumb"><a href="/">RoboMME</a> / SimpleMemVLA 评估</div>
<h1>SimpleMemVLA 在 V6 xhard1–4 上的成功率</h1>
<p class="lead">权重 checkpoints/simplememvla_robomme；benchmark 分支 PolicyEvalThirdParty-simplememvla-0927-0146（冻结快照 12.192–12.201）；
GreatLakes A40 评估。成功 = 任务在步数上限内完成；fail / timeout 如实记录，未为挑成功重跑。</p>
__BLOCKS__
</main>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("v6_smvla.html"))
    args = ap.parse_args()
    args.out.write_text(build(args.records), encoding="utf-8")
    print(f"SMVLA_PAGE=WRITTEN out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
