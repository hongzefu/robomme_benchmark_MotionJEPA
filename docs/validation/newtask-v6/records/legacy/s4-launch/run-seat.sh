#!/usr/bin/env bash
# 两席共用启动器；由主代理在独立 tmux 会话中显式调用，不自动重试。
set -uo pipefail
MAIN_ROOT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
LOG_ROOT="$MAIN_ROOT/artifacts/newtask-v6/s4-launch/logs"
case "${1:-}" in
  61890467) JOB_ID=61890467; EXPECTED_NODE=gl1526; TIERS=xhard1,xhard2; MIN_FREE=160000000000 ;;
  61890468) JOB_ID=61890468; EXPECTED_NODE=gl1517; TIERS=xhard3,xhard4; MIN_FREE=180000000000 ;;
  *) printf '需要指定已批准的作业号 61890467 或 61890468\n' >&2; exit 64 ;;
esac
cd "$MAIN_ROOT" || exit 70
LAUNCH_ANCHOR=$(cat "$MAIN_ROOT/artifacts/newtask-v6/s4-launch/launch-commit.txt") || exit 71
[[ "$LAUNCH_ANCHOR" =~ ^[0-9a-f]{40}$ ]] || exit 71
test "$(git rev-parse HEAD)" = "$LAUNCH_ANCHOR" || exit 71
test -z "$(git status --porcelain)" || exit 71
git diff --quiet 38488db08954ed10c0dd5450a5ccca9b6294d9dd "$LAUNCH_ANCHOR" -- src scripts tests pyproject.toml uv.lock || exit 71
printf 'LAUNCH_SOURCE=PASS anchor=%s code_baseline=38488db08954ed10c0dd5450a5ccca9b6294d9dd\n' "$LAUNCH_ANCHOR"
mkdir -p "$LOG_ROOT" || exit 72
LOG="$LOG_ROOT/$JOB_ID.log"
test ! -e "$LOG" || { printf '日志已存在，拒绝覆盖：%s\n' "$LOG" >&2; exit 73; }
ssh -o BatchMode=yes greatlakes "srun --jobid=$JOB_ID --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared bash -s -- $EXPECTED_NODE $TIERS $MIN_FREE" 2>&1 <<'REMOTE' | tee "$LOG"
set -euo pipefail
EXPECTED_NODE="$1"
TIERS="$2"
MIN_FREE="$3"
cd /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
RUN_ID=/tmp/v6-s4-v6-01
test "$(hostname -s)" = "$EXPECTED_NODE"
test ! -e "$RUN_ID"
test "$(df -B1 --output=avail /tmp | tail -n 1 | tr -d ' ')" -ge "$MIN_FREE"
test "$(df -Pi /tmp | awk 'NR==2 {print $4}')" -gt 10000
export UV_CACHE_DIR="$HOME/.cache/uv" UV_LINK_MODE=copy
export XDG_CACHE_HOME="$RUN_ID/.cache" HF_HOME="$RUN_ID/.cache/huggingface"
export PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$PWD/src"
command -v uv
test "$(cat artifacts/train-parity/local-smoke-01/official-src/.official_tree)" = 1d4c13697f0c5fbd7a8b05e01c196c984a07406c
printf '%s  %s\n' 6ab3b0c218ad77e29f765f98f2e670c7462d386db9f23257e282242094a5dab3 scripts/configs/newtask-v6/sampling_config.json | sha256sum --check
uv run --project "$PWD" --frozen --no-sync python - <<'PY'
import importlib
from pathlib import Path
import robomme
root = Path.cwd().resolve()
module = importlib.import_module('robomme.robomme_env.BinFill')
for label, value in [('robomme', robomme.__file__), ('BinFill', module.__file__)]:
    path = Path(value).resolve()
    assert path.is_relative_to(root / 'src'), (label, str(path))
    print(f'IMPORT_PATH=PASS module={label} path={path}', flush=True)
PY
ARGS=(--release newtask-v6 --run-id "$RUN_ID" --tiers "$TIERS" --tasks all
      --candidates-per-env 10 --max-reset-attempts 60 --select 0,3,6
      --draw-workers 16 --draw-gpus 0 --workers 16 --rollout-gpu 0
      --official-root artifacts/train-parity/local-smoke-01/official-src)
uv run --project "$PWD" --frozen --no-sync python -m scripts.parity.v5_generation pipeline "${ARGS[@]}" --dry-run
timeout --signal=TERM --kill-after=30s 6h uv run --project "$PWD" --frozen --no-sync python -m scripts.parity.v5_generation pipeline "${ARGS[@]}"
REMOTE
rc=$?
printf 'EXIT_CODE=%s\n' "$rc" | tee -a "$LOG"
exit "$rc"
