"""V1′ 原三档 144 局严格对拍入口（0926-robomme-hard-split-plan.md 第二部分 §2.2）。

逻辑从 V6 S3 运行器 `artifacts/newtask-v6/v6-s3-20260926-01/run_s3.py` 下沉而来，去掉绝对路径：
①先 1 条冒烟（BinFill/0）再剩余 143 条，失败不补跑；②逐局 H5 身份／终态校验；
③子进程独立进程组，30 分钟无日志／文件进展或 4 小时硬上限即停；④调
`train_split_parity.py compare` 与 S0 基线逐对比 sha。不新增任何抽样或 reset。

`--env-package` 经环境变量 `ROBOMME_ENV_PACKAGE` 传给子进程，由 worker 决定 import 哪个包
（worker 侧的读取在拆包阶段 3 落地）。`--dry-run` 只打印将执行的命令，不写盘、不起子进程。

用法::

    uv run --no-sync python -m scripts.parity.hard_parity run --env-package robomme_hard \\
        --manifest scripts/configs/newtask-v3/subset_manifest.json \\
        --base artifacts/newtask-v6/v1/base \\
        --official-root artifacts/train-parity/local-smoke-01/official-src \\
        --output artifacts/newtask-v6/v1-hard --workers 1 --gpus 0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "scripts" / "parity" / "train_split_parity.py"
ENV_PACKAGES = ("robomme", "robomme_hard")
PARTS = ("smoke", "remaining")
EXPECTED_ROWS = 144


class ParityError(RuntimeError):
    """对拍前置、H5 校验或比较失败；一律停止、不重试。"""


def read(path: Path):
    return json.loads(path.read_text())


def write(path: Path, value) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def key(row: dict) -> tuple:
    return tuple(row.get(name) for name in ("task", "episode", "seed", "difficulty", "recovery_mode"))


def identity(row: dict) -> str:
    return f"{row['task']}_episode_{row['episode']}"


def split_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """按既有基线 worker 顺序取 BinFill/0 作冒烟，其余为 remaining；不增加任何身份。"""
    if len(rows) != EXPECTED_ROWS:
        raise ParityError(f"清单应为 {EXPECTED_ROWS} 条，实际 {len(rows)}")
    first = [row for row in rows if row["task"] == "BinFill" and row["episode"] == 0]
    if len(first) != 1:
        raise ParityError("清单里 BinFill/0 缺失或不唯一")
    rest = [row for row in rows if key(row) != key(first[0])]
    return first, rest


def validate_h5(run_dir: Path, rows: list[dict], label: str) -> dict:
    """先核验成功轨迹与身份，再允许字节比较；相同空文件不能过关。"""
    import h5py

    def check(cond, message):
        if not cond:
            raise ParityError(message)

    expected = {identity(r): r for r in rows}
    check(len(expected) == len(rows), "身份重复")
    side = run_dir / "B"
    actual = {p.name for p in side.iterdir() if p.is_dir()} if side.is_dir() else set()
    check(actual == set(expected), f"{label} 身份目录不完整或有额外身份")
    total_steps = 0
    for name, row in expected.items():
        files = list((side / name / "hdf5_files").glob("*.h5"))
        check(len(files) == 1, f"{label}/{name} HDF5缺失或不唯一")
        path = files[0]
        check(path.name == f"{row['task']}_ep{row['episode']}_seed{row['seed']}.h5", f"{path} 文件名身份错误")
        try:
            handle = h5py.File(path, "r")
        except OSError as error:
            raise ParityError(f"{path} 无法打开：{error}") from error
        with handle:
            ep_name = f"episode_{row['episode']}"
            check(list(handle) == [ep_name], f"{path} episode身份错误")
            episode = handle[ep_name]
            check(int(episode["setup/seed"][()]) == row["seed"], f"{path} seed身份错误")
            difficulty = episode["setup/difficulty"][()]
            if isinstance(difficulty, bytes):
                difficulty = difficulty.decode()
            check(difficulty == row["difficulty"], f"{path} 难度身份错误")
            indices = sorted(int(n.removeprefix("timestep_")) for n in episode if n.startswith("timestep_"))
            check(bool(indices) and indices == list(range(len(indices))), f"{path} 时间步为空或不连续")
            terminal = episode[f"timestep_{indices[-1]}/info/is_completed"]
            check(terminal.shape == () and terminal.dtype.kind == "b" and bool(terminal[()]), f"{path} 终端未严格完成")
            total_steps += len(indices)
    print(f"HARD_H5_SEMANTICS=PASS side={label} identities={len(rows)} terminal_success={len(rows)} "
          f"timesteps={total_steps}", flush=True)
    return {"label": label, "identities": len(rows), "valid_h5": len(rows),
            "terminal_success": len(rows), "timestep_count": total_steps}


def supervise(argv: list[str], log: Path, env: dict, progress_root: Path | None = None,
              idle_seconds: float = 1800, hard_seconds: float = 14400) -> None:
    """独立进程组；30分钟无日志/文件进展或4小时硬上限即停止，不重试。"""
    def stop_group(proc):
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            proc.poll()
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()

    def interrupted(signum, _frame):
        raise RuntimeError(f"收到信号 {signum}，停止本命令进程组")

    with log.open("x") as stream:
        proc = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=True)
        previous = {s: signal.signal(s, interrupted) for s in (signal.SIGTERM, signal.SIGINT)}
        started = last_progress = last_scan = time.monotonic()
        fingerprint = None
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map() or proc.poll() is None:
                for entry, _ in selector.select(timeout=0.1):
                    chunk = os.read(entry.fd, 65536)
                    if not chunk:
                        selector.unregister(entry.fileobj)
                        continue
                    text = chunk.decode("utf-8", errors="replace")
                    print(text, end="", flush=True)
                    stream.write(text)
                    stream.flush()
                    last_progress = time.monotonic()
                now = time.monotonic()
                if progress_root is not None and now - last_scan >= 5:
                    # 持续写盘只算进展，不把文件存在或增长误记为成功身份。
                    states = []
                    if progress_root.exists():
                        for path in progress_root.rglob("*"):
                            try:
                                if path.is_file():
                                    stat = path.stat()
                                    states.append((str(path), stat.st_size, stat.st_mtime_ns))
                            except FileNotFoundError:
                                continue
                    current = tuple(sorted(states))
                    if current and current != fingerprint:
                        last_progress = now
                    fingerprint = current
                    last_scan = now
                if now - started > hard_seconds or now - last_progress > idle_seconds:
                    raise TimeoutError(f"监督超时：elapsed={now-started:.1f}s idle={now-last_progress:.1f}s；停止且不重试")
            code = proc.wait()
            stream.write(f"EXIT_CODE={code}\n")
        except BaseException as error:
            stream.write(f"SUPERVISION=STOP reason={error}\nEXIT_CODE=124\n")
            stream.flush()
            raise
        finally:
            selector.close()
            proc.stdout.close()
            stop_group(proc)
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    if code:
        raise ParityError(f"命令失败，停止且不重试：{log}，退出码 {code}")


def run_command(args, part: str) -> list[str]:
    return ["uv", "run", "--no-sync", "python", str(ENTRY), "run",
            "--manifest", str(args.output / f"{part}_manifest.json"), "--paths", "B",
            "--workers", str(args.workers), "--gpus", args.gpus, "--official-root", str(args.official_root),
            "--output", str(args.output / part)]


def compare_command(args) -> list[str]:
    combined = args.output / "combined"
    return ["uv", "run", "--no-sync", "python", str(ENTRY), "compare",
            "--run", f"base={args.base}", "--run", f"hard={combined}", "--pair", "base/B:hard/B",
            "--output", str(args.output / "compare")]


def child_env(args) -> dict:
    env = os.environ.copy()
    env.update(CUDA_VISIBLE_DEVICES=args.gpus, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               PYTHONUNBUFFERED="1", ROBOMME_ENV_PACKAGE=args.env_package)
    return env


def preflight(args, rows: list[dict]) -> str:
    """基线身份闸门：依赖、清单与官方源码树必须与 S0 基线 run_config 一致。返回基线配置 sha256。"""
    config_path = args.base / "run_config.json"
    baseline = read(config_path)
    for filename, field in (("uv.lock", "uv_lock_sha256"), ("pyproject.toml", "pyproject_sha256")):
        if hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() != baseline["environment"][field]:
            raise ParityError(f"{filename} 与基线不一致")
    if hashlib.sha256(args.manifest.read_bytes()).hexdigest() != baseline["manifest_sha256"]:
        raise ParityError("清单 sha256 与基线不一致")
    if (args.official_root / ".official_tree").read_text().strip() != baseline["official_tree"]:
        raise ParityError("官方源码树与基线不一致")
    return hashlib.sha256(config_path.read_bytes()).hexdigest()


def cmd_run(args) -> int:
    original = read(args.manifest)
    rows = original["rows"]
    parts = dict(zip(PARTS, split_rows(rows)))
    if args.dry_run:
        env = child_env(args)
        print(f"# env CUDA_VISIBLE_DEVICES={env['CUDA_VISIBLE_DEVICES']} ROBOMME_ENV_PACKAGE={env['ROBOMME_ENV_PACKAGE']}")
        for part in PARTS:
            print(" ".join(run_command(args, part)))
        print(" ".join(compare_command(args)))
        return 0
    base_sha = preflight(args, rows)
    if args.output.exists():
        raise ParityError(f"禁止覆盖或重跑：{args.output}")
    args.output.mkdir(parents=True)
    source_sha = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    for part, part_rows in parts.items():
        # 派生清单明确使用自己的元数据，不冒充原完整冻结清单。
        write(args.output / f"{part}_manifest.json", {
            "schema": "train-parity-manifest/1", "kind": "v1-hard-fixed-subset",
            "source_manifest": str(args.manifest), "source_manifest_sha256": source_sha,
            "source_ref": original["source_ref"], "rows_total": len(part_rows), "rows": part_rows})
    write(args.output / "launch.json", {
        "schema": "v1-hard-launch/1", "cwd": str(ROOT), "env_package": args.env_package,
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "baseline_config": str(args.base / "run_config.json"), "baseline_config_sha256": base_sha,
        "attempt_limit": EXPECTED_ROWS})
    env = child_env(args)
    all_results = []
    for part in PARTS:
        destination = args.output / part
        supervise(run_command(args, part), args.output / f"{part}.log", env, progress_root=destination)
        results = read(destination / "results/B.json")["results"]
        if sorted(map(key, results)) != sorted(map(key, parts[part])):
            raise ParityError(f"{part} 结果身份与清单不符")
        if not all(row["ok"] and row.get("attempt_count") == 1 for row in results):
            raise ParityError(f"{part} 存在失败或重试身份")
        if not all(Path(row["raw_h5_path"]).is_file() for row in results):
            raise ParityError(f"{part} 原始 H5 缺失")
        validate_h5(destination, parts[part], part)
        all_results.extend(results)
        print(f"HARD_PART=PASS part={part} count={len(results)}", flush=True)
    # 只建立指向本轮实际输出的只读比较视图，原始配置、路径和结果不搬动。
    combined = args.output / "combined"
    (combined / "B").mkdir(parents=True)
    (combined / "results").mkdir()
    for part in PARTS:
        for ident in (args.output / part / "B").iterdir():
            if ident.is_dir():
                (combined / "B" / ident.name).symlink_to(ident, target_is_directory=True)
    write(combined / "provenance.json", {"schema": "v1-hard-comparison-view/1",
          "note": "本目录仅为比较视图，不是一次独立运行；配置以两次真实运行记录为准。",
          "source_runs": [str(args.output / p) for p in PARTS]})
    write(combined / "results/B.json", {"schema": "v1-hard-merged-results/1", "results": all_results,
          "source_results": [str(args.output / p / "results/B.json") for p in PARTS]})
    semantics = [validate_h5(args.base, rows, "base"), validate_h5(combined, rows, "hard")]
    write(args.output / "h5_semantics.json", {"schema": "v1-hard-h5-semantics/1", "sides": semantics})
    supervise(compare_command(args), args.output / "compare.log", env)
    pairs = [json.loads(line) for line in (args.output / "compare/h5_pairs.jsonl").read_text().splitlines()]
    if len(pairs) != EXPECTED_ROWS or {row["identity"] for row in pairs} != {identity(r) for r in rows}:
        raise ParityError("比较对数或身份不符")
    sha_equal = sum(row["sha_equal"] == 1 for row in pairs)
    mismatch = sum(row["field_mismatch"] for row in pairs)
    verdict = "PASS" if sha_equal == EXPECTED_ROWS and mismatch == 0 else "FAIL"
    print(f"NATIVE_REGRESSION_HARD={verdict} compared={len(pairs)} sha_equal={sha_equal} "
          f"field_mismatch={mismatch} env_package={args.env_package} base={base_sha}", flush=True)
    return 0 if verdict == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="冒烟 1 条 + 剩余 143 条 + 与基线逐对比 sha")
    run.add_argument("--env-package", choices=ENV_PACKAGES, required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--base", type=Path, required=True)
    run.add_argument("--official-root", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--gpus", default="0")
    run.add_argument("--dry-run", action="store_true", help="只打印将执行的命令")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in ("manifest", "base", "official_root", "output"):
        path = getattr(args, name)
        setattr(args, name, path if path.is_absolute() else ROOT / path)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
