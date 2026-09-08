#!/usr/bin/env bash
set -euo pipefail

ICL_REPO_PATH=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
ICL_EXPECTED_COMMIT="${1:?用法：bash scripts/legacy/robomme_icl/historical_helpers/icl-formal-v3.sh <已提交基线SHA>}"
ICL_RUN_REPORT="$ICL_REPO_PATH/artifacts/reports/robomme-icl/formal-v3"
ICL_SUITE="$ICL_REPO_PATH/artifacts/generated/robomme-icl/validation24-v3"
ICL_VERIFY="$ICL_REPO_PATH/artifacts/generated/robomme-icl/validation24-v3-verification"
ICL_VERIFY_W16="$ICL_REPO_PATH/artifacts/generated/robomme-icl/validation24-v3-verification-w16"
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

command -v uv
command -v nvidia-smi
command -v iostat
uv run --no-sync python -B - "$ICL_EXPECTED_COMMIT" <<'PY'
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from robomme_icl.runtime import configure_runtime
from robomme_icl.io.fingerprint import runtime_fingerprint, source_commit
from robomme_icl.io.paths import output_path
from robomme_icl.suite import load_configs, load_suite, plan_slots

configure_runtime()
root = Path.cwd()
status = subprocess.check_output(["git", "status", "--porcelain"], text=True)
if status:
    raise RuntimeError("正式运行启动时工作区不干净：" + status)
sha = source_commit()
if sha != sys.argv[1]:
    raise RuntimeError("正式运行提交基线已改变：" + sha)

report = output_path(root / "artifacts/reports/robomme-icl/formal-v3")
suite = output_path(root / "artifacts/generated/robomme-icl/validation24-v3")
primary = output_path(root / "artifacts/generated/robomme-icl/validation24-v3-verification")
comparison = output_path(root / "artifacts/generated/robomme-icl/validation24-v3-verification-w16")
if report.exists() and any(report.iterdir()):
    raise RuntimeError("报告目录已有内容，拒绝覆盖：" + str(report))
for path in (suite, primary, comparison):
    if path.exists():
        raise RuntimeError("正式认证与匹配吞吐对照必须使用全新输出目录，拒绝复用：" + str(path))

fingerprints = {str(gpu): runtime_fingerprint(render_gpu=gpu) for gpu in (0, 1)}
smoke_path = root / "artifacts/generated/robomme-icl/smoke-v3"
smoke = load_suite(smoke_path)
if {row["task_kind"] for row in smoke["episodes"]} != {"BinFill", "RouteStick", "VideoUnmaskSwap", "VideoRepick"}:
    raise RuntimeError("smoke-v3 尚未覆盖全部四任务")
if {cert["render_gpu"] for cert in smoke["certification"].values()} != {0, 1}:
    raise RuntimeError("smoke-v3 尚未覆盖两张 GPU")
for certification in smoke["certification"].values():
    if certification["runtime_fingerprint"] != fingerprints[str(certification["render_gpu"])]:
        raise RuntimeError("提交后源码与 smoke-v3 的双卡认证指纹不同")

configs = load_configs()
slots = plan_slots(*configs)
task_counts = Counter(slot["task_kind"] for slot in slots)
difficulty_counts = Counter((slot["task_kind"], slot["difficulty"]) for slot in slots)
if len(slots) != 96 or set(task_counts.values()) != {24} or set(difficulty_counts.values()) != {8}:
    raise RuntimeError("正式范围必须为四任务各24条、每难度8条，总计96条")

script = root / "scripts/legacy/robomme_icl/historical_helpers/icl-formal-v3.sh"
record = {
    "source_commit": sha,
    "start_status": status,
    "started_at_utc": datetime.now(timezone.utc).isoformat(),
    "host_timezone": str(datetime.now().astimezone().tzinfo),
    "legacy_tree": subprocess.check_output(["git", "rev-parse", "HEAD:src/robomme"], text=True).strip(),
    "runtime_fingerprints": fingerprints,
    "smoke_suite": str(smoke_path),
    "smoke_suite_hash": smoke["suite_hash"],
    "task_config": configs[0],
    "position_config": configs[1],
    "session": "gen-icl-cert96-dualgpu-20260907-v3",
    "storage": subprocess.check_output(["findmnt", "-T", str(root), "-n", "-o", "TARGET,SOURCE,FSTYPE"], text=True).strip(),
    "episode_batch_size": 1,
    "prepare_workers": 32,
    "generation_workers": 32,
    "comparison_generation_workers": 16,
    "resume_workers": 4,
    "replay_workers": 32,
    "reset_workers": 32,
    "cpu_affinity": sorted(os.sched_getaffinity(0)),
    "simulation": "physx_cpu",
    "render_devices": [0, 1],
    "gpu_binding": "sorted(gpus)[seed % len(gpus)]",
    "timeout_seconds": 1200,
    "gpu_sample_interval_ms": 500,
    "iostat_interval_seconds": 2,
    "suite": str(suite),
    "primary_output": str(primary),
    "comparison_output": str(comparison),
    "generation_comparison": {
        "same_suite": True,
        "same_96_specs": True,
        "same_reverse_order": True,
        "same_gpu_binding": True,
        "fresh_output_directories": True,
        "worker_order": [32, 16],
        "interpretation": "完成后依据实际phase时间与逐条计时比较；未预设16或32最优，顺序执行可能存在预热差异",
    },
    "phase_timings": str(report / "phase_timings.tsv"),
    "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
    "script": script.read_text(),
    "scope": {"tasks": 4, "episodes_per_task": 24, "per_difficulty": 8, "total": 96},
}
report.mkdir(parents=True, exist_ok=True)
with (report / "run_context.json").open("x", encoding="utf-8") as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print("正式 v3 双卡运行基线：" + sha, flush=True)
PY

