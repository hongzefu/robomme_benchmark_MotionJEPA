#!/usr/bin/env bash
set -o pipefail
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask || exit 1
UV_CACHE_DIR=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/cache/uv PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.parity.v6_site --host 0.0.0.0 --port 8060 --site-dir artifacts/newtask-v6/site-v9 2>&1 | tee -a artifacts/newtask-v6/site-v9/server.log
code=${PIPESTATUS[0]}
printf 'EXIT_CODE=%s\n' "$code" >> artifacts/newtask-v6/site-v9/server.log
exit "$code"
