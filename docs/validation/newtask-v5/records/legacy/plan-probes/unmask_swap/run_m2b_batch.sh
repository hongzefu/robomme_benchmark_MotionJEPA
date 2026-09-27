#!/bin/bash
# M2b 批量（按优先级）：发起者顺延变体，每配置 N=300
SP=/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/unmask_swap
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
N=300; P=6
run() { uv run --no-sync python $SP/m2b_fallback.py "$@" $P; }
for T in VideoUnmaskSwap ButtonUnmaskSwap; do run $T v4pad 6 $N evc 0.07; done
for T in VideoUnmaskSwap ButtonUnmaskSwap; do run $T v4pad 10 $N evc 0.07; done
for T in VideoUnmaskSwap ButtonUnmaskSwap; do run $T v4pad 3 $N evc 0.07; done
for T in VideoUnmaskSwap ButtonUnmaskSwap; do run $T v4 10 $N evc 0.07; run $T v4 6 $N evc 0.07; run $T v4 3 $N evc 0.07; done
for T in VideoUnmaskSwap ButtonUnmaskSwap; do run $T v4pad 6 $N ev 0.07; run $T v4 10 $N ev 0.07; run $T v4 3 $N ev 0.07; done
for T in VideoUnmaskSwap ButtonUnmaskSwap; do run $T v4pad 15 $N evc 0.07; run $T v4pad 6 $N evc 0.05; run $T tight 10 $N evc 0.07; run $T tight 6 $N evc 0.07; done
echo ALL_DONE
