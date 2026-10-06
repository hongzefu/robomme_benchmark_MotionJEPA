#!/usr/bin/env bash
# v7.5eval 官方重跑（SimpleMemVLA，加录制器）单片启动器：环境与参数逐项照抄旧官方
#   /nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA-official-xhard0/scripts/run_official_xhard0.sh
# 差别（方案 §2.5，均须写进留档）：
#   1. 用 official_observer/smvla_wrap.py 代替 ``-m robomme_sim.eval_success``（runpy 执行同一模块，外挂只读钩子）；
#      PYTHONPATH = 旧官方工作树 : 本目录 : 原 PYTHONPATH。
#   2. OUTDIR 必须是新目录（起前断言无 episodes*.jsonl），且只许落在白名单根下（R8）；REC_ROOT 为录制根；
#      V75_RESUME=1 只许续用标记 .v75-created 中清单 sha256 与分片都一致的目录；VIDEO_DIR=none 关闭录像（同历史）。
#   3. 始终带 --resume（与历史一致：旧 gl_run_official_xhard0.sh 每遍都传 --resume）；登录节点 3 遍重试由编排器负责。
#   4. 可选 NODE_TMP：OUTDIR／REC_ROOT 默认落在节点本地盘，跑完由调用方搬回。
# 用法：MANIFEST=<清单.jsonl> SHARD=<i/n> OUTDIR=<新目录> REC_ROOT=<新目录> [VIDEO_DIR=<目录>] [NODE_TMP=<目录>] \
#       [SMVLA_OFFICIAL_REPO=<旧官方工作树>] [V75_RESUME=1] [V75_ENCODE_CPUS=<编码核>] \
#       bash scripts/eval-official/official_observer/run_official_smvla.sh [额外参数，透传给 eval_success]
set -euo pipefail
OBS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${SMVLA_OFFICIAL_REPO:-/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA-official-xhard0}"
cd "$REPO"
# 本检出（git worktree）不带 venv 与权重：默认借主检出的
MAIN_REPO="${MAIN_REPO:-/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA}"
PYBIN="${PYBIN:-$MAIN_REPO/.venv-robomme/bin/python}"
CHECKPOINT="$(readlink -f "${CHECKPOINT:-$MAIN_REPO/checkpoints/simplememvla_robomme}")"
: "${MANIFEST:?}" "${SHARD:?}"
if [ -n "${NODE_TMP:-}" ]; then
  mkdir -p "$NODE_TMP"
  OUTDIR="${OUTDIR:-$NODE_TMP/out}"
  REC_ROOT="${REC_ROOT:-$NODE_TMP/rec}"
fi
: "${OUTDIR:?必须显式给新目录 OUTDIR（或 NODE_TMP）}" "${REC_ROOT:?必须显式给新目录 REC_ROOT（或 NODE_TMP）}"
OUTDIR="$(readlink -m "$OUTDIR")"; REC_ROOT="$(readlink -m "$REC_ROOT")"; MANIFEST="$(readlink -f "$MANIFEST")"
VIDEO_DIR="${VIDEO_DIR:-$OUTDIR/videos}"
# 与旧 gl_run_official_xhard0.sh 一致：VIDEO_DIR=none 关闭录像
if [ "$VIDEO_DIR" = none ]; then VIDEO_DIR=""; else VIDEO_DIR="$(readlink -m "$VIDEO_DIR")"; fi
V75_ENCODE_CPUS="${V75_ENCODE_CPUS:-$(python3 -c 'import os; print(max(os.sched_getaffinity(0)))')}"
python3 -c "
import os,sys
w=set()
for p in sys.argv[1].split(','):
    a,_,b=p.partition('-'); w.update(range(int(a),int(b or a)+1))
sys.exit(0 if w and w<=os.sched_getaffinity(0) else 1)" "$V75_ENCODE_CPUS" \
  || { echo "错误: V75_ENCODE_CPUS=$V75_ENCODE_CPUS 不在 CPU 亲和集合内"; echo "EXIT_CODE=1"; exit 1; }
export V75_ENCODE_CPUS
i="${SHARD%/*}"; n="${SHARD#*/}"
EPISODE_LOG="$OUTDIR/episodes-shard$(printf %02d "$i")of$(printf %02d "$n").jsonl"
NFS=/nfs/turbo/coe-chaijy-unreplicated/hongzefu
ALLOW=("$NFS/v75eval/" "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/v7.5eval/")
[ -n "${NODE_TMP:-}" ] && ALLOW+=("$(readlink -m "$NODE_TMP")/")
for d in "$OUTDIR" "$REC_ROOT" ${VIDEO_DIR:+"$VIDEO_DIR"}; do
  case "$d/" in
    "$NFS/v7-eval/"*|"$NFS/v7-eval-stage/"*|"$REPO/"*|"$MAIN_REPO/"*)
      echo "错误: 输出目录落在历史／官方目录下: $d"; echo "EXIT_CODE=1"; exit 1;;
  esac
  ok=0; for a in "${ALLOW[@]}"; do case "$d/" in "$a"*) ok=1;; esac; done
  [ "$ok" = 1 ] || { echo "错误: 输出目录不在白名单根下（${ALLOW[*]}）: $d"; echo "EXIT_CODE=1"; exit 1; }
