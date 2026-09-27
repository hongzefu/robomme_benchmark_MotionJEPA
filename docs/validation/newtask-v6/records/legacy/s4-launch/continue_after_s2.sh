#!/usr/bin/env bash
# 只消费已结束的 S2；恢复时复用报告与已运行分支，不覆盖、不重复派发。
set -euo pipefail
ROOT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
HERE="$ROOT/artifacts/newtask-v6/s4-launch"
S2="$ROOT/artifacts/newtask-v6/v6-s2-20260926-01"
S3="$ROOT/artifacts/newtask-v6/v6-s3-20260926-01"
cd "$ROOT"
export UV_CACHE_DIR="$ROOT/artifacts/cache/uv" PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
MODE="${1:-dispatch}"
case "$MODE" in dispatch|--check|--s3-child) ;; *) exit 64 ;; esac
test "$#" -le 1
trap 'rc=$?; printf "CONTINUE_STATUS=STOP exit=%s line=%s\n" "$rc" "$LINENO" >&2; exit "$rc"' ERR

guard_head() {
  local anchor
  anchor=$(cat "$HERE/launch-commit.txt")
  [[ "$anchor" =~ ^[0-9a-f]{40}$ ]]
  test "$(git rev-parse HEAD)" = "$anchor"
  test -z "$(git status --porcelain)"
  git diff --quiet 38488db08954ed10c0dd5450a5ccca9b6294d9dd "$anchor" -- src scripts tests pyproject.toml uv.lock
  printf 'LAUNCH_SOURCE=PASS anchor=%s code_baseline=38488db08954ed10c0dd5450a5ccca9b6294d9dd\n' "$anchor"
}

if [ "$MODE" = --s3-child ]; then
  guard_head
  test ! -e "$S3/run.log"
  set +e
  uv run --frozen --no-sync python "$S3/run_s3.py" --run 2>&1 | tee "$S3/run.log"
  rc=$?
  printf 'EXIT_CODE=%s\n' "$rc" | tee -a "$S3/run.log"
  exit "$rc"
fi
if [ "$MODE" != --check ]; then
  exec 9>"$HERE/continue.lock"
  flock -n 9
fi
guard_head
command -v uv
test -f uv.lock && test -f pyproject.toml
test -f "$S2/report.json" && test -f "$S2/report.md"
printf 'CONTINUE_STATUS=REUSE_S2_REPORT\n'
uv run --frozen --no-sync python "$HERE/s2_gate.py" "$ROOT"
guard_head
test -f "$S3/smoke_manifest.json" && test -f "$S3/remaining_manifest.json"

branch_state() {
  local session="$1" log="$2" marker="$3"
  if tmux has-session -t "=$session" 2>/dev/null; then
    printf 'RUNNING'
  elif [ -f "$log" ]; then
    if [ "$(tail -n 1 "$log")" = EXIT_CODE=0 ] && grep -qF "$marker" "$log"; then
      printf 'COMPLETE'
    else
      printf 'CONTINUE_STATUS=STOP incomplete_branch=%s log=%s\n' "$session" "$log" >&2
      return 73
    fi
  else
    printf 'READY'
  fi
}
S3_STATE=$(branch_state v6-s3-20260926-01 "$S3/run.log" 'NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0')
A_STATE=$(branch_state v6-s4-61890467 "$HERE/logs/61890467.log" 'cells=26')
B_STATE=$(branch_state v6-s4-61890468 "$HERE/logs/61890468.log" 'cells=29')
if [ "$S3_STATE" = READY ]; then
  for output in "$S3/launch.json" "$S3/smoke" "$S3/remaining"; do
    test ! -e "$output"
  done
fi
printf 'CONTINUE_BRANCH=STATE stage=S3 state=%s\n' "$S3_STATE"
printf 'CONTINUE_BRANCH=STATE stage=S4_A state=%s\n' "$A_STATE"
printf 'CONTINUE_BRANCH=STATE stage=S4_B state=%s\n' "$B_STATE"
if [ "$MODE" = --check ]; then
  printf 'CONTINUE_STATUS=CHECK_PASS dispatched=0\n'
  exit 0
fi
# 全部分支均检查后才派发，活动或已完成分支保持不动。
if [ "$S3_STATE" = READY ]; then
  tmux new-session -d -s v6-s3-20260926-01 "bash $HERE/continue_after_s2.sh --s3-child"
  printf 'CONTINUE_BRANCH=STARTED stage=S3 session=v6-s3-20260926-01\n'
fi
if [ "$A_STATE" = READY ]; then
  tmux new-session -d -s v6-s4-61890467 "bash $HERE/run-seat-a.sh"
  printf 'CONTINUE_BRANCH=STARTED stage=S4_A session=v6-s4-61890467\n'
fi
if [ "$B_STATE" = READY ]; then
  tmux new-session -d -s v6-s4-61890468 "bash $HERE/run-seat-b.sh"
  printf 'CONTINUE_BRANCH=STARTED stage=S4_B session=v6-s4-61890468\n'
fi
printf 'CONTINUE_STATUS=DISPATCHED_OR_RESUMED generation_result=PENDING\n'
