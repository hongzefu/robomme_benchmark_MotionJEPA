#!/usr/bin/env bash
# 仅在源目录停止写入后由主代理启动；两档逐文件散列直回本机，不修改源端。
set -euo pipefail
HERE=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/s4-launch
case "${1:-}" in
  61890467) JOB_ID=61890467; EXPECTED_NODE=gl1526; TIERS=xhard1,xhard2 ;;
  61890468) JOB_ID=61890468; EXPECTED_NODE=gl1517; TIERS=xhard3,xhard4 ;;
  *) printf '需要已批准的作业号 61890467 或 61890468\n' >&2; exit 64 ;;
esac
test ! -L "$HERE/verification"
mkdir -p "$HERE/verification"
OUT="$HERE/verification/source-$JOB_ID.json"
LOG="$HERE/verification/source-$JOB_ID.stderr.log"
set -o noclobber
exec 3>"$OUT"
exec 4>"$LOG"
trap 'status=$?; printf "HASH_EXIT_CODE=%s job=%s\n" "$status" "$JOB_ID"' EXIT
# 散列仅使用CPU；不触发GPU步骤收尾的模式恢复。
ssh -o BatchMode=yes greatlakes "srun --jobid=$JOB_ID --overlap --exact --ntasks=1 --cpus-per-task=1 --gres=none bash -s -- $EXPECTED_NODE $TIERS" >&3 2>&4 <<'REMOTE'
set -euo pipefail
EXPECTED_NODE="$1"
TIERS="$2"
test "$(hostname -s)" = "$EXPECTED_NODE"
cd /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
export UV_CACHE_DIR="$HOME/.cache/uv" UV_LINK_MODE=copy
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
command -v uv >&2
uv run --project "$PWD" --frozen --no-sync python - "$TIERS" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path('/tmp/v6-s4-v6-01')
result = {}
for tier in sys.argv[1].split(','):
    directory = root / tier
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError(f'档位目录缺失或是符号链接：{directory}')
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise RuntimeError(f'禁止穿透符号链接：{path}')
        if not path.is_file():
            continue
        before = path.stat()
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(block)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise RuntimeError(f'散列期间源文件改变：{path}')
        result[str(path.relative_to(root))] = {'bytes': after.st_size, 'sha256': digest.hexdigest()}
json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
sys.stdout.write('\n')
print(f'源端散列完成 files={len(result)}', file=sys.stderr)
PY
REMOTE
exec 3>&-
exec 4>&-
printf 'HASH_MANIFEST_DONE job=%s out=%s stderr=%s\n' "$JOB_ID" "$OUT" "$LOG"
