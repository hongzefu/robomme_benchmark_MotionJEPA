#!/bin/bash
# 打印重跑一片 9 某策略录制根（NFS 暂存或已搬回 /data 的副本）
P=$1
for d in /nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval/stage/O1/$P/s9 /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/v7.5eval/official-rec/O1/$P/s9; do
  [ -d "$d/rec/BinFill_31_543100" ] && { echo "$d"; exit 0; }
done; exit 1
