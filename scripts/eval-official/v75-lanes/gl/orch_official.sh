#!/bin/bash
# 登录节点 tmux 内：在编排席 62612889 里运行编排器（2.2 + 2.3）
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
PY=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/uv-python/cpython-3.11.14-linux-x86_64-gnu/bin/python3.11
exec srun --jobid=62612889 --overlap --ntasks=1 --cpus-per-task=1 $PY $N/wt/4c19c39a/scripts/eval-official/orchestrate.py --plan $N/state/official-plan.json --state $N/state/official --workdir $N
