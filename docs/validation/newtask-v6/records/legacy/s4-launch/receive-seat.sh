#!/usr/bin/env bash
# 独立回传已存在的档位目录；成功或失败批次均可留证，不重跑生成、不删除源头。
set -euo pipefail
MAIN_ROOT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
DEST="$MAIN_ROOT/artifacts/newtask-v6/v6-01"
case "${1:-}" in
  61890467) JOB_ID=61890467; TIERS=(xhard1 xhard2) ;;
  61890468) JOB_ID=61890468; TIERS=(xhard3 xhard4) ;;
  *) printf '需要指定已批准的作业号 61890467 或 61890468\n' >&2; exit 64 ;;
esac
test ! -L "$DEST"
mkdir -p "$DEST"
for tier in "${TIERS[@]}"; do
  test ! -e "$DEST/$tier" || { printf '接收目录已存在，拒绝覆盖：%s\n' "$DEST/$tier" >&2; exit 73; }
done
for tier in "${TIERS[@]}"; do
  # 中途失败可能尚未进入下一档；只回传实际存在目录，不制造成功记录。
  presence=$(ssh -o BatchMode=yes greatlakes "srun --jobid=$JOB_ID --overlap --exact --ntasks=1 --cpus-per-task=1 --gres=none bash -c 'if test -d /tmp/v6-s4-v6-01/$tier; then echo PRESENT; else echo MISSING; fi'")
  if [ "$presence" = MISSING ]; then
    printf 'TRANSFER_MISSING tier=%s job=%s\n' "$tier" "$JOB_ID"
    continue
  elif [ "$presence" != PRESENT ]; then
    printf 'TRANSFER_PROBE_FAIL tier=%s response=%s\n' "$tier" "$presence" >&2
    exit 74
  fi
  # 纯CPU步骤不申请GPU，避免短步骤结束将并发生成所用GPU恢复成独占模式。
  # srun 默认块缓冲会卡住 rsync 的协议握手，须显式关闭缓冲。
  rsync -a --info=progress2 -e 'ssh -o BatchMode=yes' \
    --rsync-path="srun --unbuffered --jobid=$JOB_ID --overlap --exact --ntasks=1 --cpus-per-task=1 --gres=none rsync" \
    "greatlakes:/tmp/v6-s4-v6-01/$tier" "$DEST/"
  printf 'TRANSFER_DONE tier=%s job=%s destination=%s\n' "$tier" "$JOB_ID" "$DEST/$tier"
done
printf 'TRANSFER_EXIT_CODE=0 job=%s\n' "$JOB_ID"
