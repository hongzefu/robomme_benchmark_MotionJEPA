#!/usr/bin/env bash
# Astra 新侧启动器（1003-oracle-subgoal-groundsg-eval-plan.md 第二部分 1.5，S5）。
# 环境变量与 VLA 启动命令逐项照抄 Astra 的 examples/champ/run.sh，只把 PYTHONPATH 的环境源一段
# （原为 Astra 嵌套的 third_party/robomme_benchmark/src）换成本仓库 src，其余三段语义不变；
# 另设 NO_PROXY；起跑前打印 robomme_hard.__file__ 与 robomme.__file__；端口探测与 trap 清理；
# 不加无进展看门狗（Astra 请求之间本来就有 20 秒间隔与长退避，保持官方行为）。
#
# 第二阶段（1005-eval-video-phase2-all-models-rerun-plan.md 第二部分一节 S3）：
# - 费用硬上限：必须先起 astra_cost_guard.py --cap 5（--interval 2），把它的 --state 文件经 ASTRA_GUARD_STATE 传进来；
#   check 核对守卫心跳新鲜，run 里每次规划请求发送前同步预留（astra_hard_runner.py GuardedResponsesClient）。
#   局清单最多 2 局（R6），runner 另在守卫预留文件里跨 RUN 登记局数。
# - 解释器显式设：BENCH_PY（默认 SIM_PYTHON）、TOOL_PY（默认 BENCH_PY），供席位函数库与验收脚本使用。
# - source seat_media_lib.sh（S2b；路径可由 SEAT_MEDIA_LIB 覆盖）：source 前后 MAX_STEPS、trap、shell 选项必须不变，
#   且须提供 render_official_dir 与 transcode_episode_dir，否则 RUN_BLOCKED（退出码 3）。
# - 每局收尾显式三步：render_official_dir <局目录> → transcode_episode_dir <局目录>（重绘失败则加 --keep-raw、
#   写 official-render.failed，原始帧保留）→ official_media_check.py（路径可由 OFFICIAL_MEDIA_CHECK 覆盖）。
#   局目录 = <RUN>/results/<task>/ep<NNN>/<key>.a1（轨迹、arrays.npz、原始帧同目录）。
#   runner 退出后（无论成败）逐局收尾；中断后可用 --finish 对已有 RUN 重入收尾。
#
# 用法：
#   VLA_PYTHON=… SIM_PYTHON=… VLA_CHECKPOINT=…/symbolic-grounded-subgoal/79999 \
#   MONITOR_BASE=… MONITOR_ADAPTER=… MAX_STEPS=1300 OPENAI_API_KEY=… ASTRA_GUARD_STATE=… \
#   [VLA_GPU=0 MONITOR_GPU=1 PORT=18762 ASTRA_ROOT=… BENCH_PY=… TOOL_PY=…] \
#   bash scripts/eval-official/run_astra.sh CASES.json <根>/group_0/<新 RUN 目录>
#   SIM_PYTHON=… [BENCH_PY=… TOOL_PY=…] bash scripts/eval-official/run_astra.sh --finish <已有 RUN 目录>
# CASES.json 由 astra_hard_runner.py prepare 生成（dataset 为 test-hard0 或 test-hard）。
# RUN 目录的上一层必须叫 group_0 或 group_1：STOP.json 停机口（费用守卫写、Astra 读）就在那一层。
# 密钥只从调用者环境变量 OPENAI_API_KEY 读；本脚本不读任何密钥文件、不回显密钥。
set -euo pipefail
REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
RUNNER="$REPO/scripts/eval-official/astra_hard_runner.py"

tool_py() { echo "${TOOL_PY:-$BENCH_PY}"; }

# source 席位函数库：前后 MAX_STEPS、trap、shell 选项不变，且两个收尾函数都在；否则返回 3。
source_media_lib() {
  local lib="${SEAT_MEDIA_LIB:-$REPO/scripts/eval-official/seat_media_lib.sh}"
  local steps_before="${MAX_STEPS-<unset>}" trap_before trap_after opts_before opts_after fn
  if [[ ! -f "$lib" ]]; then
    echo "RUN_BLOCKED reason=missing_dependency missing=S2b file=$lib" >&2
    return 3
  fi
  trap_before="$(trap -p)"
  opts_before="$(set +o)"
  # shellcheck source=/dev/null
  source "$lib"
  trap_after="$(trap -p)"
  opts_after="$(set +o)"
  if [[ "${MAX_STEPS-<unset>}" != "$steps_before" ]]; then
    echo "RUN_BLOCKED reason=media_lib_side_effect what=MAX_STEPS before=$steps_before after=${MAX_STEPS-<unset>}" >&2
    return 3
  fi
  if [[ "$trap_after" != "$trap_before" ]]; then
    echo "RUN_BLOCKED reason=media_lib_side_effect what=trap" >&2
    return 3
  fi
  if [[ "$opts_after" != "$opts_before" ]]; then
    echo "RUN_BLOCKED reason=media_lib_side_effect what=shell_options" >&2
    return 3
  fi
  for fn in render_official_dir transcode_episode_dir; do
    if ! declare -F "$fn" >/dev/null; then
      echo "RUN_BLOCKED reason=missing_dependency missing=S2b function=$fn lib=$lib" >&2
      return 3
    fi
  done
  echo "ASTRA_MEDIA_LIB=OK lib=$lib max_steps=${MAX_STEPS-<unset>} traps_unchanged=1"
}

