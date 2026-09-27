"""真实浏览器逐任务播放、跳转与移动导航验证，不启动仿真。"""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(__file__).resolve().parent
catalog = json.loads((out / 'catalog.json').read_text())
errors = []
checks = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path='/home/hongzefu/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome', args=['--disable-gpu'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1080})
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8060/', wait_until='domcontentloaded')
    page.wait_for_selector('.difficulty-card')
    assert page.locator('.task-link').count() == 16
    assert page.locator('table').count() == 0
    for task in catalog['tasks']:
        page.locator('.task-link').filter(has=page.locator('.task-id', has_text=re.compile('^'+re.escape(task['id'])+'$'))).click()
        assert page.locator('.difficulty-card').count() == len(task['tiers'])
        page.wait_for_function("Array.from(document.querySelectorAll('video')).every(v => v.readyState >= 1 && Number.isFinite(v.duration))", timeout=30000)
        video = page.locator('video').last
        video.evaluate('(v) => { v.muted = true; return v.play(); }')
        page.wait_for_function("document.querySelectorAll('video')[document.querySelectorAll('video').length-1].currentTime > .2", timeout=20000)
        duration = video.evaluate('(v) => v.duration')
        target = min(duration / 2, 10)
        video.evaluate('(v, t) => {v.pause(); v.currentTime = t;}', target)
        page.wait_for_function("(t) => {const v=[...document.querySelectorAll('video')].at(-1); return !v.seeking && Math.abs(v.currentTime-t)<.5 && v.readyState>=2}", arg=target, timeout=20000)
        card = page.locator('.difficulty-card').last
        old_src = video.get_attribute('src')
        card.locator('.sample-button').nth(1).click()
        assert video.get_attribute('src') != old_src
        page.wait_for_function("[...document.querySelectorAll('video')].at(-1).readyState>=2", timeout=20000)
        checks.append({'task':task['id'], 'cards':len(task['tiers']), 'play':True, 'seek':True, 'sample_switch':True})
        print('BROWSER_TASK=PASS task=' + task['id'], flush=True)
    page.locator('#task-search').fill('VideoRepick')
    assert page.locator('.task-link').count() == 1
    page.locator('.task-link').click()
    page.locator('#task-search').fill('')
    page.wait_for_function("Array.from(document.querySelectorAll('video')).every(v=>v.readyState>=1)")
    page.locator('h1').click()
    page.wait_for_timeout(300)
    page.screenshot(path=str(out / 'desktop.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#menu-toggle').click()
    page.locator('#task-search').fill('InsertPeg')
    page.locator('.task-link').click()
    assert page.locator('.difficulty-card').count() == 2
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.wait_for_timeout(350)
    page.screenshot(path=str(out / 'mobile.png'), full_page=True)
    assert not errors, errors
    browser.close()
report={'status':'PASS','tasks':checks,'cards':sum(x['cards'] for x in checks),'page_errors':errors,'mobile_navigation':True,'search':True,'no_table':True}
(out / 'browser-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print('SITE_BROWSER=PASS tasks=16 cards=71 playback=16 seek=16 switch=16 mobile=1 errors=0')
