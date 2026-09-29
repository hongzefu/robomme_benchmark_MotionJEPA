# 一次性观察器与复现说明

本文件保留本轮临时观察器的源码，供复现，不作为长期入口。`run_rounds.sh`、`client_rounds_probe.py` 和 SimpleMemVLA 后续批次没有实跑；对应多轮记录只有不触发仿真的夹具检查。不得把这里的代码视为执行新批次的授权。

benchmark 用 `git archive ce3843b4fbe981307655570425ec39a3cdaad4a7` 恢复；framesample 用其仓库的 `git archive b22fc9c1ec73584870342c6335676a63dc417f9e` 恢复。原运行绝对路径、环境、权重、CPU配额和预算见 launch.md；新运行须使用新的输出目录与实际占位JobID，不复用本次旧席位。

首次失败 SimpleMemVLA 观察器与下列收尾版本不同：首次每次事件同步追加JSONL，且没有跨轮缓存包装；失败后改为退出时统一落盘并增加未实跑的多轮循环。首次失败的载模数据只作启动与故障证据，不进入有效吞吐比较。

## simplemem_probe.py

SHA256：`338afbb20da31e392e51639abeb601e0ebc6c85c449bd9c587c01677ba58e767`。

```python
"""一次性计时观察器：只包装策略与客户端，不改 benchmark 行为。"""
import functools
import json
import os
from pathlib import Path
import sys
import time

START = time.perf_counter()
OUT = Path(os.environ['PROBE_METRICS'])
OUT.parent.mkdir(parents=True, exist_ok=True)
EVENTS = []

def emit(data):
    EVENTS.append(data)

def timed(name, fn):
    @functools.wraps(fn)
    def call(*a, **kw):
        wall, cpu = time.perf_counter(), time.process_time()
        try:
            result = fn(*a, **kw)
            return result
        finally:
            emit(dict(kind=name, wall_s=time.perf_counter()-wall,
                      cpu_s=time.process_time()-cpu))
    return call

emit(dict(kind='process_start', affinity=sorted(os.sched_getaffinity(0)),
          pid=os.getpid(), argv=sys.argv, python=sys.executable,
          epoch=time.time(), dispatch_epoch=os.environ.get('DISPATCH_EPOCH')))
from robomme_sim import eval_success
from robomme_sim.inproc_pool import InProcSimPool

original_build = eval_success.build_policy
CACHED_POLICY = None
def build(args):
    global CACHED_POLICY
    if CACHED_POLICY is not None:
        return CACHED_POLICY
    batched, factory, normalizer = timed('model_load', original_build)(args)
    batched.generate_batch = timed('inference', batched.generate_batch)
    def buffers():
        buffer = factory()
        buffer._prepare_inputs = timed('prepare_inputs', buffer._prepare_inputs)
        return buffer
    CACHED_POLICY = batched, buffers, normalizer
    return CACHED_POLICY
eval_success.build_policy = build
for name in ('reset', 'step'):
    setattr(InProcSimPool, name, timed('environment_' + name, getattr(InProcSimPool, name)))
emit(dict(kind='imports_ready', wall_s=time.perf_counter()-START))
from robomme_sim.testhard_eval import main
original_argv = sys.argv[:]
try:
    rounds = int(os.environ.get('PROBE_ROUNDS', '1'))
    for repeat in range(rounds):
        sys.argv = original_argv[:]
        if rounds > 1:
            idx = sys.argv.index('--out') + 1
            sys.argv[idx] += '/round-' + str(repeat + 1)
        emit(dict(kind='round_start', round=repeat+1, epoch=time.time()))
        print(f'PROBE_ROUND_START round={repeat+1} epoch={time.time()}', flush=True)
        rc = main()
        emit(dict(kind='round_end', round=repeat+1, epoch=time.time(), exit_code=rc))
        print(f'PROBE_ROUND_END round={repeat+1} exit_code={rc} epoch={time.time()}', flush=True)
        if rc:
            raise SystemExit(rc)
finally:
    emit(dict(kind='process_end', wall_s=time.perf_counter()-START))
    with OUT.open('x') as f:
        for event in EVENTS:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
```

## run_simplemem.sh

SHA256：`4c7a100b8678f8a13ae5d36775a29927931f906a9de1e8835757fd80d90af42a`。