# 本局官方视频验收：runner 写本局身份清单行与账本行，再调 official_media_check.py（S2b）。
astra_media_check() {  # $1 = 局目录 <key>.a<N>；$2 = RUN
  local d="$1" run="$2" name key out check
  check="${OFFICIAL_MEDIA_CHECK:-$REPO/scripts/eval-official/official_media_check.py}"
  name="$(basename -- "$d")"; key="${name%.a*}"
  out="$run/official-media"
  mkdir -p -- "$out"
  "$(tool_py)" "$RUNNER" media-inputs --episode-dir "$d" \
    --manifest "$out/$key.manifest.jsonl" --ledger "$out/$key.ledger.jsonl" || return $?
  "$(tool_py)" "$check" --manifest "$out/$key.manifest.jsonl" --ledger "$out/$key.ledger.jsonl" \
    --root "$(dirname -- "$d")" --out "$out/$key.official-media.jsonl"
}

# 一局收尾（显式三步）：重绘官方视频 → 转码普通视频（重绘失败则保留原始帧）→ 官方视频验收。
finish_episode() {  # $1 = 局目录 <key>.a<N>；$2 = RUN
  local d="$1" run="$2" rrc=0 trc=0 mrc=0
  if [[ ! -f "$d/trace.jsonl" ]]; then
    echo "ASTRA_FINISH=SKIP dir=$d reason=no_trace"
    return 0
  fi
  render_official_dir "$d" || rrc=$?
  if (( rrc == 0 )); then
    rm -f -- "$d/official-render.failed"
    transcode_episode_dir "$d" || trc=$?
  else
    echo "rc=$rrc time=$(date +%s)" > "$d/official-render.failed"
    transcode_episode_dir "$d" --keep-raw || trc=$?
  fi
  astra_media_check "$d" "$run" || mrc=$?
  echo "ASTRA_FINISH dir=$d render_rc=$rrc transcode_rc=$trc media_check_rc=$mrc"
  (( rrc == 0 && trc == 0 && mrc == 0 ))
}

finish_run() {  # $1 = RUN；逐局收尾，打印汇总行；任一局失败返回 5
  local run="$1" d total=0 fail=0
  while IFS= read -r -d '' d; do
    total=$((total + 1))
    finish_episode "$d" "$run" || fail=$((fail + 1))
  done < <(find "$run/results" -mindepth 3 -maxdepth 3 -type d -name '*.a[0-9]*' -print0 2>/dev/null | sort -z)
  echo "ASTRA_FINISH_SUMMARY run=$run total=$total fail=$fail"
  (( fail == 0 )) || return 5
}

if [[ "${1:-}" == "--finish" ]]; then
  if [[ $# != 2 ]]; then
    echo 'Usage: bash scripts/eval-official/run_astra.sh --finish <existing RUN directory>' >&2
    exit 2
  fi
  : "${SIM_PYTHON:?Set SIM_PYTHON to the simulator/monitor environment Python}"
  BENCH_PY="${BENCH_PY:-$SIM_PYTHON}"
  TOOL_PY="${TOOL_PY:-$BENCH_PY}"
  export BENCH_PY TOOL_PY
  [[ -d "$2/results" ]] || { echo "RUN_BLOCKED reason=no_results run=$2" >&2; exit 2; }
  source_media_lib || exit $?
  frc=0
  finish_run "$2" || frc=$?
  exit "$frc"
fi

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
# 费用守卫（--cap 5）必须先起：它的状态文件给 check 核心跳、给 run 做发送前同步预留
: "${ASTRA_GUARD_STATE:?Start astra_cost_guard.py --cap 5 first and set ASTRA_GUARD_STATE to its --state file}"
# 解释器显式设（席位函数库与验收脚本用 TOOL_PY，缺省回落 BENCH_PY）
BENCH_PY="${BENCH_PY:-$SIM_PYTHON}"
TOOL_PY="${TOOL_PY:-$BENCH_PY}"
export BENCH_PY TOOL_PY
# 收尾函数库先 source（缺即在起任何服务之前 RUN_BLOCKED）；MAX_STEPS 与 trap 必须不被它改动
source_media_lib || exit $?
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
# 起跑前核对（不加载模型、不联网）：局清单与身份（≤2 局）、数据集与步数配对、费用守卫心跳、validate_checkpoints、
# 端口可绑定；打印 robomme_hard.__file__ 与 robomme.__file__（必须都在本仓库 src 下）
"$SIM_PYTHON" "$RUNNER" check --cases "$CASES" --vla-checkpoint "$VLA_CHECKPOINT" \
  --monitor-adapter "$MONITOR_ADAPTER" --max-steps "$MAX_STEPS" --port "$PORT" --astra-root "$ASTRA" \
  --guard-state "$ASTRA_GUARD_STATE"
mkdir -p -- "$(dirname -- "$RUN")"
mkdir -- "$RUN"
cp -- "$CASES" "$RUN/cases.json"
echo "RUN_INPUTS bench_py=$BENCH_PY tool_py=$TOOL_PY sim_python=$SIM_PYTHON vla_python=$VLA_PYTHON guard_state=$ASTRA_GUARD_STATE" \
  | tee "$RUN/run-inputs.txt"
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
# VLA 进程不需要规划接口的密钥（照抄上游 run.sh 同位置注释，译为中文）。
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
  --max-steps "$MAX_STEPS" --astra-root "$ASTRA" --guard-state "$ASTRA_GUARD_STATE" \
  > "$RUN/runner.log" 2>&1 || rc=$?
"$SIM_PYTHON" "$RUNNER" summarize --cases "$RUN/cases.json" \
  --results "$RUN/results" --output "$RUN/summary.json" || true
# VLA 不再需要：先停掉再做 CPU 收尾（重绘、转码、验收），不占卡
cleanup
frc=0
finish_run "$RUN" || frc=$?
echo "ASTRA_RUN_DONE run=$RUN rc=$rc finish_rc=$frc"
(( rc != 0 )) || rc=$frc
exit "$rc"
