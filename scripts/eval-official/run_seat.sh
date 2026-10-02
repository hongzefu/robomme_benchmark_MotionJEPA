#!/usr/bin/env bash
# v7.5eval 席位执行器（0929-v7.5eval-restructure-plan.md §5、第二部分 R4～R6）。
#
# 一个席位（一张 GPU）上按策略顺序（默认先 smvla 后 mme）逐个：起 server → 等就绪 → 起常驻客户端
# （env_client.py run，金丝雀先跑）→ 看门狗 → 收 server；同一张卡上两个策略的 server 绝不同时驻留。
#
# 用法：
#   run_seat.sh --seat 甲 --seat-idx 1 --gpu 0 --cond N --out <dir> (--queue <dir> | --identities <json>)
#               [--policies smvla,mme] [--cpus 0-3] [--canary Task:source_episode:seed] [--order forward|reverse|shuffle]
#               [--mme-ckpt <run>/79999] [--smvla-ckpt <dir>] [--compile-cache on|off] [--det on|off]
#               [--relay on|off] [--limit N] [--no-record] [--client-per-task] [--never-degrade]
#               [--episode-wall-smvla S] [--episode-wall-mme S]
# V8 模式（1001-v8-post-evaluation-gl-plan.md、契约 C3；不带 --v8 时一切同旧版）：
#   run_seat.sh ... --identities <shard-NN.json> --v8 --ledger-dir <dir> --reset-budget N --infra-retry-budget N
#               [--rec-root <dir>] [--openpi-data-home <dir> --tokenizer-sha256 <hex>]（跑 mme 时这两项必填）
#   账本 <ledger-dir>/<policy>.ledger.jsonl；录像根 <rec-root>/<policy>（传给客户端 --rec-root）；
#   单局墙钟默认 smvla 900 s、mme 1200 s；客户端退出 5（reset 额度耗尽）与 3（阻塞）不重启、照实收尾；
#   MME server 启动前 OPENPI_DATA_HOME 固定为 --openpi-data-home，核 <dir>/big_vision/paligemma_tokenizer.model 的
#   sha256：不符打印 RUN_BLOCKED reason=tokenizer_sha 并不启 server，相符打印 TOKENIZER_SHA=PASS sha256=<hex>。
#   V8 模式不接受 --queue、--canary、--client-per-task、--no-record；setsid 起的进程组记在 <out>/.v8-pgids，
#   供外层 run_v8_gl.sh 在本脚本异常死亡后回收。
# --client-per-task（仅 identities 模式，计划 5.1 E1「每任务起新客户端进程、server 常驻」）：server 常驻，
#   按身份文件里任务首次出现的顺序分组，每组起一个新客户端 ``--only <task>_<seed>,...``（组内按文件顺序），逐组串行；
#   首次推理放宽仍只给 server 新（重）起后的第一个客户端；看门狗照常；结果都追加进同一个 results.jsonl。
# 可用环境变量覆盖解释器：BENCH_PY、MME_PY、SMVLA_PY（默认 $REPO/artifacts/v7.5eval/venvs/smvla-env/bin/python）、
# 缓存根 V75_JAX_CACHE_ROOT。
#
# 端口：18000 + 100 × 席号 + 10 × 策略号（smvla=0、mme=1），MME 录制中继 +1；起前 /dev/tcp 探测，被占依次 +2，最多 5 次。
# 超时：server 就绪 1200 s（等待中 kill -0 查 server 存活）；客户端第一局另放宽 600 s（首次推理编译）；
#       单局墙钟 smvla 600 s、mme 900 s → 基础设施超时（客户端退出 75，本脚本重起客户端）；
#       progress.json 20 min 不更新 → 杀掉 server 与客户端重起一次；server 中途死亡 → 重起（最多 2 次）。
# 日志：<out>/seat-<seat>.log，末行 EXIT_CODE=<rc>。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCH_PY="${BENCH_PY:-$REPO/.venv/bin/python}"
MME_PY="${MME_PY:-$REPO/third_party/mme-vla/.venv/bin/python}"
SMVLA_PY="${SMVLA_PY:-$REPO/artifacts/v7.5eval/venvs/smvla-env/bin/python}"
MME_COMMIT="ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b"
MME_YAML_EXPECT="perceptual-framesamp-modul.yaml"

