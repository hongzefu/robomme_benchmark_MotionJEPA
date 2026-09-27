"""逐样例核查真实子目标列表切换及播放器，避免按档位套用概括。"""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path(__file__).resolve().parent
checks=[];errors=[]
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path='/home/hongzefu/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',args=['--disable-gpu'])
    page=b.new_page(viewport={'width':1440,'height':1100})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8060/',wait_until='domcontentloaded')
    page.wait_for_selector('.task-link')
    catalog=page.request.get('http://127.0.0.1:8060/api/catalog').json()
    for task in catalog['tasks']:
        if task['id'] not in ('VideoPlaceButton','VideoPlaceOrder'):continue
        page.locator('.task-link').filter(has=page.locator('.task-id',has_text=re.compile('^'+task['id']+'$'))).click()
        for tier in task['tiers']:
            card=page.locator('.difficulty-card[data-tier="'+tier['id']+'"]')
            for index,sample in enumerate(tier['videos']):
                card.locator('.sample-button').nth(index).click()
                expected=sample['subgoal_flow']
                stages=card.locator('.subgoal-stage')
                assert stages.count()==2
                assert stages.nth(0).locator('li').all_text_contents()==expected['demo_steps']
                assert stages.nth(1).locator('li').all_text_contents()==expected['execution_steps']
                assert stages.nth(0).locator('h4').inner_text()=='演示子目标'
                assert stages.nth(1).locator('h4').inner_text()=='执行子目标'
                assert card.locator('.subgoal-memory').count()==0
                text=card.locator('.subgoal-flow').inner_text()
                assert '需要记住' not in text and '读取题目' not in text
                v=card.locator('video')
                assert v.get_attribute('src').endswith(sample['url'])
                v.evaluate('(v)=>{v.muted=true;return v.play();}')
                page.wait_for_function('id=>{const v=Array.from(document.querySelectorAll("video")).find(v=>v.src.endsWith("/media/"+id));return v&&v.currentTime>.2&&!v.error;}',arg=sample['id'],timeout=15000)
                v.evaluate('(v)=>v.pause()')
                checks.append({'task':task['id'],'tier':tier['id'],'id':sample['id'],'demo_subgoals':len(expected['demo_steps']),'execution_subgoals':len(expected['execution_steps']),'list_exact':True,'playback':True})
        print('ATOMIC_TASK=PASS task='+task['id'],flush=True)
    page.goto('http://127.0.0.1:8060/#task=VideoPlaceButton')
    page.wait_for_function('document.getElementById("selected-id").textContent==="VideoPlaceButton"')
    card=page.locator('.difficulty-card[data-tier="xhard3"]')
    card.locator('.sample-button').nth(1).click()
    card.screenshot(path=str(out/'button-xhard3-atomic.png'))
    page.set_viewport_size({'width':390,'height':900})
    page.wait_for_timeout(350)
    card.locator('.subgoal-flow').scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(out/'mobile-atomic.png'))
    page.goto('http://127.0.0.1:8060/#task=BinFill')
    page.wait_for_function('document.getElementById("selected-id").textContent==="BinFill"')
    assert page.locator('.subgoal-flow').count()==0
    assert not errors,errors
    b.close()
assert len(checks)==30
(out/'atomic-browser-result.json').write_text(json.dumps({'status':'PASS','samples':checks,'page_errors':errors,'mobile_no_overflow':True,'other_tasks_unchanged':True},ensure_ascii=False,indent=2)+'\n')
print('ATOMIC_SUBGOAL_BROWSER=PASS samples=30 lists_exact=30 playback=30 errors=0')
