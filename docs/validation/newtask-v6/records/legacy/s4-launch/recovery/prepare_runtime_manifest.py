"""从固定Git对象生成运行源码清单，不能由即将执行的NFS文件自证。"""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REF = '38488db08954ed10c0dd5450a5ccca9b6294d9dd'
paths = subprocess.check_output(['git', 'ls-tree', '-rz', '--name-only', REF, '--',
                                  'src', 'scripts', 'tests', 'pyproject.toml', 'uv.lock'], cwd=ROOT).decode().strip('\0').split('\0')
files = {}
for name in sorted(paths):
    if Path(name).suffix.lower() in ('.md', '.markdown'):
        continue
    data = subprocess.check_output(['git', 'show', f'{REF}:{name}'], cwd=ROOT)
    files[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
payload = {'schema': 'v6-runtime-tree/1', 'source_commit': REF,
           'scan_roots': ['src', 'scripts', 'tests'], 'extra_suffixes': ['.py', '.json'],
           'excluded_components': ['__pycache__'], 'excluded_tracked_suffixes': ['.md', '.markdown'],
           'output_boundary': '生成产物在/tmp独立根或artifacts，不在扫描的src/scripts/tests目录内；不豁免任何未知.py/.json',
           'files': files}
with (HERE / 'runtime-manifest.json').open('x') as stream:
    json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
    stream.write('\n')
print(f'RUNTIME_MANIFEST=PASS source={REF} files={len(files)} sha256={hashlib.sha256((HERE / "runtime-manifest.json").read_bytes()).hexdigest()}')
