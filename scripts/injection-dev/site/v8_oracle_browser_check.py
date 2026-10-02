#!/usr/bin/env python3
"""v8 各档总表页的浏览器检查（v8 方案第一部分 §3「各档总表页」）：不播放视频、不修改服务端。

由 ``v7_oracle_browser_check.py`` 改写：

- 数据一律来自 ``/api/subgoals``（``v8_subgoal_lengths.py`` 从 v8 规格与真实 h5 统计）与 ``/api/catalog``；
  ``subgoals.json`` 缺失时服务端返回 ``{}``，本检查器据此判 FAIL，不允许页面静默缺内容；
- 成功率格（2026-10-02 起评估接入）：按目录每格 ``rates.new``（xhard0 另有 ``rates.old``）推算「百分比」与「成功 / 局数」，与页面逐格一致；执行步上限（原任务页表格行，已撤下，不再核对）等于 ``subgoals.json`` 的 ``max_steps``
  （规格 ``exec_cap``／xhard0 1300）；
- 配置格逐维与表 1 一致（``v8_site_catalog.TABLE1``），不对照任何计划表格；去掉 v7 的 PatternLock 定值断言；
- 可选 ``--delivery``：逐格执行步均值／最小／最大与 ``delivery.json`` 的 ``exec_steps`` 再核一遍（与交付 h5 一致）。

逐格覆盖目录里全部 (任务, 档)（完整根 43 新值格 + 16 xhard0 格 = 59）。只核「各档总表」页（任务页对比表已按用户要求撤下，只断言其隐藏）；截图写 ``--shots``。
末行打印 ``V8_ORACLE_BROWSER=PASS|FAIL cells=<n> missing=<n>``（另附 mismatch、page_errors）。**判定行按前缀匹配**：
``V8_ORACLE_BROWSER=PASS cells=59 missing=0`` 之后可能追加键。任何中断都记入 problems 并照打判定行（FAIL）。
``--expect-cells`` 缺省由目录推出：目录新值格等于 ``V8_CELLS`` 时为 ``len(V8_CELLS) + 16``（= 59），
子表时为目录新值格数 + 16（xhard0 每任务一格）。

    uv run --no-project --with playwright python scripts/injection-dev/site/v8_oracle_browser_check.py \\
      --base http://127.0.0.1:8081 --shots artifacts/newtask-v8/site-checks/oracle \\
      --delivery artifacts/newtask-v8/gen1/delivery.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("v8_site_catalog", HERE / "v8_site_catalog.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

METRICS = ["config", "total", "demo", "exec", "policy-simplememvla", "policy-mmevla", "n"]
TASK_METRICS = METRICS + ["old-policy-simplememvla", "old-policy-mmevla", "max_steps"]

CHECK_JS = """({cat, oracle, metrics, scope}) => {
    const root = document.querySelector(scope), bad = [], missing = [];
    const nums = s => (s.match(/\\d+(?:\\.\\d+)?/g) || []).map(Number);
    const tasks = scope === '#matrix' ? cat.tasks.filter(t => root.querySelector(`td[data-task="${t.id}"]`)) : cat.tasks;
    let checked = 0;
    for (const task of tasks) {
        for (const tier of cat.tiers) {
            const c = task.tiers[tier], gt = (oracle[task.id] || {})[tier];
            if (c && !gt) { missing.push(task.id + '/' + tier + ' subgoals 无该格'); continue; }
            if (c) checked++;
            for (const metric of metrics) {
                const key = `${task.id}/${tier}/${metric}`;
                const cells = root.querySelectorAll(`td[data-task="${task.id}"][data-tier="${tier}"][data-metric="${metric}"]`);
                if (cells.length !== 1) { missing.push(key + ' 单元格数量 ' + cells.length); continue; }
                const cell = cells[0], text = cell.textContent.trim();
                if (!c) { if (text !== '无该档位') bad.push(key + ' 缺档标记不符'); continue; }
                if (metric === 'config') {
                    const dims = [...cell.querySelectorAll('[data-dim]')].map(d => [d.dataset.dim, JSON.parse(d.dataset.values)]);
                    bad.push(...(window.__cfgCheck(task.id, tier, dims, text) || []).map(x => key + ' ' + x));
                    continue;
                }
                if (metric.includes('policy-')) {
                    const old = metric.startsWith('old-');
                    if (old && tier !== 'xhard0') { if (text !== '—') bad.push(key + ' 旧入口适用范围不符'); }
                    else {
                        const pid = metric.replace(/^(old-)?policy-/, ''), counts = ((c.rates || {})[old ? 'old' : 'new'] || {})[pid];
                        const n = c.episodes.length, s = (counts || {}).success || 0;
                        if (!counts || !Object.keys(counts).length) bad.push(key + ' 成功率格缺评估数据');
                        else if (!text.includes(Math.round(100 * s / n) + '%') || !text.includes(s + ' / ' + n + ' 局成功'))
                            bad.push(key + ' 成功率不符：' + text + ' vs ' + s + '/' + n);
                    }
                    continue;
                }
                const value = cell.querySelector('.oracle-value')?.textContent || '', range = cell.querySelector('.oracle-range')?.textContent || '';
                if (metric === 'n' || metric === 'max_steps') {
                    if (gt[metric] == null ? text !== '—' : JSON.stringify(nums(value)) !== JSON.stringify([gt[metric]])) bad.push(key + ' 数值不符：' + text);
                } else {
                    const p = metric === 'exec' ? '' : metric + '_';
                    if (JSON.stringify(nums(value)) !== JSON.stringify([gt[p + 'mean']]) || JSON.stringify(nums(range)) !== JSON.stringify([gt[p + 'min'], gt[p + 'max']])) bad.push(key + ' 长度不符');
                }
            }
        }
    }
    return {bad, missing, checked};
}"""


def install_cfg_check(page, table1: dict) -> None:
    """把表 1 参照值注入页面，供 CHECK_JS 逐维比较（定值相等、区间落在内、维度集合相同）。"""
    page.evaluate("""([table1, noDim, x0]) => {
        window.__cfgCheck = (task, tier, dims, text) => {
            const want = table1[task] || {}, bad = [];
            if (tier === 'xhard0') { if (!text.includes(x0.slice(0, 8))) bad.push('xhard0 配置说明缺失'); return bad; }
            const names = Object.keys(want).filter(d => want[d][tier] !== undefined);
            if (!names.length) { if (!text.includes(noDim.slice(0, 8))) bad.push('无梯度说明缺失'); return bad; }
            if (JSON.stringify(dims.map(d => d[0]).sort()) !== JSON.stringify(names.slice().sort())) bad.push('配置维度不符');
            for (const [dim, values] of dims) {
                const w = (want[dim] || {})[tier];
                const okv = v => Array.isArray(w) ? v >= w[0] && v <= w[1] : v === w;
                if (!values.length || !values.every(okv)) bad.push(`配置 ${dim}=${JSON.stringify(values)} 与表 1 不符`);
            }
            return bad;
        };
    }""", [table1, C.NO_DIM_TEXT, C.XHARD0_TEXT])


def delivery_exec(path: Path) -> dict:
    """``delivery.json`` 逐格执行步统计（与 v8_subgoal_lengths 同口径）。"""
    data = C.load_delivery(path)
    by_cell: dict = defaultdict(list)
    for row in data["rows"]:
        by_cell[(row["task"], row["tier"])].append(row["exec_steps"])
    return {k: {"mean": round(statistics.mean(v), 1), "min": min(v), "max": max(v), "n": len(v)} for k, v in by_cell.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8081")
    ap.add_argument("--shots", type=Path, required=True)
    ap.add_argument("--delivery", type=Path, help="可选：再与 delivery.json 的 exec_steps 逐格核对")
    ap.add_argument("--expect-cells", type=int, default=None,
                    help="期望格数；缺省由目录推出（完整根 len(V8_CELLS)+16 = 59，子表为目录新值格数 + 16）")
    ap.add_argument("--chrome", help="Chromium 可执行文件；缺省用 Playwright 自带")
    args = ap.parse_args()
    args.shots.mkdir(parents=True, exist_ok=True)
    base = args.base.rstrip("/")
    problems: list[str] = []
    missing: list[str] = []
    errors: list[str] = []
    cells = 0
    catalog: dict = {"tasks": []}
    table1 = {task: {dim: dict(v) for dim, v in dims.items()} for task, dims in C.TABLE1.items()}
    with sync_playwright() as pw:
        launch = {"headless": True, "args": ["--disable-gpu"]}
        if args.chrome:
            launch["executable_path"] = args.chrome
        browser = pw.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            catalog = page.request.get(base + "/api/catalog").json()
            sg = page.request.get(base + "/api/subgoals").json()
            if not isinstance(sg, dict) or sg.get("schema") != "v8-subgoals/1" or not sg.get("oracle"):
                raise RuntimeError("subgoals.json 缺失或为空（/api/subgoals 不是 v8-subgoals/1）")
            want = [(t["id"], tier) for t in catalog["tasks"] for tier in t["tiers"]]
            cells = len(want)
            for task, tier in want:
                if tier not in sg["oracle"].get(task, {}):
                    missing.append(f"{task}/{tier} oracle 缺格")
            if args.delivery:
                for (task, tier), st in delivery_exec(args.delivery).items():
                    gt = sg["oracle"].get(task, {}).get(tier)
                    if gt is None or [gt["mean"], gt["min"], gt["max"], gt["n"]] != [st["mean"], st["min"], st["max"], st["n"]]:
                        problems.append(f"{task}/{tier} 执行步统计与 delivery.json 不符：{gt} vs {st}")
            page.goto(base + "/#view=oracle", wait_until="domcontentloaded")
            page.wait_for_selector("#oracle-section .oracle-table")
            install_cfg_check(page, table1)
            heads = [h.split("\n")[0].strip() for h in page.locator("#oracle-section .oracle-table thead th").all_inner_texts()]
            if heads != ["任务", "对比项", *catalog["tiers"]]:
                problems.append(f"总表表头不符：{heads}")
            result = page.evaluate(CHECK_JS, {"cat": catalog, "oracle": sg["oracle"], "metrics": METRICS,
                                              "scope": "#oracle-section"})
            problems += result["bad"]
            missing += result["missing"]
            if result["checked"] != cells:
                problems.append(f"总表核对格数 {result['checked']} != {cells}")
            for metric in METRICS:
                toggle = page.locator(f'#oracle-section input[data-oracle-metric="{metric}"]')
                if not toggle.is_checked():
                    problems.append(f"默认未勾选 {metric}")
                toggle.uncheck()
                if page.locator(f'#oracle-section td[data-metric="{metric}"]:visible').count():
                    problems.append(f"取消后仍显示 {metric}")
                toggle.check()
            for width in (390, 1024, 1440):
                page.set_viewport_size({"width": width, "height": 1000})
                page.wait_for_timeout(300)
                if page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"):
                    problems.append(f"{width}px 页面横向溢出")
                page.screenshot(path=str(args.shots / f"oracle-{width}.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
            # 任务页不再显示各档对比表（用户 2026-10-01「每个页面的这个表格不要再显示了。太占位置」）：
            # 逐任务确认 #matrix 是隐藏的空容器；配置、长度与评估位只在上面的「各档总表」核对
            for task in catalog["tasks"]:
                tier = next(iter(task["tiers"]))
                page.evaluate("h => { location.hash = h; }", f"#task={task['id']}&tier={tier}&ep=1")
                page.wait_for_function("() => !document.getElementById('task-section').hidden")
                if not page.evaluate("() => { const m = document.getElementById('matrix'); return m && m.hidden && !m.children.length; }"):
                    problems.append(f"任务页 {task['id']} 的对比表未撤下")
            page.screenshot(path=str(args.shots / "task-1440.png"))
        except Exception as exc:
            problems.append(f"检查中断：{type(exc).__name__}: {exc}")
        finally:
            browser.close()
    expect = args.expect_cells
    if expect is None:
        try:
            H = C.load_hard_specs()
            new_cells = {(t["id"], tier) for t in catalog["tasks"] for tier in t["tiers"] if tier != "xhard0"}
            expect = (len(H.V8_CELLS) if new_cells == set(H.V8_CELLS) else len(new_cells)) + len(C.NAMES)
        except Exception as exc:
            problems.append(f"无法推出期望格数：{type(exc).__name__}: {exc}")
            expect = -1
    if cells != expect:
        problems.append(f"格数 {cells} != 期望 {expect}")
    problems += ["页面脚本错误：" + e for e in errors]
    report = {"cells": cells, "missing": missing, "problems": problems, "page_errors": errors}
    (args.shots / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for line in (missing + problems)[:60]:
        print(f"# {line}")
    ok = not problems and not missing
    print(f"V8_ORACLE_BROWSER={'PASS' if ok else 'FAIL'} cells={cells} missing={len(missing)} "
          f"mismatch={len(problems)} page_errors={len(errors)}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