SEAT="" ; SEAT_IDX="" ; GPU="" ; COND="" ; OUT="" ; QUEUE="" ; IDENTS="" ; POLICIES="smvla,mme" ; CPUS=""
CANARY="" ; ORDER="forward" ; CLIENT_PER_TASK=0 ; ONLY_LIST="" ; COMPILE_CACHE="off" ; DET="off" ; RELAY="off" ; LIMIT="0" ; NO_RECORD=""
NEVER_DEGRADE="" ; WALL_SMVLA="" ; WALL_MME=""
V8=0 ; LEDGER_DIR="" ; RESET_BUDGET="" ; INFRA_RETRY_BUDGET="" ; REC_ROOT="" ; OPENPI_HOME="" ; TOKENIZER_SHA=""
TOKENIZER_REL="big_vision/paligemma_tokenizer.model"
MME_CKPT="${MME_CKPT:-/data/hongzefu/robomme_policy_learning_MotionJEPA/v1-store/models/official-mme-vla/perceptual-framesamp-modul/79999}"
SMVLA_CKPT="${SMVLA_CKPT:-/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA/checkpoints/simplememvla_robomme}"
READY_TIMEOUT=1200 ; FIRST_EXTRA=600 ; NOPROG_S=1200 ; MAX_CLIENT_RESTARTS=8 ; MAX_SERVER_RESTARTS=2

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seat) SEAT="$2"; shift 2;;
    --seat-idx) SEAT_IDX="$2"; shift 2;;
    --gpu) GPU="$2"; shift 2;;
    --cond) COND="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --queue) QUEUE="$2"; shift 2;;
    --identities) IDENTS="$2"; shift 2;;
    --policies) POLICIES="$2"; shift 2;;
    --cpus) CPUS="$2"; shift 2;;
    --canary) CANARY="$2"; shift 2;;
    --order) ORDER="$2"; shift 2;;
    --mme-ckpt) MME_CKPT="$2"; shift 2;;
    --smvla-ckpt) SMVLA_CKPT="$2"; shift 2;;
    --compile-cache) COMPILE_CACHE="$2"; shift 2;;
    --det) DET="$2"; shift 2;;
    --relay) RELAY="$2"; shift 2;;
    --limit) LIMIT="$2"; shift 2;;
    --no-record) NO_RECORD="--no-record"; shift;;
    --client-per-task) CLIENT_PER_TASK=1; shift;;
    --noprog-s) NOPROG_S="$2"; shift 2;;
    --never-degrade) NEVER_DEGRADE="--never-degrade"; shift;;
    --episode-wall-smvla) WALL_SMVLA="$2"; shift 2;;
    --episode-wall-mme) WALL_MME="$2"; shift 2;;
    --v8) V8=1; shift;;
    --ledger-dir) LEDGER_DIR="$2"; shift 2;;
    --reset-budget) RESET_BUDGET="$2"; shift 2;;
    --infra-retry-budget) INFRA_RETRY_BUDGET="$2"; shift 2;;
    --rec-root) REC_ROOT="$2"; shift 2;;
    --openpi-data-home) OPENPI_HOME="$2"; shift 2;;
    --tokenizer-sha256) TOKENIZER_SHA="$2"; shift 2;;
    *) echo "未知参数 $1" >&2; exit 2;;
  esac
done
if [[ -z "$SEAT" || -z "$SEAT_IDX" || -z "$GPU" || -z "$COND" || -z "$OUT" ]]; then
  echo "缺少必需参数（--seat --seat-idx --gpu --cond --out）" >&2; exit 2
fi
if (( CLIENT_PER_TASK == 1 )) && [[ -n "$QUEUE" ]]; then
  echo "--client-per-task 只用于 --identities 模式" >&2; exit 2
fi
if [[ -n "$QUEUE" && -n "$IDENTS" ]] || [[ -z "$QUEUE" && -z "$IDENTS" ]]; then
  echo "--queue 与 --identities 必须二选一" >&2; exit 2
fi
is_uint() { [[ "$1" =~ ^[0-9]+$ ]]; }
for _w in "$WALL_SMVLA" "$WALL_MME"; do
  [[ -z "$_w" ]] || is_uint "$_w" || { echo "--episode-wall-smvla／--episode-wall-mme 须为非负整数秒" >&2; exit 2; }
