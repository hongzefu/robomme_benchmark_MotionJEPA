#!/bin/bash
# 第 4 步本机车道：replay-local.sh <gpu> <cpus> <cond...>；卡 0 先等 R1 结束
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
WT=$R/artifacts/v7.5eval/wt/30257b46
GPU=$1; CPUS=$2; shift 2
IN=$R/artifacts/v7.5eval/replay/inputs
if [ "$GPU" = 0 ]; then while tmux has-session -t '=v75-r1-card0' 2>/dev/null; do sleep 60; done; fi
cd $WT || exit 97
export MME_PY=$R/third_party/mme-vla/.venv/bin/python SMVLA_PY=$R/artifacts/v7.5eval/venvs/smvla-env/bin/python BENCH_PY=$R/.venv/bin/python CPUS=$CPUS SMVLA_CKPT=$R/artifacts/v7.5eval/ckpt/simplememvla_robomme
for COND in "$@"; do
  for P in ${POLICIES:-smvla mme}; do
    echo "REPLAY_LANE_START cond=$COND policy=$P gpu=$GPU $(date -Is)"
    bash scripts/eval-official/run_policy_replay.sh $COND $GPU $P $IN/A-$P $IN/B-$P $R/artifacts/v7.5eval/replay/$COND/$P
    echo "REPLAY_LANE_STEP cond=$COND policy=$P rc=$?"
  done
done
echo "全部完成 $(date -Is)"
