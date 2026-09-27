"""逐样例核查人读子目标标签、题目问句与「题目所问」标记及播放器（site-v10）。"""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path(__file__).resolve().parent
checks=[];errors=[]
def expected_texts(steps):
    result=[]
    for step in steps:
        text=step['text']
        if step.get('asked'):
            text+='◀ 题目所问'
            if step.get('note'):text+=step['note']
        result.append(text)
    return result
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path='/home/hongzefu/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',args=['--disable-gpu'])
    page=b.new_page(viewport={'width':1440,'height':1100})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8060/',wait_until='domcontentloaded')
    page.wait_for_selector('.task-link')
    catalog=page.request.get('http://127.0.0.1:8060/api/catalog').json()
    asked_total=0
    for task in catalog['tasks']:
        if task['id'] not in ('VideoPlaceButton','VideoPlaceOrder'):continue
        page.locator('.task-link').filter(has=page.locator('.task-id',has_text=re.compile('^'+task['id']+'$'))).click()
        for tier in task['tiers']:
            card=page.locator('.difficulty-card[data-tier="'+tier['id']+'"]')
            for index,sample in enumerate(tier['videos']):
                card.locator('.sample-button').nth(index).click()
                expected=sample['subgoal_flow']
                assert card.locator('.subgoal-question').inner_text()==expected['question']
                stages=card.locator('.subgoal-stage')
                assert stages.count()==2
                assert stages.nth(0).locator('li').all_text_contents()==expected_texts(expected['demo_steps'])
                assert stages.nth(1).locator('li').all_text_contents()==expected_texts(expected['execution_steps'])
                assert stages.nth(0).locator('h4').inner_text()=='演示子目标'
                assert stages.nth(1).locator('h4').inner_text()=='执行子目标'
                assert card.locator('.subgoal-asked').count()==1
                asked_total+=1
                text=card.locator('.subgoal-flow').inner_text()
                assert '图像坐标' not in text and '抓起方块' not in text and '放下方块' not in text
                v=card.locator('video')
                assert v.get_attribute('src').endswith(sample['url'])
                v.evaluate('(v)=>{v.muted=true;return v.play();}')
                page.wait_for_function('id=>{const v=Array.from(document.querySelectorAll("video")).find(v=>v.src.endsWith("/media/"+id));return v&&v.currentTime>.2&&!v.error;}',arg=sample['id'],timeout=15000)
                v.evaluate('(v)=>v.pause()')
                checks.append({'task':task['id'],'tier':tier['id'],'id':sample['id'],'question':expected['question'],'demo_subgoals':len(expected['demo_steps']),'execution_subgoals':len(expected['execution_steps']),'list_exact':True,'asked_badge':1,'playback':True})
        print('ATOMIC_TASK=PASS task='+task['id'],flush=True)
    page.goto('http://127.0.0.1:8060/#task=VideoPlaceButton')
    page.wait_for_function('document.getElementById("selected-id").textContent==="VideoPlaceButton"')
    page.locator('.difficulty-card[data-tier="xhard3"] .sample-button').nth(1).click()
    page.locator('.difficulty-card[data-tier="xhard3"]').screenshot(path=str(out/'button-xhard3-labels.png'))
    others=0
    for task in catalog['tasks']:
        if task['id'] in ('VideoPlaceButton','VideoPlaceOrder'):continue
        page.locator('.task-link').filter(has=page.locator('.task-id',has_text=re.compile('^'+task['id']+'$'))).click()
        assert page.locator('.subgoal-stage').count()==0
        others+=1
    mobile=b.new_page(viewport={'width':390,'height':844})
    mobile.on('pageerror',lambda e:errors.append(str(e)))
    mobile.goto('http://127.0.0.1:8060/#task=VideoPlaceButton',wait_until='domcontentloaded')
    mobile.wait_for_function('document.getElementById("selected-id").textContent==="VideoPlaceButton"')
    mobile.wait_for_timeout(800)
    overflow=mobile.evaluate('document.documentElement.scrollWidth>document.documentElement.clientWidth')
    mobile.screenshot(path=str(out/'mobile-labels.png'),full_page=False)
    b.close()
result={'checks':checks,'samples':len(checks),'lists_exact':sum(c['list_exact'] for c in checks),'asked':asked_total,'playback':sum(c['playback'] for c in checks),'errors':errors,'other_tasks_without_lists':others,'mobile_horizontal_overflow':overflow}
(out/'atomic-browser-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
verdict='PASS' if not errors and len(checks)==30 and asked_total==30 and not overflow else 'FAIL'
print(f'ATOMIC_SUBGOAL_BROWSER={verdict} samples={len(checks)} lists_exact={result["lists_exact"]} asked={asked_total} playback={result["playback"]} errors={len(errors)} other_tasks={others} mobile_overflow={overflow}')
