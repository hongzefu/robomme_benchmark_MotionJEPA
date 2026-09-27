"""S3 固定 144 身份：先一条冒烟，再剩余 143 条，失败不补跑。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import selectors
import signal
import time

ROOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask')
OUT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'scripts/configs/newtask-v3/subset_manifest.json'
BASE = ROOT / 'artifacts/newtask-v6/v1/base'
OFFICIAL = ROOT / 'artifacts/train-parity/local-smoke-01/official-src'
ENTRY = ROOT / 'scripts/parity/train_split_parity.py'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def key(row):
    return tuple(row.get(name) for name in ('task', 'episode', 'seed', 'difficulty', 'recovery_mode'))


def validate_h5(run_dir, rows, label):
    """先核验成功轨迹与身份，再允许字节比较；相同空文件不能过关。"""
    import h5py
    expected = {f"{r['task']}_episode_{r['episode']}": r for r in rows}
    assert len(expected) == len(rows), '身份重复'
    actual = {p.name for p in (run_dir / 'B').iterdir() if p.is_dir()}
    assert actual == set(expected), f'{label} 身份目录不完整或有额外身份'
    total_steps = 0
    for identity, row in expected.items():
        files = list((run_dir / 'B' / identity / 'hdf5_files').glob('*.h5'))
        assert len(files) == 1, f'{label}/{identity} HDF5缺失或不唯一'
        path = files[0]
        assert path.name == f"{row['task']}_ep{row['episode']}_seed{row['seed']}.h5"
        with h5py.File(path, 'r') as handle:
            ep_name = f"episode_{row['episode']}"
            assert list(handle) == [ep_name], f'{path} episode身份错误'
            episode = handle[ep_name]
            assert int(episode['setup/seed'][()]) == row['seed']
            difficulty = episode['setup/difficulty'][()]
            if isinstance(difficulty, bytes):
                difficulty = difficulty.decode()
            assert difficulty == row['difficulty'], f'{path} 难度身份错误'
            indices = sorted(int(name.removeprefix('timestep_')) for name in episode if name.startswith('timestep_'))
            assert indices and indices == list(range(len(indices))), f'{path} 时间步为空或不连续'
            terminal = episode[f'timestep_{indices[-1]}/info/is_completed']
            assert terminal.shape == () and terminal.dtype.kind == 'b' and bool(terminal[()]), f'{path} 终端未严格完成'
            total_steps += len(indices)
    result = {'label': label, 'identities': len(rows), 'valid_h5': len(rows),
              'terminal_success': len(rows), 'timestep_count': total_steps}
    print(f"S3_H5_SEMANTICS=PASS side={label} identities={len(rows)} terminal_success={len(rows)} timesteps={total_steps}", flush=True)
    return result


def command(args, log, progress_root=None, idle_seconds=1800, hard_seconds=14400):
    """独立进程组；30分钟无日志/文件进展或4小时硬上限即停止，不重试。"""
    def stop_group(proc):
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            proc.poll()
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()

    def interrupted(signum, _frame):
        raise RuntimeError(f'收到信号 {signum}，停止本命令进程组')

    with log.open('x') as stream:
        proc = subprocess.Popen(args, cwd=ROOT, env=os.environ.copy(), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=True)
        previous = {s: signal.signal(s, interrupted) for s in (signal.SIGTERM, signal.SIGINT)}
        started = last_progress = last_scan = time.monotonic()
        fingerprint = None
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map() or proc.poll() is None:
                for entry, _ in selector.select(timeout=0.1):
                    chunk = os.read(entry.fd, 65536)
                    if not chunk:
                        selector.unregister(entry.fileobj)
                        continue
                    text = chunk.decode('utf-8', errors='replace')
                    print(text, end='', flush=True)
                    stream.write(text)
                    stream.flush()
                    last_progress = time.monotonic()
                now = time.monotonic()
                if progress_root is not None and now - last_scan >= 5:
                    # 持续写盘只算进展，不把文件存在或增长误记为成功身份。
                    states = []
                    if progress_root.exists():
                        for path in progress_root.rglob('*'):
                            try:
                                if path.is_file():
                                    stat = path.stat()
                                    states.append((str(path), stat.st_size, stat.st_mtime_ns))
                            except FileNotFoundError:
                                continue
                    current = tuple(sorted(states))
                    if current and current != fingerprint:
                        last_progress = now
                    fingerprint = current
                    last_scan = now
                if now - started > hard_seconds or now - last_progress > idle_seconds:
                    raise TimeoutError(f'监督超时：elapsed={now-started:.1f}s idle={now-last_progress:.1f}s；停止且不重试')
            code = proc.wait()
            stream.write(f'EXIT_CODE={code}\n')
        except BaseException as error:
            stream.write(f'SUPERVISION=STOP reason={error}\nEXIT_CODE=124\n')
            stream.flush()
            raise
        finally:
            selector.close()
            proc.stdout.close()
            stop_group(proc)
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    if code:
        raise RuntimeError(f'命令失败，停止且不重试：{log}，退出码 {code}')


def prepare():
    original = read(MANIFEST)
    assert len(original['rows']) == 144
    # 按既有基线 worker 的顺序取 BinFill/0，避免增加任何身份。
    first = [row for row in original['rows'] if row['task'] == 'BinFill' and row['episode'] == 0]
    assert len(first) == 1
    rest = [row for row in original['rows'] if key(row) != key(first[0])]
    for name, rows in [('smoke', first), ('remaining', rest)]:
        # 派生清单明确使用自己的元数据，不冒充原完整冻结清单。
        value = {'schema': 'train-parity-manifest/1', 'kind': 'v6-s3-fixed-subset',
                 'source_manifest': str(MANIFEST),
                 'source_manifest_sha256': hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
                 'source_ref': original['source_ref'], 'rows_total': len(rows), 'rows': rows}
        write(OUT / f'{name}_manifest.json', value)
    print('S3_PREPARE=PASS smoke=1 remaining=143 total=144')


def run():
    full = read(MANIFEST)['rows']
    baseline = read(BASE / 'run_config.json')
    for filename, field in [('uv.lock', 'uv_lock_sha256'), ('pyproject.toml', 'pyproject_sha256')]:
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == baseline['environment'][field]
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == baseline['manifest_sha256']
    assert (OFFICIAL / '.official_tree').read_text().strip() == baseline['official_tree']
    parts = [read(OUT / f'{name}_manifest.json')['rows'] for name in ('smoke', 'remaining')]
    assert len(parts[0]) == 1 and len(parts[1]) == 143
    assert sorted(map(key, parts[0] + parts[1])) == sorted(map(key, full))
    write(OUT / 'launch.json', {'schema': 'v6-s3-launch/1', 'cwd': str(ROOT),
          'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
          'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'baseline_config': str(BASE / 'run_config.json'), 'attempt_limit': 144})
    os.environ.update(CUDA_VISIBLE_DEVICES='0', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONUNBUFFERED='1')
    os.environ.setdefault('UV_CACHE_DIR', str(ROOT / 'artifacts/cache/uv'))
    all_results = []
    for name, expected in zip(('smoke', 'remaining'), parts):
        destination = OUT / name
        assert not destination.exists(), f'禁止覆盖或重跑：{destination}'
        command(['uv', 'run', '--no-sync', 'python', str(ENTRY), 'run',
                 '--manifest', str(OUT / f'{name}_manifest.json'), '--paths', 'B',
                 '--workers', '1', '--gpus', '0', '--official-root', str(OFFICIAL),
                 '--output', str(destination)], OUT / f'{name}.log', progress_root=destination)
        results = read(destination / 'results/B.json')['results']
        assert sorted(map(key, results)) == sorted(map(key, expected))
        assert all(row['ok'] and row.get('attempt_count') == 1 for row in results)
        assert all(Path(row['raw_h5_path']).is_file() for row in results)
        validate_h5(destination, expected, name)
        all_results.extend(results)
        print(f'S3_PART=PASS part={name} count={len(results)}', flush=True)
    # 只建立指向本轮实际输出的只读比较视图，原始配置、路径和结果不搬动。
    combined = OUT / 'combined'
    (combined / 'B').mkdir(parents=True)
    (combined / 'results').mkdir()
    for name in ('smoke', 'remaining'):
        for identity in (OUT / name / 'B').iterdir():
            if identity.is_dir():
                (combined / 'B' / identity.name).symlink_to(identity, target_is_directory=True)
    write(combined / 'provenance.json', {'schema': 'v6-s3-comparison-view/1',
          'note': '本目录仅为比较视图，不是一次独立运行；配置以两次真实运行记录为准。',
          'source_runs': [str(OUT / name) for name in ('smoke', 'remaining')]})
    write(combined / 'results/B.json', {'schema': 'v6-s3-merged-results/1', 'results': all_results,
          'source_results': [str(OUT / name / 'results/B.json') for name in ('smoke', 'remaining')]})
    semantics = [validate_h5(BASE, full, 'base'), validate_h5(combined, full, 'v6')]
    write(OUT / 'h5_semantics.json', {'schema': 'v6-s3-h5-semantics/1', 'sides': semantics})
    command(['uv', 'run', '--no-sync', 'python', str(ENTRY), 'compare',
             '--run', f'base={BASE}', '--run', f'v6={combined}', '--pair', 'base/B:v6/B',
             '--output', str(OUT / 'compare')], OUT / 'compare.log')
    pairs = [json.loads(line) for line in (OUT / 'compare/h5_pairs.jsonl').read_text().splitlines()]
    expected_ids = {f"{r['task']}_episode_{r['episode']}" for r in full}
    assert len(pairs) == 144 and {row['identity'] for row in pairs} == expected_ids
    assert all(row['sha_equal'] == 1 and row['field_mismatch'] == 0 for row in pairs)
    print('NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0', flush=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['--prepare']:
        prepare()
    elif sys.argv[1:] == ['--run']:
        run()
    else:
        raise SystemExit('必须明确指定 --prepare 或 --run')
