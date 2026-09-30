#!/usr/bin/env bash
# v7.5eval 第 4 步驱动：一张卡上、一个策略的开环回放全套（0929-v7.5eval-restructure-plan.md §3.2 第 4 步）。
#
# 用法：run_policy_replay.sh <cond> <gpu> <policy:mme|smvla> <inputsA> <inputsB> <outroot>
#   inputsA / inputsB 为 policy_replay.py build-inputs 产出的输入目录（A = 第 3 步那一局；B = 官方重跑一首片一局）。
# 可选环境变量：BENCH_PY MME_PY SMVLA_PY MME_CKPT SMVLA_CKPT CPUS（taskset 核表）PORT（默认 18900+10×gpu）
#   REPEATS（同 server 回放次数，默认 3）RESTARTS（重启次数，默认 3）DET_STATES（默认 "off on"）
#   CACHE_TEST（mme 编译缓存三态，默认 on）
#   V75_GPU_LOCK：同卡测速隔离锁。本机（无 SLURM_JOB_ID）必加锁，缺省 /home/hongzefu/.claude/jobs/6f127313/tmp/gpu<N>.lock；
#     GL 作业内（有 SLURM_JOB_ID）整卡归本作业，不加锁。外层已持有该锁时设 V75_GPU_LOCK_HELD=1（同一文件再 flock 会自锁死）。
#   每次起 server 前与每次回放前查该卡计算进程，有外来进程打印 WARN_GPU_BUSY 并记入 gpu-busy.jsonl／report.json（不阻塞）。
# 开跑时清掉 <outroot> 下旧的 compare/、det-*/、report.json 等；本次运行编号 RUN_ID 写进每份产物，report 只汇总本次。
#
# 每种确定性状态（off / on）各起 6 次 server，server 起法与 run_seat.sh::start_server 逐项相同：
#   S_same：A×REPEATS、B×REPEATS（同一 server 重复）；
#   S_r1..S_rN：各一次 A（新 server 首次）再一次 B（B 在 A 之后）——每次重启回放 1 遍；
#   S_aba：A→B→A；S_bab：B→A→B（常驻顺序，与各自独立启动比）。
# mme 另测编译缓存三态（det off 下）：关闭（即 S_same 的 A rep0）、冷缓存（空目录）、重启后命中（文件数不变且 >0，日志查 cache hit）。
# 每次回放先 reset；timing.json 记 rng_restored（MME：reset 已执行；SMVLA：server 回 rng_matches_ref）。
# 输出：<outroot>/det-<off|on>/<组>/<输入>/rep<k>/{actions.npz,timing.json}、<outroot>/compare/*.json、
#       <outroot>/report.json；判定行 POLICY_REPLAY=INFO …、DET_RULE=INFO …、POLICY_REPLAY_DONE …，末行 EXIT_CODE=<rc>。
set -uo pipefail

