#!/usr/bin/env bash
# 主代理创建批准文件后方可显式启动，缺批准时连SSH也不调用。
set -uo pipefail
ROOT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
HERE="$ROOT/artifacts/newtask-v6/s4-launch/recovery"
cd "$ROOT" || exit 70
export UV_CACHE_DIR="$ROOT/artifacts/cache/uv" PYTHONUNBUFFERED=1
uv run --frozen --no-sync python "$HERE/launch.py" --check-approval || exit 77
exec 9>"$HERE/launch.lock"
flock -n 9 || exit 78
test ! -e "$HERE/run.log" || exit 73
uv run --frozen --no-sync python "$HERE/launch.py" 2>&1 | tee "$HERE/run.log"
rc=$?
printf 'EXIT_CODE=%s\n' "$rc" | tee -a "$HERE/run.log"
exit "$rc"
