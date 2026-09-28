#!/usr/bin/env python3
"""三侧对拍入口（0927 计划第一部分 §5.4、§6.1，第二部分 §1.3 / §3.2 / §3.4）：generate / publish / compare。

三侧：O 官方（vendor 编排 d53f21a7 + 环境源码 1fadc0ec worktree，官方 ``_worker``）；P 修改前（tag ``pre-hard-split``
worktree，官方 ``_worker``）；H 修改后（拆包后 HEAD，``--force-mirror`` + ``ROBOMME_ENV_PACKAGE=robomme_hard``）。
判定是「行为一致」（用户 U-1）：身份、setup、结构、任务成功全等才 PASS；动作／状态／图像／帧数四项差异按
``scripts/configs/hard-parity-tolerances.json`` 的阈值判（U-19）；sha 相等数等只作参考。

子命令::

    # 生成（GL 节点；--stage 给 NFS 暂存目录时每局 sha256 后搬到暂存并删本地副本）
    uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side O --tier native \
        --manifest scripts/configs/newtask-v3/subset_manifest.json --src-root <1fadc0ec worktree> \
        --workers 16 --gpu 0 --out /tmp/hs/O-native --stage <NFS>/hs-stage/O-native
    # 上传 bucket 并逐对象读回核对（sled-vail）
    uv run --no-sync python scripts/parity/hard_parity.py publish --side O --tier native
    # 比对（sled-vail，读 /data 上的拉回目录）
    uv run --no-sync python scripts/parity/hard_parity.py compare --pair O:P --tier native \
        --manifest scripts/configs/newtask-v3/subset_manifest.json --calibrate

``generate`` 默认断言 GPU 型号为 A40；``--dev-smoke`` 放行本机 Ada（开发冒烟，``NATIVE_SMOKE``）。
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "parity" / "train_split_runner.py"
GENERATE_H5 = ROOT / "scripts" / "injection-dev" / "generate_h5.py"
VENDOR = ROOT / "scripts" / "parity" / "official"
TOLERANCES = ROOT / "scripts" / "configs" / "hard-parity-tolerances.json"
LOCAL_H5_ROOT = ROOT / "artifacts" / "newtask-v6" / "hard-split" / "h5"
COMPARE_ROOT = ROOT / "artifacts" / "newtask-v6" / "hard-split" / "compare"
BUCKET = "HongzeFu/robomme-hard-parity"
HF = ["uvx", "--from", "huggingface_hub==1.8.0", "--with", "click", "hf"]
SIDES = ("O", "P", "H")
PAIRS = ("O:P", "P:H", "O:H")
TIERS = ("native", "xhard")
TIER_NAMES = ("xhard1", "xhard2", "xhard3", "xhard4")
# 容差自定规则（用户 U-22，第二部分 §3.4）：最大值 × 1.5，带下界与合理性上界
TOL_RULES = {
    "action_max": {"floor": 0.005, "ceiling": 0.05},
    "state_max": {"floor": 0.005, "ceiling": 0.05},
    "image_mad": {"floor": 1.0, "ceiling": 10.0},
    "frames_max": {"floor": 5, "ceiling": 200},
}
TOL_KEYS = {"action_max": "action_max_rad", "state_max": "state_max", "image_mad": "image_mad",
            "frames_max": "frames_max"}


class ParityError(RuntimeError):
    """前置、清单、上传或比对失败；一律停止、不重试。"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def gpu_facts() -> dict[str, str]:
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                         capture_output=True, text=True)
    names = [line.split(",") for line in out.stdout.strip().splitlines() if line.strip()]
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if names and visible and visible.isdigit() and int(visible) < len(names):
        names = [names[int(visible)]]
    name, driver = (names[0][0].strip(), names[0][1].strip()) if names else ("unknown", "unknown")
    return {"gpu_model": name, "driver": driver}


def versions() -> dict[str, str]:
    code = ("import json,importlib.metadata as m,sys;"
            "out={'python':sys.version.split()[0]};"
            "[out.__setitem__(p,m.version(p)) for p in ('mani_skill','sapien','torch') if __import__('importlib').util.find_spec(p.replace('-','_'))];"
            "import torch;out['cuda']=str(torch.version.cuda);print(json.dumps(out))")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"error": proc.stderr[-300:]}


# ── 身份 ───────────────────────────────────────────────────────────────


def native_rows(manifest: Path) -> list[dict[str, Any]]:
    payload = json.loads(manifest.read_text())
    rows = payload["rows"]
    if len(rows) != int(payload["rows_total"]):
        raise ParityError("清单行数与 rows_total 不符")
    return [{"task": r["task"], "tier": r["difficulty"], "episode": int(r["episode"]), "seed": int(r["seed"])} for r in rows]


