#!/bin/bash
# 通用：命令输出 tee 到日志并追加 EXIT_CODE 行
LOG=$1; shift
set -o pipefail
PYTHONUNBUFFERED=1 "$@" 2>&1 | tee -a "$LOG"
echo "EXIT_CODE=$?" >> "$LOG"
