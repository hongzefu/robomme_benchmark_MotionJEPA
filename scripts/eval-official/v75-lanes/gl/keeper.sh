#!/bin/bash
# 登录节点 tmux 内：keeper.sh <jobid> [取消的等待步骤号...]；先取消点名的等待步骤，再起一个永不结束的 --gpu_cmode=shared 保持步骤
J=$1; shift
for v in $(env | grep -o '^SLURM_[A-Z_]*'); do unset "$v"; done
for s in "$@"; do scancel "$J.$s" && echo "KEEPER cancelled $J.$s $(date -Is)"; done
echo "KEEPER start $J $(date -Is)"
exec srun --jobid="$J" --overlap --ntasks=1 --cpus-per-task=1 --gpu_cmode=shared --job-name=v75-keeper sleep infinity
