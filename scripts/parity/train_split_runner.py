#!/usr/bin/env python3
"""A 路隔离运行器：用官方 dataset-gen 固定源码跑原 ``_worker``（方案 R4）。

本文件只做三件事：把官方源码目录接上 ``sys.path``、按冻结身份构造官方
``EpisodeJob``、用官方自己的 ``ProcessPoolExecutor(spawn)`` 调官方 ``_worker``。
不改官方源码、不打补丁、不替换求解器或 fail recover，也不做合并与报告
（官方 ``generate_dataset`` 的合并与校验依赖缺失的 ``data/robomme_data_h5``，
方案比较的是 ``hdf5_files/<task>_ep<ep>_seed<seed>.h5`` 原始产物）。

单独成文件的原因：``spawn`` 子进程要能按模块名重新导入官方 ``generate_dataset``
才能反序列化 ``_worker``，因此父进程必须先把官方脚本目录放进 ``sys.path``，
且父进程自身不得先导入本仓库的 ``robomme``（否则子进程继承到的 ``sys.path``
会让官方源码被工作副本遮蔽）。
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


def _strip_working_copy_src(src_root: Path) -> list[str]:
    """把除 ``src_root`` 以外的 ``robomme`` 源码路径（editable 安装的 .pth 注入）移出 sys.path。

    spawn 子进程会继承父进程的 ``sys.path``，所以这里去掉一次即可保证目标源码不被遮蔽。
    返回被移除的条目，供留档。
    """
    official_src = str((src_root / "src").resolve())
    removed: list[str] = []
    for entry in list(sys.path):
        try:
            resolved = str(Path(entry).resolve())
        except OSError:
            continue
        if resolved == official_src:
            continue
        if (Path(resolved) / "robomme" / "__init__.py").exists():
            sys.path.remove(entry)
            removed.append(entry)
    return removed


def _probe_robomme(src_root: Path) -> str:
    """在干净子进程里确认 ``import robomme`` 解析到指定源码树而非别处。"""
    code = (
        "import sys, json;"
        f"sys.path.insert(0, {str(src_root / 'src')!r});"
        "import robomme;print(robomme.__file__)"
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError("robomme 探针失败：\n" + proc.stderr)
    resolved = proc.stdout.strip().splitlines()[-1]
    expected = str((src_root / "src" / "robomme").resolve())
    if not resolved.startswith(expected):
        raise RuntimeError(f"robomme 解析到 {resolved}，不在目标源码 {expected} 下")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A 路隔离运行器（官方 _worker）")
    parser.add_argument("--official-root", required=True, help="官方固定源码根目录（提供 _worker 等编排代码）")
    parser.add_argument(
        "--src-root", default=None,
        help="环境源码树根目录，默认与 --official-root 相同（A 路）；"
             "B 路传本工作副本根目录，官方 _worker 会从这里加载 robomme",
    )
    parser.add_argument("--jobs-json", required=True, help="身份列表 JSON（task/episode/seed/difficulty/worker_dir）")
    parser.add_argument("--results-json", required=True, help="逐条结果输出")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--gpu", default="0")
    parser.add_argument(
        "--sampling-config", default=None,
        help="C／D 路：显式采样配置 JSON（形如 {\"tasks\": {<env>: {...}}}），按 task 取块传给 gym.make",
    )
    parser.add_argument(
        "--force-mirror", action="store_true",
        help="即使不传两个显式输入也走镜像 worker（用于让 B 路产出随机流轨迹）",
    )
    parser.add_argument(
        "--episode-specs", default=None,
        help="D 路：每局规格 JSON（形如 {\"specs\": {<task>/<episode>: {...}}}）",
    )
    parser.add_argument(
        "--identity-source", choices=("train_metadata", "formula"), default="train_metadata",
        help="身份复核来源：train_metadata＝官方 metadata 逐字比（原值五路，默认）；"
             "formula＝V4 xhard 身份按 scripts/parity/v4_specs.py 的 seed 公式硬校验（3.5）",
    )
    args = parser.parse_args(argv)

    official_root = Path(args.official_root).resolve()
    src_root = Path(args.src_root).resolve() if args.src_root else official_root
    script_dir = official_root / "scripts" / "data-generation"
    if not (script_dir / "generate_dataset.py").exists():
        raise SystemExit(f"官方生成脚本不存在：{script_dir / 'generate_dataset.py'}")

    removed = _strip_working_copy_src(src_root)
    probe = _probe_robomme(src_root)
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    import generate_dataset as official  # noqa: E402  官方固定源码

    if Path(official.__file__).resolve() != (script_dir / "generate_dataset.py").resolve():
        raise SystemExit(f"导入到的不是官方脚本：{official.__file__}")

    sampling_by_task: dict = {}
    if args.sampling_config:
        payload = json.loads(Path(args.sampling_config).read_text(encoding="utf-8"))
        sampling_by_task = payload.get("tasks", payload)
    specs_by_identity: dict = {}
    if args.episode_specs:
        payload = json.loads(Path(args.episode_specs).read_text(encoding="utf-8"))
        specs_by_identity = payload.get("specs", payload)
    use_mirror = bool(sampling_by_task or specs_by_identity) or args.force_mirror
    if use_mirror:
        # 子进程要能按模块名 import 本文件所在目录下的 train_split_worker
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

    jobs_payload = json.loads(Path(args.jobs_json).read_text(encoding="utf-8"))
    jobs = []
    if args.identity_source == "train_metadata":
        # 用官方自己的 metadata 读取器复核每条身份，seed 与难度必须逐字相同。
        records_by_task = official.read_train_metadata()
    else:
        # V4：xhard 身份不在官方 metadata 里；改按 V4 seed 公式复核，仍是硬校验。
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from scripts.parity.v4_specs import DIFFICULTY as V4_DIFFICULTY, seed_for as v4_seed_for  # noqa: PLC0415
    for item in jobs_payload:
        task, episode = str(item["task"]), int(item["episode"])
        if args.identity_source == "train_metadata":
            record = records_by_task[task][episode]
            if int(record["seed"]) != int(item["seed"]) or str(record["difficulty"]) != str(item["difficulty"]):
                raise SystemExit(
                    f"{task}/episode_{episode} 身份与官方 metadata 不符："
                    f"manifest=({item['seed']}, {item['difficulty']}) "
                    f"official=({record['seed']}, {record['difficulty']})"
                )
        else:
            expected = v4_seed_for(task, episode, int(item["attempt"]))
            if int(item["seed"]) != expected or str(item["difficulty"]) != V4_DIFFICULTY:
                raise SystemExit(
                    f"{task}/episode_{episode} 身份与 V4 公式不符：jobs=({item['seed']}, {item['difficulty']}) "
                    f"formula=({expected}, {V4_DIFFICULTY})"
                )
        jobs.append(
            official.EpisodeJob(
                task=task,
                episode=episode,
                seed=int(item["seed"]),
                difficulty=str(item["difficulty"]),
                worker_dir=str(item["worker_dir"]),
                gpu=str(args.gpu),
                # 官方 _worker 只用 repo_root 定位 src：A 路指官方源码，B 路指本工作副本，
                # 编排代码始终是官方那一份，因此两路差异只可能来自环境源码本身。
                repo_root=str(src_root),
            )
        )

    # 官方 generate_dataset 在父进程里钉 CUDA_VISIBLE_DEVICES，这里照做。
    os.environ["CUDA_VISIBLE_DEVICES"] = official.GPU_ID
    results: list[dict] = []
    started = time.time()

    def _submit(executor, job):
        """A／B 路用官方 _worker；C／D 路用只多传两个显式输入的镜像 worker。"""
        if not use_mirror:
            return executor.submit(official._worker, job)
        # force_mirror 时两个输入都是 None，镜像 worker 的 gym.make 参数表与官方逐句一致
        import train_split_worker  # noqa: PLC0415 仅 C／D 路需要

        config = sampling_by_task.get(job.task)
        spec = specs_by_identity.get(f"{job.task}/{job.episode}")
        if sampling_by_task and config is None:
            raise SystemExit(f"采样配置缺少环境 {job.task}")
        if specs_by_identity and spec is None:
            raise SystemExit(f"每局规格缺少身份 {job.task}/{job.episode}")
        return executor.submit(train_split_worker.run_one, (job, config, spec))

    with ProcessPoolExecutor(
        max_workers=min(max(args.workers, 1), len(jobs)),
        mp_context=mp.get_context("spawn"),
    ) as executor:
        futures = {_submit(executor, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                results.append(future.result())
            except BaseException as exc:  # noqa: BLE001 与官方同样兜底
                results.append(
                    {
                        "task": job.task,
                        "episode": job.episode,
                        "seed": job.seed,
                        "difficulty": job.difficulty,
                        "gpu": job.gpu,
                        "recovery_mode": job.recovery_mode,
                        "attempt_count": 1,
                        "ok": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
    results.sort(key=lambda item: (str(item["task"]), int(item["episode"])))
    payload = {
        "schema": "train-parity-runner-results/1",
        "official_root": str(official_root),
        "src_root": str(src_root),
        "official_module": str(Path(official.__file__).resolve()),
        "robomme_module": probe,
        "removed_sys_path_entries": removed,
        "workers": args.workers,
        "gpu": args.gpu,
        "sampling_config": args.sampling_config,
        "episode_specs": args.episode_specs,
        "worker": "train_split_worker.run_one" if use_mirror else "official._worker",
        "elapsed_seconds": round(time.time() - started, 3),
        "results": results,
    }
    out = Path(args.results_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = [item for item in results if not item.get("ok")]
    print(f"RUNNER_DONE jobs={len(results)} ok={len(results) - len(failures)} failed={len(failures)}")
    for item in failures:
        print(f"# 失败 {item['task']}/episode_{item['episode']}: {item.get('error_type')} {item.get('error')}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
