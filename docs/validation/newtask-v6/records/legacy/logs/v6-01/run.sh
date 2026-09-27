#!/bin/bash
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
N=14
for k in $(seq 0 $((N-1))); do
  gpu=$((k % 2))
  ( set -o pipefail; CUDA_VISIBLE_DEVICES=$gpu PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.parity.v4_combos run --combos scripts/configs/newtask-v4/combos.json --samples 5 --shard $k/$N --gpu $gpu --out /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/combos/v6-01 2>&1 | tee /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/logs/v6-01/shard-$k.log >/dev/null; echo "WORKER $k EXIT=$?" | tee -a /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/logs/v6-01/master.log ) &
done
wait
PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.parity.v4_combos summarize --combos scripts/configs/newtask-v4/combos.json --samples 5 --out /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/combos/v6-01 2>&1 | tee -a /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/logs/v6-01/master.log
echo "EXIT_CODE=$?" >> /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/logs/v6-01/master.log
