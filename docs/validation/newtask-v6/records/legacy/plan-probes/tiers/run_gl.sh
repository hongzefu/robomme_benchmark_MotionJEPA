#!/bin/bash
# V6 三档实测：塞进占位 job 61890467（16 CPU/A40），16 worker；逐局产物写节点本地 /tmp 并即刻删除，结果 jsonl 落 NFS
set -o pipefail
REPO=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
D=$REPO/artifacts/newtask-v6/tiers
cd $REPO
srun --jobid=61890467 --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared \
  bash -c "cd $REPO && mkdir -p /tmp/hongzefu-tiers && export PROBE_REPO=$REPO CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1 && nvidia-smi -L && uv run --no-sync python $D/run_tiers.py --gpu 0 --workers 16 --out $D/results.jsonl --tmp-root /tmp/hongzefu-tiers; rm -rf /tmp/hongzefu-tiers" 2>&1 | tee $D/run_gl.log
echo "EXIT_CODE=$?" >> $D/run_gl.log
