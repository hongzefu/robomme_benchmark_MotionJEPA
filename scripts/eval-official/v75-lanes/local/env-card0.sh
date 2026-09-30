#!/bin/bash
# 2.1 本机卡 0 车道：C1 首遍 → C2 常驻倒序（串行同卡）
set -o pipefail
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
WT=$R/artifacts/v7.5eval/wt/2176a0e3
PY=$R/.venv/bin/python
ID=$R/artifacts/v7.5eval/identities-small48.json
OUT=$R/artifacts/v7.5eval/env
cd $WT
export CUDA_VISIBLE_DEVICES=0 PYTHONUNBUFFERED=1
echo "LANE_START env-card0 commit=$(git rev-parse HEAD) $(date -Is)"
taskset -c 0-3 $PY scripts/parity/hard_regression.py env-digest --cell C1 --identities $ID --out $OUT --gpu 0; echo "STEP_EXIT C1 rc=$?"
taskset -c 0-3 $PY scripts/parity/hard_regression.py env-digest --cell C2 --identities $ID --out $OUT --gpu 0 --resident --reverse; echo "STEP_EXIT C2 rc=$?"
$PY scripts/parity/hard_regression.py env-digest-compare --a $OUT/C1 --b $OUT/C2 --out $OUT/parity-C1-C2.json; echo "STEP_EXIT cmp rc=$?"
echo "全部完成 $(date -Is)"
