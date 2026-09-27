"""低开销只读采样：30秒，线程/proc每秒，GPU每5秒；不接触进程控制。"""
from collections import Counter
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

OUT=Path(__file__).resolve().parent
PID=1843953
PROC=Path(f'/proc/{PID}')
RUN=OUT.parents[1]/'v6-s3-20260926-01/remaining'


def parse_stat(path):
    f=path.read_text().rsplit(')',1)[1].split()
    return {'state':f[0],'ppid':int(f[1]),'pgrp':int(f[2]),'utime_ticks':int(f[11]),
            'stime_ticks':int(f[12]),'starttime':int(f[19]),'processor':int(f[36])}


def threads():
    rows=[]
    for path in sorted((PROC/'task').iterdir(),key=lambda p:int(p.name)):
        try:
            row=parse_stat(path/'stat')
            row.update(tid=int(path.name),wchan=(path/'wchan').read_text().strip(),
                       schedstat=list(map(int,(path/'schedstat').read_text().split())))
            rows.append(row)
        except FileNotFoundError:
            pass
    return rows


def file_metadata():
    directories=sorted((RUN/'B').iterdir(),key=lambda p:p.stat().st_mtime,reverse=True)[:3]
    rows=[]
    for directory in directories:
        files=[]
        for sub in ('hdf5_files','videos'):
            location=directory/sub
            if location.is_dir():
                for f in location.iterdir():
                    if f.is_file():
                        s=f.stat()
                        files.append({'path':str(f),'bytes':s.st_size,'mtime':s.st_mtime})
        rows.append({'identity':directory.name,'files':files})
    return rows


def cgroup():
    rel=(PROC/'cgroup').read_text().strip().split('::',1)[1]
    root=Path('/sys/fs/cgroup')/rel.lstrip('/')
    return {'path':str(root),'cpu.max':(root/'cpu.max').read_text(),
            'cpu.stat':(root/'cpu.stat').read_text(),'cpu.pressure':(root/'cpu.pressure').read_text()}


def main():
    for filename in ('before.json','samples.jsonl','after.json','summary.json'):
        assert not (OUT/filename).exists(), f'已有证据，禁止覆盖：{filename}'
    started=time.monotonic()
    identity=parse_stat(PROC/'stat')
    before={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'pid':PID,'identity':identity,'clock_ticks':os.sysconf('SC_CLK_TCK'),
            'duration_s':30,'proc_interval_s':1,'gpu_interval_s':5,
            'files':file_metadata(),'cgroup':cgroup()}
    (OUT/'before.json').write_text(json.dumps(before,ensure_ascii=False,indent=2))
    samples=[]
    with (OUT/'samples.jsonl').open('x') as stream:
        for index in range(31):
            delay=started+index-time.monotonic()
            if delay>0:
                time.sleep(delay)
            assert parse_stat(PROC/'stat')['starttime']==identity['starttime']
            row={'elapsed_s':time.monotonic()-started,'threads':threads()}
            if index%5==0:
                result=subprocess.run(['nvidia-smi','--query-gpu=index,pstate,clocks.sm,clocks.mem,utilization.gpu,utilization.memory,power.draw,power.limit,temperature.gpu,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True)
                row['gpu']={'exit_code':result.returncode,'rows':result.stdout.strip().splitlines()}
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
            stream.flush()
            samples.append(row)
    end={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':file_metadata(),'cgroup':cgroup()}
    (OUT/'after.json').write_text(json.dumps(end,ensure_ascii=False,indent=2))
    first={row['tid']:row for row in samples[0]['threads']}
    last={row['tid']:row for row in samples[-1]['threads']}
    counts={}
    for tid in sorted(first.keys()|last.keys()):
        observed=[row for sample in samples for row in sample['threads'] if row['tid']==tid]
        item={'samples':len(observed),'state_counts':dict(Counter(row['state'] for row in observed)),
              'wchan_counts':dict(Counter(row['wchan'] for row in observed))}
        if tid in first and tid in last:
            item['cpu_s']=(last[tid]['schedstat'][0]-first[tid]['schedstat'][0])/1e9
            item['runnable_wait_s']=(last[tid]['schedstat'][1]-first[tid]['schedstat'][1])/1e9
        counts[str(tid)]=item
    summary={'wall_s':samples[-1]['elapsed_s']-samples[0]['elapsed_s'],
             'samples':len(samples),'threads':counts,
             'limitation':'离散等待点采样不是连续调用栈；不能识别锁持有者，也不能证明整轮慢因。'}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print('RUNTIME_SAMPLE=PASS proc_samples=31 duration_s=30 gpu_interval_s=5 simulation_attempts=0')


if __name__=='__main__':
    main()
