#!/bin/bash
# 本机卡 1 接力：P3(smvla，已在跑) → P3 mme → 开环（重跑一录制）→ E3
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask; L=$R/artifacts/v7.5eval/lanes
while tmux has-session -t '=v75-replay-card1' 2>/dev/null; do sleep 60; done
echo "CHAIN1 P3_SMVLA_DONE $(date -Is)"
POLICIES=mme bash $L/replay-local2.sh 1 4-7 P3; echo "CHAIN1 P3mme rc=$?"
bash $L/iface-open-o1.sh; echo "CHAIN1 IFACE rc=$?"
bash $L/eval-local.sh E3 L1 9 1 4-7 per-task; echo "CHAIN1 E3 rc=$?"
echo "全部完成 $(date -Is)"
