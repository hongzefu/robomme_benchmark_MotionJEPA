"""只读：VPB/VPO 演示段每次搬运时空中方块颜色（中点帧、高度>0.06m 的R/G/B像素多数色）。"""
import sys,json,h5py,numpy as np,cv2,re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
E=sys.argv[1]; sys.path.insert(0,E); from geom import world
from counts import hue_name
# 腕部相机：放置子目标起始帧，夹爪间区域多数色
W={'first':1,'second':2,'third':3,'fourth':4,'fifth':5,'sixth':6}
def run(x):
    b=[bb for bb in x['boundaries'] if bb['demo']]
    ev=[]
    with h5py.File(x['h5']) as f:
        g=f[list(f.keys())[0]]
        for i,bb in enumerate(b):
            if bb['s']!='pick up the cube': continue
            nxt=b[i+1]
            t=nxt['t']
            rgb=g[f'timestep_{t}']['obs']['wrist_rgb'][()]; hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
            sub=hsv[140:256,80:176]
            m=sub[...,1]>150
            names=[hue_name(*p) for p in sub[m]]
            c=Counter(n for n in names if n in('red','green','blue'))
            ev.append(dict(t_pick=bb['t'],t_mid=t,dest=nxt['s'],color=c.most_common(1)[0][0] if c else None,votes=dict(c)))
            # 按钮位置
    btn=[bb['t'] for bb in b if bb['s']=='press the button'][0]
    goal=x['setup']['task_goal'][0]
    gc=re.search(r'place the (red|green|blue) cube',goal).group(1)
    res=dict(task=x['task'],tier=x['setup']['difficulty'],ep=x['episode'],goal=goal,goal_color=gc,button_t=btn,events=ev)
    places=[e for e in ev if e['dest']=='drop the cube onto target']
    res['places_by_color']=dict(Counter(e['color'] for e in places))
    if x['task']=='VideoPlaceOrder':
        k=W[re.search(r'on the (\w+) target',goal).group(1)]
        res['goal_ordinal']=k; res['goal_color_places']=sum(e['color']==gc for e in places); res['ordinal_ok']=k<=res['goal_color_places']
    else:
        before=[e for e in places if e['t_pick']<btn and e['color']==gc]; after=[e for e in places if e['t_pick']>btn and e['color']==gc]
        res['goal_color_before']=len(before); res['goal_color_after']=len(after)
        res['which']='after' if 'after the button' in goal else 'before'
    return res
if __name__=='__main__':
    r=json.load(open(E+'/scan_raw.json'))
    xs=[x for x in r if x['task'] in ('VideoPlaceButton','VideoPlaceOrder')]
    with ProcessPoolExecutor(16) as ex: out=list(ex.map(run,xs))
    json.dump(out,open(E+'/vp_identity.json','w'),indent=1)
    order=['easy','medium','hard','xhard1','xhard2','xhard3','xhard4']
    for o in sorted(out,key=lambda o:(o['task'],order.index(o['tier']),o['ep'])):
        seq=' '.join(f"{e['color']}->{'T' if 'target' in e['dest'] else ('O' if 'original' in e['dest'] else 'table')}" for e in o['events'])
        extra=f"ord={o.get('goal_ordinal')} gcp={o.get('goal_color_places')} ok={o.get('ordinal_ok')}" if o['task']=='VideoPlaceOrder' else f"{o['which']} before={o['goal_color_before']} after={o['goal_color_after']}"
        print(o['task'][5:],o['tier'],o['ep'],'goal',o['goal_color'],'btn',o['button_t'],'|',seq,'|',extra)
