#!/usr/bin/env bash
# Astra 新侧启动器（1003-oracle-subgoal-groundsg-eval-plan.md 第二部分 1.5，S5）。
# 环境变量与 VLA 启动命令逐项照抄 Astra 的 examples/champ/run.sh，只把 PYTHONPATH 的环境源一段
# （原为 Astra 嵌套的 third_party/robomme_benchmark/src）换成本仓库 src，其余三段语义不变；
# 另设 NO_PROXY；起跑前打印 robomme_hard.__file__ 与 robomme.__file__；端口探测与 trap 清理；
# 不加无进展看门狗（Astra 请求之间本来就有 20 秒间隔与长退避，保持官方行为）。
#
# 用法：
#   VLA_PYTHON=… SIM_PYTHON=… VLA_CHECKPOINT=…/symbolic-grounded-subgoal/79999 \
#   MONITOR_BASE=… MONITOR_ADAPTER=… MAX_STEPS=1300 OPENAI_API_KEY=… \
#   [VLA_GPU=0 MONITOR_GPU=1 PORT=18762 ASTRA_ROOT=…] \
#   bash scripts/eval-official/run_astra.sh CASES.json <根>/group_0/<新 RUN 目录>
# CASES.json 由 astra_hard_runner.py prepare 生成（dataset 为 test-hard0 或 test-hard）。
# RUN 目录的上一层必须叫 group_0 或 group_1：STOP.json 停机口（费用守卫写、Astra 读）就在那一层。
# 密钥只从调用者环境变量 OPENAI_API_KEY 读；本脚本不读任何密钥文件、不回显密钥。
set -euo pipefail
if [[ $# != 2 ]]; then
  echo 'Usage: bash scripts/eval-official/run_astra.sh CASES.json <root>/group_0/NEW_RUN_DIRECTORY' >&2
  exit 2
fi
: "${VLA_PYTHON:?Set VLA_PYTHON to the VLA environment Python}"
: "${SIM_PYTHON:?Set SIM_PYTHON to the simulator/monitor environment Python}"
: "${VLA_CHECKPOINT:?Set VLA_CHECKPOINT to symbolic-grounded-subgoal/79999}"
: "${MONITOR_BASE:?Set MONITOR_BASE to the downloaded Qwen3-VL-4B-Instruct directory}"
: "${MONITOR_ADAPTER:?Set MONITOR_ADAPTER to the released checkpoint-2246 directory}"
: "${MAX_STEPS:?Set MAX_STEPS from the launch command (test-hard0 1300, test-hard 1600)}"
: "${OPENAI_API_KEY:?Supply your own API credential through OPENAI_API_KEY}"
REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ -n "${ASTRA_ROOT:-}" ]]; then
  ASTRA=$ASTRA_ROOT
elif [[ -n "${SGEVAL_THIRD_PARTY:-}" ]]; then
  ASTRA="$SGEVAL_THIRD_PARTY/Astra-on-RoboMME"
else
  ASTRA="$REPO/third_party/Astra-on-RoboMME"
