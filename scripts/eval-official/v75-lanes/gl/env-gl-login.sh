#!/bin/bash
# 登录节点 tmux 内执行：乙 C5→C6 串行；丁 C7
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
WHICH=$1
for v in $(env | grep -o '^SLURM_[A-Z_]*'); do unset "$v"; done
S="srun --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared"
if [ "$WHICH" = yi ]; then
  $S --jobid=62608440 bash $N/lanes/env-gl.sh C5; echo "SRUN_EXIT C5 rc=$?"
  $S --jobid=62608440 bash $N/lanes/env-gl.sh C6; echo "SRUN_EXIT C6 rc=$?"
else
  $S --jobid=62608595 bash $N/lanes/env-gl.sh C7; echo "SRUN_EXIT C7 rc=$?"
fi
echo "全部完成 $(date -Is)"