if [[ $# -ne 6 ]]; then
  echo "用法：$0 <cond> <gpu> <mme|smvla> <inputsA> <inputsB> <outroot>" >&2; exit 2
fi
COND="$1" ; GPU="$2" ; POL="$3" ; INA="$4" ; INB="$5" ; OUT="$6"
[[ "$POL" == "mme" || "$POL" == "smvla" ]] || { echo "未知策略 $POL" >&2; exit 2; }

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCH_PY="${BENCH_PY:-$REPO/.venv/bin/python}"
MME_PY="${MME_PY:-$REPO/third_party/mme-vla/.venv/bin/python}"
SMVLA_PY="${SMVLA_PY:-$REPO/artifacts/v7.5eval/venvs/smvla-env/bin/python}"
MME_CKPT="${MME_CKPT:-/data/hongzefu/robomme_policy_learning_MotionJEPA/v1-store/models/official-mme-vla/perceptual-framesamp-modul/79999}"
SMVLA_CKPT="${SMVLA_CKPT:-/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA/checkpoints/simplememvla_robomme}"
MME_YAML_EXPECT="perceptual-framesamp-modul.yaml"
PORT="${PORT:-$((18900 + 10 * GPU))}"
REPEATS="${REPEATS:-3}" ; RESTARTS="${RESTARTS:-3}" ; DET_STATES="${DET_STATES:-off on}" ; CACHE_TEST="${CACHE_TEST:-on}"
PHASES="${PHASES:-same restart order}"  # 冒烟时可只给 "same"；inputsB 传 "-" 表示只回放 A
READY_TIMEOUT=1200
PR="$REPO/scripts/eval-official/policy_replay.py"

mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
INA="$(cd "$INA" && pwd)" ; [[ "$INB" != "-" ]] && INB="$(cd "$INB" && pwd)"
LOG="$OUT/run-policy-replay-$POL.log"
mkdir -p "$OUT/compare" "$OUT/server-logs"

TASKSET=()
[[ -n "${CPUS:-}" ]] && TASKSET=(taskset -c "$CPUS")
# 两个 server 分支都先清掉会影响确定性／编译缓存的变量，再只设本阶段要的（-u 须在赋值之前）
CLEAN_ENV=(-u XLA_FLAGS -u JAX_COMPILATION_CACHE_DIR -u JAX_PERSISTENT_CACHE_MIN_ENTRY_SIZE_BYTES
           -u JAX_PERSISTENT_CACHE_MIN_COMPILE_TIME_SECS -u CUBLAS_WORKSPACE_CONFIG -u JAX_DEBUG_LOG_MODULES)
NOPROXY_ENV=(-u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY
             NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost)
SERVER_PID="" ; SLOG=""
RUN_ID="$(date +%Y%m%dT%H%M%S)-$$"

ts() { date +%s; }
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

stop_server() {
  [[ -z "$SERVER_PID" ]] && return 0
  kill -TERM -- "-$SERVER_PID" 2>/dev/null || kill -TERM "$SERVER_PID" 2>/dev/null
  local i
  for i in $(seq 1 60); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 1; done
  kill -KILL -- "-$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
  for i in $(seq 1 30); do  # 核实显存已释放
    nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -qw "$SERVER_PID" || break
    sleep 1
  done
  for i in $(seq 1 30); do port_busy "$PORT" || break; sleep 1; done
  echo "SERVER_STOPPED pid=$SERVER_PID"
  SERVER_PID=""
}
trap stop_server EXIT

gpu_slug() { nvidia-smi --query-gpu=name --format=csv,noheader -i "$GPU" 2>/dev/null | head -1 | tr ' /' '__'; }

# 同卡隔离核对：$1 = 时机。本脚本的 server（会话号 = SERVER_PID）之外的计算进程一律算外来。
gpu_busy_check() {
  local where="$1" pid mem sid foreign=()
  while IFS=', ' read -r pid mem; do
    [[ -z "$pid" ]] && continue
    sid="$(ps -o sid= -p "$pid" 2>/dev/null | tr -d ' ')"
    [[ -n "$SERVER_PID" && ( "$pid" == "$SERVER_PID" || "$sid" == "$SERVER_PID" ) ]] && continue
    foreign+=("$pid:$mem")
  done < <(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits -i "$GPU" 2>/dev/null)
  if (( ${#foreign[@]} > 0 )); then
    echo "WARN_GPU_BUSY gpu=$GPU where=$where foreign=${foreign[*]}"
    printf '{"run_id": "%s", "gpu": "%s", "where": "%s", "foreign": "%s", "t": %d}\n' \
        "$RUN_ID" "$GPU" "$where" "${foreign[*]}" "$(ts)" >> "$OUT/gpu-busy.jsonl"
  fi
}

# $1 = det(on|off)；$2 = 名字（日志用）；$3 = 编译缓存目录（空 = 关闭）
start_server() {
  local det="$1" name="$2" cache="${3:-}" extra=()
  SLOG="$OUT/server-logs/$POL-det$det-$name-$(ts).log"
  if port_busy "$PORT"; then echo "RUN_BLOCKED reason=port_busy port=$PORT"; return 3; fi
  gpu_busy_check "start:$det/$name"
  if [[ "$POL" == "mme" ]]; then
    extra=(XLA_PYTHON_CLIENT_MEM_FRACTION=0.75 GLIBC_TUNABLES=glibc.rtld.optional_static_tls=16384 UV_LINK_MODE=copy
           VIRTUAL_ENV="$REPO/third_party/mme-vla/.venv")
    [[ -n "$cache" ]] && extra+=(JAX_COMPILATION_CACHE_DIR="$cache"
                                 JAX_DEBUG_LOG_MODULES="jax._src.compiler,jax._src.compilation_cache")
    [[ "$det" == "on" ]] && extra+=(XLA_FLAGS="--xla_gpu_deterministic_ops=true --xla_gpu_autotune_level=0")
    ( cd "$REPO/third_party/mme-vla" && exec setsid env "${CLEAN_ENV[@]}" "${NOPROXY_ENV[@]}" "${extra[@]}" PYTHONUNBUFFERED=1 \
        CUDA_VISIBLE_DEVICES="$GPU" "${TASKSET[@]}" "$MME_PY" scripts/serve_policy.py --seed=7 --port="$PORT" \
        policy:checkpoint --policy.config=mme_vla_suite --policy.dir="$MME_CKPT" ) >"$SLOG" 2>&1 &
  else
    local detarg=()
    [[ "$det" == "on" ]] && detarg=(--det) && extra=(CUBLAS_WORKSPACE_CONFIG=:4096:8)
    ( cd "$REPO" && exec setsid env "${CLEAN_ENV[@]}" "${NOPROXY_ENV[@]}" "${extra[@]}" PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 \
        TOKENIZERS_PARALLELISM=false PYTHONUTF8=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MPLBACKEND=Agg \
        CUDA_VISIBLE_DEVICES="$GPU" "${TASKSET[@]}" "$SMVLA_PY" scripts/eval-official/smvla_server.py serve \
        --port "$PORT" --ckpt "$SMVLA_CKPT" --warmup "${detarg[@]}" \
        --metadata_out "$OUT/server-logs/metadata-det$det-$name-$RUN_ID.json" ) >"$SLOG" 2>&1 &
  fi
  SERVER_PID=$!
  local t0; t0=$(ts)
  echo "SERVER_START policy=$POL det=$det name=$name port=$PORT pid=$SERVER_PID cache=${cache:-off} log=$SLOG"
  while true; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "SERVER_DIED_BEFORE_READY policy=$POL name=$name"; tail -n 20 "$SLOG"; SERVER_PID=""; return 4
    fi
    port_busy "$PORT" && break
    if (( $(ts) - t0 > READY_TIMEOUT )); then echo "SERVER_READY_TIMEOUT policy=$POL"; stop_server; return 4; fi
    sleep 2
  done
  echo "SERVER_READY policy=$POL det=$det name=$name ready_s=$(( $(ts) - t0 ))"
  if [[ "$POL" == "mme" ]] && ! grep -q "history_config='$MME_YAML_EXPECT'" "$SLOG"; then
    echo "RUN_BLOCKED reason=server_config（日志里没有 history_config='$MME_YAML_EXPECT'）"; stop_server; return 3
  fi
  if [[ "$POL" == "smvla" ]]; then
    grep -E "SMVLA_WARMUP|SMVLA_DET" "$SLOG" | tail -n 2
    grep -q "rng_restored=True" "$SLOG" || echo "RNG_WARN policy=smvla name=$name 预热后随机状态未恢复（见 $SLOG）"
  fi
  return 0
}

# $1 = det；$2 = 组；$3 = A|B；$4 = 次数；$5 = 起始序号
replay() {
  local det="$1" grp="$2" which="$3" n="$4" start="${5:-0}" inp
  [[ "$which" == "A" ]] && inp="$INA" || inp="$INB"
  [[ "$inp" == "-" ]] && { echo "REPLAY_SKIP $grp/$which（未给 inputsB）"; return 0; }
  gpu_busy_check "replay:$det/$grp/$which"
  env "${NOPROXY_ENV[@]}" "$BENCH_PY" "$PR" replay --policy "$POL" --inputs "$inp" --port "$PORT" \
      --repeats "$n" --start-index "$start" --tag "det-$det/$grp/$which" --label "$grp/$which" --out "$OUT" --force \
      --run-id "$RUN_ID"
}

# $1 = det；$2 = mode；$3 = a 目录（相对 OUT）；$4 = b 目录；$5 = 标签
cmpr() {
  local det="$1" mode="$2" a="$3" b="$4" label="$5"
  if [[ ! -f "$OUT/$a/actions.npz" || ! -f "$OUT/$b/actions.npz" ]]; then
    echo "COMPARE_SKIP label=$label 缺 $a 或 $b"; return 0
  fi
  "$BENCH_PY" "$PR" compare --a "$OUT/$a" --b "$OUT/$b" --kind replay --cond "$COND" --policy "$POL" --mode "$mode" \
      --det "$det" --label "$label" --run-id "$RUN_ID" --out "$OUT/compare/det$det-$(echo "$label" | tr '/ ' '__').json"
}

run_det_state() {  # $1 = det
  local det="$1" i rc d="det-$1"
  # S_same：同一 server 重复回放
  if [[ " $PHASES " == *" same "* ]]; then
    start_server "$det" same || return $?
    replay "$det" same A "$REPEATS" || { stop_server; return 4; }
    replay "$det" same B "$REPEATS" || { stop_server; return 4; }
    stop_server
  fi
  # 重启：每次新 server 各回放 1 遍（A 为新 server 首次；B 在 A 之后）
  [[ " $PHASES " == *" restart "* ]] || RESTARTS_EFF=0
  for i in $(seq 1 "${RESTARTS_EFF:-$RESTARTS}"); do
    start_server "$det" "restart$i" || return $?
    replay "$det" "restart$i" A 1 || { stop_server; return 4; }
    replay "$det" "restart$i" B 1 || { stop_server; return 4; }
    stop_server
  done
  # 常驻顺序：A→B→A、B→A→B
  if [[ " $PHASES " == *" order "* ]]; then
    start_server "$det" aba || return $?
    replay "$det" aba A 1 0 && replay "$det" aba B 1 0 && replay "$det" aba A 1 1 || { stop_server; return 4; }
    stop_server
    start_server "$det" bab || return $?
    replay "$det" bab B 1 0 && replay "$det" bab A 1 0 && replay "$det" bab B 1 1 || { stop_server; return 4; }
    stop_server
  fi

  for i in $(seq 1 $((REPEATS - 1))); do
    cmpr "$det" same "$d/same/A/rep0" "$d/same/A/rep$i" "same/A/rep0-vs-rep$i"
    cmpr "$det" same "$d/same/B/rep0" "$d/same/B/rep$i" "same/B/rep0-vs-rep$i"
  done
  for i in $(seq 2 "$RESTARTS"); do
    cmpr "$det" restart "$d/restart1/A/rep0" "$d/restart$i/A/rep0" "restart/A/1-vs-$i"
    cmpr "$det" restart "$d/restart1/B/rep0" "$d/restart$i/B/rep0" "restart/B-after-A/1-vs-$i"
  done
  cmpr "$det" restart "$d/same/A/rep0" "$d/restart1/A/rep0" "restart/A/same0-vs-1"
  cmpr "$det" ABA "$d/restart1/A/rep0" "$d/aba/A/rep0" "ABA/A-first-vs-fresh"
  cmpr "$det" ABA "$d/restart1/A/rep0" "$d/aba/A/rep1" "ABA/A-after-B-vs-fresh"
  cmpr "$det" ABA "$d/aba/A/rep0" "$d/aba/A/rep1" "ABA/A-first-vs-A-after-B"
  cmpr "$det" ABA "$d/bab/B/rep0" "$d/bab/B/rep1" "BAB/B-first-vs-B-last"
  cmpr "$det" ABA "$d/restart1/B/rep0" "$d/bab/B/rep0" "BAB/B-fresh-vs-restart-B-after-A"
  cmpr "$det" ABA "$d/restart1/B/rep0" "$d/bab/B/rep1" "BAB/B-last-vs-restart-B-after-A"
  cmpr "$det" ABA "$d/restart1/A/rep0" "$d/bab/A/rep0" "BAB/A-after-B-vs-fresh"
  return 0
}

run_cache_test() {  # mme 编译缓存三态（det off）；「关闭」即 det-off/same/A/rep0
  local cache="$OUT/jax-cache/$(gpu_slug)" n1 n2 hits  # 与 run_seat.sh 一样按 GPU 型号分目录
  rm -rf "$cache"; mkdir -p "$cache"
  start_server off cache-cold "$cache" || return $?
  replay off cache-cold A 1 || { stop_server; return 4; }
  stop_server
  n1=$(find "$cache" -type f | wc -l)
  start_server off cache-warm "$cache" || return $?
  replay off cache-warm A 1 || { stop_server; return 4; }
  stop_server
  n2=$(find "$cache" -type f | wc -l)
  hits=$(grep -ci "cache hit" "$SLOG" || true)
  local hit="no"; (( n1 > 0 && n2 == n1 && hits > 0 )) && hit="yes"
  echo "CACHE_CHECK=INFO policy=mme files_cold=$n1 files_warm=$n2 log_hits=$hits hit=$hit"
  printf '{"run_id": "%s", "files_cold": %d, "files_warm": %d, "log_hits": %d, "hit": "%s", "dir": "%s"}\n' \
      "$RUN_ID" "$n1" "$n2" "$hits" "$hit" "$cache" > "$OUT/cache-check.json"
  cmpr off cache "det-off/same/A/rep0" "det-off/cache-cold/A/rep0" "cache/off-vs-cold"
  cmpr off cache "det-off/cache-cold/A/rep0" "det-off/cache-warm/A/rep0" "cache/cold-vs-warm"
  cmpr off cache "det-off/same/A/rep0" "det-off/cache-warm/A/rep0" "cache/off-vs-warm"
  return 0
}

main() {
  if [[ -n "${SLURM_JOB_ID:-}" ]]; then
    echo "GPU_LOCK skipped=slurm job=$SLURM_JOB_ID"
  elif [[ "${V75_GPU_LOCK_HELD:-0}" == "1" ]]; then
    echo "GPU_LOCK held_by_caller=${V75_GPU_LOCK:-unknown}"
  else
    local lock="${V75_GPU_LOCK:-/home/hongzefu/.claude/jobs/6f127313/tmp/gpu$GPU.lock}"
    exec 9>"$lock"; flock 9; echo "GPU_LOCK acquired=$lock"
  fi
  # 清掉旧产物，report 只汇总本次 RUN_ID
  rm -rf "$OUT/compare" "$OUT"/det-* "$OUT/report.json" "$OUT/cache-check.json" "$OUT/gpu-busy.jsonl"
  mkdir -p "$OUT/compare"
  echo "POLICY_REPLAY_START cond=$COND gpu=$GPU policy=$POL A=$INA B=$INB out=$OUT host=$(hostname) \
git=$(git -C "$REPO" rev-parse HEAD) repeats=$REPEATS restarts=$RESTARTS det_states='$DET_STATES' phases='$PHASES' run_id=$RUN_ID"
  local det rc=0
  for det in $DET_STATES; do
    run_det_state "$det" || { rc=$?; echo "STEP_FAIL det=$det rc=$rc"; break; }
  done
  if (( rc == 0 )) && [[ "$POL" == "mme" && "$CACHE_TEST" == "on" ]]; then
    run_cache_test || { rc=$?; echo "STEP_FAIL cache rc=$rc"; }
  fi
  "$BENCH_PY" "$PR" report --root "$OUT" --cond "$COND" --policy "$POL" --run-id "$RUN_ID" || { (( rc == 0 )) && rc=1; }
  echo "全部完成 policy=$POL rc=$rc"
  return "$rc"
}

exec > >(tee -a "$LOG") 2>&1
main
rc=$?
stop_server
echo "EXIT_CODE=$rc"
exit "$rc"
