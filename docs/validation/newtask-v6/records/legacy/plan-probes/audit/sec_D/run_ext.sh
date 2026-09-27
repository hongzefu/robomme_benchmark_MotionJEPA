#!/bin/bash
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
D=artifacts/newtask-v6/plan-probes/audit/sec_D
export CUDA_VISIBLE_DEVICES=1 PYTHONUNBUFFERED=1
grep PickHighlight $D/combos.txt | xargs -P 7 -L 1 bash -c 'uv run --no-sync python '$D'/reset_probe.py $0 $1 800 '$D'/reset_ext/$0_$1.jsonl 9100200 2>&1 | grep --line-buffered -E "DONE|Traceback|Error"'
echo ALL_DONE
