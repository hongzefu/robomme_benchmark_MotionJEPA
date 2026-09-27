#!/bin/bash
# P3 演示层：4 局串行（v4-01 PatternLock 的 3 个 seed + 1 个后续 seed），GPU 0
cd /data/hongzefu/robomme_v5_probe_wt
export CUDA_VISIBLE_DEVICES=0 PYTHONPATH=/data/hongzefu/robomme_v5_probe_wt/src UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONUNBUFFERED=1
S=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v5/plan-probes-r2/patternlock_2425/demo_probe.py
for pair in "5501100 11" "5501200 12" "5501500 15" "5501800 18"; do
  set -- $pair
  echo "=== START seed=$1 ep=$2 $(date +%T)"
  uv run --no-sync python $S $1 $2 2>&1 | grep -vE "Warning|pkg_resources|import pynvml"
done
echo "DEMO_BATCH_DONE"
