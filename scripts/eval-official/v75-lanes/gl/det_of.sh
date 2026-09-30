#!/bin/bash
# 读回放报告里的确定性默认值（等报告出现，最多 4 h）；打印 on|off
REP=$1
for i in $(seq 1 480); do
  [ -f "$REP" ] && { python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(d['det_rule']['default'])" "$REP" && exit 0; }
  sleep 30
done
echo "DET_REPORT_MISSING $REP" >&2; exit 1
