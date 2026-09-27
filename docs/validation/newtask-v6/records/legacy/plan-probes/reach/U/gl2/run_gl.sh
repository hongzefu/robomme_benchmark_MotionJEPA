#!/bin/bash
# 在占位 job 里跑 U 复测：16 worker，逐局产物写节点本地 /tmp 并即刻删除，结果 jsonl 落 NFS 本目录
set -o pipefail
REPO=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
D=$REPO/artifacts/newtask-v6/reach-U2
mkdir -p /tmp/hongzefu-reachU2/episodes
cd $REPO
export PROBE_REPO=$REPO OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1
srun --jobid=61890468 --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared \
  bash -c "cd $REPO && mkdir -p /tmp/hongzefu-reachU2/episodes && export PROBE_REPO=$REPO OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1 && nvidia-smi -L && uv run --no-sync python $D/run_probe.py --gpu 0 --workers 16 --dir $D; rm -rf /tmp/hongzefu-reachU2" 2>&1 | tee $D/run_gl.log
echo "EXIT_CODE=$?" >> $D/run_gl.log
