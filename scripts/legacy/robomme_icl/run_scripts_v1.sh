#!/usr/bin/env bash
# 本次固定96条交付的维护验收启动器；日常使用scripts根的四个入口。
set -euo pipefail
ICL_REPO_PATH="$(cd "$(dirname "$0")/../../.." && pwd -P)"
ICL_EXPECTED_COMMIT="${1:?需要已提交的干净基线SHA}"
ICL_RUN_ROOT="$ICL_REPO_PATH/artifacts/generated/robomme-icl/scripts-v1"
ICL_REPORT_ROOT="$ICL_REPO_PATH/artifacts/reports/robomme-icl/scripts-v1"
cd "$ICL_REPO_PATH"
unset VIRTUAL_ENV
export PYTHONUNBUFFERED=1
export UV_CACHE_DIR="$ICL_REPO_PATH/.cache/uv"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
command -v uv
uv run --no-sync python -B - "$ICL_EXPECTED_COMMIT" <<'PY'
from datetime import datetime, timezone
import hashlib,json,os,subprocess,sys
from pathlib import Path
root=Path.cwd()
sys.path.insert(0,str(root/'scripts'))
from _icl.common import script_fingerprint
from robomme_icl.runtime import configure_runtime
from robomme_icl.io.fingerprint import runtime_fingerprint
from robomme_icl.suite import load_suite
configure_runtime()
sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
status=subprocess.check_output(['git','status','--porcelain'],text=True)
if sha!=sys.argv[1] or status:raise RuntimeError('正式运行必须从指定的干净提交启动：'+sha+' '+status)
output=root/'artifacts/generated/robomme-icl/scripts-v1'
report=root/'artifacts/reports/robomme-icl/scripts-v1'
if output.exists():raise RuntimeError('固定数据输出已存在，拒绝覆盖')
allowed_reports={'IMPLEMENTATION.md','development.json','cleanup_inventory.json'}
if report.exists() and {p.name for p in report.iterdir()}-allowed_reports:
    raise RuntimeError('固定验收报告已有运行产物，拒绝覆盖')
source=root/'artifacts/generated/robomme-icl/validation24-v3/suite.json'
suite=load_suite(source)
if len(suite['episodes'])!=96:raise RuntimeError('源清单必须包含96条')
script=root/'scripts/legacy/robomme_icl/run_scripts_v1.sh'
context={'source_commit':sha,'start_status':status,'started_at_utc':datetime.now(timezone.utc).isoformat(),
 'session':'gen-icl-scripts-v1-20260908','scripts_hash':script_fingerprint(),
 'source_suite':str(source),'source_suite_hash':suite['suite_hash'],
 'runtime_fingerprints':{str(g):runtime_fingerprint(render_gpu=g) for g in (0,1)},
 'legacy_tree':subprocess.check_output(['git','rev-parse','HEAD:src/robomme'],text=True).strip(),
 'uv_lock_hash':hashlib.sha256((root/'uv.lock').read_bytes()).hexdigest(),
 'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),'script':script.read_text(),
 'gpus':[0,1],'workers':32,'video_workers':4,'verification_workers':4,'episode_batch_size':1,
 'timeout_seconds':1200,'cpu_affinity':sorted(os.sched_getaffinity(0)),
 'storage':subprocess.check_output(['findmnt','-T',str(root),'-n','-o','TARGET,SOURCE,FSTYPE'],text=True).strip(),
 'ffmpeg_version':subprocess.check_output(['/usr/bin/ffmpeg','-version'],text=True).splitlines()[0],
 'task_config':suite['configs']['task'],'position_config':suite['configs']['position']}