done
if (( V8 == 1 )); then
  [[ -n "$IDENTS" ]] || { echo "--v8 只用于 --identities 模式（执行清单 shard JSON）" >&2; exit 2; }
  [[ -z "$CANARY" ]] || { echo "--v8 不接受 --canary（金丝雀预算为零）" >&2; exit 2; }
  (( CLIENT_PER_TASK == 0 )) || { echo "--v8 不接受 --client-per-task" >&2; exit 2; }
  [[ -z "$NO_RECORD" ]] || { echo "--v8 禁止 --no-record（视频全部保留）" >&2; exit 2; }
  [[ -n "$LEDGER_DIR" ]] || { echo "--v8 必须给 --ledger-dir" >&2; exit 2; }
  is_uint "$RESET_BUDGET" || { echo "--v8 必须给 --reset-budget <非负整数>" >&2; exit 2; }
  is_uint "$INFRA_RETRY_BUDGET" || { echo "--v8 必须给 --infra-retry-budget <非负整数>" >&2; exit 2; }
elif [[ -n "$LEDGER_DIR$RESET_BUDGET$INFRA_RETRY_BUDGET$REC_ROOT$OPENPI_HOME$TOKENIZER_SHA" ]]; then
  echo "--ledger-dir／--reset-budget／--infra-retry-budget／--rec-root／--openpi-data-home／--tokenizer-sha256 只能与 --v8 同用" >&2
  exit 2
fi
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"  # 转绝对路径（server 子进程会 cd 进子模块）
if (( V8 == 1 )); then
  LEDGER_DIR="$(mkdir -p "$LEDGER_DIR" && cd "$LEDGER_DIR" && pwd)"
  [[ -n "$REC_ROOT" ]] && REC_ROOT="$(mkdir -p "$REC_ROOT" && cd "$REC_ROOT" && pwd)"
  [[ -n "$OPENPI_HOME" && -d "$OPENPI_HOME" ]] && OPENPI_HOME="$(cd "$OPENPI_HOME" && pwd)"
fi
[[ -n "$IDENTS" ]] && IDENTS="$(cd "$(dirname "$IDENTS")" && pwd)/$(basename "$IDENTS")"
[[ -n "$QUEUE" ]] && QUEUE="$(mkdir -p "$QUEUE" && cd "$QUEUE" && pwd)"
LOG="$OUT/seat-${SEAT}.log"

TASKSET=()
[[ -n "$CPUS" ]] && TASKSET=(taskset -c "$CPUS")
# 两个 server 分支都先清掉会影响确定性／编译缓存的变量，再只设本席位要的（-u 须在赋值之前）
CLEAN_ENV=(-u XLA_FLAGS -u JAX_COMPILATION_CACHE_DIR -u JAX_PERSISTENT_CACHE_MIN_ENTRY_SIZE_BYTES
           -u JAX_PERSISTENT_CACHE_MIN_COMPILE_TIME_SECS -u CUBLAS_WORKSPACE_CONFIG)
# 去代理变量、只连 127.0.0.1（GL 计算节点有 HTTP 代理）
NOPROXY_ENV=(-u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY
             NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost)

SERVER_PID="" ; CLIENT_PID="" ; RELAY_PID="" ; FRESH_SERVER=0

ts() { date +%s; }
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

pick_port() {  # $1 = 基础端口；server 端口与其 +1（中继）都空闲才用
  local p="$1" i
  for i in 1 2 3 4 5; do
    if ! port_busy "$p" && ! port_busy "$((p + 1))"; then echo "$p"; return 0; fi
    p=$((p + 2))
  done
  return 1
}

