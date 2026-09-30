#!/bin/bash
# 等重跑一片 9 MME 暂存，构建回放输入 B-mme（本机 + NFS）
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask; L=$R/artifacts/v7.5eval/lanes
for i in $(seq 1 240); do D=$(bash $L/o1root.sh mme) && break; sleep 30; done
[ -n "$D" ] || { echo "B_MME_SOURCE_MISSING"; exit 1; }
cd $R/artifacts/v7.5eval/wt/a81c4f6b || exit 97
$R/.venv/bin/python scripts/eval-official/policy_replay.py build-inputs --policy mme --rec $D/rec/BinFill_31_543100 --proxy-rec $D/rec/proxy --kind official --out $R/artifacts/v7.5eval/replay/inputs/B-mme.tmp 2>&1 | tee /dev/stderr | grep -q "^BUILD_INPUTS=PASS" || { echo "B_MME_BUILD_FAIL"; exit 1; }
mv $R/artifacts/v7.5eval/replay/inputs/B-mme.tmp $R/artifacts/v7.5eval/replay/inputs/B-mme
rsync -a $R/artifacts/v7.5eval/replay/inputs/B-mme /nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval/replay/inputs/ && echo "B_MME_READY $(date -Is)"