```bash
#!/usr/bin/env bash
# 本轮单个配额的常驻双任务测试；禁止自动重试。
set -euo pipefail
ROOT=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/eval-cpu-20260928
REPO=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA
TAG=${1:?}
ONLY=${2:?}
cd "$REPO"
GPU_MODE=$(nvidia-smi --query-gpu=uuid,compute_mode --format=csv,noheader)
echo "GPU_MODE=$GPU_MODE"
[[ "$GPU_MODE" = *,\ Default ]] || { echo GPU_MODE_CHECK=FAIL; exit 16; }
echo GPU_MODE_CHECK=PASS
export PYTHONPATH="$REPO" PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MPLBACKEND=Agg
export UV_CACHE_DIR="$HOME/.cache/uv"
export XDG_CACHE_HOME="$ROOT/cache/simplemem-$TAG"
export PROBE_METRICS="$ROOT/simplemem-$TAG/timing.jsonl"
export __GLX_VENDOR_LIBRARY_NAME=nvidia
unset SAPIEN_DISABLE_RAY_TRACING ROBOMME_GPU_RASTER MS_SKIP_ASSET_DOWNLOAD_PROMPT
for cand in /usr/share/vulkan/icd.d/nvidia_icd.x86_64.json /usr/share/vulkan/icd.d/nvidia_icd.json; do
  if [ -f "$cand" ]; then export VK_ICD_FILENAMES="$cand"; break; fi
done
exec "$REPO/.venv-robomme/bin/python" "$ROOT/simplemem_probe.py" \
  --benchmark_root "$ROOT/benchmark-ce3843" --out "$ROOT/simplemem-$TAG" \
  --round 1 --shard 0/1 --only "$ONLY" --max_attempts 1 --retry_cap 0 \
  --pretrained_checkpoint "$REPO/checkpoints/simplememvla_robomme" \
  --attn_implementation sdpa --group_size 1 </dev/null
```

## simplemem_remaining.sh

SHA256：`ff0383b7313cca3b8fea55600bb95c2dcce4926b115fb8863b02f04072519526`。

```bash
#!/usr/bin/env bash
# 仅执行已批准的剩余七局；首局失败则不接续。
set -euo pipefail
ROOT=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/eval-cpu-20260928
trap 'code=$?; echo "BATCH_EXIT_CODE=$code"' EXIT
grep -q '^EXIT_CODE=0$' "$ROOT/simplemem-cold-pick.log"
for spec in '4 cold-demo VideoPlaceButton/0' '1 cpu1 PickXtimes/0,VideoPlaceButton/0' '2 cpu2 PickXtimes/0,VideoPlaceButton/0' '4 cpu4 PickXtimes/0,VideoPlaceButton/0'; do
  read -r cpus tag tasks <<< "$spec"
  export DISPATCH_EPOCH=$(date +%s.%N)
  echo "DISPATCH tag=$tag cpus=$cpus epoch=$DISPATCH_EPOCH"
  set +e
  timeout -k 30s 1800s srun --jobid=62268960 --overlap --exact --ntasks=1 --cpus-per-task="$cpus" --cpu-bind=cores --gpu_cmode=shared \
    /usr/bin/bash "$ROOT/run_simplemem.sh" "$tag" "$tasks" 2>&1 | tee "$ROOT/simplemem-$tag.log"
  code=${PIPESTATUS[0]}
  set -e
  echo "EXIT_CODE=$code" | tee -a "$ROOT/simplemem-$tag.log"
  [[ $code = 0 ]] || exit "$code"
done
```

## framesample_remaining.sh

SHA256：`04bbb6aea8678a5c1a4aae7e496fe53317cfa42e3b84b1dd501ba32155ae1e36`。

```bash
#!/usr/bin/env bash
# 已批准预算内的剩余七局；每个步骤退出后才启动下一个。
set -euo pipefail
ROOT=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/eval-cpu-20260928
trap 'code=$?; echo "BATCH_EXIT_CODE=$code"' EXIT
grep -q '^EXIT_CODE=0$' "$ROOT/framesample-cold-pick.log"
for spec in '4 cold-demo VideoPlaceButton' '1 cpu1 PickXtimes,VideoPlaceButton' '2 cpu2 PickXtimes,VideoPlaceButton' '4 cpu4 PickXtimes,VideoPlaceButton'; do
  read -r cpus tag tasks <<< "$spec"
  export DISPATCH_EPOCH=$(date +%s.%N)
  echo "DISPATCH tag=$tag cpus=$cpus epoch=$DISPATCH_EPOCH"
  set +e
  timeout -k 30s 1800s srun --jobid=62268960 --overlap --exact --ntasks=1 --cpus-per-task="$cpus" --cpu-bind=cores --gpu_cmode=shared \
    /usr/bin/env PORT=19281 OUTPUT="$ROOT/framesample-$tag" TASKS="$tasks" ROUNDS=1 \
    /usr/bin/bash "$ROOT/framesample-prep/run_pair_guarded.sh" 2>&1 | tee "$ROOT/framesample-$tag.log"
  code=${PIPESTATUS[0]}
  set -e
  echo "EXIT_CODE=$code" | tee -a "$ROOT/framesample-$tag.log"
  [[ $code = 0 ]] || exit "$code"
done
```

