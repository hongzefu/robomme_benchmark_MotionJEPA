#!/bin/bash
# M2 批量：每个配置 N=300 个合成布局（seed 9_100_000+i / 9_300_000+i），8 进程
SP=/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
N=300; P=8
for T in VideoUnmaskSwap ButtonUnmaskSwap; do
  for C in 3 6 10 15 20; do uv run --no-sync python $SP/m2_outer_sim.py $T v4 $C perm $N 0.07 $P; done
  for C in 3 6 10 15; do uv run --no-sync python $SP/m2_outer_sim.py $T tight $C perm $N 0.07 $P; done
  uv run --no-sync python $SP/m2_outer_sim.py $T v4 3 rand $N 0.07 $P
  uv run --no-sync python $SP/m2_outer_sim.py $T v4 10 rot3 $N 0.07 $P
  uv run --no-sync python $SP/m2_outer_sim.py $T v4 10 perm $N 0.05 $P
  uv run --no-sync python $SP/m2_outer_sim.py $T tight 10 perm $N 0.05 $P
done
echo ALL_DONE
