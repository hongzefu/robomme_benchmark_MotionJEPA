#!/bin/bash
# 2.2：旧官方原版 SimpleMemVLA 启动器（不带录制器）跑 1 局，输出新目录
set -u
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
O=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA-official-xhard0
[ -e $N/official/norec/smvla/episodes-shard00of01.jsonl ] && { echo "输出已存在，拒绝"; exit 1; }
mkdir -p $N/official/norec/smvla $N/official/norec/smvla-videos
cd $O || exit 97
echo "NOREC_START host=$(hostname) head=$(git rev-parse --short HEAD) $(date -Is)"
MANIFEST=$N/official/manifest-norec-1row.jsonl SHARD=0/1 OUTDIR=$N/official/norec/smvla VIDEO_DIR=$N/official/norec/smvla-videos \
  bash $O/scripts/run_official_xhard0.sh --resume
