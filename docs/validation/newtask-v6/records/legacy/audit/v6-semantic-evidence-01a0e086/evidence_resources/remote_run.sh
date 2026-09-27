#!/usr/bin/env bash
# 仅运行固定规格的一局；失败、超时均不重试。
set -euo pipefail
AUDIT_ROOT=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/audit/v6-semantic-01a0e086
GL_ROOT=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
export UV_PROJECT_ENVIRONMENT="$GL_ROOT/.venv"
export UV_CACHE_DIR="$HOME/.cache/uv" UV_LINK_MODE=copy
export PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$AUDIT_ROOT/runtime/src:$AUDIT_ROOT/runtime"
export XDG_CACHE_HOME="$AUDIT_ROOT/cache" HF_HOME="$AUDIT_ROOT/cache/huggingface"
cd "$AUDIT_ROOT/runtime"
command -v uv
test ! -e "$AUDIT_ROOT/rollout/run1"
uv run --project "$PWD" --frozen --no-sync python - "$AUDIT_ROOT" <<'PY'
import hashlib, importlib.util, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
manifest = json.loads((root / 'source-manifest.json').read_text())
assert manifest['audit_base'] == '0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8'
for name, expected in manifest['files'].items():
    path = root / name
    assert path.is_file() and not path.is_symlink(), name
    assert path.stat().st_size == expected['bytes'], name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected['sha256'], name
assert (root / 'official-src/.official_tree').read_text().strip() == manifest['official_tree']
origin = pathlib.Path(importlib.util.find_spec('robomme').origin).resolve()
assert origin == root / 'runtime/src/robomme/__init__.py', str(origin)
print(f'SOURCE_PREFLIGHT=PASS files={len(manifest["files"])} import={origin}', flush=True)
PY
timeout --signal=TERM --kill-after=30s 600s \
  uv run --project "$PWD" --frozen --no-sync python -m scripts.parity.v4_rollout run \
  --specs "$AUDIT_ROOT/specs.jsonl" --identities-from "$AUDIT_ROOT/identity.jsonl" \
  --tasks VideoPlaceButton --label run1 --workers 1 --gpu 0 \
  --official-root "$AUDIT_ROOT/official-src" --output "$AUDIT_ROOT/rollout"
