"""S2 固定身份运行器：每身份至多启动一次，恢复只继续未启动身份。"""
import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
STOP = threading.Event()


def read(path):
    return json.loads(path.read_text())


def write_new(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def execute(row, gpu, timeout):
    out = ROOT / "episodes" / row["id"]
    out.mkdir(parents=True, exist_ok=True)
    started = out / "started.json"
    result_path = out / "result.json"
    if started.exists():
        # 启动标记写在进程创建前；即使中断也绝不自动重试。
        if result_path.exists():
            return read(result_path)
        return {**row, "ok": False, "status": "interrupted_unresolved", "counted_attempt": True}
    if STOP.is_set():
        return {**row, "ok": False, "status": "not_started", "counted_attempt": False}
    command = [sys.executable, "-m", "scripts.parity.v4_demo_probe", "--task", row["task"],
               "--difficulty", row["difficulty"], "--seeds", str(row["seed"]),
               "--episode", str(row["episode"]), "--sampling-config", row["sampling_config"],
               "--gpu", gpu, "--out", str(out)]
    begin = time.time()
    write_new(started, {**row, "command": command, "started_at": begin, "gpu": gpu})
    print(f"S2_START id={row['id']} gpu={gpu}", flush=True)
    status, code, process = "finished", None, None
    try:
        with (out / "worker.log").open("x") as log:
            process = subprocess.Popen(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, env={**os.environ, "PYTHONUNBUFFERED": "1"})
            try:
                while True:
                    if STOP.is_set():
                        raise InterruptedError("运行器收到终止信号")
                    remaining = timeout - (time.time() - begin)
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, timeout)
                    try:
                        code = process.wait(timeout=min(1, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        continue
            except subprocess.TimeoutExpired:
                status = "timeout"
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    code = process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    code = process.wait()
    except BaseException as exc:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        status = f"launcher_error:{type(exc).__name__}:{exc}"
    summaries = []
    summary_path = out / "summary.jsonl"
    if summary_path.exists():
        try:
            summaries = [json.loads(line) for line in summary_path.read_text().splitlines() if line]
        except (ValueError, OSError):
            status = "invalid_summary"
    valid = len(summaries) == 1 and all(summaries[0].get(k) == row[k] for k in ("task", "difficulty", "seed"))
    result = {**row, "ok": bool(status == "finished" and code == 0 and valid and summaries[0].get("ok")),
              "status": status, "exit_code": code, "timeout": status == "timeout",
              "wall_s": round(time.time() - begin, 3), "counted_attempt": True,
              "summary_valid": valid, "probe_summary": summaries,
              "hdf5": [str(p.relative_to(REPO)) for p in sorted(out.rglob("*.h5"))],
              "videos": [str(p.relative_to(REPO)) for p in sorted(out.rglob("*.mp4"))]}
    write_new(result_path, result)
    print(f"S2_RESULT id={row['id']} ok={result['ok']} status={status} exit_code={code}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["check", "smoke", "remaining"])
    parser.add_argument("--gpus", default="0")
    parser.add_argument("--workers-per-gpu", type=int, choices=range(1, 5), default=1)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    manifest = read(ROOT / "manifest.json")
    rows = manifest["identities"]
    assert len(rows) == len({r["id"] for r in rows}) == manifest["attempt_budget"] == 144
    assert manifest["retries"] == 0
    snapshot = REPO / "scripts/configs/newtask-v6/sampling_config.json"
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == manifest["sampling_snapshot_sha256"]
    tasks = read(snapshot)["tasks"]
    for row in rows:
        assert read(REPO / row["sampling_config"]) == tasks[row["task"]]
    if args.mode == "check":
        print("S2_MANIFEST=PASS identities=144 extra_attempts=0")
        return 0
    lock = (ROOT / "runner.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    gpus = args.gpus.split(",")
    assert all(gpu.isdigit() for gpu in gpus) and len(set(gpus)) == len(gpus)
    gpus = [gpu for gpu in gpus for _ in range(args.workers_per_gpu)]
    if args.mode == "smoke":
        return 0 if execute(rows[0], gpus[0], manifest["timeout_s"])["ok"] else 1
    smoke = ROOT / "episodes" / rows[0]["id"] / "result.json"
    if not smoke.exists() or not read(smoke)["ok"]:
        raise SystemExit("首条冒烟未成功，禁止放大批次；不得重复启动已尝试身份")
    # 每张 GPU 至多四个串行队列，不使用可挂死的进程池换代。
    def lane(index):
        return [execute(row, gpus[index], manifest["timeout_s"]) for row in rows[1 + index::len(gpus)]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(gpus)) as pool:
        completed = [read(smoke)]
        for batch in pool.map(lane, range(len(gpus))):
            completed.extend(batch)
    report = {"identities": len(rows), "counted_attempts": sum(r["counted_attempt"] for r in completed),
              "successes": sum(r["ok"] for r in completed),
              "failures": sum(r["counted_attempt"] and not r["ok"] for r in completed),
              "not_started": sum(not r["counted_attempt"] for r in completed),
              "unresolved": sum(r["status"] == "interrupted_unresolved" for r in completed),
              "results": sorted(completed, key=lambda r: r["id"])}
    # 每次恢复产生新的汇总，保留此前的全部记录。
    target = ROOT / f"summary-{time.time_ns()}.json"
    write_new(target, report)
    completion = "COMPLETE" if not report["unresolved"] and not report["not_started"] else "INCOMPLETE"
    print(f"S2_ATTEMPTS={completion} count={report['counted_attempts']} success={report['successes']} failed={report['failures']} unresolved={report['unresolved']} not_started={report['not_started']} report={target}", flush=True)
    return 1 if report["unresolved"] or STOP.is_set() else 0


if __name__ == "__main__":
    raise SystemExit(main())