fi
ASTRA=$(cd -- "$ASTRA" && pwd)
CASES=$("$SIM_PYTHON" -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$1")
RUN=$("$SIM_PYTHON" -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' "$2")
VLA_GPU=${VLA_GPU:-0}
MONITOR_GPU=${MONITOR_GPU:-1}
PORT=${PORT:-18762}
[[ "$VLA_GPU" != "$MONITOR_GPU" ]] || { echo 'Use distinct GPUs for VLA and monitor' >&2; exit 2; }
[[ ! -e "$RUN" ]] || { echo 'Use a new run directory to preserve existing evidence' >&2; exit 2; }
GROUP=$(basename -- "$(dirname -- "$RUN")")
[[ "$GROUP" == group_0 || "$GROUP" == group_1 ]] || {
  echo "RUN_BLOCKED reason=layout parent of RUN must be group_0 or group_1 (got $GROUP)" >&2; exit 2; }
# 只换环境源一段：Astra 的 champ、openpi(src)、openpi-client 三段照抄，第四段改为本仓库 src
export PYTHONPATH="$ASTRA/examples/champ:$ASTRA/src:$ASTRA/packages/openpi-client/src:$REPO/src"
export OPENPI_DATA_HOME=${OPENPI_DATA_HOME:-"$HOME/.cache/openpi"}
export HF_HOME=${HF_HOME:-"$HOME/.cache/huggingface"}
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false USE_HF=1 IMAGE_MAX_TOKEN_NUM=128
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
# 本机与 GL 计算节点都可能有 HTTP 代理：VLA websocket 只连本机回环，不经代理
export NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost
RUNNER="$REPO/scripts/eval-official/astra_hard_runner.py"
# 起跑前核对（不加载模型、不联网）：局清单与身份、数据集与步数配对、validate_checkpoints、端口可绑定；
# 打印 robomme_hard.__file__ 与 robomme.__file__（必须都在本仓库 src 下）
"$SIM_PYTHON" "$RUNNER" check --cases "$CASES" --vla-checkpoint "$VLA_CHECKPOINT" \
  --monitor-adapter "$MONITOR_ADAPTER" --max-steps "$MAX_STEPS" --port "$PORT" --astra-root "$ASTRA"
mkdir -p -- "$(dirname -- "$RUN")"
mkdir -- "$RUN"
cp -- "$CASES" "$RUN/cases.json"
for component in vla simulator; do
  if [[ "$component" == vla ]]; then interpreter="$VLA_PYTHON"; else interpreter="$SIM_PYTHON"; fi
  "$interpreter" - > "$RUN/$component-packages.txt" <<'PYENV'
from importlib.metadata import distributions
print('\n'.join(sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions())))
PYENV
done
git -C "$REPO" rev-parse HEAD > "$RUN/repository-commit.txt"
git -C "$REPO" diff HEAD > "$RUN/local-changes.patch"
git -C "$REPO" submodule status > "$RUN/submodules.txt" || true
git -C "$ASTRA" rev-parse HEAD > "$RUN/astra-commit.txt" || true
cd "$ASTRA"
# The VLA process does not need the planner API credential.
env -u OPENAI_API_KEY CUDA_VISIBLE_DEVICES="$VLA_GPU" "$VLA_PYTHON" scripts/serve_policy.py \
  --port="$PORT" --seed=42 policy:checkpoint --policy.config=mme_vla_suite \
  --policy.dir="$VLA_CHECKPOINT" > "$RUN/vla.log" 2>&1 &
vla_pid=$!
cleanup() {
  if kill -0 "$vla_pid" 2>/dev/null; then
    kill "$vla_pid" 2>/dev/null || true
    for _ in $(seq 1 20); do kill -0 "$vla_pid" 2>/dev/null || break; sleep 0.5; done
    kill -9 "$vla_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$SIM_PYTHON" - "$vla_pid" "$PORT" <<'PY'
import os,socket,sys,time
for _ in range(180):
    os.kill(int(sys.argv[1]),0)
    try:
        with socket.create_connection(('127.0.0.1',int(sys.argv[2])),timeout=1):break
    except OSError:time.sleep(5)
else:raise TimeoutError('VLA startup exceeded 15 minutes')
PY
rc=0
CUDA_VISIBLE_DEVICES="$MONITOR_GPU" "$SIM_PYTHON" -u "$RUNNER" run \
  --cases "$RUN/cases.json" --output "$RUN/results" --spool "$RUN/planner_calls" \
  --port "$PORT" --vla-checkpoint "$VLA_CHECKPOINT" \
  --monitor-base "$MONITOR_BASE" --monitor-adapter "$MONITOR_ADAPTER" \
  --max-steps "$MAX_STEPS" --astra-root "$ASTRA" \
  > "$RUN/runner.log" 2>&1 || rc=$?
"$SIM_PYTHON" "$RUNNER" summarize --cases "$RUN/cases.json" \
  --results "$RUN/results" --output "$RUN/summary.json" || true
echo "ASTRA_RUN_DONE run=$RUN rc=$rc"
exit "$rc"
