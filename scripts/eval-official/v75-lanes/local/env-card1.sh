#!/bin/bash
# 2.1 本机卡 1：C3（与卡 1 上其他 GPU 任务经 flock 串行）
set -o pipefail
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
WT=$R/artifacts/v7.5eval/wt/2176a0e3
PY=$R/.venv/bin/python
OUT=$R/artifacts/v7.5eval/env
cd $WT || exit 97
export CUDA_VISIBLE_DEVICES=1 PYTHONUNBUFFERED=1
echo "LANE_START env-card1 commit=$(git rev-parse HEAD) $(date -Is)"
flock /home/hongzefu/.claude/jobs/6f127313/tmp/gpu1.lock taskset -c 4-7 $PY scripts/parity/hard_regression.py env-digest --cell C3 --identities $R/artifacts/v7.5eval/identities-small48.json --out $OUT --gpu 1; echo "STEP_EXIT C3 rc=$?"
$PY scripts/parity/hard_regression.py env-digest-compare --a $OUT/C1 --b $OUT/C3 --out $OUT/parity-C1-C3.json; echo "STEP_EXIT cmp rc=$?"
echo "全部完成 $(date -Is)"
