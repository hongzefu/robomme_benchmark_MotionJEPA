#!/bin/bash
set -o pipefail
cd /data/hongzefu/robomme_v5_probe_wt
export CUDA_VISIBLE_DEVICES=0 PYTHONPATH=/data/hongzefu/robomme_v5_probe_wt/src UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONUNBUFFERED=1
for park in 1 0; do SWAP10_OUTER_CUBE_PARK=$park uv run --no-sync python /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v5/plan-probes-r2/unmask_swap10/proto_sim.py hold VideoUnmaskSwap 9100000 2>&1 | grep -E "^HOLD|Error|Traceback"; done
echo 全部完成
