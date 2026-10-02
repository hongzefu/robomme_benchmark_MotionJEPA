#!/usr/bin/env bash
# V8 双模型评估：GL 计算节点内跑一个席位（1001-v8-post-evaluation-gl-plan.md 第二部分 §2／§5，契约 C3）。
#
# 已在占位 job 的 srun 步骤里（由主会话在 GL 登录节点 tmux `ev-v8-<R>-sNN` 内发起），本脚本：
#   1. 固定解释器：BENCH_PY=<repo>/.venv/bin/python、MME_PY=<repo>/third_party/mme-vla/.venv/bin/python、
#      SMVLA_PY=<repo>/artifacts/v8-two/venvs/smvla-env/bin/python；VK_ICD_FILENAMES 取法同 v75-lanes/gl/seat_run.sh；
#      --cpus 取本进程 sched_getaffinity；--gpu 0；端口按 run_seat.sh 既有规则（seat-idx = 席号 NN）。
#   2. 按策略顺序（默认先 smvla 后 mme，同卡绝不同时驻留）各调一次 run_seat.sh --v8：
#      持久状态（results.jsonl、<policy>.ledger.jsonl、progress.json、client.log、seat 日志）直接写 NFS
#      <stage>/sNN/<policy>/；录像写节点本地 <local-root>/rec/<policy>/（默认 local-root=/tmp/<R>-sNN）。
#      一律带 --never-degrade（视频无损全保留），不接受 --no-record。
#   3. 后台同步循环每 --sync-interval 秒（默认 120）把「该策略 results.jsonl 已有行的 rec_dir 指向它、且目录内
#      summary.json 已写出」的录像目录 rsync -rt 到 <stage>/sNN/<policy>/rec/<目录名>/，逐文件 sha256 一致后才删节点副本；
#      进行中的目录不碰。
#   4. 正常、失败、中断（trap TERM/INT）三路收尾：先回收子进程，再对节点上剩余的全部录像目录做全量同步并核对，
#      打印 SEAT_REC_SYNC=PASS|FAIL n= bytes=，再打印 V8_SEAT_DONE seat=NN outcome=pass|fail|aborted rc=，末行 EXIT_CODE=<rc>。
#
# 用法（一席一行）：
#   bash <repo>/scripts/eval-official/run_v8_gl.sh --run-name R --seat NN --repo <NFS 执行副本> --stage <NFS 运行根> \
#     --shard <shard-NN.json> --policies smvla,mme --mme-ckpt D --smvla-ckpt D --openpi-data-home D \
#     --tokenizer-sha256 H --reset-budget N --infra-retry-budget N [--limit N] \
#     [--episode-wall-smvla S] [--episode-wall-mme S] [--sync-interval S] [--local-root DIR]
# 退出码：0 全部策略 rc=0 且录像同步 PASS；中断 130/143；其余失败取首个非零策略 rc（录像同步 FAIL 且策略全 0 时为 7）；
#   参数错误 2；执行环境缺失（解释器、shard 等）3。
# 不嵌入任何 JobID，不含 /data 默认路径。
set -uo pipefail
export PYTHONUNBUFFERED=1

RUN_NAME="" ; SEAT="" ; REPO="" ; STAGE="" ; SHARD="" ; POLICIES="smvla,mme"
MME_CKPT="" ; SMVLA_CKPT="" ; OPENPI_HOME="" ; TOKENIZER_SHA="" ; RESET_BUDGET="" ; INFRA_RETRY_BUDGET=""
LIMIT="0" ; WALL_SMVLA="" ; WALL_MME="" ; SYNC_INTERVAL=120 ; LOCAL_ROOT="" ; COND="V8"

