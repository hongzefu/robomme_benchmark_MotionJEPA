#!/usr/bin/env python3
"""核对总表全部数据及筛选、滚动、跳转；不播放视频、不修改服务端。

可用 --html 将本次浏览器的根页面响应替换为候选 HTML，接口仍取 --base。
截图和核验报告仅写到 --shots 指定目录。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

CHROME = "/home/hongzefu/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
METRICS = ["config", "total", "demo", "exec", "policy-simplememvla", "policy-mmevla", "n"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8070")
    parser.add_argument("--html", type=Path)
    parser.add_argument("--shots", type=Path, required=True)
    args = parser.parse_args()
    args.shots.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    errors: list[str] = []
    checks: dict = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=CHROME, args=["--disable-gpu"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        if args.html:
            html = args.html.read_text(encoding="utf-8")

            def replace_root(route):
                if urlsplit(route.request.url).path == "/":
                    route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
                else:
                    route.continue_()

            page.route(args.base.rstrip("/") + "/**", replace_root)
        try:
            catalog = page.request.get(args.base.rstrip("/") + "/api/catalog").json()
            subgoals = page.request.get(args.base.rstrip("/") + "/api/subgoals").json()
            page.goto(args.base.rstrip("/") + "/#view=oracle", wait_until="domcontentloaded")
            page.wait_for_selector("#oracle-section .oracle-table")
            result = page.evaluate("""({cat, sg, metrics}) => {
                const bad = [], norm = s => s.replace(/\\s+/g, ''), nums = s => (s.match(/\\d+(?:\\.\\d+)?/g)||[]).map(Number);
                let records = 0, values = 0, absent = 0;
                const root = document.querySelector('#oracle-section');
                const heads = [...root.querySelectorAll('.oracle-table thead th')].map(x=>[...x.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim());
                if (JSON.stringify(heads)!==JSON.stringify(['任务','对比项',...cat.tiers])) bad.push('固定七列表头不符：'+heads);
                for (const task of cat.tasks) {
                    const th = root.querySelector(`th.oracle-task[data-task="${task.id}"]`) || [...root.querySelectorAll('th.oracle-task')].find(x=>x.textContent.includes(task.id));
                    if (!th || Number(th.rowSpan)!==metrics.length) bad.push(task.id+' 任务标题跨行不符');
                    for (const tier of cat.tiers) {
                        const gt = (sg.oracle[task.id]||{})[tier], c = task.tiers[tier];
                        if (gt && c) records++;
                        for (const metric of metrics) {
                            const key = `${task.id}/${tier}/${metric}`;
                            const cells = root.querySelectorAll(`td[data-task="${task.id}"][data-tier="${tier}"][data-metric="${metric}"]`);
                            if (cells.length!==1) {bad.push(key+' 单元格数量 '+cells.length); continue;}
                            const cell=cells[0];
                            if (!gt || !c) {if (cell.textContent.trim()!=='无该档位') bad.push(key+' 缺档标记不符'); absent++; continue;}
                            values++;
                            if (metric==='config') {
                                const actual=cell.innerText.split('\\n').map(x=>x.trim()).filter(Boolean);
                                const expected=tierConfig(task.id,tier,null);
                                if (JSON.stringify(actual)!==JSON.stringify(expected)) bad.push(key+' 配置不完整');
                                continue;
                            }
                            const value=cell.querySelector('.oracle-value')?.textContent||'';
                            const range=cell.querySelector('.oracle-range')?.textContent||'';
                            if (metric==='n') {if (JSON.stringify(nums(value))!==JSON.stringify([gt.n])) bad.push(key+' 样本数不符');}
                            else if (metric.startsWith('policy-')) {
                                const p=metric.slice(7), n=c.episodes.length, k=c.rates.new?.[p]?.success||0;
                                if (norm(value)!==Math.round(100*k/n)+'%' || norm(range)!==`${k}/${n}局成功`) bad.push(key+' 成功率不符');
                            } else {
                                const prefix=metric==='exec'?'':metric+'_';
                                if (JSON.stringify(nums(value))!==JSON.stringify([gt[prefix+'mean']]) || JSON.stringify(nums(range))!==JSON.stringify([gt[prefix+'min'],gt[prefix+'max']])) bad.push(key+' 长度不符');
                            }
                        }
                    }
                }
                return {bad, records, values, absent};
            }""", {"cat": catalog, "sg": subgoals, "metrics": METRICS})
            problems.extend(result.pop("bad"))
            checks["data"] = result
            if result["records"] != 71:
                problems.append(f"展示记录数不符：{result['records']} != 71")
            for metric in METRICS:
                toggle = page.locator(f'input[data-oracle-metric="{metric}"]')
                if not toggle.is_checked():
                    problems.append(f"默认未勾选 {metric}")
                toggle.uncheck()
                if page.locator(f'#oracle-section td[data-metric="{metric}"]:visible').count():
                    problems.append(f"取消后仍显示 {metric}")
                toggle.check()
            for metric in METRICS:
                page.locator(f'input[data-oracle-metric="{metric}"]').uncheck()
            if page.locator('#oracle-section td[data-metric]:visible').count() or "选择" not in page.locator('#oracle-section').inner_text():
                problems.append("全不选时未正确显示选择提示")
            for metric in METRICS:
                page.locator(f'input[data-oracle-metric="{metric}"]').check()
            task_id = catalog["tasks"][0]["id"]
            select = page.locator('#oracle-task-filter')
            all_value = select.input_value()
            select.select_option(task_id)
            visible_tasks = page.locator('#oracle-section td[data-task]').evaluate_all('(els)=>[...new Set(els.map(e=>e.dataset.task))]')
            if visible_tasks != [task_id]:
                problems.append("任务筛选不符")
            select.select_option(all_value)
            checks["interaction"] = "已核对七项隐藏恢复、全不选及任务筛选"
            for width in (390, 1024, 1440):
                page.set_viewport_size({"width": width, "height": 1000})
                # 等待响应式侧栏的 0.2 秒过渡结束，避免截图落在动画中间。
                page.wait_for_timeout(300)
                scroll = page.locator('.oracle-table').evaluate("""table => {
                    let box=table;
                    while(box && !(box.scrollWidth>box.clientWidth+1 && /auto|scroll/.test(getComputedStyle(box).overflowX))) box=box.parentElement;
                    if(!box) return {overflow:false,pageOverflow:document.documentElement.scrollWidth>innerWidth+1};
                    box.scrollLeft=box.scrollWidth; const right=box.scrollLeft;
                    box.scrollLeft=0;
                    return {overflow:true,right,left:box.scrollLeft,pageOverflow:document.documentElement.scrollWidth>innerWidth+1};
                }""")
                checks[str(width)] = scroll
                if scroll["pageOverflow"] or (scroll["overflow"] and (scroll["right"] <= 0 or scroll["left"] != 0)):
                    problems.append(f"{width}px 横向滚动异常")
                page.screenshot(path=str(args.shots / f"oracle-{width}.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator('th.oracle-task a').first.click()
            page.wait_for_selector('#task-section:visible')
            if not page.locator('#episode h3').inner_text() or not page.locator('#chips .chip').count():
                problems.append("逐局页基本内容缺失")
            page.evaluate("location.hash='#view=oracle'")
            page.wait_for_selector('#oracle-section .oracle-table:visible')
            page.evaluate("location.hash='#view=outliers'")
            page.wait_for_selector('#outlier-section:visible')
            if not page.locator('#outlier-section').inner_text().strip():
                problems.append("异常页内容为空")
            page.evaluate("location.hash='#view=oracle'")
            page.wait_for_selector('#oracle-section .oracle-table:visible')
            checks["navigation"] = "已核对任务链接、逐局页、异常页及返回总表"
        except Exception as exc:
            problems.append(f"检查中断：{type(exc).__name__}: {exc}")
        finally:
            browser.close()
    problems.extend("页面脚本错误：" + error for error in errors)
    report = {"checks": checks, "problems": problems, "page_errors": errors}
    (args.shots / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for problem in problems:
        print(problem)
    print(f"V7_ORACLE_BROWSER={'FAIL' if problems else 'PASS'} records={checks.get('data', {}).get('records', 0)} problems={len(problems)} report={args.shots / 'report.json'}")
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main())