# 只管理本脚本实际启动并记录精确 PID 的采样进程，不清理任何 tmux 会话。
ICL_GPU_SAMPLER_PID=""
ICL_IO_SAMPLER_PID=""
icl_cleanup() {
    local icl_exit=$?
    trap - EXIT HUP INT TERM
    if [[ -n "$ICL_GPU_SAMPLER_PID" ]]; then
        kill "$ICL_GPU_SAMPLER_PID" 2>/dev/null || true
        wait "$ICL_GPU_SAMPLER_PID" 2>/dev/null || true
    fi
    if [[ -n "$ICL_IO_SAMPLER_PID" ]]; then
        kill "$ICL_IO_SAMPLER_PID" 2>/dev/null || true
        wait "$ICL_IO_SAMPLER_PID" 2>/dev/null || true
    fi
    printf 'EXIT_CODE=%s\n' "$icl_exit" >> "$ICL_RUN_REPORT/main.log"
    exit "$icl_exit"
}
trap icl_cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

nvidia-smi --query-gpu=timestamp,index,utilization.gpu,memory.used --format=csv,noheader -lms 500 > "$ICL_RUN_REPORT/gpu_samples.csv" &
ICL_GPU_SAMPLER_PID=$!
iostat -xz -y 2 > "$ICL_RUN_REPORT/iostat.log" &
ICL_IO_SAMPLER_PID=$!
printf 'GPU_SAMPLER_PID=%s\nIO_SAMPLER_PID=%s\n' "$ICL_GPU_SAMPLER_PID" "$ICL_IO_SAMPLER_PID" > "$ICL_RUN_REPORT/sampler_pids.log"
printf 'phase\tstart_utc\tend_utc\tstart_epoch_ns\tend_epoch_ns\telapsed_ns\tcommand_exit\ttee_exit\tphase_exit\n' > "$ICL_RUN_REPORT/phase_timings.tsv"

icl_phase() {
    local icl_name="$1"
    shift
    command -v uv > /dev/null
    local icl_start_ns icl_end_ns icl_start_utc icl_end_utc
    icl_start_ns="$(date +%s%N)"
    icl_start_utc="$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)"
    printf 'START %s %s\n' "$icl_name" "$icl_start_utc" | tee -a "$ICL_RUN_REPORT/main.log"
    set +e
    "$@" 2>&1 | tee "$ICL_RUN_REPORT/$icl_name.log"
    local -a icl_pipeline_status=("${PIPESTATUS[@]}")
    set -e
    local icl_result="${icl_pipeline_status[0]}"
    if [[ "$icl_result" -eq 0 && "${icl_pipeline_status[1]}" -ne 0 ]]; then
        icl_result="${icl_pipeline_status[1]}"
    fi
    icl_end_ns="$(date +%s%N)"
    icl_end_utc="$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)"
    printf 'COMMAND_EXIT_CODE=%s\nTEE_EXIT_CODE=%s\nEXIT_CODE=%s\n' "${icl_pipeline_status[0]}" "${icl_pipeline_status[1]}" "$icl_result" >> "$ICL_RUN_REPORT/$icl_name.log"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$icl_name" "$icl_start_utc" "$icl_end_utc" "$icl_start_ns" "$icl_end_ns" "$((icl_end_ns - icl_start_ns))" \
        "${icl_pipeline_status[0]}" "${icl_pipeline_status[1]}" "$icl_result" >> "$ICL_RUN_REPORT/phase_timings.tsv"
    printf 'FINISH %s EXIT_CODE=%s %s\n' "$icl_name" "$icl_result" "$icl_end_utc" | tee -a "$ICL_RUN_REPORT/main.log"
    return "$icl_result"
}

icl_phase certification96 uv run --no-sync python scripts/legacy/robomme_icl/cli.py prepare --output "$ICL_SUITE" --gpus 0,1 --workers 32 --timeout-seconds 1200

# 两轮生成使用同一套已认证规格、相同逆序和原 GPU 绑定，但各写全新独立目录。
icl_phase generate-reverse-w32 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode generate --workers 32 --reverse --timeout-seconds 1200
icl_phase generate-reverse-w16 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY_W16" --mode generate --workers 16 --reverse --timeout-seconds 1200

icl_phase resume-forward-w4 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode resume --workers 4 --timeout-seconds 1200
icl_phase replay-forward-w32 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode replay --workers 32 --timeout-seconds 1200
icl_phase reset-reverse-w32 uv run --no-sync python scripts/legacy/robomme_icl/run_acceptance.py --suite "$ICL_SUITE" --output "$ICL_VERIFY" --mode reset --workers 32 --reverse --timeout-seconds 1200
icl_phase plots uv run --no-sync python scripts/legacy/robomme_icl/plot_suite.py --suite "$ICL_SUITE" --output "$ICL_RUN_REPORT/figures"