## summarize.py

SHA256：`b76b6d5ef383fe8d32ce6380b3fedccbfb96ad95003627ab88ee3f35df44e4ec`。

```python
"""汇总已经落盘的小记录，不触发策略或仿真。"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
summary = []
for path in sorted(ROOT.glob('framesample-*/round-*/timing.jsonl')):
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    result_paths = list(path.parent.glob('*/ckpt*/seed*/episodes.jsonl'))
    if len(result_paths) != 1:
        continue
    results = [json.loads(line) for line in result_paths[0].read_text().splitlines() if line.strip()]
    start = next((e for e in events if e.get('record_type') == 'client_start'), {})
    case = path.parent.parent.name
    logpath = ROOT / (case + '.log')
    log = logpath.read_text() if logpath.exists() else ''
    wall = re.search(r'RUN_END wall_s=([0-9.]+)', log)
    ready = re.search(r'SERVER_READY epoch=([0-9.]+) wall_s=([0-9.]+)', log)
    dispatch = re.search(r'DISPATCH_DELAY seconds=([0-9.]+)', log)
    for result in results:
        key = result['task'], result['episode']
        ep = next(e for e in events if e.get('record_type') == 'episode' and (e['task'], e['episode']) == key)
        rpc = [e for e in events if e.get('record_type') == 'rpc_chunk' and (e['task'], e['episode']) == key]
        summary.append(dict(case=case, round=path.parent.name, cpu_count=len(start.get('affinity', [])),
            task=key[0], episode=key[1], status=result['status'], task_success=result['task_success'],
            steps=result['steps'], demo_frames=result['demo_frames'], identity=result['identity'],
            process_wall_s=float(wall[1]) if wall else None,
            server_ready_s=float(ready[2]) if ready else None,
            dispatch_s=float(dispatch[1]) if dispatch else None,
            client_import_s=start.get('import_done_epoch', 0)-start.get('entry_epoch', 0),
            episode_wall_s=ep['wall_s'], timing=ep['timing'], counts=ep['counts'],
            rpc_first3_s=[r['wall_s'] for r in rpc[:3]],
            rpc_tail_count=max(0,len(rpc)-3),
            rpc_tail_mean_s=(sum(r['wall_s'] for r in rpc[3:])/len(rpc[3:]) if len(rpc)>3 else None)))
output = ROOT / 'summary.json'
output.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
for row in summary:
    print(row['case'],row['task'],row['cpu_count'],row['steps'],row['demo_frames'],
          round(row['episode_wall_s'],3),row['process_wall_s'])
print(f'SUMMARY=PASS episode_records={len(summary)} output={output}')
```

## framesample-prep/client_probe.py

SHA256：`269f67f79d8294041cfbc82ece3ce54fc7cd2df90894f79172fc864663e870dd`。

