#!/bin/bash
# 容差标定（集群侧）：先跑本 job 那 12 局单 worker，再跑本片 144 局的 4 worker 分片
set -o pipefail
K="$1"
GL=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
H=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/slurm-holds
SEG=$(sed -n "${K}p" $H/tvo_segments.txt)
cd $GL
O1=$GL/artifacts/train-parity/gl-tvo-16x3/shard$K; mkdir -p $O1
PYTHONUNBUFFERED=1 .venv/bin/python scripts/train_split_parity.py run --sequence "$SEG" --paths B --workers 1 --gpus 0 \
  --official-root $GL/artifacts/train-parity/gl-5d/shard1/official-src --output $O1 2>&1 | tee $O1/run.log
echo "EXIT_CODE=$?" >> $O1/run.log
O2=$GL/artifacts/train-parity/gl-tvo-w4/shard$K; mkdir -p $O2
PYTHONUNBUFFERED=1 .venv/bin/python scripts/train_split_parity.py run --shard $K/4 --paths B --workers 4 --gpus 0 \
  --official-root $GL/artifacts/train-parity/gl-5d/shard1/official-src --output $O2 2>&1 | tee $O2/run.log
echo "EXIT_CODE=$?" >> $O2/run.log
