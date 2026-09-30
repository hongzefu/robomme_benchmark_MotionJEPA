#!/usr/bin/env bash
# v7.5eval 官方重跑（MME-VLA，加录制器）单片启动器：逻辑照抄旧官方
#   /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-official-xhard0/scripts/gl_eval_official_xhard0.sh
# （同样的环境变量、守卫、server 命令、3 遍重评、无进展看门狗），只有以下差别（方案 §2.5，均须写进留档）：
#   1. server 仍监听 PORT；透明代理 mme_proxy.py 监听 PORT+1 转发到 PORT；客户端连 PORT+1。
#   2. 客户端经 mme_client_wrap.py 同进程 runpy 运行官方 eval.py（外挂只读钩子）；PYTHONPATH 在官方 src 之后
#      追加本目录（官方 robomme 仍优先解析），起跑前仍核对 robomme.__file__ 与 robomme_hard 未导入。
#   3. 录制根 REC_ROOT；SAVE_ROOT 必须是新目录（起前断言无 episodes*.jsonl），且只许落在白名单根下（R8）；
#      V75_RESUME=1 只许续用标记文件 .v75-created 中清单 sha256 与分片都一致的目录。
#   6. 看门狗循环里另查 server／代理进程：死亡即打印 SERVER_DIED／PROXY_DIED、杀 eval、退出码 5／6。
#   4. 可选 NODE_TMP：SAVE_ROOT／REC_ROOT 默认落在节点本地盘，跑完由调用方搬回（本脚本不搬）。
#   5. server 启动环境显式去掉 XLA_FLAGS 与 JAX 编译缓存变量（与历史一致：只设 XLA_PYTHON_CLIENT_MEM_FRACTION=0.75）。
# 用法（环境变量）：
#   MANIFEST=<清单 jsonl> SHARD=<i> PORT=<端口> RUN_TAG=<标签> SAVE_ROOT=<新目录> REC_ROOT=<新目录> \
#   [NODE_TMP=<节点本地目录>] [VIDEO_DIR=<目录>] [ONLY_TASKS=a,b] [ROBOMME_ENV=<客户端 venv>] [SERVER_REPO=<目录>] \
#   [MME_OFFICIAL_REPO=<旧官方工作树>] [V75_RESUME=1（仅允许续用本脚本自己建的 SAVE_ROOT）] \
#   [V75_ENCODE_CPUS=<编码核，默认 CPU 亲和集合最后一核>] bash scripts/eval-official/official_observer/run_official_mme.sh
set -uo pipefail
OBS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${MME_OFFICIAL_REPO:-/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-official-xhard0}"
cd "$REPO" || { echo "错误: 旧官方工作树不存在: $REPO"; echo "EXIT_CODE=1"; exit 1; }
: "${MANIFEST:?}" "${SHARD:?}" "${PORT:?}" "${RUN_TAG:?}"
PROXY_PORT=$((PORT + 1))
CKPT=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/eval-out/mmevla-ckpt/perceptual-framesamp-modul/79999
if [[ -n "${NODE_TMP:-}" ]]; then
  mkdir -p "$NODE_TMP" && [[ -w "$NODE_TMP" ]] || { echo "错误: NODE_TMP 不可写: $NODE_TMP"; echo "EXIT_CODE=1"; exit 1; }
  SAVE_ROOT="${SAVE_ROOT:-$NODE_TMP/save}"
  REC_ROOT="${REC_ROOT:-$NODE_TMP/rec}"
fi
: "${SAVE_ROOT:?必须显式给新目录 SAVE_ROOT（或 NODE_TMP）}" "${REC_ROOT:?必须显式给新目录 REC_ROOT（或 NODE_TMP）}"
SAVE_ROOT="$(readlink -m "$SAVE_ROOT")"; REC_ROOT="$(readlink -m "$REC_ROOT")"; MANIFEST="$(readlink -f "$MANIFEST")"
SAVE_DIR="$SAVE_ROOT/mmevla-official-xhard0/ckpt79999/seed7"
VIDEO_DIR="$(readlink -m "${VIDEO_DIR:-$SAVE_ROOT/videos-xhard0}")"
# 编码核：默认取本进程 CPU 亲和集合的最后一个核；必须是亲和集合的子集（录制器初始化时还会再校验）
V75_ENCODE_CPUS="${V75_ENCODE_CPUS:-$(python3 -c 'import os; print(max(os.sched_getaffinity(0)))')}"
python3 -c "
import os,sys
w=set()
for p in sys.argv[1].split(','):
    a,_,b=p.partition('-'); w.update(range(int(a),int(b or a)+1))