report.mkdir(parents=True,exist_ok=True)
with (report/'run_context.json').open('x') as f:json.dump(context,f,ensure_ascii=False,indent=2)
print('正式四入口验收基线：'+sha,flush=True)
PY
mkdir -p "$ICL_RUN_ROOT/logs"
ICL_GPU_SAMPLER_PID=""
icl_cleanup() {
    local icl_exit=$?
    trap - EXIT HUP INT TERM
    if [[ -n "$ICL_GPU_SAMPLER_PID" ]]; then
        kill "$ICL_GPU_SAMPLER_PID" 2>/dev/null || true
        wait "$ICL_GPU_SAMPLER_PID" 2>/dev/null || true
    fi
    printf 'EXIT_CODE=%s\n' "$icl_exit" >> "$ICL_REPORT_ROOT/main.log"
    exit "$icl_exit"
}
trap icl_cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
nvidia-smi --query-gpu=timestamp,index,utilization.gpu,memory.used --format=csv,noheader -lms 500 > "$ICL_REPORT_ROOT/gpu_samples.csv" &
ICL_GPU_SAMPLER_PID=$!
printf 'GPU_SAMPLER_PID=%s\n' "$ICL_GPU_SAMPLER_PID" > "$ICL_REPORT_ROOT/sampler_pids.log"
printf 'phase\tstart_epoch_ns\tend_epoch_ns\tcommand_exit\ttee_exit\n' > "$ICL_REPORT_ROOT/phase_timings.tsv"
icl_phase() {
    local icl_name="$1"
    shift
    local icl_start icl_end
    icl_start="$(date +%s%N)"
    printf 'START %s %s\n' "$icl_name" "$(date --iso-8601=seconds)" | tee -a "$ICL_REPORT_ROOT/main.log"
    set +e
    "$@" 2>&1 | tee "$ICL_RUN_ROOT/logs/$icl_name.log"
    local -a icl_status=("${PIPESTATUS[@]}")
    set -e
    icl_end="$(date +%s%N)"
    local icl_result="${icl_status[0]}"
    if [[ "$icl_result" -eq 0 && "${icl_status[1]}" -ne 0 ]]; then icl_result="${icl_status[1]}"; fi
    printf 'EXIT_CODE=%s\n' "$icl_result" >> "$ICL_RUN_ROOT/logs/$icl_name.log"
    printf '%s\t%s\t%s\t%s\t%s\n' "$icl_name" "$icl_start" "$icl_end" "${icl_status[0]}" "${icl_status[1]}" >> "$ICL_REPORT_ROOT/phase_timings.tsv"
    printf 'FINISH %s EXIT_CODE=%s\n' "$icl_name" "$icl_result" | tee -a "$ICL_REPORT_ROOT/main.log"
    return "$icl_result"
}
icl_phase prepare uv run --no-sync python scripts/prepare_suite.py --source-suite artifacts/generated/robomme-icl/validation24-v3/suite.json --output-dir "$ICL_RUN_ROOT" --workers 32
# 仅保留本次认证所用来源清单快照；原始大数据在全部验收成功后按用户要求清理。
command -v uv > /dev/null
uv run --no-sync python -B - <<'PY'
from pathlib import Path
root=Path.cwd()
source=root/'artifacts/generated/robomme-icl/validation24-v3/suite.json'
target=root/'artifacts/generated/robomme-icl/scripts-v1/provenance/source_suite.json'
target.parent.mkdir(parents=True,exist_ok=True)
with target.open('xb') as stream:stream.write(source.read_bytes())
PY
icl_phase generate uv run --no-sync python scripts/generate_dataset.py --suite "$ICL_RUN_ROOT/suite" --output-dir "$ICL_RUN_ROOT" --workers 32 --video-workers 4
icl_phase replay uv run --no-sync python scripts/replay_dataset.py --input "$ICL_RUN_ROOT/hdf5_files" --output-dir "$ICL_RUN_ROOT/replay" --workers 32 --video-workers 4
icl_phase plot uv run --no-sync python scripts/plot_distribution.py --suite "$ICL_RUN_ROOT/suite" --output-dir "$ICL_RUN_ROOT/distributions"
icl_phase verify uv run --no-sync python scripts/legacy/robomme_icl/verify_scripts_bundle.py --run-root "$ICL_RUN_ROOT" --source-suite "$ICL_RUN_ROOT/provenance/source_suite.json" --report-dir "$ICL_REPORT_ROOT" --workers 4
