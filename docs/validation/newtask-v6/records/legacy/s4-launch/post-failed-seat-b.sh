#!/usr/bin/env bash
# 仅回传已经停止的故障席位证据，不把生成失败改写为成功。
set -euo pipefail
HERE=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/s4-launch
test "$(tail -n 1 "$HERE/logs/61890468.log")" = EXIT_CODE=137
grep -q 'STEP 61890468.10 ON gl1517 CANCELLED' "$HERE/logs/61890468.log"
bash "$HERE/hash-seat.sh" 61890468
bash "$HERE/receive-seat.sh" 61890468
