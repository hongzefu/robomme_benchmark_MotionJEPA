#!/bin/bash
# 本机 5.1 单格：eval-local.sh <cond> <seat> <idx> <gpu> <cpus> <mode: per-task|reverse>
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
WT=$R/artifacts/v7.5eval/wt/a81c4f6b
COND=$1; SEAT=$2; IDX=$3; GPU=$4; CPUS=$5; MODE=$6
cd $WT || exit 97
export MME_PY=$R/third_party/mme-vla/.venv/bin/python SMVLA_PY=$R/artifacts/v7.5eval/venvs/smvla-env/bin/python BENCH_PY=$R/.venv/bin/python
case $MODE in per-task) M=(--client-per-task);; reverse) M=(--order reverse);; esac
rc_all=0
for P in smvla mme; do
  DET=$(bash $N/lanes/det_of.sh $R/artifacts/v7.5eval/replay/P3/$P/report.json) || { echo "DET_MISSING $P"; rc_all=9; continue; }
  echo "EVAL_LOCAL_START cond=$COND policy=$P det=$DET mode=$MODE $(date -Is)"
  bash scripts/eval-official/run_seat.sh --seat $SEAT --seat-idx $IDX --gpu $GPU --cpus $CPUS --cond $COND \
    --out $R/artifacts/v7.5eval/newiface/$COND --identities $R/artifacts/v7.5eval/identities-small48.json \
    --policies $P --det $DET "${M[@]}" \
    --mme-ckpt /data/hongzefu/robomme_policy_learning_MotionJEPA/v1-store/models/official-mme-vla/perceptual-framesamp-modul/79999 \
    --smvla-ckpt $R/artifacts/v7.5eval/ckpt/simplememvla_robomme
  rc=$?; echo "EVAL_LOCAL_END cond=$COND policy=$P det=$DET rc=$rc $(date -Is)"; [ $rc = 0 ] || rc_all=$rc
done
exit $rc_all
