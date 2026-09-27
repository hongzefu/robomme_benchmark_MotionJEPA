"""获用户批准，仅暂停两条指定watch30秒并自动恢复；不触碰S3。"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

OUT=Path(__file__).resolve().parent
WATCHES={1275035:['watch','-n','-0.1','nvidia-smi'],1488784:['watch','-n','0.1','nvidia-smi']}
WORKER=1843953
def state(pid):
    p=Path(f'/proc/{pid}')
    raw=(p/'stat').read_text().split(') ',1)[1].split()
    return {'pid':pid,'state':raw[0],'starttime':raw[19], 'cpu_ticks':int(raw[11])+int(raw[12]), 'wchan':(p/'wchan').read_text().strip()}
bound={}
for pid,argv in WATCHES.items():
    actual=Path(f'/proc/{pid}/cmdline').read_bytes().decode().strip('\0').split('\0')
    assert actual==argv,(pid,actual)
    bound[pid]=state(pid)['starttime']
worker_start=state(WORKER)['starttime']
def resume():
    for pid,start in bound.items():
        try:
            if state(pid)['starttime']==start:os.kill(pid,signal.SIGCONT)
        except ProcessLookupError:pass
def interrupted(signum,frame):
    raise RuntimeError(f'测试收到信号{signum}')
for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupted)
rows=[]
def sample(phase,seconds):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        s=state(WORKER)
        assert s['starttime']==worker_start
        rows.append({'time':time.time(),'phase':phase,**s})
        time.sleep(min(.5,max(0,until-time.monotonic())))
with (OUT/'pause-binding.json').open('x') as f:json.dump({'watches':bound,'worker':WORKER,'worker_start':worker_start,'approval':'允许暂停30秒并自动恢复'},f,ensure_ascii=False,indent=2)
sample('before',5)
# 独立恢复保险只持有这两个已经绑定的PID，最迟35秒检查并恢复。
guard_code='''import os,signal,time,json,sys
time.sleep(35)
for pid,start in json.loads(sys.argv[1]).items():
 try:
  current=open('/proc/'+pid+'/stat').read().split(') ',1)[1].split()[19]
  if current==start:os.kill(int(pid),signal.SIGCONT)
 except (FileNotFoundError,ProcessLookupError):pass
'''
guard=subprocess.Popen([sys.executable,'-c',guard_code,json.dumps(bound)],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
paused_at=time.time()
try:
    for pid,start in bound.items():
        assert state(pid)['starttime']==start
        os.kill(pid,signal.SIGSTOP)
    print('WATCH_PAUSED targets=1275035,1488784 seconds=30',flush=True)
    sample('paused',30)
finally:
    resume()
    resumed_at=time.time()
    print('WATCH_RESUMED targets=1275035,1488784',flush=True)
sample('after',8)
guard.wait(timeout=5)
summary={}
for phase in ('before','paused','after'):
    selected=[r for r in rows if r['phase']==phase]
    summary[phase]={'samples':len(selected),'driver_lock_samples':sum('rwlock' in r['wchan'] for r in selected),'running_samples':sum(r['state']=='R' for r in selected),'cpu_seconds':(selected[-1]['cpu_ticks']-selected[0]['cpu_ticks'])/os.sysconf('SC_CLK_TCK'),'wall_seconds':selected[-1]['time']-selected[0]['time']}
result={'paused_seconds':resumed_at-paused_at,'summary':summary,'samples':rows,'restored':{str(pid):state(pid) for pid in bound}}
with (OUT/'pause-result.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(summary,ensure_ascii=False),flush=True)
assert all(r['state']!='T' for r in result['restored'].values())
print('WATCH_RESTORE=PASS targets=2',flush=True)
