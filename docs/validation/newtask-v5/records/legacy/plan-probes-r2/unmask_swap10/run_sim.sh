#!/bin/bash
set -o pipefail
cd /data/hongzefu/robomme_v5_probe_wt
export CUDA_VISIBLE_DEVICES=0 PYTHONPATH=/data/hongzefu/robomme_v5_probe_wt/src UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONUNBUFFERED=1
R="uv run --no-sync python /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v5/plan-probes-r2/unmask_swap10/proto_sim.py"
F='pkg_resources|pynvml|UserWarning|FutureWarning'
for pf in 1 0; do
  SWAP10_PREFILTER=$pf $R reset VideoUnmaskSwap 9100000,9100001,9100205,4500300 2>&1 | grep -v -E "$F"
  SWAP10_PREFILTER=$pf $R reset ButtonUnmaskSwap 9300000,9300002,9300006,9300009 2>&1 | grep -v -E "$F"
done
SWAP10_PREFILTER=1 $R demo VideoUnmaskSwap 9100000,9100001,9100205 2>&1 | grep -v -E "$F"
SWAP10_PREFILTER=1 $R demo ButtonUnmaskSwap 9300000,9300002,9300006 2>&1 | grep -v -E "$F"
echo 全部完成
