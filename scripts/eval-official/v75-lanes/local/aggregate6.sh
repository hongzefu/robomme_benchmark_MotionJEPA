#!/bin/bash
# 汇总器补充：o2x 编排器日志
OUT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/v7.5eval/logs/events-all.log
tail -n +1 -F /nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval/logs/orch-final2.log 2>/dev/null | stdbuf -oL tr '\r' '\n' | grep --line-buffered -aE 'STEP_START|STEP_DONE|STEP_FAIL|LANE_DONE|ORCH_DONE|SEAT_EXPIRING|PLAN_INVALID|Traceback' | stdbuf -oL sed 's|^|[orch-final2] |' >> "$OUT"
