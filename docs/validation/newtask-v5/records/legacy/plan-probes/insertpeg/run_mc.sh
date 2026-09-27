#!/bin/bash
# 并行跑 Monte Carlo 各组（每组若干配置），结果写 mc_<组>.json / .log
set -o pipefail
S=/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/insertpeg
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
run() { PYTHONUNBUFFERED=1 uv run --no-sync python $S/mc.py --n 10000 --K 1024 --configs "$2" --out $S/mc_$1.json 2>&1 | grep --line-buffered -v Warn | tee $S/mc_$1.log; }
run a "0,1,2,3,4,5,6,7,8" &
run b "9,10,11,12,13" &
run c "14,15" &
run d "16,17" &
run e "18,19" &
run f "20,21" &
run g "22,23" &
run h "24,25" &
run i "26,27" &
run j "28,29" &
run k "30,31" &
run l "32,33,34" &
wait
echo ALL_DONE
