"""从固定144条原始结果重算指标，兼容旧 Counter 报告省略零字段。"""
import json
from pathlib import Path
import sys

KEYS = ('expected', 'attempted', 'success', 'failed', 'timeout', 'missing',
        'invalid_summary', 'successful_media_fail')


def read(path):
    return json.loads(path.read_text())


def compare_metrics(saved, actual):
    """只允许经逐条重算证实为零的字段缺席，绝不默认补零后放行。"""
    assert not (set(saved) - set(KEYS)), ('未知汇总字段', set(saved) - set(KEYS))
    for key in KEYS:
        if key in saved:
            assert saved[key] == actual[key], (key, saved[key], actual[key])
        else:
            assert actual[key] == 0, ('非零指标缺失', key, actual[key])


def check(repo):
    root = repo / 'artifacts/newtask-v6/v6-s2-20260926-01'
    exits = [line for line in (root / 'run.log').read_text().splitlines() if line.startswith('EXIT_CODE=')]
    assert exits == ['EXIT_CODE=0'], exits
    manifest = read(root / 'manifest.json')
    identities = manifest['identities']
    ids = {row['id'] for row in identities}
    assert len(ids) == len(identities) == manifest['attempt_budget'] == 144
    assert manifest['retries'] == 0
    assert {p.name for p in (root / 'episodes').iterdir() if p.is_dir()} == ids
    report = read(root / 'report.json')
    assert (root / 'report.md').is_file()
    assert report['attempt_coverage_complete'] is True and report['unexpected_episode_dirs'] == []
    assert len(report['identities']) == 144
    reported = {row['id']: row for row in report['identities']}
    assert set(reported) == ids
    batches = list(root.glob('summary-*.json'))
    assert len(batches) == 1
    batch = read(batches[0])
    assert batch['identities'] == batch['counted_attempts'] == len(batch['results']) == 144
    assert batch['unresolved'] == batch['not_started'] == 0
    batched = {row['id']: row for row in batch['results']}
    assert set(batched) == ids
    totals = dict.fromkeys(KEYS, 0)
    cells = {}
    for identity in identities:
        episode = root / 'episodes' / identity['id']
        started, result = read(episode / 'started.json'), read(episode / 'result.json')
        row = reported[identity['id']]
        for source in (started, result, row):
            assert all(source[k] == identity[k] for k in ('id', 'task', 'difficulty', 'episode', 'seed'))
        assert result == row['result'] == batched[identity['id']]
        assert result['counted_attempt'] is True
        summaries = [json.loads(line) for line in (episode / 'summary.jsonl').read_text().splitlines() if line]
        valid = len(summaries) == 1 and all(summaries[0][k] == identity[k] for k in ('task', 'difficulty', 'seed'))
        success = bool(valid and result['ok'] and summaries[0]['ok'])
        assert row['started'] is True and row['result_present'] is True
        assert row['identity_summary_valid'] == valid and row['success'] == success
        assert row['timeout'] == result['timeout']
        h5s, videos = row['hdf5'], row['videos']
        # 汇总报告是既有真实媒体检查结果；同时核查当前文件仍在且大小未变。
        for media in h5s + videos:
            path = repo / media['path']
            assert path.is_file() and path.stat().st_size == media['bytes'], str(path)
        assert {str(p.relative_to(repo)) for p in episode.rglob('*.h5')} == {m['path'] for m in h5s}
        assert {str(p.relative_to(repo)) for p in episode.rglob('*.mp4')} == {m['path'] for m in videos}
        media_ok = len(h5s) == 1 and all(m['ok'] is True for m in h5s) and bool(videos) and all(m['first_frame_decodable'] is True for m in videos)
        assert row['success_media_ok'] == media_ok
        values = dict(expected=1, attempted=1, success=int(success), failed=int(not success),
                      timeout=int(result['timeout']), missing=0, invalid_summary=int(not valid),
                      successful_media_fail=int(success and not media_ok))
        cell = cells.setdefault((identity['task'], identity['difficulty']), dict.fromkeys(KEYS, 0))
        for key in KEYS:
            totals[key] += values[key]
            cell[key] += values[key]
    assert read(root / 'episodes' / identities[0]['id'] / 'result.json')['ok'] is True
    compare_metrics(report['totals'], totals)
    assert len(report['cells']) == len(cells)
    assert {(c['task'], c['difficulty']) for c in report['cells']} == set(cells)
    for cell in report['cells']:
        compare_metrics({k: v for k, v in cell.items() if k not in ('task', 'difficulty')}, cells[(cell['task'], cell['difficulty'])])
    assert batch['successes'] == totals['success'] and batch['failures'] == totals['failed']
    assert totals['attempted'] == 144 and totals['missing'] == 0
    assert totals['success'] > 0 and totals['successful_media_fail'] == 0
    print('S2_CONTINUE_GATE=PASS ' + ' '.join(f'{k}={v}' for k, v in totals.items()), flush=True)
    return totals


if __name__ == '__main__':
    check(Path(sys.argv[1]).resolve())
