"""阶段二：冻结旧入口与新封套加载器的全量对拍，以及建池前的拒绝边界。"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

from scripts import generate_dataset_newseed as gen
from scripts.injection.candidates.io import load_candidates, write_candidates

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts/injection/20260912-contract-v3-10"
CANDIDATES = RUN / "candidates/candidates.jsonl"
SAMPLING = ROOT / "scripts/configs/newtask-v2/native_sampling.json"
BASELINE = "c336390"


@pytest.fixture
def tmp_path():
    """默认 pytest 调用也把生成入口的所有测试产物留在仓库内。"""
    parent = ROOT / "artifacts/test-tmp"
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="candidate-loader-", dir=parent))


@pytest.fixture(scope="module")
def old():
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE}:scripts/generate_dataset_newseed.py"], cwd=ROOT, text=True
    )
    module = types.ModuleType("stage2_legacy_generator")
    module.__file__ = gen.__file__
    sys.modules[module.__name__] = module
    exec(compile(source, gen.__file__, "exec"), module.__dict__)
    module.frozen_source = source
    return module


def kwargs_reader(source):
    """直接执行实际 worker 在 gym.make 之前的 kwargs 语句，不手抄参数表。"""
    worker = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_worker")
    construction = next(n for n in worker.body if isinstance(n, ast.Try)
                        and any(isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
                                and s.target.id == "kwargs" for s in n.body))
    nodes = []
    for node in construction.body:
        if isinstance(node, ast.Assign):
            break
        nodes.append(copy.deepcopy(node))
    function = ast.parse("def read(job):\n    return kwargs\n").body[0]
    function.body = nodes + function.body
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), "<真实参数语句>", "exec"), namespace)
    return namespace["read"]


def test_all_3400_loader_and_kwargs_equal_before_and_after_role_rewrite(old, tmp_path):
    source_sha = hashlib.sha256(CANDIDATES.read_bytes()).hexdigest()
    header, rows = load_candidates(CANDIDATES, repo_root=ROOT)
    legacy_configs = old.load_sampling_config(SAMPLING, ROOT)
    configs = gen.validate_sampling_config(header["sampling_config"], ROOT)
    assert configs == legacy_configs
    before = old.frozen_source
    after = Path(gen.__file__).read_text()
    old_kwargs, new_kwargs = kwargs_reader(before), kwargs_reader(after)
    legacy = {}
    for item in json.loads((RUN / "manifest.json").read_text())["groups"]:
        group = old.load_episode_specs(RUN / item["path"], ROOT, tmp_path / "old")[0]
        for ep, record in group.records.items():
            job = old.EpisodeJob(group.task, ep, 0, old.get_layout("train").seed(group.task, ep, 0),
                                 group.difficulty, str(tmp_path), str(ROOT), legacy_configs[group.task], record)
            legacy[(group.task, group.difficulty, ep)] = old._spec_canonical_json(old_kwargs(job))
    assert len(legacy) == 3400
    for role_rewrite in (False, True):
        path = CANDIDATES
        if role_rewrite:
            rows = copy.deepcopy(rows)
            for row in rows:
                row["role"] = "primary" if row["split"] == "train" else "spare"
                row["error_type"] = None
            path = tmp_path / "rewritten.jsonl"
            write_candidates(path, header, rows)
        read_header = {}
        groups = gen.load_episode_specs(path, ROOT, tmp_path / "new", candidate_header=read_header)
        assert read_header == header
        actual = {}
        for group in groups:
            for ep in group.episodes:
                job = gen.EpisodeJob(group.task, ep, 0, gen.get_layout("train").seed(group.task, ep, 0),
                                     group.difficulty, str(tmp_path), str(ROOT), configs[group.task], group.records[ep],
                                     emit_h5_digest=True)
                actual[(group.task, group.difficulty, ep)] = gen._spec_canonical_json(new_kwargs(job))
        assert actual == legacy
    assert hashlib.sha256(CANDIDATES.read_bytes()).hexdigest() == source_sha
    print("LOADER_PARITY=PASS compared=3400 kwargs_mismatch=0 role_rewrite_mismatch=0")


def capture_jobs(monkeypatch, module):
    captured = []
    def run(**kwargs):
        captured.extend(kwargs["jobs"])
        return [], []
    monkeypatch.setattr(module, "_run_jobs", run)
    return captured


def test_generation_uses_snapshot_and_explicit_digest_flag(old, tmp_path, monkeypatch):
    new_jobs = capture_jobs(monkeypatch, gen)
    old_jobs = capture_jobs(monkeypatch, old)
    gen.generate_dataset_newseed(tmp_path / "jsonl", env="RouteStick", episodes=2, difficulty_ratio="100",
                                 workers=1, max_attempts=1, episode_specs=CANDIDATES)
    old.generate_dataset_newseed(tmp_path / "legacy", env="RouteStick", episodes=2, difficulty_ratio="100",
                                 workers=1, max_attempts=1, episode_specs=RUN / "specs/RouteStick/easy.json",
                                 sampling_config=SAMPLING)
    assert len(new_jobs) == len(old_jobs) == 2
    left, right = kwargs_reader(old.frozen_source), kwargs_reader(Path(gen.__file__).read_text())
    for before, after in zip(old_jobs, new_jobs):
        assert left(before) == right(after)
        assert after.emit_h5_digest is True
    assert gen.EpisodeJob("RouteStick", 0, 0, 16000, "easy", str(tmp_path), str(ROOT)).emit_h5_digest is False
    assert new_jobs[0].sampling_config is not new_jobs[1].sampling_config


@pytest.mark.parametrize("kind", ["json", "none"])
def test_legacy_job_path_unchanged(old, tmp_path, monkeypatch, kind):
    actual = capture_jobs(monkeypatch, gen)
    expected = capture_jobs(monkeypatch, old)
    options = dict(env="RouteStick", episodes=2, workers=1, difficulty_ratio="100", max_attempts=1)
    if kind == "json":
        options.update(episode_specs=RUN / "specs/RouteStick/easy.json", sampling_config=SAMPLING)
    gen.generate_dataset_newseed(tmp_path / "new", **options)
    old.generate_dataset_newseed(tmp_path / "old", **options)
    for left, right in zip(expected, actual):
        assert kwargs_reader(old.frozen_source)(left) == kwargs_reader(Path(gen.__file__).read_text())(right)
        assert right.emit_h5_digest is False
    assert len(actual) == len(expected) == 2


@pytest.mark.parametrize("bad", ["layout", "retry", "external", "test_only", "seed"])
def test_invalid_inputs_rejected_before_pool(tmp_path, monkeypatch, bad):
    captured = capture_jobs(monkeypatch, gen)
    options = dict(env="RouteStick", episodes=1, workers=1, difficulty_ratio="100", max_attempts=1, episode_specs=CANDIDATES)
    if bad == "layout":
        options["layout_name"] = "test"
    elif bad == "retry":
        options["max_attempts"] = 2
    elif bad == "external":
        payload = json.loads(SAMPLING.read_text())
        payload["positions"]["RouteStick"]["grid_spacing_x"] += 0.001
        path = tmp_path / "different.json"
        path.write_text(json.dumps(payload))
        options["sampling_config"] = path
    elif bad == "test_only":
        options["episode_start"] = 115
    else:
        lines = CANDIDATES.read_text().splitlines()
        row = json.loads(lines[1])
        row["seed"] += 1
        lines[1] = json.dumps(row)
        path = tmp_path / "bad.jsonl"
        path.write_text("\n".join(lines) + "\n")
        options["episode_specs"] = path
    with pytest.raises((gen.EpisodeSpecError, gen.SamplingConfigError)):
        gen.generate_dataset_newseed(tmp_path / "rejected", **options)
    assert not captured


def test_jsonl_selection_never_launches_test_candidates(tmp_path):
    groups = gen.load_episode_specs(CANDIDATES, ROOT, tmp_path, candidate_split="train")
    assert sum(len(g.episodes) for g in groups) == 1842
    assert sum(len(g.episodes) for g in gen.load_episode_specs(CANDIDATES, ROOT, tmp_path, candidate_split="test")) == 1558
    with pytest.raises(gen.EpisodeSpecError):
        gen.load_episode_specs(CANDIDATES, ROOT, tmp_path, task="unknown")


def test_digest_reads_final_closed_bytes_and_old_flag_does_nothing(tmp_path):
    # 执行真实散列分支；成品先替换为最终字节，检查读错转换前文件和多读旧路径的回归。
    worker = ast.parse(inspect.getsource(gen._worker)).body[0]
    block = next(n for n in worker.body if isinstance(n, ast.If) and isinstance(n.test, ast.Attribute)
                 and n.test.attr == "emit_h5_digest")
    function = ast.parse("def run(job, raw_path, summary):\n    phases = {}\n    return summary\n").body[0]
    function.body.insert(1, block)
    namespace = {**gen.__dict__, "base": lambda: {}, "binfill_demo": {}, "output_root": tmp_path,
                 "close_error": None, "_video_summary": lambda *a, **k: {}}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), "<真实散列分支>", "exec"), namespace)
    path = tmp_path / "finished.h5"
    job = gen.EpisodeJob("RouteStick", 0, 0, 16000, "easy", str(tmp_path), str(ROOT))
    assert namespace["run"](job, path, {}) == {}
    path.write_bytes(b"final" * 4000)
    result = namespace["run"](gen.replace(job, emit_h5_digest=True), path, {})
    assert result == {"h5_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "h5_bytes": 20000}
    failed = namespace["run"](gen.replace(job, emit_h5_digest=True), tmp_path / "missing.h5", {})
    assert failed["ok"] is False and failed["failure_class"] == "code"
