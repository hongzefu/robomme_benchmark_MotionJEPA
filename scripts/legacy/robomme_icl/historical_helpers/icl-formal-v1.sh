#!/usr/bin/env bash
set -euo pipefail
ICL_REPO_PATH=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
ICL_RUN_REPORT="$ICL_REPO_PATH/artifacts/reports/robomme-icl/formal-v1"
ICL_SUITE="$ICL_REPO_PATH/artifacts/generated/robomme-icl/validation24"
ICL_VERIFY="$ICL_REPO_PATH/artifacts/generated/robomme-icl/validation24-verification"
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
trap 'icl_exit=$?; printf "EXIT_CODE=%s\n" "$icl_exit" >> "$ICL_RUN_REPORT/main.log"' EXIT
command -v uv
uv run --no-sync python -B - <<'PY'
import hashlib,json,subprocess
from pathlib import Path
from robomme_icl.io.fingerprint import runtime_fingerprint,source_commit
root=Path.cwd()
status=subprocess.check_output(['git','status','--porcelain'],text=True)
if status:
    raise RuntimeError('正式运行启动时工作区不干净：'+status)
sha=source_commit()
if sha!='3e56b223607801ca0dd596dacbd17b4458d9981b':
    raise RuntimeError('正式运行提交基线已改变：'+sha)
script=root/'scripts/legacy/robomme_icl/historical_helpers/icl-formal-v1.sh'
record={
 'source_commit':sha,'start_status':status,
 'legacy_tree':subprocess.check_output(['git','rev-parse','HEAD:src/robomme'],text=True).strip(),
 'runtime_fingerprint':runtime_fingerprint(),
 'task_config':json.loads((root/'src/robomme_icl/configs/task_distribution.json').read_text()),
 'position_config':json.loads((root/'src/robomme_icl/configs/position_distribution.json').read_text()),
 'session':'gen-icl-cert96-20260907-v1','storage':'/data NVMe ext4',
 'episode_batch_size':1,'prepare_workers':4,'generation_workers':1,'replay_workers':4,'reset_workers':4,
 'simulation':'physx_cpu','render_device':'cuda:0',
 'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),'script':script.read_text(),
 'scope':{'tasks':4,'episodes_per_task':24,'per_difficulty':8,'total':96},
}
path=root/'artifacts/reports/robomme-icl/formal-v1/run_context.json'
with path.open('x') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print('正式运行基线：'+sha,flush=True)
PY

icl_phase() {
    local icl_name="$1"
    shift
    printf 'START %s\n' "$icl_name" | tee -a "$ICL_RUN_REPORT/main.log"
    set +e
    "$@" 2>&1 | tee "$ICL_RUN_REPORT/$icl_name.log"
    local icl_result=${PIPESTATUS[0]}
    set -e
    printf 'EXIT_CODE=%s\n' "$icl_result" >> "$ICL_RUN_REPORT/$icl_name.log"
    printf 'FINISH %s EXIT_CODE=%s\n' "$icl_name" "$icl_result" | tee -a "$ICL_RUN_REPORT/main.log"
    return "$icl_result"
}

# 首先在已提交源码重新完成四任务最小认证，再进入完整规模。
icl_phase baseline-smoke uv run --no-sync python scripts/legacy/robomme_icl/cli.py prepare --output "$ICL_REPO_PATH/artifacts/generated/robomme-icl/baseline-smoke-3e56b22" --episodes-per-task 1 --workers 4 --max-candidates 64
icl_phase certification96 uv run --no-sync python scripts/legacy/robomme_icl/cli.py prepare --output "$ICL_SUITE" --workers 4
icl_phase generate-reverse-w1 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode generate --workers 1 --reverse
icl_phase resume-forward-w4 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode resume --workers 4
icl_phase replay-forward-w4 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode replay --workers 4
icl_phase reset-reverse-w4 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode reset --workers 4 --reverse
