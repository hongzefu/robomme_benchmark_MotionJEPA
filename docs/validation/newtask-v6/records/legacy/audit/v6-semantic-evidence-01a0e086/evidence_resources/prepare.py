"""只准备固定审查输入与来源清单，不启动仿真。"""
import hashlib
import json
from pathlib import Path

LOCAL = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-evidence-01a0e086/evidence_resources')
SNAPSHOT = Path('/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-0a3f989-01a0e086')
REMOTE = Path('/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/audit/v6-semantic-01a0e086')
SOURCE = SNAPSHOT / 'scripts/configs/newtask-v6/v6-01/xhard4/specs.jsonl'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(SOURCE) == 'c860fe93df0a67f9b24536ddfd8ed080ca13e41b5df29425dd32716ca09c351a'
rows = [json.loads(line) for line in SOURCE.read_text().splitlines()]
row = next(r for r in rows[1:] if r['task'] == 'VideoPlaceButton' and r['episode'] == 5)
assert row['seed'] == 7000500
assert row['spec_sha256'] == 'f08a26a6450a8fd1f20be62b25914f97f8ea287873fbbd6dadfde87233b18a31'
for path in sorted((REMOTE / 'runtime').rglob('*')):
    if path.is_file():
        original = SNAPSHOT / path.relative_to(REMOTE / 'runtime')
        assert path.read_bytes() == original.read_bytes(), str(path)
with (REMOTE / 'specs.jsonl').open('xb') as f:
    f.write(SOURCE.read_bytes())
with (REMOTE / 'identity.jsonl').open('x') as f:
    f.write(json.dumps({'task': 'VideoPlaceButton', 'episode': 5, 'role': 'semantic_probe'}) + '\n')
files = {}
for directory in ('runtime', 'official-src'):
    for path in sorted((REMOTE / directory).rglob('*')):
        assert not path.is_symlink(), str(path)
        if path.is_file():
            files[str(path.relative_to(REMOTE))] = {'sha256': sha(path), 'bytes': path.stat().st_size}
for name in ('specs.jsonl', 'identity.jsonl'):
    path = REMOTE / name
    files[name] = {'sha256': sha(path), 'bytes': path.stat().st_size}
manifest = {'audit_base': '0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8', 'official_tree': '1d4c13697f0c5fbd7a8b05e01c196c984a07406c', 'reset_limit': 2, 'rollout_limit': 1, 'retry_limit': 0, 'files': files}
for root in (LOCAL, REMOTE):
    with (root / 'source-manifest.json').open('x') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write('\n')
for directory in ('runtime', 'official-src'):
    for path in sorted((REMOTE / directory).rglob('*'), reverse=True):
        path.chmod(path.stat().st_mode & ~0o222)
    path = REMOTE / directory
    path.chmod(path.stat().st_mode & ~0o222)
print(f'PREPARATION=PASS files={len(files)} reset_limit=2 rollout_limit=1 retries=0')
