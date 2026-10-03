#!/bin/bash
# 本机卡 0 接力：R1 → P1 → E1 → E2
L=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/v7.5eval/lanes
while tmux has-session -t '=v75-r1-card0' 2>/dev/null; do sleep 60; done
echo "CHAIN0 R1_DONE $(date -Is)"
D=$(grep -a "^OFFICIAL_SHARD_DONE" /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/v7.5eval/logs/r1-card0.log | tail -1)
echo "CHAIN0 $D"
case "$D" in *staged=yes*) printf '{"line": "%s"}\n' "$D" > /nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval/reports/R1smoke-done.json;; *) echo "CHAIN0 R1_NOT_STAGED";; esac
bash $L/replay-local2.sh 0 0-3 P1; echo "CHAIN0 P1 rc=$?"
bash $L/eval-local.sh E1 L0 10 0 0-3 per-task; echo "CHAIN0 E1 rc=$?"
bash $L/eval-local.sh E2 L0 10 0 0-3 reverse; echo "CHAIN0 E2 rc=$?"
echo "全部完成 $(date -Is)"
