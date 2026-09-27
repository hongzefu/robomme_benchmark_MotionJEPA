"""Independent re-verification of BinFill-02: recompute the native dynamic vs static vs xhard
first-appearance split directly from records.json + h5 frames, without trusting the existing
ordinal_appearance.json produced by the original audit."""
import json, h5py, numpy as np, re
ROOT = '/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill'
R = json.load(open(ROOT + '/records.json'))
CH = {'red': 0, 'green': 1, 'blue': 2}

def iscol(rgb, u, v, c, r=1):
    p = rgb[v-r:v+r+1, u-r:u+r+1].reshape(-1, 3).astype(float)
    ch = CH[c]
    o = np.max(p[:, [k for k in range(3) if k != ch]], axis=1)
    return int(((p[:, ch] > 60) & (p[:, ch] > o * 2.5)).sum()) > 0

summary = {'native_dynamic': [], 'native_static': [], 'xhard': []}
missing_grounded = []
for r in R:
    f = h5py.File(r['h5'], 'r')
    e = f[list(f.keys())[0]]
    picks = []
    texts_seen = []
    for g in r['grounded_checks']:
        if not g['expected']:
            continue
        texts_seen.append(g['text'].split(' at ')[0])
        m = re.search(r'<(\d+), (\d+)>', g['text'])
        a, b = int(m.group(1)), int(m.group(2))
        first = None
        for t in range(0, g['t'] + 1, 5):
            if iscol(e[f'timestep_{t}/obs/front_rgb'][()], b, a, g['expected']):
                first = t
                break
        picks.append((g['text'].split(' at ')[0], g['t'], first))
    row = dict(kind=r['kind'], diff=r['difficulty'], ep=r['episode'], picks=picks)
    if r['kind'] == 'new':
        summary['xhard'].append(row)
    else:
        # dynamic native episodes were pre-identified by the original audit as
        # easy/0, medium/2, medium/6, medium/10, hard/7, hard/11
        key = (r['difficulty'], r['episode'])
        if key in {('easy', 0), ('medium', 2), ('medium', 6), ('medium', 10), ('hard', 7), ('hard', 11)}:
            summary['native_dynamic'].append(row)
        else:
            summary['native_static'].append(row)

print('=== native dynamic (expect first_appear tracking pick order in 50-step steps) ===')
for row in summary['native_dynamic']:
    print(row['diff'], row['ep'], row['picks'])

print('\n=== native static (expect first_appear==0 for all, incl. 2nd/3rd) ===')
for row in summary['native_static']:
    print(row['diff'], row['ep'], row['picks'])

print('\n=== xhard (expect first_appear==0 for all, ordinals up to 7th) ===')
max_ord = 0
ORD = ['first','second','third','fourth','fifth','sixth','seventh','eighth','ninth','tenth']
for row in summary['xhard']:
    for text, t, first in row['picks']:
        for i, w in enumerate(ORD):
            if w in text:
                max_ord = max(max_ord, i + 1)
print('max ordinal index reached in xhard:', max_ord, '(', ORD[max_ord-1], ')')
all_zero = all(first == 0 for row in summary['xhard'] for (_, _, first) in row['picks'])
print('all xhard first_appear==0:', all_zero)
