"""实跑编排：从候选快照派发，终态日志可重放，完成后发布唯一结果表。"""
from __future__ import annotations
import argparse
import copy
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    __package__ = "scripts.injection.rollout"
from .state import (ROOT, RunStore, StateError, atomic_text, candidate_key, file_sha, read_rows,
                    run_root, write_json, result_key)

TIER_TIMEOUT_S = 3600

#: 七类互斥的最终任务结果。
OUTCOME_PASS = "通过"
OUTCOME_SPEC_REJECT = "规格拒绝"
OUTCOME_COLLISION = "碰撞拒绝"
OUTCOME_BINDING = "实际对象/动作不符"
OUTCOME_PLAN = "规划失败"
OUTCOME_TIMEOUT = "超时"
OUTCOME_NOT_RUN = "未运行"


#: 归入「超时」的 error_type：录像器步数上限与生成器单条墙钟上限
WALL_TIMEOUT_ERROR_TYPES = ("FailsafeTimeout", "EpisodeWallClockTimeout")


def classify_outcome(record: dict[str, Any]) -> str:
    """把 worker 返回的一条记录翻成七类互斥的任务结果。

    ⚠ 执行状态不是 ``completed``（代码错误、基础设施错误）时任务结果一律记「未运行」
    并注明原因——系统错误不能冒充物理不可行。
    """
    if record.get("ok"):
        return OUTCOME_PASS
    error_type = str(record.get("error_type") or "")
    failure_class = str(record.get("failure_class") or "")
    if error_type == "EpisodeSpecError":
        return OUTCOME_SPEC_REJECT
    if error_type == "BinCollisionError":
        return OUTCOME_COLLISION
    if error_type == "SpecBindingError":
        return OUTCOME_BINDING
    if error_type in WALL_TIMEOUT_ERROR_TYPES or failure_class == "timeout":
        # FailsafeTimeout 是录像器 2000 步上限；EpisodeWallClockTimeout 是生成器单条墙钟上限（pebble 杀 worker）
        return OUTCOME_TIMEOUT
    if failure_class in ("code", "infra"):
        return OUTCOME_NOT_RUN
    # 余下的任务性失败（规划耗尽、螺旋规划失败、场景生成失败、环境报告失败）归规划失败；
    # 原始 error_type 在结果行里原样保留，便于事后细分。
    return OUTCOME_PLAN


def execution_state(record: dict[str, Any]) -> str:
    """执行状态四态：completed / code_error / infra_error / timeout。"""
    if record.get("ok"):
        return "completed"
    failure_class = str(record.get("failure_class") or "")
    if str(record.get("error_type") or "") in WALL_TIMEOUT_ERROR_TYPES or failure_class == "timeout":
        return "timeout"
    if failure_class == "code":
        return "code_error"
    if failure_class == "infra":
        return "infra_error"
    return "completed"  # 任务性失败：确实跑完了，只是任务没成功


def new_call(store, kind, keys, options):
    parent = store.logs / "attempts"
    parent.mkdir(parents=True, exist_ok=True)
    call = parent / f"{kind}-{len(list(parent.iterdir())) + 1:04d}"
    call.mkdir()
    header, _, _ = store.load()
    payload = {"kind": kind, "keys": [list(k) for k in keys], "options": options,
               "identity_sha256": header["identity_sha256"], "candidates": str(store.candidates),
               "output_root": str(store.state), "started_at": time.time()}
    write_json(call / "scope.json", payload)
    return call


def terminal_cache(store, kind):
    """读取完整物理终态；重复行必须完全相同，半行只登记中断位置。"""
    header, _, _ = store.load()
    result = {}
    for scope_path in sorted((store.logs / "attempts").glob(f"{kind}-*/scope.json")):
        scope = json.loads(scope_path.read_text())
        if scope["identity_sha256"] != header["identity_sha256"]:
            raise StateError("尝试日志属于其他候选身份")
        keys = [tuple(k) for k in scope["keys"]]
        if len(keys) != len(set(keys)):
            raise StateError("执行范围存在重复键")
        for row in read_rows(scope_path.parent / "episode_results.jsonl", incomplete_tail=True):
            key = candidate_key(row)
            if key not in keys:
                raise StateError(f"终态超出冻结范围：{key}")
            if key in result and result[key] != row:
                raise StateError(f"两条完整终态冲突：{key}")
            result[key] = row
    return result


def normalize(store, raw, kind, index):
    raw = copy.deepcopy(raw)
    raw.setdefault("outcome", classify_outcome(raw))
    return store.normalize(raw, kind, candidate_index=index)


def recover(store):
    header, candidates, results = store.load()
    index = {candidate_key(r): r for r in candidates}
    for kind in ("h5", "reset"):
        rows = [normalize(store, r, kind, index) for r in terminal_cache(store, kind).values()]
        if rows:
            store.merge(rows)
    completed = set(store.completed_groups())
    for path in (store.logs / "attempts").glob("reset-*/summary.json"):
        summary = json.loads(path.read_text())
        completed.update(summary.get("completed_groups", []))
    store.publish(store.load()[2], completed_groups=sorted(completed))
    return store.audit()


def choose_groups(header, filters=None):
    groups = [(g["task"], g["difficulty"]) for g in header["delivery_config_snapshot"]["groups"]
              if f"{g['task']}/{g['difficulty']}" in header["group_provenance"]]
    if filters:
        wanted = {tuple(value.split("/")) for value in filters}
        if not wanted.issubset(set(groups)):
            raise StateError("请求组不在候选文件内")
        groups = [g for g in groups if g in wanted]
    return groups


