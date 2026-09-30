#!/bin/bash
# 第 4 步 GL 车道（计算节点内）：replay-gl.sh <cond>；P6 已按用户同意并入 P5
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
WT=$N/wt/30257b46
COND=$1
cd $WT || exit 97
for f in /usr/share/vulkan/icd.d/nvidia_icd.x86_64.json /usr/share/vulkan/icd.d/nvidia_icd.json; do [ -f "$f" ] && { export VK_ICD_FILENAMES=$f; break; }; done
export MME_PY=$N/wt/2abf227d/third_party/mme-vla/.venv/bin/python SMVLA_PY=$N/venvs/smvla-env/bin/python BENCH_PY=$WT/.venv/bin/python CPUS=$(python3 -c 'import os;print(",".join(map(str,sorted(os.sched_getaffinity(0)))))')
export MME_CKPT=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/eval-out/mmevla-ckpt/perceptual-framesamp-modul/79999
rc_all=0
for P in ${POLICIES:-smvla mme}; do
  if [ "$P" = mme ]; then for w in $(seq 1 360); do [ -f $N/replay/inputs/B-mme/meta.json ] && break; sleep 30; done; [ -f $N/replay/inputs/B-mme/meta.json ] || { echo "B_MME_MISSING"; continue; }; fi
  echo "REPLAY_LANE_START cond=$COND policy=$P host=$(hostname) $(date -Is)"
  bash scripts/eval-official/run_policy_replay.sh $COND 0 $P $N/replay/inputs/A-$P $N/replay/inputs/B-$P $N/replay/$COND/$P; rc=$?
  echo "REPLAY_LANE_STEP cond=$COND policy=$P rc=$rc"; [ $rc = 0 ] || rc_all=$rc
done
exit $rc_all
