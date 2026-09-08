#!/usr/bin/env bash
set -euo pipefail
ICL_REPO_PATH=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
ICL_EXPECTED_COMMIT="$1"
ICL_RUN_REPORT="$ICL_REPO_PATH/artifacts/reports/robomme-icl/formal-dualgpu-v2"
ICL_SUITE="$ICL_REPO_PATH/artifacts/generated/robomme-icl/validation24-dualgpu"
ICL_VERIFY="$ICL_REPO_PATH/artifacts/generated/robomme-icl/validation24-dualgpu-verification"
cd "$ICL_REPO_PATH"
export PYTHONUNBUFFERED=1
export UV_CACHE_DIR="$ICL_REPO_PATH/.cache/uv"
export MS_ASSET_DIR="$ICL_REPO_PATH/.cache/maniskill"
export MPLCONFIGDIR="$ICL_REPO_PATH/.cache/matplotlib"
export XDG_CACHE_HOME="$ICL_REPO_PATH/.cache/xdg"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
test ! -e "$ICL_RUN_REPORT/run_context.json"
mkdir -p "$ICL_RUN_REPORT"
command -v uv
uv run --no-sync python -B - "$ICL_EXPECTED_COMMIT" <<'PY'
import hashlib,json,os,subprocess,sys
from pathlib import Path
from robomme_icl.runtime import configure_runtime
from robomme_icl.io.fingerprint import runtime_fingerprint,source_commit
from robomme_icl.suite import load_suite
configure_runtime()
root=Path.cwd()
status=subprocess.check_output(['git','status','--porcelain'],text=True)
if status:
    raise RuntimeError('正式运行启动时工作区不干净：'+status)
sha=source_commit()
if sha!=sys.argv[1]:
    raise RuntimeError('正式运行提交基线已改变：'+sha)
fps={str(gpu):runtime_fingerprint(render_gpu=gpu) for gpu in (0,1)}
smoke=load_suite(root/'artifacts/generated/robomme-icl/dual-gpu-smoke')
for cert in smoke['certification'].values():
    if cert['runtime_fingerprint']!=fps[str(cert['render_gpu'])]:
        raise RuntimeError('提交后源码与已通过的双卡smoke字节指纹不同')
script=root/'scripts/legacy/robomme_icl/historical_helpers/icl-formal-dualgpu-v2.sh'
record={
 'source_commit':sha,'start_status':status,
 'legacy_tree':subprocess.check_output(['git','rev-parse','HEAD:src/robomme'],text=True).strip(),
 'runtime_fingerprints':fps,
 'task_config':json.loads((root/'src/robomme_icl/configs/task_distribution.json').read_text()),
 'position_config':json.loads((root/'src/robomme_icl/configs/position_distribution.json').read_text()),
 'session':'gen-icl-cert96-dualgpu-20260907-v2','storage':'/data NVMe ext4',
 'episode_batch_size':1,'prepare_workers':32,'generation_workers':32,'replay_workers':32,'reset_workers':32,
 'cpu_affinity':sorted(os.sched_getaffinity(0)),
 'simulation':'physx_cpu','render_devices':[0,1],'gpu_binding':'sorted(gpus)[seed % len(gpus)]',
 'timeout_seconds':1200,'gpu_sample_interval_ms':500,
 'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),'script':script.read_text(),
 'scope':{'tasks':4,'episodes_per_task':24,'per_difficulty':8,'total':96},
}
path=root/'artifacts/reports/robomme-icl/formal-dualgpu-v2/run_context.json'
with path.open('x') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print('正式双卡运行基线：'+sha,flush=True)
PY

# 仅管理本脚本启动且记录了PID的两个采样进程。
nvidia-smi --query-gpu=timestamp,index,utilization.gpu,memory.used --format=csv,noheader -lms 500 > "$ICL_RUN_REPORT/gpu_samples.csv" &
ICL_GPU_SAMPLER_PID=$!
iostat -xz -y 2 > "$ICL_RUN_REPORT/iostat.log" &
ICL_IO_SAMPLER_PID=$!
printf 'GPU_SAMPLER_PID=%s\nIO_SAMPLER_PID=%s\n' "$ICL_GPU_SAMPLER_PID" "$ICL_IO_SAMPLER_PID" > "$ICL_RUN_REPORT/sampler_pids.log"
icl_cleanup() {
    local icl_exit=$?
    trap - EXIT HUP INT TERM
    kill "$ICL_GPU_SAMPLER_PID" "$ICL_IO_SAMPLER_PID" 2>/dev/null || true
    wait "$ICL_GPU_SAMPLER_PID" "$ICL_IO_SAMPLER_PID" 2>/dev/null || true
    printf 'EXIT_CODE=%s\n' "$icl_exit" >> "$ICL_RUN_REPORT/main.log"
    exit "$icl_exit"
}
trap icl_cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

icl_phase() {
    local icl_name="$1"
    shift
    printf 'START %s %s\n' "$icl_name" "$(date --iso-8601=seconds)" | tee -a "$ICL_RUN_REPORT/main.log"
    set +e
    "$@" 2>&1 | tee "$ICL_RUN_REPORT/$icl_name.log"
    local icl_result=${PIPESTATUS[0]}
    set -e
    printf 'EXIT_CODE=%s\n' "$icl_result" >> "$ICL_RUN_REPORT/$icl_name.log"
    printf 'FINISH %s EXIT_CODE=%s %s\n' "$icl_name" "$icl_result" "$(date --iso-8601=seconds)" | tee -a "$ICL_RUN_REPORT/main.log"
    return "$icl_result"
}

icl_phase certification96 uv run --no-sync python scripts/legacy/robomme_icl/cli.py prepare --output "$ICL_SUITE" --gpus 0,1 --workers 32 --timeout-seconds 1200
icl_phase generate-reverse-w32 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode generate --workers 32 --reverse --timeout-seconds 1200
icl_phase resume-forward-w4 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode resume --workers 4 --timeout-seconds 1200
icl_phase replay-forward-w32 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode replay --workers 32 --timeout-seconds 1200
icl_phase reset-reverse-w32 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode reset --workers 32 --reverse --timeout-seconds 1200
icl_phase plots uv run --no-sync python scripts/legacy/robomme_icl/plot_suite.py --suite "$ICL_SUITE" --output "$ICL_RUN_REPORT/figures"
