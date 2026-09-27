#!/bin/bash
set -o pipefail
cd /data/hongzefu/robomme_v5_probe_wt
export CUDA_VISIBLE_DEVICES=0 PYTHONPATH=/data/hongzefu/robomme_v5_probe_wt/src UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONUNBUFFERED=1
for t in VideoUnmaskSwap ButtonUnmaskSwap; do
  SWAP10_PREFILTER=${PF:-1} uv run --no-sync python /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v5/plan-probes-r2/unmask_swap10/offline_joint.py $t ${N:-500} 12 ${TAG:-main} 2>&1 | grep -v -E "pkg_resources|pynvml|UserWarning|FutureWarning"
done
echo 全部完成