```python
"""对消费端封装计时；不修改或覆盖 robomme 实现。"""
import json
import atexit
import os
import resource
import time
from pathlib import Path

entry_epoch = time.time()
entry_affinity = sorted(os.sched_getaffinity(0))
print("CLIENT_ENTRY " + json.dumps(dict(epoch=entry_epoch, affinity=entry_affinity)), flush=True)
import eval as target
import_done_epoch = time.time()
print("CLIENT_IMPORT_DONE " + json.dumps(dict(epoch=import_done_epoch, import_wall_s=import_done_epoch-entry_epoch)), flush=True)

timings = {}
counts = {}
records = []
rpc_events = []


def flush_records():
    with open(os.environ["TIMING_PATH"], "x") as handle:
        handle.write(json.dumps(dict(record_type="client_start", entry_epoch=entry_epoch,
                                     import_done_epoch=import_done_epoch, affinity=entry_affinity)) + "\n")
        for row in records:
            handle.write(json.dumps(row) + "\n")
        for row in rpc_events:
            handle.write(json.dumps(row) + "\n")


atexit.register(flush_records)


def measured(name, function):
    def call(*args, **kwargs):
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            timings[name] = timings.get(name, 0.0) + time.perf_counter() - started
            counts[name] = counts.get(name, 0) + 1
    return call


class TimedRunner(target.EnvRunner):
    def make_env(self, episode_id):
        timings.clear()
        counts.clear()
        return measured("make_env_s", super().make_env)(episode_id)
    get_init_obs = measured("reset_and_demo_s", target.EnvRunner.get_init_obs)
    step = measured("env_step_s", target.EnvRunner.step)
    close_env = measured("close_env_s", target.EnvRunner.close_env)


class TimedEvaluator(target.EpisodeEvaluator):
    def get_action_chunk(self, *args, **kwargs):
        started = time.perf_counter()
        epoch = time.time()
        try:
            return measured("rpc_add_buffer_and_infer_s", super().get_action_chunk)(*args, **kwargs)
        finally:
            rpc_events.append(dict(record_type="rpc_chunk", index=len(rpc_events),
                                   episode_rpc_index=counts.get("rpc_add_buffer_and_infer_s", 0)-1,
                                   epoch=epoch, wall_s=time.perf_counter()-started,
                                   task=self.active_task, episode=self.active_episode))

    def eval_each_episode(self, runner, *args, **kwargs):
        self.active_task = runner.env_id
        self.active_episode = runner.episode_id
        started = time.perf_counter()
        cpu_start = time.process_time()
        status = "error"
        try:
            status = super().eval_each_episode(runner, *args, **kwargs)
            return status
        finally:
            row = dict(record_type="episode", task=runner.env_id, episode=runner.episode_id, status=status,
                       wall_s=time.perf_counter() - started,
                       client_cpu_s=time.process_time() - cpu_start,
                       max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                       timing=timings.copy(), counts=counts.copy())
            records.append(row)
            print("EPISODE_TIMING " + json.dumps(row), flush=True)


target.EnvRunner = TimedRunner
target.EpisodeEvaluator = TimedEvaluator


class TimedRecorder(target.RolloutRecorder):
    save_video = measured("save_video_s", target.RolloutRecorder.save_video)


target.RolloutRecorder = TimedRecorder

if __name__ == "__main__":
    import tyro
    tyro.cli(target.evaluate)
```

## framesample-prep/run_pair.sh

SHA256：`8f95d000877872ef621bb55833d49ede8d0de8d5e2e26a8e2d2d24969b28d47a`。

