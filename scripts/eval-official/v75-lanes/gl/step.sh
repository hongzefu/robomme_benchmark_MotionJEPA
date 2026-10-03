#!/bin/bash
# 编排器步骤包装：执行命令，写报告 JSON（rc 与起止时间），末行 STEP_RC=
# 若 $N/skip/<报告名>.skip 存在：该步骤已改派到别的席位执行，直接退出（不写报告、不碰产物）
REPORT=$1; shift
SKIP=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval/skip/$(basename "$REPORT" .json).skip
if [ -z "${V75_NOSKIP:-}" ] && [ -e "$SKIP" ]; then echo "STEP_SKIPPED_REASSIGNED report=$REPORT reason=$(cat "$SKIP")"; echo "STEP_RC=3"; exit 3; fi
START=$(date -Is)
"$@"; rc=$?
mkdir -p "$(dirname "$REPORT")"
printf '{"rc": %d, "start": "%s", "end": "%s", "host": "%s", "job": "%s"}\n' "$rc" "$START" "$(date -Is)" "$(hostname)" "${SLURM_JOB_ID:-none}" > "$REPORT"
echo "STEP_RC=$rc"
exit $rc
