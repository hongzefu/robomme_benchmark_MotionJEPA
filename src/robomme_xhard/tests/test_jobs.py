"""S3 定向测试：xhard 作业展开与生成器开关（纯 CPU，不 gym.make、不起仿真、不用 GPU）。

两条判定行：
- XHARD_BASELINE_EQ=PASS：旧比例参数下，新版生成器与 BASE（da32a8b1）的 _args 解析、
  jobs 列表、gym.make 名字、run_parameters / metadata / run_summary 输出逐项相同（RL2）。
- XHARD_JOBS=PASS jobs=52 mothers=16 attempt0=1：合成的“每任务 2 个母 seed”清单展开正确。
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from robomme_xhard import jobs as xj
from robomme_xhard.configs import DIFFICULTIES, SOURCE_DIFFICULTY, TASK_ORDER, valid_pairs

BASE_SHA = "da32a8b1"
REPO_ROOT = Path(__file__).resolve().parents[3]
GEN_REL = "scripts/data-generation-newSeed/generate_dataset_newseed.py"
GEN_PATH = REPO_ROOT / GEN_REL
ALL_XHARD = ",".join(DIFFICULTIES)

# 旧比例参数组合：用于关闭态逐项比较
OLD_ARGVS = [
    ["--output-dir", "OUT"],
    ["--output-dir", "OUT", "--difficulty", "211"],
    ["--output-dir", "OUT", "--env", "VideoUnmask,ButtonUnmask", "--episodes", "5", "--difficulty", "211"],
    ["--output-dir", "OUT", "--env", "PickXtimes", "--episodes", "3", "--episode-start", "100", "--difficulty", "001"],
    ["--output-dir", "OUT", "--env", "all", "--episodes", "2", "--difficulty", "010", "--layout", "test"],
    ["--output-dir", "OUT", "--env", "BinFill,RouteStick", "--episodes", "4", "--workers", "3", "--gpus", "0,1",
     "--max-attempts", "5", "--no-limit-threads", "--max-tasks-per-child", "0", "--affinity", "per-gpu"],
]
NEW_ARG_DEFAULTS = {"mother_manifest": None, "with_mother": False, "mother_rank": None,
                    "difficulty_cycle": None, "stop_on_pool_crash": False}
NEW_JOB_DEFAULTS = {"card_role": None, "make_name": None, "source_difficulty": None,
                    "xhard_values": (), "recovery": "auto"}


def _exec_module(name: str, source: str) -> types.ModuleType:
    """以真实生成器路径为 __file__ 执行源码，使 SCRIPT_DIR / REPO_ROOT 与新版一致。"""
    module = types.ModuleType(name)
    module.__file__ = str(GEN_PATH)
    sys.modules[name] = module  # dataclass 处理需要模块已登记
    exec(compile(source, str(GEN_PATH), "exec"), module.__dict__)
    return module


@pytest.fixture(scope="module")
def new_gen() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("_s3_gen_new", GEN_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_s3_gen_new"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def base_gen() -> types.ModuleType:
    source = subprocess.run(
        ["git", "show", f"{BASE_SHA}:{GEN_REL}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return _exec_module("_s3_gen_base", source)


def _fake_run(store: dict):
    """替身 _run_jobs：记录作业，并把每个作业当作成功返回（不建进程池）。"""

    def fake(jobs, **kwargs):
        store["jobs"] = list(jobs)
        store["kwargs"] = kwargs
        succeeded = [
            {
                "task": job.task,
                "episode": job.episode,
                "attempt": job.attempt,
                "seed": job.seed,
                "difficulty": job.difficulty,
                "ok": True,
                "peak_rss_mb": 1.0,
                "timestep_count": 100 + index,
                "h5_path": str(Path(job.output_root) / "hdf5_files" / f"{job.task}_ep{job.episode}_seed{job.seed}.h5"),
            }
            for index, job in enumerate(jobs)
        ]
        return succeeded, []

    return fake


def _run_generate(module, monkeypatch, out: Path, args) -> dict:
    store: dict = {}
    out.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(module, "_run_jobs", _fake_run(store))
    monkeypatch.setattr(module, "_prepare_output", lambda value: Path(value))
    kwargs = dict(
        output_dir=str(out),
        env=args.env,
        episodes=args.episodes,
        episode_start=args.episode_start,
        workers=args.workers,
        gpus=args.gpus,
        difficulty_ratio=args.difficulty_ratio,
        layout_name=args.layout,
        max_attempts=args.max_attempts,
        limit_threads=args.limit_threads,
        max_tasks_per_child=args.max_tasks_per_child or None,
        affinity=args.affinity,
    )
    for key in NEW_ARG_DEFAULTS:
        if hasattr(args, key):
            kwargs[key] = getattr(args, key)
    store["summary"] = module.generate_dataset_newseed(**kwargs)
    return store


def _strip_volatile(summary: dict) -> dict:
    return {k: v for k, v in summary.items() if k not in ("elapsed_s", "throughput_ep_per_min")}


def _read_outputs(out: Path) -> dict[str, bytes]:
    files = {}
    for path in sorted(out.rglob("*.json")):
        if path.name == "run_summary.json":
            continue
        files[str(path.relative_to(out))] = path.read_bytes()
    return files


# ── 关闭态：与 BASE 逐项相同（RL2） ─────────────────────────────────────────


def test_baseline_equivalence(new_gen, base_gen, monkeypatch, tmp_path, capsys):
    compared_jobs = 0
    for index, argv in enumerate(OLD_ARGVS):
        argv = [str(tmp_path) if item == "OUT" else item for item in argv]
        new_args = new_gen._args(argv)
        base_args = base_gen._args(argv)
        new_vars, base_vars = vars(new_args), vars(base_args)
        assert {k: new_vars[k] for k in base_vars} == base_vars
        assert {k: new_vars[k] for k in NEW_ARG_DEFAULTS} == NEW_ARG_DEFAULTS
        assert set(new_vars) == set(base_vars) | set(NEW_ARG_DEFAULTS)

        base_store = _run_generate(base_gen, monkeypatch, tmp_path / f"base{index}", base_args)
        new_store = _run_generate(new_gen, monkeypatch, tmp_path / f"new{index}", new_args)

        base_jobs, new_jobs = base_store["jobs"], new_store["jobs"]
        assert len(base_jobs) == len(new_jobs) > 0
        for old, new in zip(base_jobs, new_jobs):
            old_fields = dataclasses.asdict(old)
            new_fields = dataclasses.asdict(new)
            old_fields["output_root"] = Path(old_fields["output_root"]).name
            new_fields["output_root"] = Path(new_fields["output_root"]).name.replace("new", "base")
            assert {k: new_fields[k] for k in old_fields} == old_fields
            assert {k: new_fields[k] for k in NEW_JOB_DEFAULTS} == NEW_JOB_DEFAULTS
            assert new.gym_id == old.task  # gym.make 名字不变
            assert new.fixed_seed is False
            assert new.recovery_mode == old.recovery_mode
            compared_jobs += 1
        # _run_jobs 收到的其余参数也一致（旧模式不传 xhard_mode）
        new_kwargs, base_kwargs = dict(new_store["kwargs"]), dict(base_store["kwargs"])
        assert new_kwargs.pop("jsonl_path").name == base_kwargs.pop("jsonl_path").name
        assert new_kwargs == base_kwargs

        # run_parameters 与各任务 metadata 逐字节相同（output_dir 字段按目录名替换后比较）
        base_files = _read_outputs(tmp_path / f"base{index}")
        new_files = _read_outputs(tmp_path / f"new{index}")
        assert set(base_files) == set(new_files)
        for name, data in base_files.items():
            fixed = new_files[name].replace(f"new{index}".encode(), f"base{index}".encode())
            assert fixed == data, name
        base_summary = json.loads((tmp_path / f"base{index}" / "run_summary.json").read_text())
        new_summary = json.loads(
            (tmp_path / f"new{index}" / "run_summary.json").read_text().replace(f"new{index}", f"base{index}")
        )
        assert _strip_volatile(new_summary) == _strip_volatile(base_summary)

    with capsys.disabled():
        print(f"\nXHARD_BASELINE_EQ=PASS argv_sets={len(OLD_ARGVS)} jobs_compared={compared_jobs} jobs_diff=0 names_diff=0")


def test_old_mode_rejects_mother_flags(new_gen, tmp_path):
    for extra in (["--with-mother"], ["--mother-rank", "0"], ["--mother-manifest", "x.json"]):
        with pytest.raises(SystemExit):
            new_gen._args(["--output-dir", str(tmp_path), "--difficulty", "211", *extra])


# ── xhard 作业展开 ────────────────────────────────────────────────────────


def _synthetic_manifest(ranks=(0, 1)) -> dict:
    tasks = {}
    for code, task in enumerate(TASK_ORDER, start=1):
        tasks[task] = [
            {
                "episode": 10 + rank,
                "seed": code * 1000 + 1000 + rank * 100,
                "source_difficulty": SOURCE_DIFFICULTY[task],
                "rank": rank,
            }
            for rank in ranks
        ]
    return {"version": 1, "tasks": tasks}


def test_expand_cards_counts_and_identity(capsys):
    manifest = _synthetic_manifest()
    seeds = {(t, e["episode"]): e["seed"] for t, es in manifest["tasks"].items() for e in es}
    pairs = valid_pairs()
    assert len(pairs) == 52

    cards_all = xj.expand_cards(manifest, DIFFICULTIES, with_mother=True)
    xhard_all = [c for c in cards_all if c.role == xj.ROLE_XHARD]
    mother_all = [c for c in cards_all if c.role == xj.ROLE_MOTHER]
    assert len(xhard_all) == 52 * 2
    assert len(mother_all) == 16 * 2

    cards = xj.expand_cards(manifest, DIFFICULTIES, with_mother=True, mother_rank=0)
    xhard = [c for c in cards if c.role == xj.ROLE_XHARD]
    mothers = [c for c in cards if c.role == xj.ROLE_MOTHER]
    assert len(xhard) == 52
    assert len(mothers) == 16
    assert sorted((c.task, c.difficulty) for c in xhard) == sorted(pairs)
    assert all(c.rank == 0 for c in cards)
    attempt0 = all(c.attempt == 0 for c in cards_all)
    assert attempt0
    # seed 与清单一致、母卡 difficulty = source_difficulty、名字正确
    for card in cards_all:
        assert card.seed == seeds[(card.task, card.mother_episode)]
        assert card.source_difficulty == SOURCE_DIFFICULTY[card.task]
        if card.role == xj.ROLE_MOTHER:
            assert card.difficulty == card.source_difficulty
            assert xj.make_name(card) == card.task
        else:
            assert card.difficulty in DIFFICULTIES
            assert xj.make_name(card) == f"{card.task}XHard"
    # MoveCube、InsertPeg 只有母卡
    assert {c.task for c in xhard_all}.isdisjoint({"MoveCube", "InsertPeg"})
    assert {"MoveCube", "InsertPeg"} <= {c.task for c in mother_all}
    # 身份唯一
    assert len({c.identity for c in cards_all}) == len(cards_all)
    # 排序：官网任务顺序 → difficulty（母卡最前）→ rank
    keys = [
        (TASK_ORDER.index(c.task), -1 if c.role == xj.ROLE_MOTHER else DIFFICULTIES.index(c.difficulty), c.rank)
        for c in cards_all
    ]
    assert keys == sorted(keys)
    # 不带 --with-mother 时没有母卡
    assert all(c.role == xj.ROLE_XHARD for c in xj.expand_cards(manifest, DIFFICULTIES))

    with capsys.disabled():
        print(f"\nXHARD_JOBS=PASS jobs={len(xhard)} mothers={len(mothers)} attempt0={int(attempt0)}")


def test_output_roots_isolated(tmp_path):
    cards = xj.expand_cards(_synthetic_manifest(), DIFFICULTIES, with_mother=True)
    roots = {xj.card_output_root(tmp_path, c) for c in cards}
    assert roots == {tmp_path / d for d in DIFFICULTIES} | {tmp_path / "mother"}
    # 同一输出根内 h5 文件名（task_ep_seed）互不相同
    names = {(xj.card_output_root(tmp_path, c), f"{c.task}_ep{c.mother_episode}_seed{c.seed}.h5") for c in cards}
    assert len(names) == len(cards)


def test_parse_difficulties_errors():
    assert xj.parse_difficulties("xhard20, XHARD12") == ("xhard12", "xhard20")
    for bad in ("211,xhard12", "hard,xhard12", "xhard13", "xhard12,xhard12", "xhard12,,xhard14", ""):
        with pytest.raises(xj.XHardJobError):
            xj.parse_difficulties(bad)


def test_manifest_validation_errors(tmp_path):
    good = _synthetic_manifest()
    xj.validate_manifest(good)
    broken = []
    m = json.loads(json.dumps(good)); m["version"] = 2; broken.append(m)
    m = json.loads(json.dumps(good)); m["tasks"]["NoSuchTask"] = m["tasks"]["BinFill"]; broken.append(m)
    m = json.loads(json.dumps(good)); m["tasks"]["BinFill"][0]["source_difficulty"] = "medium"; broken.append(m)
    m = json.loads(json.dumps(good)); m["tasks"]["VideoRepick"][0]["source_difficulty"] = "hard"; broken.append(m)
    m = json.loads(json.dumps(good)); m["tasks"]["BinFill"][1]["rank"] = 0; broken.append(m)
    m = json.loads(json.dumps(good)); m["tasks"]["BinFill"][0]["rank"] = -1; broken.append(m)
    m = json.loads(json.dumps(good)); m["tasks"]["BinFill"][0]["episode"] = 100; broken.append(m)
    m = json.loads(json.dumps(good)); m["tasks"]["BinFill"][0]["seed"] = True; broken.append(m)
    m = json.loads(json.dumps(good)); del m["tasks"]["BinFill"][0]["episode"]; broken.append(m)
    for data in broken:
        with pytest.raises(xj.XHardJobError):
            xj.validate_manifest(data)
    with pytest.raises(xj.XHardJobError):
        xj.load_manifest(tmp_path / "missing.json")
    # 指定任务不在清单里 / 缺少 rank
    partial = {"version": 1, "tasks": {"BinFill": good["tasks"]["BinFill"][:1]}}
    with pytest.raises(xj.XHardJobError):
        xj.expand_cards(partial, DIFFICULTIES, tasks=["PickXtimes"])
    with pytest.raises(xj.XHardJobError):
        xj.expand_cards(partial, DIFFICULTIES, mother_rank=1)
    with pytest.raises(xj.XHardJobError):
        xj.expand_cards(good, ["xhard13"])


# ── 生成器 xhard 模式（替身 _run_jobs，不建进程池） ──────────────────────────


def test_generator_cli_xhard(new_gen, tmp_path):
    manifest = tmp_path / "mother.json"
    manifest.write_text(json.dumps(_synthetic_manifest()), encoding="utf-8")
    args = new_gen._args(
        ["--outdir", str(tmp_path / "o"), "--difficulty", ALL_XHARD, "--mother-manifest", str(manifest),
         "--with-mother", "--mother-rank", "0"]
    )
    assert args.output_dir == str(tmp_path / "o")
    assert args.with_mother is True and args.mother_rank == 0
    with pytest.raises(SystemExit):  # 混用旧比例参数
        new_gen._args(["--output-dir", "o", "--difficulty", "211,xhard12", "--mother-manifest", str(manifest)])
    with pytest.raises(SystemExit):  # xhard 模式缺清单
        new_gen._args(["--output-dir", "o", "--difficulty", "xhard12"])
    with pytest.raises(SystemExit):  # rank 越界
        new_gen._args(["--output-dir", "o", "--difficulty", "xhard12", "--mother-manifest", "m", "--mother-rank", "-1"])


def test_generator_xhard_mode(new_gen, monkeypatch, tmp_path):
    manifest = tmp_path / "mother.json"
    manifest.write_text(json.dumps(_synthetic_manifest()), encoding="utf-8")
    out = tmp_path / "pilot"
    args = new_gen._args(
        ["--output-dir", str(out), "--difficulty", ALL_XHARD, "--mother-manifest", str(manifest),
         "--with-mother", "--mother-rank", "0", "--workers", "4"]
    )
    store = _run_generate(new_gen, monkeypatch, out, args)
    jobs = store["jobs"]
    assert store["kwargs"]["xhard_mode"] is True
    assert len(jobs) == 52 + 16
    assert all(job.attempt == 0 and job.fixed_seed for job in jobs)
    for job in jobs:
        expected_root = out / ("mother" if job.card_role == "mother" else job.difficulty)
        assert Path(job.output_root) == expected_root
        if job.card_role == "mother":
            assert job.gym_id == job.task and job.difficulty == SOURCE_DIFFICULTY[job.task]
        else:
            assert job.gym_id == f"{job.task}XHard" and job.difficulty in DIFFICULTIES
    # metadata：每个子目录各自写，记录额外字段
    meta = json.loads((out / "xhard12" / "record_dataset_BinFill_metadata.json").read_text())
    record = meta["records"][0]
    assert record["difficulty"] == "xhard12" and record["source_difficulty"] == "hard"
    assert record["attempt"] == 0 and record["mother_episode"] == record["episode"]
    assert (out / "mother" / "record_dataset_MoveCube_metadata.json").is_file()
    assert not (out / "xhard12" / "record_dataset_MoveCube_metadata.json").exists()
    repick = json.loads((out / "mother" / "record_dataset_VideoRepick_metadata.json").read_text())
    assert repick["records"][0]["difficulty"] == "medium"
    # run_summary 每卡一行
    summary = json.loads((out / "run_summary.json").read_text())
    rows = summary["cards"]
    assert len(rows) == 68
    expected_keys = {"task", "difficulty", "source_difficulty", "mother_episode", "seed", "ok",
                     "task_success", "timesteps", "h5", "error"}
    assert all(expected_keys <= set(row) for row in rows)
    assert summary["exhausted_count"] == 0

    # 再跑一次：H5 已存在则拒绝覆盖
    first = jobs[0]
    h5 = new_gen._h5_path(Path(first.output_root), first)
    h5.parent.mkdir(parents=True, exist_ok=True)
    h5.write_bytes(b"")
    with pytest.raises(new_gen.DatasetGenerationError):
        _run_generate(new_gen, monkeypatch, out, args)


def test_generator_xhard_rejects_bad_inputs(new_gen, monkeypatch, tmp_path):
    manifest = tmp_path / "mother.json"
    manifest.write_text(json.dumps(_synthetic_manifest()), encoding="utf-8")
    base = ["--output-dir", str(tmp_path / "o"), "--mother-manifest", str(manifest)]
    for extra in (["--difficulty", "xhard13"], ["--difficulty", "xhard12", "--episodes", "3"]):
        args = new_gen._args([*base, *extra])
        with pytest.raises(new_gen.DatasetGenerationError):
            _run_generate(new_gen, monkeypatch, tmp_path / "o", args)
    # 直接调用时混用也报错
    with pytest.raises(new_gen.DatasetGenerationError):
        new_gen.generate_dataset_newseed(output_dir=str(tmp_path / "o"), difficulty_ratio="211,xhard12",
                                         mother_manifest=str(manifest))
    with pytest.raises(new_gen.DatasetGenerationError):
        new_gen.generate_dataset_newseed(output_dir=str(tmp_path / "o"), difficulty_ratio="211", with_mother=True)


def test_fixed_seed_failure_never_bumps(new_gen):
    """固定 seed 卡片：EpisodeJob 有 fixed_seed，_run_jobs 中只在非固定卡片上调用 bump（源码静态核对）。"""
    import inspect

    source = inspect.getsource(new_gen._run_jobs)
    assert "if job.fixed_seed:" in source
    assert "pending.append(job)" in source and "pending.appendleft(job)" in source
    job = new_gen.EpisodeJob(task="BinFill", episode=10, attempt=0, seed=5000, difficulty="xhard12",
                             output_root="x", repo_root="y", card_role="xhard", make_name="BinFillXHard",
                             source_difficulty="hard")
    assert job.fixed_seed and job.gym_id == "BinFillXHard"


def test_worker_import_order(new_gen):
    """worker 内 import robomme_xhard 必须在 import robomme.robomme_env 之后，且不在文件顶部。"""
    import inspect

    for func in (new_gen._pool_init, new_gen._worker):
        source = inspect.getsource(func)
        assert source.index("import robomme.robomme_env") < source.index("import robomme_xhard")
    top = GEN_PATH.read_text(encoding="utf-8").split("\ndef ", 1)[0]
    assert "robomme_xhard" not in top


# ---------------------------------------------------------------- 固定 seed 卡片的调度行为（替身进程池驱动）
#
# 用假进程池替换生成器模块里的 ProcessPoolExecutor：submit 不起任何进程，按脚本立即返回一个
# 已完成（或永不完成）的 concurrent.futures.Future；_run_jobs 里真实的 wait / BrokenProcessPool 分支照常走。
# 判定行：XHARD_FIXED_SEED_BEHAVIOR=PASS


class _FakePool:
    """替身进程池：按卡片身份消费预设结局，并把每次提交的卡片原样记入日志。"""

    instances: list["_FakePool"] = []

    def __init__(self, script, submitted, **kwargs):
        self.script = script
        self.submitted = submitted
        self.kwargs = kwargs
        self.shutdown_calls = 0
        _FakePool.instances.append(self)

    def submit(self, fn, job):
        from concurrent.futures import Future

        self.submitted.append(job)
        outcome = self.script[(job.task, job.episode, job.difficulty)].pop(0)
        future: Future = Future()
        if outcome == "hang":  # 永不完成：模拟池崩溃时仍在途的卡片
            return future
        if isinstance(outcome, BaseException):
            future.set_exception(outcome)
            return future
        future.set_result({
            "task": job.task, "episode": job.episode, "attempt": job.attempt, "seed": job.seed,
            "difficulty": job.difficulty, "wall_s": 0.0, **outcome,
        })
        return future

    def shutdown(self, wait=True, cancel_futures=False):
        self.shutdown_calls += 1


def _card(new_gen, task, episode, seed, difficulty, role="xhard"):
    return new_gen.EpisodeJob(
        task=task, episode=episode, attempt=0, seed=seed, difficulty=difficulty,
        output_root="x", repo_root="y", card_role=role,
        make_name=f"{task}XHard" if role == "xhard" else None, source_difficulty="hard",
    )


def _drive(new_gen, monkeypatch, tmp_path, jobs, script, workers):
    submitted: list = []
    _FakePool.instances = []
    monkeypatch.setattr(new_gen, "ProcessPoolExecutor",
                        lambda **kwargs: _FakePool(script, submitted, **kwargs))
    jsonl = tmp_path / "episode_results.jsonl"
    succeeded, exhausted = new_gen._run_jobs(
        jobs, ["0"], workers, "train", jsonl, max_attempts=5, max_tasks_per_child=None,
        cpu_plan={}, xhard_mode=True,
    )
    lines = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
    return succeeded, exhausted, submitted, lines


def test_fixed_seed_run_jobs_failures_are_final_and_infra_requeues(new_gen, monkeypatch, tmp_path):
    """任务失败与代码错误不 bump、直接记最终；infra 原卡重排，连续 3 次放弃，中途成功则记成功。"""
    x_task = _card(new_gen, "BinFill", 7, 4701, "xhard12")
    m_code = _card(new_gen, "PickXtimes", 7, 1700, "hard", role="mother")
    x_infra3 = _card(new_gen, "StopCube", 59, 7900, "xhard14")
    x_infra2 = _card(new_gen, "RouteStick", 7, 16700, "xhard20")
    m_infra3 = _card(new_gen, "PatternLock", 7, 15700, "hard", role="mother")
    script = {
        ("BinFill", 7, "xhard12"): [{"ok": False, "failure_class": "task", "error_type": "SceneGenerationError"}],
        ("PickXtimes", 7, "hard"): [{"ok": False, "failure_class": "code", "error_type": "KeyError"}],
        # infra 两种来源：worker 抛出的异常（父进程合成 infra）与结果里直接标 infra
        ("StopCube", 59, "xhard14"): [RuntimeError("w1"), RuntimeError("w2"), RuntimeError("w3"), {"ok": True}],
        ("RouteStick", 7, "xhard20"): [RuntimeError("w1"), {"ok": False, "failure_class": "infra"}, {"ok": True}],
        ("PatternLock", 7, "hard"): [{"ok": False, "failure_class": "infra"}] * 3 + [{"ok": True}],
    }
    jobs = [x_task, m_code, x_infra3, x_infra2, m_infra3]
    succeeded, exhausted, submitted, lines = _drive(new_gen, monkeypatch, tmp_path, jobs, script, workers=1)

    # 每次提交的都是原卡片：seed 与 attempt 从不改变（没有任何 bump）
    originals = {(j.task, j.episode, j.difficulty): j for j in jobs}
    for job in submitted:
        assert job == originals[(job.task, job.episode, job.difficulty)]
        assert job.attempt == 0
    counts = {key: sum(1 for j in submitted if (j.task, j.episode, j.difficulty) == key) for key in originals}
    assert counts == {
        ("BinFill", 7, "xhard12"): 1,       # 任务失败：只跑一次
        ("PickXtimes", 7, "hard"): 1,       # 代码错误：只跑一次
        ("StopCube", 59, "xhard14"): 3,     # 连续 3 次 infra：第 3 次放弃，第 4 个结局不会被消费
        ("RouteStick", 7, "xhard20"): 3,    # 两次 infra 后成功
        ("PatternLock", 7, "hard"): 3,      # 母卡同样连续 3 次放弃
    }
    assert script[("StopCube", 59, "xhard14")] == [{"ok": True}]
    assert script[("PatternLock", 7, "hard")] == [{"ok": True}]

    ex = {(r["task"], r["episode"], r["difficulty"]): r for r in exhausted}
    assert set(ex) == {("BinFill", 7, "xhard12"), ("PickXtimes", 7, "hard"),
                       ("StopCube", 59, "xhard14"), ("PatternLock", 7, "hard")}
    assert ex[("BinFill", 7, "xhard12")]["failure_class"] == "task"
    assert ex[("PickXtimes", 7, "hard")]["failure_class"] == "code"
    assert ex[("StopCube", 59, "xhard14")]["failure_class"] == "infra"
    assert ex[("StopCube", 59, "xhard14")]["card_role"] == "xhard"
    for record in exhausted:
        key = (record["task"], record["episode"], record["difficulty"])
        assert (record["seed"], record["attempt"]) == (originals[key].seed, 0)
    assert [(r["task"], r["seed"], r["attempt"]) for r in succeeded] == [("RouteStick", 16700, 0)]
    # jsonl 逐次落盘：1 + 1 + 3 + 3 + 3 = 11 行，全部 attempt 0
    assert len(lines) == 11 and all(line["attempt"] == 0 for line in lines)
    assert len(_FakePool.instances) == 1  # 非池崩溃不重建池


def test_fixed_seed_run_jobs_pool_crash_returns_inflight_card_unchanged(new_gen, monkeypatch, tmp_path):
    """池崩溃：崩溃卡记 infra 后原卡重排；同池在途卡原样退回队首，池被重建，两卡最终用原 seed 成功。"""
    crash = _card(new_gen, "VideoPlaceOrder", 7, 11705, "xhard16")
    inflight = _card(new_gen, "VideoRepick", 46, 13600, "hard", role="mother")
    script = {
        ("VideoPlaceOrder", 7, "xhard16"): [new_gen.BrokenProcessPool("池坏了"), {"ok": True}],
        ("VideoRepick", 46, "hard"): ["hang", {"ok": True}],
    }
    succeeded, exhausted, submitted, lines = _drive(
        new_gen, monkeypatch, tmp_path, [crash, inflight], script, workers=2)

    assert exhausted == []
    assert sorted((r["task"], r["seed"], r["attempt"]) for r in succeeded) == [
        ("VideoPlaceOrder", 11705, 0), ("VideoRepick", 13600, 0)]
    assert submitted.count(crash) == 2 and submitted.count(inflight) == 2
    assert all(job in (crash, inflight) for job in submitted)  # 没有任何 bump 出来的新卡片
    # 第一个池在崩溃后被关闭并重建一个新池
    assert len(_FakePool.instances) == 2 and _FakePool.instances[0].shutdown_calls >= 1
    # 退回在途卡时落一条 infra 记录，seed / attempt 与原卡相同
    returned = [line for line in lines if line.get("error") == "池重建，任务退回队列"]
    assert len(returned) == 1
    assert (returned[0]["task"], returned[0]["seed"], returned[0]["attempt"]) == ("VideoRepick", 13600, 0)
    assert returned[0]["failure_class"] == "infra" and returned[0]["card_role"] == "mother"
    crashed = [line for line in lines if line.get("error_type") == "BrokenProcessPool"]
    assert len(crashed) == 1 and crashed[0]["seed"] == 11705
