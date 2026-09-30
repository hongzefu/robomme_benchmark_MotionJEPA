#!/bin/bash
# 2.4 本机旧官方小样本 R1（卡 0，taskset 0-3）
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
WT=$R/artifacts/v7.5eval/wt/2abf227d
cd $WT || exit 97
export CUDA_VISIBLE_DEVICES=0 MANIFEST=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval/official/manifest-small48.jsonl
exec taskset -c 0-3 bash scripts/eval-official/official_observer/official_rerun_shard.sh R1smoke 0 --port-base 19000
