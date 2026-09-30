#!/bin/bash
# 汇总器：各日志关键行加前缀写入一份汇总日志（每份日志一个 tail 进程，逐级行缓冲）
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/v7.5eval; N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
OUT=$R/logs/events-all.log
PAT='STEP_DONE|STEP_FAIL|LANE_DONE|ORCH_DONE|SEAT_EXPIRING|ORCH_DEAD|WATCHDOG_EXIT|CHAIN[01] |DET_RULE|POLICY_REPLAY_DONE|REPLAY_LANE_STEP|IFACE_OPEN|EVAL_LOCAL_END|SEAT_DONE|RUN_BLOCKED|INFRA_EXHAUSTED|NO_PROGRESS|B_MME_MISSING|DET_MISSING|MOVE_FAIL|MOVE_DIFF|STORAGE_DEGRADE|Traceback|out of memory|svulkan2|全部完成'
watch1() { tail -n 0 -F "$2" 2>/dev/null | stdbuf -oL tr '\r' '\n' | grep --line-buffered -aE "$PAT" | stdbuf -oL sed "s|^|[$1] |" >> "$OUT"; }
watch1 orch-off $N/logs/orch-official.log &
watch1 orch-main $N/logs/orch-main.log &
watch1 wd-off $N/logs/watchdog-official.log &
watch1 wd-main $N/logs/watchdog-main.log &
watch1 card0 $R/logs/chain-card0.log &
watch1 card1 $R/logs/chain-card1.log &
watch1 mover $R/logs/mover.log &
wait