```bash
#!/usr/bin/env bash
# 在已有占位 job 的单个 srun 内，常驻一个 server，按指定任务串行评估。
set -euo pipefail
PREP=$(cd "$(dirname "$0")" && pwd)
COMPUTE_START_EPOCH=$(date +%s.%N)
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu
: "${PORT:?}" "${OUTPUT:?}"
TASKS=${TASKS:-PickXtimes,VideoPlaceButton}
EPISODE=${EPISODE:-0}
ROUNDS=${ROUNDS:-1}
JAX_PY="$N/robomme_policy_learning_MotionJEPA/.venv/bin/python"
CLIENT_PY="$N/robomme_policy_learning-frameSamp-continue/robomme_env/bin/python"
CKPT="$N/eval-out/mmevla-ckpt/perceptual-framesamp-modul/79999"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_CACHE_DIR="$PREP/uv-cache" UV_LINK_MODE=copy
export XDG_CACHE_HOME="$PREP/cache" HF_HOME="$PREP/cache/huggingface" OPENPI_DATA_HOME="$PREP/cache/openpi"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MPLBACKEND=Agg
export __GLX_VENDOR_LIBRARY_NAME=nvidia
unset SAPIEN_DISABLE_RAY_TRACING ROBOMME_GPU_RASTER MS_SKIP_ASSET_DOWNLOAD_PROMPT
for candidate in /usr/share/vulkan/icd.d/nvidia_icd.x86_64.json /usr/share/vulkan/icd.d/nvidia_icd.json; do
  if [[ -f "$candidate" ]]; then export VK_ICD_FILENAMES="$candidate"; break; fi
done
export PYTHONPATH="$PREP/source/src:$PREP/source/packages/openpi-client/src:$PREP/../benchmark-ce3843/src:$PREP/source/examples/robomme"
export XLA_PYTHON_CLIENT_MEM_FRACTION=0.75 GLIBC_TUNABLES=glibc.rtld.optional_static_tls=16384
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export NO_PROXY=127.0.0.1,localhost
if [[ -e "$OUTPUT" ]]; then echo "OUTPUT_EXISTS=$OUTPUT"; exit 2; fi
if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then echo "PORT_BUSY=$PORT"; exit 2; fi
mkdir -p "$OUTPUT"
cd "$PREP/source"
started=$(date +%s)
echo "START epoch=$COMPUTE_START_EPOCH dispatch_epoch=${DISPATCH_EPOCH:-unknown} host=$(hostname) cpus=${SLURM_CPUS_PER_TASK:-unknown} tasks=$TASKS"
echo "THREAD_ENV OMP_NUM_THREADS=${OMP_NUM_THREADS:-unset} MKL_NUM_THREADS=${MKL_NUM_THREADS:-unset} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-unset} VK_ICD_FILENAMES=${VK_ICD_FILENAMES:-unset}"
[[ -f "$OPENPI_DATA_HOME/big_vision/paligemma_tokenizer.model" ]] || { echo TOKENIZER_MISSING; exit 5; }
if [[ -n "${DISPATCH_EPOCH:-}" ]]; then
  awk -v start="$COMPUTE_START_EPOCH" -v dispatch="$DISPATCH_EPOCH" 'BEGIN {printf "DISPATCH_DELAY seconds=%.6f\n", start-dispatch}'
fi
"$JAX_PY" scripts/serve_policy.py --seed=7 --port="$PORT" \
  policy:checkpoint --policy.dir="$CKPT" --policy.config=mme_vla_suite > >(tee "$OUTPUT/server.log") 2>&1 &
SERVER_PID=$!
cleanup() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID"
    for attempt in $(seq 1 20); do
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 0.1
    done
    kill -0 "$SERVER_PID" 2>/dev/null && kill -KILL "$SERVER_PID" || true
    wait "$SERVER_PID" || true
  fi
}
trap cleanup EXIT
ready=0
for attempt in $(seq 1 600); do
  kill -0 "$SERVER_PID" 2>/dev/null || { echo SERVER_DIED; exit 3; }
  if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then ready=1; break; fi
  sleep 2
done
[[ "$ready" = 1 ]] || { echo SERVER_TIMEOUT; exit 4; }
echo "SERVER_READY epoch=$(date +%s.%N) wall_s=$(( $(date +%s) - started ))"
for round in $(seq 1 "$ROUNDS"); do
  round_dir="$OUTPUT/round-$round"
  mkdir -p "$round_dir"
  export TIMING_PATH="$round_dir/timing.jsonl"
  uv run --offline --no-project --python "$CLIENT_PY" --with cryptography==44.0.3 python "$PREP/client_probe.py" \
    --args.host=127.0.0.1 --args.port="$PORT" --args.model_seed=7 --args.model_ckpt_id=79999 \
    --args.policy_name=framesample-cpu --args.only_tasks="$TASKS" --args.episode_start="$EPISODE" \
    --args.episode_stride=1 --args.max_episodes=1 --args.save_dir="$round_dir" 2>&1 | tee "$round_dir/client.log"
done
echo "RUN_END wall_s=$(( $(date +%s) - started ))"
```

## framesample-prep/run_pair_guarded.sh

SHA256：`db37bd2735cb452bf6c4cedce06b6556a1f89088b03f63b8baf9e190a0d5e324`。

