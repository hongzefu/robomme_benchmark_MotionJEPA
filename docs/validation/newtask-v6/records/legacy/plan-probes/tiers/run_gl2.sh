#!/bin/bash
set -o pipefail
REPO=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
D=$REPO/artifacts/newtask-v6/tiers
cd $REPO
srun --jobid=61890467 --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared   bash -c "cd $REPO && mkdir -p /tmp/hongzefu-tiers && export PROBE_REPO=$REPO CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1 && uv run --no-sync python $D/run_tiers.py --gpu 0 --workers 12 --out $D/results.jsonl --tmp-root /tmp/hongzefu-tiers; rm -rf /tmp/hongzefu-tiers" 2>&1 | tee $D/run_gl3.log
echo EXIT_CODE=$? >> $D/run_gl3.log