sys.exit(0 if w and w<=os.sched_getaffinity(0) else 1)" "$V75_ENCODE_CPUS" \
  || { echo "错误: V75_ENCODE_CPUS=$V75_ENCODE_CPUS 不在 CPU 亲和集合内"; echo "EXIT_CODE=1"; exit 1; }
export V75_ENCODE_CPUS
ROBOMME_ENV="${ROBOMME_ENV:-/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-testhard-v7/robomme_env}"
OFFICIAL_SRC="$REPO/third_party/robomme_benchmark/src"
SERVER_REPO="${SERVER_REPO:-/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-testhard-v7}"
# R8：新目录守卫——输出只许落在白名单根下（NODE_TMP、NFS v75eval/、本机 artifacts/v7.5eval/），历史目录一律拒绝；
# 已有逐局结果即拒绝（旧启动器 done_keys 会整片静默跳过且 EXIT_CODE=0）
NFS=/nfs/turbo/coe-chaijy-unreplicated/hongzefu
ALLOW=("$NFS/v75eval/" "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/v7.5eval/")
[[ -n "${NODE_TMP:-}" ]] && ALLOW+=("$(readlink -m "$NODE_TMP")/")
for d in "$SAVE_ROOT" "$REC_ROOT" "$VIDEO_DIR"; do
  case "$d/" in
    "$NFS/v7-eval/"*|"$NFS/v7-eval-stage/"*|"$NFS/eval-out/"*|"$REPO/"*)
      echo "错误: 输出目录落在历史／官方目录下: $d"; echo "EXIT_CODE=1"; exit 1;;
  esac
  ok=0; for a in "${ALLOW[@]}"; do [[ "$d/" == "$a"* ]] && ok=1; done
  [[ "$ok" = 1 ]] || { echo "错误: 输出目录不在白名单根下（${ALLOW[*]}）: $d"; echo "EXIT_CODE=1"; exit 1; }
done
MARK="manifest_sha256=$(sha256sum "$MANIFEST" | cut -c1-64) shard=$SHARD"
if [[ "${V75_RESUME:-0}" = 1 ]]; then
  [[ -f "$SAVE_ROOT/.v75-created" && "$(cat "$SAVE_ROOT/.v75-created")" == "$MARK" ]] \
    || { echo "错误: V75_RESUME=1 但 $SAVE_ROOT/.v75-created 缺失或与本次清单／分片不符"; echo "EXIT_CODE=1"; exit 1; }
  echo "V75_RESUME: 续用本脚本建的 $SAVE_ROOT（$MARK）"
else
  if [[ -d "$SAVE_ROOT" ]] && [[ -n "$(find "$SAVE_ROOT" -name 'episodes*.jsonl' -print -quit 2>/dev/null)" ]]; then
    echo "错误: SAVE_ROOT 已有 episodes*.jsonl（必须新目录）: $SAVE_ROOT"; echo "EXIT_CODE=1"; exit 1
  fi
  if [[ -d "$REC_ROOT" ]] && [[ -n "$(ls -A "$REC_ROOT" 2>/dev/null)" ]]; then
    echo "错误: REC_ROOT 非空（必须新目录）: $REC_ROOT"; echo "EXIT_CODE=1"; exit 1
  fi
