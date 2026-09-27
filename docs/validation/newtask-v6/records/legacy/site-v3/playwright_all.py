"""逐个真实UI视频播放、解码、拖动、继续播放；极短尾片明确失败。"""
import json
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT=Path(__file__).resolve().parent
rows=[]
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/home/hongzefu/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',args=['--disable-gpu'])
    page=browser.new_page(viewport={'width':1440,'height':1080})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8060/',wait_until='domcontentloaded')
    page.wait_for_selector('.task-link')
    catalog=page.request.get('http://127.0.0.1:8060/api/catalog').json()
    for task in catalog['tasks']:
        page.locator('.task-link').filter(has=page.locator('.task-id',has_text=re.compile('^'+re.escape(task['id'])+'$'))).click()
        for tier in task['tiers']:
            card=page.locator('.difficulty-card[data-tier="'+tier['id']+'"]')
            video=card.locator('video')
            for index,sample in enumerate(tier['videos']):
                row={'task':task['id'],'tier':tier['id'],'id':sample['id'],'label':sample['label']}
                started=time.monotonic()
                try:
                    card.locator('.sample-button').nth(index).click()
                    assert video.get_attribute('src').endswith(sample['url'])
                    video.evaluate('''v=>new Promise((resolve,reject)=>{
                      if(v.readyState>=2)return resolve();
                      const t=setTimeout(()=>reject(Error('解码超时')),15000);
                      v.addEventListener('loadeddata',()=>{clearTimeout(t);resolve()},{once:true});
                      v.addEventListener('error',()=>{clearTimeout(t);reject(Error('媒体错误'+v.error?.code))},{once:true});
                    })''')
                    row.update(video.evaluate('(v)=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,error:v.error?.code||0})'))
                    assert row['width']>0 and row['height']>0 and row['error']==0
                    if row['duration']<.5:
                        row['status']='TOO_SHORT_FOR_TRAJECTORY'
                    else:
                        start=video.evaluate('(v)=>{v.muted=true; v.currentTime=0; return v.currentTime;}')
                        video.evaluate('(v)=>v.play()')
                        page.wait_for_function('''id=>{const v=document.querySelector('video[src$="/media/'+id+'"]');return v && v.currentTime>=.25&&!v.paused&&!v.error;}''',arg=sample['id'],timeout=15000)
                        row['play_time']=video.evaluate('(v)=>v.currentTime')
                        target=min(row['duration']*.5,10)
                        video.evaluate('(v,t)=>{v.pause();v.currentTime=t;}',target)
                        page.wait_for_function('''x=>{const v=document.querySelector('video[src$="/media/'+x.id+'"]');return v&&!v.seeking&&v.readyState>=2&&Math.abs(v.currentTime-x.t)<.15;}''',arg={'id':sample['id'],'t':target},timeout=15000)
                        row['seek_time']=video.evaluate('(v)=>v.currentTime')
                        video.evaluate('(v)=>v.play()')
                        page.wait_for_function('''x=>{const v=document.querySelector('video[src$="/media/'+x.id+'"]');return v&&v.currentTime>=x.t+.2&&!v.error;}''',arg={'id':sample['id'],'t':target},timeout=15000)
                        row['resume_time']=video.evaluate('(v)=>{v.pause();return v.currentTime;}')
                        row['status']='PASS'
                except Exception as e:
                    row['status']='FAIL'
                    row['error_message']=str(e)
                row['elapsed_seconds']=round(time.monotonic()-started,3)
                rows.append(row)
                with (OUT/'playwright-all-results.json').open('w') as f:json.dump({'rows':rows,'page_errors':errors},f,ensure_ascii=False,indent=2)
        print('TASK_VIDEOS_CHECKED task='+task['id']+' total='+str(len(rows)),flush=True)
    browser.close()
counts={k:sum(r['status']==k for r in rows) for k in ('PASS','FAIL','TOO_SHORT_FOR_TRAJECTORY')}
print('ALL_VIDEO_BROWSER='+json.dumps(counts)+' page_errors='+str(len(errors)),flush=True)
raise SystemExit(1 if counts['FAIL'] or errors else 0)
