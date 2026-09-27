"""只读扫描 VideoPlaceButton xhard1-4 全部12个交付H5，统计 grounded_subgoal 文本
中 'put the cube back to its original position' 段是否带坐标 <r,c>，
并与同文件里其它 'drop onto' 类型段对照。"""
import json
from pathlib import Path
import h5py

idx = json.loads(Path('artifacts/audit/v6-semantic-vs-native-82e3d92/new-tier-index.json').read_text())
rows = []
for e in idx['VideoPlaceButton']:
    h5path = Path(e['h5'])
    with h5py.File(h5path, 'r') as f:
        ep_key = next(iter(f))
        ep = f[ep_key]
        n = sum(k.startswith('timestep_') for k in ep)
        texts = []
        for i in range(n):
            t = ep[f'timestep_{i}']
            gs = t['info/grounded_subgoal'][()]
            gs = gs.decode() if isinstance(gs, bytes) else str(gs)
            boundary = bool(t['info/is_subgoal_boundary'][()]) if 'info/is_subgoal_boundary' in t else None
            texts.append((i, gs, boundary))
        # 去重成段（按文本变化）
        segs = []
        prev = None
        for i, gs, b in texts:
            if gs != prev:
                segs.append({'start': i, 'text': gs})
                prev = gs
        rows.append({'difficulty': e['difficulty'], 'episode': e['episode'], 'h5': str(h5path),
                      'n_steps': n, 'segments': segs})

out = Path(__file__).parent / 'scan_result.json'
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2))

# 汇总：home-return 段文本分布
home_texts = []
other_place_texts = []
for r in rows:
    for s in r['segments']:
        if 'original position' in s['text']:
            home_texts.append(s['text'])
        if 'drop onto target' in s['text'] or 'drop the cube' in s['text']:
            other_place_texts.append(s['text'])

from collections import Counter
print('HOME_TEXT_COUNTER=', Counter(home_texts))
print('OTHER_PLACE_COUNTER_SAMPLE=', Counter(other_place_texts).most_common(10))
print('N_EPISODES=', len(rows))
print('TOTAL_HOME_SEGMENTS=', len(home_texts))
