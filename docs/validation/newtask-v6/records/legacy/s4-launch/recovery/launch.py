"""批准文件生效后才允许一个shared步骤启动恢复；没有任何自动批准或重试。"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from recovery import approval, verify_manifest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ALLOWED_DOCUMENTS = frozenset({'AGENTS.md', 'NEWTASK_RELEASE_V6_PLAN.md', 'scripts/README.md'})
RUNTIME_MANIFEST_SHA256 = 'a781578c35820f386631887a56fc51dc310c171d439877b2bc29a342710717bd'


def verify_source():
    """只允许三份已授权文档的普通修改；工作树中的运行源码必须仍等于冻结基线。"""
    anchor = (HERE.parent / 'launch-commit.txt').read_text().strip()
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() == anchor
    status = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=REPO, text=True)
    for line in status.splitlines():
        assert line[:2] in {' M', 'M ', 'MM'} and line[3:] in ALLOWED_DOCUMENTS, ('未授权工作树状态', line)
        path = REPO / line[3:]
        assert path.is_file() and not path.is_symlink(), ('文档非普通文件', str(path))
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '--',
                                        'src', 'scripts', 'tests'], cwd=REPO, text=True)
    assert not untracked.strip(), ('运行源码目录存在未跟踪文件', untracked)
    subprocess.run(['git', 'diff', '--quiet', '38488db08954ed10c0dd5450a5ccca9b6294d9dd',
                    '--', 'src', 'scripts', 'tests', 'pyproject.toml', 'uv.lock',
                    ':(exclude)scripts/README.md'], cwd=REPO, check=True)
    documents = {}
    for name in sorted(ALLOWED_DOCUMENTS):
        path = REPO / name
        assert path.is_file() and not path.is_symlink(), name
        data = path.read_bytes()
        documents[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        print(f'LAUNCH_DOCUMENT path={name} sha256={documents[name]["sha256"]} bytes={len(data)}', flush=True)
    provenance = {'anchor': anchor, 'code_baseline': '38488db08954ed10c0dd5450a5ccca9b6294d9dd',
                  'working_tree_status': status.splitlines(), 'documents': documents,
                  'scope': '运行源码冻结；仅允许三份授权文档普通修改，不声明全工作树干净'}
    print(f'RECOVERY_SOURCE=PASS anchor={anchor} allowed_modified_documents={len(status.splitlines())} code_frozen=1', flush=True)
    return provenance


def check():
    manifest = approval(HERE / 'manifest.json', HERE / 'approval.json')
    verify_manifest(manifest)
    provenance = verify_source()
    runtime_manifest = HERE / 'runtime-manifest.json'
    assert hashlib.sha256(runtime_manifest.read_bytes()).hexdigest() == RUNTIME_MANIFEST_SHA256
    provenance['runtime_manifest_sha256'] = RUNTIME_MANIFEST_SHA256
    provenance['runtime_manifest_source'] = '38488db08954ed10c0dd5450a5ccca9b6294d9dd'
    print(f'RECOVERY_APPROVAL=PASS anchor={provenance["anchor"]} max_attempts=76', flush=True)
    return manifest, provenance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-approval', action='store_true')
    args = parser.parse_args()
    manifest, provenance = check()
    if args.check_approval:
        return 0
    with (HERE / 'launch-source.json').open('x') as stream:
        json.dump(provenance, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    assert manifest['output'] == '/tmp/v6-s4-v6-01-infra-recovery-01'
    script = '''set -euo pipefail
test "$(hostname -s)" = gl1517
cd /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
OUTPUT=/tmp/v6-s4-v6-01-infra-recovery-01
test ! -e "$OUTPUT"
test "$(nvidia-smi --query-gpu=uuid,compute_mode --format=csv,noheader)" = "GPU-dd2731bb-7405-64c2-6124-4487ab37cb31, Default"
mkdir -p "$OUTPUT/control"
export UV_CACHE_DIR="$HOME/.cache/uv" UV_LINK_MODE=copy
export XDG_CACHE_HOME="$OUTPUT/.cache" HF_HOME="$OUTPUT/.cache/huggingface"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/src"
command -v uv
'''
    for name in ('manifest.json', 'approval.json', 'recovery.py', 'launch-source.json',
                 'runtime-manifest.json', 'runtime_guard.py'):
        data = (HERE / name).read_bytes()
        encoded = base64.b64encode(data).decode()
        script += f"printf '%s' {shlex.quote(encoded)} | base64 --decode > \"$OUTPUT/control/{name}\"\n"
        script += f"printf '%s  %s\\n' {hashlib.sha256(data).hexdigest()} \"$OUTPUT/control/{name}\" | sha256sum --check\n"
    # 同一个shared步骤内，核验实际NFS执行树及导入位置；此处尚未构造任何环境。
    script += ('uv run --project "$PWD" --frozen --no-sync python "$OUTPUT/control/runtime_guard.py" '
               '--root "$PWD" --manifest "$OUTPUT/control/runtime-manifest.json" '
               f'--expected-sha {RUNTIME_MANIFEST_SHA256} --check-import\n')
    script += 'timeout --signal=TERM --kill-after=30s 6h uv run --project "$PWD" --frozen --no-sync python "$OUTPUT/control/recovery.py" --manifest "$OUTPUT/control/manifest.json" --approval "$OUTPUT/control/approval.json"\n'
    command = ['ssh', '-o', 'BatchMode=yes', 'greatlakes',
               'srun --jobid=61890468 --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared bash -s']
    return subprocess.run(command, input=script.encode()).returncode


if __name__ == '__main__':
    raise SystemExit(main())