```bash
#!/usr/bin/env bash
# 在已有占位 job 的单个 srun 内，常驻一个 server，按指定任务串行评估。
set -euo pipefail
PREP=$(cd "$(dirname "$0")" && pwd)
COMPUTE_START_EPOCH=$(date +%s.%N)
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu
: "${PORT:?}" "${OUTPUT:?}"
TASKS=${TASKS:-PickXtimes,VideoPlaceButton}
EPISODE=${EPISODE:-0}
ROUNDS=${ROUNDS:-1}
JAX_PY="$N/robomme_policy_learning_MotionJEPA/.venv/bin/python"
CLIENT_PY="$N/robomme_policy_learning-frameSamp-continue/robomme_env/bin/python"
CKPT="$N/eval-out/mmevla-ckpt/perceptual-framesamp-modul/79999"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_CACHE_DIR="$PREP/uv-cache" UV_LINK_MODE=copy
export XDG_CACHE_HOME="$PREP/cache" HF_HOME="$PREP/cache/huggingface" OPENPI_DATA_HOME="$PREP/cache/openpi"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MPLBACKEND=Agg
export __GLX_VENDOR_LIBRARY_NAME=nvidia
unset SAPIEN_DISABLE_RAY_TRACING ROBOMME_GPU_RASTER MS_SKIP_ASSET_DOWNLOAD_PROMPT
for candidate in /usr/share/vulkan/icd.d/nvidia_icd.x86_64.json /usr/share/vulkan/icd.d/nvidia_icd.json; do
  if [[ -f "$candidate" ]]; then export VK_ICD_FILENAMES="$candidate"; break; fi
done
export PYTHONPATH="$PREP/source/src:$PREP/source/packages/openpi-client/src:$PREP/../benchmark-ce3843/src:$PREP/source/examples/robomme"
export XLA_PYTHON_CLIENT_MEM_FRACTION=0.75 GLIBC_TUNABLES=glibc.rtld.optional_static_tls=16384
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export NO_PROXY=127.0.0.1,localhost
if [[ -e "$OUTPUT" ]]; then echo "OUTPUT_EXISTS=$OUTPUT"; exit 2; fi
if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then echo "PORT_BUSY=$PORT"; exit 2; fi
mkdir -p "$OUTPUT"
cd "$PREP/source"
started=$(date +%s)
echo "START epoch=$COMPUTE_START_EPOCH dispatch_epoch=${DISPATCH_EPOCH:-unknown} host=$(hostname) cpus=${SLURM_CPUS_PER_TASK:-unknown} tasks=$TASKS"
echo "THREAD_ENV OMP_NUM_THREADS=${OMP_NUM_THREADS:-unset} MKL_NUM_THREADS=${MKL_NUM_THREADS:-unset} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-unset} VK_ICD_FILENAMES=${VK_ICD_FILENAMES:-unset}"
[[ -f "$OPENPI_DATA_HOME/big_vision/paligemma_tokenizer.model" ]] || { echo TOKENIZER_MISSING; exit 5; }
if [[ -n "${DISPATCH_EPOCH:-}" ]]; then
  awk -v start="$COMPUTE_START_EPOCH" -v dispatch="$DISPATCH_EPOCH" 'BEGIN {printf "DISPATCH_DELAY seconds=%.6f\n", start-dispatch}'
fi
"$JAX_PY" scripts/serve_policy.py --seed=7 --port="$PORT" \
  policy:checkpoint --policy.dir="$CKPT" --policy.config=mme_vla_suite > >(tee "$OUTPUT/server.log") 2>&1 &
SERVER_PID=$!
cleanup() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID"
    for attempt in $(seq 1 20); do
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 0.1
    done
    kill -0 "$SERVER_PID" 2>/dev/null && kill -KILL "$SERVER_PID" || true
    wait "$SERVER_PID" || true
  fi
}
trap cleanup EXIT
ready=0
for attempt in $(seq 1 600); do
  kill -0 "$SERVER_PID" 2>/dev/null || { echo SERVER_DIED; exit 3; }
  if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then ready=1; break; fi
  sleep 2
done
[[ "$ready" = 1 ]] || { echo SERVER_TIMEOUT; exit 4; }
echo "SERVER_READY epoch=$(date +%s.%N) wall_s=$(( $(date +%s) - started ))"
for round in $(seq 1 "$ROUNDS"); do
  round_dir="$OUTPUT/round-$round"
  mkdir -p "$round_dir"
  export TIMING_PATH="$round_dir/timing.jsonl"
  uv run --offline --no-project --python "$CLIENT_PY" --with cryptography==44.0.3 python "$PREP/client_probe.py" \
    --args.host=127.0.0.1 --args.port="$PORT" --args.model_seed=7 --args.model_ckpt_id=79999 \
    --args.policy_name=framesample-cpu --args.only_tasks="$TASKS" --args.episode_start="$EPISODE" \
    --args.episode_stride=1 --args.max_episodes=1 --args.save_dir="$round_dir" 2>&1 | tee "$round_dir/client.log"
  "$JAX_PY" "$PREP/completion_guard.py" \
    --episodes "$round_dir/framesample-cpu/ckpt79999/seed7/episodes.jsonl" \
    --tasks "$TASKS" --episode "$EPISODE"
done
echo "RUN_END wall_s=$(( $(date +%s) - started ))"
```

## framesample-prep/completion_guard.py

SHA256：`ae7dc982f97f9dbf5d8fff7a8f5d370502cf3a88590c60715386c93b38882ef7`。

