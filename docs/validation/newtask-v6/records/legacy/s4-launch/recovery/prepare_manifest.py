"""仅从冻结规格和已有事故记录制作恢复清单，不导入仿真。"""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = [json.loads(line) for line in (HERE / 'frozen-specs.jsonl').read_text().splitlines()]
header, specs = rows[0], rows[1:]
results, scheduled = [], set()
for directory in sorted((HERE.parent / 'incident/xhard4-rounds').iterdir()):
    jobs = json.loads((directory / 'jobs.json').read_text())
    scheduled.update((row['task'], row['episode']) for row in jobs)
    if (directory / 'results.json').exists():
        results.extend(json.loads((directory / 'results.json').read_text())['results'])
known = {(row['task'], row['episode']): row for row in results}
assert len(known) == len(results) == 88
success = collections.Counter(row['task'] for row in results if row['ok'])
tasks = [task for task in header['tasks'] if success[task] < 3]
assert len(tasks) == 8
eligible, excluded = [], []
for row in specs:
    key = row['task'], row['episode']
    result = known.get(key)
    if result is not None and result['ok']:
        excluded.append({'task': key[0], 'episode': key[1], 'reason': 'existing_success'})
    elif result is not None and result['error_type'] == 'DatasetGenerationError':
        excluded.append({'task': key[0], 'episode': key[1], 'reason': 'true_task_failure'})
    elif row['task'] in tasks:
        if result is not None:
            assert result['error_type'] == 'RuntimeError' and 'ErrorInitializationFailed' in result['error']
            category = 'vulkan_initialization_failure'
        else:
            category = 'cancelled_unknown' if key in scheduled else 'never_scheduled'
        eligible.append({key: row[key] for key in ('task', 'episode', 'seed', 'attempt', 'spec_sha256')} | {'category': category})
assert len(eligible) == 76 and len(excluded) == 28
limits = {task: {'existing_success': success[task], 'prior_attempts': sum(t == task for t, _ in scheduled),
                  'recovery_limit': sum(r['task'] == task for r in eligible)} for task in tasks}
for task, limit in limits.items():
    limit['cumulative_limit'] = limit['prior_attempts'] + limit['recovery_limit']
    assert limit['cumulative_limit'] == (16 if task == 'InsertPeg' else 18 if task == 'StopCube' else 19)
manifest = {'schema': 'v6-infra-recovery/1', 'run_name': 'v6-01-infra-recovery-01',
            'output': '/tmp/v6-s4-v6-01-infra-recovery-01', 'source_specs': '/tmp/v6-s4-v6-01/xhard4/specs.jsonl',
            'source_specs_sha256': hashlib.sha256((HERE / 'frozen-specs.jsonl').read_bytes()).hexdigest(),
            'source_identity_sha256': header['identity_sha256'], 'max_attempts': 76,
            'first': {'task': 'StopCube', 'episode': 3}, 'order': [0, 3, 6, 1, 2, 4, 5, 7, 8, 9],
            'limits': limits, 'eligible': eligible, 'excluded': excluded}
with (HERE / 'manifest.json').open('x') as stream:
    json.dump(manifest, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print('RECOVERY_MANIFEST=PASS eligible=76 excluded_success=26 excluded_task_failure=2 reset_extra=0')
