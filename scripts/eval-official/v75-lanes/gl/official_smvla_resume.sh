#!/bin/bash
# 席位内：official_smvla_resume.sh <run> <shard>
# 续跑某官方分片的 SimpleMemVLA 部分：用已提交的 run_official_smvla.sh，OUTDIR 沿用原目录（V75_RESUME=1，--resume 只重评非终态行），
# 照历史最多 3 次、遇 0/2 即停；录制写新的节点目录，结束后暂存到 stage/<run>/smvla/s<shard>-resume/ 并核对（2026-09-30 GPU 独占事故后补跑）
RUN=$1; SHARD=$2
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval; WT=$N/wt/4c19c39a
M=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v7-eval/eval-official-xhard0-192.jsonl
NT=/tmp/v75-$RUN-s$SHARD-smvlaresume-${SLURM_JOB_ID:-local}
AFF=$(python3 -c 'import os;print(sorted(os.sched_getaffinity(0))[-1])')
cd "$WT" || exit 97
echo "SMVLA_RESUME_START run=$RUN shard=$SHARD host=$(hostname) $(date -Is)"
rc=1
for a in 1 2 3; do
  mkdir -p "$NT"; RR=$NT/rec-a$a
  env MANIFEST=$M SHARD=$SHARD/10 OUTDIR=$N/official/$RUN/smvla/s$SHARD REC_ROOT=$RR VIDEO_DIR=$NT/videos-a$a NODE_TMP=$NT V75_RESUME=1 V75_ENCODE_CPUS=$AFF \
    bash scripts/eval-official/official_observer/run_official_smvla.sh; rc=$?
  echo "SMVLA_RESUME_ATTEMPT $a rc=$rc"; [ $rc = 0 ] || [ $rc = 2 ] && break
done
final=$(python3 -c "import json,glob;fs=glob.glob('$N/official/$RUN/smvla/s$SHARD/episodes-shard*.jsonl');last={};[last.__setitem__((r['task'],r['source_episode']),r['status']) for f in fs for r in (json.loads(l) for l in open(f) if l.strip())];print(sum(1 for v in last.values() if v in ('success','fail','timeout')))")
DST=$N/stage/$RUN/smvla/s$SHARD-resume; mkdir -p "$DST"
if rsync -rt "$NT/" "$DST/"; then n=$(rsync -rc --dry-run --out-format="%n" "$NT/" "$DST/" | { grep -v "/$" || true; } | wc -l); else n=err; fi
[ "$n" = 0 ] && rm -rf "${NT:?}" && st=yes || st=no
echo "SMVLA_RESUME_DONE run=$RUN shard=$SHARD final_rows=$final rc=$rc staged=$st"
[ "$st" = yes ] || exit 7
exit $rc