usage() { sed -n '2,27p' "${BASH_SOURCE[0]}" >&2; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-name) RUN_NAME="$2"; shift 2;;
    --seat) SEAT="$2"; shift 2;;
    --repo) REPO="$2"; shift 2;;
    --stage) STAGE="$2"; shift 2;;
    --shard) SHARD="$2"; shift 2;;
    --policies) POLICIES="$2"; shift 2;;
    --mme-ckpt) MME_CKPT="$2"; shift 2;;
    --smvla-ckpt) SMVLA_CKPT="$2"; shift 2;;
    --openpi-data-home) OPENPI_HOME="$2"; shift 2;;
    --tokenizer-sha256) TOKENIZER_SHA="$2"; shift 2;;
    --reset-budget) RESET_BUDGET="$2"; shift 2;;
    --infra-retry-budget) INFRA_RETRY_BUDGET="$2"; shift 2;;
    --limit) LIMIT="$2"; shift 2;;
    --episode-wall-smvla) WALL_SMVLA="$2"; shift 2;;
    --episode-wall-mme) WALL_MME="$2"; shift 2;;
    --sync-interval) SYNC_INTERVAL="$2"; shift 2;;
    --local-root) LOCAL_ROOT="$2"; shift 2;;
    --no-record) echo "run_v8_gl.sh 禁止 --no-record（全部视频保留）" >&2; exit 2;;
    -h|--help) usage; exit 0;;
    *) echo "未知参数 $1" >&2; usage; exit 2;;
  esac
done

die2() { echo "$1" >&2; exit 2; }
[[ -n "$RUN_NAME" && -n "$SEAT" && -n "$REPO" && -n "$STAGE" && -n "$SHARD" ]] \
  || die2 "缺少必需参数（--run-name --seat --repo --stage --shard）"
[[ "$RUN_NAME" =~ ^[A-Za-z0-9._-]+$ ]] || die2 "--run-name 只许字母数字 . _ -"
[[ "$SEAT" =~ ^[0-9]{2}$ ]] || die2 "--seat 须为两位席号 NN（如 03）"
[[ "$RESET_BUDGET" =~ ^[0-9]+$ && "$INFRA_RETRY_BUDGET" =~ ^[0-9]+$ ]] \
  || die2 "--reset-budget 与 --infra-retry-budget 必填且为非负整数"
[[ "$LIMIT" =~ ^[0-9]+$ && "$SYNC_INTERVAL" =~ ^[0-9]+$ ]] || die2 "--limit／--sync-interval 须为非负整数"
IFS=',' read -r -a POLS <<< "$POLICIES"
for pol in "${POLS[@]}"; do
  case "$pol" in
    smvla) [[ -n "$SMVLA_CKPT" ]] || die2 "跑 smvla 须给 --smvla-ckpt";;
    mme) [[ -n "$MME_CKPT" && -n "$OPENPI_HOME" && -n "$TOKENIZER_SHA" ]] \
           || die2 "跑 mme 须给 --mme-ckpt --openpi-data-home --tokenizer-sha256";;
    *) die2 "未知策略 $pol（只许 smvla,mme）";;
  esac
