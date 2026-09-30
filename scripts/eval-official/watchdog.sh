#!/usr/bin/env bash
# v7.5eval 编排器看门狗（0929-v7.5eval-restructure-plan.md 第二部分 §3 runbook；AGENTS.md P4「检查器自身崩溃也必须被独立监督」）。
#
# 用法：watchdog.sh --heartbeat <state>/orch.heartbeat [--stale 600] [--interval 30] [--events <file>]
#
# - 心跳文件缺失或 mtime 距今 >= --stale 秒（整秒精度）：每个「过期期」只写一次 ORCH_DEAD 行
#   （stdout + <state>/events.log），并写 <state>/notify/<时间>-needs_human-orch_dead.json；
#   心跳恢复更新时写一行 ORCH_ALIVE，开启下一个过期期的判定。
# - 心跳 JSON 的 "phase" 为 "done"（编排器正常收尾）时写 WATCHDOG_EXIT reason=orch_done 并退出 0。
# - 退出时（含被信号终止）由 trap 打印 EXIT_CODE=。
set -u

HEARTBEAT=""
STALE=600
INTERVAL=30
EVENTS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --heartbeat) HEARTBEAT="$2"; shift 2 ;;
    --stale) STALE="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --events) EVENTS="$2"; shift 2 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done
if [ -z "$HEARTBEAT" ]; then
  echo "缺 --heartbeat" >&2
  exit 2
fi
STATE_DIR="$(cd "$(dirname "$HEARTBEAT")" 2>/dev/null && pwd || dirname "$HEARTBEAT")"
[ -n "$EVENTS" ] || EVENTS="$STATE_DIR/events.log"
NOTIFY_DIR="$STATE_DIR/notify"

on_exit() { rc=$?; echo "EXIT_CODE=$rc"; }
trap on_exit EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

ts() { date +%Y-%m-%dT%H:%M:%S%z; }
emit() {
  # 单行事件同时写 stdout 与 events.log
  echo "$1"
  echo "$1" >> "$EVENTS" 2>/dev/null || echo "WATCHDOG_EVENTS_WRITE_FAIL file=$EVENTS" >&2
}

echo "WATCHDOG_START ts=$(ts) heartbeat=$HEARTBEAT stale_s=$STALE interval_s=$INTERVAL pid=$$"
dead=0
while :; do
  now=$(date +%s)
  if [ -e "$HEARTBEAT" ]; then
    mtime=$(stat -c %Y "$HEARTBEAT" 2>/dev/null || echo 0)
    age=$((now - mtime))
    if grep -q '"phase": "done"' "$HEARTBEAT" 2>/dev/null; then
      emit "WATCHDOG_EXIT ts=$(ts) reason=orch_done heartbeat=$HEARTBEAT"
      exit 0
    fi
  else
    age=-1
  fi
  if [ "$age" -lt 0 ] || [ "$age" -ge "$STALE" ]; then
    if [ "$dead" -eq 0 ]; then
      dead=1
      emit "ORCH_DEAD ts=$(ts) heartbeat=$HEARTBEAT age_s=$age stale_s=$STALE"
      mkdir -p "$NOTIFY_DIR" 2>/dev/null
      printf '{"kind": "needs_human", "name": "orch", "event": "ORCH_DEAD", "age_s": %s, "heartbeat": "%s", "ts": "%s"}\n' \
        "$age" "$HEARTBEAT" "$(ts)" > "$NOTIFY_DIR/$(date +%Y%m%dT%H%M%S)-needs_human-orch_dead.json" 2>/dev/null
    fi
  elif [ "$dead" -eq 1 ]; then
    dead=0
    emit "ORCH_ALIVE ts=$(ts) heartbeat=$HEARTBEAT age_s=$age"
  fi
  sleep "$INTERVAL"
done