kill_group() {  # $1 = 进程组首进程 pid；先 TERM 再 KILL
  local pid="$1" i
  [[ -z "$pid" ]] && return 0
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
  for i in $(seq 1 60); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  kill -KILL -- "-$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

stop_server() {
  [[ -n "$RELAY_PID" ]] && kill_group "$RELAY_PID"; RELAY_PID=""
  if [[ -n "$SERVER_PID" ]]; then
    kill_group "$SERVER_PID"
    # 核实显存已释放：该 pid 不应再出现在计算进程列表里
    local i
    for i in $(seq 1 30); do
      nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -qw "$SERVER_PID" || break
      sleep 1
    done
    echo "SERVER_STOPPED pid=$SERVER_PID"
  fi
  SERVER_PID=""
}

cleanup() {
  [[ -n "$CLIENT_PID" ]] && kill_group "$CLIENT_PID"; CLIENT_PID=""
  stop_server
}

gpu_slug() { nvidia-smi --query-gpu=name --format=csv,noheader -i "$GPU" 2>/dev/null | head -1 | tr ' /' '__'; }

ckpt_fingerprint() {  # $1 = 目录；逐文件 sha256 汇成一个指纹
  "$BENCH_PY" - "$1" <<'PY'
import hashlib, sys, time
from pathlib import Path
t0 = time.time(); root = Path(sys.argv[1]).resolve(); h = hashlib.sha256(); n = b = 0
for p in sorted(x for x in root.rglob("*") if x.is_file()):
    fh = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            fh.update(chunk)
    h.update(f"{p.relative_to(root)}\t{p.stat().st_size}\t{fh.hexdigest()}\n".encode()); n += 1; b += p.stat().st_size
print(f"CKPT_FINGERPRINT dir={root} sha256={h.hexdigest()} files={n} bytes={b} secs={time.time()-t0:.1f}")
PY
}

preflight_mme() {
  local sub="$REPO/third_party/mme-vla" head hc
  head="$(git -C "$sub" rev-parse HEAD)"
  [[ "$head" == "$MME_COMMIT" ]] || { echo "RUN_BLOCKED reason=mme_commit head=$head"; return 1; }
  git -C "$sub" diff --quiet HEAD -- src scripts packages pyproject.toml uv.lock || { echo "RUN_BLOCKED reason=mme_dirty"; return 1; }
  if [[ -n "$(ls -A "$sub/third_party/robomme_benchmark" 2>/dev/null)" ]]; then
    echo "RUN_BLOCKED reason=nested_submodule_not_empty"; return 1
  fi
  hc="$(cat "$MME_CKPT/../history_config.txt" 2>/dev/null)"
  [[ "$hc" == "$MME_YAML_EXPECT" ]] || { echo "RUN_BLOCKED reason=history_config value='$hc'"; return 1; }
  [[ -f "$sub/src/mme_vla_suite/models/config/robomme/$hc" ]] || { echo "RUN_BLOCKED reason=yaml_missing $hc"; return 1; }
  [[ -d "$MME_CKPT/params" && -d "$MME_CKPT/assets" ]] || { echo "RUN_BLOCKED reason=ckpt_layout $MME_CKPT"; return 1; }
  [[ -x "$MME_PY" ]] || { echo "RUN_BLOCKED reason=mme_venv_missing $MME_PY"; return 1; }
  echo "MME_PREFLIGHT=PASS commit=$head history_config=$hc ckpt=$MME_CKPT py=$MME_PY"
}

tokenizer_gate() {  # V8：MME server 启动前核 OPENPI_DATA_HOME 下 tokenizer 的 sha256（不现场下载顶替）
  local f actual
  if [[ -z "$OPENPI_HOME" || -z "$TOKENIZER_SHA" ]]; then
    echo "RUN_BLOCKED reason=tokenizer_sha detail=missing_args（V8 跑 mme 须给 --openpi-data-home 与 --tokenizer-sha256）"
    return 1
  fi
  f="$OPENPI_HOME/$TOKENIZER_REL"
  if [[ ! -f "$f" ]]; then
    echo "RUN_BLOCKED reason=tokenizer_sha detail=file_missing file=$f"; return 1
  fi
  actual="$(sha256sum "$f" | awk '{print $1}')"
  if [[ "${actual,,}" != "${TOKENIZER_SHA,,}" ]]; then
    echo "RUN_BLOCKED reason=tokenizer_sha expected=${TOKENIZER_SHA,,} actual=$actual file=$f"; return 1
  fi
  echo "TOKENIZER_SHA=PASS sha256=$actual file=$f openpi_data_home=$OPENPI_HOME"
}

note_pgid() {  # V8：记下 setsid 起的进程组，供外层编排在本脚本异常死亡后回收（$1 = 角色，$2 = pid）
  (( V8 == 1 )) && echo "$1 $2" >> "$OUT/.v8-pgids" 2>/dev/null
  return 0
}

start_server() {  # $1 = 策略；$2 = 端口；$3 = 日志
  local pol="$1" port="$2" slog="$3"
  local extra=()
  if [[ "$pol" == "mme" ]]; then
    extra=(XLA_PYTHON_CLIENT_MEM_FRACTION=0.75 GLIBC_TUNABLES=glibc.rtld.optional_static_tls=16384 UV_LINK_MODE=copy
           VIRTUAL_ENV="$REPO/third_party/mme-vla/.venv")
    if [[ "$COMPILE_CACHE" == "on" ]]; then
      extra+=(JAX_COMPILATION_CACHE_DIR="${V75_JAX_CACHE_ROOT:-$REPO/artifacts/v7.5eval/jax-cache}/$(gpu_slug)")
    fi
    [[ "$DET" == "on" ]] && extra+=(XLA_FLAGS="--xla_gpu_deterministic_ops=true --xla_gpu_autotune_level=0")
    # V8：tokenizer 缓存根固定（server 在 env 清理后启动，须显式写进 server 环境）
    (( V8 == 1 )) && extra+=(OPENPI_DATA_HOME="$OPENPI_HOME")
    ( cd "$REPO/third_party/mme-vla" && exec setsid env "${CLEAN_ENV[@]}" "${NOPROXY_ENV[@]}" "${extra[@]}" PYTHONUNBUFFERED=1 \
        CUDA_VISIBLE_DEVICES="$GPU" "${TASKSET[@]}" "$MME_PY" scripts/serve_policy.py --seed=7 --port="$port" \
        policy:checkpoint --policy.config=mme_vla_suite --policy.dir="$MME_CKPT" ) >"$slog" 2>&1 &
  else
    # 确定性模式：与 run_policy_replay.sh 相同，--det + CUBLAS_WORKSPACE_CONFIG=:4096:8
    local detarg=()
    [[ "$DET" == "on" ]] && detarg=(--det) && extra=(CUBLAS_WORKSPACE_CONFIG=:4096:8)
    ( cd "$REPO" && exec setsid env "${CLEAN_ENV[@]}" "${NOPROXY_ENV[@]}" "${extra[@]}" PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false \
        PYTHONUTF8=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True MPLBACKEND=Agg CUDA_VISIBLE_DEVICES="$GPU" \
        "${TASKSET[@]}" "$SMVLA_PY" scripts/eval-official/smvla_server.py serve --port "$port" --ckpt "$SMVLA_CKPT" \
        --warmup "${detarg[@]}" --metadata_out "$OUT/$pol/server-metadata-$port.json" ) >"$slog" 2>&1 &
  fi
  SERVER_PID=$!
  note_pgid server "$SERVER_PID"
  local t0; t0=$(ts)
  echo "SERVER_START policy=$pol port=$port pid=$SERVER_PID log=$slog"
  while true; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "SERVER_DIED_BEFORE_READY policy=$pol port=$port"; tail -n 20 "$slog"; SERVER_PID=""; return 1
    fi
    if port_busy "$port"; then break; fi
    if (( $(ts) - t0 > READY_TIMEOUT )); then
      echo "SERVER_READY_TIMEOUT policy=$pol port=$port limit_s=$READY_TIMEOUT"; stop_server; return 1
    fi
    sleep 2 & wait $!
  done
  echo "SERVER_READY policy=$pol port=$port ready_s=$(( $(ts) - t0 ))"
  FRESH_SERVER=1  # 下一个客户端的第一局享受首次推理放宽
  if [[ "$pol" == "mme" ]]; then
    if grep -q "history_config='$MME_YAML_EXPECT'" "$slog"; then
      echo "SERVER_CONFIG=PASS policy=mme history_config=$MME_YAML_EXPECT seed=7"
    else
      echo "RUN_BLOCKED reason=server_config（日志里没有 history_config='$MME_YAML_EXPECT'）"; stop_server; return 3
    fi
    if [[ "$RELAY" == "on" ]]; then
      ( exec setsid env "${NOPROXY_ENV[@]}" PYTHONUNBUFFERED=1 "$BENCH_PY" "$REPO/scripts/eval-official/mme_client.py" relay \
          --listen "$((port + 1))" --upstream "$port" --log "$OUT/$pol/relay-$port.jsonl" ) >"$OUT/$pol/relay-$port.log" 2>&1 &
      RELAY_PID=$!
      local i; for i in $(seq 1 60); do port_busy "$((port + 1))" && break; sleep 0.5; done
      echo "RELAY_READY port=$((port + 1)) pid=$RELAY_PID"
    fi
  fi
  return 0
}

wall_of() {  # 单局墙钟：显式参数优先；否则旧版 smvla 600／mme 900，V8 默认 smvla 900／mme 1200
  if [[ "$1" == "mme" ]]; then
    if [[ -n "$WALL_MME" ]]; then echo "$WALL_MME"; elif (( V8 == 1 )); then echo 1200; else echo 900; fi
  else
    if [[ -n "$WALL_SMVLA" ]]; then echo "$WALL_SMVLA"; elif (( V8 == 1 )); then echo 900; else echo 600; fi
  fi
}

restart_server() {  # 起 server 失败时保留 RUN_BLOCKED 的 3，其余记基础设施 4
  local rc
  start_server "$@"; rc=$?
  (( rc == 0 )) && return 0
  stop_server
  (( rc == 3 )) && return 3
  return 4
}

write_report() {  # $1 = 策略；$2 = 退出状态；写 <out>/<pol>/seat-report.json 并打印 SEAT_DONE 判定行
  "$BENCH_PY" - "$OUT/$1" "$1" "$COND" "$SEAT" "$2" "${QUEUE:-}" "$REPO/scripts/eval-official/claim_queue.py" <<'PY'
import importlib.util, json, sys
from pathlib import Path
out, pol, cond, seat, rc, queue, qpy = sys.argv[1:8]
rows = []
p = Path(out) / "results.jsonl"
if p.exists():
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
main = [r for r in rows if not r.get("canary")]
last = {}
for r in main:
    # V8 结果行带 key（task_tier_seed）；旧行仍按 (task, seed)
    last[r["key"] if r.get("v8") and r.get("key") else (r["task"], int(r["seed"]))] = r
final = list(last.values())
rep = {"policy": pol, "cond": cond, "seat": seat, "loop_exit_status": int(rc), "records": len(rows),
       "canary": sum(1 for r in rows if r.get("canary")), "done": sum(1 for r in final if not r.get("infra")),
       "errors": sum(1 for r in final if r.get("status") == "error" and not r.get("infra")),
       "infra": sum(1 for r in main if r.get("infra")), "run_blocked": sum(1 for r in rows if r.get("run_blocked")),
       "queue_check": "NA", "queue": None}
for k in ("success", "fail", "timeout"):
    rep[k] = sum(1 for r in final if r.get("status") == k and not r.get("infra"))
if queue:
    spec = importlib.util.spec_from_file_location("claim_queue", qpy)
    q = importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
    st = q.ClaimQueue(Path(queue) / pol).check()
    rep["queue"] = {k: int(st.get(k, 0)) for k in ("dup", "missing", "requeued", "done", "total", "late",
                                                   "open_claims", "retries_used", "infra_exhausted")}
    rep["queue_check"] = "PASS" if st["dup"] == 0 and st["missing"] == 0 else "FAIL"
    print(q.check_line(st))
(Path(out) / "seat-report.json").write_text(json.dumps(rep, sort_keys=True, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"SEAT_DONE policy={pol} cond={cond} seat={seat} done={rep['done']} errors={rep['errors']} infra={rep['infra']} "
      f"queue_check={rep['queue_check']} loop_exit_status={rc}")
sys.exit(1 if rep["queue_check"] == "FAIL" else 0)
PY
}

start_client() {  # $1 = 策略；$2 = 客户端连接端口；$3 = 是否带金丝雀
  local pol="$1" cport="$2" with_canary="$3" wall extra=0
  wall="$(wall_of "$pol")"
  # 首次推理放宽只给 server 新（重）起后的第一个客户端；客户端单独重起（server 已热）不放宽
  (( FRESH_SERVER == 1 )) && extra="$FIRST_EXTRA"
  FRESH_SERVER=0
  local src=() canary=() pol_env=() v8args=()
  if [[ -n "$QUEUE" ]]; then src=(--queue "$QUEUE"); else src=(--identities "$IDENTS" --order "$ORDER"); fi
  # 每任务一个客户端：只跑本组身份，组内保持文件顺序
  [[ -n "$ONLY_LIST" ]] && src=(--identities "$IDENTS" --order forward --only "$ONLY_LIST")
  [[ "$with_canary" == 1 && -n "$CANARY" ]] && canary=(--canary "$CANARY")
  # smvla 旧官方环境与推理同进程、OMP_NUM_THREADS=1；新接口环境侧照设
  [[ "$pol" == "smvla" ]] && pol_env=(OMP_NUM_THREADS=1)
  if (( V8 == 1 )); then
    v8args=(--v8 --ledger "$LEDGER_DIR/$pol.ledger.jsonl" --reset-budget "$RESET_BUDGET"
            --infra-retry-budget "$INFRA_RETRY_BUDGET")
    [[ -n "$REC_ROOT" ]] && v8args+=(--rec-root "$REC_ROOT/$pol")
  fi
  ( cd "$REPO" && exec setsid env "${NOPROXY_ENV[@]}" "${pol_env[@]}" GLIBC_TUNABLES=glibc.rtld.optional_static_tls=16384 \
      PYTHONUNBUFFERED=1 CUDA_VISIBLE_DEVICES="$GPU" V75_DATA_ROOT="${V75_DATA_ROOT:-/data}" "${TASKSET[@]}" \
      "$BENCH_PY" scripts/eval-official/env_client.py run --policy "$pol" "${src[@]}" --cond "$COND" --seat "$SEAT" \
      --port "$cport" --out "$OUT/$pol" --episode-wall-s "$wall" --first-extra-s "$extra" --limit "$LIMIT" \
      "${canary[@]}" $NO_RECORD $NEVER_DEGRADE "${v8args[@]}" ) >>"$OUT/$pol/client.log" 2>&1 &
  CLIENT_PID=$!
  note_pgid client "$CLIENT_PID"
  echo "CLIENT_START policy=$pol port=$cport pid=$CLIENT_PID canary=${canary[1]:-none} wall_s=$wall first_extra_s=$extra only=${ONLY_LIST:-all}"
}

run_policy() {  # $1 = 策略；$2 = 策略号
  local pol="$1" pidx="$2" base port cport slog rc
  mkdir -p "$OUT/$pol"
  [[ -n "$SERVER_PID" ]] && { echo "RUN_BLOCKED reason=previous_server_alive pid=$SERVER_PID"; return 3; }
  if [[ "$pol" == "mme" ]]; then
    if (( V8 == 1 )); then tokenizer_gate || return 3; fi
    preflight_mme || return 3
  fi
  [[ "$pol" == "smvla" && ! -x "$SMVLA_PY" ]] && { echo "RUN_BLOCKED reason=smvla_venv_missing $SMVLA_PY"; return 3; }
  base=$((18000 + 100 * SEAT_IDX + 10 * pidx))
  port="$(pick_port "$base")" || { echo "INFRA port_exhausted base=$base"; return 4; }
  local ck; [[ "$pol" == "mme" ]] && ck="$MME_CKPT" || ck="$SMVLA_CKPT"
  ckpt_fingerprint "$ck" > "$OUT/$pol/ckpt-fingerprint.txt" 2>&1 &
  local fp_pid=$!
  slog="$OUT/$pol/server-$port-$(ts).log"
  start_server "$pol" "$port" "$slog"; rc=$?
  wait "$fp_pid"; cat "$OUT/$pol/ckpt-fingerprint.txt"
  if (( rc != 0 )); then write_report "$pol" "$rc"; return "$rc"; fi
  cport="$port"; [[ "$pol" == "mme" && "$RELAY" == "on" ]] && cport=$((port + 1))

  rc=0
  if (( CLIENT_PER_TASK == 1 )); then
    local groups g task keys first_group=1
    # 按任务首次出现顺序分组；每行 "<task>\t<key>,<key>,..."
    groups="$("$BENCH_PY" - "$IDENTS" <<'PY'
import json, sys
rows = json.load(open(sys.argv[1], encoding="utf-8"))
order, by = [], {}
for r in rows:
    t = r["task"]
    if t not in by:
        order.append(t); by[t] = []
    by[t].append(f"{t}_{int(r['seed'])}")
for t in order:
    print(f"{t}\t{','.join(by[t])}")
PY
)" || { echo "RUN_BLOCKED reason=task_groups"; rc=3; }
    while IFS=$'\t' read -r task keys; do
      [[ -z "$task" ]] && continue
      (( rc != 0 )) && break
      ONLY_LIST="$keys"
      echo "TASK_CLIENT policy=$pol task=$task n=$(awk -F, '{print NF}' <<< "$keys")"
      policy_loop "$pol" "$port" "$cport" "$first_group" || rc=$?
      first_group=0
    done <<< "$groups"
    ONLY_LIST=""
  else
    policy_loop "$pol" "$port" "$cport" 1 || rc=$?
  fi
  stop_server
  local qrc=0
  write_report "$pol" "$rc" || qrc=$?
  (( rc == 0 && qrc != 0 )) && rc=5  # 队列核对 FAIL（重复或遗漏）：非零退出
  echo "POLICY_DONE policy=$pol seat=$SEAT rc=$rc"
  return "$rc"
}

policy_loop() {  # $1 策略 $2 server 端口 $3 客户端端口 $4 是否带金丝雀；返回 0 完成 / 3 阻塞 / 4 基础设施用尽
  local pol="$1" port="$2" cport="$3" rc slog
  # 无进展阈值须大于「单局墙钟 + 首次放宽 + 启动余量」，单局卡死先由客户端墙钟计时器以 75 退出并回收
  local noprog=$(( $(wall_of "$pol") + FIRST_EXTRA + 600 ))
  (( NOPROG_S > noprog )) && noprog=$NOPROG_S
  local client_restarts=0 server_restarts=0 noprog_restarts=0 last
  start_client "$pol" "$cport" "${4:-1}"
  while true; do
    if ! kill -0 "$CLIENT_PID" 2>/dev/null; then
      wait "$CLIENT_PID"; rc=$?; CLIENT_PID=""
      echo "CLIENT_EXIT policy=$pol rc=$rc"
      if (( rc == 0 )); then break; fi
      if (( rc == 3 )); then echo "RUN_BLOCKED reason=client policy=$pol"; return 3; fi
      # V8：reset 额度耗尽（客户端退出 5）不重启，照实收尾
      if (( V8 == 1 && rc == 5 )); then echo "RESET_BUDGET_EXHAUSTED policy=$pol seat=$SEAT（客户端退出 5，不重启）"; return 5; fi
      client_restarts=$((client_restarts + 1))
      if (( client_restarts > MAX_CLIENT_RESTARTS )); then echo "INFRA_EXHAUSTED policy=$pol client_restarts=$client_restarts"; return 4; fi
      start_client "$pol" "$cport" 0
      continue
    fi
    if [[ -n "$SERVER_PID" ]] && ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "SERVER_DIED policy=$pol pid=$SERVER_PID"; SERVER_PID=""
      kill_group "$CLIENT_PID"; CLIENT_PID=""
      server_restarts=$((server_restarts + 1))
      if (( server_restarts > MAX_SERVER_RESTARTS )); then echo "INFRA_EXHAUSTED policy=$pol server_restarts=$server_restarts"; return 4; fi
      stop_server
      slog="$OUT/$pol/server-$port-$(ts).log"
      restart_server "$pol" "$port" "$slog" || return $?
      start_client "$pol" "$cport" 0
      continue
    fi
    last=$(stat -c %Y "$OUT/$pol/progress.json" 2>/dev/null || echo 0)
    (( last == 0 )) && last=$(stat -c %Y "$OUT/$pol/client.log" 2>/dev/null || ts)
    if (( $(ts) - last > noprog )); then
      echo "NO_PROGRESS policy=$pol idle_s=$(( $(ts) - last )) restarts=$noprog_restarts"
      kill_group "$CLIENT_PID"; CLIENT_PID=""
      if (( noprog_restarts >= 1 )); then echo "INFRA_EXHAUSTED policy=$pol no_progress_twice"; return 4; fi
      noprog_restarts=$((noprog_restarts + 1))
      stop_server
      slog="$OUT/$pol/server-$port-$(ts).log"
      restart_server "$pol" "$port" "$slog" || return $?
      touch "$OUT/$pol/progress.json"
      start_client "$pol" "$cport" 0
      continue
    fi
    sleep 10 & wait $!  # 后台 sleep + wait：收到 SIGTERM 时 trap 立即生效
  done
  return 0
}

main() {
  trap cleanup EXIT
  trap 'exit 143' TERM INT
  echo "SEAT_START seat=$SEAT idx=$SEAT_IDX gpu=$GPU cpus=${CPUS:-all} cond=$COND policies=$POLICIES host=$(hostname) \
git=$(git -C "$REPO" rev-parse HEAD) compile_cache=$COMPILE_CACHE det=$DET relay=$RELAY"
  if (( V8 == 1 )); then
    echo "V8_MODE ledger_dir=$LEDGER_DIR reset_budget=$RESET_BUDGET infra_retry_budget=$INFRA_RETRY_BUDGET \
rec_root=${REC_ROOT:-<out>/<policy>/rec} wall_smvla=$(wall_of smvla) wall_mme=$(wall_of mme) never_degrade=${NEVER_DEGRADE:+1}"
  fi
  local overall=0 pol pidx rc
  IFS=',' read -r -a POLS <<< "$POLICIES"
  for pol in "${POLS[@]}"; do
    case "$pol" in smvla) pidx=0;; mme) pidx=1;; *) echo "未知策略 $pol"; return 2;; esac
    run_policy "$pol" "$pidx"; rc=$?
    (( rc != 0 )) && overall=$rc
  done
  echo "全部完成 seat=$SEAT rc=$overall"
  return "$overall"
}

# main 放后台、外层转发 TERM/INT：信号能到达 main 的 trap（cleanup 杀掉 setsid 起的 server／客户端进程组）
exec > >(tee -a "$LOG") 2>&1
main &
MAIN_PID=$!
trap 'kill -TERM "$MAIN_PID" 2>/dev/null' TERM INT
while true; do
  wait "$MAIN_PID"; rc=$?
  kill -0 "$MAIN_PID" 2>/dev/null || break
done
echo "EXIT_CODE=$rc"
exit "$rc"