def xhard_rows(manifest: Path) -> list[dict[str, Any]]:
    payload = json.loads(manifest.read_text())
    items = payload.get("successes", payload)
    return [{"task": s["task"], "tier": s["difficulty"], "episode": int(s["episode"]), "seed": int(s["seed"])} for s in items]


def rows_for(tier: str, manifest: Path) -> list[dict[str, Any]]:
    return native_rows(manifest) if tier == "native" else xhard_rows(manifest)


def ident(row: dict[str, Any]) -> tuple[str, str, int]:
    return (row["task"], row["tier"], int(row["seed"]))


# ── generate ────────────────────────────────────────────────────────────


class Mover(threading.Thread):
    """盯各轮 ``results.partial.jsonl``：新完成的局算 sha256，写 identities 行；给了暂存目录就复制过去、核 sha、删本地副本。"""

    def __init__(self, out: Path, stage: Path | None, side: str, tier: str, runner_meta: dict[str, Any]):
        super().__init__(daemon=True)
        self.out, self.stage, self.side, self.tier, self.meta = out, stage, side, tier, runner_meta
        self.seen: set[tuple[str, int, str]] = set()
        self.stop_flag = threading.Event()
        self.errors: list[str] = []
        self.identities = out / "identities.jsonl"

    def _worker_dir(self, record: dict[str, Any]) -> Path:
        tier = str(record.get("difficulty"))
        nested = self.out / "episodes" / tier / f"{record['task']}_episode_{record['episode']}"
        return nested if nested.exists() else self.out / "episodes" / f"{record['task']}_episode_{record['episode']}"

    def handle(self, record: dict[str, Any]) -> None:
        key = (record["task"], int(record["episode"]), str(record.get("difficulty")))
        if key in self.seen:
            return
        self.seen.add(key)
        wdir = self._worker_dir(record)
        h5s = sorted((wdir / "hdf5_files").glob("*.h5")) if wdir.exists() else []
        line = {"side": self.side, "tier": str(record.get("difficulty")), "task": record["task"],
                "episode": int(record["episode"]), "seed": int(record["seed"]), "success": bool(record.get("ok")),
                "error_type": record.get("error_type"), "env_package": record.get("env_package"),
                "env_module": record.get("env_module"), "wrapper_modules": record.get("wrapper_modules"),
                "worker": self.meta.get("worker"), "robomme_module": self.meta.get("robomme_module"),
                "path": None, "bytes": None, "sha256": None, "frames": None, "media": []}
        if h5s:
            h5 = h5s[0]
            line.update(sha256=sha256_file(h5), bytes=h5.stat().st_size)
            try:
                import h5py

                with h5py.File(h5, "r") as handle:
                    episode = handle[list(handle.keys())[0]]
                    line["frames"] = sum(1 for k in episode if k.startswith("timestep_"))
            except Exception as exc:  # noqa: BLE001 打不开也如实记
                line["h5_error"] = f"{type(exc).__name__}: {exc}"
            rel = wdir.relative_to(self.out)
            line["path"] = str(rel / "hdf5_files" / h5.name)
            line["media"] = [str(p.relative_to(self.out)) for p in sorted(wdir.rglob("*.mp4"))]
            if self.stage is not None:
                self._ship(wdir, rel)
        with self.identities.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(f"EPISODE_DONE side={self.side} {line['tier']}/{line['task']}/{line['episode']} "
              f"success={int(line['success'])} sha={str(line['sha256'])[:12]}", flush=True)

    def _ship(self, wdir: Path, rel: Path) -> None:
        dest = self.stage / rel
        dest.mkdir(parents=True, exist_ok=True)
        for path in sorted(p for p in wdir.rglob("*") if p.is_file()):
            target = dest / path.relative_to(wdir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            if path.suffix == ".h5" and sha256_file(target) != sha256_file(path):
                self.errors.append(f"暂存副本 sha 不符：{target}")
                return
        # 完成标记：拉取端只拉带 SHIPPED 的局，避免拉到复制了一半的文件
        shipped = {str(p.relative_to(wdir)): sha256_file(p) for p in sorted(wdir.rglob("*"))
                   if p.is_file() and p.suffix in (".h5", ".mp4")}
        (dest / "SHIPPED").write_text(json.dumps(shipped, ensure_ascii=False, sort_keys=True) + "\n")
        for path in sorted((p for p in wdir.rglob("*") if p.is_file() and p.suffix in (".h5", ".mp4")), reverse=True):
            path.unlink()  # 节点 /tmp 只留小文件（sidecar），大文件搬走即删

    def scan(self) -> None:
        for partial in sorted(self.out.rglob("results.partial.jsonl")):
            for text in partial.read_text(encoding="utf-8").splitlines():
                if text.strip():
                    try:
                        self.handle(json.loads(text))
                    except Exception as exc:  # noqa: BLE001
                        self.errors.append(f"{type(exc).__name__}: {exc}")

    def run(self) -> None:
        while not self.stop_flag.is_set():
            self.scan()
            self.stop_flag.wait(5)
        self.scan()


def cmd_generate(args) -> int:
    facts = gpu_facts()
    if not args.dev_smoke and "A40" not in facts["gpu_model"]:
        raise ParityError(f"正式 generate 只许在 A40 上跑：当前 {facts}")
    rows = rows_for(args.tier, args.manifest)
    if args.tier == "xhard" and args.side != "H":
        raise ParityError("xhard 只生成 H 侧（P 侧复用 S4 交付存档）")
    if args.smoke:
        rows = rows[: args.smoke]
    out = args.out
    if out.exists() and any(out.iterdir()) and not args.resume:
        raise ParityError(f"{out} 已存在且非空；续跑用 --resume")
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(PYTHONUNBUFFERED="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    env.pop("PYTHONPATH", None)
    meta: dict[str, Any] = {}
    if args.tier == "native":
        jobs = [{"task": r["task"], "episode": r["episode"], "seed": r["seed"], "difficulty": r["tier"],
                 "worker_dir": str(out / "episodes" / f"{r['task']}_episode_{r['episode']}")} for r in rows]
        runner_dir = out / "_runner"
        runner_dir.mkdir(exist_ok=True)
        (runner_dir / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False, indent=1))
        command = [sys.executable, str(RUNNER), "--official-root", str(VENDOR), "--src-root", str(args.src_root),
                   "--jobs-json", str(runner_dir / "jobs.json"), "--results-json", str(runner_dir / "results.json"),
                   "--workers", str(args.workers), "--gpu", str(args.gpu)]
        if args.side == "H":
            command.append("--force-mirror")
            env["ROBOMME_ENV_PACKAGE"] = "robomme_hard"
            meta["worker"] = "train_split_worker.run_one"
        else:
            env["ROBOMME_ENV_PACKAGE"] = "robomme"
            meta["worker"] = "official._worker"
        if args.resume:
            command.append("--resume")
    else:
        identities = out / "_identities.jsonl"
        identities.write_text("".join(json.dumps({"task": r["task"], "tier": r["tier"], "seed": r["seed"]}) + "\n"
                                      for r in rows))
        command = [sys.executable, str(GENERATE_H5), "--mode", "replay", "--identities", str(identities),
                   "--output", str(out), "--workers", str(args.workers), "--gpu", str(args.gpu),
                   "--pkg", "robomme_hard", "--src-root", str(args.src_root)]
        if args.resume:
            command.append("--resume")
        meta["worker"] = "train_split_worker.run_one"
    launch = {"schema": "hard-parity-launch/1", "side": args.side, "tier": args.tier, "rows": len(rows),
              "manifest": str(args.manifest), "manifest_sha256": sha256_file(args.manifest),
              "src_root": str(args.src_root), "src_commit": subprocess.run(
                  ["git", "-C", str(args.src_root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
              "orchestration": str(VENDOR), "workers": args.workers, "gpu": args.gpu, **facts,
              "versions": versions(), "host": os.uname().nodename, "slurm_job": os.environ.get("SLURM_JOB_ID"),
              "started_at": now(), "command": command, "env_package": env.get("ROBOMME_ENV_PACKAGE", "robomme_hard"),
              "stage": str(args.stage) if args.stage else None, "dev_smoke": bool(args.dev_smoke)}
    (out / f"launch-{int(time.time())}.json").write_text(json.dumps(launch, ensure_ascii=False, indent=2))
    print(f"GENERATE_START side={args.side} tier={args.tier} rows={len(rows)} gpu={facts['gpu_model']} "
          f"driver={facts['driver']} workers={args.workers}", flush=True)
    mover = Mover(out, args.stage, args.side, args.tier, meta)
    mover.start()
    with (out / "generate.log").open("a", encoding="utf-8") as log:
        proc = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    runner_json = out / "_runner" / "results.json"
    if runner_json.exists():
        payload = json.loads(runner_json.read_text())
        meta.update(robomme_module=payload.get("robomme_module"), worker=payload.get("worker"))
    mover.stop_flag.set()
    mover.join()
    lines = [json.loads(t) for t in (out / "identities.jsonl").read_text().splitlines() if t.strip()] \
        if (out / "identities.jsonl").exists() else []
    got = {ident(r) for r in lines}
    want = {ident(r) for r in rows}
    ok_count = sum(r["success"] for r in lines)
    status = "PASS" if got == want and proc.returncode in (0, 1) and not mover.errors else "FAIL"
    label = "NATIVE_SMOKE" if args.dev_smoke else ("SHARD_SMOKE" if args.smoke else "GENERATE")
    print(f"{label}={status if not args.smoke or ok_count == len(rows) else 'FAIL'} side={args.side} tier={args.tier} "
          f"rows={len(rows)} recorded={len(got & want)} success={ok_count} runner_exit={proc.returncode} "
          f"gpu={facts['gpu_model']} mover_errors={len(mover.errors)}", flush=True)
    for error in mover.errors[:10]:
        print(f"# {error}")
    return 0 if status == "PASS" else 1


# ── publish ─────────────────────────────────────────────────────────────


def side_prefix(side: str, tier: str, manifest: dict[str, Any]) -> str:
    return f"{manifest['prefix']}/{tier}"


def cmd_publish(args) -> int:
    local = args.local or (LOCAL_H5_ROOT / f"{args.side}-{args.tier}")
    ident_path = local / "identities.jsonl"
    if not ident_path.exists():
        raise ParityError(f"{ident_path} 不存在")
    lines = [json.loads(t) for t in ident_path.read_text().splitlines() if t.strip()]
    sums = []
    for line in lines:
        if line.get("path"):
            path = local / line["path"]
            actual = sha256_file(path)
            if actual != line["sha256"]:
                raise ParityError(f"本地副本 sha 与 identities 不符：{path}")
            sums.append(f"{actual}  {line['path']}")
    (local / "SHA256SUMS").write_text("\n".join(sorted(sums)) + "\n")
    launches = sorted(local.glob("launch-*.json"))
    first = json.loads(launches[0].read_text()) if launches else {}
    manifest = {
        "schema": "hard-parity-side/1", "side": args.side, "tier": args.tier, "prefix": args.prefix,
        "src_commit": first.get("src_commit"), "orchestration_commit": "d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa",
        "tag": "pre-hard-split" if args.side == "P" else None, "code_baseline": args.code_baseline,
        "gpu_model": first.get("gpu_model", args.gpu_model), "driver": first.get("driver", args.driver),
        "versions": first.get("versions"), "job_ids": sorted({json.loads(p.read_text()).get("slurm_job") for p in launches} - {None}),
        "nodes": sorted({json.loads(p.read_text()).get("host") for p in launches} - {None}),
        "workers": first.get("workers", args.workers), "manifest": first.get("manifest"),
        "subset_manifest_sha256": first.get("manifest_sha256"), "objects": len(sums), "generated_at": first.get("started_at"),
        "published_at": now(), "notes": args.note,
    }
    (local / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    remote = f"hf://buckets/{BUCKET}/{args.prefix}/{args.tier}"
    listing = subprocess.run([*HF, "buckets", "list", f"{BUCKET}/{args.prefix}/{args.tier}", "-R"],
                             capture_output=True, text=True)
    existing = [l for l in listing.stdout.splitlines()
                if l.strip() and l.strip() != "(empty)" and not l.startswith(("ID", "---", "Installed ", "Resolved "))]
    if existing and not args.resume_upload:
        raise ParityError(f"bucket 目录已存在（只增不改，R13）：{remote}；重传须请示并另起目录名")
    include = ["--include", "identities.jsonl", "--include", "SHA256SUMS", "--include", "manifest.json",
               "--include", "launch-*.json", "--include", "*.h5"]
    if args.dry_run:
        print(f"PUBLISH_DRY_RUN remote={remote} objects={len(sums)}")
        return 0
    # 只给 --include 即白名单；再加 --exclude "*" 会把全部排除（1.8.0 实测 uploads=0）
    subprocess.run([*HF, "buckets", "sync", str(local), remote, *include], check=True)
    mismatch = 0
    with tempfile.TemporaryDirectory(dir=args.readback_tmp) as tmp:
        for entry in sums:
            sha, rel = entry.split("  ", 1)
            target = Path(tmp) / "obj"
            subprocess.run([*HF, "buckets", "cp", f"{remote}/{rel}", str(target)], check=True, capture_output=True)
            if not target.is_file():  # 远端没有该对象时 cp 只警告不报错
                mismatch += 1
                continue
            mismatch += int(sha256_file(target) != sha)
            target.unlink()
    listing = subprocess.run([*HF, "buckets", "list", f"{BUCKET}/{args.prefix}/{args.tier}", "-R"],
                             capture_output=True, text=True).stdout
    (local / "bucket-list.txt").write_text(listing)
    status = "PASS" if mismatch == 0 else "FAIL"
    print(f"BUCKET_SYNC={status} side={args.side} tier={args.tier} objects={len(sums)} "
          f"readback_sha_equal={len(sums) - mismatch} mismatch={mismatch} remote={remote}", flush=True)
    return 0 if status == "PASS" else 1


# ── compare ─────────────────────────────────────────────────────────────


def _decode(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode()
    if hasattr(value, "tolist"):
        return _decode(value.tolist())
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


def read_setup(episode) -> dict[str, Any]:
    setup = episode["setup"]
    keys = ("seed", "difficulty", "task_goal", "available_multi_choices", "front_camera_intrinsic",
            "wrist_camera_intrinsic")
    return {k: _decode(setup[k][()]) for k in keys if k in setup}


def schema_of(episode) -> list[str]:
    import h5py

    items: set[str] = set()

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset):
            head, _, rest = name.partition("/")
            group = "timestep" if head.startswith("timestep_") else head
            items.add(f"{group}/{rest}|{obj.dtype}|{obj.shape}")
    episode.visititems(visit)
    return sorted(items)


def side_lines(side_dir: Path) -> list[dict[str, Any]]:
    """读一侧 identities.jsonl；运行中逐局写的行拿不到 runner 结束后才有的 robomme_module／worker，
    从该侧 _runner/results.json（runner 探针原值）补齐空缺，不覆盖已有值。"""
    lines = [json.loads(t) for t in (side_dir / "identities.jsonl").read_text().splitlines() if t.strip()]
    runner = side_dir / "_runner" / "results.json"
    if runner.is_file():
        payload = json.loads(runner.read_text())
        for line in lines:
            if line.get("robomme_module") is None:
                line["robomme_module"] = payload.get("robomme_module")
            if line.get("worker") is None and payload.get("worker"):
                line["worker"] = payload.get("worker")
    return lines


def self_check(side_dir: Path, rows: list[dict[str, Any]]) -> tuple[dict[tuple, dict], list[str]]:
    lines = side_lines(side_dir)
    problems = []
    by_id: dict[tuple, dict] = {}
    for line in lines:
        key = ident(line)
        if key in by_id:
            problems.append(f"重复身份 {key}")
        by_id[key] = line
    want = {ident(r) for r in rows}
    if set(by_id) != want:
        problems.append(f"身份集合不符：缺 {len(want - set(by_id))} 多 {len(set(by_id) - want)}")
    return by_id, problems


def _ts(episode) -> list[str]:
    return sorted((k for k in episode if k.startswith("timestep_")), key=lambda k: int(k.split("_")[1]))


def pair_metrics(left: str, right: str) -> dict[str, Any]:
    """一对 h5：setup／结构／四项容差指标／首个分叉步。在进程池里跑。"""
    import h5py
    import numpy as np

    out: dict[str, Any] = {"left": left, "right": right}
    try:
        with h5py.File(left, "r") as lf, h5py.File(right, "r") as rf:
            le, re_ = lf[list(lf.keys())[0]], rf[list(rf.keys())[0]]
            out["setup_left"], out["setup_right"] = read_setup(le), read_setup(re_)
            out["setup_equal"] = out["setup_left"] == out["setup_right"]
            out["schema_equal"] = schema_of(le) == schema_of(re_)
            lt, rt = _ts(le), _ts(re_)
            out["contiguous"] = [int(k.split("_")[1]) for k in lt] == list(range(len(lt))) and \
                [int(k.split("_")[1]) for k in rt] == list(range(len(rt)))
            out["frames_left"], out["frames_right"] = len(lt), len(rt)
            n = min(len(lt), len(rt))
            action = state = 0.0
            mads = []
            diverge = None
            for i in range(n):
                a, b = le[lt[i]], re_[rt[i]]
                ja, jb = a["action/joint_action"][()], b["action/joint_action"][()]
                d_action = float(np.max(np.abs(ja.astype(np.float64) - jb.astype(np.float64)))) if ja.size else 0.0
                d_state = max(float(np.max(np.abs(a[f"obs/{k}"][()].astype(np.float64) - b[f"obs/{k}"][()].astype(np.float64))))
                              for k in ("joint_state", "gripper_state"))
                action, state = max(action, d_action), max(state, d_state)
                frame = [float(np.mean(np.abs(a[f"obs/{c}"][()].astype(np.int16) - b[f"obs/{c}"][()].astype(np.int16))))
                         for c in ("front_rgb", "wrist_rgb")]
                mads.append(sum(frame) / 2)
                if diverge is None and (d_action > 0 or d_state > 0 or frame[0] > 0 or frame[1] > 0):
                    diverge = i
            out.update(action_max=action, state_max=state, image_mad=float(np.mean(mads)) if mads else 0.0,
                       frames_diff=abs(len(lt) - len(rt)), first_divergence=diverge, common=n, error=None)
    except Exception as exc:  # noqa: BLE001 打不开即判定层不等
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def load_tolerances() -> dict[str, float]:
    if not TOLERANCES.is_file():
        raise ParityError(f"容差文件不存在，拒跑（R21）：{TOLERANCES}；先跑 compare --pair O:P --calibrate")
    payload = json.loads(TOLERANCES.read_text())
    return {k: float(payload[v]) for k, v in TOL_KEYS.items()}


def calibrate(pairs: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
    import numpy as np

    raw_p95, raw_max, tol, ceiling_hit = {}, {}, {}, []
    for key, field in (("action_max", "action_max"), ("state_max", "state_max"), ("image_mad", "image_mad"),
                       ("frames_max", "frames_diff")):
        values = [p[field] for p in pairs if p.get("error") is None]
        raw_p95[key] = float(np.percentile(values, 95)) if values else 0.0
        raw_max[key] = float(max(values)) if values else 0.0
        rule = TOL_RULES[key]
        value = raw_max[key] * 1.5
        value = math.ceil(value) if key == "frames_max" else value
        tol[key] = max(value, rule["floor"])
        if raw_max[key] > rule["ceiling"]:
            ceiling_hit.append(key)
    payload = {TOL_KEYS[k]: tol[k] for k in tol}
    payload.update(calibrated_from="O:P native", n=len(pairs), raw_p95=raw_p95, raw_max=raw_max,
                   rule="最大值 × 1.5（帧数向上取整），下界 0.005/0.005/1.0/5，合理性上界 0.05/0.05/10/200（U-22）",
                   calibrated_at=now())
    return not ceiling_hit, {"payload": payload, "ceiling_hit": ceiling_hit}


def cmd_compare(args) -> int:
    left_side, right_side = args.pair.split(":")
    if args.calibrate and args.pair != "O:P":
        raise ParityError("--calibrate 只允许 O:P（R21）")
    rows = rows_for(args.tier, args.manifest)
    left_dir = args.left or LOCAL_H5_ROOT / f"{left_side}-{args.tier}"
    right_dir = args.right or LOCAL_H5_ROOT / f"{right_side}-{args.tier}"
    out = COMPARE_ROOT / f"{left_side}{right_side}-{args.tier}"
    if out.exists() and not args.overwrite_compare:
        raise ParityError(f"{out} 已存在")
    out.mkdir(parents=True, exist_ok=True)
    left, left_problems = self_check(left_dir, rows)
    right, right_problems = self_check(right_dir, rows)
    for label, problems in ((left_side, left_problems), (right_side, right_problems)):
        print(f"SIDE_SELF_CHECK={'PASS' if not problems else 'FAIL'} side={label} tier={args.tier} "
              f"problems={len(problems)}" + (f" detail={problems[:3]}" if problems else ""), flush=True)
    keys = sorted({ident(r) for r in rows})
    jobs = {}
    with cf.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for key in keys:
            a, b = left.get(key), right.get(key)
            if a and b and a.get("path") and b.get("path"):
                jobs[key] = pool.submit(pair_metrics, str(left_dir / a["path"]), str(right_dir / b["path"]))
        metrics = {key: future.result() for key, future in jobs.items()}
    tol = None if args.calibrate else load_tolerances()
    counts = {k: 0 for k in ("identity_equal", "setup_equal", "schema_equal", "success_equal", "both_success",
                             "sha_equal", "frames_equal", "binding_ok")}
    tol_hits, pair_rows = [], []
    for key in keys:
        a, b, m = left.get(key), right.get(key), metrics.get(key, {})
        record = {"task": key[0], "tier": key[1], "seed": key[2], "left": a, "right": b,
                  **{k: v for k, v in m.items() if k not in ("left", "right")}}
        present = a is not None and b is not None
        counts["identity_equal"] += int(present)
        success_a = bool(a and a["success"] and a.get("path"))
        success_b = bool(b and b["success"] and b.get("path"))
        counts["success_equal"] += int(present and success_a == success_b)
        counts["both_success"] += int(success_a and success_b)
        counts["setup_equal"] += int(bool(m.get("setup_equal")) and m.get("error") is None)
        counts["schema_equal"] += int(bool(m.get("schema_equal")) and bool(m.get("contiguous")))
        counts["sha_equal"] += int(present and a.get("sha256") is not None and a.get("sha256") == b.get("sha256"))
        counts["frames_equal"] += int(m.get("frames_diff") == 0)
        binding_ok = present and all(_binding_ok(side, line) for side, line in ((left_side, a), (right_side, b)))
        counts["binding_ok"] += int(binding_ok)
        record["binding_ok"] = binding_ok
        if tol and m.get("error") is None and m:
            over = {k: m[f] for k, f in (("action_max", "action_max"), ("state_max", "state_max"),
                                          ("image_mad", "image_mad"), ("frames_max", "frames_diff")) if m[f] > tol[k]}
            if over:
                tol_hits.append({"key": key, "over": over})
                record["tol_over"] = over
        pair_rows.append(record)
    with (out / "h5_pairs.jsonl").open("w", encoding="utf-8") as stream:
        for record in pair_rows:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    n = len(keys)
    judged = all(counts[k] == n for k in ("identity_equal", "setup_equal", "schema_equal", "success_equal",
                                            "both_success", "binding_ok")) and not left_problems and not right_problems
    ok_metrics = [m for m in metrics.values() if m.get("error") is None]
    worst = {k: max((m[f] for m in ok_metrics), default=0.0) for k, f in (
        ("action_max", "action_max"), ("state_max", "state_max"), ("image_mad", "image_mad"), ("frames_max", "frames_diff"))}
    divergence = [m["first_divergence"] for m in ok_metrics if m.get("first_divergence") is not None]
    shape = "16x3x3" if args.tier == "native" else "13x3x3+16x3"
    base = (f"tier={args.tier} compared={n} identity_equal={counts['identity_equal']} setup_equal={counts['setup_equal']} "
            f"schema_equal={counts['schema_equal']} success_equal={counts['success_equal']} "
            f"both_success={counts['both_success']}")
    name = f"PARITY_{left_side}_{right_side}"
    if args.calibrate:
        within, result = calibrate(ok_metrics)
        payload = result["payload"]
        payload["tol_file_note"] = "由 hard_parity.py compare --pair O:P --calibrate 写入；改阈值须改本文件并写进留档（R21）"
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        TOLERANCES.parent.mkdir(parents=True, exist_ok=True)
        TOLERANCES.write_text(text)
        tol_sha = hashlib.sha256(text.encode()).hexdigest()
        print(f"PARITY_TOL_CALIB={'PASS' if within else 'FAIL'} pair=O:P n={len(ok_metrics)} "
              f"action_p95={payload['raw_p95']['action_max']:.3g} action_max={payload['raw_max']['action_max']:.3g} "
              f"state_max={payload['raw_max']['state_max']:.3g} image_mad_max={payload['raw_max']['image_mad']:.3g} "
              f"frames_max={payload['raw_max']['frames_max']:.3g} tol_file_sha={tol_sha[:12]}"
              + ("" if within else f" ceiling_hit={result['ceiling_hit']}（停止类）"), flush=True)
        tol = load_tolerances()
        for record in pair_rows:
            if record.get("error") is None and "action_max" in record:
                over = {k: record[f] for k, f in (("action_max", "action_max"), ("state_max", "state_max"),
                                                  ("image_mad", "image_mad"), ("frames_max", "frames_diff")) if record[f] > tol[k]}
                if over:
                    tol_hits.append({"key": (record["task"], record["tier"], record["seed"]), "over": over})
    tol_ok = not tol_hits
    severity = "none"
    if not tol_ok:
        worst_ratio = max(v / tol[k] for hit in tol_hits for k, v in hit["over"].items())
        severity = "continue" if worst_ratio <= 2 and len(tol_hits) <= math.floor(0.05 * n) and judged else "stop"
    verdict = "PASS" if judged and tol_ok else "FAIL"
    tol_text = " ".join(f"{k}={worst[k]:.3g}/{tol[k]:.3g}" for k in ("action_max", "state_max", "image_mad", "frames_max"))
    print(f"{name}={verdict} {base} tol={'PASS' if tol_ok else 'FAIL'} {tol_text} sha_equal={counts['sha_equal']} "
          f"frames_equal={counts['frames_equal']} binding_ok={counts['binding_ok']} shape={shape}"
          + ("" if verdict == "PASS" else f" severity={severity} tol_over={len(tol_hits)}"), flush=True)
    print(f"PARITY_REFERENCE=INFO pair={args.pair} tier={args.tier} first_divergence_n={len(divergence)} "
          f"first_divergence_median={sorted(divergence)[len(divergence) // 2] if divergence else None} "
          f"first_divergence_min={min(divergence) if divergence else None}", flush=True)
    summary = {"verdict": verdict, "counts": counts, "worst": worst, "tolerances": tol, "tol_hits": tol_hits,
               "severity": severity, "left_problems": left_problems, "right_problems": right_problems}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n")
    return 0 if verdict == "PASS" else 1


def _binding_ok(side: str, line: dict[str, Any]) -> bool:
    """ENV_PACKAGE_BINDING：H 侧环境类模块必须属于 robomme_hard；O／P 侧走官方 _worker、robomme 来自其 src_root。"""
    if line is None:
        return False
    if side == "H":
        return str(line.get("env_module") or "").startswith("robomme_hard.")
    if side == "P" and line.get("worker") is None and line.get("env_module") is None:
        return True  # S4 交付存档（ca32e9b，未记 env_module）按 manifest 如实写 code_baseline
    module = str(line.get("robomme_module") or "")
    return line.get("worker") == "official._worker" and "/robomme/" in module and "robomme_hard" not in module


def cmd_binding(args) -> int:
    counts = {}
    mismatch = 0
    for side in SIDES:
        path = LOCAL_H5_ROOT / f"{side}-native" / "identities.jsonl"
        lines = side_lines(path.parent)
        bad = sum(not _binding_ok(side, line) for line in lines)
        mismatch += bad
        counts[side] = "robomme_hard" if side == "H" else "robomme"
    status = "PASS" if mismatch == 0 else "FAIL"
    print(f"ENV_PACKAGE_BINDING={status} sides=3 O={counts['O']} P={counts['P']} H={counts['H']} mismatch={mismatch}")
    return 0 if status == "PASS" else 1


def cmd_import_s4(args) -> int:
    """P 侧 xhard = S4 交付存档（ca32e9b，16 worker）：逐局只读 symlink 引入 + identities.jsonl（sha 重算核对）。"""
    delivery = json.loads(args.manifest.read_text())
    out = LOCAL_H5_ROOT / "P-xhard"
    if out.exists():
        raise ParityError(f"{out} 已存在")
    out.mkdir(parents=True)
    lines, bad = [], 0
    for s in delivery["successes"]:
        h5 = next(f for f in s["files"] if f["path"].endswith(".h5"))
        rel = Path("episodes") / s["difficulty"] / f"{s['task']}_episode_{s['episode']}" / "hdf5_files" / Path(h5["path"]).name
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).symlink_to(h5["path"])
        actual = sha256_file(Path(h5["path"]))
        bad += int(actual != h5["sha256"])
        media = []
        for f in s["files"]:
            if f["path"].endswith(".mp4"):
                target = (out / rel).parent.parent / Path(f["path"]).name
                target.symlink_to(f["path"])
                media.append(str(target.relative_to(out)))
        lines.append({"side": "P", "tier": s["difficulty"], "task": s["task"], "episode": int(s["episode"]),
                      "seed": int(s["seed"]), "success": True, "error_type": None, "env_package": "robomme",
                      "env_module": None, "wrapper_modules": None, "worker": None, "robomme_module": None,
                      "path": str(rel), "bytes": int(h5["bytes"]), "sha256": actual, "frames": None, "media": media,
                      "source": "s4-relaunch-02/final-delivery.json", "code_baseline": delivery["code_baseline"]})
    (out / "identities.jsonl").write_text("".join(json.dumps(l, ensure_ascii=False, sort_keys=True) + "\n" for l in lines))
    status = "PASS" if bad == 0 and len(lines) == 165 else "FAIL"
    print(f"S4_IMPORT={status} rows={len(lines)} sha_mismatch={bad} out={out}")
    return 0 if status == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--side", choices=SIDES, required=True)
    gen.add_argument("--tier", choices=TIERS, required=True)
    gen.add_argument("--manifest", type=Path, required=True)
    gen.add_argument("--src-root", type=Path, required=True)
    gen.add_argument("--workers", type=int, default=16)
    gen.add_argument("--gpu", default="0")
    gen.add_argument("--out", type=Path, required=True)
    gen.add_argument("--stage", type=Path, default=None, help="NFS 暂存目录；每局 sha 后复制过去并删本地大文件")
    gen.add_argument("--smoke", type=int, default=0, help="只跑前 N 局（SHARD_SMOKE）")
    gen.add_argument("--dev-smoke", action="store_true", help="放行非 A40（本机开发冒烟 NATIVE_SMOKE）")
    gen.add_argument("--resume", action="store_true")
    gen.set_defaults(func=cmd_generate)
    pub = sub.add_parser("publish")
    pub.add_argument("--side", choices=SIDES, required=True)
    pub.add_argument("--tier", choices=TIERS, required=True)
    pub.add_argument("--prefix", required=True, help="bucket 侧目录，如 O-1fadc0e-a40、P-ca32e9b-s4、H-<sha7>-a40")
    pub.add_argument("--local", type=Path, default=None)
    pub.add_argument("--code-baseline", default=None)
    pub.add_argument("--gpu-model", default=None)
    pub.add_argument("--driver", default=None)
    pub.add_argument("--workers", type=int, default=16)
    pub.add_argument("--note", default=None)
    pub.add_argument("--readback-tmp", default=str(ROOT / "artifacts" / "hard-split"))
    pub.add_argument("--resume-upload", action="store_true", help="目录已存在时只补缺对象（上传中断后续传）")
    pub.add_argument("--dry-run", action="store_true")
    pub.set_defaults(func=cmd_publish)
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("--pair", choices=PAIRS, required=True)
    cmp_.add_argument("--tier", choices=TIERS, required=True)
    cmp_.add_argument("--manifest", type=Path, required=True)
    cmp_.add_argument("--left", type=Path, default=None)
    cmp_.add_argument("--right", type=Path, default=None)
    cmp_.add_argument("--workers", type=int, default=16)
    cmp_.add_argument("--calibrate", action="store_true")
    cmp_.add_argument("--overwrite-compare", action="store_true")
    cmp_.set_defaults(func=cmd_compare)
    imp = sub.add_parser("import-s4", help="P 侧 xhard 复用 S4 交付存档（只读 symlink）")
    imp.add_argument("--manifest", type=Path, required=True)
    imp.set_defaults(func=cmd_import_s4)
    bind = sub.add_parser("binding", help="ENV_PACKAGE_BINDING：三侧 native identities 的包归属")
    bind.set_defaults(func=cmd_binding)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in ("manifest", "src_root", "out", "stage", "local", "left", "right"):
        value = getattr(args, name, None)
        if isinstance(value, Path) and not value.is_absolute():
            setattr(args, name, (Path.cwd() / value).resolve())
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
