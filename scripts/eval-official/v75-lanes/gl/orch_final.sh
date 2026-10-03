#!/bin/bash
# 第三个编排器：最终编排：重跑二续跑/补跑、5.2 MME 与补跑队列、E5 MME、甲丙金丝雀（等待只在本地步骤）
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
PY=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/uv-python/cpython-3.11.14-linux-x86_64-gnu/bin/python3.11
exec srun --jobid=62612889 --overlap --ntasks=1 --cpus-per-task=1 $PY $N/wt/30257b46/scripts/eval-official/orchestrate.py --plan $N/state/final-plan.json --state $N/state/final --workdir $N