```python
"""只读核验逐局结果；不会导入仿真或策略依赖。"""
import argparse
import json
import re
from pathlib import Path


def validate(path, tasks, episode):
    expected = {(task, episode) for task in tasks}
    if len(expected) != len(tasks):
        raise ValueError("任务参数重复")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    actual = [(row["task"], row["episode"]) for row in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError(f"身份缺失、重复或多余：expected={sorted(expected)} actual={actual}")
    for row in rows:
        if row["status"] not in {"success", "fail", "timeout"}:
            raise ValueError(f"异常终态：{row['task']} {row['status']}")
        if row.get("task_success") is not (row["status"] == "success"):
            raise ValueError("任务成功字段与终态冲突")
        binding = row["spec_binding"]
        if binding.get("available") is not True or binding.get("mode") != "replay":
            raise ValueError("规格绑定不可用或非回放")
        if binding.get("injected_mismatch") != 0 or binding.get("unused") != 0:
            raise ValueError("规格回注不一致、未消费或缺少计数")
        if not re.fullmatch(r"[a-f0-9]{64}", binding.get("spec_sha256") or ""):
            raise ValueError("缺少规格指纹")
        if binding["spec_sha256"] != row["identity"]["spec_sha256"]:
            raise ValueError("规格绑定指纹与身份指纹不一致")
        if not isinstance(binding.get("value_points"), int) or binding["value_points"] <= 0:
            raise ValueError("规格取值点为空或缺失")
        if episode != 0 or row["tier"] != "xhard1" or row["max_steps"] != 1500:
            raise ValueError("本次固定第0局必须为xhard1且步数上限1500")
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--episode", type=int, required=True)
    args = parser.parse_args()
    try:
        count = validate(args.episodes, args.tasks.split(","), args.episode)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"FRAME_COMPLETION=FAIL reason={error}")
        raise SystemExit(1)
    print(f"FRAME_COMPLETION=PASS episodes={count} infra_errors=0 binding_mismatch=0")


if __name__ == "__main__":
    main()
```

## framesample-prep/client_rounds_probe.py

SHA256：`1869cfdb3cc8d0ac757330f5261cba2beebdaec80261536fc3f55a834f33b113`。

```python
"""一次导入，逐轮复用同一消费进程；每轮守卫通过后才继续。"""
import atexit
import dataclasses
import json
import os
from pathlib import Path
import time

import client_probe as observer
from completion_guard import validate

target = observer.target
atexit.unregister(observer.flush_records)


def run_rounds(args: target.Args, rounds: int = 1):
    if rounds < 1 or args.model_seed != 7 or args.episode_start != 0 or args.max_episodes != 1:
        raise ValueError("本轮固定seed7、第0局、每任务1局，轮数必须为正")
    if not args.only_tasks or args.overwrite:
        raise ValueError("必须显式给任务且禁止覆盖输出")
    root = Path(args.save_dir)
    root.mkdir(parents=True, exist_ok=True)
    boundaries = []
    try:
        for round_index in range(1, rounds + 1):
            directory = root / f"round-{round_index}"
            directory.mkdir(exist_ok=False)
            os.environ["TIMING_PATH"] = str(directory / "timing.jsonl")
            observer.records.clear()
            observer.rpc_events.clear()
            observer.timings.clear()
            observer.counts.clear()
            round_args = dataclasses.replace(args, save_dir=str(directory))
            boundary = dict(round=round_index, start_epoch=time.time(), pid=os.getpid())
            boundaries.append(boundary)
            print("ROUND_START " + json.dumps(boundary), flush=True)
            try:
                target.evaluate(round_args)
                episodes = directory / args.policy_name / f"ckpt{args.model_ckpt_id}" / f"seed{args.model_seed}" / "episodes.jsonl"
                count = validate(episodes, args.only_tasks.split(","), args.episode_start)
                print(f"FRAME_COMPLETION=PASS round={round_index} episodes={count}", flush=True)
                boundary["guard"] = "PASS"
            except BaseException:
                boundary["guard"] = "FAIL"
                raise
            finally:
                boundary["end_epoch"] = time.time()
                boundary["wall_s"] = boundary["end_epoch"] - boundary["start_epoch"]
                observer.flush_records()
                print("ROUND_END " + json.dumps(boundary), flush=True)
    finally:
        with (root / "round-boundaries.json").open("x") as handle:
            json.dump(dict(pid=os.getpid(), client_entry_epoch=observer.entry_epoch,
                           client_import_done_epoch=observer.import_done_epoch,
                           rounds=boundaries), handle, indent=2)


if __name__ == "__main__":
    import tyro
    tyro.cli(run_rounds)
```

## framesample-prep/run_rounds.sh

SHA256：`5692338c48fb0e5d161ac424eb1eda147d4436c36d03b17bf4a7ab3ead3f494b`。

