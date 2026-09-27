#!/bin/bash
# swap-real：塞进占位 job 61890468 跑，16 worker；逐局产物写节点本地 /tmp 并在 worker 内即刻删除；结果 jsonl 落 NFS 本目录
set -o pipefail
REPO=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
D=$REPO/artifacts/newtask-v6/swap-real
cd $REPO
srun --jobid=61890468 --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared \
  bash -c "cd $REPO && mkdir -p /tmp/hongzefu-swapreal/episodes && export PROBE_REPO=$REPO OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1 && nvidia-smi -L && uv run --no-sync python $D/run_probe.py --gpu 0 --workers 16 --out $D/results.jsonl --tmp /tmp/hongzefu-swapreal --s5 48 --v5 24; rm -rf /tmp/hongzefu-swapreal" 2>&1 | tee $D/run_gl.log
echo "EXIT_CODE=$?" >> $D/run_gl.log
