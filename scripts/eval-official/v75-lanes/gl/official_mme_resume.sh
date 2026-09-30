#!/bin/bash
# 席位内：official_mme_resume.sh <run> <shard> <port>
# 续跑某官方分片的 MME 部分：用已提交的 run_official_mme.sh，SAVE_ROOT 沿用原目录（V75_RESUME=1，done_keys 跳过已有终态），
# 录制写新的节点目录，结束后暂存到 stage/<run>/mme/s<shard>-resume/ 并核对；旧分片的 GPU 独占模式事故后补跑（2026-09-30）
RUN=$1; SHARD=$2; PORT=$3
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval; WT=$N/wt/4c19c39a
NT=/tmp/v75-$RUN-s$SHARD-mmeresume-${SLURM_JOB_ID:-local}; mkdir -p "$NT"
AFF=$(python3 -c 'import os;print(sorted(os.sched_getaffinity(0))[-1])')
cd "$WT" || exit 97
echo "MME_RESUME_START run=$RUN shard=$SHARD host=$(hostname) $(date -Is)"
env MANIFEST=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v7-eval/eval-official-xhard0-192.jsonl SHARD=$SHARD PORT=$PORT RUN_TAG=v75-$RUN-s$SHARD-resume \
  SAVE_ROOT=$N/official/$RUN/mme/s$SHARD REC_ROOT=$NT/rec VIDEO_DIR=$NT/videos NODE_TMP=$NT V75_RESUME=1 V75_ENCODE_CPUS=$AFF \
  bash scripts/eval-official/official_observer/run_official_mme.sh
rc=$?
rows=$(python3 -c "import json,glob,sys;fs=glob.glob('$N/official/$RUN/mme/s$SHARD/*/*/*/episodes.jsonl');rs=[json.loads(l) for f in fs for l in open(f) if l.strip()];last={};[last.__setitem__((r['task'],r['source_episode']),r['status']) for r in rs];print(sum(1 for v in last.values() if v in ('success','fail','timeout')))")
DST=$N/stage/$RUN/mme/s$SHARD-resume; mkdir -p "$DST"
if rsync -rt "$NT/" "$DST/"; then n=$(rsync -rc --dry-run --out-format="%n" "$NT/" "$DST/" | { grep -v "/$" || true; } | wc -l); else n=err; fi
[ "$n" = 0 ] && rm -rf "${NT:?}" && st=yes || st=no
echo "MME_RESUME_DONE run=$RUN shard=$SHARD final_rows=$rows rc=$rc staged=$st"
[ "$st" = yes ] || exit 7
exit $rc