def invoke_generator(store, *, groups=None, episodes=None, gpus="0", tier=1, wall_limit_h=0, episode_range=None):
    header, candidates, results = store.load()
    selected = choose_groups(header, groups)
    existing = {candidate_key(r) for r in results if r["kind"] == "h5"}
    eligible = {candidate_key(r): r for r in candidates if r["split"] == "train" and (r["task"], r["difficulty"]) in selected}
    if episodes is not None:
        if episodes < 1:
            raise StateError("episodes 必须为正")
        eligible = {k: v for k, v in eligible.items() if k[2] < episodes}
    if episode_range:
        start, end = map(int, episode_range.split(":"))
        if start < 0 or end <= start:
            raise StateError("episode-range 应为起止递增的半开区间")
        eligible = {k: v for k, v in eligible.items() if start <= k[2] < end}
    if not eligible:
        raise StateError("训练执行范围为空")
    keys = [(t, d, ep) for ep in sorted({k[2] for k in eligible}) for t, d in selected
            if (t, d, ep) in eligible and (t, d, ep) not in existing]
    if not keys:
        return {"executed": 0, "reused": len(eligible)}
    options = {"gpus": gpus, "tier": tier, "episode_timeout": 600, "wall_limit_h": wall_limit_h}
    call = new_call(store, "h5", keys, options)
    uv = shutil.which("uv")
    if not uv:
        raise StateError("找不到 uv，拒绝回退到裸 Python")
    command = [uv, "run", "--no-sync", "python", str(ROOT / "scripts/injection/rollout/run.py"),
               "--execute-scope", str(call / "scope.json")]
    write_json(call / "command.json", {"command": command, "generator": str(ROOT / "scripts/generate_dataset_newseed.py")})
    started = time.monotonic()
    with (call / "generator.log").open("w", encoding="utf-8") as sink:
        process = subprocess.Popen(command, cwd=ROOT, env={**os.environ, "PYTHONUNBUFFERED": "1"},
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        def tee():
            for line in process.stdout:
                sink.write(line)
                sink.flush()
                print(line, end="", flush=True)
        reader = threading.Thread(target=tee, daemon=True)
        reader.start()
        try:
            code = process.wait(timeout=wall_limit_h * 3600 if wall_limit_h else None)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code = 124
        reader.join()
    recover(store)
    actual = {candidate_key(r) for r in store.load()[2] if r["kind"] == "h5"}
    missing = set(eligible) - actual
    report = {"exit_code": code, "elapsed_s": round(time.monotonic() - started, 2),
              "executed": len(keys) - len(missing), "reused": len(eligible) - len(keys), "missing": len(missing)}
    write_json(call / "invocation.json", report)
    if code != 0 or missing:
        raise StateError(f"生成调用未完整结束，保留已完成终态供续跑：{report}")
    return report


def execute_scope(path):
    """子进程只读冻结候选和选取清单；环境输入全部来自同一份候选快照。"""
    from ..candidates.io import load_candidates, project_spec
    from scripts import generate_dataset_newseed as gen
    if Path(gen.__file__).resolve() != ROOT / "scripts/generate_dataset_newseed.py":
        raise StateError("实际导入的生成器不在冻结仓库路径内")
    scope_path = Path(path)
    scope = json.loads(scope_path.read_text())
    header, candidates = load_candidates(scope["candidates"], repo_root=ROOT)
    if scope["identity_sha256"] != header["identity_sha256"]:
        raise StateError("冻结执行范围的候选身份改变")
    index = {candidate_key(r): r for r in candidates}
    keys = [tuple(k) for k in scope["keys"]]
    if len(keys) != len(set(keys)):
        raise StateError("派发范围重复")
    configs = gen.validate_sampling_config(header["sampling_config"], ROOT)
    options = scope["options"]
    gpus = gen._parse_gpus(options["gpus"])
    jobs = []
    for key in keys:
        candidate = index[key]
        if candidate["split"] != "train" or candidate["seed"] != gen.get_layout("train").seed(candidate["task"], candidate["episode"], 0):
            raise StateError("派发候选的 split 或 seed 不符")
        task, difficulty, episode = key
        output = Path(scope["output_root"]) / task / difficulty
        gen._prepare_output(output)
        spec = project_spec(candidate)
        gen.validate_episode_spec(spec, task, difficulty, str(key))
        jobs.append(gen.EpisodeJob(task, episode, 0, candidate["seed"], difficulty, str(output), str(ROOT),
                                   copy.deepcopy(configs[task]), spec, binfill_demo=True, emit_h5_digest=True))
    os.environ[gen.LIMIT_THREADS_ENV] = "1"
    gen._apply_thread_env("1")
    started = time.monotonic()
    succeeded, failed = gen._run_jobs(jobs=jobs, gpu_ids=gpus, workers=int(options["tier"]), layout_name="train",
        jsonl_path=scope_path.parent / "episode_results.jsonl", max_attempts=1, max_tasks_per_child=8,
        cpu_plan=gen._cpu_plan(gpus, "per-gpu"), episode_timeout_s=options["episode_timeout"])
    for task, difficulty in sorted({(j.task, j.difficulty) for j in jobs}):
        records = [r for r in succeeded if r["task"] == task and r["difficulty"] == difficulty]
        if records:
            gen._write_metadata(Path(scope["output_root"]) / task / difficulty, task, records)
    summary = {"requested": len(jobs), "succeeded": len(succeeded), "failed": len(failed),
               "elapsed_s": round(time.monotonic() - started, 2)}
    write_json(scope_path.parent / "summary.json", summary)
    print(f"H5_EXECUTION=PASS requested={len(jobs)} succeeded={len(succeeded)} failed={len(failed)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-scope", required=True)
    args = parser.parse_args()
    execute_scope(args.execute_scope)


if __name__ == "__main__":
    main()
