"""核查放置任务子目标说明、已知问题提示与现有播放器。"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path(__file__).resolve().parent
errors=[]
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path='/home/hongzefu/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',args=['--disable-gpu'])
    page=b.new_page(viewport={'width':1440,'height':1100})
    page.on('pageerror',lambda e:errors.append(str(e)))
    for task in ('VideoPlaceButton','VideoPlaceOrder'):
        page.goto('http://127.0.0.1:8060/#task='+task,wait_until='domcontentloaded')
        page.wait_for_function('task=>document.getElementById("selected-id")?.textContent===task',arg=task)
        page.wait_for_selector('.subgoal-flow')
        assert page.locator('.subgoal-flow').count()==5
        assert page.locator('.subgoal-stage').count()==15
        if task=='VideoPlaceButton':
            assert page.locator('#known-issue').is_visible()
            text=page.locator('#known-issue').inner_text()
            assert all(x in text for x in ('示例4','示例7','平台B','平台A','不能证明'))
            assert page.locator('.subgoal-memory').first.inner_text().find('最后一次')>=0
            page.screenshot(path=str(out/'button-desktop.png'))
        else:
            assert not page.locator('#known-issue').is_visible()
            assert '不重演完整访问序列' in page.locator('.subgoal-flow').first.inner_text()
            page.screenshot(path=str(out/'order-desktop.png'))
        for card in page.locator('.difficulty-card').all():
            v=card.locator('video')
            v.evaluate('(v)=>{v.muted=true;return v.play();}')
            page.wait_for_function('id=>document.getElementById(id).querySelector("video").currentTime>.25',arg=card.get_attribute('id'),timeout=15000)
            v.evaluate('(v)=>v.pause()')
        print('SUBGOAL_BROWSER_TASK=PASS task='+task,flush=True)
    page.goto('http://127.0.0.1:8060/#task=VideoPlaceButton',wait_until='domcontentloaded')
    page.wait_for_function('document.getElementById("selected-id")?.textContent==="VideoPlaceButton"')
    page.wait_for_selector('#known-issue:not([hidden])')
    page.set_viewport_size({'width':390,'height':900})
    page.wait_for_timeout(300)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(out/'button-mobile.png'),full_page=False)
    page.goto('http://127.0.0.1:8060/#task=BinFill',wait_until='domcontentloaded')
    page.wait_for_function('document.getElementById("selected-id")?.textContent==="BinFill"')
    page.wait_for_selector('.difficulty-card')
    assert page.locator('.subgoal-flow').count()==0
    assert not page.locator('#known-issue').is_visible()
    assert not errors,errors
    b.close()
report={'status':'PASS','tasks':2,'tier_flows':10,'stages':30,'video_playback':10,'known_issue_only_vpb':True,'mobile_no_overflow':True,'other_task_unchanged':True,'page_errors':errors}
(out/'flow-browser-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('SUBGOAL_BROWSER=PASS tasks=2 tiers=10 playback=10 issue=1 mobile=1 errors=0')
