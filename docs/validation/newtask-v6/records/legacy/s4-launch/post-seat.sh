#!/usr/bin/env bash
# 每席生成退出后先冻结源端散列清单，再把同一份产物回传本机。
set -euo pipefail
HERE=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/s4-launch
case "${1:-}" in 61890467|61890468) JOB_ID="$1" ;; *) exit 64 ;; esac
test "$(tail -n 1 "$HERE/logs/$JOB_ID.log")" = EXIT_CODE=0
bash "$HERE/hash-seat.sh" "$JOB_ID"
bash "$HERE/receive-seat.sh" "$JOB_ID"
