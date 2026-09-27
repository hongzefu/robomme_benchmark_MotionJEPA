"""只读现有 PatternLock 轨迹，核对节点、语言标签与少量原始画面。"""
import json
from pathlib import Path
import h5py
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
OUT=ROOT/'artifacts/audit/v6-semantic-results/pattern_lock'
PIN=ROOT/'artifacts/audit/v6-semantic-0a3f989'
delivery=json.loads((PIN/'docs/validation/newtask-v6/records/final-delivery.json').read_text())
rows=[x for x in delivery['successes'] if x['task']=='PatternLock']
paths=[Path(next(y['path'] for y in x['files'] if y['path'].endswith('.h5'))) for x in rows]
paths+=sorted((ROOT/'artifacts/newtask-v6/v6-s3-20260926-01/remaining/B').glob('PatternLock_episode_*/hdf5_files/*.h5'))
specs={}
for tier in range(1,5):
 for line in (ROOT/f'artifacts/newtask-v6/v6-01/xhard{tier}/specs.jsonl').read_text().splitlines():
  x=json.loads(line)
  if x.get('task')=='PatternLock': specs[(x['difficulty'],x['episode'])]=x['spec']['actions']['path_nodes']
directions={(1,0):'forward',(-1,0):'backward',(0,1):'left',(0,-1):'right',(1,1):'forward-left',(1,-1):'forward-right',(-1,1):'backward-left',(-1,-1):'backward-right'}
def decode(v):return v.decode() if isinstance(v,bytes) else v
results=[]
contact=[]
for path in paths:
 with h5py.File(path,'r') as h:
  ep=h[next(iter(h))]; setup=ep['setup']; difficulty=decode(setup['difficulty'][()]); episode=int(ep.name.split('_')[-1]); seed=int(setup['seed'][()]); n={'easy':3,'medium':4}.get(difficulty,5)
  nodes=np.array([[-.1+(i//n-(n-1)/2)*.1,(i%n-(n-1)/2)*.1] for i in range(n*n)])
  keys=sorted((k for k in ep if k.startswith('timestep_')),key=lambda k:int(k.split('_')[1]))
  phase={True:[],False:[]}; events={True:[],False:[]}; bounds={True:[],False:[]}; raw=[]
  for key in keys:
   step=ep[key]; i=int(key.split('_')[1]); demo=bool(step['info/is_video_demo'][()]); p=step['obs/eef_state'][()][:3]; sg=decode(step['info/simple_subgoal'][()]); completed=bool(step['info/is_completed'][()]); boundary=bool(step['info/is_subgoal_boundary'][()]); dist=np.linalg.norm(nodes-p[:2],axis=1); nearest=int(dist.argmin()); touch=nearest if dist[nearest]<=.0100001 and p[2]<.1 else None
   phase[demo].append(i)
   if touch is not None and (not events[demo] or events[demo][-1]['node']!=touch):events[demo].append({'frame':i,'node':touch,'xyz':p.tolist(),'subgoal':sg})
   if boundary:bounds[demo].append({'frame':i,'subgoal':sg,'xyz':p.tolist()})
   raw.append((i,demo,p,sg,completed,touch))
  demo_nodes=[e['node'] for e in events[True]]; exec_nodes=[e['node'] for e in events[False]]; expected=specs.get((difficulty,episode),demo_nodes)
  labels=['move '+directions[(int(np.sign(nodes[b,0]-nodes[a,0])),int(np.sign(nodes[b,1]-nodes[a,1])))] for a,b in zip(expected,expected[1:])]
  bd=[e['subgoal'] for e in bounds[True]]; be=[e['subgoal'] for e in bounds[False]]
  samples=[0,phase[True][-1],phase[False][0],len(keys)-1]
  for i in samples:
   a=ep[keys[i]]['obs/front_rgb'][()]
   image=Image.fromarray(a); tile=Image.new('RGB',(256,286),'white');tile.paste(image,(0,30));ImageDraw.Draw(tile).text((3,4),f'{difficulty}/ep{episode} f{i} demo={raw[i][1]}',fill='black');contact.append(tile)
  result={'path':str(path),'difficulty':difficulty,'episode':episode,'seed':seed,'frames':len(keys),'demo_frames':len(phase[True]),'execution_frames':len(phase[False]),'expected_nodes':expected,'demo_nodes':demo_nodes,'execution_nodes':exec_nodes,'demo_events':events[True],'execution_events':events[False],'demo_boundaries':bounds[True],'execution_boundaries':bounds[False],'expected_labels':labels,'demo_labels_match':bd==labels,'execution_labels_match':be==labels or be==labels+['All tasks completed'],'nodes_match':demo_nodes==exec_nodes==expected,'final_completed':raw[-1][4],'last_subgoal':raw[-1][3],'task_goal':[decode(v) for v in setup['task_goal'][()]]}
  results.append(result);print(difficulty,episode,'nodes',len(expected),'match',result['nodes_match'],'labels',result['demo_labels_match'],result['execution_labels_match'],'boundaries',len(bd),len(be),'frames',len(keys),flush=True)
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'existing-audit.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
for start in range(0,len(contact),28):
 chunk=contact[start:start+28];sheet=Image.new('RGB',(1024,286*((len(chunk)+3)//4)),'white')
 for j,im in enumerate(chunk):sheet.paste(im,((j%4)*256,(j//4)*286))
 sheet.save(OUT/f'contact-{start//28}.png')
print('PL_EXISTING='+('PASS' if all(r['nodes_match'] and r['demo_labels_match'] and r['execution_labels_match'] and r['final_completed'] for r in results) else 'FAIL'), 'episodes='+str(len(results)))
