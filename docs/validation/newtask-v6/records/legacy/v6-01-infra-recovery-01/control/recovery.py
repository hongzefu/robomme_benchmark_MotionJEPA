"""获批后仅恢复冻结身份；逐条落盘，基础设施或代码错误即停。"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import sys

# 与主入口generate_dataset_newseed::_worker的retryable七类一致；这里只分类，不重试同一身份。
TASK_FAILURE_TYPES = frozenset({'SceneGenerationError', 'FailsafeTimeout', 'PlannerExhausted',
                                'ScrewPlanFailure', 'DatasetGenerationError', 'BinCollisionError',
                                'SpecBindingError'})


def read(path):
    return json.loads(Path(path).read_text())


def approval(manifest_path, approval_path):
    manifest_path = Path(manifest_path)
    manifest = read(manifest_path)
    decision = read(approval_path)
    assert decision['approved'] is True, '未明确批准'
    assert decision['run_name'] == manifest['run_name']
    assert decision['manifest_sha256'] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert decision['max_attempts'] == manifest['max_attempts'] == 76
    assert isinstance(decision['user_instruction'], str) and decision['user_instruction'].strip()
    return manifest


def verify_manifest(manifest):
    assert manifest['schema'] == 'v6-infra-recovery/1'
    assert manifest['run_name'] == 'v6-01-infra-recovery-01'
    assert manifest['max_attempts'] == len(manifest['eligible']) == 76
    eligible = {(r['task'], r['episode']): r for r in manifest['eligible']}
    assert len(eligible) == 76
    assert not set(eligible) & {(r['task'], r['episode']) for r in manifest['excluded']}
    assert sum(r['reason'] == 'existing_success' for r in manifest['excluded']) == 26
    assert sum(r['reason'] == 'true_task_failure' for r in manifest['excluded']) == 2
    assert manifest['first'] == {'task': 'StopCube', 'episode': 3}
    assert manifest['order'] == [0, 3, 6, 1, 2, 4, 5, 7, 8, 9]
    assert set(manifest['limits']) == {r['task'] for r in manifest['eligible']}
    for task, limit in manifest['limits'].items():
        assert limit['recovery_limit'] == sum(r['task'] == task for r in manifest['eligible'])
        assert limit['prior_attempts'] == 9
        assert limit['cumulative_limit'] == limit['prior_attempts'] + limit['recovery_limit']
        assert limit['cumulative_limit'] == (16 if task == 'InsertPeg' else 18 if task == 'StopCube' else 19)
    return eligible


def recover(manifest, output, batch_runner):
    """首轮一条；随后每格每轮至多一条，最多八并行。异常后不派下一轮。"""
    eligible = verify_manifest(manifest)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    successes = {task: limit['existing_success'] for task, limit in manifest['limits'].items()}
    attempted = collections.Counter()
    seen = set()
    first = ('StopCube', 3)
    stop = None
    round_index = 0
    with (output / 'attempts.jsonl').open('x') as events, (output / 'results.jsonl').open('x') as results:
        def append(stream, row):
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

        while True:
            keys = [first] if round_index == 0 else []
            if round_index:
                for task in manifest['limits']:
                    if successes[task] >= 3:
                        continue
                    for episode in manifest['order']:
                        key = task, episode
                        if key in eligible and key not in seen:
                            keys.append(key)
                            break
            if not keys:
                break
            assert len(keys) <= 8 and len({task for task, _ in keys}) == len(keys)
            batch = [eligible[key] for key in keys]
            for key, row in zip(keys, batch):
                task, episode = key
                assert key not in seen and len(seen) < 76
                assert attempted[task] < manifest['limits'][task]['recovery_limit']
                seen.add(key)
                attempted[task] += 1
                append(events, {'event': 'start', 'round': round_index, **row})
            try:
                returned = batch_runner(batch, round_index, output)
                assert len(returned) == len(keys)
                result_map = {(r['task'], r['episode']): r for r in returned}
                assert set(result_map) == set(keys)
                for key, row in zip(keys, batch):
                    result = result_map[key]
                    assert result['seed'] == row['seed'] and result['spec_sha256'] == row['spec_sha256']
                    assert type(result['ok']) is bool
            except BaseException as error:
                for row in batch:
                    append(events, {'event': 'unresolved_stop', 'round': round_index, **row,
                                    'error_type': type(error).__name__, 'error': str(error)})
                stop = 'runner_or_code_error'
                break
            for key, row in zip(keys, batch):
                task, episode = key
                result = result_map[key]
                if result['ok']:
                    category = 'success'
                    successes[task] += 1
                elif result['error_type'] in TASK_FAILURE_TYPES:
                    category = 'true_task_failure'
                else:
                    category = 'infrastructure_or_code_error'
                append(results, {**result, 'recovery_category': category,
                                 'execution_role': 'infra_recovery', 'recovery_reason': row['category']})
                append(events, {'event': 'finish', 'round': round_index, **row, 'category': category})
                print(f'RECOVERY_RESULT task={task} episode={episode} category={category} attempted={len(seen)}', flush=True)
                if category == 'infrastructure_or_code_error' or (key == first and not result['ok']):
                    stop = category if key != first else 'first_probe_failed'
            if stop:
                break
            round_index += 1
        summary = {'run_name': manifest['run_name'], 'attempted': len(seen), 'max_attempts': 76,
                   'stop_reason': stop, 'success_with_original': successes,
                   'per_task_attempts': dict(attempted),
                   'shortfall': {task: max(0, 3 - count) for task, count in successes.items()}}
        with (output / 'summary.json').open('x') as stream:
            json.dump(summary, stream, ensure_ascii=False, indent=2)
    print('RECOVERY_STOP' if stop else 'RECOVERY_DONE', json.dumps(summary, ensure_ascii=False), flush=True)
    return 1 if stop else 0


def batch_specs(rows, specs):
    """角色取冻结selected字段，执行恢复的身份另记于结果，不覆盖业务角色。"""
    return [dict(specs[(row['task'], row['episode'])],
                 _role='selected' if specs[(row['task'], row['episode'])]['selected'] else 'backfill')
            for row in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    manifest = read(args.manifest)
    verify_manifest(manifest)
    if args.check:
        print('RECOVERY_PREPARE=PASS eligible=76 launch=NOT_RUN approval=NOT_CONSUMED')
        return 0
    assert args.approval is not None
    manifest = approval(args.manifest, args.approval)
    repo = Path('/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl')
    assert Path.cwd().resolve() == repo
    assert os.uname().nodename.split('.')[0] == 'gl1517'
    specs_path = Path(manifest['source_specs'])
    assert hashlib.sha256(specs_path.read_bytes()).hexdigest() == manifest['source_specs_sha256']
    sys.path.insert(0, str(repo))
    from scripts.parity import v4_rollout as rollout
    header, specs = rollout._load_all(specs_path)
    assert header['identity_sha256'] == manifest['source_identity_sha256']
    for row in manifest['eligible']:
        saved = specs[(row['task'], row['episode'])]
        assert all(saved[k] == row[k] for k in ('seed', 'attempt', 'spec_sha256'))
    command_args = argparse.Namespace(label='infra-recovery-01', workers=1, gpu='0',
        official_root='artifacts/train-parity/local-smoke-01/official-src')
    def execute(rows, index, out):
        batch = batch_specs(rows, specs)
        command_args.workers = min(16, len(batch))
        return rollout._run_batch(batch, header, out, command_args, index)
    return recover(manifest, Path(manifest['output']) / 'rollout/run1', execute)


if __name__ == '__main__':
    raise SystemExit(main())
