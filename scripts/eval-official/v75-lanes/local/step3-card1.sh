#!/bin/bash
# 第 3 步：真席位脚本跑通（本机卡 1），每策略 1 局；经 flock 与卡 1 其他 GPU 任务串行
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
WT=$R/artifacts/v7.5eval/wt/2abf227d
cd $WT || exit 97
export SMVLA_PY=$R/artifacts/v7.5eval/venvs/smvla-env/bin/python MME_PY=$R/third_party/mme-vla/.venv/bin/python BENCH_PY=$R/.venv/bin/python
exec flock /home/hongzefu/.claude/jobs/6f127313/tmp/gpu1.lock bash scripts/eval-official/run_seat.sh --seat L1 --seat-idx 9 --gpu 1 --cpus 4-7 \
  --cond S3 --out $R/artifacts/v7.5eval/newiface/step3 --identities $R/artifacts/v7.5eval/identities-step3-1.json \
  --policies smvla,mme --limit 1 \
  --mme-ckpt /data/hongzefu/robomme_policy_learning_MotionJEPA/v1-store/models/official-mme-vla/perceptual-framesamp-modul/79999 \
  --smvla-ckpt $R/artifacts/v7.5eval/ckpt/simplememvla_robomme
