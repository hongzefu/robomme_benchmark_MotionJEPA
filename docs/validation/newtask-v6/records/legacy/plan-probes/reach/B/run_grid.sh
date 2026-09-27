#!/bin/bash
# 16 个 worker 并行跑全网格，各写 parts/w*.csv
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
N=16
for i in $(seq 0 $((N-1))); do
  CUDA_VISIBLE_DEVICES=1 uv run --no-sync python artifacts/newtask-v6/plan-probes/reach/B/probe.py \
    --tasks artifacts/newtask-v6/plan-probes/reach/B/grid_tasks.json --worker $i --nworkers $N \
    --out artifacts/newtask-v6/plan-probes/reach/B/parts/w$i.csv 2>&1 | grep --line-buffered -E "^\[w|Traceback|Error" &
done
wait
echo "ALL DONE"