```bash
#!/usr/bin/env bash
# 在已有占位 job 的单个 srun 内，server 和 client 均只启动一次。
set -euo pipefail
PREP=$(cd "$(dirname "$0")" && pwd)
COMPUTE_START_EPOCH=$(date +%s.%N)
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu
: "${PORT:?}" "${OUTPUT:?}"
TASKS=${TASKS:-PickXtimes,VideoPlaceButton}
EPISODE=${EPISODE:-0}
ROUNDS=${ROUNDS:-1}
JAX_PY="$N/robomme_policy_learning_MotionJEPA/.venv/bin/python"
CLIENT_PY="$N/robomme_policy_learning-frameSamp-continue/robomme_env/bin/python"
CKPT="$N/eval-out/mmevla-ckpt/perceptual-framesamp-modul/79999"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_CACHE_DIR="$PREP/uv-cache" UV_LINK_MODE=copy
export XDG_CACHE_HOME="$PREP/cache" HF_HOME="$PREP/cache/huggingface" OPENPI_DATA_HOME="$PREP/cache/openpi"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MPLBACKEND=Agg
export __GLX_VENDOR_LIBRARY_NAME=nvidia
unset SAPIEN_DISABLE_RAY_TRACING ROBOMME_GPU_RASTER MS_SKIP_ASSET_DOWNLOAD_PROMPT
for candidate in /usr/share/vulkan/icd.d/nvidia_icd.x86_64.json /usr/share/vulkan/icd.d/nvidia_icd.json; do
  if [[ -f "$candidate" ]]; then export VK_ICD_FILENAMES="$candidate"; break; fi
done
export PYTHONPATH="$PREP/source/src:$PREP/source/packages/openpi-client/src:$PREP/../benchmark-ce3843/src:$PREP/source/examples/robomme"
export XLA_PYTHON_CLIENT_MEM_FRACTION=0.75 GLIBC_TUNABLES=glibc.rtld.optional_static_tls=16384
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export NO_PROXY=127.0.0.1,localhost
if [[ -e "$OUTPUT" ]]; then echo "OUTPUT_EXISTS=$OUTPUT"; exit 2; fi
if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then echo "PORT_BUSY=$PORT"; exit 2; fi
mkdir -p "$OUTPUT"
cd "$PREP/source"
started=$(date +%s)
echo "START epoch=$COMPUTE_START_EPOCH dispatch_epoch=${DISPATCH_EPOCH:-unknown} host=$(hostname) cpus=${SLURM_CPUS_PER_TASK:-unknown} tasks=$TASKS"
echo "THREAD_ENV OMP_NUM_THREADS=${OMP_NUM_THREADS:-unset} MKL_NUM_THREADS=${MKL_NUM_THREADS:-unset} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-unset} VK_ICD_FILENAMES=${VK_ICD_FILENAMES:-unset}"
[[ -f "$OPENPI_DATA_HOME/big_vision/paligemma_tokenizer.model" ]] || { echo TOKENIZER_MISSING; exit 5; }
if [[ -n "${DISPATCH_EPOCH:-}" ]]; then
  awk -v start="$COMPUTE_START_EPOCH" -v dispatch="$DISPATCH_EPOCH" 'BEGIN {printf "DISPATCH_DELAY seconds=%.6f\n", start-dispatch}'
fi
"$JAX_PY" scripts/serve_policy.py --seed=7 --port="$PORT" \
  policy:checkpoint --policy.dir="$CKPT" --policy.config=mme_vla_suite > >(tee "$OUTPUT/server.log") 2>&1 &
SERVER_PID=$!
cleanup() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID"
    for attempt in $(seq 1 20); do
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 0.1
    done
    kill -0 "$SERVER_PID" 2>/dev/null && kill -KILL "$SERVER_PID" || true
    wait "$SERVER_PID" || true
  fi
}
trap cleanup EXIT
ready=0
for attempt in $(seq 1 600); do
  kill -0 "$SERVER_PID" 2>/dev/null || { echo SERVER_DIED; exit 3; }
  if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then ready=1; break; fi
  sleep 2
done
[[ "$ready" = 1 ]] || { echo SERVER_TIMEOUT; exit 4; }
echo "SERVER_READY epoch=$(date +%s.%N) wall_s=$(( $(date +%s) - started ))"
  uv run --offline --no-project --python "$CLIENT_PY" --with cryptography==44.0.3 python "$PREP/client_rounds_probe.py" \
    --rounds="$ROUNDS" \
    --args.host=127.0.0.1 --args.port="$PORT" --args.model_seed=7 --args.model_ckpt_id=79999 \
    --args.policy_name=framesample-cpu --args.only_tasks="$TASKS" --args.episode_start="$EPISODE" \
    --args.episode_stride=1 --args.max_episodes=1 --args.save_dir="$OUTPUT" 2>&1 | tee "$OUTPUT/client.log"
echo "RUN_END wall_s=$(( $(date +%s) - started ))"
```
