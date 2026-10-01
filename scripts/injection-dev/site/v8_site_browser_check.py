#!/usr/bin/env python3
"""v8 站点的浏览器交互检查（v8 方案第一部分 §3「站点与 v7 布局一致」）：Playwright + headless Chromium，连测试实例。

由 ``v7_site_browser_check.py`` 改写。v7 的评估断言（评估视频播放、翻转／重跑筛选合计、MME error 页签、6 路同步）
全部删除或反转——v8 不做两策略评估，评估板块原位保留、内容置空。逐格（目录里全部 (任务, 档)，完整根 59 格）
按 hash 直达第 1 局，核对：

- **布局**：v7 页面的 15 个 DOM 区块都在（``SECTIONS``）；
- **评估位**：每个评估栏显示「未评估」占位（新值局 2 栏、xhard0 新旧入口各 2 栏），计数进 ``eval_placeholders``；
  局号点全部为空心「未评估」；页面上没有成功／失败／超时／错误徽标（``fail_badges``）；
- **成败筛选**：两者都成／分歧／两者都未成／翻转／同卡重跑各按钮计数为 0，并实点「两者都未成」确认可见局号为 0
  （合计 ``eval_filter_hits``）；「未评估」按钮计数等于该格局数；
- **评估媒体**：全程拦截 ``/media/<id>`` 请求，凡不是目录里生成视频的 ID 记为 ``eval_media_requests``；
- **逐段数据**：``/api/subgoals`` 必须是 ``v8-subgoals/1``（缺失或空对象即 FAIL），每局（含 xhard0 旧入口）都有逐段记录，
  第 1 局页面的逐段表行数、task goal 条数与数据一致（``subgoal_missing``）；
- **配置**：任务页总表的配置格（``data-dim``／``data-values``）与逐局配置（``li[data-dim]``）逐维与表 1 一致
  （``v8_site_catalog.TABLE1``，定值相等、区间落在内），维度集合与表 1 相同（``config_mismatch``）；
- **xhard5 与生成视频**：表头含 xhard5、SwingXtimes／StopCube 的 xhard5 页签可用，每格第 1 局的生成视频元数据可读并实际播放
  （``currentTime > 0.2``）；「同步播放」让 xhard0 本局两段生成视频前进；
- 390px 宽度下无横向溢出；页面无脚本错误。

截图写到 ``--shots``。末行打印
``V8_SITE=PASS|FAIL sections=15 eval_placeholders=<n> eval_filter_hits=0 eval_media_requests=0 subgoal_missing=0 config_mismatch=0``
（另附 cells、played、fail_badges、page_errors）。

    uv run --no-project --with playwright python scripts/injection-dev/site/v8_site_browser_check.py \\
      --base http://127.0.0.1:8081 --shots artifacts/newtask-v8/site-checks
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("v8_site_catalog", HERE / "v8_site_catalog.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

SECTIONS = ("sidebar", "task-search", "task-nav", "status-panel", "outlier-section", "oracle-section", "task-section",
            "matrix", "tier-tabs", "filters", "legend", "rerun-panel", "chips", "episode", "notes")
VERDICT_FILTERS = ("both", "split", "none", "flip", "rerun")
FAIL_BADGES = ("#episode .badge.s-fail, #episode .badge.s-error, #episode .badge.s-timeout, #episode .badge.s-success, "
               "#chips .dot.s-fail, #chips .dot.s-error, #chips .dot.s-timeout, #chips .dot.s-success")
MEDIA = re.compile(r"/media/([A-Za-z0-9_-]{1,128})")


def wait_played(page, selector: str, timeout_ms: int = 15000) -> bool:
    try:
        page.wait_for_function(
            """sel => { const v = document.querySelector(sel); return v && v.currentTime > 0.2; }""",
            arg=selector, timeout=timeout_ms)
        return True
    except Exception:
        return False


def check_values(task: str, tier: str, dim: str, values) -> bool:
    return bool(values) and all(C.table1_ok(task, dim, tier, v) for v in values)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8081")
    ap.add_argument("--shots", type=Path, required=True)
    ap.add_argument("--chrome", help="Chromium 可执行文件；缺省用 Playwright 自带")
    args = ap.parse_args()
    args.shots.mkdir(parents=True, exist_ok=True)
    base = args.base.rstrip("/")
    problems: list[str] = []
    page_errors: list[str] = []
    media_requests: list[str] = []
    n = {"sections": 0, "cells": 0, "eval_placeholders": 0, "eval_filter_hits": 0, "subgoal_missing": 0,
         "config_mismatch": 0, "fail_badges": 0, "played": 0, "videos_meta": 0}
    want_placeholders = 0
    with sync_playwright() as p:
        launch = {"headless": True, "args": ["--disable-gpu", "--autoplay-policy=no-user-gesture-required"]}
        if args.chrome:
            launch["executable_path"] = args.chrome
        browser = p.chromium.launch(**launch)
        context = browser.new_context(viewport={"width": 1500, "height": 1100})
        context.on("request", lambda r: media_requests.append(r.url) if MEDIA.search(r.url) else None)
        page = context.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        catalog = page.request.get(f"{base}/api/catalog").json()
        sg = page.request.get(f"{base}/api/subgoals").json()
        gen_media = {g["media"] for t in catalog["tasks"] for cell in t["tiers"].values() for ep in cell["episodes"]
                     for g in ep.get("gen", {}).values() if g.get("media")}
        if any(ep.get("eval") for t in catalog["tasks"] for cell in t["tiers"].values() for ep in cell["episodes"]):
            problems.append("目录里有非空评估（v8 评估应置空）")
        if not isinstance(sg, dict) or sg.get("schema") != "v8-subgoals/1" or not sg.get("episodes"):
            problems.append("subgoals.json 缺失或为空（/api/subgoals 不是 v8-subgoals/1）")
            sg = {"episodes": {}, "oracle": {}}
        # 数据层：每局逐段记录齐全（xhard0 两个入口）
        for t in catalog["tasks"]:
            for tier, cell in t["tiers"].items():
                for ep in cell["episodes"]:
                    rec = sg["episodes"].get(t["id"], {}).get(tier, {}).get(str(ep["idx"]))
                    sides = ("new", "old") if tier == "xhard0" else ("new",)
                    if rec is None or any(s not in rec for s in sides) or "goal" not in rec:
                        n["subgoal_missing"] += 1
        if n["subgoal_missing"]:
            problems.append(f"逐段数据缺 {n['subgoal_missing']} 局")

        page.goto(f"{base}/", wait_until="domcontentloaded")
        page.wait_for_selector(".task-link")
        present = page.evaluate("ids => ids.filter(id => document.getElementById(id))", list(SECTIONS))
        n["sections"] = len(present)
        if n["sections"] != len(SECTIONS):
            problems.append(f"缺少区块：{sorted(set(SECTIONS) - set(present))}")
        heads = page.locator("#matrix .oracle-table thead th").all_inner_texts()
        if not any("xhard5" in h for h in heads):
            problems.append("任务页总表表头缺 xhard5 列")

        for task in catalog["tasks"]:
            for tier, cell in task["tiers"].items():
                n["cells"] += 1
                key = f"{task['id']}/{tier}"
                entries = 2 if tier == "xhard0" else 1
                want_placeholders += 2 * entries
                page.evaluate("h => { location.hash = h; }", f"#task={task['id']}&tier={tier}&ep=1")
                try:
                    page.wait_for_function(
                        "([t, tier, n]) => document.querySelector('#episode h3')?.textContent.startsWith(t + ' · ' + tier + ' · 第 1 局')"
                        " && document.querySelectorAll('#episode .col').length === n",
                        arg=[task["id"], tier, 3 * entries], timeout=10000)
                except Exception:
                    problems.append(f"{key} 栏数或标题不符")
                    continue
                ph = page.locator("#episode .eval-placeholder")
                cnt = ph.count()
                n["eval_placeholders"] += cnt
                if cnt != 2 * entries or page.locator("#episode .badge.s-unevaluated").count() != 2 * entries \
                        or any("未评估" not in x for x in ph.all_inner_texts()):
                    problems.append(f"{key} 评估占位 {cnt} != {2 * entries} 或文字不符")
                bad = page.locator(FAIL_BADGES).count()
                n["fail_badges"] += bad
                if bad:
                    problems.append(f"{key} 出现成败徽标 {bad} 个")
                chips = page.locator("#chips .chip").count()
                if chips != len(cell["episodes"]):
                    problems.append(f"{key} 局号 {chips} != {len(cell['episodes'])}")
                if page.locator("#chips .dot.s-unevaluated").count() != 2 * chips:
                    problems.append(f"{key} 局号点不全是「未评估」")
                counts = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#filters .filter')]"
                                       ".map(b => [b.dataset.filter, Number(b.textContent.trim().split(/\\s+/).pop())]))")
                hits = sum(counts.get(f, 0) for f in VERDICT_FILTERS)
                n["eval_filter_hits"] += hits
                if hits:
                    problems.append(f"{key} 成败筛选命中 {hits}")
                if counts.get("uneval") != len(cell["episodes"]):
                    problems.append(f"{key} 未评估计数 {counts.get('uneval')} != {len(cell['episodes'])}")
                # 逐段
                rec = sg["episodes"].get(task["id"], {}).get(tier, {}).get("1")
                if rec is not None:
                    rows = page.locator("#episode .sg-ep .sg-table tr").count()
                    segs = len(rec.get("new", []))
                    goals = page.locator("#episode .goal ol li").count()
                    if (segs and rows != segs + 1) or goals != max(1, len(rec.get("goal", []))):
                        n["subgoal_missing"] += 1
                        problems.append(f"{key} 第 1 局逐段表 {rows - 1}/{segs} 行或 goal {goals} 条不符")
                # 配置（总表格 + 逐局）
                if tier != "xhard0":
                    want_dims = set(C.TABLE1.get(task["id"], {}))
                    items = page.evaluate(
                        "t => [...document.querySelectorAll(`#matrix td[data-tier=\"${t}\"][data-metric=\"config\"] [data-dim]`)]"
                        ".map(d => [d.dataset.dim, JSON.parse(d.dataset.values)])", tier)
                    lis = page.evaluate("() => [...document.querySelectorAll('#episode .cfg-sem li[data-dim]')]"
                                        ".map(d => [d.dataset.dim, JSON.parse(d.dataset.value)])")
                    if {d for d, _ in items} != want_dims or {d for d, _ in lis} != want_dims:
                        n["config_mismatch"] += 1
                        problems.append(f"{key} 配置维度不符：{sorted(d for d, _ in items)} vs 表 1 {sorted(want_dims)}")
                    for dim, values in items:
                        if not check_values(task["id"], tier, dim, values):
                            n["config_mismatch"] += 1
                            problems.append(f"{key} 总表配置 {dim}={values} 与表 1 不符")
                    for dim, value in lis:
                        if not check_values(task["id"], tier, dim, [value]):
                            n["config_mismatch"] += 1
                            problems.append(f"{key} 第 1 局配置 {dim}={value} 与表 1 不符")
                    if not want_dims and C.NO_DIM_TEXT not in page.locator(
                            f'#matrix td[data-tier="{tier}"][data-metric="config"]').inner_text():
                        problems.append(f"{key} 无梯度任务的配置说明缺失")
                # 生成视频
                if cell["episodes"][0]["gen"].get("new", {}).get("media"):
                    try:
                        page.wait_for_function(
                            "() => [...document.querySelectorAll('#episode video')].every(v => v.readyState >= 1 && !v.error)",
                            timeout=15000)
                        n["videos_meta"] += page.locator("#episode video").count()
                    except Exception:
                        problems.append(f"{key} 视频元数据未就绪")
                    page.evaluate("() => document.querySelector('#episode .col video').play()")
                    if wait_played(page, "#episode .col video"):
                        n["played"] += 1
                    else:
                        problems.append(f"{key} 生成视频未播放")
                    page.evaluate("() => document.querySelectorAll('video').forEach(v => v.pause())")
                if tier == "xhard5" and task["id"] == "SwingXtimes":
                    page.wait_for_timeout(300)
                    page.screenshot(path=str(args.shots / "xhard5-swingxtimes.png"), full_page=True)

        # 实点成败筛选：可见局号必须为 0；再点「未评估」恢复全部
        page.evaluate("h => { location.hash = h; }", "#task=BinFill&tier=xhard1&ep=1")
        page.wait_for_function("() => document.querySelector('#episode h3')?.textContent.startsWith('BinFill · xhard1')")
        for filt in ("both", "split", "none"):
            page.click(f'#filters .filter[data-filter="{filt}"]')
            visible = page.locator("#chips .chip:visible").count()
            n["eval_filter_hits"] += visible
            if visible:
                problems.append(f"点「{filt}」后可见局号 {visible} 个")
        page.click('#filters .filter[data-filter="uneval"]')
        if page.locator("#chips .chip:visible").count() != page.locator("#chips .chip").count():
            problems.append("「未评估」筛选没有显示全部局号")
        page.click('#filters .filter[data-filter="all"]')
        page.screenshot(path=str(args.shots / "xhard1-binfill.png"), full_page=True)

        # xhard5 页签
        page.evaluate("h => { location.hash = h; }", "#task=StopCube&tier=xhard5&ep=1")
        page.wait_for_function("() => document.querySelector('#episode h3')?.textContent.startsWith('StopCube · xhard5')")
        if page.locator('#tier-tabs .tier-tab:has-text("xhard5"):not([disabled])').count() != 1:
            problems.append("StopCube 的 xhard5 页签不可用")
        page.screenshot(path=str(args.shots / "xhard5-stopcube.png"), full_page=True)

        # 同步播放：xhard0 BinFill 第 1 局，两段生成视频都前进
        page.evaluate("h => { location.hash = h; }", "#task=BinFill&tier=xhard0&ep=1")
        page.wait_for_function("() => document.querySelectorAll('#episode video').length === 2"
                               " && [...document.querySelectorAll('#episode video')].every(v => v.readyState >= 1)")
        page.click("#sync-play")
        try:
            page.wait_for_function("() => [...document.querySelectorAll('#episode video')].every(v => v.currentTime > 0.2)",
                                   timeout=20000)
        except Exception:
            problems.append("同步播放后并非全部生成视频前进")
        page.evaluate("() => document.querySelectorAll('video').forEach(v => v.pause())")
        page.screenshot(path=str(args.shots / "xhard0-binfill.png"), full_page=True)

        page.evaluate("location.hash='#view=oracle'")
        try:
            page.wait_for_selector("#oracle-section .oracle-table", timeout=10000)
            if page.locator("#oracle-section td[data-metric^='policy-'] .eval-uneval").count() == 0:
                problems.append("各档总表成功率格没有显示「未评估」")
        except Exception:
            problems.append("各档总表未显示")
        page.screenshot(path=str(args.shots / "oracle.png"), full_page=False)

        mobile = context.new_page()
        mobile.set_viewport_size({"width": 390, "height": 900})
        mobile.goto(f"{base}/#task=VideoPlaceOrder&tier=xhard0&ep=1", wait_until="domcontentloaded")
        mobile.wait_for_selector("#episode .col")
        overflow = mobile.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        if overflow > 0:
            problems.append(f"390px 横向溢出 {overflow}px")
        mobile.screenshot(path=str(args.shots / "mobile.png"), full_page=True)
        browser.close()

    eval_media = sorted({m.group(1) for url in media_requests if (m := MEDIA.search(url)) and m.group(1) not in gen_media})
    n["eval_media_requests"] = len(eval_media)
    if eval_media:
        problems.append(f"出现非生成视频的媒体请求 {len(eval_media)} 个")
    if n["eval_placeholders"] != want_placeholders:
        problems.append(f"评估占位合计 {n['eval_placeholders']} != {want_placeholders}")
    problems += [f"页面报错：{e}" for e in page_errors]
    for problem in problems[:60]:
        print(f"# {problem}")
    ok = not problems and n["sections"] == len(SECTIONS)
    (args.shots / "browser-result.json").write_text(
        json.dumps({**n, "want_placeholders": want_placeholders, "media_requests": len(media_requests),
                    "problems": problems}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"V8_SITE={'PASS' if ok else 'FAIL'} sections={n['sections']} eval_placeholders={n['eval_placeholders']} "
          f"eval_filter_hits={n['eval_filter_hits']} eval_media_requests={n['eval_media_requests']} "
          f"subgoal_missing={n['subgoal_missing']} config_mismatch={n['config_mismatch']} "
          f"cells={n['cells']} played={n['played']} fail_badges={n['fail_badges']} page_errors={len(page_errors)}",
          flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