done
SEAT_IDX=$((10#$SEAT))
[[ -n "$LOCAL_ROOT" ]] || LOCAL_ROOT="/tmp/$RUN_NAME-s$SEAT"
REC_LOCAL="$LOCAL_ROOT/rec"
SEAT_STAGE="$STAGE/s$SEAT"

export BENCH_PY="$REPO/.venv/bin/python"
export MME_PY="$REPO/third_party/mme-vla/.venv/bin/python"
export SMVLA_PY="$REPO/artifacts/v8-two/venvs/smvla-env/bin/python"
for f in /usr/share/vulkan/icd.d/nvidia_icd.x86_64.json /usr/share/vulkan/icd.d/nvidia_icd.json; do
  [[ -f "$f" ]] && { export VK_ICD_FILENAMES="$f"; break; }
done
# 录像降级只看此盘空间；--never-degrade 下恒无损，此处指向节点本地录像根以免探测不存在的路径
export V75_DATA_ROOT="$LOCAL_ROOT"

ts_iso() { date -Is; }
RUN_SEAT_PID="" ; SYNC_PID="" ; ABORTED=0 ; ABORT_RC=0 ; FINALIZED=0

# ---------------- 录像同步 ----------------
# 列出 $1（results.jsonl）中 rec_dir 的目录名（basename），每行一个
rec_names_in_results() {
  [[ -f "$1" ]] || return 0
  "$BENCH_PY" - "$1" <<'PY'
import json, os, sys
names = set()
with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
    for line in f:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = r.get("rec_dir") if isinstance(r, dict) else None
        if d:
            names.add(os.path.basename(str(d).rstrip("/")))
for n in sorted(names):
    print(n)
PY
}

# 同步一个录像目录：rsync -rt → 逐文件 sha256 → 一致才删源；成功时把字节数加进 SYNC_BYTES
SYNC_BYTES=0
sync_one_dir() {  # $1 = 源目录；$2 = 目的目录
  local src="$1" dst="$2" f rel a b bytes=0 bad=0
  mkdir -p "$dst" || return 1
  rsync -rt "$src/" "$dst/" || { echo "REC_SYNC_RSYNC_FAIL src=$src"; return 1; }
  while IFS= read -r -d '' f; do
    rel="${f#"$src"/}"
    a="$(sha256sum "$f" | awk '{print $1}')"
    b="$(sha256sum "$dst/$rel" 2>/dev/null | awk '{print $1}')"
    if [[ -z "$a" || "$a" != "$b" ]]; then
      echo "REC_SYNC_SHA_MISMATCH file=$rel src_sha=$a dst_sha=${b:-missing}"; bad=1
    else
      bytes=$((bytes + $(stat -c %s "$f")))
    fi
  done < <(find "$src" -type f -print0)
  (( bad == 0 )) || return 1
  rm -rf -- "$src" || return 1
  SYNC_BYTES=$((SYNC_BYTES + bytes))
  return 0
}

# $1 = periodic|final。periodic 只搬「结果行已指向且 summary.json 已写出」的目录；final 搬节点上剩余全部目录。
# 打印统计并返回 0（全部成功）/1（有失败）。final 时打印 SEAT_REC_SYNC 判定行。
sync_recordings() {
  local mode="$1" pol src dst name n=0 fail=0 left=0
  SYNC_BYTES=0
  for pol in "${POLS[@]}"; do
    src="$REC_LOCAL/$pol"; dst="$SEAT_STAGE/$pol/rec"
    [[ -d "$src" ]] || continue
    if [[ "$mode" == "periodic" ]]; then
      local -A done_names=()
      while IFS= read -r name; do [[ -n "$name" ]] && done_names["$name"]=1; done \
        < <(rec_names_in_results "$SEAT_STAGE/$pol/results.jsonl")
    fi
    for d in "$src"/*/; do
      [[ -d "$d" ]] || continue
      name="$(basename "$d")"
      if [[ "$mode" == "periodic" ]]; then
        [[ -n "${done_names[$name]:-}" && -f "$src/$name/summary.json" ]] || continue
      fi
      if sync_one_dir "$src/$name" "$dst/$name"; then
        n=$((n + 1)); echo "REC_SYNCED policy=$pol dir=$name mode=$mode"
      else
        fail=$((fail + 1)); echo "REC_SYNC_FAIL policy=$pol dir=$name mode=$mode"
      fi
    done
  done
  if [[ "$mode" == "final" ]]; then
    for pol in "${POLS[@]}"; do
      [[ -d "$REC_LOCAL/$pol" ]] && left=$((left + $(find "$REC_LOCAL/$pol" -mindepth 1 -maxdepth 1 -type d | wc -l)))
    done
    if (( fail == 0 && left == 0 )); then
      echo "SEAT_REC_SYNC=PASS n=$n bytes=$SYNC_BYTES seat=$SEAT"
    else
      echo "SEAT_REC_SYNC=FAIL n=$n bytes=$SYNC_BYTES seat=$SEAT failed=$fail left_on_node=$left"
    fi
  fi
  (( fail == 0 && left == 0 ))
}

sync_loop() {  # 后台：周期同步；收到 TERM 立即退出（主流程随后做全量同步），连同 sleep 子进程一起收掉
  local sp=""
  trap '[[ -n "$sp" ]] && kill "$sp" 2>/dev/null; exit 0' TERM INT
  while true; do
    sleep "$SYNC_INTERVAL" & sp=$!
    wait "$sp"; sp=""
    sync_recordings periodic
  done
}

stop_sync_loop() {
  [[ -n "$SYNC_PID" ]] || return 0
  kill -TERM "$SYNC_PID" 2>/dev/null
  wait "$SYNC_PID" 2>/dev/null
  SYNC_PID=""
}

# ---------------- 子进程回收 ----------------
# run_seat.sh 异常死亡（如被 KILL）时，其 setsid 起的 server／客户端进程组可能残留：按 .v8-pgids 回收，
# 只杀命令行确属本评估入口的进程组（防 PID 复用误杀）。
reap_orphans() {
  local f="$SEAT_STAGE/.v8-pgids" role pid cmd
  [[ -f "$f" ]] || return 0
  while read -r role pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    kill -0 "$pid" 2>/dev/null || continue
    cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)"
    case "$cmd" in
      *env_client.py*|*smvla_server.py*|*serve_policy.py*|*mme_client.py*)
        echo "REAP_ORPHAN role=$role pgid=$pid"
        kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
        local i; for i in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
        kill -KILL -- "-$pid" 2>/dev/null || true;;
    esac
  done < "$f"
}

stop_run_seat() {  # 转发 TERM 给 run_seat.sh（它会收掉 server／客户端），最多等 180 s
  [[ -n "$RUN_SEAT_PID" ]] || return 0
  if kill -0 "$RUN_SEAT_PID" 2>/dev/null; then
    kill -TERM "$RUN_SEAT_PID" 2>/dev/null
    local i; for i in $(seq 1 180); do kill -0 "$RUN_SEAT_PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$RUN_SEAT_PID" 2>/dev/null && kill -KILL "$RUN_SEAT_PID" 2>/dev/null
  fi
  wait "$RUN_SEAT_PID" 2>/dev/null
  RUN_SEAT_PID=""
}

finalize() {  # $1 = outcome；$2 = rc
  local outcome="$1" rc="$2" src
  (( FINALIZED == 1 )) && return
  FINALIZED=1
  trap '' TERM INT  # 收尾期间不再被打断
  stop_sync_loop
  stop_run_seat
  reap_orphans
  if ! sync_recordings final; then
    [[ "$outcome" == "pass" ]] && outcome="fail"
    (( rc == 0 )) && rc=7
  fi
  echo "V8_SEAT_DONE seat=$SEAT outcome=$outcome rc=$rc run_name=$RUN_NAME host=$(hostname) $(ts_iso)"
  echo "EXIT_CODE=$rc"
  exit "$rc"
}

on_signal() {  # $1 = 信号名
  ABORTED=1
  [[ "$1" == "INT" ]] && ABORT_RC=130 || ABORT_RC=143
  echo "V8_SEAT_SIGNAL sig=$1 seat=$SEAT $(ts_iso)"
  finalize aborted "$ABORT_RC"
}
trap 'on_signal TERM' TERM
trap 'on_signal INT' INT

# ---------------- 主流程 ----------------
mkdir -p "$SEAT_STAGE" "$REC_LOCAL" || { echo "RUN_BLOCKED reason=mkdir stage=$SEAT_STAGE local=$REC_LOCAL"; echo "EXIT_CODE=3"; exit 3; }
SEAT_LOG="$SEAT_STAGE/run_v8_gl-s$SEAT.log"
exec > >(tee -a "$SEAT_LOG") 2>&1

CPUS="$("$BENCH_PY" -c 'import os;print(",".join(map(str,sorted(os.sched_getaffinity(0)))))' 2>/dev/null)"
echo "V8_SEAT_START run_name=$RUN_NAME seat=$SEAT idx=$SEAT_IDX host=$(hostname) cpus=${CPUS:-?} repo=$REPO \
stage=$SEAT_STAGE local=$LOCAL_ROOT shard=$SHARD policies=$POLICIES reset_budget=$RESET_BUDGET \
infra_retry_budget=$INFRA_RETRY_BUDGET limit=$LIMIT sync_interval=$SYNC_INTERVAL vk_icd=${VK_ICD_FILENAMES:-unset} $(ts_iso)"

blocked=""
[[ -x "$BENCH_PY" ]] || blocked="bench_py_missing $BENCH_PY"
[[ -z "$blocked" && -n "$CPUS" ]] || blocked="${blocked:-cpus_unknown}"
[[ -z "$blocked" && -f "$SHARD" ]] || blocked="${blocked:-shard_missing $SHARD}"
[[ -z "$blocked" && -f "$REPO/scripts/eval-official/run_seat.sh" ]] || blocked="${blocked:-run_seat_missing}"
if [[ -n "$blocked" ]]; then
  echo "RUN_BLOCKED reason=$blocked"
  finalize fail 3
fi

sync_loop &
SYNC_PID=$!

overall=0
for i in "${!POLS[@]}"; do
  pol="${POLS[$i]}"
  mkdir -p "$SEAT_STAGE/$pol" "$REC_LOCAL/$pol"
  : > "$SEAT_STAGE/.v8-pgids"
  args=(--seat "$SEAT" --seat-idx "$SEAT_IDX" --gpu 0 --cpus "$CPUS" --cond "$COND" --out "$SEAT_STAGE"
        --policies "$pol" --identities "$SHARD" --limit "$LIMIT" --never-degrade
        --v8 --ledger-dir "$SEAT_STAGE/$pol" --reset-budget "$RESET_BUDGET" --infra-retry-budget "$INFRA_RETRY_BUDGET"
        --rec-root "$REC_LOCAL")
  [[ -n "$WALL_SMVLA" ]] && args+=(--episode-wall-smvla "$WALL_SMVLA")
  [[ -n "$WALL_MME" ]] && args+=(--episode-wall-mme "$WALL_MME")
  if [[ "$pol" == "mme" ]]; then
    args+=(--mme-ckpt "$MME_CKPT" --openpi-data-home "$OPENPI_HOME" --tokenizer-sha256 "$TOKENIZER_SHA")
  else
    args+=(--smvla-ckpt "$SMVLA_CKPT")
  fi
  echo "V8_POLICY_START seat=$SEAT policy=$pol $(ts_iso)"
  bash "$REPO/scripts/eval-official/run_seat.sh" "${args[@]}" \
    > >(tee -a "$SEAT_STAGE/$pol/seat-$SEAT.log") 2>&1 &
  RUN_SEAT_PID=$!
  while true; do
    wait "$RUN_SEAT_PID"; rc=$?
    kill -0 "$RUN_SEAT_PID" 2>/dev/null || break
  done
  RUN_SEAT_PID=""
  echo "V8_POLICY_DONE seat=$SEAT policy=$pol rc=$rc $(ts_iso)"
  if (( rc > 128 )); then
    echo "V8_SUPERVISOR_DIED seat=$SEAT policy=$pol rc=$rc（run_seat.sh 被信号终止，回收残留子进程）"
    reap_orphans
  fi
  (( rc != 0 && overall == 0 )) && overall=$rc
done

if (( overall == 0 )); then finalize pass 0; else finalize fail "$overall"; fi
