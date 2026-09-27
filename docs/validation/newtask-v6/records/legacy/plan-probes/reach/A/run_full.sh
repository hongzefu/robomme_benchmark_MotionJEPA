#!/bin/bash
# 全网格 0.025 并行分片运行：5 类位姿 × 4 段 x 区间 = 20 个进程
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
D=artifacts/newtask-v6/plan-probes/reach/A
export CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1
T0=$(date +%s)
for t in grasp push push2 peg peg2; do
  for r in "-0.40 -0.225" "-0.20 -0.025" "0.0 0.175" "0.2 0.35"; do
    set -- $r
    uv run --no-sync python $D/probe_reach.py --step 0.025 --types $t --xmin $1 --xmax $2 \
      --out $D/shards/${t}_$1.csv 2>&1 | grep --line-buffered -E "TYPE_DONE|Error|Traceback" | sed -u "s/^/[$t x=$1] /" &
  done
done
wait
echo "ALL_SHARDS_FINISHED 用时 $(( $(date +%s) - T0 ))s"
echo DONE
