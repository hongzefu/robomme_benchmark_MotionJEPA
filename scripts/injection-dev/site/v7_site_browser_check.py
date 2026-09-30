#!/usr/bin/env python3
"""v7 对照站点的浏览器交互检查（0929 站点方案 §6）：Playwright + headless Chromium，连测试实例，不碰线上 8070。

逐格（16 任务 × 各自档位，共 71 格）按 hash 直达第 1 局，核对：
- 栏数：xhard0 为 6 栏（新旧入口各 3 栏），其余 3 栏；
- 每个视频元数据可读（``readyState>=1``、无 ``error``），并实际播放首个评估视频（``currentTime>0.2``）；
- 局号数等于目录局数。

另外抽查：
- xhard0「新旧入口翻转」筛选在全部任务上的合计等于目录 flip 数；
- MME 两局 error 显示 3 个重评页签，可切换；
- 两局生成失败显示「生成失败」；
- 「同步播放」让本局全部视频前进；
- 390px 宽度下无横向溢出。

截图写到 ``--shots``。末行打印 ``V7_SITE_BROWSER=PASS|FAIL …``。

    uv run --no-project --with playwright python scripts/injection-dev/site/v7_site_browser_check.py \\
      --base http://127.0.0.1:8071 --shots artifacts/newtask-v7/site-checks
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROME = "/home/hongzefu/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"


def wait_played(page, selector: str, timeout_ms: int = 15000) -> bool:
    try:
        page.wait_for_function(
            """sel => { const v = document.querySelector(sel); return v && v.currentTime > 0.2; }""",
            arg=selector, timeout=timeout_ms)
        return True
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8071")
    ap.add_argument("--shots", type=Path, required=True)
    args = ap.parse_args()
    args.shots.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    page_errors: list[str] = []
    cells = played = videos_meta = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=CHROME, args=["--disable-gpu", "--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        catalog = page.request.get(f"{args.base}/api/catalog").json()
        page.goto(f"{args.base}/", wait_until="domcontentloaded")
        page.wait_for_selector(".task-link")
        flip_total = 0
        error_eps, genfail_eps = [], []
        for task in catalog["tasks"]:
            for tier, cell in task["tiers"].items():
                cells += 1
                page.evaluate("h => { location.hash = h; }", f"#task={task['id']}&tier={tier}&ep=1")
                want_cols = 6 if tier == "xhard0" else 3
                try:
                    page.wait_for_function(
                        "([t, tier, n]) => document.querySelector('#episode h3')?.textContent.startsWith(t + ' · ' + tier + ' · 第 1 局')"
                        " && document.querySelectorAll('#episode .col').length === n",
                        arg=[task["id"], tier, want_cols], timeout=10000)
                except Exception:
                    problems.append(f"{task['id']}/{tier} 栏数或标题不符")
                    continue
                chips = page.locator("#chips .chip").count()
                if chips != len(cell["episodes"]):
                    problems.append(f"{task['id']}/{tier} 局号 {chips} != {len(cell['episodes'])}")
                try:
                    page.wait_for_function(
                        "() => [...document.querySelectorAll('#episode video')].every(v => v.readyState >= 1 && !v.error)",
                        timeout=15000)
                    videos_meta += page.locator("#episode video").count()
                except Exception:
                    problems.append(f"{task['id']}/{tier} 视频元数据未就绪")
                page.evaluate("() => { const v = document.querySelectorAll('#episode video')[1]; v.play(); }")
                if wait_played(page, "#episode .col:nth-child(2) video"):
                    played += 1
                else:
                    problems.append(f"{task['id']}/{tier} 评估视频未播放")
                page.evaluate("() => document.querySelectorAll('video').forEach(v => v.pause())")
                if tier == "xhard0":
                    flip_btn = page.locator('#filters .filter[data-filter="flip"]')
                    flip_total += int(flip_btn.inner_text().split()[-1])
                for ep in cell["episodes"]:
                    if any(r.get("status") == "error" for r in ep["eval"]["new"].values()):
                        error_eps.append((task["id"], tier, ep["idx"]))
                    if any(g.get("status") == "generation_failed" for g in ep["gen"].values()):
                        genfail_eps.append((task["id"], tier, ep["idx"]))
        want_flip = sum(1 for t in catalog["tasks"] for ep in t["tiers"].get("xhard0", {"episodes": []})["episodes"]
                        if any(ep.get("flip", {}).values()))
        if flip_total != want_flip:
            problems.append(f"翻转筛选合计 {flip_total} != 目录 {want_flip}")

        for task, tier, idx in error_eps:
            page.evaluate("h => { location.hash = h; }", f"#task={task}&tier={tier}&ep={idx}")
            page.wait_for_function("i => document.querySelector('#episode h3')?.textContent.includes('第 ' + i + ' 局')", arg=idx)
            n = page.locator("#episode .attempt").count()
            if n != 3:
                problems.append(f"{task}/{tier}/{idx} 重评页签 {n} != 3")
            else:
                page.locator("#episode .attempt").nth(2).click()
                if page.locator("#episode .attempt").nth(2).get_attribute("aria-pressed") != "true":
                    problems.append(f"{task}/{tier}/{idx} 重评页签切换失败")
            page.screenshot(path=str(args.shots / f"error-{task}-{tier}-{idx}.png"), full_page=True)
        for task, tier, idx in genfail_eps:
            page.evaluate("h => { location.hash = h; }", f"#task={task}&tier={tier}&ep={idx}")
            page.wait_for_function("i => document.querySelector('#episode h3')?.textContent.includes('第 ' + i + ' 局')", arg=idx)
            if page.locator("#episode .badge.s-generation_failed").count() != 2:
                problems.append(f"{task}/{tier}/{idx} 未显示两处生成失败")
        page.screenshot(path=str(args.shots / "genfail.png"), full_page=True)

        # 同步播放：xhard0 BinFill 第 1 局，6 个视频都前进
        page.evaluate("h => { location.hash = h; }", "#task=BinFill&tier=xhard0&ep=1")
        page.wait_for_function("() => document.querySelectorAll('#episode video').length === 6"
                               " && [...document.querySelectorAll('#episode video')].every(v => v.readyState >= 1)")
        page.click("#sync-play")
        try:
            page.wait_for_function("() => [...document.querySelectorAll('#episode video')].every(v => v.currentTime > 0.2)", timeout=20000)
        except Exception:
            problems.append("同步播放后并非全部视频前进")
        sync_ok = "同步播放后并非全部视频前进" not in problems
        page.screenshot(path=str(args.shots / "xhard0-binfill.png"), full_page=True)
        page.evaluate("h => { location.hash = h; }", "#task=BinFill&tier=xhard1&ep=1")
        page.wait_for_function("() => document.querySelectorAll('#episode .col').length === 3")
        page.screenshot(path=str(args.shots / "xhard1-binfill.png"), full_page=True)

        mobile = browser.new_page(viewport={"width": 390, "height": 900})
        mobile.goto(f"{args.base}/#task=VideoPlaceOrder&tier=xhard0&ep=1", wait_until="domcontentloaded")
        mobile.wait_for_selector("#episode .col")
        overflow = mobile.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        if overflow > 0:
            problems.append(f"390px 横向溢出 {overflow}px")
        mobile.screenshot(path=str(args.shots / "mobile.png"), full_page=True)
        browser.close()
    problems += [f"页面报错：{e}" for e in page_errors]
    for problem in problems[:40]:
        print(f"# {problem}")
    ok = not problems
    result = {"cells": cells, "played": played, "videos_meta": videos_meta, "flip_total": flip_total,
              "error_eps": error_eps, "genfail_eps": genfail_eps, "sync_ok": sync_ok, "problems": problems}
    (args.shots / "browser-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(f"V7_SITE_BROWSER={'PASS' if ok else 'FAIL'} cells={cells} videos_meta={videos_meta} played={played} "
          f"flip={flip_total} error_tabs={len(error_eps)} genfail={len(genfail_eps)} sync={int(sync_ok)} "
          f"overflow={int(any('溢出' in x for x in problems))} page_errors={len(page_errors)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
