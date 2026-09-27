#!/usr/bin/env bash
set -o pipefail
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask || exit 1
unset PYTHONPATH
export UV_CACHE_DIR=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/cache/uv
export CUDA_VISIBLE_DEVICES=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1
timeout --signal=TERM --kill-after=5s 280s uv run --no-sync python scripts/parity/train_split_runner.py --official-root artifacts/train-parity/local-smoke-01/official-src --src-root . --jobs-json artifacts/newtask-v6/s3-slow-investigation/gpu1-smoke-20260926-01/jobs.json --results-json artifacts/newtask-v6/s3-slow-investigation/gpu1-smoke-20260926-01/results.json --workers 1 --gpu 1 2>&1 | tee artifacts/newtask-v6/s3-slow-investigation/gpu1-smoke-20260926-01/run.log
code=${PIPESTATUS[0]}
printf 'EXIT_CODE=%s\n' "$code" >> artifacts/newtask-v6/s3-slow-investigation/gpu1-smoke-20260926-01/run.log
exit "$code"
