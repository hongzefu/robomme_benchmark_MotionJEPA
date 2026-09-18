"""reset 的批次停点、缓存复用与 unused 全范围遍历，不启动仿真。"""
import json
import tempfile
from pathlib import Path

from scripts.injection.candidates.io import load_candidates
from tests._shared.frozen_injection import load as frozen_load
old_run = frozen_load("env_check").run_env_check
OldPlan = frozen_load("env_check").EnvCheckPlan
from scripts.injection.rollout.reset_check import run_env_check, EnvCheckPlan
from scripts.injection.rollout.state import ROOT


def test_normal_720_keys_match_old_batches_and_resume_reuses_all():
    header, rows = load_candidates(ROOT / "artifacts/injection/20260912-contract-v3-10/candidates/candidates.jsonl")
    parent = ROOT / "artifacts/test-tmp"
    parent.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="reset-pipeline-", dir=parent))
    docs, plans, old_plans = {}, [], []
    for group in header["delivery_config_snapshot"]["groups"]:
        key = group["task"], group["difficulty"]
        docs[key] = {"episodes": [r["spec"] for r in rows if (r["task"], r["difficulty"]) == key]}
        plans.append(EnvCheckPlan(*key, start=group["run_episodes"], need=50))
        old_plans.append(OldPlan(*key, start=group["run_episodes"], need=50))
    cache = {}
    def success(job):
        return {"task": job.task, "difficulty": job.difficulty, "episode": job.episode, "seed": job.seed,
                "spec_sha256": job.spec_sha256, "ok": True, "injection_bound": True,
                "error_type": None, "error": None, "bound": {"gpu": "0", "pid": 1}, "wall_s": 0.1, "phases": {}}
    def terminal(job, row):
        key = job.task, job.difficulty, job.episode
        assert key not in cache
        cache[key] = row
    common = dict(gpus=["0", "1"], workers_per_gpu=20, sampling_config=None, repo_root=ROOT, submit=success)
    old = old_run(docs, old_plans, out_dir=output / "old", **common)
    new = run_env_check(docs, plans, out_dir=output / "new", on_terminal=terminal, **common)
    assert old["groups"] == new["groups"]
    def read(directory):
        return sorted([json.loads(line) for p in directory.glob("*/*.jsonl") for line in p.read_text().splitlines()],
                      key=lambda r: (r["task"], r["difficulty"], r["episode"]))
    assert read(output / "old") == read(output / "new")
    assert len(cache) == 720
    def forbidden(job):
        raise AssertionError("已有终态不得重复 reset")
    resumed = run_env_check(docs, plans, out_dir=output / "resumed", cached_results=cache,
                           **{**common, "submit": forbidden})
    assert resumed["groups"] == new["groups"]
    assert read(output / "resumed") == read(output / "new")
    unused_docs, unused_plans, seen = {}, [], []
    for group, doc in docs.items():
        start = next(p.start for p in plans if (p.task, p.difficulty) == group)
        records = [r for r in doc["episodes"] if r["episode"] >= start and (*group, r["episode"]) not in cache]
        unused_docs[group] = {"episodes": records}
        unused_plans.append(EnvCheckPlan(*group, start=start, need=len(records)))
    def mixed(job):
        seen.append((job.task, job.difficulty, job.episode))
        result = success(job)
        if job.episode % 7 == 0:
            result.update(ok=False, error_type="SceneGenerationError", failure_class="task")
        return result
    all_result = run_env_check(unused_docs, unused_plans, out_dir=output / "unused", **{**common, "submit": mixed})
    assert len(seen) == len(set(seen)) == 838
    assert len(read(output / "unused")) == 838
    assert sum(g["checked"] for g in all_result["groups"].values()) == 838
    assert sum(g["failed"] for g in all_result["groups"].values()) > 0
    print("RESET_BATCH_PARITY=PASS keys=720 resume_rerun=0 unused_checked=838")
