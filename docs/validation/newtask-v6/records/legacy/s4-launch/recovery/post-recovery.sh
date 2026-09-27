#!/usr/bin/env bash
# 恢复完成后独立验收；仅主代理显式启动，不生成轨迹。
set -euo pipefail
ROOT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
HERE="$ROOT/artifacts/newtask-v6/s4-launch"
VERIFY="$HERE/verification"
DEST="$ROOT/artifacts/newtask-v6/v6-01-infra-recovery-01"
SOURCE=/tmp/v6-s4-v6-01-infra-recovery-01
test "$(tail -n 1 "$HERE/recovery/run.log")" = EXIT_CODE=0 || { printf '恢复日志尚未成功结束\n' >&2; exit 75; }
test ! -e "$DEST" && test ! -L "$DEST" || { printf '接收目录已存在，拒绝覆盖\n' >&2; exit 73; }
test ! -L "$VERIFY"
mkdir -p "$VERIFY"
for name in source-recovery.json transfer-recovery.json media-recovery.json recovery.stderr.log recovery.exit; do
  test ! -e "$VERIFY/$name" && test ! -L "$VERIFY/$name" || exit 73
done
set -o noclobber
exec 4>"$VERIFY/recovery.stderr.log"
exec 2>&4
trap 'rc=$?; printf "POST_RECOVERY_EXIT_CODE=%s\n" "$rc" | tee "$VERIFY/recovery.exit"; exit "$rc"' EXIT
cd "$ROOT"
export UV_CACHE_DIR="$ROOT/artifacts/cache/uv" UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
command -v uv >&2
ssh -o BatchMode=yes greatlakes 'srun --jobid=61890468 --overlap --exact --ntasks=1 --cpus-per-task=1 --gres=none bash -s' >"$VERIFY/source-recovery.json" <<'REMOTE'
set -euo pipefail
test "$(hostname -s)" = gl1517
cd /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
export UV_CACHE_DIR="$HOME/.cache/uv" UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1
command -v uv >&2
uv run --project "$PWD" --frozen --no-sync python - <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path('/tmp/v6-s4-v6-01-infra-recovery-01')
files={}
for name in ('control','rollout'):
    directory=root/name
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError(f'源目录缺失或为符号链接：{directory}')
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise RuntimeError(f'禁止穿透符号链接：{path}')
        if not path.is_file():
            continue
        before=path.stat()
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(8*1024*1024),b''):
                digest.update(block)
        after=path.stat()
        if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):
            raise RuntimeError(f'源文件仍在变化：{path}')
        files[str(path.relative_to(root))]={'bytes':after.st_size,'sha256':digest.hexdigest()}
json.dump(files,sys.stdout,ensure_ascii=False,indent=2)
sys.stdout.write('\n')
PY
REMOTE
printf 'RECOVERY_SOURCE_HASH=PASS\n'
mkdir "$DEST"
rsync -a --info=progress2 -e 'ssh -o BatchMode=yes' \
  --rsync-path='srun --unbuffered --jobid=61890468 --overlap --exact --ntasks=1 --cpus-per-task=1 --gres=none rsync' \
  "greatlakes:$SOURCE/control" "greatlakes:$SOURCE/rollout" "$DEST/"
uv run --frozen --no-sync python "$HERE/verify_s4.py" compare --root "$DEST" \
  --source-manifest "$VERIFY/source-recovery.json" --out "$VERIFY/transfer-recovery.json"
uv run --frozen --no-sync python - "$HERE/verify_s4.py" "$DEST" "$VERIFY/media-recovery.json" <<'PY'
import importlib.util,json,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('s4_verify',sys.argv[1])
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root=Path(sys.argv[2])/'rollout/run1'
checks,errors=[],[]
rows=module.read_rows(root/'results.jsonl')
for row in rows:
    if row.get('ok') is not True:
        continue
    identity={k:row[k] for k in ('task','episode','difficulty','seed')}
    try:
        checks.append({**identity,**module.verify_success(root,row)})
    except Exception as exc:
        errors.append({**identity,'error':f'{type(exc).__name__}: {exc}'})
report={'verdict':'FAIL' if errors else 'PASS','checks':checks,'errors':errors,
        'video_scope':'每个成功结果的每个视频实际解码首帧，不证明全片解码',
        'successful_results':sum(row.get('ok') is True for row in rows),'total_results':len(rows)}
with Path(sys.argv[3]).open('x',encoding='utf-8') as stream:
    json.dump(report,stream,ensure_ascii=False,indent=2)
    stream.write('\n')
print(f"RECOVERY_MEDIA={report['verdict']} checks={len(checks)} errors={len(errors)}")
raise SystemExit(1 if errors else 0)
PY
printf 'POST_RECOVERY_DONE destination=%s\n' "$DEST"