done
MARK="manifest_sha256=$(sha256sum "$MANIFEST" | cut -c1-64) shard=$SHARD"
if [ "${V75_RESUME:-0}" = 1 ]; then
  if [ ! -f "$OUTDIR/.v75-created" ] || [ "$(cat "$OUTDIR/.v75-created")" != "$MARK" ]; then
    echo "错误: V75_RESUME=1 但 $OUTDIR/.v75-created 缺失或与本次清单／分片不符"; echo "EXIT_CODE=1"; exit 1
  fi
  echo "V75_RESUME: 续用本脚本建的 $OUTDIR（$MARK）"
else
  if [ -d "$OUTDIR" ] && [ -n "$(find "$OUTDIR" -name 'episodes*.jsonl' -print -quit 2>/dev/null)" ]; then
    echo "错误: OUTDIR 已有 episodes*.jsonl（必须新目录）: $OUTDIR"; echo "EXIT_CODE=1"; exit 1
  fi
  if [ -d "$REC_ROOT" ] && [ -n "$(ls -A "$REC_ROOT" 2>/dev/null)" ]; then
    echo "错误: REC_ROOT 非空（必须新目录）: $REC_ROOT"; echo "EXIT_CODE=1"; exit 1
  fi
fi
if [ -z "${VK_ICD_FILENAMES:-}" ]; then
  for cand in /usr/share/vulkan/icd.d/nvidia_icd.x86_64.json /usr/share/vulkan/icd.d/nvidia_icd.json; do
    [ -f "$cand" ] && { export VK_ICD_FILENAMES="$cand"; break; }
  done
fi
export __GLX_VENDOR_LIBRARY_NAME="${__GLX_VENDOR_LIBRARY_NAME:-nvidia}"
export MPLBACKEND=Agg MS_ASSET_DIR="${MS_ASSET_DIR:-$HOME/.maniskill}"
export PYTHONPATH="$REPO:$OBS_DIR:${PYTHONPATH:-}" PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
# 以下沿用官方 eval_robomme.sh 的环境设定
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}" PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/simplememvla/triton}"
export TORCHINDUCTOR_CACHE_DIR="${TORCHINDUCTOR_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/simplememvla/torchinductor}"
export REC_ROOT V75_DATA_ROOT="${V75_DATA_ROOT:-$REC_ROOT}"
mkdir -p "$TRITON_CACHE_DIR" "$TORCHINDUCTOR_CACHE_DIR" "$OUTDIR" "$REC_ROOT"
[ -f "$OUTDIR/.v75-created" ] || echo "$MARK" > "$OUTDIR/.v75-created"
unset __EGL_VENDOR_LIBRARY_DIRS SAPIEN_DISABLE_RAY_TRACING ROBOMME_GPU_RASTER XLA_FLAGS || true
REC_ROOT="$REC_ROOT/preflight" "$PYBIN" "$OBS_DIR/smvla_wrap.py" --v75-preflight \
  || { echo "错误: 录制器包装自检失败"; echo "EXIT_CODE=1"; exit 1; }
echo "XHARD0_PREFLIGHT host=$(hostname) repo=$REPO head=$(git -C "$REPO" rev-parse --short HEAD) shard=$SHARD manifest=$MANIFEST ckpt=$CHECKPOINT ckpt_config_sha256=$(sha256sum "$CHECKPOINT/config.json" | cut -c1-64) log=$EPISODE_LOG video_dir=${VIDEO_DIR:-<关闭>} observer=$OBS_DIR rec_root=$REC_ROOT"
nvidia-smi --query-gpu=index,name,compute_mode --format=csv,noheader || true
set +e
"$PYBIN" "$OBS_DIR/smvla_wrap.py" \
  --pretrained_checkpoint "$CHECKPOINT" \
  --dataset_split test \
  --group_size 1 \
  --execute_horizon "${EXECUTE_HORIZON:-16}" \
  --max_steps "${MAX_STEPS:-1300}" \
  --num_denoising_steps "${NUM_DENOISING_STEPS:-10}" \
  --eval_temperature "${EVAL_TEMPERATURE:-1.0}" \
  --max_subtask_tokens "${MAX_SUBTASK_TOKENS:-64}" \
  --compute_dtype "${COMPUTE_DTYPE:-bfloat16}" \
  --attn_implementation "${ATTN_IMPLEMENTATION:-sdpa}" \
  --num_gpus 1 \
  --episode_manifest "$MANIFEST" --shard "$SHARD" --episode_log "$EPISODE_LOG" \
  ${VIDEO_DIR:+--video_dir "$VIDEO_DIR"} \
  --resume "$@"
RC=$?
nrec=$(grep -c . "$REC_ROOT/recorder-index.jsonl" 2>/dev/null); nrec=${nrec:-0}
npass=$(grep -c '"RECORDER_VERIFY": "PASS"' "$REC_ROOT/recorder-index.jsonl" 2>/dev/null); npass=${npass:-0}
echo "OBSERVER_RECORDINGS episodes=$nrec verify_pass=$npass rec_root=$REC_ROOT"
[ -n "${NODE_TMP:-}" ] && echo "NODE_TMP_STAGED outdir=$OUTDIR rec_root=$REC_ROOT（由调用方搬回并核对 sha256）"
echo "EXIT_CODE=$RC"
exit "$RC"
