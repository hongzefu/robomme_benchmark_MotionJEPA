#!/bin/bash
# 新旧接口开环（重跑一片 9 BinFill ep31 官方录制）
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask; L=$R/artifacts/v7.5eval/lanes
cd $R/artifacts/v7.5eval/wt/bac285d8 || exit 97
mkdir -p $R/artifacts/v7.5eval/replay/iface
S=$(bash $L/o1root.sh smvla) && $R/.venv/bin/python scripts/eval-official/policy_replay.py iface-open --policy smvla --rec-official $S/rec/BinFill_31_543100 \
  --old-src /nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA-official-xhard0/robomme_sim/robomme_env.py --out $R/artifacts/v7.5eval/replay/iface/o1-smvla.json
M=$(bash $L/o1root.sh mme) && $R/.venv/bin/python scripts/eval-official/policy_replay.py iface-open --policy mme --rec-official $M/rec/BinFill_31_543100 --proxy-rec $M/rec/proxy \
  --old-src /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-official-xhard0/examples/robomme --out $R/artifacts/v7.5eval/replay/iface/o1-mme.json