fi
mkdir -p "$SAVE_ROOT" "$REC_ROOT"
[[ -f "$SAVE_ROOT/.v75-created" ]] || echo "$MARK" > "$SAVE_ROOT/.v75-created"
SERVER_LOG="$SAVE_ROOT/server.log"
PROXY_LOG="$SAVE_ROOT/proxy.log"
[[ -f "$MANIFEST" ]] || { echo "错误: 清单不存在: $MANIFEST"; echo "EXIT_CODE=1"; exit 1; }
[[ -d "$CKPT/params" ]] || { echo "错误: checkpoint 缺 params: $CKPT"; echo "EXIT_CODE=1"; exit 1; }
[[ -x "$SERVER_REPO/.venv/bin/python" ]] || { echo "错误: server 环境不存在: $SERVER_REPO/.venv"; echo "EXIT_CODE=1"; exit 1; }
git -C "$SERVER_REPO" diff --quiet ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b -- src scripts/serve_policy.py pyproject.toml uv.lock packages \
  || { echo "错误: $SERVER_REPO 的 server 代码与官方 ecf086c 不同"; echo "EXIT_CODE=1"; exit 1; }
[[ -x "$ROBOMME_ENV/bin/python" ]] || { echo "错误: 客户端环境不存在: $ROBOMME_ENV"; echo "EXIT_CODE=1"; exit 1; }
[[ -d "$OFFICIAL_SRC/robomme" ]] || { echo "错误: 官方子模块未初始化: $OFFICIAL_SRC"; echo "EXIT_CODE=1"; exit 1; }
SHARD_N=$(python3 -c "
import json,sys
print(sum(1 for l in open(sys.argv[1]) if l.strip() and int(json.loads(l)['shard'])==int(sys.argv[2])))" "$MANIFEST" "$SHARD")
[[ "$SHARD_N" -gt 0 ]] || { echo "错误: 清单里 shard=$SHARD 没有行"; echo "EXIT_CODE=1"; exit 1; }
# 客户端公共环境：去掉代理变量（GL 节点代理拒绝 websocket，HTTP 403）、官方 src 置顶、本目录追加在后
CLIENT_ENV=(env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY
  NO_PROXY=127.0.0.1,localhost PYTHONUNBUFFERED=1 GLIBC_TUNABLES=glibc.rtld.optional_static_tls=16384
  PYTHONPATH="$OFFICIAL_SRC:$OBS_DIR" REC_ROOT="$REC_ROOT" V75_DATA_ROOT="${V75_DATA_ROOT:-$REC_ROOT}"
  V75_ENCODE_CPUS="$V75_ENCODE_CPUS")
# 起跑前核对（同旧启动器）：robomme 必须解析到本工作树官方子模块，且导入 env_runner 后 robomme_hard 不在 sys.modules
( cd examples/robomme && "${CLIENT_ENV[@]}" "$ROBOMME_ENV/bin/python" -c "
import sys, robomme, env_runner
assert robomme.__file__.startswith(sys.argv[1]), robomme.__file__
assert 'robomme_hard' not in sys.modules
print('OFFICIAL_ROBOMME', robomme.__file__)" "$OFFICIAL_SRC" ) || { echo "错误: 客户端未解析到官方 robomme 或导入了 robomme_hard"; echo "EXIT_CODE=1"; exit 1; }
# 包装器自检：钩子装得上、官方 robomme 仍优先（写进 REC_ROOT/preflight，不占逐局目录）
( cd examples/robomme && "${CLIENT_ENV[@]}" REC_ROOT="$REC_ROOT/preflight" "$ROBOMME_ENV/bin/python" "$OBS_DIR/mme_client_wrap.py" --v75-preflight ) \
  || { echo "错误: 录制器包装自检失败"; echo "EXIT_CODE=1"; exit 1; }
echo "=== MMEVLA_OFFICIAL_XHARD0_OBSERVED host=$(hostname) job=${SLURM_JOB_ID:-none} HEAD=$(git -C "$REPO" rev-parse HEAD) server_repo=$SERVER_REPO@$(git -C "$SERVER_REPO" rev-parse --short HEAD) submodule=$(git -C "$REPO/third_party/robomme_benchmark" rev-parse HEAD) observer=$OBS_DIR shard=$SHARD shard_n=$SHARD_N port=$PORT proxy_port=$PROXY_PORT ckpt=$CKPT save_root=$SAVE_ROOT rec_root=$REC_ROOT start=$(date -Is) ==="
nvidia-smi --query-gpu=name,driver_version,compute_mode --format=csv,noheader
# 端口占用守卫（server 与代理两个端口）
for p in "$PORT" "$PROXY_PORT"; do
  if (exec 3<>"/dev/tcp/127.0.0.1/${p}") 2>/dev/null; then
    exec 3>&-
    echo "错误: 端口 ${p} 起跑前已被占用"; echo "EXIT_CODE=1"; exit 1
  fi
done
# 显存上限 0.75 只改 server 启动环境；不开确定性标志、不开编译缓存（与历史一致，方案 2.3）
( cd "$SERVER_REPO" && exec env -u XLA_FLAGS -u JAX_COMPILATION_CACHE_DIR -u JAX_PERSISTENT_CACHE_MIN_COMPILE_TIME_SECS \
  -u JAX_PERSISTENT_CACHE_MIN_ENTRY_SIZE_BYTES -u JAX_ENABLE_COMPILATION_CACHE \
  XLA_PYTHON_CLIENT_MEM_FRACTION=0.75 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
  uv run --frozen --no-sync scripts/serve_policy.py --seed=7 --port="$PORT" \
    policy:checkpoint --policy.dir="$CKPT" --policy.config=mme_vla_suite ) >> "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
PROXY_PID=""
EVAL_PID=""
cleanup() {
  [[ -n "$EVAL_PID" ]] && kill "$EVAL_PID" 2>/dev/null
  if [[ -n "$PROXY_PID" ]] && kill -0 "$PROXY_PID" 2>/dev/null; then
    kill -TERM "$PROXY_PID"; for _ in $(seq 1 60); do kill -0 "$PROXY_PID" 2>/dev/null || break; sleep 1; done
    kill -9 "$PROXY_PID" 2>/dev/null || true
  fi
  if kill -0 "$SERVER_PID" 2>/dev/null; then kill "$SERVER_PID"; sleep 2; kill -9 "$SERVER_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT
for _ in $(seq 1 600); do   # server 就绪上限 20 分钟；server 先死立即退出
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then echo "错误: server 提前退出"; tail -30 "$SERVER_LOG"; echo "EXIT_CODE=1"; exit 1; fi
  if (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then exec 3>&-; break; fi
  sleep 2
done
grep -m1 -E "Restoring checkpoint|checkpoint" "$SERVER_LOG" | sed 's/^/SERVER_CKPT_LINE /'
echo "server 端口就绪 $(date +%T)"
# 透明代理（客户端 venv：websockets 15 + openpi_client）
( cd examples/robomme && exec "${CLIENT_ENV[@]}" "$ROBOMME_ENV/bin/python" "$OBS_DIR/mme_proxy.py" \
    --listen "$PROXY_PORT" --upstream "$PORT" --log-dir "$REC_ROOT/proxy" ) >> "$PROXY_LOG" 2>&1 &
PROXY_PID=$!
for _ in $(seq 1 150); do
  if ! kill -0 "$PROXY_PID" 2>/dev/null; then echo "错误: 代理提前退出"; tail -30 "$PROXY_LOG"; echo "EXIT_CODE=1"; exit 1; fi
  grep -q PROXY_READY "$PROXY_LOG" 2>/dev/null && break
  sleep 2
done
grep -q PROXY_READY "$PROXY_LOG" || { echo "错误: 代理 300 s 未就绪"; echo "EXIT_CODE=1"; exit 1; }
echo "代理就绪 $(grep -m1 PROXY_READY "$PROXY_LOG") $(date +%T)"
RC=0
unresolved=0
died=""
for pass in 1 2 3; do
  errors=$(grep -c '"status": "error"' "$SAVE_DIR/episodes.jsonl" 2>/dev/null); errors=${errors:-0}
  if [[ "$errors" -gt "$SHARD_N" ]]; then echo "RETRY_CAP_HIT shard=$SHARD errors=$errors"; RC=4; break; fi
  echo "EVAL_PASS $pass errors_so_far=$errors $(date -Is)"
  ( cd examples/robomme && "${CLIENT_ENV[@]}" \
      "$ROBOMME_ENV/bin/python" "$OBS_DIR/mme_client_wrap.py" eval.py --args.host=127.0.0.1 --args.port="$PROXY_PORT" \
      --args.model_seed=7 --args.model_ckpt_id=79999 \
      --args.policy_name=mmevla-official-xhard0 --args.episode_manifest="$MANIFEST" --args.shard="$SHARD" \
      --args.video_dir="$VIDEO_DIR" --args.save_dir="$SAVE_ROOT" ${ONLY_TASKS:+--args.only_tasks="$ONLY_TASKS"} ) &
  EVAL_PID=$!
  started=$(date +%s)
  stalled=0
  while kill -0 "$EVAL_PID" 2>/dev/null; do   # 无进展看门狗：首局放宽 10 分钟，之后 30 分钟
    sleep 30
    # server／代理进程守卫（本启动器新增）：任一死亡即杀 eval、停止重评，以不同退出码报告
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then died=server; echo "SERVER_DIED pass=$pass $(date -Is)"; tail -30 "$SERVER_LOG"; fi
    if [[ -z "$died" ]] && ! kill -0 "$PROXY_PID" 2>/dev/null; then died=proxy; echo "PROXY_DIED pass=$pass $(date -Is)"; tail -30 "$PROXY_LOG"; fi
    if [[ -n "$died" ]]; then pkill -TERM -P "$EVAL_PID" 2>/dev/null; kill "$EVAL_PID" 2>/dev/null; break; fi
    last=$(stat -c %Y "$SAVE_DIR/episodes.jsonl" 2>/dev/null || echo "$started")
    [[ "$last" -lt "$started" ]] && last=$started
    limit=1800; [[ ! -f "$SAVE_DIR/episodes.jsonl" ]] && limit=2400
    if (( $(date +%s) - last > limit )); then
      echo "EVAL_STALL pass=$pass idle_s=$(( $(date +%s) - last )) 杀掉重起（记基础设施 error）"
      pkill -TERM -P "$EVAL_PID" 2>/dev/null; kill "$EVAL_PID" 2>/dev/null; stalled=1; break
    fi
  done
  wait "$EVAL_PID"; RC=$?; EVAL_PID=""
  if [[ "$died" = server ]]; then RC=5; break; fi
  if [[ "$died" = proxy ]]; then RC=6; break; fi
  [[ "$stalled" = 1 ]] && { RC=124; continue; }
  unresolved=$(python3 -c "
import json,sys
last={}
for l in open(sys.argv[1]):
    if l.strip():
        r=json.loads(l); last[(r['task'],r['source_episode'])]=r['status']
print(sum(v=='error' for v in last.values()))" "$SAVE_DIR/episodes.jsonl" 2>/dev/null || echo 0)
  echo "EVAL_PASS_END $pass rc=$RC unresolved_errors=$unresolved"
  [[ "$unresolved" = 0 ]] && break
done
# 退出码：0 全部终态；3 有未解决 error；4 重试上限；5 server 死亡；6 代理死亡；124 最后一遍无进展
# 有未解决的 error 身份时不得以 0 退出
[[ "$RC" = 0 && "${unresolved:-0}" != 0 ]] && RC=3
# 先停代理让记账线程落盘，再做透明性对账（判定行供编排器读取；不改 EXIT_CODE 语义）
if [[ -n "$PROXY_PID" ]] && kill -0 "$PROXY_PID" 2>/dev/null; then
  kill -TERM "$PROXY_PID"; for _ in $(seq 1 300); do kill -0 "$PROXY_PID" 2>/dev/null || break; sleep 1; done
fi
PROXY_PID=""
"${CLIENT_ENV[@]}" "$ROBOMME_ENV/bin/python" "$OBS_DIR/transparency_check.py" --rec-root "$REC_ROOT" --out "$REC_ROOT/transparency.json"
nrec=$(grep -c . "$REC_ROOT/recorder-index.jsonl" 2>/dev/null); nrec=${nrec:-0}
npass=$(grep -c '"RECORDER_VERIFY": "PASS"' "$REC_ROOT/recorder-index.jsonl" 2>/dev/null); npass=${npass:-0}
echo "OBSERVER_RECORDINGS episodes=$nrec verify_pass=$npass rec_root=$REC_ROOT"
[[ -n "${NODE_TMP:-}" ]] && echo "NODE_TMP_STAGED save_root=$SAVE_ROOT rec_root=$REC_ROOT（由调用方搬回并核对 sha256）"
echo "EVAL_RC=$RC end=$(date -Is)"
echo "EXIT_CODE=$RC"
exit "$RC"
