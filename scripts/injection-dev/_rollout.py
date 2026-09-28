"""第二阶段：只读 jsonl → 生成 h5 → 按状态机回写（0927 计划第一部分 §5.2）。

由 ``scripts/parity/v4_rollout.py`` 下沉：真正起环境、录 h5、跑规划的仍是 ``train_split_runner.py``
（``--identity-source formula --no-recovery``）→ ``train_split_worker.run_one``（``gym.make(..., sampling_config=,
native_episode_spec=)``），环境包由 ``ROBOMME_ENV_PACKAGE`` 决定（默认 robomme_hard）。

两种模式：

* ``continue``（正常生产）：进入即在 ``<specs>.lock`` 上 ``O_EXCL`` 取锁并持有到回写结束；待跑集 = 每格
  ``selected`` 且 ``rollout`` 缺失的行；某行失败 → ``selected=false``、``rollout.status="failed"``、``tried=true``，
  从同格 ``tried=false`` 且未选中的候选里按 ``candidate`` 升序递补一个；每格 ``selected`` 行数 ≤ ``delivery_per_cell``。
  基础设施失败每身份最多重跑 1 次（计入预算、记原因与次数）；任务失败不重试挑成功。
  全部批次结束后一次回写：重读 specs，整份文件 sha256 必须等于读入时；只改 ``selected``／``tried``／``rollout``；
  临时文件 + ``os.replace``；写后 ``load_specs`` 核 ``identity_sha256`` 未变并重算 ``delivery_sha256``。
* ``replay``（对拍专用）：只按给定身份清单逐局重放，不递补、不回写 jsonl，结果只写 ``--output``；
  清单与调度集合必须全等 → ``REPLAY_SET``。

恢复（``--resume``）：联合核对各轮 ``jobs.json``、``results.partial.jsonl``、局目录与 h5；局目录有完整 h5 而 partial
无记录的身份标 ``UNKNOWN`` 并列清单交用户，不直接重跑、不直接采纳。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import _common  # noqa: F401  路径设置

from robomme_hard.env_record_wrapper import hard_specs  # noqa: E402

RUNNER = _common.REPO_ROOT / "scripts" / "parity" / "train_split_runner.py"
INFRA_TYPES = {"BrokenProcessPool", "TerminatedWorkerError", "TimeoutError", "RunnerCrash"}
INFRA_PATTERN = re.compile(r"svulkan2|vulkan|ErrorIncompatibleDriver|EXCLUSIVE|CUDA error|out of memory|"
                           r"Resource temporarily unavailable|Too many open files", re.I)


class RolloutError(RuntimeError):
    """锁、回写、恢复歧义或清单不符；一律停止。"""


def is_infra(result: dict[str, Any]) -> bool:
    if result.get("ok"):
        return False
    return result.get("error_type") in INFRA_TYPES or bool(INFRA_PATTERN.search(str(result.get("error") or "")))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ── 锁 ─────────────────────────────────────────────────────────────────


class SpecsLock:
    """``<specs>.lock``：``O_EXCL`` 创建，记 pid／host／启动时间；已存在一律拒绝（不自动判陈旧）。"""

    def __init__(self, specs: Path):
        self.path = Path(str(specs) + ".lock")
        self.held = False

    def acquire(self) -> None:
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError as exc:
            info = self.path.read_text(errors="replace") if self.path.exists() else ""
            raise RolloutError(f"锁已存在，拒绝并交用户：{self.path} {info.strip()}") from exc
        with os.fdopen(fd, "w") as stream:
            json.dump({"pid": os.getpid(), "host": socket.gethostname(),
                       "started": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}, stream)
        self.held = True

    def release(self) -> None:
        if self.held and self.path.exists():
            self.path.unlink()
        self.held = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


# ── 调 runner ──────────────────────────────────────────────────────────


def episode_dir(out_dir: Path, row: dict[str, Any]) -> Path:
    return out_dir / "episodes" / row["tier"] / f"{row['task']}_episode_{row['episode']}"


def h5_facts(path: Path) -> dict[str, Any]:
    import h5py

    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 24), b""):
            digest.update(chunk)
            size += len(chunk)
    with h5py.File(path, "r") as handle:
        episode = handle[list(handle.keys())[0]]
        frames = sum(1 for k in episode.keys() if k.startswith("timestep_"))
    return {"h5_sha256": digest.hexdigest(), "bytes": size, "frames": frames}


def run_batch(batch: list[dict[str, Any]], header: dict[str, Any], out_dir: Path, round_index: int, *,
              src_root: Path, workers: int, gpu: str, pkg: str, official_root: Path | None = None,
              resume: bool = False, runner_env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """一批身份（同一档）交给 runner，返回逐条结果（含回注绑定核验与 h5 事实）。"""
    tiers = {row["tier"] for row in batch}
    if len(tiers) != 1 or tiers != {header["difficulty"]}:
        raise RolloutError(f"一批只能是同一档且与 header 一致：{tiers}")
    work = out_dir / "_rounds" / f"{header['difficulty']}_round_{round_index:02d}"
    work.mkdir(parents=True, exist_ok=resume)
    done_here = set()
    if resume and (work / "results.partial.jsonl").exists():
        done_here = {(r["task"], int(r["episode"])) for r in map(json.loads, (work / "results.partial.jsonl").read_text().splitlines()) if r}
    jobs, specs = [], {}
    for row in batch:
        wdir = episode_dir(out_dir, row)
        if wdir.exists() and (row["task"], row["episode"]) not in done_here:
            # 官方 _worker 要求局目录不存在：上一次（基础设施失败或中断）的目录改名挪开留作证据，不删除
            aside = wdir.with_name(f"{wdir.name}.aside{int(time.time())}")
            wdir.rename(aside)
            print(f"# 局目录已存在，挪开留证：{aside}", flush=True)
        jobs.append({"task": row["task"], "episode": row["episode"], "seed": row["seed"], "attempt": row["attempt"],
                     "difficulty": row["tier"], "seed_rule": header["seed_rule"],
                     "worker_dir": str(episode_dir(out_dir, row))})
        specs[f"{row['task']}/{row['episode']}"] = row["spec"]
    tasks = sorted({row["task"] for row in batch})
    (work / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    (work / "sampling.json").write_text(json.dumps({"tasks": {t: header["sampling_config"][t] for t in tasks}},
                                                   ensure_ascii=False), encoding="utf-8")
    (work / "specs.json").write_text(json.dumps({"specs": specs}, ensure_ascii=False), encoding="utf-8")
    command = [
        sys.executable, str(RUNNER), "--src-root", str(src_root), "--jobs-json", str(work / "jobs.json"),
        "--results-json", str(work / "results.json"), "--workers", str(workers), "--gpu", str(gpu),
        "--sampling-config", str(work / "sampling.json"), "--episode-specs", str(work / "specs.json"),
        "--identity-source", "formula", "--no-recovery",
    ]
    if official_root is not None:
        command += ["--official-root", str(official_root)]
    if resume:
        command.append("--resume")
    env = dict(runner_env or os.environ)
    env.update(ROBOMME_ENV_PACKAGE=pkg, PYTHONUNBUFFERED="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    env.pop("PYTHONPATH", None)
    started = time.time()
    with (work / "runner.log").open("a", encoding="utf-8") as log:
        proc = subprocess.run(command, text=True, stdout=log, stderr=subprocess.STDOUT, env=env)
    raw: dict[tuple[str, int], dict[str, Any]] = {}
    if (work / "results.json").exists():
        raw = {(r["task"], int(r["episode"])): r for r in json.loads((work / "results.json").read_text())["results"]}
    elif (work / "results.partial.jsonl").exists():
        for line in (work / "results.partial.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                raw[(r["task"], int(r["episode"]))] = r
    out = []
    for row in batch:
        result = raw.get((row["task"], row["episode"]))
        if result is None:
            result = {"ok": False, "error_type": "RunnerCrash", "error": f"runner exit={proc.returncode}，无该局结果"}
        wdir = episode_dir(out_dir, row)
        binding = None
        replay = wdir / "spec_replay.json"
        if replay.exists():
            payload = json.loads(replay.read_text(encoding="utf-8"))
            mismatches = payload.get("mismatches", [])
            binding = {"mismatch": len(mismatches),
                       "unattributed_mismatch": sum(1 for m in mismatches if not m.get("decision_key")),
                       "unused": len(payload.get("unused", [])), "value_points": payload.get("value_points")}
        h5 = sorted((wdir / "hdf5_files").glob("*.h5"))
        record = {
            "task": row["task"], "tier": row["tier"], "candidate": row["candidate"], "episode": row["episode"],
            "seed": row["seed"], "attempt": row["attempt"], "spec_sha256": row["spec_sha256"],
            "ok": bool(result.get("ok")), "error_type": result.get("error_type"),
            "error": (str(result.get("error") or ""))[:500] or None, "spec_binding": binding,
            "env_package": result.get("env_package"), "env_module": result.get("env_module"),
            "wrapper_modules": result.get("wrapper_modules"),
            "h5": str(h5[0]) if h5 else None, "round": round_index, "role": row.get("_role", "selected"),
        }
        if record["ok"] and h5:
            record.update(h5_facts(h5[0]))
        out.append(record)
    print(f"ROUND {header['difficulty']}/{round_index} jobs={len(batch)} ok={sum(r['ok'] for r in out)} "
          f"infra={sum(is_infra(r) for r in out)} wall_s={time.time() - started:.0f}", flush=True)
    return out


def rollout_block(record: dict[str, Any], pkg: str, code_baseline: str, output: Path) -> dict[str, Any]:
    block = {
        "status": "ok" if record["ok"] else "failed", "round": record["round"], "role": record["role"],
        "env_package": pkg, "env_module": record.get("env_module"), "code_baseline": code_baseline,
        "source": str(output), "written_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    if record["ok"]:
        block.update({k: record.get(k) for k in ("h5_sha256", "bytes", "frames")})
        block["h5_path"] = record.get("h5")
    else:
        block["error_type"] = record.get("error_type")
    return block


def _has_run_traces(output: Path) -> bool:
    """输出目录已跑过（有局目录或轮次目录）才拒绝；调用方预先写入的 launch／清单等小文件不算。"""
    return (output / "episodes").exists() or (output / "_rounds").exists()


def unknown_identities(out_dir: Path) -> list[str]:
    """局目录有完整 h5、但各轮 partial 与 results.json 都没有记录的身份（恢复的歧义窗口）。"""
    recorded = set()
    for partial in out_dir.glob("_rounds/*/results.partial.jsonl"):
        for line in partial.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                recorded.add((r["task"], int(r["episode"]), str(r.get("difficulty"))))
    unknown = []
    for h5 in out_dir.glob("episodes/*/*/hdf5_files/*.h5"):
        tier = h5.parents[2].name
        task, _, episode = h5.parents[1].name.rpartition("_episode_")
        if (task, int(episode), tier) not in recorded:
            unknown.append(f"{tier}/{task}/{episode}")
    return sorted(unknown)


# ── continue 模式：状态机 ──────────────────────────────────────────────────


def plan_pending(rows: list[dict[str, Any]], per_cell: int, redo: set[tuple[str, int]] = frozenset(),
                 tasks: set[str] | None = None) -> list[dict[str, Any]]:
    for row in rows:
        if (row["task"], row["candidate"]) in redo:
            row["rollout"], row["selected"] = None, True
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["task"]] = counts.get(row["task"], 0) + int(row["selected"])
    bad = {t: n for t, n in counts.items() if n > per_cell}
    if bad:
        raise RolloutError(f"每格 selected 超过 delivery_per_cell={per_cell}：{bad}")
    return [row for row in rows if row["selected"] and row["rollout"] is None and (tasks is None or row["task"] in tasks)]


def apply_results(rows: list[dict[str, Any]], results: list[dict[str, Any]], pkg: str, code_baseline: str,
                  output: Path) -> list[dict[str, Any]]:
    """按结果更新行；失败的行退选并递补同格下一个未试候选。返回新一轮待跑行。"""
    by_key = {(r["task"], r["candidate"]): r for r in rows}
    backfill = []
    for record in results:
        row = by_key[(record["task"], record["candidate"])]
        row["tried"] = True
        row["rollout"] = rollout_block(record, pkg, code_baseline, output)
        if not record["ok"]:
            row["selected"] = False
            spare = sorted((r for r in rows if r["task"] == row["task"] and not r["tried"] and not r["selected"]),
                           key=lambda r: r["candidate"])
            if spare:
                spare[0]["selected"] = True
                spare[0]["_role"] = "backfill"
                backfill.append(spare[0])
    return backfill


def write_back(specs: Path, header: dict[str, Any], rows: list[dict[str, Any]], expected_file_sha: str) -> dict[str, Any]:
    """持锁回写：整份文件 sha 必须未变；只改结果段；临时文件 + os.replace；写后复核身份不变。"""
    if file_sha256(specs) != expected_file_sha:
        raise RolloutError(f"{specs} 在运行期间被他人改过（整份文件 sha 不符），中止回写")
    clean = [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]
    new_header = dict(header)
    new_header["delivery_sha256"] = hard_specs.delivery_sha256(clean)
    if hard_specs.identity_sha256(new_header, clean) != header["identity_sha256"]:
        raise RolloutError("回写后 identity_sha256 变了——只允许改结果段")
    hard_specs.validate_specs(new_header, clean)
    fd, name = tempfile.mkstemp(prefix=".hardspecs-", dir=specs.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        for record in [new_header, *clean]:
            stream.write(hard_specs.canonical_json(record) + "\n")
    os.chmod(name, 0o644)
    os.replace(name, specs)
    header2, _ = hard_specs.load_specs(specs, check_fingerprint=False)
    if header2["identity_sha256"] != header["identity_sha256"]:
        raise RolloutError("回写后重读 identity_sha256 不符")
    return new_header


def run_continue(specs: Path, output: Path, *, src_root: Path, workers: int, gpu: str, pkg: str,
                 code_baseline: str, redo: set[tuple[str, int]] = frozenset(), resume: bool = False,
                 max_infra_retries: int = 1, batch_runner=None, tasks: set[str] | None = None) -> dict[str, Any]:
    """``batch_runner`` 只供纯 CPU 夹具注入假 runner（STATE_MACHINE）。"""
    runner = batch_runner or (lambda batch, header, idx: run_batch(
        batch, header, output, idx, src_root=src_root, workers=workers, gpu=gpu, pkg=pkg, resume=resume))
    lock = SpecsLock(specs)
    lock.acquire()  # 锁先于一切：取锁失败的进程 worker 数为零、直接退出
    try:
        file_sha = file_sha256(specs)
        header, rows = hard_specs.load_specs(specs, check_fingerprint=False)
        if resume:
            unknown = unknown_identities(output)
            if unknown:
                raise RolloutError(f"恢复歧义：以下身份有 h5 但无 partial 记录，标 UNKNOWN 交用户：{unknown}")
        elif _has_run_traces(output):
            raise RolloutError(f"{output} 已有运行痕迹（episodes/ 或 _rounds/）；续跑用 --resume")
        output.mkdir(parents=True, exist_ok=True)
        pending = plan_pending(rows, int(header["delivery_per_cell"]), redo, tasks)
        infra_retries: dict[tuple[str, int], int] = {}
        attempted = 0
        round_index = 0
        while pending:
            results = runner(pending, header, round_index)
            attempted += len(results)
            retry = []
            final = []
            for record in results:
                key = (record["task"], record["candidate"])
                if is_infra(record) and infra_retries.get(key, 0) < max_infra_retries:
                    infra_retries[key] = infra_retries.get(key, 0) + 1
                    retry.append(next(r for r in pending if (r["task"], r["candidate"]) == key))
                else:
                    final.append(record)
            backfill = apply_results(rows, final, pkg, code_baseline, output)
            pending = retry + backfill
            round_index += 1
        header = write_back(specs, header, rows, file_sha)
        delivered = sum(hard_specs.delivered(r) for r in rows)
        summary = {"attempted": attempted, "rounds": round_index, "infra_retries": sum(infra_retries.values()),
                   "delivered": delivered, "delivery_sha256": header["delivery_sha256"]}
        (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary
    finally:
        lock.release()


# ── replay 模式 ─────────────────────────────────────────────────────────


def load_identities(path: Path) -> list[dict[str, Any]]:
    """身份清单：S4 ``final-delivery.json``（取 ``successes``）或每行 ``{task, tier|difficulty, seed}`` 的 jsonl。"""
    text = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix == ".json":
        items = json.loads(text)
        items = items.get("successes", items)
    else:
        items = [json.loads(line) for line in text.splitlines() if line.strip()]
    return [{"task": i["task"], "tier": i.get("tier", i.get("difficulty")), "seed": int(i["seed"])} for i in items]


def run_replay(identities: list[dict[str, Any]], output: Path, *, src_root: Path, workers: int, gpu: str, pkg: str,
               resume: bool = False, specs_paths: dict[str, Path] | None = None) -> dict[str, Any]:
    wanted = {(i["task"], i["tier"], i["seed"]) for i in identities}
    if len(wanted) != len(identities):
        raise RolloutError("身份清单有重复")
    if _has_run_traces(output) and not resume:
        raise RolloutError(f"{output} 已有运行痕迹（episodes/ 或 _rounds/）；续跑用 --resume")
    output.mkdir(parents=True, exist_ok=True)
    scheduled: set[tuple[str, str, int]] = set()
    results: list[dict[str, Any]] = []
    for tier in hard_specs.TIERS:
        path = (specs_paths or {}).get(tier, hard_specs.packaged_specs_path(tier))
        header, rows = hard_specs.load_specs(path, check_fingerprint=False)
        batch = [dict(r, _role="replay") for r in rows if (r["task"], tier, int(r["seed"])) in wanted]
        if not batch:
            continue
        scheduled |= {(r["task"], tier, int(r["seed"])) for r in batch}
        results.extend(run_batch(batch, header, output, 0, src_root=src_root, workers=workers, gpu=gpu, pkg=pkg,
                                 resume=resume))
    equal = scheduled == wanted
    print(f"REPLAY_SET={'PASS' if equal else 'FAIL'} scheduled={len(scheduled)} equal={len(scheduled & wanted)}"
          + ("" if equal else f" missing={sorted(wanted - scheduled)[:5]}"), flush=True)
    with (output / "results.jsonl").open("w", encoding="utf-8") as stream:
        for record in sorted(results, key=lambda r: (hard_specs.TIERS.index(r["tier"]), r["task"], r["candidate"])):
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {"scheduled": len(scheduled), "wanted": len(wanted), "equal": equal, "ok": sum(r["ok"] for r in results),
               "failed": sum(not r["ok"] for r in results)}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if not equal:
        raise RolloutError("REPLAY_SET 不符")
    return summary
