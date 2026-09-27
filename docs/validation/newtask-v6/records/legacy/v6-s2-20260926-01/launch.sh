#!/usr/bin/env bash
# 固定批次的首条成功后才启动其余身份；失败不重试。
set -euo pipefail
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
export UV_CACHE_DIR=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/cache/uv
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --no-sync python artifacts/newtask-v6/v6-s2-20260926-01/run.py smoke --gpus 0
uv run --no-sync python artifacts/newtask-v6/v6-s2-20260926-01/run.py remaining --gpus 0,1 --workers-per-gpu 4
