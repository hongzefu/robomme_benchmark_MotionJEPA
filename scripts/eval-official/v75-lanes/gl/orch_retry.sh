#!/bin/bash
# 第三个编排器：补跑 E5 MME（乙）与丁的 E7 SMVLA 补暂存
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
PY=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/uv-python/cpython-3.11.14-linux-x86_64-gnu/bin/python3.11
exec srun --jobid=62612889 --overlap --ntasks=1 --cpus-per-task=1 $PY $N/wt/30257b46/scripts/eval-official/orchestrate.py --plan $N/state/retry-plan.json --state $N/state/retry --workdir $N
