import json
from pathlib import Path
import h5py

base = Path('artifacts/newtask-v6/v1/base/B')
dirs = sorted(base.glob('VideoPlaceButton_episode_*'))
rows = []
for d in dirs:
    files = list((d / 'hdf5_files').glob('*.h5'))
    assert len(files) == 1, files
    with h5py.File(files[0], 'r') as f:
        ep = f[next(iter(f))]
        n = sum(k.startswith('timestep_') for k in ep)
        texts = []
        prev = None
        for i in range(n):
            gs = ep[f'timestep_{i}']['info/grounded_subgoal'][()]
            gs = gs.decode() if isinstance(gs, bytes) else str(gs)
            if gs != prev:
                texts.append(gs)
                prev = gs
        rows.append({'dir': d.name, 'h5': str(files[0]), 'segments': texts})
Path(__file__).parent.joinpath('scan_native_result.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
final_drop_texts = [r['segments'][-1] if 'drop' in r['segments'][-1] else None for r in rows]
print('N_DIRS=', len(rows))
for r in rows:
    print(r['dir'], '->', r['segments'])
