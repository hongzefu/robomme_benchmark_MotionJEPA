"""纯文件运行树核验，先验证清单，再核对NFS文件；可选验证实际包导入路径。"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path

BASELINE = '38488db08954ed10c0dd5450a5ccca9b6294d9dd'


def verify_tree(root, manifest_path, expected_sha):
    root, manifest_path = Path(root).resolve(), Path(manifest_path)
    data = manifest_path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected_sha, '运行源码清单SHA不符'
    manifest = json.loads(data)
    assert manifest['schema'] == 'v6-runtime-tree/1' and manifest['source_commit'] == BASELINE
    assert manifest['scan_roots'] == ['src', 'scripts', 'tests']
    assert manifest['extra_suffixes'] == ['.py', '.json']
    assert manifest['excluded_components'] == ['__pycache__']
    registered = manifest['files']
    assert registered
    for name, expected in registered.items():
        relative = Path(name)
        assert not relative.is_absolute() and '..' not in relative.parts, name
        path = root / relative
        assert path.is_file() and not path.is_symlink(), ('缺文件或符号链接', name)
        content = path.read_bytes()
        assert len(content) == expected['bytes'] and hashlib.sha256(content).hexdigest() == expected['sha256'], ('源码SHA不符', name)
    extra = []
    for name in manifest['scan_roots']:
        directory = root / name
        assert directory.is_dir() and not directory.is_symlink(), name
        for path in directory.rglob('*'):
            relative = path.relative_to(root)
            if '__pycache__' in relative.parts:
                continue
            assert not path.is_symlink(), ('源码目录含额外符号链接', str(relative))
            if path.is_file() and path.suffix in ('.py', '.json') and str(relative) not in registered:
                extra.append(str(relative))
    assert not extra, ('运行源码存在未登记文件', sorted(extra))
    print(f'RUNTIME_TREE=PASS baseline={BASELINE} files={len(registered)} extra=0 manifest_sha256={expected_sha}', flush=True)
    return len(registered)


def check_import(root):
    module = importlib.import_module('robomme')
    actual = Path(module.__file__).resolve()
    expected = Path(root).resolve() / 'src/robomme/__init__.py'
    assert actual == expected, ('robomme实际导入位置不符', str(actual), str(expected))
    assert {Path(p).resolve() for p in module.__path__} == {expected.parent}
    print(f'ROBOMME_IMPORT=PASS path={actual}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--check-import', action='store_true')
    args = parser.parse_args()
    verify_tree(args.root, args.manifest, args.expected_sha)
    if args.check_import:
        check_import(args.root)
