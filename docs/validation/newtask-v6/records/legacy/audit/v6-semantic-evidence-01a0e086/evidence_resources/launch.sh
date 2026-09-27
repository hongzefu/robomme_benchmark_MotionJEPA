#!/usr/bin/env bash
# 由主代理放进独立 tmux；本脚本不创建、取消或重试作业。
set -uo pipefail
LOCAL_ROOT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/audit/v6-semantic-evidence-01a0e086/evidence_resources
REMOTE_ROOT=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/audit/v6-semantic-01a0e086
LOG="$LOCAL_ROOT/run.log"
test ! -e "$LOG" || exit 73
ssh -O check greatlakes || exit 74
ssh -o BatchMode=yes greatlakes \
  "srun --jobid=62018665 --overlap --exact --ntasks=1 --cpus-per-task=1 --gpu_cmode=shared bash '$REMOTE_ROOT/remote_run.sh'" \
  2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
printf 'EXIT_CODE=%s\n' "$rc" | tee -a "$LOG"
exit "$rc"
